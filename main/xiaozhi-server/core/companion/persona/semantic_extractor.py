from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urlparse

import requests

from core.companion.models import PersonaSpec


class PersonaSemanticExtractor:
    """Optional evidence-bound LLM enrichment for non-standard Skill layouts.

    The deterministic importer and the preserved upstream text remain authoritative.
    This pass may only add searchable indexes whose evidence occurs in the source.
    """

    def __init__(self, config: dict[str, Any] | None):
        value = config if isinstance(config, dict) else {}
        self.enabled = bool(value.get("enabled", False))
        self.base_url = str(value.get("base_url") or "").rstrip("/")
        self.api_key = str(value.get("api_key") or "")
        self.model = str(value.get("model") or "")
        self.timeout = max(3, min(60, int(value.get("timeout_seconds") or 20)))

    def enrich(self, spec: PersonaSpec) -> dict[str, Any]:
        if not self.enabled:
            return {"enabled": False, "status": "skipped", "added": {}}
        parsed = urlparse(self.base_url)
        if parsed.scheme != "https" or not parsed.hostname or not self.api_key or not self.model:
            return {
                "enabled": True,
                "status": "unavailable",
                "added": {},
                "findings": ["语义提取配置不完整或 URL 非 HTTPS"],
            }
        source = str(spec.source_behavior or "").strip()
        if not source:
            return {
                "enabled": True,
                "status": "skipped",
                "added": {},
                "findings": ["没有可分析的原始人物规则"],
            }
        payload = {
            "model": self.model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "你是人物 Skill 结构化索引器，只返回 JSON。不得改写或删除原文。"
                        "输出 core_rules、examples、signature_utterances 三个数组。每项必须包含 "
                        "evidence，且 evidence 必须是输入原文中的连续短句。无法确认就不要输出。"
                        "signature_utterances 字段为 id、display_text、semantic_rule、explicit_aliases、"
                        "positive_examples、evidence。"
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {"personaId": spec.id, "sourceBehavior": source[:40_000]},
                        ensure_ascii=False,
                    ),
                },
            ],
        }
        try:
            response = requests.post(
                self.base_url + "/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json=payload,
                timeout=self.timeout,
                allow_redirects=False,
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            content = re.sub(r"^```(?:json)?\s*|\s*```$", "", str(content).strip())
            value = json.loads(content)
            if not isinstance(value, dict):
                raise ValueError("语义提取结果不是对象")
            added = self._merge(spec, value, source)
            return {"enabled": True, "status": "enriched", "added": added, "findings": []}
        except Exception:
            return {
                "enabled": True,
                "status": "unavailable",
                "added": {},
                "findings": ["语义提取 LLM 暂时不可用，已使用确定性转换结果"],
            }

    @staticmethod
    def _evidence(item: Any, source: str) -> str:
        if not isinstance(item, dict):
            return ""
        evidence = re.sub(r"\s+", " ", str(item.get("evidence") or "")).strip()[:500]
        normalized_source = re.sub(r"\s+", " ", source)
        return evidence if evidence and evidence in normalized_source else ""

    def _merge(self, spec: PersonaSpec, value: dict[str, Any], source: str) -> dict[str, int]:
        added = {"core_rules": 0, "examples": 0, "signature_utterances": 0}
        existing_rules = {re.sub(r"\s+", "", str(item.get("rule") or "")) for item in spec.core_rules}
        for item in value.get("core_rules", [])[:20]:
            evidence = self._evidence(item, source)
            rule = re.sub(r"\s+", " ", str(item.get("rule") or "")).strip()[:500] if isinstance(item, dict) else ""
            key = re.sub(r"\s+", "", rule)
            if not evidence or not rule or key in existing_rules:
                continue
            existing_rules.add(key)
            spec.core_rules.append(
                {
                    "id": f"semantic-{len(spec.core_rules) + 1:03d}",
                    "rule": rule,
                    "priority": 70,
                    "confidence": max(0.0, min(1.0, float(item.get("confidence", 0.8)))),
                    "evidence_refs": [evidence],
                }
            )
            added["core_rules"] += 1

        existing_examples = {
            (str(item.get("user") or ""), str(item.get("assistant") or "")) for item in spec.examples
        }
        for item in value.get("examples", [])[:20]:
            evidence = self._evidence(item, source)
            if not evidence or not isinstance(item, dict):
                continue
            user = str(item.get("user") or "").strip()[:300]
            assistant = str(item.get("assistant") or "").strip()[:500]
            if not user or not assistant or (user, assistant) in existing_examples:
                continue
            existing_examples.add((user, assistant))
            spec.examples.append(
                {
                    "id": f"semantic-example-{len(spec.examples) + 1:03d}",
                    "scene": str(item.get("scene") or "语义提取示例")[:100],
                    "user": user,
                    "assistant": assistant,
                    "tags": ["semantic-extractor"],
                    "evidence_refs": [evidence],
                }
            )
            added["examples"] += 1

        existing_signatures = {str(item.get("id") or "") for item in spec.signature_utterances}
        for item in value.get("signature_utterances", [])[:12]:
            evidence = self._evidence(item, source)
            if not evidence or not isinstance(item, dict):
                continue
            # Signature expressions are an optional, explicit Persona capability.
            # Do not promote an ordinary catchphrase merely because an LLM judged
            # it memorable; the source must name it as a signature/greeting.
            if not re.search(r"招牌|标志性(?:问候|台词|表达)|signature", evidence, re.I):
                continue
            signature_id = re.sub(r"[^a-z0-9._-]+", "-", str(item.get("id") or "").lower()).strip("-")[:64]
            display_text = str(item.get("display_text") or "").strip()[:160]
            if not signature_id or not display_text or signature_id in existing_signatures:
                continue
            existing_signatures.add(signature_id)
            spec.signature_utterances.append(
                {
                    "id": signature_id,
                    "display_text": display_text,
                    "explicit_aliases": [str(x)[:80] for x in item.get("explicit_aliases", [])[:16]],
                    "semantic_rule": str(item.get("semantic_rule") or evidence)[:2000],
                    "positive_examples": [str(x)[:180] for x in item.get("positive_examples", [])[:20]],
                    "ambiguity_policy": "上下文不能唯一确定时不触发",
                    "assets": {},
                    "style_map": {},
                    "fallback": "tts",
                    "evidence_refs": [evidence],
                }
            )
            added["signature_utterances"] += 1
        return added
