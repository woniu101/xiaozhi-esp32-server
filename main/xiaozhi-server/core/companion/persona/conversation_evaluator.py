from __future__ import annotations

from difflib import SequenceMatcher
import re
from typing import Any

from core.companion.models import PersonaSpec


SUITE_VERSION = "companion-conversation-quality/1"
GENERIC_ASSISTANT_PHRASES = (
    "作为ai",
    "作为一个ai",
    "我理解你的感受",
    "还有什么可以帮你",
    "请问还有什么",
    "如果你有任何问题",
)


def _normalized(value: Any) -> str:
    return re.sub(r"[^\w\u4e00-\u9fff]+", "", str(value or "").lower())


def _sample_expected(sample: dict[str, Any]) -> dict[str, Any]:
    value = sample.get("expected")
    return value if isinstance(value, dict) else {}


def evaluate_conversation_samples(
    spec: PersonaSpec,
    samples: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    """Evaluate recorded/generated turns without persisting raw dialogue.

    Samples are supplied by a replay runner or the admin API. This evaluator is
    intentionally deterministic so model/Prompt changes can be compared over time.
    It complements, rather than replaces, human review and an optional Judge LLM.
    """
    if not samples:
        return {
            "suiteVersion": SUITE_VERSION,
            "status": "not_run",
            "score": None,
            "sampleCount": 0,
            "metrics": {},
            "findings": ["尚未提供真实对话样本"],
            "turns": [],
        }

    safe_samples = [item for item in samples[:500] if isinstance(item, dict)]
    if not safe_samples:
        return {
            "suiteVersion": SUITE_VERSION,
            "status": "not_run",
            "score": None,
            "sampleCount": 0,
            "metrics": {},
            "findings": ["没有可评估的有效对话样本"],
            "turns": [],
        }
    findings: list[str] = []
    turn_reports: list[dict[str, Any]] = []
    generic_count = 0
    empty_count = 0
    long_count = 0
    question_overuse_count = 0
    expectation_failure_count = 0
    repeated_count = 0
    previous_reply = ""

    for index, sample in enumerate(safe_samples, 1):
        assistant = str(sample.get("assistant") or "").strip()[:10_000]
        expected = _sample_expected(sample)
        normalized = _normalized(assistant)
        issues: list[str] = []

        if not assistant:
            issues.append("empty_reply")
            empty_count += 1
        if any(phrase in normalized for phrase in GENERIC_ASSISTANT_PHRASES):
            issues.append("generic_assistant_phrase")
            generic_count += 1
        max_chars = max(20, min(2000, int(expected.get("maxChars") or 260)))
        if len(assistant) > max_chars:
            issues.append("too_long")
            long_count += 1
        max_questions = max(0, min(3, int(expected.get("maxQuestions", 1))))
        if len(re.findall(r"[?？]", assistant)) > max_questions:
            issues.append("question_overuse")
            question_overuse_count += 1

        must_include = [str(item) for item in expected.get("mustInclude", []) if str(item)]
        forbidden = [str(item) for item in expected.get("forbidden", []) if str(item)]
        if must_include and not all(item in assistant for item in must_include):
            issues.append("missing_expected_content")
            expectation_failure_count += 1
        if forbidden and any(item in assistant for item in forbidden):
            issues.append("forbidden_content")
            expectation_failure_count += 1

        similarity = 0.0
        if previous_reply and normalized:
            similarity = SequenceMatcher(None, previous_reply, normalized).ratio()
            if min(len(previous_reply), len(normalized)) >= 12 and similarity >= 0.78:
                issues.append("repeated_reply_pattern")
                repeated_count += 1
        if normalized:
            previous_reply = normalized

        turn_reports.append(
            {
                "index": index,
                "scene": str(sample.get("scene") or "")[:100],
                "issues": issues,
                "replyChars": len(assistant),
                "similarityToPrevious": round(similarity, 3),
            }
        )

    total = max(1, len(safe_samples))
    penalty = (
        empty_count * 25
        + generic_count * 12
        + expectation_failure_count * 15
        + repeated_count * 10
        + long_count * 5
        + question_overuse_count * 5
    ) / total
    score = round(max(0.0, 100.0 - penalty), 2)
    if empty_count:
        findings.append(f"{empty_count} 轮没有生成有效回复")
    if generic_count:
        findings.append(f"{generic_count} 轮出现通用 AI 助手套话")
    if repeated_count:
        findings.append(f"{repeated_count} 轮与上一轮表达高度重复")
    if expectation_failure_count:
        findings.append(f"{expectation_failure_count} 项场景预期未满足")
    if question_overuse_count:
        findings.append(f"{question_overuse_count} 轮提问数量超过场景上限")
    if not findings:
        findings.append("样本未发现阻断性人物质量问题")

    generic_rate = generic_count / total
    repeated_rate = repeated_count / total
    blocking_pattern = generic_rate >= 0.4 or repeated_rate >= 0.5
    return {
        "suiteVersion": SUITE_VERSION,
        "personaId": spec.id,
        "status": "passed" if score >= 80 and empty_count == 0 and not blocking_pattern else "failed",
        "score": score,
        "sampleCount": len(safe_samples),
        "metrics": {
            "emptyReplyRate": round(empty_count / total, 4),
            "genericPhraseRate": round(generic_rate, 4),
            "repeatedReplyRate": round(repeated_rate, 4),
            "longReplyRate": round(long_count / total, 4),
            "questionOveruseRate": round(question_overuse_count / total, 4),
            "expectationFailureRate": round(expectation_failure_count / total, 4),
        },
        "findings": findings,
        "turns": turn_reports,
    }
