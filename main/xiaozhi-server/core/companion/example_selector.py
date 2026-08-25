from __future__ import annotations

import re
from typing import Collection

from .response_planner import ResponsePlan
from .semantic_text import semantic_concepts, semantic_tokens


LOW_SIGNAL_STYLE_TOKENS = {
    "我想",
    "你想",
    "帮我",
    "姐姐",
    "哥哥",
    "老师",
    "主播",
    "今天",
    "现在",
    "这个",
    "那个",
    "什么",
    "怎么",
    "可以",
    "还是",
    "有点",
}


def _retrieval_score(left: str, right: str) -> float:
    left_tokens = semantic_tokens(left) - LOW_SIGNAL_STYLE_TOKENS
    right_tokens = semantic_tokens(right) - LOW_SIGNAL_STYLE_TOKENS
    lexical = len(left_tokens & right_tokens)
    concepts = len(semantic_concepts(left) & semantic_concepts(right))
    return lexical + concepts * 2.5


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
        source = " ".join(
            (
                scene,
                str(item.get("user") or ""),
                " ".join(map(str, item.get("tags") or [])),
            )
        )
        score = _retrieval_score(query, source)
        if plan.dialogue_act in scene.lower():
            score += 3
        scored.append((score, -index, item_id, item))
    scored.sort(reverse=True, key=lambda value: (value[0], value[1]))
    selected = [value for value in scored if value[0] > 0][:limit]
    # A Persona's cadence is often carried by examples rather than adjectives.
    # When lexical retrieval finds no scene match, keep a small rotating style
    # anchor instead of sending the LLM no demonstration at all.
    if not selected:
        selected = scored[: min(limit, 2)]
    result = []
    for _, _, item_id, item in selected:
        result.append({**item, "id": item_id})
    return result


def render_examples(examples: list[dict]) -> str:
    if not examples:
        return ""
    lines = [
        "<situational_examples>",
        "以下示例只用于模仿当前场景的节奏和表达，不要照抄事实：",
    ]
    for item in examples:
        lines.append(
            f"- 场景：{str(item.get('scene') or '对话')[:80]}；"
            f"用户：{str(item.get('user') or '')[:180]}；"
            f"角色：{str(item.get('assistant') or '')[:240]}"
        )
    lines.extend(["示例中的经历不是本轮事实。", "</situational_examples>"])
    return "\n".join(lines)


def select_source_sections(
    sections: list[dict],
    user_message: str,
    plan: ResponsePlan,
    limit: int = 2,
) -> list[dict]:
    query = " ".join((user_message, plan.dialogue_act, *plan.scene_tags))
    scored = []
    for index, item in enumerate(sections or []):
        if not isinstance(item, dict) or item.get("category") == "references":
            continue
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        title = str(item.get("title") or "")
        score = _retrieval_score(query, f"{title} {content}")
        if score <= 0:
            continue
        try:
            priority = int(item.get("runtime_priority", 40))
        except (TypeError, ValueError):
            priority = 40
        scored.append((score, priority, -index, item))
    scored.sort(reverse=True, key=lambda value: (value[0], value[1], value[2]))
    return [item for _, _, _, item in scored[:limit]]


def render_source_sections(sections: list[dict]) -> str:
    if not sections:
        return ""
    lines = [
        "<persona_scene_rules>",
        "以下是原 Skill 中与本轮语境最相关的规则；优先按其接球机制回应，不要退回通用助手话术：",
    ]
    for item in sections:
        title = str(item.get("title") or "人物规则")[:100]
        content = re.sub(r"\s+", " ", str(item.get("content") or "")).strip()[:900]
        if content:
            lines.append(f"- {title}：{content}")
    lines.extend(
        [
            "只迁移表达机制，不把参考材料中的经历冒充为本轮事实。",
            "</persona_scene_rules>",
        ]
    )
    return "\n".join(lines)
