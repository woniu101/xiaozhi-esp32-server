from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .models import PersonaSpec
from .state_models import CompanionIdentity, CompanionState


@dataclass
class CompanionSession:
    identity: CompanionIdentity
    session_id: str
    persona_spec: PersonaSpec
    persona_prompt: str
    state: CompanionState
    overlay: dict[str, Any] = field(default_factory=dict)
    memory_extractor: Any = None
