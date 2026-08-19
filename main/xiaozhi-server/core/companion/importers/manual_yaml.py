from __future__ import annotations

from pathlib import Path

import yaml

from core.companion.importers.base import ImportInspection, ImportResult, PersonaImportAdapter
from core.companion.importers.validator import PersonaSpecValidator
from core.companion.models import PersonaSpec
from core.companion.persona.registry import content_hash


class ManualYamlAdapter(PersonaImportAdapter):
    def detect(self, source_path: str | Path) -> bool:
        path = Path(source_path)
        return path.is_file() and path.suffix.lower() in {".yaml", ".yml"}

    def inspect(self, source_path: str | Path) -> ImportInspection:
        path = Path(source_path)
        return ImportInspection("manual-yaml", self.detect(path), str(path))

    def convert(self, source_path: str | Path) -> ImportResult:
        path = Path(source_path)
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("Persona YAML 根节点必须是对象")
        spec = PersonaSpec.from_dict(data)
        raw = path.read_bytes()
        digest = content_hash({path.name: raw})
        spec.source.setdefault("adapter", "manual-yaml")
        spec.source.setdefault("family", "manual")
        spec.source.setdefault("artifact_sha256", digest)
        return ImportResult(spec, PersonaSpecValidator().validate(spec), [path.name], digest)
