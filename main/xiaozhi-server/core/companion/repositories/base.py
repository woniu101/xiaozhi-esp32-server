from __future__ import annotations

from abc import ABC, abstractmethod

from core.companion.state_models import CompanionEvent, CompanionIdentity, CompanionState, MemoryCandidate


class CompanionRepository(ABC):
    @abstractmethod
    async def get_state(self, identity: CompanionIdentity) -> CompanionState:
        raise NotImplementedError

    @abstractmethod
    async def commit_turn(
        self,
        identity: CompanionIdentity,
        turn_id: str,
        expected_revision: int,
        state: CompanionState,
        events: list[CompanionEvent],
        memories: list[MemoryCandidate],
    ) -> str:
        """Return committed, duplicate, or conflict."""
        raise NotImplementedError

    @abstractmethod
    async def search_memories(
        self,
        identity: CompanionIdentity,
        query: str,
        limit: int = 6,
        exclude_ids: set[int | str] | None = None,
    ) -> list[dict]:
        raise NotImplementedError
