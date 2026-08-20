from __future__ import annotations

import asyncio
import inspect
import json
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

    async def before_turn(
        self,
        session: CompanionSession,
        user_message: str,
        turn_id: str | None = None,
        track_turn: bool = True,
    ) -> CompanionTurnContext:
        started = perf_counter()
        try:
            if session.commit_pending:
                try:
                    refreshed = await self.repository.get_state(session.identity)
                    if refreshed.revision >= session.state.revision:
                        session.state = refreshed
                    session.commit_pending = await self.repository.has_pending_commits(
                        session.identity
                    )
                except Exception:
                    metrics.increment("companion_outbox_state_refresh_failed_total")
            session.state = self.reducer.decay(session.state)
            events = self.extractor.extract_pre_turn(user_message)
            allowed = session.overlay.get("allowed_stages") or session.persona_spec.relationship_policy.get("allowed_stages")
            preview_state = self.reducer.preview(session.state, events, allowed)
            if track_turn:
                session.turn_preview_state = preview_state
                session.turn_preview_events = events
                session.pending_pre_turn_events[turn_id or "__latest__"] = events
            context = await self.context_builder.build(
                session,
                user_message,
                state=preview_state,
                events=events,
                turn_id=turn_id,
                track_turn=track_turn,
            )
            if track_turn:
                session.pending_turn_diagnostics[turn_id or "__latest__"] = {
                    "personaId": session.identity.persona_id,
                    "personaVersion": session.identity.persona_version,
                    "relationshipMode": session.overlay.get("relationship_mode", "legacy"),
                    "stateBefore": session.state.to_dict(),
                    "previewState": preview_state.to_dict(),
                    "responsePlan": context.metadata.get("response_plan", {}),
                    "recalledMemoryIds": context.metadata.get("recalled_memory_ids", []),
                    "selectedExampleIds": context.metadata.get("selected_example_ids", []),
                    "contextBuildMs": round((perf_counter() - started) * 1000, 3),
                }
            return context
        except Exception:
            if track_turn:
                self._clear_turn_preview(session)
                session.pending_pre_turn_events.pop(turn_id or "__latest__", None)
                session.pending_recalled_memories.pop(turn_id or "__latest__", None)
                session.pending_turn_diagnostics.pop(turn_id or "__latest__", None)
            raise
        finally:
            metrics.observe_ms("companion_before_turn_latency_ms", (perf_counter() - started) * 1000)

    async def after_turn(self, session: CompanionSession, turn: CompletedTurn) -> None:
        started = perf_counter()
        pre_turn_events = self._pop_turn_value(session.pending_pre_turn_events, turn.turn_id)
        recalled_memories = self._pop_turn_value(session.pending_recalled_memories, turn.turn_id)
        diagnostic_value = self._pop_turn_value(session.pending_turn_diagnostics, turn.turn_id)
        diagnostic = diagnostic_value if isinstance(diagnostic_value, dict) else {}
        if turn.aborted or turn.failed_reason:
            events, memories = [], []
        else:
            extractor = session.memory_extractor or self.extractor
            extract_args = (
                turn,
                session.overlay.get("memory_rules") or [],
                recalled_memories,
            )
            try:
                if isinstance(extractor, RuleBasedEventExtractor) and extractor.structured_extractor is None:
                    events, memories = extractor.extract(*extract_args)
                else:
                    events, memories = await asyncio.to_thread(extractor.extract, *extract_args)
            except Exception:
                self._clear_turn_preview(session)
                raise
            events = self._deduplicate_events([*pre_turn_events, *events])
        allowed = session.overlay.get("allowed_stages") or session.persona_spec.relationship_policy.get("allowed_stages")
        meaningful = is_meaningful_turn(turn, events)
        for _ in range(3):
            expected_revision = session.state.revision
            new_state = self.reducer.reduce(session.state, events, meaningful, allowed)
            commit_diagnostic = {
                **diagnostic,
                **(turn.diagnostic if isinstance(turn.diagnostic, dict) else {}),
                "turnId": turn.turn_id,
                "aborted": bool(turn.aborted),
                "failed": bool(turn.failed_reason),
                "meaningfulTurn": meaningful,
                "allowedStages": list(allowed or []),
                "eventTypes": [event.event_type for event in events],
                "memoryCandidates": [
                    {
                        "type": item.memory_type,
                        "subjectKey": item.subject_key,
                        "operation": item.operation,
                    }
                    for item in memories
                ],
                "stateAfter": new_state.to_dict(),
                "postProcessMs": round((perf_counter() - started) * 1000, 3),
            }
            try:
                result = await self.repository.commit_turn(
                    session.identity,
                    turn.turn_id,
                    expected_revision,
                    new_state,
                    events,
                    memories,
                    commit_diagnostic,
                )
            except Exception:
                self._clear_turn_preview(session)
                raise
            if result == "committed":
                session.state = new_state
                opening = re.sub(r"\s+", " ", turn.assistant_message).strip()[:80]
                if opening:
                    session.recent_reply_openings.append(opening)
                    del session.recent_reply_openings[:-3]
                self._clear_turn_preview(session)
                for memory in memories:
                    metrics.increment(
                        "companion_memory_saved_total",
                        type=memory.memory_type,
                        sensitivity=memory.sensitivity,
                    )
                metrics.observe_ms("companion_after_turn_latency_ms", (perf_counter() - started) * 1000)
                return
            if result == "queued":
                session.commit_pending = True
                self._clear_turn_preview(session)
                metrics.increment("companion_commit_queued_total")
                metrics.observe_ms(
                    "companion_after_turn_latency_ms",
                    (perf_counter() - started) * 1000,
                    status="queued",
                )
                return
            if result == "duplicate":
                session.state = await self.repository.get_state(session.identity)
                self._clear_turn_preview(session)
                metrics.observe_ms("companion_after_turn_latency_ms", (perf_counter() - started) * 1000,
                                   status="duplicate")
                return
            session.state = await self.repository.get_state(session.identity)
            metrics.increment("companion_state_cas_conflict_total")
        metrics.observe_ms("companion_after_turn_latency_ms", (perf_counter() - started) * 1000, status="failed")
        self._clear_turn_preview(session)
        raise RuntimeError("Companion 状态并发更新失败，超过最大重试次数")

    def _deduplicate_events(self, events):
        result = []
        seen = set()
        for event in events:
            payload = json.dumps(event.payload or {}, ensure_ascii=False, sort_keys=True, default=str)
            key = (event.event_type, payload)
            if key in seen:
                continue
            seen.add(key)
            result.append(event)
        return result

    def _pop_turn_value(self, values: dict, turn_id: str):
        result = values.pop(turn_id, None)
        if result is None:
            return values.pop("__latest__", [])
        values.pop("__latest__", None)
        return result

    def _clear_turn_preview(self, session: CompanionSession):
        session.turn_preview_state = None
        session.turn_preview_events = []
