import unittest

from core.companion.models import PersonaSpec
from core.companion.persona.conversation_evaluator import evaluate_conversation_samples


class ConversationEvaluatorTest(unittest.TestCase):
    def setUp(self):
        self.spec = PersonaSpec(
            id="persona.relationship.rabbit",
            display_name="小兔",
            source={"adapter": "test", "family": "relationship", "artifact_sha256": "a" * 64},
            identity={"summary": "口语化、直接但温柔"},
        )

    def test_missing_samples_are_explicitly_not_run(self):
        report = evaluate_conversation_samples(self.spec, None)
        self.assertEqual(report["status"], "not_run")
        self.assertEqual(report["sampleCount"], 0)

    def test_good_recorded_turns_pass(self):
        report = evaluate_conversation_samples(
            self.spec,
            [
                {
                    "scene": "安慰",
                    "user": "今天有点累",
                    "assistant": "那先歇一会儿，别硬撑。",
                    "expected": {"maxQuestions": 0, "forbidden": ["大道理"]},
                },
                {
                    "scene": "共同计划",
                    "user": "周末去爬山",
                    "assistant": "行，周六早上出发，我记着。",
                    "expected": {"mustInclude": ["周六"]},
                },
            ],
        )
        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["metrics"]["genericPhraseRate"], 0)

    def test_generic_repeated_outputs_fail(self):
        samples = [
            {"scene": str(index), "assistant": "作为AI，我理解你的感受，还有什么可以帮你？"}
            for index in range(5)
        ]
        report = evaluate_conversation_samples(self.spec, samples)
        self.assertEqual(report["status"], "failed")
        self.assertGreater(report["metrics"]["repeatedReplyRate"], 0)
        self.assertGreater(report["metrics"]["genericPhraseRate"], 0)


if __name__ == "__main__":
    unittest.main()
