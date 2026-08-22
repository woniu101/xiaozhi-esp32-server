import asyncio
from io import BytesIO
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch
import wave

from config import settings
from core.utils.cache.manager import CacheType, cache_manager


settings.config_file_valid = True
cache_manager.set(
    CacheType.CONFIG,
    "main_config",
    {
        "log": {
            "log_level": "ERROR",
            "log_dir": "/tmp",
            "log_file": "xiaozhi-gpt-sovits-v2-tests.log",
        }
    },
)

from core.providers.tts.gpt_sovits_v2 import TTSProvider
from core.providers.tts.http_client import HttpAudioResponse


class GptSovitsV2ProviderTest(unittest.TestCase):
    def make_provider(self, **overrides):
        config = {
            "url": "http://192.168.18.14:9880/tts",
            "text_lang": "zh",
            "ref_audio_path": "reference/neutral.wav",
            "prompt_text": "中性参考文本",
            "prompt_lang": "zh",
            "dynamic_emotion": True,
            "streaming_mode": 2,
            "stream_sample_rate": 32000,
            "speed_factor": 1.0,
            "temperature": 1.0,
            "top_p": 1.0,
            "top_k": 5,
            "emotion_presets": {
                "warm": {
                    "ref_audio_path": "reference/warm.wav",
                    "prompt_text": "温柔参考文本",
                    "speed_factor": 0.8,
                    "temperature": 0.8,
                    "top_p": 0.8,
                }
            },
            "tts_timeout": 60,
        }
        config.update(overrides)
        return TTSProvider(config, delete_audio_file=True)

    def test_companion_style_routes_reference_and_blends_parameters(self):
        provider = self.make_provider()
        provider.set_emotion_style("warm", 0.5, enabled=True)

        payload = provider.build_request("你好", streaming=True)

        self.assertEqual("reference/warm.wav", payload["ref_audio_path"])
        self.assertEqual("温柔参考文本", payload["prompt_text"])
        self.assertEqual(0.9, payload["speed_factor"])
        self.assertEqual(0.9, payload["temperature"])
        self.assertEqual(0.9, payload["top_p"])
        self.assertEqual("raw", payload["media_type"])
        self.assertEqual(2, payload["streaming_mode"])

    def test_binding_switch_off_keeps_base_reference(self):
        provider = self.make_provider()
        provider.set_emotion_style("warm", 1.0, enabled=False)

        payload = provider.build_request("你好", streaming=False)

        self.assertEqual("reference/neutral.wav", payload["ref_audio_path"])
        self.assertEqual("中性参考文本", payload["prompt_text"])
        self.assertEqual(0, payload["streaming_mode"])
        self.assertEqual("wav", payload["media_type"])

    def test_reports_reference_preset_and_raw_stream_capabilities(self):
        capabilities = self.make_provider().get_capabilities()

        self.assertTrue(capabilities["streaming"])
        self.assertEqual("raw-pcm", capabilities["streaming_mode"])
        self.assertEqual("reference-preset", capabilities["emotion_control"])

    @patch("core.providers.tts.gpt_sovits_v2.post_audio", new_callable=AsyncMock)
    def test_non_stream_preview_forces_wav_response(self, post):
        post.return_value = HttpAudioResponse(200, b"RIFF-test", "", {})
        provider = self.make_provider()

        audio = asyncio.run(provider.text_to_speak("测试", None))

        self.assertEqual(b"RIFF-test", audio)
        payload = post.call_args.args[1]
        self.assertEqual(0, payload["streaming_mode"])
        self.assertEqual("wav", payload["media_type"])

    def test_stream_fallback_converts_wav_to_device_pcm(self):
        wav_buffer = BytesIO()
        with wave.open(wav_buffer, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(32000)
            wav_file.writeframes(b"\x00\x00" * 32000)
        provider = self.make_provider()
        provider.conn = SimpleNamespace(
            sample_rate=24000,
            audio_format="pcm",
            client_abort=False,
        )
        provider._stream_segment_text = "GPT 降级测试"
        provider.text_to_speak = AsyncMock(return_value=wav_buffer.getvalue())

        asyncio.run(provider._stream_from_wav_fallback("GPT 降级测试", 0.0))
        provider._finish_stream_state()

        self.assertEqual("stream-fallback-wav", provider.last_synthesis_metrics["mode"])
        self.assertEqual(18, provider.tts_audio_queue.qsize())


if __name__ == "__main__":
    unittest.main()
