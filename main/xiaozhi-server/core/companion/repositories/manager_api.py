from __future__ import annotations

from config.manage_api_client import ManageApiClient
from core.companion.repositories.base import CompanionRepository
from core.companion.repositories.memory_ranking import rank_memories
from core.companion.state_models import CompanionEvent, CompanionIdentity, CompanionState, MemoryCandidate


class ManagerApiCompanionRepository(CompanionRepository):
    """MySQL-backed repository accessed through manager-api's server-secret endpoints."""

    def _client(self):
        if ManageApiClient._instance is None:
            raise RuntimeError("manager-api client 尚未初始化")
        return ManageApiClient._instance

    async def get_state(self, identity: CompanionIdentity) -> CompanionState:
        value = await self._client()._execute_async_request(
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
                }
                for memory in memories
            ],
        }
        return await self._client()._execute_async_request(
            "POST", "/config/companion/commit", json=payload
        )

    async def search_memories(
        self, identity: CompanionIdentity, query: str, limit: int = 6
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
        return rank_memories(rows or [], query, limit)
