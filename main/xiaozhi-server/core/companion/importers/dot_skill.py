from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import yaml

from core.companion.importers.base import ImportInspection, ImportResult, PersonaImportAdapter
from core.companion.importers.compiler import PersonaCompiler
from core.companion.importers.markdown_sections import bullets, find_section, find_sections, parse_sections, prose
from core.companion.importers.safe_source import (
    locate_artifacts,
    locate_behavior_references,
    materialize_source,
)
from core.companion.importers.validator import PersonaSpecValidator
from core.companion.models import PersonaSpec
from core.companion.persona.registry import FilesystemPersonaRegistry, content_hash


DEFAULT_REGISTRY = "data/companion/personas"
SUPPORTED_UPSTREAM_SCHEMAS = {"1", "2", "3", ""}
SKILL_FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*(?:\n|$)", re.S)
PERSONA_SECTION_MARKERS = (
    "角色扮演规则",
    "身份卡",
    "人物设定",
    "核心心智模型",
    "心智模型",
    "表达dna",
    "表达风格",
    "诚实边界",
    "内在张力",
    "relationship context",
    "expression dna",
    "mental models",
)

SECTION_CATEGORY_RULES = (
    ("core", 100, re.compile(r"角色扮演|core (?:rules|personality)|核心(?:规则|性格)|最高优先" , re.I)),
    ("dialogue", 98, re.compile(r"对话纪律|对话规则|dialogue|conversation", re.I)),
    ("expression", 96, re.compile(r"表达|说话|口头禅|称谓|signature|expression|voice", re.I)),
    ("boundaries", 94, re.compile(r"边界|禁忌|反模式|诚实|限制|boundar|limit|reject", re.I)),
    ("turns", 90, re.compile(r"回合|场景|response|turn", re.I)),
    ("examples", 72, re.compile(r"示例|example|招牌点单", re.I)),
    ("identity", 68, re.compile(r"身份|关系背景|identity|relationship context", re.I)),
    ("mental_models", 62, re.compile(r"模型|思考|mental model", re.I)),
    ("heuristics", 60, re.compile(r"启发式|判断|优先级|heuristic|quick rule", re.I)),
    ("references", 0, re.compile(r"reference|参考|资料|来源|按需加载", re.I)),
)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON 文件格式错误 {path.name}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"JSON 文件根节点必须是对象: {path.name}")
    return value


def _read_skill_frontmatter(markdown: str) -> dict[str, Any]:
    match = SKILL_FRONTMATTER_RE.match(markdown)
    if not match:
        return {}
    try:
        value = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"SKILL.md frontmatter 格式错误: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError("SKILL.md frontmatter 必须是对象")
    return value


def _clean_source_behavior(markdown: str) -> str:
    """Preserve upstream behavior text while removing packaging-only syntax."""
    value = SKILL_FRONTMATTER_RE.sub("", markdown, count=1)
    value = re.sub(r"<br\s*/?>", "\n", value, flags=re.I)
    value = value.replace("\x00", "")
    value = re.sub(r"[ \t]+\n", "\n", value)
    value = re.sub(r"\n{4,}", "\n\n\n", value)
    return value.strip()[:100_000]


def _section_category(title: str) -> tuple[str, int]:
    normalized = re.sub(r"[`*_]", "", str(title or "")).strip()
    for category, priority, pattern in SECTION_CATEGORY_RULES:
        if pattern.search(normalized):
            return category, priority
    return "other", 40


def _source_section_index(
    sections, source_path: str = "SKILL.md", order_offset: int = 0
) -> list[dict[str, Any]]:
    result = []
    for section in sections:
        if section.title == "document" and not section.content.strip():
            continue
        source_order = order_offset + len(result)
        category, priority = _section_category(section.title)
        result.append(
            {
                "id": f"source-section-{source_order + 1:03d}",
                "title": section.title,
                "level": section.level,
                "parent_titles": list(section.parent_titles),
                "content": section.content.strip(),
                "category": category,
                "runtime_priority": priority,
                "source_order": source_order,
                "source_path": source_path,
            }
        )
    return result


def _conversion_coverage(
    source_behavior: str,
    source_sections: list[dict[str, Any]],
    behavior_references: list[str] | None = None,
) -> dict[str, Any]:
    structured_categories = {
        "core", "dialogue", "expression", "boundaries", "examples",
        "identity", "mental_models", "heuristics",
    }
    structured = [item["title"] for item in source_sections if item["category"] in structured_categories]
    unmapped = [item["title"] for item in source_sections if item["category"] == "other"]
    references = [item["title"] for item in source_sections if item["category"] == "references"]
    return {
        "mode": "lossless-hybrid",
        "source_chars": len(source_behavior),
        "section_count": len(source_sections),
        "preserved_section_count": len(source_sections),
        "structured_section_count": len(structured),
        "structured_sections": structured,
        "unmapped_sections": unmapped,
        "reference_sections": references,
        "behavior_reference_files": list(behavior_references or []),
        "dropped_sections": [],
        "warnings": (["部分章节仅原文保留，未生成结构化索引"] if unmapped else []),
    }


def _skill_display_name(markdown: str, frontmatter: dict[str, Any]) -> str:
    headings = re.findall(r"^#\s+(.+?)\s*$", markdown, re.M)
    title = next((item for item in headings if item.strip().lower() != "skill.md"), "")
    title = re.sub(r"[`*_]", "", title).strip()
    title = re.sub(r"(?i)(?:[.·\s_-]*(?:persona\s*)?skill|\s+perspective|视角)+$", "", title).strip()
    if title:
        return title[:100]
    description = str(frontmatter.get("description") or "").strip()
    if description:
        first = re.split(r"[：:。\n]", description, maxsplit=1)[0].strip()
        first = re.sub(r"视角$", "", first).strip()
        if first:
            return first[:100]
    return str(frontmatter.get("name") or "Imported Persona")[:100]


def _is_persona_skill(markdown: str, frontmatter: dict[str, Any]) -> bool:
    sections = parse_sections(markdown)
    normalized_titles = [section.normalized_title for section in sections]
    marker_hits = sum(
        1
        for marker in PERSONA_SECTION_MARKERS
        if any(marker.lower() in title for title in normalized_titles)
    )
    description = str(frontmatter.get("description") or "").lower()
    roleplay_signal = bool(re.search(r"(?:第一人称|角色扮演|模拟.{0,12}(?:语气|风格|思维)|像.{0,12}一样|persona|roleplay)", markdown, re.I))
    perspective_signal = "perspective" in str(frontmatter.get("name") or "").lower() or "视角" in description
    return marker_hits >= 2 and (roleplay_signal or perspective_signal or marker_hits >= 4)


def _skill_meta(markdown: str, frontmatter: dict[str, Any]) -> tuple[dict[str, Any], str]:
    display_name = _skill_display_name(markdown, frontmatter)
    slug = str(frontmatter.get("name") or "").strip()
    description = str(frontmatter.get("description") or "").strip()
    public_figure = bool(
        "perspective" in slug.lower()
        or "视角" in description
        or re.search(r"(?:公开表达|公开内容|公众人物|主播|创作者|偶像)", description)
    )
    fictional = bool(re.search(r"(?:虚构人物|小说角色|游戏角色|虚拟角色)", description))
    family = "celebrity" if public_figure else "relationship" if fictional else "colleague"
    return (
        {
            "name": display_name,
            "display_name": display_name,
            "slug": slug,
            "version": str(frontmatter.get("version") or "v1"),
            "persona_mode": "public-figure" if public_figure else "fictional" if fictional else "colleague",
            "profile": {"summary": description},
            "source_context": {
                "is_real_person": not fictional,
                "is_public_figure": public_figure,
                "is_fictional": fictional,
            },
        },
        family,
    )


def _clean_lines(values: list[str], limit: int = 30) -> list[str]:
    result = []
    seen = set()
    for value in values:
        value = re.sub(r"\s+", " ", value).strip(" -\t")
        if not value or value.startswith("{") or value in seen:
            continue
        seen.add(value)
        result.append(value)
        if len(result) >= limit:
            break
    return result


def _section_values(sections, aliases: tuple[str, ...], include_prose: bool = True) -> list[str]:
    section = find_section(sections, *aliases)
    if not section:
        return []
    values = bullets(section.content)
    paragraph = prose(section.content) if include_prose else ""
    if paragraph:
        values.insert(0, paragraph)
    return _clean_lines(values)


def _all_section_values(sections, aliases: tuple[str, ...], include_prose: bool = True) -> list[str]:
    values = []
    for section in find_sections(sections, *aliases):
        if include_prose:
            paragraph = prose(section.content)
            if paragraph:
                values.append(paragraph)
        values.extend(bullets(section.content))
    return _clean_lines(values)


def _first_text(sections, *aliases: str) -> str:
    values = _section_values(sections, tuple(aliases))
    return values[0] if values else ""


def _identity_summary(meta: dict, sections) -> str:
    identity = _first_text(sections, "Identity", "Relationship Context", "身份", "关系背景")
    if identity:
        return identity
    profile = meta.get("profile")
    if isinstance(profile, str):
        return profile.strip()
    if isinstance(profile, dict):
        return "，".join(str(value).strip() for value in profile.values() if value)
    return str(meta.get("summary") or "").strip()


def _extract_examples(markdown: str) -> list[dict[str, Any]]:
    examples = []
    pending_user = ""
    scene = "示例表达"
    for raw_line in markdown.splitlines():
        line = raw_line.strip().lstrip("> ")
        if not line:
            continue
        heading_match = re.match(r"^#{2,6}\s+(.+?)\s*$", line)
        if heading_match:
            scene = re.sub(r"[`*_]", "", heading_match.group(1)).strip()[:100]
            continue
        line = re.sub(r"<br\s*/?>", "", line, flags=re.I).strip()
        # Standard Skills commonly bold the speaker label: **用户**： / **我**：
        line = re.sub(r"^\*\*\s*([^*]+?)\s*\*\*\s*([:：])", r"\1\2", line)
        scene_match = re.match(r"(?:when|场景|情境)\s*[:：]\s*(.+)", line, re.I)
        if scene_match:
            scene = scene_match.group(1).strip()
            continue
        user_match = re.match(r"(?:user|用户)\s*[:：]\s*(.+)", line, re.I)
        if user_match:
            pending_user = user_match.group(1).strip()
            continue
        assistant_match = re.match(r"(?:assistant|角色|回复|你|我)\s*[:：]\s*(.+)", line, re.I)
        if assistant_match and pending_user:
            examples.append(
                {
                    "id": f"example-{len(examples) + 1:03d}",
                    "scene": scene,
                    "user": pending_user,
                    "assistant": assistant_match.group(1).strip(),
                    "tags": [],
                }
            )
            pending_user = ""
        if len(examples) >= 20:
            break
    return examples


def _merge_examples(documents: list[tuple[str, str]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for source_path, markdown in documents:
        for item in _extract_examples(markdown):
            key = (str(item.get("user") or ""), str(item.get("assistant") or ""))
            if not all(key) or key in seen:
                continue
            seen.add(key)
            result.append(
                {
                    **item,
                    "id": f"example-{len(result) + 1:03d}",
                    "source_path": source_path,
                }
            )
            if len(result) >= 50:
                return result
    return result


def _extract_signature_utterances(markdown: str, examples: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Extract explicit signature routing without reducing semantic rules to keywords."""
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw_line in markdown.splitlines():
        line = re.sub(r"<br\s*/?>", "", raw_line).strip().lstrip("-*+ ")
        if "招牌" not in line and "signature" not in line.lower():
            continue
        aliases = []
        for candidate in re.findall(r"`([^`]{1,100})`", line):
            token = re.match(r"([A-Za-z][A-Za-z0-9._-]{1,40})", candidate.strip())
            if token and token.group(1).lower() not in {item.lower() for item in aliases}:
                aliases.append(token.group(1))
        if not aliases:
            latin = re.search(r"\b([A-Za-z][A-Za-z0-9._-]{2,40})\b", line)
            if latin:
                aliases.append(latin.group(1))
        if not aliases:
            continue
        canonical = aliases[0]
        signature_id = re.sub(r"[^a-z0-9._-]+", "-", canonical.lower()).strip("-")
        if not signature_id or signature_id in seen:
            continue
        seen.add(signature_id)
        display_text = canonical
        decorated_candidates = [
            candidate.strip()
            for candidate in re.findall(r"`([^`]{1,100})`", line)
            if canonical.lower() in candidate.lower()
        ]
        decorated = max(decorated_candidates, key=len, default="")
        if decorated:
            display_text = decorated
        positive_examples = []
        for item in examples:
            if canonical.lower() in str(item.get("assistant") or "").lower():
                positive_examples.append(str(item.get("user") or "")[:180])
                if len(positive_examples) >= 8:
                    break
        result.append(
            {
                "id": signature_id[:64],
                "display_text": display_text[:160],
                "explicit_aliases": aliases[:8],
                "semantic_rule": line[:1000],
                "positive_examples": positive_examples,
                "ambiguity_policy": "上下文不能唯一确定时不触发",
                "assets": {},
                "style_map": {
                    "neutral": "classic", "restrained": "classic",
                    "happy": "playful", "excited": "playful",
                    "warm": "soft", "soft": "soft",
                },
                "fallback": "tts",
            }
        )
    return result[:12]


def _extract_mental_models(sections) -> list[dict[str, str]]:
    result = []
    containers = find_sections(sections, "Mental Models", "Core Mental Models", "心智模型", "核心心智模型")
    container_titles = {section.title for section in containers}
    candidates = list(find_sections(sections, "Model", "模型"))
    candidates.extend(
        section
        for section in sections
        if any(parent in container_titles for parent in section.parent_titles)
    )
    seen = set()
    for section in candidates:
        title = re.sub(r"^(?:(?:model|模型)\s*[:：]\s*|\d+[.、]\s*)", "", section.title, flags=re.I).strip()
        if not title or title.lower() in {"mental models", "心智模型"}:
            continue
        description = prose(section.content) or "；".join(bullets(section.content))
        if title in seen or not description:
            continue
        seen.add(title)
        result.append({"name": title, "description": description})
    return result[:7]


def _normalize_source(
    meta: dict,
    manifest: dict,
    artifact_sha256: str,
    inferred_family: str | None = None,
) -> dict[str, Any]:
    source_context = meta.get("source_context") if isinstance(meta.get("source_context"), dict) else {}
    lifecycle = meta.get("lifecycle") if isinstance(meta.get("lifecycle"), dict) else {}
    generation = meta.get("generation") if isinstance(meta.get("generation"), dict) else {}
    persona_mode = str(meta.get("persona_mode") or source_context.get("persona_mode") or "").strip().lower()
    mode_family = {
        "public-figure": "celebrity",
        "public_figure": "celebrity",
        "celebrity": "celebrity",
        "relationship": "relationship",
        "companion": "relationship",
        "self-owned": "relationship",
        "self_owned": "relationship",
        "fictional": "relationship",
        "colleague": "colleague",
    }.get(persona_mode)
    family_candidates = (
        manifest.get("character"),
        meta.get("character"),
        generation.get("character"),
        mode_family,
        inferred_family,
    )
    family = next(
        (
            str(candidate).strip().lower()
            for candidate in family_candidates
            if str(candidate or "").strip().lower() in {"relationship", "celebrity", "colleague", "manual"}
        ),
        "colleague",
    )
    is_fictional = bool(source_context.get("is_fictional", persona_mode == "fictional"))
    is_public_figure = bool(
        source_context.get(
            "is_public_figure",
            persona_mode in {"public-figure", "public_figure", "celebrity"} or family == "celebrity",
        )
    )
    is_real_person = bool(
        source_context.get(
            "is_real_person",
            not is_fictional and (is_public_figure or family in {"relationship", "celebrity", "colleague"}),
        )
    )
    return {
        "adapter": "dot-skill",
        "upstream_schema_version": str(meta.get("schema_version") or manifest.get("install", {}).get("min_schema_version") or ""),
        "family": family,
        "upstream_id": manifest.get("id") or meta.get("id") or meta.get("slug") or "",
        "upstream_version": lifecycle.get("version") or meta.get("version") or "v1",
        "source_url": meta.get("source_url") or "",
        "source_commit": meta.get("source_commit") or "",
        "artifact_sha256": artifact_sha256,
        "is_real_person": is_real_person,
        "is_public_figure": is_public_figure,
        "is_fictional": is_fictional,
    }


def _normalize_persona(
    meta: dict,
    manifest: dict,
    markdown: str,
    artifact_sha256: str,
    inferred_family: str | None = None,
    behavior_references: dict[str, str] | None = None,
) -> PersonaSpec:
    sections = parse_sections(markdown)
    behavior_documents = [("SKILL.md", markdown)] + list(
        (behavior_references or {}).items()
    )
    cleaned_documents = [
        (source_path, _clean_source_behavior(content))
        for source_path, content in behavior_documents
    ]
    source_behavior = "\n\n".join(
        (
            content
            if index == 0
            else f"# 行为参考：{source_path}\n\n{content}"
        )
        for index, (source_path, content) in enumerate(cleaned_documents)
        if content
    )[:100_000].strip()
    # The source index is behavior-only. Frontmatter remains available through
    # normalized source metadata and must not consume runtime prompt budget.
    source_sections: list[dict[str, Any]] = []
    for source_path, content in cleaned_documents:
        indexed = _source_section_index(
            parse_sections(content), source_path, len(source_sections)
        )
        source_sections.extend(indexed)
    source_sections = source_sections[:256]
    source = _normalize_source(meta, manifest, artifact_sha256, inferred_family)
    if behavior_references:
        source["behavior_reference_sha256"] = content_hash(
            {
                path: content.encode("utf-8")
                for path, content in behavior_references.items()
            }
        )
    family = source["family"]
    display_name = str(manifest.get("display_name") or meta.get("display_name") or meta.get("name") or "Imported Persona")
    upstream_id = (
        source["upstream_id"]
        or meta.get("slug")
        or re.sub(r"[^a-zA-Z0-9._-]+", "_", display_name).strip("_")
        or artifact_sha256[:12]
    )
    persona_slug = re.sub(r"[^a-zA-Z0-9._-]+", "_", str(upstream_id).split(".")[-1]).strip("._-")
    persona_slug = persona_slug or artifact_sha256[:12]
    persona_id = str(meta.get("cyber_persona_id") or f"persona.{family}.{persona_slug}")

    core_values = _section_values(
        sections,
        (
            "Core Relational Rules",
            "Core Thinking Rules",
            "Core Rules",
            "Core Personality",
            "核心关系规则",
            "核心思考规则",
            "核心规则",
            "核心性格",
            "角色扮演规则",
        ),
        include_prose=False,
    )
    mental_models = _extract_mental_models(sections)
    if not core_values:
        core_values = [f"{item['name']}：{item['description']}" for item in mental_models]
    core_rules = [
        {"id": f"core-{index:03d}", "rule": value, "priority": 100 - index, "confidence": 0.8, "evidence_refs": []}
        for index, value in enumerate(core_values, 1)
    ]

    favorite_patterns = _all_section_values(
        sections,
        (
            "Signature phrases",
            "Signature Moves",
            "口头禅",
            "口头禅与高频词",
            "标志性表达",
            "称谓",
            "标志性开头",
            "标志性结尾",
        ),
    )
    forbidden_patterns = _all_section_values(
        sections,
        ("Forbidden vocabulary", "Rejects", "禁用词", "拒绝模式", "禁忌", "绝对反对", "反模式"),
    )
    expression = {
        "rhythm": _first_text(sections, "Rhythm", "节奏", "说话方式"),
        "warmth": _first_text(sections, "Warmth level", "温度", "亲和程度"),
        "directness": _first_text(sections, "Distance style", "Directness", "距离感", "直接程度"),
        "humor_style": _first_text(sections, "Humor style", "幽默方式"),
        "average_sentence_length": _first_text(sections, "Average sentence length", "平均句长"),
        "question_density": _first_text(sections, "Question density", "提问密度"),
        "favorite_patterns": favorite_patterns,
        "forbidden_patterns": forbidden_patterns + ["客服式总结", "机械重复用户原话"],
    }

    emotional_logic = {
        "opens_up_when": _section_values(sections, ("Opens up when", "愿意敞开时", "靠近触发")),
        "withdraws_when": _section_values(sections, ("Pulls away when", "Withdraws when", "退缩时", "疏远触发")),
        "defensive_when": _section_values(sections, ("Defends themselves by", "Becomes defensive when", "防御方式", "防御触发")),
        "affectionate_when": _section_values(sections, ("Shows affection when", "表达亲近时", "亲近触发")),
        "care_patterns": _section_values(sections, ("Shows care by", "Care pattern", "关心方式")),
    }
    conflict_repair = {
        "conflict_style": _first_text(sections, "Conflict style", "冲突方式"),
        "silence_pattern": _first_text(sections, "Silence pattern", "沉默模式"),
        "repair_pattern": _first_text(sections, "Repair pattern", "修复模式"),
        "accepted_apologies": _section_values(sections, ("Accepted apologies", "接受的道歉")),
        "boundaries": _section_values(sections, ("Boundaries", "Honest Boundaries", "边界", "诚实边界")),
    }
    decision_heuristics = _all_section_values(
        sections,
        (
            "Quick Rules",
            "Decision Heuristics",
            "快速规则",
            "决策启发",
            "你的优先级",
            "你会推进的情况",
            "你会拖或推掉的情况",
            "你如何说不",
        ),
    )

    correction_values = _section_values(
        sections,
        ("Correction Log", "Correction 记录", "Correction 层", "纠正记录"),
        include_prose=False,
    )
    for index, value in enumerate(correction_values, 1):
        core_rules.insert(
            0,
            {
                "id": f"correction-{index:03d}",
                "rule": value,
                "priority": 200 - index,
                "confidence": 1.0,
                "evidence_refs": ["persona.md#correction"],
            },
        )

    limitations = _section_values(sections, ("Honest Boundaries", "Limits", "能力边界", "诚实边界"))
    if family == "celebrity":
        limitations.extend(["只依据人物的公开表达塑造表达与思考特征", "不推断相关人物的私人恋爱行为"])
    limitations.extend(["不代表相关真人的真实观点", "不虚构与用户未发生过的共同经历"])
    limitations = _clean_lines(limitations)

    recommended_relationship_mode = {
        "relationship": "romance",
        "celebrity": "friend",
        "colleague": "friend",
    }.get(family, "friend")
    # A Persona describes identity and expression. The relationship range belongs to
    # the agent binding and is selected in role configuration. All imported personas
    # therefore expose the complete state-machine vocabulary while retaining a safe,
    # backwards-compatible recommendation derived from the source material.
    allowed_stages = ["familiar", "friend", "ambiguous", "lover", "intimate"]

    examples = _merge_examples(behavior_documents)
    spec = PersonaSpec(
        id=persona_id,
        display_name=display_name,
        source=source,
        identity={
            "summary": _identity_summary(meta, sections),
            "public_role": str((meta.get("profile") or {}).get("public_role", "")) if isinstance(meta.get("profile"), dict) else "",
            "fictionalization_notice": "这是基于人物设定塑造的 AI 角色，不代表相关真人的真实观点。",
        },
        core_rules=core_rules,
        expression=expression,
        emotional_logic=emotional_logic,
        conflict_repair=conflict_repair,
        mental_models=mental_models,
        decision_heuristics=decision_heuristics,
        relationship_policy={
            "initial_stage": "familiar",
            "allowed_stages": allowed_stages,
            "recommended_mode": recommended_relationship_mode,
            "stage_transition_rules": [],
            "intimacy_boundaries": conflict_repair["boundaries"],
            "source": "agent-binding",
        },
        examples=examples,
        limitations=limitations,
        source_behavior=source_behavior,
        source_sections=source_sections,
        signature_utterances=_extract_signature_utterances(markdown, examples),
        conversion_coverage=_conversion_coverage(
            source_behavior, source_sections, list(behavior_references or {})
        ),
        quality={"status": "needs_review", "thin_sections": [], "contradictions": [], "compiler_warnings": []},
    )
    thin = []
    for name, value in (("core_rules", spec.core_rules), ("expression", favorite_patterns or expression["rhythm"]), ("emotional_logic", any(emotional_logic.values()))):
        if not value:
            thin.append(name)
    spec.quality["thin_sections"] = thin
    return spec


class DotSkillAdapter(PersonaImportAdapter):
    def detect(self, source_path: str | Path) -> bool:
        try:
            with materialize_source(source_path) as root:
                artifacts = locate_artifacts(root)
                if "persona.md" in artifacts and ("manifest.json" in artifacts or "meta.json" in artifacts):
                    return True
                if "SKILL.md" not in artifacts:
                    return False
                markdown = artifacts["SKILL.md"].read_text(encoding="utf-8")
                return _is_persona_skill(markdown, _read_skill_frontmatter(markdown))
        except (OSError, ValueError):
            return False

    def inspect(self, source_path: str | Path) -> ImportInspection:
        with materialize_source(source_path) as root:
            artifacts = locate_artifacts(root)
            raw_files = {name: path.read_bytes() for name, path in artifacts.items()}
            digest = content_hash(raw_files)
            legacy_detected = "persona.md" in artifacts and ("manifest.json" in artifacts or "meta.json" in artifacts)
            skill_frontmatter = {}
            skill_detected = False
            if "SKILL.md" in artifacts:
                skill_markdown = artifacts["SKILL.md"].read_text(encoding="utf-8")
                skill_frontmatter = _read_skill_frontmatter(skill_markdown)
                skill_detected = _is_persona_skill(skill_markdown, skill_frontmatter)
                behavior_references = locate_behavior_references(
                    root, artifacts["SKILL.md"], skill_markdown
                )
            else:
                behavior_references = {}
            detected = legacy_detected or skill_detected
            metadata = {}
            warnings = []
            if "manifest.json" in artifacts:
                metadata["manifest"] = _read_json(artifacts["manifest.json"])
            else:
                warnings.append("缺少 manifest.json，将使用兼容导入")
            if "meta.json" in artifacts:
                metadata["meta"] = _read_json(artifacts["meta.json"])
            else:
                warnings.append("缺少 meta.json，来源信息可能不完整")
            if skill_detected and not legacy_detected:
                metadata["skillFrontmatter"] = skill_frontmatter
                warnings.append("检测到标准 SKILL.md 人物，将通过兼容层转换为 PersonaSpec")
            metadata["files"] = sorted((*artifacts, *behavior_references))
            if behavior_references:
                warnings.append(
                    f"已加载 {len(behavior_references)} 份对话/风格参考文件"
                )
            return ImportInspection(
                "dot-skill", detected, str(source_path), metadata, warnings,
                artifact_sha256=digest,
            )

    def convert(self, source_path: str | Path) -> ImportResult:
        with materialize_source(source_path) as root:
            artifacts = locate_artifacts(root)
            legacy_layout = "persona.md" in artifacts and ("manifest.json" in artifacts or "meta.json" in artifacts)
            skill_layout = "SKILL.md" in artifacts
            if not legacy_layout and not skill_layout:
                raise ValueError("dot-skill 来源需要 persona.md + 元数据，或人物型 SKILL.md")
            raw_files = {name: path.read_bytes() for name, path in artifacts.items()}
            digest = content_hash(raw_files)
            manifest = _read_json(artifacts["manifest.json"]) if "manifest.json" in artifacts else {}
            meta = _read_json(artifacts["meta.json"]) if "meta.json" in artifacts else {}
            inferred_family = None
            if legacy_layout:
                markdown = raw_files["persona.md"].decode("utf-8")
                behavior_references = {}
            else:
                markdown = raw_files["SKILL.md"].decode("utf-8")
                frontmatter = _read_skill_frontmatter(markdown)
                if not _is_persona_skill(markdown, frontmatter):
                    raise ValueError("SKILL.md 是工具型 Skill，不包含可转换的人物结构")
                meta, inferred_family = _skill_meta(markdown, frontmatter)
                reference_paths = locate_behavior_references(
                    root, artifacts["SKILL.md"], markdown
                )
                behavior_references = {
                    path: reference.read_text(encoding="utf-8")
                    for path, reference in reference_paths.items()
                }
            upstream_schema = str(meta.get("schema_version") or manifest.get("install", {}).get("min_schema_version") or "")
            if upstream_schema not in SUPPORTED_UPSTREAM_SCHEMAS:
                raise ValueError(f"不支持的 dot-skill schema: {upstream_schema}")
            if inferred_family is None:
                parent_family = root.parent.name.lower()
                inferred_family = parent_family if parent_family in {"colleague", "relationship", "celebrity"} else None
            spec = _normalize_persona(
                meta,
                manifest,
                markdown,
                digest,
                inferred_family,
                behavior_references,
            )
            report = PersonaSpecValidator().validate(spec)
            spec.quality["status"] = "valid" if report.valid and not report.issues else "needs_review"
            spec.quality["compiler_warnings"] = [issue.message for issue in report.issues]
            return ImportResult(
                spec,
                report,
                sorted((*raw_files, *behavior_references)),
                digest,
            )


def _registry(path: str) -> FilesystemPersonaRegistry:
    return FilesystemPersonaRegistry(path)


def _print_json(value: Any):
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="导入和管理 dot-skill Persona")
    parser.add_argument("--registry", default=DEFAULT_REGISTRY, help="Persona 文件仓库")
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_parser = subparsers.add_parser("inspect")
    inspect_parser.add_argument("--source", required=True)
    inspect_parser.add_argument("--registry", dest="command_registry")

    import_parser = subparsers.add_parser("import")
    import_parser.add_argument("--source", required=True)
    import_parser.add_argument("--agent-id")
    import_parser.add_argument("--version")
    import_parser.add_argument("--status", choices=["draft", "published"], default="draft")
    import_parser.add_argument("--registry", dest="command_registry")

    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("--persona-id", required=True)
    validate_parser.add_argument("--version")
    validate_parser.add_argument("--registry", dest="command_registry")

    diff_parser = subparsers.add_parser("diff")
    diff_parser.add_argument("--persona-id", required=True)
    diff_parser.add_argument("--from", dest="left", required=True)
    diff_parser.add_argument("--to", dest="right", required=True)
    diff_parser.add_argument("--registry", dest="command_registry")

    publish_parser = subparsers.add_parser("publish")
    publish_parser.add_argument("--persona-id", required=True)
    publish_parser.add_argument("--version", required=True)
    publish_parser.add_argument("--registry", dest="command_registry")

    rollback_parser = subparsers.add_parser("rollback")
    rollback_parser.add_argument("--persona-id", required=True)
    rollback_parser.add_argument("--version", required=True)
    rollback_parser.add_argument("--registry", dest="command_registry")

    list_parser = subparsers.add_parser("list")
    list_parser.add_argument("--registry", dest="command_registry")

    archive_parser = subparsers.add_parser("archive")
    archive_parser.add_argument("--persona-id", required=True)
    archive_parser.add_argument("--version", required=True)
    archive_parser.add_argument("--registry", dest="command_registry")

    migrate_parser = subparsers.add_parser("migrate-filesystem-to-manager-api")
    migrate_parser.add_argument("--manager-url", required=True, help="manager-api 根地址，例如 http://127.0.0.1:8002/xiaozhi")
    migrate_parser.add_argument("--token", required=True, help="智控台 Bearer Token")
    migrate_parser.add_argument("--persona-id", help="只迁移指定 Persona；默认迁移全部")
    migrate_parser.add_argument("--dry-run", action="store_true", help="只校验和生成报告，不上传")
    migrate_parser.add_argument("--registry", dest="command_registry")
    return parser


def _post_migration(manager_url: str, token: str, payload: dict[str, Any]) -> dict[str, Any]:
    endpoint = manager_url.rstrip("/") + "/persona/migrate/filesystem"
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=utf-8"},
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            value = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        message = error.read().decode("utf-8", errors="replace")[:1000]
        raise RuntimeError(f"manager-api 迁移失败 HTTP {error.code}: {message}") from error
    if not isinstance(value, dict) or value.get("code") != 0:
        raise RuntimeError(f"manager-api 迁移失败: {value.get('msg') if isinstance(value, dict) else '响应不合法'}")
    return value.get("data") or {}


def _migrate_filesystem(args, registry: FilesystemPersonaRegistry) -> int:
    report: dict[str, Any] = {"dry_run": args.dry_run, "migrated": [], "failed": []}
    personas = registry.personas()
    if args.persona_id:
        personas = [item for item in personas if item["persona_id"] == args.persona_id]
        if not personas:
            raise FileNotFoundError(f"本地 Persona 不存在: {args.persona_id}")
    for item in personas:
        persona_id = item["persona_id"]
        for version in item["versions"]:
            try:
                spec, prompt, metadata = registry.load(persona_id, version)
                validation_path = registry._version_dir(persona_id, version) / "validation.json"
                validation = _read_json(validation_path)
                payload = {
                    "personaId": persona_id,
                    "version": version,
                    "artifactHash": metadata["artifact_sha256"],
                    "canonicalSpec": spec.to_dict(),
                    "runtimePrompt": prompt,
                    "validationReport": validation,
                    "sourceStatus": metadata.get("status", "draft"),
                }
                result = {"personaId": persona_id, "version": version, "status": "validated"}
                if not args.dry_run:
                    result = _post_migration(args.manager_url, args.token, payload)
                report["migrated"].append(result)
            except Exception as error:
                report["failed"].append({"personaId": persona_id, "version": version, "error": str(error)[:500]})
    report["summary"] = {"success": len(report["migrated"]), "failed": len(report["failed"])}
    _print_json(report)
    return 0 if not report["failed"] else 2


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    adapter = DotSkillAdapter()
    registry = _registry(args.command_registry or args.registry)
    if args.command == "inspect":
        _print_json(adapter.inspect(args.source).__dict__)
        return 0
    if args.command == "import":
        result = adapter.convert(args.source)
        result.report = PersonaSpecValidator().validate(result.spec)
        prompt = PersonaCompiler().compile(result.spec)
        version = args.version or str(result.spec.source.get("upstream_version") or "v1")
        record = registry.save(result.spec, prompt, result.report, result.artifact_sha256, version, args.status)
        _print_json(
            {
                "persona_id": record.persona_id,
                "version": record.version,
                "status": record.status,
                "valid": result.report.valid,
                "issues": result.report.to_dict()["issues"],
                "path": str(record.path),
                "agent_id": args.agent_id,
            }
        )
        return 0 if result.report.valid else 2
    if args.command == "validate":
        spec, _, metadata = registry.load(args.persona_id, args.version)
        report = PersonaSpecValidator().validate(spec)
        _print_json({"metadata": metadata, "validation": report.to_dict()})
        return 0 if report.valid else 2
    if args.command == "diff":
        print(registry.diff(args.persona_id, args.left, args.right), end="")
        return 0
    if args.command == "publish":
        registry.publish(args.persona_id, args.version)
        _print_json(registry.get_published(args.persona_id))
        return 0
    if args.command == "rollback":
        registry.rollback(args.persona_id, args.version)
        _print_json(registry.get_published(args.persona_id))
        return 0
    if args.command == "list":
        _print_json(registry.personas())
        return 0
    if args.command == "archive":
        registry.archive(args.persona_id, args.version)
        _print_json({"persona_id": args.persona_id, "version": args.version, "status": "archived"})
        return 0
    if args.command == "migrate-filesystem-to-manager-api":
        return _migrate_filesystem(args, registry)
    return 1


if __name__ == "__main__":
    sys.exit(main())
