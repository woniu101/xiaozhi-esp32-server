from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from core.companion.models import PersonaSpec, ValidationReport


@dataclass
class ImportInspection:
    adapter: str
    detected: bool
    source_path: str
    metadata: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


@dataclass
class ImportResult:
    spec: PersonaSpec
    report: ValidationReport
    source_files: list[str]
    artifact_sha256: str


class PersonaImportAdapter(ABC):
    @abstractmethod
    def detect(self, source_path: str | Path) -> bool:
        raise NotImplementedError

    @abstractmethod
    def inspect(self, source_path: str | Path) -> ImportInspection:
        raise NotImplementedError

    @abstractmethod
    def convert(self, source_path: str | Path) -> ImportResult:
        raise NotImplementedError
