from types import SimpleNamespace
import unittest

from core.companion.presentation import apply_success_acknowledgement, resolve_presentation
from core.companion.proactive import proactive_due
from core.companion.state_models import CompanionEvent


def _session(**emotion):
    defaults = {"irritation": 0.0, "fatigue": 0.1, "warmth": 0.5, "valence": 0.55, "arousal": 0.35}
    defaults.update(emotion)
    return SimpleNamespace(state=SimpleNamespace(emotion=SimpleNamespace(**defaults)))


class CompanionPresentationTest(unittest.TestCase):
    def test_warm_state_maps_to_abstract_style_and_expression(self):
        value = resolve_presentation(_session(warmth=0.8, valence=0.7), "今天也想陪你")
        self.assertEqual("warm", value.emotion)
        self.assertEqual("smile", value.expression)

    def test_apology_overrides_style_without_provider_parameters(self):
        value = resolve_presentation(_session(warmth=0.8), "对不起，我刚才理解错了")
        self.assertEqual("apologetic", value.emotion)

    def test_current_turn_distress_immediately_changes_presentation(self):
        session = _session()
        session.turn_preview_events = [CompanionEvent("user_expressed_distress", 0.9)]
        value = resolve_presentation(session, "先缓一缓，我在。")
        self.assertEqual("concerned", value.emotion)
        self.assertEqual("concerned", value.expression)

    def test_proactive_schedule_uses_user_turn_and_last_message(self):
        now = 10_000.0
        self.assertTrue(proactive_due(now, now - 600, 0, 5))
        self.assertFalse(proactive_due(now, now - 600, now - 60, 5))

    def test_proactive_schedule_enforces_five_minute_floor(self):
        now = 10_000.0
        self.assertFalse(proactive_due(now, now - 299, 0, 1))
        self.assertTrue(proactive_due(now, now - 300, 0, 1))

    def test_tool_acknowledgement_only_prefixes_success(self):
        self.assertEqual("行，灯已打开", apply_success_acknowledgement("灯已打开", "行", True))
        self.assertEqual("灯具离线", apply_success_acknowledgement("灯具离线", "行", False))
        self.assertEqual("行，灯已打开", apply_success_acknowledgement("行，灯已打开", "行", True))
