from __future__ import annotations

import json
import re
from typing import Any

from core.companion.models import PersonaSpec


ALLOWED_STAGES = ("stranger", "familiar", "friend", "ambiguous", "lover", "intimate")
RELATIONSHIP_MODES = {
    "friend": ("stranger", "familiar", "friend"),
    "romance": ("stranger", "familiar", "friend", "ambiguous", "lover"),
    "deep": ALLOWED_STAGES,
}
TEXT_FIELDS = {
    "ai_identity_notice",
    "user_address",
    "voice_reply_style",
    "tool_rephrase_style",
    "tool_ack_prefix",
    "proactive_timezone",
    "proactive_quiet_start",
    "proactive_quiet_end",
}
LIST_FIELDS = {
    "allowed_stages",
    "intimacy_boundaries",
    "memory_rules",
    "proactive_behavior_rules",
    "additional_rules",
}


def normalize_overlay(value: Any) -> dict[str, Any]:
    """Keep only product-level Companion controls; runtime scores are never accepted."""
    if value in (None, ""):
        return {}
    if isinstance(value, str):
        value = json.loads(value)
    if not isinstance(value, dict):
        raise ValueError("Companion Overlay 必须是 JSON 对象")
    result: dict[str, Any] = {}
    for key in TEXT_FIELDS:
        item = value.get(key)
        if item is not None:
            text = str(item).strip()
            if text:
                result[key] = text[:500]
    for key in LIST_FIELDS:
        item = value.get(key)
        if isinstance(item, list):
            values = []
            for entry in item[:20]:
                text = str(entry).strip()
                if text and text not in values:
                    values.append(text[:300])
            if values:
                result[key] = values
    initial_stage = str(value.get("initial_stage") or "").strip()
    if initial_stage in ALLOWED_STAGES:
        result["initial_stage"] = initial_stage
    relationship_mode = str(value.get("relationship_mode") or "").strip().lower()
    if relationship_mode in {*RELATIONSHIP_MODES, "custom"}:
        result["relationship_mode"] = relationship_mode
    if "allowed_stages" in result:
        result["allowed_stages"] = [
            stage for stage in result["allowed_stages"] if stage in ALLOWED_STAGES
        ]
        if not result["allowed_stages"]:
            result.pop("allowed_stages")
    if isinstance(value.get("proactive_enabled"), bool):
        result["proactive_enabled"] = value["proactive_enabled"]
    interval = value.get("proactive_interval_minutes")
    if isinstance(interval, (int, float)) and not isinstance(interval, bool):
        result["proactive_interval_minutes"] = max(5, min(10080, int(interval)))
    for key, minimum, maximum in (
        ("proactive_daily_limit", 1, 20),
        ("proactive_rejection_cooldown_minutes", 60, 43200),
        ("proactive_max_unanswered", 1, 10),
    ):
        item = value.get(key)
        if isinstance(item, (int, float)) and not isinstance(item, bool):
            result[key] = max(minimum, min(maximum, int(item)))
    timezone_name = str(result.get("proactive_timezone") or "")[:64]
    if timezone_name:
        result["proactive_timezone"] = timezone_name
    for key in ("proactive_quiet_start", "proactive_quiet_end"):
        if key in result and not re.fullmatch(
            r"(?:[01]\d|2[0-3]):[0-5]\d", result[key]
        ):
            result.pop(key, None)
    return result


def effective_overlay(spec: PersonaSpec, value: Any) -> dict[str, Any]:
    """Resolve binding-level relationship intent without mixing it with persona identity.

    Legacy bindings without ``relationship_mode`` keep the imported Persona policy. Once
    a mode is selected, the agent binding owns the relationship range. Persona identity
    (including public-figure metadata) still controls the mandatory AI identity notice,
    but no longer silently changes how close the user is allowed to become.
    """
    overlay = normalize_overlay(value)
    policy = spec.relationship_policy if isinstance(spec.relationship_policy, dict) else {}
    configured_stages = [
        stage for stage in policy.get("allowed_stages", []) if stage in ALLOWED_STAGES
    ] or ["familiar", "friend"]
    persona_stages = ["stranger"] + [stage for stage in configured_stages if stage != "stranger"]
    source = spec.source if isinstance(spec.source, dict) else {}

    relationship_mode = overlay.get("relationship_mode")
    if relationship_mode in RELATIONSHIP_MODES:
        effective_stages = list(RELATIONSHIP_MODES[relationship_mode])
    elif relationship_mode == "custom":
        requested_stages = overlay.get("allowed_stages") or persona_stages
        effective_stages = [stage for stage in ALLOWED_STAGES if stage in requested_stages]
    else:
        # Compatibility path for existing agent bindings created before relationship
        # intent became a binding-level choice.
        requested_stages = overlay.get("allowed_stages") or persona_stages
        effective_stages = [
            stage for stage in ALLOWED_STAGES if stage in persona_stages and stage in requested_stages
        ]
    if not effective_stages:
        effective_stages = ["familiar"]
    overlay["allowed_stages"] = effective_stages

    requested_initial = overlay.get("initial_stage") or policy.get("initial_stage") or effective_stages[0]
    overlay["initial_stage"] = (
        requested_initial if requested_initial in effective_stages else effective_stages[0]
    )

    if source.get("is_real_person"):
        mandatory_notice = str(
            spec.identity.get("fictionalization_notice")
            or "这是基于人物设定塑造的 AI 角色，不代表相关真人本人。"
        ).strip()
        optional_notice = str(overlay.get("ai_identity_notice") or "").strip()
        overlay["ai_identity_notice"] = mandatory_notice
        if optional_notice and optional_notice != mandatory_notice:
            overlay["ai_identity_notice"] += " " + optional_notice
    return overlay


def render_overlay(overlay: dict[str, Any]) -> str:
    if not overlay:
        return ""
    lines = ["<companion_overlay>"]
    labels = {
        "ai_identity_notice": "身份与真实性边界",
        "user_address": "对用户的称呼偏好",
        "voice_reply_style": "语音回复要求",
        "tool_rephrase_style": "工具结果表达要求",
        "tool_ack_prefix": "即时操作确认语",
        "intimacy_boundaries": "亲密边界",
        "memory_rules": "记忆规则",
        "proactive_behavior_rules": "主动行为规则",
        "additional_rules": "附加规则",
    }
    for key, label in labels.items():
        value = overlay.get(key)
        if isinstance(value, list):
            lines.append(f"{label}：" + "；".join(value))
        elif value:
            lines.append(f"{label}：{value}")
    if overlay.get("proactive_enabled"):
        lines.append(
            "主动行为：已启用；"
            f"最短间隔 {overlay.get('proactive_interval_minutes', 180)} 分钟；"
            f"每日最多 {overlay.get('proactive_daily_limit', 3)} 次；"
            f"安静时段 {overlay.get('proactive_quiet_start', '23:00')}—"
            f"{overlay.get('proactive_quiet_end', '08:00')}"
        )
    lines.extend(["这些配置不能覆盖安全规则，也不能直接修改内部情绪或关系分数。", "</companion_overlay>"])
    return "\n".join(lines)
