import json
from types import SimpleNamespace
import unittest

from config import settings
from core.utils.cache.manager import CacheType, cache_manager


settings.config_file_valid = True
cache_manager.set(
    CacheType.CONFIG,
    "main_config",
    {
        "log": {
            "log_level": "ERROR",
            "log_dir": "/tmp",
            "log_file": "xiaozhi-input-expression-tests.log",
        }
    },
)

from core.companion.event_extractor import RuleBasedEventExtractor
from core.companion.input_signal import enrich_text_affect, parse_user_turn_signal
from core.companion.presentation import render_expression_plan, resolve_turn_expression_plan
from core.companion.state_models import CompanionEvent, EmotionState, UserTurnSignal
from core.providers.asr.utils import lang_tag_filter


class InputSignalTest(unittest.TestCase):
    def test_funasr_keeps_stable_emotion_label_and_separate_emoji(self):
        result = lang_tag_filter("<|zh|><|SAD|><|Speech|><|withitn|>我有点累。")

        self.assertEqual("我有点累。", result["content"])
        self.assertEqual("SAD", result["emotion"])
        self.assertEqual("😔", result["emotion_emoji"])

    def test_asr_json_becomes_clean_text_and_structured_signal(self):
        signal = parse_user_turn_signal(
            json.dumps(
                {
                    "speaker": "小明",
                    "content": "今天终于做完了",
                    "language": "zh",
                    "emotion": "HAPPY",
                },
                ensure_ascii=False,
            ),
            turn_id="turn-1",
        )

        self.assertEqual("turn-1", signal.turn_id)
        self.assertEqual("今天终于做完了", signal.text)
        self.assertEqual("小明", signal.speaker)
        self.assertEqual("HAPPY", signal.acoustic_emotion)
        self.assertGreaterEqual(signal.acoustic_confidence, 0.55)

    def test_legacy_emoji_emotion_remains_compatible(self):
        signal = parse_user_turn_signal(
            {"content": "没事", "emotion": "😔"},
            turn_id="turn-2",
        )

        self.assertEqual("SAD", signal.acoustic_emotion)
        self.assertLess(signal.valence, 0.5)

    def test_acoustic_affect_can_create_pre_turn_event_without_keywords(self):
        signal = UserTurnSignal(
            turn_id="turn-3",
            text="今天发生了一些事",
            acoustic_emotion="SAD",
            acoustic_confidence=0.7,
        )

        events = RuleBasedEventExtractor().extract_pre_turn(signal)

        self.assertEqual(["user_expressed_distress"], [item.event_type for item in events])
        self.assertEqual("acoustic", events[0].payload["source"])

    def test_text_affect_is_added_without_overwriting_acoustic_source(self):
        signal = UserTurnSignal(
            turn_id="turn-4",
            text="我真的好开心",
            acoustic_emotion="NEUTRAL",
            acoustic_confidence=0.55,
        )
        enriched = enrich_text_affect(
            signal,
            [CompanionEvent("user_expressed_joy", 0.82)],
        )

        self.assertEqual("NEUTRAL", enriched.acoustic_emotion)
        self.assertEqual("HAPPY", enriched.text_emotion)
        self.assertGreater(enriched.valence, 0.5)


class TurnExpressionPlanTest(unittest.TestCase):
    def _session(self, events=None, **emotion):
        defaults = EmotionState().__dict__
        defaults.update(emotion)
        defaults.pop("updated_at", None)
        state = SimpleNamespace(emotion=SimpleNamespace(**defaults))
        return SimpleNamespace(
            state=state,
            turn_preview_state=None,
            turn_preview_events=events or [],
            overlay={"tts_dynamic_emotion": True},
        )

    def test_distress_has_one_comforting_plan_for_text_tts_and_device(self):
        plan = resolve_turn_expression_plan(
            self._session([CompanionEvent("user_expressed_distress", 0.9)]),
            turn_id="turn-5",
        )

        self.assertEqual("comforting", plan.primary_style)
        self.assertIn("soft", plan.modifiers)
        self.assertEqual("concerned", plan.provider_hint["style"])
        self.assertEqual("concerned", plan.device_expression)
        self.assertTrue(plan.dynamic_emotion_enabled)
        prompt = render_expression_plan(plan)
        self.assertIn("先接住对方", prompt)
        self.assertNotIn("comforting", prompt)

    def test_proactive_turn_has_fresh_soft_intimate_plan(self):
        plan = resolve_turn_expression_plan(
            self._session(warmth=0.8),
            turn_id="proactive-1",
            source="proactive",
        )

        self.assertEqual("intimate", plan.primary_style)
        self.assertIn("soft", plan.modifiers)
        self.assertEqual("warm", plan.provider_hint["style"])
        self.assertEqual("proactive", plan.source)


if __name__ == "__main__":
    unittest.main()
