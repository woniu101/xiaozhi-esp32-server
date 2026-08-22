import asyncio
import math
import time
import uuid

import aiohttp

from config.logger import setup_logging
from core.providers.tts.base import TTSProviderBase
from core.providers.tts.http_client import get_json, post_audio
from core.providers.tts.streaming_support import SingleStreamTTSMixin
from core.utils.tts import convert_percentage_to_range


TAG = __name__
logger = setup_logging()


# IndexTTS2.5 emotion order:
# happy, angry, sad, afraid, disgusted, melancholic, surprised, calm.
DEFAULT_EMOTION_VECTOR_MAP = {
    "neutral": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.65],
    "warm": [0.30, 0.0, 0.0, 0.0, 0.0, 0.05, 0.05, 0.55],
    "happy": [0.75, 0.0, 0.0, 0.0, 0.0, 0.0, 0.15, 0.20],
    "excited": [0.85, 0.0, 0.0, 0.0, 0.0, 0.0, 0.45, 0.05],
    "concerned": [0.0, 0.0, 0.25, 0.15, 0.0, 0.40, 0.0, 0.45],
    "soft": [0.10, 0.0, 0.05, 0.0, 0.0, 0.15, 0.0, 0.70],
    "apologetic": [0.0, 0.0, 0.35, 0.05, 0.0, 0.40, 0.0, 0.45],
    "restrained": [0.0, 0.05, 0.05, 0.0, 0.0, 0.20, 0.0, 0.65],
}


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


def _emotion_vectors(configured):
    result = {key: list(value) for key, value in DEFAULT_EMOTION_VECTOR_MAP.items()}
    if not isinstance(configured, dict):
        return result
    for style, vector in configured.items():
        if style not in result or not isinstance(vector, (list, tuple)) or len(vector) != 8:
            continue
        parsed = []
        for value in vector:
            try:
                item = float(value)
            except (TypeError, ValueError):
                parsed = []
                break
            if not math.isfinite(item):
                parsed = []
                break
            parsed.append(max(0.0, min(1.2, item)))
        if parsed:
            result[style] = parsed
    return result


class TTSProvider(SingleStreamTTSMixin, TTSProviderBase):
    """Adapter for the dedicated IndexTTS2.5 Companion API service."""

    def __init__(self, config, delete_audio_file):
        super().__init__(config, delete_audio_file)
        base_url = str(config.get("api_url") or "http://127.0.0.1:8092").strip().rstrip("/")
        self.api_url = base_url if base_url.endswith("/v1/tts") else f"{base_url}/v1/tts"
        self.stream_api_url = f"{self.api_url}/stream"
        self.health_url = f"{self.api_url.rsplit('/v1/tts', 1)[0]}/health/ready"
        self.voice = str(config.get("private_voice") or config.get("voice") or "tuniang-normal").strip()
        self.lang = _normalize_language(config.get("language") or config.get("lang") or "zh")
        self.speed = _finite_float(config.get("speed", 1.0), 1.0, 0.5, 2.0)
        if "ttsRate" in config:
            self.speed = round(
                convert_percentage_to_range(
                    config["ttsRate"], min_val=0.5, max_val=2.0, base_val=self.speed
                ),
                2,
            )
        self.emotion_alpha = _finite_float(config.get("emotion_alpha", 0.85), 0.85, 0.0, 1.0)
        self.normalize_emotion = _as_bool(config.get("normalize_emotion"), True)
        self.text_normalization = _as_bool(config.get("text_normalization"), True)
        self.emotion_vector_map = _emotion_vectors(config.get("emotion_vector_map"))
        self.stream_chunk_size = int(
            _finite_float(config.get("stream_chunk_size", 8192), 8192, 1024, 65536)
        )
        self.stream_fallback = _as_bool(config.get("stream_fallback"), True)
        self.interval_silence_ms = int(
            _finite_float(config.get("interval_silence_ms", 80), 80, 0, 1000)
        )
        self.max_text_tokens_per_segment = int(
            _finite_float(
                config.get("max_text_tokens_per_segment", 80), 80, 20, 240
            )
        )
        self.audio_file_type = "wav"
        self.configure_single_stream(_as_bool(config.get("streaming"), True))

    def get_capabilities(self) -> dict:
        return {
            **super().get_capabilities(),
            "streaming": self.streaming_enabled,
            "streaming_mode": "segment-pcm",
            "dynamic_emotion": self.dynamic_emotion_enabled,
            "emotion_control": "eight-axis-vector",
            "health_check": True,
            "voice_management": True,
        }

    def build_request(self, text):
        payload = {
            "request_id": uuid.uuid4().hex,
            "text": text,
            "voice_id": self.voice,
            "lang": self.lang,
            "speed": self.speed,
            "interval_silence_ms": self.interval_silence_ms,
            "max_text_tokens_per_segment": self.max_text_tokens_per_segment,
            "text_normalization": self.text_normalization,
        }
        if self.current_dynamic_emotion_enabled:
            # Presentation intensity changes how strongly the selected direction is
            # applied, while the provider keeps the same stable eight-axis contract.
            alpha = self.emotion_alpha * (0.4 + 0.6 * self.current_emotion_intensity)
            payload["emotion"] = {
                "vector": list(
                    self.emotion_vector_map.get(
                        self.current_emotion_style,
                        self.emotion_vector_map["neutral"],
                    )
                ),
                "alpha": round(max(0.0, min(1.0, alpha)), 4),
                "normalize": self.normalize_emotion,
            }
        return payload

    async def text_to_speak(self, text, output_file):
        started_at = time.perf_counter()
        response = await post_audio(
            self.api_url,
            self.build_request(text),
            self.tts_timeout,
            accept="audio/wav",
        )
        elapsed = time.perf_counter() - started_at
        if response.status_code != 200:
            details = (response.text or "").strip().replace("\n", " ")[:500]
            error_msg = (
                f"IndexTTS2.5 TTS请求失败: {response.status_code}"
                + (f" - {details}" if details else "")
            )
            logger.bind(tag=TAG).error(error_msg)
            raise RuntimeError(error_msg)
        if not response.content.startswith(b"RIFF"):
            raise RuntimeError("IndexTTS2.5 返回的内容不是有效 WAV 音频")
        self.record_synthesis_metrics(
            mode="non-stream",
            elapsed_seconds=round(elapsed, 4),
            audio_bytes=len(response.content),
            rtf=response.headers.get("X-RTF") if response.headers else None,
        )
        if output_file:
            with open(output_file, "wb") as file:
                file.write(response.content)
            return None
        return response.content

    async def stream_text_to_speak(self, text):
        started_at = time.perf_counter()
        timeout = aiohttp.ClientTimeout(
            total=self.tts_timeout,
            connect=min(10.0, self.tts_timeout),
            sock_read=self.tts_timeout,
        )
        response = None
        first_chunk_at = None
        input_bytes = 0
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    self.stream_api_url,
                    json=self.build_request(text),
                    headers={"Accept": "application/octet-stream"},
                ) as response:
                    if response.status != 200:
                        details = (await response.text()).strip().replace("\n", " ")[:500]
                        raise RuntimeError(
                            f"IndexTTS2.5 流式请求失败: {response.status}"
                            + (f" - {details}" if details else "")
                        )
                    self.register_active_stream(response)
                    source_rate = int(response.headers.get("X-Sample-Rate", "22050"))
                    transcoder = self.ensure_stream_transcoder(source_rate)
                    async for chunk in response.content.iter_chunked(self.stream_chunk_size):
                        if self.synthesis_cancelled():
                            response.close()
                            break
                        if not chunk:
                            continue
                        if first_chunk_at is None:
                            first_chunk_at = time.perf_counter()
                        input_bytes += len(chunk)
                        transcoder.feed(chunk)
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            if (
                not self.synthesis_cancelled()
                and input_bytes == 0
                and self.stream_fallback
            ):
                logger.bind(tag=TAG).warning(
                    f"IndexTTS2.5 流式接口首包前失败，安全降级整段 WAV: {exc}"
                )
                await self._stream_from_wav_fallback(text, started_at)
                return
            if not self.synthesis_cancelled():
                raise RuntimeError(f"IndexTTS2.5 流式连接失败: {exc}") from exc
        finally:
            if response is not None:
                self.clear_active_stream(response)
        completed_at = time.perf_counter()
        self.record_synthesis_metrics(
            mode="stream",
            elapsed_seconds=round(completed_at - started_at, 4),
            first_audio_seconds=(
                round(first_chunk_at - started_at, 4) if first_chunk_at else None
            ),
            audio_bytes=input_bytes,
            cancelled=self.synthesis_cancelled(),
        )

    async def _stream_from_wav_fallback(self, text, started_at):
        audio = await self.text_to_speak(text, None)
        if self.synthesis_cancelled():
            return
        pcm_bytes = self.feed_wav_to_stream(audio)
        self.record_synthesis_metrics(
            mode="stream-fallback-wav",
            elapsed_seconds=round(time.perf_counter() - started_at, 4),
            first_audio_seconds=None,
            audio_bytes=pcm_bytes,
            cancelled=False,
        )

    async def health_check(self) -> dict:
        try:
            status_code, payload = await get_json(
                self.health_url,
                min(5.0, self.tts_timeout),
            )
            return {
                "ok": status_code == 200 and bool(payload.get("ready")),
                "status_code": status_code,
                "details": payload,
            }
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as exc:
            return {"ok": False, "error": str(exc)}
