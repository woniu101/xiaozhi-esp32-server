import unittest

from core.companion.latency import ConversationLatencyTracker, should_drop_audio


class CompanionLatencyTest(unittest.TestCase):
    def test_tracker_exposes_each_voice_stage_relative_to_asr(self):
        tracker = ConversationLatencyTracker("sentence-1", started_at=100.0)
        tracker.mark("llm_request", 100.05)
        tracker.mark("llm_first_token", 100.2)
        tracker.mark("tts_text_enqueued", 100.24)
        tracker.mark("first_audio", 100.5)
        tracker.mark("completed", 101.0)

        self.assertEqual(
            tracker.snapshot(),
            {
                "llm_requestMs": 50.0,
                "llm_first_tokenMs": 200.0,
                "tts_text_enqueuedMs": 240.0,
                "first_audioMs": 500.0,
                "completedMs": 1000.0,
                "transportId": "sentence-1",
            },
        )

    def test_aborted_or_stale_sentence_audio_is_dropped(self):
        self.assertTrue(
            should_drop_audio("sentence-old", "sentence-current", {"sentence-old"})
        )
        self.assertTrue(
            should_drop_audio("sentence-aborted", "sentence-aborted", {"sentence-aborted"})
        )
        self.assertFalse(
            should_drop_audio("sentence-current", "sentence-current", set())
        )


if __name__ == "__main__":
    unittest.main()
