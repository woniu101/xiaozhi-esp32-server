from __future__ import annotations

import threading
import uuid
from typing import Any

from .state_models import CompletedTurn


class TurnRecorder:
    """Thread-safe recorder for one logical top-level chat turn."""

    def __init__(self, user_message: str, turn_id: str | None = None):
        self.turn_id = turn_id or uuid.uuid4().hex
        self.user_message = user_message
        self._assistant_chunks: list[str] = []
        self._tool_events: list[dict[str, Any]] = []
        self._aborted = False
        self._failed_reason: str | None = None
        self._finalized = False
        self._result: CompletedTurn | None = None
        self._lock = threading.Lock()

    def append_assistant_chunk(self, text: str | None):
        if not text:
            return
        with self._lock:
            if not self._finalized:
                self._assistant_chunks.append(text)

    def record_tool(self, name: str, args: dict | None = None, result: Any = None):
        with self._lock:
            if not self._finalized:
                self._tool_events.append({"name": name, "args": args or {}, "result": result})

    def mark_aborted(self):
        with self._lock:
            if not self._finalized:
                self._aborted = True

    def mark_failed(self, reason: str):
        with self._lock:
            if not self._finalized:
                self._failed_reason = reason

    def finalize(self) -> CompletedTurn:
        with self._lock:
            if self._result is None:
                self._finalized = True
                self._result = CompletedTurn(
                    turn_id=self.turn_id,
                    user_message=self.user_message,
                    assistant_message="".join(self._assistant_chunks).strip(),
                    tool_events=list(self._tool_events),
                    aborted=self._aborted,
                    failed_reason=self._failed_reason,
                )
            return self._result
