from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


PERSONA_SCHEMA_VERSION = "cyber-persona/v1"


@dataclass
class ValidationIssue:
    code: str
    message: str
    path: str = ""
    severity: str = "warning"


@dataclass
class ValidationReport:
    valid: bool = True
    issues: list[ValidationIssue] = field(default_factory=list)

    def add(self, code: str, message: str, path: str = "", severity: str = "warning"):
        self.issues.append(ValidationIssue(code, message, path, severity))
        if severity == "error":
            self.valid = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PersonaSpec:
    id: str
    display_name: str
    source: dict[str, Any]
    identity: dict[str, Any]
    core_rules: list[dict[str, Any]] = field(default_factory=list)
    expression: dict[str, Any] = field(default_factory=dict)
    emotional_logic: dict[str, Any] = field(default_factory=dict)
    conflict_repair: dict[str, Any] = field(default_factory=dict)
    mental_models: list[dict[str, Any]] = field(default_factory=list)
    decision_heuristics: list[str] = field(default_factory=list)
    relationship_policy: dict[str, Any] = field(default_factory=dict)
    examples: list[dict[str, Any]] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    quality: dict[str, Any] = field(default_factory=dict)
    schema_version: str = PERSONA_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "PersonaSpec":
        known = {
            "id",
            "display_name",
            "source",
            "identity",
            "core_rules",
            "expression",
            "emotional_logic",
            "conflict_repair",
            "mental_models",
            "decision_heuristics",
            "relationship_policy",
            "examples",
            "limitations",
            "quality",
            "schema_version",
        }
        return cls(**{key: value[key] for key in known if key in value})
