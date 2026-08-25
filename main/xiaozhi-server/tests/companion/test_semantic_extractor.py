import json
import unittest
from unittest.mock import patch

from core.companion.models import PersonaSpec
from core.companion.persona.semantic_extractor import PersonaSemanticExtractor


class PersonaSemanticExtractorTest(unittest.TestCase):
    def setUp(self):
        self.spec = PersonaSpec(
            id="persona.rabbit",
            display_name="兔娘",
            source={},
            identity={},
            source_behavior=(
                "当用户明确想听招牌问候时，可以回应 Ciallo。"
                "用户：想听那个了。 兔娘：Ciallo～"
            ),
        )

    def test_disabled_extractor_is_deterministic_noop(self):
        report = PersonaSemanticExtractor({"enabled": False}).enrich(self.spec)
        self.assertEqual("skipped", report["status"])
        self.assertEqual([], self.spec.signature_utterances)

    def test_only_items_with_literal_source_evidence_are_merged(self):
        response_value = {
            "core_rules": [
                {
                    "rule": "仅在明确语境使用招牌问候",
                    "confidence": 0.9,
                    "evidence": "当用户明确想听招牌问候时",
                },
                {"rule": "凭空添加的规则", "evidence": "原文中不存在"},
            ],
            "examples": [],
            "signature_utterances": [
                {
                    "id": "ciallo",
                    "display_text": "Ciallo～",
                    "semantic_rule": "用户明确想听招牌问候时使用",
                    "explicit_aliases": ["Ciallo"],
                    "positive_examples": ["想听那个了"],
                    "evidence": "当用户明确想听招牌问候时，可以回应 Ciallo。",
                }
            ],
        }

        class FakeResponse:
            def raise_for_status(self):
                return None

            def json(self):
                return {"choices": [{"message": {"content": json.dumps(response_value, ensure_ascii=False)}}]}

        extractor = PersonaSemanticExtractor({
            "enabled": True,
            "base_url": "https://llm.example/v1",
            "api_key": "secret",
            "model": "semantic-indexer",
        })
        with patch("core.companion.persona.semantic_extractor.requests.post", return_value=FakeResponse()):
            report = extractor.enrich(self.spec)

        self.assertEqual("enriched", report["status"])
        self.assertEqual(1, report["added"]["core_rules"])
        self.assertEqual(1, report["added"]["signature_utterances"])
        self.assertEqual("ciallo", self.spec.signature_utterances[0]["id"])
        self.assertNotIn("凭空添加的规则", [item["rule"] for item in self.spec.core_rules])

    def test_does_not_invent_signature_from_an_ordinary_phrase(self):
        self.spec.source_behavior = "她偶尔会说 Ciallo，但这只是一句普通示例。"
        report = PersonaSemanticExtractor(None)._merge(
            self.spec,
            {
                "signature_utterances": [
                    {
                        "id": "ciallo",
                        "display_text": "Ciallo",
                        "semantic_rule": "想问候时使用",
                        "evidence": "她偶尔会说 Ciallo，但这只是一句普通示例。",
                    }
                ]
            },
            self.spec.source_behavior,
        )

        self.assertEqual(0, report["signature_utterances"])
        self.assertEqual([], self.spec.signature_utterances)


if __name__ == "__main__":
    unittest.main()
