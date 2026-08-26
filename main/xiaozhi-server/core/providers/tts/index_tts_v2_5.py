import asyncio
from io import BytesIO
import math
import os
import time
import uuid
import wave

import aiohttp

from config.logger import setup_logging
from core.providers.tts.base import TTSProviderBase
from core.providers.tts.http_client import (
    MAX_ERROR_RESPONSE_BYTES,
    decode_response_body,
    get_json,
    post_audio,
    read_bounded,
    validate_content_length,
)
from core.providers.tts.streaming_support import SingleStreamTTSMixin
from core.utils.tts import convert_percentage_to_range


TAG = __name__
logger = setup_logging()
MAX_STREAM_RESPONSE_BYTES = 64 * 1024 * 1024
_INDEX_TTS_COMPAT_TRANSLATION = str.maketrans(
    {
        # Some Windows IndexTTS2.5 deployments still encode inference text with
        # GBK. Katakana middle dot is not representable there; the visually and
        # phonetically equivalent GBK middle dot is safe. This translation is
        # applied only to the remote synthesis payload, never subtitles/history.
        "・": "·",
    }
)


def _finite_float(value, default, minimum, maximum):
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(parsed):
        return default
    return max(minimum, min(maximum, parsed))


def _as_bool(value, default=False):
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() in ("true", "1", "yes", "on")


def _normalize_language(value):
    text = str(value or "zh").strip().lower()
    aliases = {
        "中文": "zh",
        "普通话": "zh",
        "zh-cn": "zh",
        "英语": "en",
        "英文": "en",
        "日语": "ja",
        "jp": "ja",
        "韩语": "ko",
        "kr": "ko",
    }
    return aliases.get(text, text)


def _normalize_api_urls(value):
    base_url = str(value or "http://127.0.0.1:8092").strip().rstrip("/")
    if base_url.endswith("/v1/tts/stream"):
        base_url = base_url[: -len("/stream")]
    api_url = base_url if base_url.endswith("/v1/tts") else f"{base_url}/v1/tts"
    service_root = api_url[: -len("/v1/tts")]
    return api_url, f"{api_url}/stream", f"{service_root}/health/ready"


def _normalize_synthesis_text(value):
    return str(value or "").translate(_INDEX_TTS_COMPAT_TRANSLATION)


def _validate_wav(audio: bytes) -> None:
    if not audio or not audio.startswith(b"RIFF"):
        raise RuntimeError("IndexTTS2.5 返回的内容不是有效 WAV 音频")
    try:
        with wave.open(BytesIO(audio), "rb") as wav_file:
            sample_rate = wav_file.getframerate()
            if sample_rate < 8000 or sample_rate > 192000:
                raise RuntimeError("IndexTTS2.5 返回的 WAV 采样率不受支持")
            frame_count = wav_file.getnframes()
            if frame_count <= 0:
                raise RuntimeError("IndexTTS2.5 返回的 WAV 不包含有效音频帧")
            channels = wav_file.getnchannels()
            if channels not in (1, 2):
                raise RuntimeError("IndexTTS2.5 返回的 WAV 声道数不受支持")
            sample_width = wav_file.getsampwidth()
            if sample_width not in (1, 2, 3, 4):
                raise RuntimeError("IndexTTS2.5 返回的 WAV 采样宽度不受支持")
            if len(wav_file.readframes(frame_count)) != frame_count * channels * sample_width:
                raise RuntimeError("IndexTTS2.5 返回的 WAV 音频数据不完整")
    except (EOFError, wave.Error) as exc:
        raise RuntimeError("IndexTTS2.5 返回的内容不是有效 WAV 音频") from exc


class TTSProvider(SingleStreamTTSMixin, TTSProviderBase):
    """IndexTTS2.5 HTTP adapter with safe segment-stream fallback."""

    def __init__(self, config, delete_audio_file):
        normalized_config = dict(config)
        normalized_config["tts_timeout"] = _finite_float(
            config.get("tts_timeout"), 60.0, 1.0, 300.0
        )
        super().__init__(normalized_config, delete_audio_file)
        self.api_url, self.stream_api_url, self.health_url = _normalize_api_urls(
            normalized_config.get("api_url")
        )
        self.voice = str(
            normalized_config.get("private_voice")
            or normalized_config.get("voice")
            or "tuniang-normal"
        ).strip()
        self.lang = _normalize_language(
            normalized_config.get("language") or normalized_config.get("lang") or "zh"
        )
        self.speed = _finite_float(
            normalized_config.get("speed", 1.0), 1.0, 0.5, 2.0
        )
        if "ttsRate" in normalized_config:
            tts_rate = _finite_float(
                normalized_config["ttsRate"], 0.0, -100.0, 100.0
            )
            self.speed = round(
                convert_percentage_to_range(
                    tts_rate, min_val=0.5, max_val=2.0, base_val=self.speed
                ),
                2,
            )
        self.text_normalization = _as_bool(
            normalized_config.get("text_normalization"), True
        )
        self.stream_chunk_size = int(
            _finite_float(
                normalized_config.get("stream_chunk_size", 8192),
                8192,
                1024,
                65536,
            )
        )
        self.stream_fallback = _as_bool(
            normalized_config.get("stream_fallback"), True
        )
        self.audio_file_type = "wav"
        self.configure_single_stream(
            _as_bool(normalized_config.get("streaming"), True)
        )

    def build_request(self, text):
        # Keep this contract intentionally small. Character/emotion policy belongs
        # to the dot-skill layer rather than this standard voice provider.
        synthesis_text = _normalize_synthesis_text(text)
        if synthesis_text != text:
            logger.bind(tag=TAG).info(
                "IndexTTS2.5 请求文本已做服务端编码兼容，展示原文保持不变"
            )
        return {
            "request_id": uuid.uuid4().hex,
            "text": synthesis_text,
            "voice_id": self.voice,
            "lang": self.lang,
            "speed": self.speed,
            "text_normalization": self.text_normalization,
        }

    async def text_to_speak(self, text, output_file):
        response = await post_audio(
            self.api_url,
            self.build_request(text),
            self.tts_timeout,
            accept="audio/wav",
        )
        if response.status_code != 200:
            details = (response.text or "").strip().replace("\n", " ")[:500]
            error_msg = (
                f"IndexTTS2.5 TTS请求失败: {response.status_code}"
                + (f" - {details}" if details else "")
            )
            raise RuntimeError(error_msg)
        _validate_wav(response.content)
        if output_file:
            parent = os.path.dirname(output_file)
            if parent:
                os.makedirs(parent, exist_ok=True)
            with open(output_file, "wb") as file:
                file.write(response.content)
            return None
        return response.content

    @staticmethod
    def _validate_stream_headers(headers):
        audio_format = str(headers.get("X-Audio-Format", "pcm_s16le_mono")).lower()
        if audio_format not in ("pcm_s16le_mono", "pcm_s16le"):
            raise RuntimeError(f"IndexTTS2.5 流式音频格式不受支持: {audio_format}")
        try:
            source_rate = int(headers.get("X-Sample-Rate", "22050"))
        except (TypeError, ValueError) as exc:
            raise RuntimeError("IndexTTS2.5 流式采样率无效") from exc
        if source_rate < 8000 or source_rate > 192000:
            raise RuntimeError(f"IndexTTS2.5 流式采样率无效: {source_rate}")
        return source_rate

    async def stream_text_to_speak(self, text):
        timeout = aiohttp.ClientTimeout(
            total=self.tts_timeout,
            connect=min(10.0, self.tts_timeout),
            sock_read=self.tts_timeout,
        )
        response = None
        packets_before = self._stream_packet_count
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    self.stream_api_url,
                    json=self.build_request(text),
                    headers={"Accept": "application/octet-stream"},
                    allow_redirects=False,
                ) as response:
                    if response.status != 200:
                        error_body = await read_bounded(
                            response, MAX_ERROR_RESPONSE_BYTES
                        )
                        details = (
                            decode_response_body(response, error_body)
                            .strip()
                            .replace("\n", " ")[:500]
                        )
                        raise RuntimeError(
                            f"IndexTTS2.5 流式请求失败: {response.status}"
                            + (f" - {details}" if details else "")
                        )
                    source_rate = self._validate_stream_headers(response.headers)
                    validate_content_length(
                        response.headers, MAX_STREAM_RESPONSE_BYTES
                    )
                    self.register_active_stream(response)
                    transcoder = self.ensure_stream_transcoder(source_rate)
                    received_bytes = 0
                    async for chunk in response.content.iter_chunked(
                        self.stream_chunk_size
                    ):
                        if self.synthesis_cancelled():
                            response.close()
                            return
                        if chunk:
                            received_bytes += len(chunk)
                            if received_bytes > MAX_STREAM_RESPONSE_BYTES:
                                response.close()
                                raise RuntimeError(
                                    "IndexTTS2.5 流式响应超过安全大小限制"
                                )
                            transcoder.feed(chunk)
                    if received_bytes == 0:
                        raise RuntimeError("IndexTTS2.5 流式接口返回了空音频")
                    if received_bytes % 2 != 0:
                        raise RuntimeError("IndexTTS2.5 流式接口返回了不完整的 PCM 样本")
        except (
            aiohttp.ClientError,
            asyncio.TimeoutError,
            RuntimeError,
            ValueError,
        ) as exc:
            emitted_packets = self._stream_packet_count - packets_before
            if (
                not self.synthesis_cancelled()
                and emitted_packets == 0
                and self.stream_fallback
            ):
                logger.bind(tag=TAG).warning(
                    f"IndexTTS2.5 流式接口首包前失败，安全降级整段 WAV: {exc}"
                )
                self.reset_stream_for_fallback()
                await self._stream_from_wav_fallback(text)
                return
            if not self.synthesis_cancelled():
                raise RuntimeError(f"IndexTTS2.5 流式连接失败: {exc}") from exc
        finally:
            if response is not None:
                self.clear_active_stream(response)

    async def _stream_from_wav_fallback(self, text):
        audio = await self.text_to_speak(text, None)
        if not self.synthesis_cancelled():
            self.feed_wav_to_stream(audio)

    async def health_check(self) -> dict:
        started_at = time.perf_counter()
        try:
            status_code, payload = await get_json(
                self.health_url,
                min(5.0, self.tts_timeout),
            )
            return {
                "ok": status_code == 200 and payload.get("status") == "ready",
                "status_code": status_code,
                "latency_ms": round((time.perf_counter() - started_at) * 1000, 1),
                "details": payload,
            }
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as exc:
            return {"ok": False, "error": str(exc)}

    async def close(self):
        self.cancel_current_synthesis()
        await super().close()
        if hasattr(self, "opus_encoder") and self.opus_encoder is not None:
            self.opus_encoder.close()
