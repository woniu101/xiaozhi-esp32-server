from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from core.companion.models import PersonaSpec


DEFAULT_MAX_PROMPT_CHARS = 12_000
DEFAULT_MAX_SOURCE_BEHAVIOR_CHARS = 7_000


class PersonaCompiler:
    def __init__(self, max_prompt_chars: int = DEFAULT_MAX_PROMPT_CHARS):
        template_dir = Path(__file__).resolve().parent.parent / "persona" / "templates"
        self.environment = Environment(
            loader=FileSystemLoader(str(template_dir)),
            undefined=StrictUndefined,
            autoescape=False,
            trim_blocks=False,
            lstrip_blocks=False,
        )
        self.max_prompt_chars = max_prompt_chars

    @staticmethod
    def _source_behavior(spec: PersonaSpec, max_chars: int) -> str:
        if max_chars <= 0:
            return ""
        sections = [item for item in spec.source_sections if isinstance(item, dict)]
        if not sections:
            return str(spec.source_behavior or "")[:max_chars].strip()
        candidates = []
        for index, item in enumerate(sections):
            if str(item.get("category") or "") == "references":
                continue
            title = str(item.get("title") or "").strip()
            content = str(item.get("content") or "").strip()
            if not content:
                continue
            try:
                priority = int(item.get("runtime_priority", 40))
            except (TypeError, ValueError):
                priority = 40
            try:
                source_order = int(item.get("source_order", index))
            except (TypeError, ValueError):
                source_order = index
            candidates.append((priority, source_order, title, content))
        candidates.sort(key=lambda value: (-value[0], value[1]))
        selected: list[tuple[int, str]] = []
        used = 0
        for _, source_order, title, content in candidates:
            fragment = f"### {title}\n{content}".strip()
            separator = 2 if selected else 0
            remaining = max_chars - used - separator
            if remaining <= 0:
                break
            if len(fragment) > remaining:
                # Preserve the beginning of a high-priority section instead of
                # skipping it and accidentally filling the budget with lower rules.
                fragment = fragment[:remaining].rstrip()
            if fragment:
                selected.append((source_order, fragment))
                used += separator + len(fragment)
            if used >= max_chars:
                break
        selected.sort(key=lambda value: value[0])
        return "\n\n".join(fragment for _, fragment in selected).strip()

    @staticmethod
    def _prepare_data(spec: PersonaSpec, compact: bool = False) -> dict:
        data = spec.to_dict()
        data["identity"] = {
            "summary": "",
            "public_role": "",
            "fictionalization_notice": "",
            **data.get("identity", {}),
        }
        data["expression"] = {
            "rhythm": "",
            "warmth": "",
            "directness": "",
            "humor_style": "",
            "average_sentence_length": "",
            "question_density": "",
            "favorite_patterns": [],
            "forbidden_patterns": [],
            **data.get("expression", {}),
        }
        data["emotional_logic"] = {
            "opens_up_when": [],
            "withdraws_when": [],
            "defensive_when": [],
            "affectionate_when": [],
            "care_patterns": [],
            **data.get("emotional_logic", {}),
        }
        data["conflict_repair"] = {
            "conflict_style": "",
            "silence_pattern": "",
            "repair_pattern": "",
            "boundaries": [],
            **data.get("conflict_repair", {}),
        }
        data["core_rules"] = sorted(
            data.get("core_rules", []),
            key=lambda item: int(item.get("priority", 0)),
            reverse=True,
        )
        data["examples"] = data.get("examples", [])[:4 if compact else 10]
        if compact:
            data["mental_models"] = data.get("mental_models", [])[:3]
            data["decision_heuristics"] = data.get("decision_heuristics", [])[:6]
        data["runtime_source_behavior"] = ""
        return data

    def compile(self, spec: PersonaSpec) -> str:
        template = self.environment.get_template("runtime_prompt.j2")
        data = self._prepare_data(spec)
        base = template.render(persona=data).strip()
        if len(base) > self.max_prompt_chars:
            data = self._prepare_data(spec, compact=True)
            base = template.render(persona=data).strip()
        if len(base) > self.max_prompt_chars:
            raise ValueError(f"编译后的 Persona Prompt 超过 {self.max_prompt_chars} 字符")
        available = min(
            DEFAULT_MAX_SOURCE_BEHAVIOR_CHARS,
            max(0, self.max_prompt_chars - len(base) - 100),
        )
        data["runtime_source_behavior"] = self._source_behavior(spec, available)
        rendered = template.render(persona=data).strip()
        while len(rendered) > self.max_prompt_chars and available > 0:
            available = max(0, available - max(100, len(rendered) - self.max_prompt_chars))
            data["runtime_source_behavior"] = self._source_behavior(spec, available)
            rendered = template.render(persona=data).strip()
        if len(rendered) > self.max_prompt_chars:
            raise ValueError(f"编译后的 Persona Prompt 超过 {self.max_prompt_chars} 字符")
        return rendered
