from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .models import PersonaSpec
from .state_models import CompanionEvent, CompanionIdentity, CompanionState


@dataclass
class CompanionSession:
    identity: CompanionIdentity
    session_id: str
    persona_spec: PersonaSpec
    persona_prompt: str
    state: CompanionState
    overlay: dict[str, Any] = field(default_factory=dict)
    memory_extractor: Any = None
    turn_preview_state: CompanionState | None = None
    turn_preview_events: list[CompanionEvent] = field(default_factory=list)
    pending_pre_turn_events: dict[str, list[CompanionEvent]] = field(default_factory=dict)
    pending_recalled_memories: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    pending_turn_diagnostics: dict[str, dict[str, Any]] = field(default_factory=dict)
    recent_memory_turns: list[list[str]] = field(default_factory=list)
    recent_example_turns: list[list[str]] = field(default_factory=list)
    recent_response_acts: list[str] = field(default_factory=list)
    recent_reply_openings: list[str] = field(default_factory=list)
    # Manager API signature assets are downloaded once when the session opens.
    # The canonical spec keeps portable asset:// URIs; only this process-local
    # map contains machine-specific cache paths.
    signature_asset_files: dict[str, str] = field(default_factory=dict)
    commit_pending: bool = False
