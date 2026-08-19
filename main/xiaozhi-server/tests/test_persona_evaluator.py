import unittest

from core.companion.importers.compiler import PersonaCompiler
from core.companion.models import PersonaSpec
from core.companion.persona.evaluator import evaluate_persona
from core.companion.persona.judge import PersonaJudge


class PersonaEvaluatorTest(unittest.TestCase):
    def _spec(self):
        return PersonaSpec.from_dict(
            {
                "schema_version": "cyber-persona/v1",
                "id": "persona.fictional.test",
                "display_name": "测试兔",
                "source": {"adapter": "test", "family": "relationship", "is_fictional": True,
                           "artifact_sha256": "a" * 64},
                "identity": {"summary": "一个虚构测试人物"},
                "core_rules": [{"id": "care", "rule": "先问清具体情况", "priority": 100}],
                "limitations": ["不虚构未发生的共同经历"],
                "relationship_policy": {"initial_stage": "familiar", "allowed_stages": ["familiar", "friend"]},
            }
        )

    def test_rule_suite_returns_named_scenarios(self):
        spec = self._spec()
        report = evaluate_persona(spec, PersonaCompiler().compile(spec))
        self.assertEqual("passed", report["status"])
        self.assertGreaterEqual(len(report["scenarios"]), 7)

    def test_disabled_judge_is_safe_and_deterministic(self):
        result = PersonaJudge({"enabled": False}).evaluate(self._spec(), "prompt")
        self.assertEqual("skipped", result["status"])
