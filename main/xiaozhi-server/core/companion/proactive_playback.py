from __future__ import annotations

from dataclasses import dataclass
import uuid
from typing import Awaitable, Callable

from core.providers.tts.dto.dto import ContentType, SentenceType, TTSMessageDTO
from core.companion.signature_audio import SignatureSpeechRouter, enqueue_speech_segments


@dataclass(frozen=True)
class OnlineProactivePlaybackResult:
    sent: bool
    reason: str
    sentence_id: str | None = None
    error: str = ""


def _user_became_active(conn, expected_user_turn: float | None) -> bool:
    return bool(
        (
            expected_user_turn is not None
            and conn.last_companion_user_turn_time != expected_user_turn
        )
        or conn.active_turn_recorder is not None
    )


async def enqueue_online_proactive_playback(
    conn,
    text: str,
    expected_user_turn: float | None,
    *,
    send_state: Callable[..., Awaitable[None]],
    expression_plan: dict | None = None,
) -> OnlineProactivePlaybackResult:
    """Start a server-initiated online TTS turn using the standard device protocol.

    The current ESP32 protocol requires ``tts/start`` before binary Opus frames.
    Normal replies send it from the STT path; proactive replies have no STT event,
    so they must perform the transition explicitly before touching the TTS queue.
    """
    message = str(text or "").strip()
    if not message:
        return OnlineProactivePlaybackResult(False, "empty")
    if conn.client_is_speaking or _user_became_active(conn, expected_user_turn):
        return OnlineProactivePlaybackResult(False, "user_active")

    sentence_id = uuid.uuid4().hex
    start_sent = False
    try:
        conn.sentence_id = sentence_id
        # A previous aborted turn must not suppress this newly scheduled sentence.
        conn.client_abort = False
        await send_state(conn, "start")
        start_sent = True
        conn.client_is_speaking = True

        # The websocket send above yields control. Recheck before queueing audio so
        # a user turn that arrived concurrently always wins over proactive speech.
        if conn.client_abort or _user_became_active(conn, expected_user_turn):
            await send_state(conn, "stop", None)
            conn.client_is_speaking = False
            return OnlineProactivePlaybackResult(False, "user_active", sentence_id)

        conn.tts.tts_text_queue.put(
            TTSMessageDTO(
                sentence_id,
                SentenceType.FIRST,
                ContentType.ACTION,
                expression_plan=expression_plan,
                turn_id=(expression_plan or {}).get("turn_id"),
            )
        )
        signature_router = SignatureSpeechRouter.from_session(
            getattr(conn, "companion_session", None), expression_plan
        )
        enqueue_speech_segments(
            conn.tts,
            signature_router,
            message,
            sentence_id=sentence_id,
            expression_plan=expression_plan,
            turn_id=(expression_plan or {}).get("turn_id"),
            final=True,
        )
        conn.tts.tts_text_queue.put(
            TTSMessageDTO(
                sentence_id,
                SentenceType.LAST,
                ContentType.ACTION,
                expression_plan=expression_plan,
                turn_id=(expression_plan or {}).get("turn_id"),
            )
        )
        return OnlineProactivePlaybackResult(True, "sent", sentence_id)
    except Exception as error:
        if start_sent:
            try:
                await send_state(conn, "stop", None)
            except Exception:
                pass
        conn.client_is_speaking = False
        return OnlineProactivePlaybackResult(
            False,
            "protocol_error",
            sentence_id,
            str(error)[:300],
        )
