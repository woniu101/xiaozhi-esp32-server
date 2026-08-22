import json
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.connection import ConnectionHandler
TAG = __name__


async def handleAbortMessage(conn: "ConnectionHandler"):
    interrupt_started_at = time.perf_counter()
    aborted_sentence_id = getattr(conn, "sentence_id", None)
    conn.logger.bind(tag=TAG).info("Abort message received")
    # 设置成打断状态，会自动打断llm、tts任务
    conn.close_after_chat = False
    conn.client_abort = True
    if conn.tts is not None and hasattr(conn.tts, "cancel_current_synthesis"):
        conn.tts.cancel_current_synthesis()
    # Treat an explicit device abort as fresh user activity. This prevents a
    # concurrently scheduled proactive turn from clearing the abort and starting
    # playback immediately after the user asked the device to stop.
    if hasattr(conn, "last_companion_user_turn_time"):
        conn.last_companion_user_turn_time = time.time()
    if getattr(conn, "active_turn_recorder", None) is not None:
        conn.active_turn_recorder.mark_aborted()
    if aborted_sentence_id:
        conn.aborted_sentence_ids.add(aborted_sentence_id)
        if len(conn.aborted_sentence_ids) > 20:
            conn.aborted_sentence_ids.pop()
    conn.clear_queues()
    # 打断客户端说话状态
    await conn.websocket.send(
        json.dumps({"type": "tts", "state": "stop", "session_id": conn.session_id})
    )
    conn.clearSpeakStatus()
    tracker = getattr(conn, "companion_turn_latency", {}).get(aborted_sentence_id)
    if tracker is not None:
        tracker.abort(interrupt_started_at)
    conn.logger.bind(tag=TAG).info("Abort message received-end")
