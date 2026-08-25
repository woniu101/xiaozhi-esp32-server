import unittest
import queue
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

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
from core.providers.tts.base import TTSProviderBase
from core.providers.tts.dto.dto import SentenceType
from core.handle.sendAudioHandle import sendAudioMessage


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

    def test_fixed_file_subtitle_is_attached_only_to_first_packet(self):
        provider = SimpleNamespace(
            before_stop_play_files=[
                (b"packet-1", "Ciallo～"),
                (b"packet-2", "Ciallo～"),
            ],
            tts_audio_queue=queue.Queue(),
            current_sentence_id="sentence-1",
        )

        TTSProviderBase._process_before_stop_play_files(provider)

        first = provider.tts_audio_queue.get_nowait()
        second = provider.tts_audio_queue.get_nowait()
        last = provider.tts_audio_queue.get_nowait()
        self.assertEqual((SentenceType.MIDDLE, b"packet-1", "Ciallo～", "sentence-1"), first)
        self.assertEqual((SentenceType.MIDDLE, b"packet-2", None, "sentence-1"), second)
        self.assertEqual(SentenceType.LAST, last[0])


class FixedFileSubtitleTest(unittest.IsolatedAsyncioTestCase):
    async def test_middle_file_text_is_queued_at_audio_boundary(self):
        callbacks = []
        controller = SimpleNamespace(add_message=callbacks.append)
        logger = SimpleNamespace(bind=lambda **kwargs: SimpleNamespace(info=lambda *args: None))
        conn = SimpleNamespace(
            sentence_id="sentence-1",
            aborted_sentence_ids=set(),
            companion_turn_latency={},
            tts=SimpleNamespace(tts_audio_first_sentence=False),
            audio_rate_controller=controller,
            audio_flow_control={"sentence_id": "sentence-1"},
            logger=logger,
            calling=True,
            close_after_chat=False,
        )

        with patch(
            "core.handle.sendAudioHandle.sendAudio", new=AsyncMock()
        ), patch(
            "core.handle.sendAudioHandle.send_tts_message", new=AsyncMock()
        ) as send_message:
            await sendAudioMessage(
                conn,
                SentenceType.MIDDLE,
                b"packet",
                "Ciallo～(∠・ω< )⌒★",
                "sentence-1",
            )
            send_message.assert_not_awaited()
            self.assertEqual(1, len(callbacks))
            await callbacks[0]()
            send_message.assert_awaited_once_with(
                conn, "sentence_start", "Ciallo～(∠・ω< )⌒★"
            )


if __name__ == "__main__":
    unittest.main()
