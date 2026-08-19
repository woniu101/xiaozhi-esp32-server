from __future__ import annotations

import asyncio
import inspect
import re
from dataclasses import replace
from time import perf_counter

from core.companion.context_builder import CompanionContextBuilder
from core.companion.event_extractor import RuleBasedEventExtractor
from core.companion.observability import metrics
from core.companion.overlay import effective_overlay
from core.companion.repositories.base import CompanionRepository
from core.companion.session import CompanionSession
from core.companion.state_models import CompanionIdentity, CompanionTurnContext, CompletedTurn
from core.companion.state_reducer import StateReducer


def is_meaningful_turn(turn: CompletedTurn, events) -> bool:
    compact_user_text = re.sub(r"\s+", "", turn.user_message or "")
    relationship_events = {event.event_type for event in events if event.event_type != "tool_used"}
    return (
        bool(compact_user_text and turn.assistant_message)
        and not turn.aborted
        and not turn.failed_reason
        and (len(compact_user_text) >= 4 or bool(relationship_events))
    )


class CompanionManager:
    def __init__(self, persona_registry, repository: CompanionRepository):
        self.persona_registry = persona_registry
        self.repository = repository
        self.context_builder = CompanionContextBuilder(repository)
        self.extractor = RuleBasedEventExtractor()
        self.reducer = StateReducer()

    async def open_session(
        self,
        identity: CompanionIdentity,
        session_id: str,
        overlay: dict | str | None = None,
    ) -> CompanionSession:
        loaded = self.persona_registry.load_for_runtime(
            identity.persona_id, identity.persona_version, agent_id=identity.agent_id
        )
        if inspect.isawaitable(loaded):
            loaded = await loaded
        spec, prompt, metadata = loaded
        resolved_identity = CompanionIdentity(
            user_id=identity.user_id,
            agent_id=identity.agent_id,
            persona_id=identity.persona_id,
            persona_version=metadata["version"],
        )
        state = await self.repository.get_state(resolved_identity)
        normalized_overlay = effective_overlay(spec, overlay)
        initial_stage = normalized_overlay.get("initial_stage") or spec.relationship_policy.get("initial_stage")
        if state.revision == 0 and initial_stage:
            state.relationship = replace(state.relationship, stage=initial_stage)
        return CompanionSession(resolved_identity, session_id, spec, prompt, state, normalized_overlay)

    async def before_turn(self, session: CompanionSession, user_message: str) -> CompanionTurnContext:
        started = perf_counter()
        try:
            session.state = self.reducer.decay(session.state)
            return await self.context_builder.build(session, user_message)
        finally:
            metrics.observe_ms("companion_before_turn_latency_ms", (perf_counter() - started) * 1000)

    async def after_turn(self, session: CompanionSession, turn: CompletedTurn) -> None:
        started = perf_counter()
        if turn.aborted or turn.failed_reason:
            events, memories = [], []
        else:
            extractor = session.memory_extractor or self.extractor
            events, memories = await asyncio.to_thread(
                extractor.extract,
                turn,
                session.overlay.get("memory_rules") or [],
            )
        allowed = session.overlay.get("allowed_stages") or session.persona_spec.relationship_policy.get("allowed_stages")
        meaningful = is_meaningful_turn(turn, events)
        for _ in range(3):
            expected_revision = session.state.revision
            new_state = self.reducer.reduce(session.state, events, meaningful, allowed)
            result = await self.repository.commit_turn(
                session.identity,
                turn.turn_id,
                expected_revision,
                new_state,
                events,
                memories,
            )
            if result == "committed":
                session.state = new_state
                for memory in memories:
                    metrics.increment(
                        "companion_memory_saved_total",
                        type=memory.memory_type,
                        sensitivity=memory.sensitivity,
                    )
                metrics.observe_ms("companion_after_turn_latency_ms", (perf_counter() - started) * 1000)
                return
            if result == "duplicate":
                session.state = await self.repository.get_state(session.identity)
                metrics.observe_ms("companion_after_turn_latency_ms", (perf_counter() - started) * 1000,
                                   status="duplicate")
                return
            session.state = await self.repository.get_state(session.identity)
            metrics.increment("companion_state_cas_conflict_total")
        metrics.observe_ms("companion_after_turn_latency_ms", (perf_counter() - started) * 1000, status="failed")
        raise RuntimeError("Companion 状态并发更新失败，超过最大重试次数")
