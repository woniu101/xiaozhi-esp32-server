from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from core.companion.models import PersonaSpec


DEFAULT_MAX_PROMPT_CHARS = 12_000


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

    def compile(self, spec: PersonaSpec) -> str:
        template = self.environment.get_template("runtime_prompt.j2")
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
        data["examples"] = data.get("examples", [])[:10]
        rendered = template.render(persona=data).strip()
        if len(rendered) <= self.max_prompt_chars:
            return rendered
        compact = dict(data)
        compact["examples"] = compact.get("examples", [])[:4]
        compact["mental_models"] = compact.get("mental_models", [])[:3]
        compact["decision_heuristics"] = compact.get("decision_heuristics", [])[:6]
        rendered = template.render(persona=compact).strip()
        if len(rendered) > self.max_prompt_chars:
            raise ValueError(f"编译后的 Persona Prompt 超过 {self.max_prompt_chars} 字符")
        return rendered
