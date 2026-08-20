from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return utc_now().isoformat()


@dataclass
class EmotionState:
    valence: float = 0.55
    arousal: float = 0.35
    warmth: float = 0.5
    irritation: float = 0.0
    fatigue: float = 0.1
    updated_at: str = field(default_factory=iso_now)


@dataclass
class RelationshipState:
    stage: str = "familiar"
    trust: float = 0.3
    affection: float = 0.3
    intimacy: float = 0.15
    conflict: float = 0.0
    meaningful_turns: int = 0
    shared_event_count: int = 0
    updated_at: str = field(default_factory=iso_now)


@dataclass
class CompanionState:
    emotion: EmotionState = field(default_factory=EmotionState)
    relationship: RelationshipState = field(default_factory=RelationshipState)
    revision: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any] | None) -> "CompanionState":
        if not value:
            return cls()
        return cls(
            emotion=EmotionState(**value.get("emotion", {})),
            relationship=RelationshipState(**value.get("relationship", {})),
            revision=int(value.get("revision", 0)),
        )


@dataclass(frozen=True)
class CompanionIdentity:
    user_id: str
    agent_id: str
    persona_id: str
    persona_version: str | None = None


@dataclass
class CompanionEvent:
    event_type: str
    confidence: float
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class MemoryCandidate:
    memory_type: str
    content: str
    importance: float
    confidence: float
    sensitivity: str = "personal"
    occurred_at: str | None = None
    subject_key: str | None = None
    expires_at: str | None = None
    operation: str = "upsert"


@dataclass
class CompanionTurnContext:
    persona_prompt: str
    runtime_state_prompt: str
    relevant_memories_prompt: str
    response_plan_prompt: str = ""
    situational_examples_prompt: str = ""
    expected_expression: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def render(self) -> str:
        blocks = [
            self.persona_prompt,
            self.runtime_state_prompt,
            self.response_plan_prompt,
            self.relevant_memories_prompt,
            self.situational_examples_prompt,
        ]
        return "\n\n".join(block for block in blocks if block).strip()


@dataclass
class CompletedTurn:
    turn_id: str
    user_message: str
    assistant_message: str
    tool_events: list[dict[str, Any]] = field(default_factory=list)
    aborted: bool = False
    failed_reason: str | None = None
    diagnostic: dict[str, Any] = field(default_factory=dict)
