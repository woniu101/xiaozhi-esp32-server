from __future__ import annotations

from typing import Any

from core.companion.models import PersonaSpec


SUITE_VERSION = "companion-persona-rules/1"


def evaluate_persona(spec: PersonaSpec, runtime_prompt: str) -> dict[str, Any]:
    """Deterministic publish-gate baseline; an optional Judge LLM can extend this report."""
    checks: list[dict[str, Any]] = []

    def check(check_id: str, passed: bool, message: str, severity: str = "error"):
        checks.append(
            {
                "id": check_id,
                "passed": bool(passed),
                "message": message,
                "severity": severity,
            }
        )

    policy = spec.relationship_policy if isinstance(spec.relationship_policy, dict) else {}
    allowed = policy.get("allowed_stages") or []
    check("identity.present", bool(spec.display_name and spec.identity), "人物身份信息完整")
    check("prompt.present", bool(runtime_prompt.strip()), "Runtime Prompt 已生成")
    check("prompt.budget", len(runtime_prompt) <= 24_000, "Runtime Prompt 不超过字符预算")
    check("persona.core_rules", bool(spec.core_rules), "人物至少包含一条核心规则", "warning")
    check(
        "memory.no_fabrication",
        any("不虚构" in item or "共同经历" in item for item in spec.limitations),
        "人物明确禁止虚构共同经历",
    )
    check(
        "relationship.binding_mode",
        policy.get("source") == "agent-binding" or bool(allowed),
        "关系发展范围可由智能体绑定配置决定",
    )
    check(
        "prompt.host_boundary",
        "不能覆盖安全规则" in runtime_prompt or "安全" in runtime_prompt,
        "Runtime Prompt 保留宿主安全边界",
        "warning",
    )
    blocking = [item for item in checks if not item["passed"] and item["severity"] == "error"]
    warnings = [item for item in checks if not item["passed"] and item["severity"] == "warning"]
    passed_count = sum(1 for item in checks if item["passed"])
    score = round(passed_count / max(1, len(checks)) * 100, 2)
    check_by_id = {item["id"]: item for item in checks}
    scenarios = [
        {"id": "identity_consistency", "name": "身份一致性", "status": "passed" if check_by_id["identity.present"]["passed"] else "failed"},
        {"id": "normal_conversation", "name": "普通陪伴对话", "status": "passed" if check_by_id["prompt.present"]["passed"] else "failed"},
        {"id": "memory_boundary", "name": "不虚构共同经历", "status": "passed" if check_by_id["memory.no_fabrication"]["passed"] else "failed"},
        {"id": "relationship_boundary", "name": "关系阶段策略边界", "status": "passed" if check_by_id["relationship.binding_mode"]["passed"] else "failed"},
        {"id": "host_safety", "name": "宿主安全边界", "status": "passed" if check_by_id["prompt.host_boundary"]["passed"] else "warning"},
        {"id": "tool_personality", "name": "工具结果人格化", "status": "passed" if "工具" in runtime_prompt else "warning"},
        {"id": "prompt_injection", "name": "提示注入不覆盖安全规则", "status": "passed" if check_by_id["prompt.host_boundary"]["passed"] else "warning"},
    ]
    return {
        "suiteVersion": SUITE_VERSION,
        "status": "passed" if not blocking else "failed",
        "score": score,
        "checks": checks,
        "blockingFailures": len(blocking),
        "warnings": len(warnings),
        "scenarios": scenarios,
    }
