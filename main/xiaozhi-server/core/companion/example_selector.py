from __future__ import annotations

import re
from typing import Collection

from .response_planner import ResponsePlan
from .semantic_text import semantic_overlap


STATIC_EXAMPLES_RE = re.compile(
    r"\n表达示例只用于学习风格，不要机械复述：.*?(?=\n能力与真实性限制：)",
    re.S,
)
TAGGED_EXAMPLES_RE = re.compile(r"\n?<persona_examples>.*?</persona_examples>\n?", re.S)


def strip_static_examples(prompt: str) -> str:
    value = TAGGED_EXAMPLES_RE.sub("\n", str(prompt or ""))
    return STATIC_EXAMPLES_RE.sub("\n", value).strip()


def select_examples(
    examples: list[dict],
    user_message: str,
    plan: ResponsePlan,
    recent_ids: Collection[str] | None = None,
    limit: int = 3,
) -> list[dict]:
    recent = set(recent_ids or [])
    scored = []
    query = " ".join((user_message, plan.dialogue_act, *plan.scene_tags))
    for index, item in enumerate(examples or []):
        if not isinstance(item, dict):
            continue
        assistant = str(item.get("assistant") or "").strip()
        if not assistant:
            continue
        item_id = str(item.get("id") or f"example-{index + 1:03d}")
        if item_id in recent:
            continue
        scene = str(item.get("scene") or "")
        source = " ".join((scene, str(item.get("user") or ""), " ".join(map(str, item.get("tags") or []))))
        score = semantic_overlap(query, source)
        if plan.dialogue_act in scene.lower():
            score += 3
        scored.append((score, -index, item_id, item))
    scored.sort(reverse=True, key=lambda value: (value[0], value[1]))
    selected = [value for value in scored if value[0] > 0][:limit]
    result = []
    for _, _, item_id, item in selected:
        result.append({**item, "id": item_id})
    return result


def render_examples(examples: list[dict]) -> str:
    if not examples:
        return ""
    lines = ["<situational_examples>", "以下示例只用于模仿当前场景的节奏和表达，不要照抄事实："]
    for item in examples:
        lines.append(
            f"- 场景：{str(item.get('scene') or '对话')[:80]}；"
            f"用户：{str(item.get('user') or '')[:180]}；"
            f"角色：{str(item.get('assistant') or '')[:240]}"
        )
    lines.extend(["示例中的经历不是本轮事实。", "</situational_examples>"])
    return "\n".join(lines)
