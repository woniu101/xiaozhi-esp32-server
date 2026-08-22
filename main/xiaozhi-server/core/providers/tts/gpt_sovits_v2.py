import asyncio
import math
import time

import aiohttp
from config.logger import setup_logging
from core.providers.tts.base import TTSProviderBase
from core.providers.tts.http_client import get_json, post_audio
from core.providers.tts.streaming_support import SingleStreamTTSMixin
from core.utils.util import parse_string_to_list

TAG = __name__
logger = setup_logging()


def _stream_mode(value):
    if isinstance(value, bool):
        return 1 if value else 0
    text = str(value if value is not None else "0").strip().lower()
    if text in ("true", "yes", "on"):
        return 1
    if text in ("false", "no", "off", ""):
        return 0
    try:
        return max(0, min(3, int(text)))
    except ValueError:
        return 0


def _finite_number(value, default, minimum, maximum):
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(parsed):
        return default
    return max(minimum, min(maximum, parsed))


class TTSProvider(SingleStreamTTSMixin, TTSProviderBase):
    def __init__(self, config, delete_audio_file):
        super().__init__(config, delete_audio_file)
        self.url = config.get("url")
        self.text_lang = config.get("text_lang", "zh")
        self.ref_audio_path = config.get('ref_audio') if config.get('ref_audio') else config.get("ref_audio_path")
        self.prompt_text = config.get('ref_text') if config.get('ref_text') else config.get("prompt_text")
        self.prompt_lang = config.get("prompt_lang", "zh")
        configured_presets = config.get("emotion_presets", {})
        self.emotion_presets = configured_presets if isinstance(configured_presets, dict) else {}

        # 处理空字符串的情况
        top_k = config.get("top_k", "5")
        top_p = config.get("top_p", "1")
        temperature = config.get("temperature", "1")
        batch_threshold = config.get("batch_threshold", "0.75")
        batch_size = config.get("batch_size", "1")
        speed_factor = config.get("speed_factor", "1.0")
        seed = config.get("seed", "-1")
        repetition_penalty = config.get("repetition_penalty", "1.35")

        self.top_k = int(top_k) if top_k else 5
        self.top_p = float(top_p) if top_p else 1
        self.temperature = float(temperature) if temperature else 1
        self.batch_threshold = float(batch_threshold) if batch_threshold else 0.75
        self.batch_size = int(batch_size) if batch_size else 1
        self.speed_factor = float(speed_factor) if speed_factor else 1.0
        self.seed = int(seed) if seed else -1
        self.repetition_penalty = (
            float(repetition_penalty) if repetition_penalty else 1.35
        )

        self.text_split_method = config.get("text_split_method", "cut0")

        self.split_bucket = str(config.get("split_bucket", True)).lower() in (
            "true",
            "1",
            "yes",
        )
        self.return_fragment = str(config.get("return_fragment", False)).lower() in (
            "true",
            "1",
            "yes",
        )

        self.streaming_mode = _stream_mode(config.get("streaming_mode", 0))

        self.parallel_infer = str(config.get("parallel_infer", True)).lower() in (
            "true",
            "1",
            "yes",
        )

        self.aux_ref_audio_paths = parse_string_to_list(
            config.get("aux_ref_audio_paths")
        )
        self.audio_file_type = config.get("format", "wav")
        self.stream_sample_rate = int(
            _finite_number(config.get("stream_sample_rate", 32000), 32000, 8000, 48000)
        )
        self.stream_chunk_size = int(
            _finite_number(config.get("stream_chunk_size", 8192), 8192, 1024, 65536)
        )
        self.fragment_interval = _finite_number(
            config.get("fragment_interval", 0.3), 0.3, 0.05, 2.0
        )
        self.overlap_length = int(
            _finite_number(config.get("overlap_length", 2), 2, 0, 16)
        )
        self.min_chunk_length = int(
            _finite_number(config.get("min_chunk_length", 16), 16, 4, 128)
        )
        self.stream_fallback = str(config.get("stream_fallback", True)).lower() in (
            "true",
            "1",
            "yes",
        )
        self.health_url = f"{str(self.url).rstrip('/').rsplit('/tts', 1)[0]}/openapi.json"
        self.configure_single_stream(self.streaming_mode > 0)

    def get_capabilities(self) -> dict:
        return {
            **super().get_capabilities(),
            "streaming": self.streaming_enabled,
            "streaming_mode": "raw-pcm" if self.streaming_enabled else "disabled",
            "dynamic_emotion": self.dynamic_emotion_enabled,
            "emotion_control": "reference-preset",
            "health_check": True,
            "voice_management": "reference-audio",
        }

    def _active_emotion_preset(self):
        if not self.current_dynamic_emotion_enabled:
            return {}
        style = self.provider_emotion_style() or self.current_emotion_style
        preset = self.emotion_presets.get(style, {})
        return preset if isinstance(preset, dict) else {}

    def _blend_preset_number(self, preset, key, base, minimum, maximum):
        if key not in preset:
            return base
        target = _finite_number(preset.get(key), base, minimum, maximum)
        intensity = self.current_emotion_intensity
        return base + (target - base) * intensity

    def build_request(self, text, streaming=False):
        preset = self._active_emotion_preset()
        ref_audio_path = (
            preset.get("ref_audio_path")
            or preset.get("ref_audio")
            or self.ref_audio_path
        )
        prompt_text = preset.get("prompt_text", preset.get("ref_text", self.prompt_text))
        prompt_lang = preset.get("prompt_lang", self.prompt_lang)
        aux_ref_audio_paths = preset.get("aux_ref_audio_paths", self.aux_ref_audio_paths)
        if not isinstance(aux_ref_audio_paths, list):
            aux_ref_audio_paths = parse_string_to_list(aux_ref_audio_paths)

        speed_factor = self._blend_preset_number(
            preset, "speed_factor", self.speed_factor, 0.5, 2.0
        )
        temperature = self._blend_preset_number(
            preset, "temperature", self.temperature, 0.1, 2.0
        )
        top_p = self._blend_preset_number(preset, "top_p", self.top_p, 0.05, 1.0)
        top_k = round(
            self._blend_preset_number(preset, "top_k", self.top_k, 1, 100)
        )

        return {
            "text": text,
            "text_lang": self.text_lang,
            "ref_audio_path": ref_audio_path,
            "aux_ref_audio_paths": aux_ref_audio_paths,
            "prompt_text": prompt_text,
            "prompt_lang": prompt_lang,
            "top_k": top_k,
            "top_p": round(top_p, 4),
            "temperature": round(temperature, 4),
            "text_split_method": self.text_split_method,
            "batch_size": self.batch_size,
            "batch_threshold": self.batch_threshold,
            "split_bucket": self.split_bucket,
            "return_fragment": bool(streaming and self.return_fragment),
            "speed_factor": round(speed_factor, 4),
            "fragment_interval": self.fragment_interval,
            "media_type": "raw" if streaming else self.audio_file_type,
            "streaming_mode": self.streaming_mode if streaming else 0,
            "overlap_length": self.overlap_length,
            "min_chunk_length": self.min_chunk_length,
            "seed": self.seed,
            "parallel_infer": self.parallel_infer,
            "repetition_penalty": self.repetition_penalty,
        }

    async def text_to_speak(self, text, output_file):
        started_at = time.perf_counter()
        resp = await post_audio(
            self.url,
            self.build_request(text, streaming=False),
            self.tts_timeout,
            accept=f"audio/{self.audio_file_type}",
        )
        if resp.status_code == 200:
            if self.audio_file_type == "wav" and not resp.content.startswith(b"RIFF"):
                raise RuntimeError("GPT-SoVITS V2 返回的内容不是有效 WAV 音频")
            self.record_synthesis_metrics(
                mode="non-stream",
                elapsed_seconds=round(time.perf_counter() - started_at, 4),
                audio_bytes=len(resp.content),
            )
            if output_file:
                with open(output_file, "wb") as file:
                    file.write(resp.content)
            else:
                return resp.content
        else:
            error_msg = f"GPT_SoVITS_V2 TTS请求失败: {resp.status_code} - {resp.text}"
            logger.bind(tag=TAG).error(error_msg)
            raise Exception(error_msg)

    async def stream_text_to_speak(self, text):
        started_at = time.perf_counter()
        first_chunk_at = None
        input_bytes = 0
        response = None
        timeout = aiohttp.ClientTimeout(
            total=self.tts_timeout,
            connect=min(10.0, self.tts_timeout),
            sock_read=self.tts_timeout,
        )
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(
                    self.url,
                    json=self.build_request(text, streaming=True),
                    headers={"Accept": "audio/raw"},
                ) as response:
                    if response.status != 200:
                        details = (await response.text()).strip().replace("\n", " ")[:500]
                        raise RuntimeError(
                            f"GPT-SoVITS V2 流式请求失败: {response.status}"
                            + (f" - {details}" if details else "")
                        )
                    self.register_active_stream(response)
                    transcoder = self.ensure_stream_transcoder(self.stream_sample_rate)
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
        except (aiohttp.ClientError, asyncio.TimeoutError, RuntimeError) as exc:
            if (
                not self.synthesis_cancelled()
                and input_bytes == 0
                and self.stream_fallback
            ):
                logger.bind(tag=TAG).warning(
                    f"GPT-SoVITS V2 流式接口首包前失败，安全降级整段 WAV: {exc}"
                )
                await self._stream_from_wav_fallback(text, started_at)
                return
            if not self.synthesis_cancelled():
                raise RuntimeError(f"GPT-SoVITS V2 流式连接失败: {exc}") from exc
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
            status_code, _ = await get_json(
                self.health_url,
                min(5.0, self.tts_timeout),
            )
            return {
                "ok": status_code == 200,
                "status_code": status_code,
            }
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as exc:
            return {"ok": False, "error": str(exc)}
