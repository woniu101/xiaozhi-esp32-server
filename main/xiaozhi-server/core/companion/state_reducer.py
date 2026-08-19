from __future__ import annotations

from dataclasses import replace

from .emotion import EmotionEngine
from .relationship import RelationshipEngine
from .state_models import CompanionEvent, CompanionState


class StateReducer:
    def __init__(self):
        self.emotion = EmotionEngine()
        self.relationship = RelationshipEngine()

    def decay(self, state: CompanionState) -> CompanionState:
        return replace(
            state,
            emotion=self.emotion.decay(state.emotion),
            relationship=self.relationship.decay(state.relationship),
        )

    def reduce(
        self,
        state: CompanionState,
        events: list[CompanionEvent],
        meaningful_turn: bool,
        allowed_stages: list[str] | None = None,
    ) -> CompanionState:
        return CompanionState(
            emotion=self.emotion.apply(state.emotion, events),
            relationship=self.relationship.apply(state.relationship, events, meaningful_turn, allowed_stages),
            revision=state.revision + 1,
        )

    def preview(
        self,
        state: CompanionState,
        events: list[CompanionEvent],
        allowed_stages: list[str] | None = None,
    ) -> CompanionState:
        """Apply current-user signals for response generation without committing a revision."""
        return CompanionState(
            emotion=self.emotion.apply(state.emotion, events),
            relationship=self.relationship.apply(state.relationship, events, False, allowed_stages),
            revision=state.revision,
        )
