import os
import tempfile
import types
import unittest
from unittest.mock import patch

from core.providers.tts.base import TTSProviderBase
from core.providers.tts.dto.dto import ContentType, SentenceType, TTSMessageDTO


class _Provider(TTSProviderBase):
    def __init__(self):
        super().__init__({"output_dir": "tmp/", "tts_timeout": 1}, False)

    async def text_to_speak(self, text, output_file):
        raise NotImplementedError


class TtsFileFallbackTest(unittest.TestCase):
    def message(self, filename):
        return TTSMessageDTO(
            sentence_id="sentence",
            sentence_type=SentenceType.MIDDLE,
            content_type=ContentType.FILE,
            content_detail="Ciallo",
            content_file=filename,
        )

    def test_decode_failure_publishes_no_partial_packet_and_falls_back_text(self):
        provider = _Provider()
        published = []
        fallback = []
        with tempfile.NamedTemporaryFile() as audio:
            def fail_after_one(callback):
                callback(b"partial")
                raise ValueError("broken tail")

            provider._process_audio_file_stream = lambda filename, callback: fail_after_one(callback)
            result = provider._play_audio_file_or_fallback(
                self.message(audio.name),
                audio_handler=published.append,
                fallback_handler=fallback.append,
            )

        self.assertFalse(result)
        self.assertEqual([], published)
        self.assertEqual(["Ciallo"], fallback)

    def test_success_emits_subtitle_then_all_buffered_packets(self):
        provider = _Provider()
        published = []
        with tempfile.NamedTemporaryFile() as audio:
            provider._process_audio_file_stream = lambda filename, callback: (
                callback(b"one"), callback(b"two")
            )
            result = provider._play_audio_file_or_fallback(
                self.message(audio.name),
                audio_handler=published.append,
                emit_first=True,
            )

        self.assertTrue(result)
        self.assertEqual([b"one", b"two"], published)
        sentence_type, audio_data, text, sentence_id = provider.tts_audio_queue.get_nowait()
        self.assertEqual(SentenceType.FIRST, sentence_type)
        self.assertIsNone(audio_data)
        self.assertEqual("Ciallo", text)
        self.assertEqual("sentence", sentence_id)

    def test_missing_file_uses_same_fallback(self):
        provider = _Provider()
        fallback = []
        missing = os.path.join(tempfile.gettempdir(), "missing-signature-audio.wav")
        if os.path.exists(missing):
            os.unlink(missing)

        result = provider._play_audio_file_or_fallback(
            self.message(missing), fallback_handler=fallback.append
        )

        self.assertFalse(result)
        self.assertEqual(["Ciallo"], fallback)

    def test_duplex_file_boundary_finishes_then_restarts_session(self):
        provider = _Provider()
        provider.conn = types.SimpleNamespace(loop=object())
        events = []

        async def noop():
            return None

        def finish(session_id):
            events.append(("finish", session_id))
            provider._mark_duplex_session_finished()
            return noop()

        def start(session_id):
            events.append(("start", session_id))
            return noop()

        class CompletedFuture:
            def result(self, timeout=None):
                return None

        def submit(coroutine, loop):
            self.assertIs(loop, provider.conn.loop)
            coroutine.close()
            return CompletedFuture()

        with patch("core.providers.tts.base.asyncio.run_coroutine_threadsafe", side_effect=submit):
            provider._restart_duplex_session_after_file("sentence", finish, start)

        self.assertEqual([("finish", "sentence"), ("start", "sentence")], events)

    def test_file_boundary_positions_text_cursor_at_current_buffer_end(self):
        provider = _Provider()
        spoken = []
        provider.tts_text_buff = ["already", "beforefile"]
        provider.processed_chars = len("already")
        provider.to_tts_stream = lambda text, opus_handler=None: spoken.append(text)

        self.assertTrue(provider._process_remaining_text_stream())
        self.assertEqual(len("alreadybeforefile"), provider.processed_chars)

        provider.tts_text_buff.append("afterfile")
        self.assertTrue(provider._process_remaining_text_stream())
        self.assertEqual(["beforefile", "afterfile"], spoken)
        self.assertEqual(len("alreadybeforefileafterfile"), provider.processed_chars)


if __name__ == "__main__":
    unittest.main()
