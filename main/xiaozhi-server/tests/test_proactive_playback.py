import asyncio
from types import SimpleNamespace
import unittest

from core.companion.proactive_playback import enqueue_online_proactive_playback
from core.providers.tts.dto.dto import ContentType, SentenceType


class RecordingQueue:
    def __init__(self, events):
        self.events = events
        self.items = []

    def put(self, item):
        self.events.append(("queue", item.sentence_type.value))
        self.items.append(item)


def _connection(events):
    return SimpleNamespace(
        sentence_id=None,
        client_abort=False,
        client_is_speaking=False,
        active_turn_recorder=None,
        last_companion_user_turn_time=100.0,
        tts=SimpleNamespace(tts_text_queue=RecordingQueue(events)),
    )


class ProactivePlaybackTest(unittest.TestCase):
    def test_existing_user_activity_prevents_start_control(self):
        events = []
        conn = _connection(events)
        conn.last_companion_user_turn_time = 101.0

        async def send_state(_conn, state, text=None):
            events.append(("state", state))

        result = asyncio.run(
            enqueue_online_proactive_playback(
                conn, "我来看看你。", 100.0, send_state=send_state
            )
        )

        self.assertFalse(result.sent)
        self.assertEqual("user_active", result.reason)
        self.assertEqual([], events)
        self.assertEqual([], conn.tts.tts_text_queue.items)

    def test_start_control_precedes_tts_queue(self):
        events = []
        conn = _connection(events)

        async def send_state(_conn, state, text=None):
            events.append(("state", state))

        result = asyncio.run(
            enqueue_online_proactive_playback(
                conn, "今天过得怎么样？", 100.0, send_state=send_state
            )
        )

        self.assertTrue(result.sent)
        self.assertEqual(("state", "start"), events[0])
        self.assertEqual(
            [SentenceType.FIRST, SentenceType.MIDDLE, SentenceType.LAST],
            [item.sentence_type for item in conn.tts.tts_text_queue.items],
        )
        self.assertEqual(ContentType.TEXT, conn.tts.tts_text_queue.items[1].content_type)
        self.assertEqual("今天过得怎么样？", conn.tts.tts_text_queue.items[1].content_detail)
        self.assertTrue(conn.client_is_speaking)

    def test_user_activity_after_start_stops_without_queueing_audio(self):
        events = []
        conn = _connection(events)

        async def send_state(_conn, state, text=None):
            events.append(("state", state))
            if state == "start":
                conn.last_companion_user_turn_time = 101.0

        result = asyncio.run(
            enqueue_online_proactive_playback(
                conn, "我来看看你。", 100.0, send_state=send_state
            )
        )

        self.assertFalse(result.sent)
        self.assertEqual("user_active", result.reason)
        self.assertEqual([("state", "start"), ("state", "stop")], events)
        self.assertEqual([], conn.tts.tts_text_queue.items)
        self.assertFalse(conn.client_is_speaking)

    def test_protocol_failure_rolls_back_speaking_state(self):
        events = []
        conn = _connection(events)

        async def send_state(_conn, state, text=None):
            raise ConnectionError("socket closed")

        result = asyncio.run(
            enqueue_online_proactive_playback(
                conn, "还好吗？", 100.0, send_state=send_state
            )
        )

        self.assertFalse(result.sent)
        self.assertEqual("protocol_error", result.reason)
        self.assertIn("socket closed", result.error)
        self.assertEqual([], conn.tts.tts_text_queue.items)
        self.assertFalse(conn.client_is_speaking)


if __name__ == "__main__":
    unittest.main()
