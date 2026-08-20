from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from config.manage_api_client import ManageApiClient
from core.companion.observability import metrics
from core.companion.repositories.base import CompanionRepository
from core.companion.repositories.commit_outbox import DurableCommitOutbox
from core.companion.repositories.memory_ranking import rank_memories
from core.companion.state_reducer import StateReducer
from core.companion.state_models import CompanionEvent, CompanionIdentity, CompanionState, MemoryCandidate


class ManagerApiCompanionRepository(CompanionRepository):
    """MySQL-backed repository accessed through manager-api's server-secret endpoints."""

    def __init__(self, embedder=None, outbox_path: str | Path | None = None):
        self.embedder = embedder
        self.outbox = DurableCommitOutbox(outbox_path) if outbox_path else None
        self.reducer = StateReducer()
        self._drain_task = None
        self._drain_lock = asyncio.Lock()

    def _client(self):
        if ManageApiClient._instance is None:
            raise RuntimeError("manager-api client 尚未初始化")
        return ManageApiClient._instance

    async def get_state(self, identity: CompanionIdentity) -> CompanionState:
        if getattr(self, "outbox", None) is not None and await self.has_pending_commits(identity):
            try:
                await asyncio.wait_for(self.flush_pending(force=True, limit=50), timeout=1.0)
            except Exception:
                self._schedule_drain()
        return await self._fetch_state(identity, retry=True)

    async def _fetch_state(self, identity: CompanionIdentity, retry: bool) -> CompanionState:
        requester = (
            self._client()._execute_async_request
            if retry
            else self._client()._async_request
        )
        value = await requester(
            "POST",
            "/config/companion/state",
            json={
                "userId": identity.user_id,
                "agentId": identity.agent_id,
                "personaId": identity.persona_id,
            },
        )
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
        payload = {
            "userId": identity.user_id,
            "agentId": identity.agent_id,
            "personaId": identity.persona_id,
            "turnId": turn_id,
            "expectedRevision": expected_revision,
            "state": state.to_dict(),
            "events": [
                {
                    "eventType": event.event_type,
                    "confidence": event.confidence,
                    "payload": event.payload,
                }
                for event in events
            ],
            "memories": [
                {
                    "memoryType": memory.memory_type,
                    "subjectKey": memory.subject_key,
                    "content": memory.content,
                    "importance": memory.importance,
                    "confidence": memory.confidence,
                    "sensitivity": memory.sensitivity,
                    "occurredAt": memory.occurred_at,
                    "expiresAt": memory.expires_at,
                    "operation": memory.operation,
                }
                for memory in memories
            ],
            "diagnostic": diagnostic or {},
        }
        outbox = getattr(self, "outbox", None)
        if outbox is not None and await self.has_pending_commits(identity):
            await self.flush_pending(force=True, limit=50)
            if await self.has_pending_commits(identity):
                outbox.enqueue(payload, "waiting for earlier commits")
                metrics.increment("companion_outbox_enqueued_total", reason="ordered_after_pending")
                self._schedule_drain()
                return "queued"
        try:
            return await self._client()._execute_async_request(
                "POST", "/config/companion/commit", json=payload
            )
        except Exception as error:
            if outbox is None:
                raise
            outbox.enqueue(payload, str(error))
            metrics.increment("companion_outbox_enqueued_total", reason="commit_failed")
            self._schedule_drain()
            return "queued"

    async def has_pending_commits(self, identity: CompanionIdentity) -> bool:
        outbox = getattr(self, "outbox", None)
        if outbox is None:
            return False
        count = outbox.count(
            identity.user_id,
            identity.agent_id,
            identity.persona_id,
        )
        return count > 0

    def _schedule_drain(self):
        if getattr(self, "outbox", None) is None:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        if getattr(self, "_drain_task", None) is None or self._drain_task.done():
            self._drain_task = loop.create_task(self._drain_loop())

    async def _drain_loop(self):
        while self.outbox is not None and self.outbox.count() > 0:
            wait_seconds = self.outbox.seconds_until_next()
            if wait_seconds > 0:
                await asyncio.sleep(min(wait_seconds, 300))
            await self.flush_pending(force=False, limit=50)

    async def flush_pending(self, force: bool = False, limit: int = 50) -> int:
        if getattr(self, "outbox", None) is None:
            return 0
        lock = getattr(self, "_drain_lock", None)
        if lock is None:
            self._drain_lock = asyncio.Lock()
            lock = self._drain_lock
        async with lock:
            return await self._flush_pending_unlocked(force, limit)

    async def _flush_pending_unlocked(self, force: bool, limit: int) -> int:
        delivered = 0
        rows = self.outbox.due(limit, force)
        blocked_identities: set[tuple[str, str, str]] = set()
        for row in rows:
            identity_key = (row["user_id"], row["agent_id"], row["persona_id"])
            if identity_key in blocked_identities:
                continue
            payload = row["payload"]
            try:
                result = await self._client()._async_request(
                    "POST", "/config/companion/commit", json=payload
                )
                if result == "conflict":
                    payload = await self._rebase_payload(payload)
                    self.outbox.replace_payload(row["id"], payload)
                    result = await self._client()._async_request(
                        "POST", "/config/companion/commit", json=payload
                    )
                    metrics.increment("companion_outbox_rebased_total")
                if result in {"committed", "duplicate"}:
                    self.outbox.mark_delivered(row["id"])
                    delivered += 1
                    metrics.increment("companion_outbox_delivered_total", result=result)
                    continue
                raise RuntimeError(f"unexpected Companion commit result: {result}")
            except Exception as error:
                attempts = int(row.get("attempts") or 0) + 1
                self.outbox.postpone(row["id"], attempts, str(error))
                blocked_identities.add(identity_key)
                metrics.increment("companion_outbox_retry_total", reason=type(error).__name__)
        return delivered

    async def _rebase_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        identity = CompanionIdentity(
            str(payload["userId"]),
            str(payload["agentId"]),
            str(payload["personaId"]),
        )
        remote = await self._fetch_state(identity, retry=False)
        events = [
            CompanionEvent(
                str(item.get("eventType") or ""),
                float(item.get("confidence") or 0),
                item.get("payload") if isinstance(item.get("payload"), dict) else {},
            )
            for item in payload.get("events", [])
            if isinstance(item, dict) and item.get("eventType")
        ]
        diagnostic = payload.get("diagnostic") if isinstance(payload.get("diagnostic"), dict) else {}
        allowed = diagnostic.get("allowedStages")
        allowed_stages = allowed if isinstance(allowed, list) else None
        rebased = self.reducer.reduce(
            remote,
            events,
            bool(diagnostic.get("meaningfulTurn", False)),
            allowed_stages,
        )
        value = dict(payload)
        value["expectedRevision"] = remote.revision
        value["state"] = rebased.to_dict()
        value["diagnostic"] = {
            **diagnostic,
            "stateBefore": remote.to_dict(),
            "stateAfter": rebased.to_dict(),
            "outboxRebased": True,
        }
        return value

    async def search_memories(
        self,
        identity: CompanionIdentity,
        query: str,
        limit: int = 6,
        exclude_ids: set[int | str] | None = None,
    ) -> list[dict]:
        rows = await self._client()._execute_async_request(
            "POST",
            "/config/companion/memories/search",
            json={
                "userId": identity.user_id,
                "agentId": identity.agent_id,
                "personaId": identity.persona_id,
                "query": query,
                "limit": 100,
            },
        )
        return rank_memories(
            rows or [], query, limit, exclude_ids=exclude_ids, embedder=getattr(self, "embedder", None)
        )
