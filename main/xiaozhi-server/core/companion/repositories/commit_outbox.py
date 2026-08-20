from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3
import time
from typing import Any
from contextlib import closing


class DurableCommitOutbox:
    """Small local SQLite outbox for manager-api Companion commits.

    Payloads contain the same personal memory candidates that would otherwise be
    sent to manager-api, so the database is created with owner-only permissions.
    Delivered rows are deleted; unresolved rows remain durable across restarts.
    """

    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            descriptor = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)
        except FileExistsError:
            pass
        else:
            os.close(descriptor)
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass
        self._initialize()

    def _connect(self):
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=5000")
        return connection

    def _initialize(self):
        with closing(self._connect()) as connection, connection:
            # The queue is tiny and serialized by the repository. DELETE mode avoids
            # leaving memory-bearing WAL/SHM sidecars with platform-dependent modes.
            connection.execute("PRAGMA journal_mode=DELETE")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS companion_commit_outbox (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    turn_id TEXT NOT NULL UNIQUE,
                    user_id TEXT NOT NULL,
                    agent_id TEXT NOT NULL,
                    persona_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    next_attempt_at REAL NOT NULL DEFAULT 0,
                    last_error TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_companion_outbox_due
                ON companion_commit_outbox(next_attempt_at, id)
                """
            )

    def enqueue(self, payload: dict[str, Any], error: str = ""):
        now = time.time()
        with closing(self._connect()) as connection, connection:
            connection.execute(
                """
                INSERT INTO companion_commit_outbox(
                    turn_id,user_id,agent_id,persona_id,payload_json,
                    attempts,next_attempt_at,last_error,created_at,updated_at
                ) VALUES(?,?,?,?,?,0,?,?,?,?)
                ON CONFLICT(turn_id) DO UPDATE SET
                    payload_json=excluded.payload_json,
                    last_error=excluded.last_error,
                    updated_at=excluded.updated_at
                """,
                (
                    str(payload["turnId"]),
                    str(payload["userId"]),
                    str(payload["agentId"]),
                    str(payload["personaId"]),
                    json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                    now + 2,
                    str(error or "")[:500],
                    now,
                    now,
                ),
            )

    def due(self, limit: int = 50, force: bool = False) -> list[dict[str, Any]]:
        query = "SELECT * FROM companion_commit_outbox"
        params: list[Any] = []
        if not force:
            query += " WHERE next_attempt_at <= ?"
            params.append(time.time())
        query += " ORDER BY id ASC LIMIT ?"
        params.append(max(1, min(500, int(limit))))
        with closing(self._connect()) as connection, connection:
            rows = connection.execute(query, params).fetchall()
        result = []
        for row in rows:
            value = dict(row)
            value["payload"] = json.loads(value.pop("payload_json"))
            result.append(value)
        return result

    def mark_delivered(self, row_id: int):
        with closing(self._connect()) as connection, connection:
            connection.execute("DELETE FROM companion_commit_outbox WHERE id=?", (row_id,))

    def postpone(self, row_id: int, attempts: int, error: str):
        bounded_attempts = max(1, int(attempts))
        delay = min(300, 2 ** min(8, bounded_attempts))
        with closing(self._connect()) as connection, connection:
            connection.execute(
                """
                UPDATE companion_commit_outbox
                SET attempts=?, next_attempt_at=?, last_error=?, updated_at=?
                WHERE id=?
                """,
                (
                    bounded_attempts,
                    time.time() + delay,
                    str(error or "")[:500],
                    time.time(),
                    row_id,
                ),
            )

    def replace_payload(self, row_id: int, payload: dict[str, Any]):
        with closing(self._connect()) as connection, connection:
            connection.execute(
                "UPDATE companion_commit_outbox SET payload_json=?, updated_at=? WHERE id=?",
                (
                    json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                    time.time(),
                    row_id,
                ),
            )

    def count(self, user_id: str | None = None, agent_id: str | None = None,
              persona_id: str | None = None) -> int:
        query = "SELECT COUNT(*) FROM companion_commit_outbox"
        params: list[Any] = []
        if user_id is not None and agent_id is not None and persona_id is not None:
            query += " WHERE user_id=? AND agent_id=? AND persona_id=?"
            params.extend((user_id, agent_id, persona_id))
        with closing(self._connect()) as connection, connection:
            return int(connection.execute(query, params).fetchone()[0])

    def seconds_until_next(self) -> float:
        with closing(self._connect()) as connection, connection:
            row = connection.execute(
                "SELECT MIN(next_attempt_at) FROM companion_commit_outbox"
            ).fetchone()
        if not row or row[0] is None:
            return 0.0
        return max(0.0, float(row[0]) - time.time())

    def oldest_age_seconds(self) -> float:
        with closing(self._connect()) as connection, connection:
            row = connection.execute(
                "SELECT MIN(created_at) FROM companion_commit_outbox"
            ).fetchone()
        if not row or row[0] is None:
            return 0.0
        return max(0.0, time.time() - float(row[0]))
