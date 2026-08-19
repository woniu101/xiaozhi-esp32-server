from __future__ import annotations

import re
import json
from pathlib import Path

from jsonschema import Draft202012Validator

from core.companion.models import PERSONA_SCHEMA_VERSION, PersonaSpec, ValidationReport


DANGEROUS_PATTERNS = (
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions", re.I),
    re.compile(r"忽略(所有|以上|之前).{0,8}(指令|提示词)"),
    re.compile(r"\b(?:bash|powershell|cmd)\s+-[a-z]", re.I),
    re.compile(r"(?:读取|发送|上传).{0,20}(密钥|token|secret|环境变量)", re.I),
    re.compile(r"</?(?:companion_persona|companion_runtime|relevant_memories)\b", re.I),
)


class PersonaSpecValidator:
    def __init__(self):
        schema_path = Path(__file__).resolve().parent.parent / "schemas" / "persona-spec-v1.schema.json"
        self.schema_validator = Draft202012Validator(json.loads(schema_path.read_text(encoding="utf-8")))

    def validate(self, spec: PersonaSpec) -> ValidationReport:
        report = ValidationReport()
        for error in sorted(self.schema_validator.iter_errors(spec.to_dict()), key=lambda item: list(item.path)):
            report.add(
                "schema.invalid",
                error.message,
                ".".join(str(part) for part in error.path),
                "error",
            )
        if spec.schema_version != PERSONA_SCHEMA_VERSION:
            report.add("schema.version", "不支持的 PersonaSpec 版本", "schema_version", "error")
        if not spec.id or len(spec.id) > 160:
            report.add("identity.id", "人物 ID 不能为空且不得超过 160 字符", "id", "error")
        if not spec.display_name or len(spec.display_name) > 100:
            report.add("identity.name", "人物名称不能为空且不得超过 100 字符", "display_name", "error")
        if not isinstance(spec.source, dict) or not spec.source.get("adapter"):
            report.add("source.adapter", "缺少人物来源 Adapter", "source.adapter", "error")
        family = spec.source.get("family")
        if family not in {"relationship", "celebrity", "colleague", "manual"}:
            report.add("source.family", f"未知人物 family: {family}", "source.family", "warning")
        if not spec.core_rules:
            report.add("persona.core_rules", "没有提取到核心人物规则", "core_rules", "warning")
        if not spec.expression:
            report.add("persona.expression", "没有提取到表达 DNA", "expression", "warning")
        serialized = str(spec.to_dict())
        for pattern in DANGEROUS_PATTERNS:
            if pattern.search(serialized):
                report.add(
                    "security.prompt_injection",
                    "人物内容包含疑似宿主控制或敏感数据指令，必须移除后才能发布",
                    severity="error",
                )
                break
        if len(serialized) > 200_000:
            report.add("persona.size", "PersonaSpec 体积超过限制", severity="error")
        if len(spec.examples) > 50:
            report.add("persona.examples", "示例超过 50 条，运行时将只选取部分示例", "examples")
        return report
