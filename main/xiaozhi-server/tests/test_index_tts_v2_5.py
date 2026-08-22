import asyncio
import unittest
from unittest.mock import Mock, patch

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
            "log_file": "xiaozhi-index-tts-tests.log",
        }
    },
)

from core.companion.overlay import normalize_overlay
from core.providers.tts.index_tts_v2_5 import TTSProvider


class IndexTTS25ProviderTest(unittest.TestCase):
    def make_provider(self, **overrides):
        config = {
            "api_url": "http://192.168.18.14:8092",
            "voice": "fallback-voice",
            "private_voice": "tuniang-normal",
            "language": "普通话",
            "speed": 1.0,
            "dynamic_emotion": True,
            "emotion_alpha": 0.85,
            "normalize_emotion": True,
            "tts_timeout": 60,
        }
        config.update(overrides)
        return TTSProvider(config, delete_audio_file=True)

    def test_companion_style_builds_eight_axis_emotion(self):
        provider = self.make_provider()
        provider.set_emotion_style("happy", 0.8, enabled=True)

        payload = provider.build_request("你好呀")

        self.assertEqual("tuniang-normal", payload["voice_id"])
        self.assertEqual("ZH", payload["lang"])
        self.assertEqual(8, len(payload["emotion"]["vector"]))
        self.assertEqual(0.75, payload["emotion"]["vector"][0])
        self.assertAlmostEqual(0.748, payload["emotion"]["alpha"])
        self.assertTrue(payload["emotion"]["normalize"])

    def test_binding_switch_off_omits_emotion(self):
        provider = self.make_provider()
        provider.set_emotion_style("excited", 1.0, enabled=False)

        self.assertNotIn("emotion", provider.build_request("你好"))

    def test_model_switch_off_cannot_be_overridden_by_binding(self):
        provider = self.make_provider(dynamic_emotion=False)
        provider.set_emotion_style("excited", 1.0, enabled=True)

        self.assertNotIn("emotion", provider.build_request("你好"))

    def test_invalid_style_uses_neutral_vector_and_clamps_intensity(self):
        provider = self.make_provider()
        provider.set_emotion_style("not-a-style", 2.5, enabled=True)

        payload = provider.build_request("你好")

        self.assertEqual("neutral", provider.current_emotion_style)
        self.assertEqual(1.0, provider.current_emotion_intensity)
        self.assertEqual(provider.emotion_vector_map["neutral"], payload["emotion"]["vector"])

    @patch("core.providers.tts.index_tts_v2_5.requests.post")
    def test_tts_calls_stable_wav_endpoint(self, post):
        response = Mock(status_code=200, content=b"RIFF-test")
        post.return_value = response
        provider = self.make_provider()

        audio = asyncio.run(provider.text_to_speak("测试", None))

        self.assertEqual(b"RIFF-test", audio)
        args, kwargs = post.call_args
        self.assertEqual("http://192.168.18.14:8092/v1/tts", args[0])
        self.assertEqual(60.0, kwargs["timeout"])
        self.assertEqual("测试", kwargs["json"]["text"])

    def test_overlay_preserves_explicit_dynamic_emotion_choice(self):
        self.assertFalse(normalize_overlay({"tts_dynamic_emotion": False})["tts_dynamic_emotion"])
        self.assertTrue(normalize_overlay({"tts_dynamic_emotion": True})["tts_dynamic_emotion"])


if __name__ == "__main__":
    unittest.main()
