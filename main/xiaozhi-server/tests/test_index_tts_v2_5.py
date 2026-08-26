import asyncio
from io import BytesIO
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import AsyncMock, patch
import wave

import aiohttp

# Avoid contacting manager-api while importing modules that initialize logging.
from core.utils.cache.manager import CacheType, cache_manager


cache_manager.set(
    CacheType.CONFIG,
    "main_config",
    {
        "log": {
            "log_level": "ERROR",
            "log_dir": "tmp",
            "log_file": "test.log",
        }
    },
)

from core.providers.tts.http_client import HttpAudioResponse, read_bounded
from core.providers.tts.index_tts_v2_5 import TTSProvider


def make_wav(sample_rate=16000, frame_count=1600):
    output = BytesIO()
    with wave.open(output, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(b"\x01\x00" * frame_count)
    return output.getvalue()


class FakeContent:
    def __init__(self, events):
        self.events = events

    async def iter_chunked(self, _chunk_size):
        for event in self.events:
            if isinstance(event, Exception):
                raise event
            yield event


class FakeResponse:
    def __init__(self, events, status=200, headers=None, text=""):
        self.status = status
        self.headers = headers or {
            "X-Sample-Rate": "16000",
            "X-Audio-Format": "pcm_s16le_mono",
        }
        self.content = FakeContent(events)
        self._text = text
        self.closed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def text(self):
        return self._text

    def close(self):
        self.closed = True


class FakeSession:
    def __init__(self, response):
        self.response = response

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    def post(self, *_args, **_kwargs):
        return self.response


class IndexTTS25Test(unittest.TestCase):
    def make_provider(self, **overrides):
        config = {
            "api_url": "http://127.0.0.1:8092/",
            "voice": "tuniang-normal",
            "lang": "普通话",
            "speed": 1.0,
            "streaming": True,
            "stream_fallback": True,
            "output_dir": "tmp/",
        }
        config.update(overrides)
        provider = TTSProvider(config, delete_audio_file=True)
        provider.conn = types.SimpleNamespace(sample_rate=16000, audio_format="pcm")
        provider.current_sentence_id = "sentence-1"
        provider._stream_segment_text = "测试"
        return provider

    def test_request_contract_is_minimal_and_normalized(self):
        provider = self.make_provider(api_url="http://127.0.0.1:8092/v1/tts/stream")

        payload = provider.build_request("你好")

        self.assertEqual(provider.api_url, "http://127.0.0.1:8092/v1/tts")
        self.assertEqual(provider.stream_api_url, "http://127.0.0.1:8092/v1/tts/stream")
        self.assertEqual(provider.health_url, "http://127.0.0.1:8092/health/ready")
        self.assertEqual(
            set(payload),
            {
                "request_id",
                "text",
                "voice_id",
                "lang",
                "speed",
                "text_normalization",
            },
        )
        self.assertEqual(payload["lang"], "zh")
        self.assertNotIn("emotion", payload)

    def test_request_replaces_gbk_incompatible_katakana_middle_dot_only_in_payload(self):
        provider = self.make_provider()
        original = "Ciallo～(∠・ω< )⌒★"

        payload = provider.build_request(original)

        self.assertEqual(payload["text"], "Ciallo～(∠·ω< )⌒★")
        self.assertEqual(original, "Ciallo～(∠・ω< )⌒★")
        payload["text"].encode("gbk")

    def test_speed_is_finite_clamped_and_accepts_tts_rate(self):
        self.assertEqual(self.make_provider(speed="nan").speed, 1.0)
        self.assertEqual(self.make_provider(speed=9).speed, 2.0)
        self.assertEqual(self.make_provider(speed=1.0, ttsRate=-100).speed, 0.5)
        self.assertEqual(self.make_provider(speed=1.0, ttsRate="invalid").speed, 1.0)

    def test_blank_timeout_uses_index_safe_default(self):
        self.assertEqual(self.make_provider(tts_timeout="").tts_timeout, 60.0)
        self.assertEqual(self.make_provider(tts_timeout="nan").tts_timeout, 60.0)

    def test_non_stream_response_is_validated_and_can_be_saved(self):
        provider = self.make_provider()
        audio = make_wav()
        response = HttpAudioResponse(200, audio, "", {})

        with patch(
            "core.providers.tts.index_tts_v2_5.post_audio",
            new=AsyncMock(return_value=response),
        ):
            self.assertEqual(asyncio.run(provider.text_to_speak("你好", None)), audio)
            with tempfile.TemporaryDirectory() as directory:
                output = Path(directory) / "nested" / "voice.wav"
                self.assertIsNone(
                    asyncio.run(provider.text_to_speak("你好", str(output)))
                )
                self.assertEqual(output.read_bytes(), audio)

    def test_non_stream_error_and_invalid_wav_are_rejected(self):
        provider = self.make_provider()
        cases = [
            HttpAudioResponse(503, b"busy", "busy", {}),
            HttpAudioResponse(200, b"RIFF-not-a-wave", "", {}),
            HttpAudioResponse(200, make_wav(sample_rate=1000), "", {}),
            HttpAudioResponse(200, make_wav()[:-10], "", {}),
        ]
        for response in cases:
            with self.subTest(response=response.status_code), patch(
                "core.providers.tts.index_tts_v2_5.post_audio",
                new=AsyncMock(return_value=response),
            ):
                with self.assertRaises(RuntimeError):
                    asyncio.run(provider.text_to_speak("你好", None))

    def test_stream_failure_before_first_device_packet_falls_back_to_wav(self):
        provider = self.make_provider()
        response = FakeResponse(
            [b"\x00\x00" * 10, aiohttp.ClientConnectionError("disconnected")]
        )
        fallback = AsyncMock()

        with patch(
            "core.providers.tts.index_tts_v2_5.aiohttp.ClientSession",
            return_value=FakeSession(response),
        ), patch.object(provider, "_stream_from_wav_fallback", fallback):
            asyncio.run(provider.stream_text_to_speak("你好"))

        fallback.assert_awaited_once_with("你好")
        self.assertEqual(provider._stream_packet_count, 0)

    def test_stream_failure_after_first_device_packet_never_replays(self):
        provider = self.make_provider()
        # 60ms at 16kHz mono int16 is exactly one device PCM packet.
        response = FakeResponse(
            [b"\x00\x00" * 960, aiohttp.ClientConnectionError("disconnected")]
        )
        fallback = AsyncMock()

        with patch(
            "core.providers.tts.index_tts_v2_5.aiohttp.ClientSession",
            return_value=FakeSession(response),
        ), patch.object(provider, "_stream_from_wav_fallback", fallback):
            with self.assertRaises(RuntimeError):
                asyncio.run(provider.stream_text_to_speak("你好"))

        fallback.assert_not_awaited()
        self.assertEqual(provider._stream_packet_count, 1)

    def test_unsupported_stream_headers_fall_back_before_audio(self):
        provider = self.make_provider()
        response = FakeResponse(
            [], headers={"X-Sample-Rate": "16000", "X-Audio-Format": "mp3"}
        )
        fallback = AsyncMock()

        with patch(
            "core.providers.tts.index_tts_v2_5.aiohttp.ClientSession",
            return_value=FakeSession(response),
        ), patch.object(provider, "_stream_from_wav_fallback", fallback):
            asyncio.run(provider.stream_text_to_speak("你好"))

        fallback.assert_awaited_once_with("你好")

    def test_empty_stream_falls_back_instead_of_reporting_silent_success(self):
        provider = self.make_provider()
        response = FakeResponse([])
        fallback = AsyncMock()

        with patch(
            "core.providers.tts.index_tts_v2_5.aiohttp.ClientSession",
            return_value=FakeSession(response),
        ), patch.object(provider, "_stream_from_wav_fallback", fallback):
            asyncio.run(provider.stream_text_to_speak("你好"))

        fallback.assert_awaited_once_with("你好")

    def test_cancellation_closes_the_active_response(self):
        provider = self.make_provider()
        response = FakeResponse([])

        async def exercise():
            provider.register_active_stream(response)
            provider.cancel_current_synthesis()
            await asyncio.sleep(0)

        asyncio.run(exercise())

        self.assertTrue(provider.synthesis_cancelled())
        self.assertTrue(response.closed)

    def test_bounded_reader_rejects_declared_and_streamed_oversize_bodies(self):
        declared = FakeResponse([], headers={"Content-Length": "5"})
        streamed = FakeResponse([b"123", b"45"], headers={"X-Test": "1"})

        with self.assertRaises(ValueError):
            asyncio.run(read_bounded(declared, 4))
        with self.assertRaises(ValueError):
            asyncio.run(read_bounded(streamed, 4))

        self.assertTrue(streamed.closed)

    def test_declared_oversize_stream_falls_back_before_audio(self):
        provider = self.make_provider()
        response = FakeResponse(
            [],
            headers={
                "X-Sample-Rate": "16000",
                "X-Audio-Format": "pcm_s16le_mono",
                "Content-Length": str(65 * 1024 * 1024),
            },
        )
        fallback = AsyncMock()

        with patch(
            "core.providers.tts.index_tts_v2_5.aiohttp.ClientSession",
            return_value=FakeSession(response),
        ), patch.object(provider, "_stream_from_wav_fallback", fallback):
            asyncio.run(provider.stream_text_to_speak("你好"))

        fallback.assert_awaited_once_with("你好")


if __name__ == "__main__":
    unittest.main()
