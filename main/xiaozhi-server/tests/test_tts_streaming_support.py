import unittest

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
            "log_file": "xiaozhi-tts-streaming-support-tests.log",
        }
    },
)

from core.providers.tts.streaming_support import StreamingPcmTranscoder


class StreamingPcmTranscoderTest(unittest.TestCase):
    def test_resamples_odd_chunks_and_emits_fixed_pcm_frames(self):
        frames = []
        transcoder = StreamingPcmTranscoder(
            source_rate=22050,
            target_rate=24000,
            output_format="pcm",
            opus_encoder=None,
            callback=frames.append,
        )
        one_second_silence = b"\x00\x00" * 22050

        transcoder.feed(one_second_silence[:1001])
        transcoder.feed(one_second_silence[1001:19003])
        transcoder.feed(one_second_silence[19003:])
        transcoder.finish()

        self.assertEqual(17, len(frames))
        self.assertTrue(all(len(frame) == 2880 for frame in frames))
        self.assertEqual(len(one_second_silence), transcoder.input_bytes)
        self.assertGreater(transcoder.output_bytes, transcoder.input_bytes)

    def test_same_rate_does_not_change_pcm_payload_before_frame_padding(self):
        frames = []
        transcoder = StreamingPcmTranscoder(
            source_rate=24000,
            target_rate=24000,
            output_format="pcm",
            opus_encoder=None,
            callback=frames.append,
        )
        payload = b"\x01\x00" * 1440

        transcoder.feed(payload)
        transcoder.finish()

        self.assertEqual([payload], frames)


if __name__ == "__main__":
    unittest.main()
