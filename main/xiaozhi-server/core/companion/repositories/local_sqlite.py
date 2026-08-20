from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from pathlib import Path

from core.companion.repositories.base import CompanionRepository
from core.companion.state_models import CompanionEvent, CompanionIdentity, CompanionState, MemoryCandidate, iso_now
from core.companion.repositories.memory_ranking import rank_memories


class SQLiteCompanionRepository(CompanionRepository):
    def __init__(self, database_path: str | Path, embedder=None):
        self.database_path = Path(database_path).expanduser().resolve()
        self.embedder = embedder
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self):
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def _initialize(self):
        with self._connect() as connection:
            self._create_tables(connection)
            self._migrate_persona_scope(connection)
            self._migrate_memory_lifecycle(connection)
            self._migrate_turn_diagnostics(connection)
            connection.executescript(
                """
                CREATE INDEX IF NOT EXISTS idx_companion_event_owner
                    ON companion_event(user_id, agent_id, persona_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_companion_turn_owner
                    ON companion_turn(user_id, agent_id, persona_id, created_at);
                CREATE INDEX IF NOT EXISTS idx_companion_memory_owner
                    ON companion_memory(user_id, agent_id, persona_id, importance, created_at);
                CREATE INDEX IF NOT EXISTS idx_companion_memory_subject
                    ON companion_memory(user_id, agent_id, persona_id, subject_key, status);
                """
            )

    def _create_tables(self, connection):
        connection.executescript(
            """
                CREATE TABLE IF NOT EXISTS companion_state (
                    user_id TEXT NOT NULL,
                    agent_id TEXT NOT NULL,
                    persona_id TEXT NOT NULL,
                    state_json TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (user_id, agent_id, persona_id)
                );
                CREATE TABLE IF NOT EXISTS companion_event (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    turn_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    agent_id TEXT NOT NULL,
                    persona_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    payload_hash TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE (turn_id, event_type, payload_hash)
                );
                CREATE TABLE IF NOT EXISTS companion_turn (
                    turn_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    agent_id TEXT NOT NULL,
                    persona_id TEXT NOT NULL,
                    state_revision INTEGER NOT NULL,
                    diagnostic_json TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS companion_memory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    agent_id TEXT NOT NULL,
                    persona_id TEXT NOT NULL,
                    memory_type TEXT NOT NULL,
                    subject_key TEXT,
                    content TEXT NOT NULL,
                    normalized_hash TEXT NOT NULL,
                    importance REAL NOT NULL,
                    confidence REAL NOT NULL,
                    sensitivity TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    superseded_by INTEGER,
                    occurred_at TEXT,
                    source_turn_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    last_accessed_at TEXT NOT NULL,
                    expires_at TEXT,
                    UNIQUE (user_id, agent_id, persona_id, memory_type, normalized_hash)
                );
            """
        )

    def _migrate_persona_scope(self, connection):
        """Upgrade early local databases without discarding their active Persona state."""
        tables = ("companion_state", "companion_event", "companion_turn", "companion_memory")
        legacy_tables = [
            table
            for table in tables
            if connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
            ).fetchone()
            and "persona_id" not in {
                row["name"] for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
            }
        ]
        if not legacy_tables:
            return
        if set(legacy_tables) != set(tables):
            raise RuntimeError("Companion SQLite schema is partially migrated")

        connection.execute("PRAGMA foreign_keys=OFF")
        for table in tables:
            connection.execute(f"ALTER TABLE {table} RENAME TO {table}_legacy_scope")
        self._create_tables(connection)
        connection.execute(
            """
            INSERT INTO companion_state(user_id,agent_id,persona_id,state_json,revision,updated_at)
            SELECT user_id,agent_id,'__legacy__',state_json,revision,updated_at
            FROM companion_state_legacy_scope
            """
        )
        connection.execute(
            """
            INSERT INTO companion_event(id,turn_id,user_id,agent_id,persona_id,event_type,payload_json,payload_hash,confidence,created_at)
            SELECT id,turn_id,user_id,agent_id,'__legacy__',event_type,payload_json,payload_hash,confidence,created_at
            FROM companion_event_legacy_scope
            """
        )
        connection.execute(
            """
            INSERT INTO companion_turn(turn_id,user_id,agent_id,persona_id,state_revision,created_at)
            SELECT turn_id,user_id,agent_id,'__legacy__',state_revision,created_at
            FROM companion_turn_legacy_scope
            """
        )
        connection.execute(
            """
            INSERT INTO companion_memory(
                id,user_id,agent_id,persona_id,memory_type,content,normalized_hash,
                importance,confidence,sensitivity,occurred_at,source_turn_id,
                created_at,last_accessed_at,expires_at
            )
            SELECT id,user_id,agent_id,'__legacy__',memory_type,content,normalized_hash,
                   importance,confidence,sensitivity,occurred_at,source_turn_id,
                   created_at,last_accessed_at,NULL
            FROM companion_memory_legacy_scope
            """
        )
        for table in tables:
            connection.execute(f"DROP TABLE {table}_legacy_scope")
        connection.execute("PRAGMA foreign_keys=ON")

    def _migrate_memory_lifecycle(self, connection):
        columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(companion_memory)").fetchall()
        }
        additions = {
            "subject_key": "TEXT",
            "status": "TEXT NOT NULL DEFAULT 'active'",
            "superseded_by": "INTEGER",
            "expires_at": "TEXT",
        }
        for name, definition in additions.items():
            if name not in columns:
                connection.execute(f"ALTER TABLE companion_memory ADD COLUMN {name} {definition}")

    def _migrate_turn_diagnostics(self, connection):
        columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(companion_turn)").fetchall()
        }
        if "diagnostic_json" not in columns:
            connection.execute("ALTER TABLE companion_turn ADD COLUMN diagnostic_json TEXT")

    def _claim_legacy_scope(self, connection, identity: CompanionIdentity):
        """Assign a pre-persona local history to the first Persona opened after upgrade."""
        current = connection.execute(
            "SELECT 1 FROM companion_state WHERE user_id=? AND agent_id=? AND persona_id=?",
            (identity.user_id, identity.agent_id, identity.persona_id),
        ).fetchone()
        if current:
            return
        legacy = connection.execute(
            "SELECT 1 FROM companion_state WHERE user_id=? AND agent_id=? AND persona_id='__legacy__'",
            (identity.user_id, identity.agent_id),
        ).fetchone()
        if not legacy:
            return
        for table in ("companion_state", "companion_event", "companion_turn", "companion_memory"):
            connection.execute(
                f"UPDATE {table} SET persona_id=? WHERE user_id=? AND agent_id=? AND persona_id='__legacy__'",
                (identity.persona_id, identity.user_id, identity.agent_id),
            )

    async def get_state(self, identity: CompanionIdentity) -> CompanionState:
        return self._get_state_sync(identity)

    def _get_state_sync(self, identity: CompanionIdentity) -> CompanionState:
        with self._connect() as connection:
            self._claim_legacy_scope(connection, identity)
            row = connection.execute(
                "SELECT state_json, revision FROM companion_state WHERE user_id=? AND agent_id=? AND persona_id=?",
                (identity.user_id, identity.agent_id, identity.persona_id),
            ).fetchone()
        if not row:
            return CompanionState()
        value = json.loads(row["state_json"])
        value["revision"] = row["revision"]
        return CompanionState.from_dict(value)

    async def commit_turn(
        self,
        identity: CompanionIdentity,
        turn_id: str,
        expected_revision: int,
        state: CompanionState,
        events: list[CompanionEvent],
        memories: list[MemoryCandidate],
        diagnostic: dict | None = None,
    ) -> str:
        return self._commit_turn_sync(
            identity, turn_id, expected_revision, state, events, memories, diagnostic
        )

    def _commit_turn_sync(
        self, identity, turn_id, expected_revision, state, events, memories, diagnostic=None
    ) -> str:
        now = iso_now()
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            duplicate = connection.execute(
                "SELECT 1 FROM companion_turn WHERE turn_id=? AND user_id=? AND agent_id=? AND persona_id=?",
                (turn_id, identity.user_id, identity.agent_id, identity.persona_id),
            ).fetchone()
            if duplicate:
                connection.rollback()
                return "duplicate"
            row = connection.execute(
                "SELECT revision FROM companion_state WHERE user_id=? AND agent_id=? AND persona_id=?",
                (identity.user_id, identity.agent_id, identity.persona_id),
            ).fetchone()
            actual_revision = int(row["revision"]) if row else 0
            if actual_revision != expected_revision:
                connection.rollback()
                return "conflict"
            state_json = json.dumps(state.to_dict(), ensure_ascii=False, separators=(",", ":"))
            if row:
                connection.execute(
                    "UPDATE companion_state SET state_json=?, revision=?, updated_at=? WHERE user_id=? AND agent_id=? AND persona_id=? AND revision=?",
                    (state_json, state.revision, now, identity.user_id, identity.agent_id, identity.persona_id, expected_revision),
                )
            else:
                connection.execute(
                    "INSERT INTO companion_state(user_id, agent_id, persona_id, state_json, revision, updated_at) VALUES(?,?,?,?,?,?)",
                    (identity.user_id, identity.agent_id, identity.persona_id, state_json, state.revision, now),
                )
            for event in events:
                payload = json.dumps(event.payload, ensure_ascii=False, sort_keys=True)
                payload_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()
                connection.execute(
                    "INSERT OR IGNORE INTO companion_event(turn_id,user_id,agent_id,persona_id,event_type,payload_json,payload_hash,confidence,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                    (turn_id, identity.user_id, identity.agent_id, identity.persona_id, event.event_type, payload, payload_hash, event.confidence, now),
                )
            for memory in memories:
                normalized = re.sub(r"\s+", "", memory.content).lower()
                normalized_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
                if memory.operation == "forget":
                    if memory.subject_key:
                        connection.execute(
                            """
                            UPDATE companion_memory SET status='forgotten', last_accessed_at=?
                            WHERE user_id=? AND agent_id=? AND persona_id=?
                              AND memory_type=? AND subject_key=? AND status='active'
                            """,
                            (
                                now, identity.user_id, identity.agent_id, identity.persona_id,
                                memory.memory_type, memory.subject_key,
                            ),
                        )
                    else:
                        connection.execute(
                            """
                            UPDATE companion_memory SET status='forgotten', last_accessed_at=?
                            WHERE user_id=? AND agent_id=? AND persona_id=?
                              AND memory_type=? AND normalized_hash=? AND status='active'
                            """,
                            (
                                now, identity.user_id, identity.agent_id, identity.persona_id,
                                memory.memory_type, normalized_hash,
                            ),
                        )
                    continue
                if memory.subject_key:
                    connection.execute(
                        """
                        UPDATE companion_memory
                        SET status='superseded'
                        WHERE user_id=? AND agent_id=? AND persona_id=?
                          AND memory_type=? AND subject_key=? AND NOT normalized_hash=?
                          AND status='active'
                        """,
                        (
                            identity.user_id,
                            identity.agent_id,
                            identity.persona_id,
                            memory.memory_type,
                            memory.subject_key,
                            normalized_hash,
                        ),
                    )
                connection.execute(
                    """
                    INSERT INTO companion_memory(
                        user_id,agent_id,persona_id,memory_type,subject_key,content,normalized_hash,importance,confidence,
                        sensitivity,status,occurred_at,source_turn_id,created_at,last_accessed_at,expires_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,'active',?,?,?,?,?)
                    ON CONFLICT(user_id,agent_id,persona_id,memory_type,normalized_hash) DO UPDATE SET
                        importance=MAX(importance, excluded.importance),
                        confidence=MAX(confidence, excluded.confidence),
                        subject_key=COALESCE(excluded.subject_key, subject_key),
                        status='active',
                        expires_at=excluded.expires_at,
                        last_accessed_at=excluded.last_accessed_at
                    """,
                    (
                        identity.user_id,
                        identity.agent_id,
                        identity.persona_id,
                        memory.memory_type,
                        memory.subject_key,
                        memory.content,
                        normalized_hash,
                        memory.importance,
                        memory.confidence,
                        memory.sensitivity,
                        memory.occurred_at,
                        turn_id,
                        now,
                        now,
                        memory.expires_at,
                    ),
                )
                if memory.subject_key:
                    stored = connection.execute(
                        """
                        SELECT id FROM companion_memory
                        WHERE user_id=? AND agent_id=? AND persona_id=?
                          AND memory_type=? AND normalized_hash=?
                        """,
                        (
                            identity.user_id,
                            identity.agent_id,
                            identity.persona_id,
                            memory.memory_type,
                            normalized_hash,
                        ),
                    ).fetchone()
                    connection.execute(
                        """
                        UPDATE companion_memory SET superseded_by=?
                        WHERE user_id=? AND agent_id=? AND persona_id=?
                          AND memory_type=? AND subject_key=? AND status='superseded'
                          AND superseded_by IS NULL
                        """,
                        (
                            stored["id"],
                            identity.user_id,
                            identity.agent_id,
                            identity.persona_id,
                            memory.memory_type,
                            memory.subject_key,
                        ),
                    )
            connection.execute(
                "INSERT INTO companion_turn(turn_id,user_id,agent_id,persona_id,state_revision,diagnostic_json,created_at) VALUES(?,?,?,?,?,?,?)",
                (
                    turn_id,
                    identity.user_id,
                    identity.agent_id,
                    identity.persona_id,
                    state.revision,
                    json.dumps(diagnostic or {}, ensure_ascii=False, separators=(",", ":")),
                    now,
                ),
            )
            connection.commit()
            return "committed"
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    async def search_memories(
        self,
        identity: CompanionIdentity,
        query: str,
        limit: int = 6,
        exclude_ids: set[int | str] | None = None,
    ) -> list[dict]:
        return self._search_memories_sync(identity, query, limit, exclude_ids)

    def _search_memories_sync(
        self,
        identity: CompanionIdentity,
        query: str,
        limit: int,
        exclude_ids: set[int | str] | None = None,
    ) -> list[dict]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id,memory_type,subject_key,content,importance,confidence,sensitivity,occurred_at,created_at,expires_at
                FROM companion_memory
                WHERE user_id=? AND agent_id=? AND persona_id=?
                  AND sensitivity IN ('public', 'personal')
                  AND status='active'
                  AND (expires_at IS NULL OR expires_at > ?)
                ORDER BY importance DESC, created_at DESC
                LIMIT 100
                """,
                (identity.user_id, identity.agent_id, identity.persona_id, iso_now()),
            ).fetchall()
            selected = rank_memories(
                rows, query, limit, exclude_ids=exclude_ids, embedder=self.embedder
            )
            if selected:
                connection.executemany(
                    "UPDATE companion_memory SET last_accessed_at=? WHERE id=?",
                    [(iso_now(), row["id"]) for row in selected],
                )
                connection.commit()
        return [dict(row) for row in selected]
