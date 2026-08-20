from types import SimpleNamespace
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from core.companion.presentation import apply_success_acknowledgement, resolve_presentation
from core.companion.proactive import (
    ProactiveRuntimeRegistry,
    ProactiveRuntimeState,
    in_quiet_hours,
    is_proactive_rejection,
    proactive_decision,
    proactive_due,
)
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

    def test_proactive_schedule_respects_cross_midnight_quiet_hours(self):
        timezone = ZoneInfo("Asia/Shanghai")
        late = datetime(2026, 8, 20, 23, 30, tzinfo=timezone).timestamp()
        morning = datetime(2026, 8, 21, 7, 30, tzinfo=timezone).timestamp()
        daytime = datetime(2026, 8, 21, 9, 0, tzinfo=timezone).timestamp()
        self.assertTrue(in_quiet_hours(late, "23:00", "08:00", "Asia/Shanghai"))
        self.assertTrue(in_quiet_hours(morning, "23:00", "08:00", "Asia/Shanghai"))
        self.assertFalse(in_quiet_hours(daytime, "23:00", "08:00", "Asia/Shanghai"))

    def test_proactive_schedule_enforces_daily_and_unanswered_limits(self):
        now = datetime(2026, 8, 20, 12, 0, tzinfo=ZoneInfo("Asia/Shanghai")).timestamp()
        daily = proactive_decision(
            now, now - 3600, ProactiveRuntimeState(sent_today=3), 5, daily_limit=3
        )
        unanswered = proactive_decision(
            now,
            now - 3600,
            ProactiveRuntimeState(unanswered_count=2, waiting_for_response=True),
            5,
            max_unanswered=3,
        )
        self.assertEqual("daily_limit", daily.reason)
        self.assertEqual("unanswered_limit", unanswered.reason)

    def test_proactive_schedule_backs_off_while_waiting_for_response(self):
        now = datetime(2026, 8, 20, 12, 0, tzinfo=ZoneInfo("Asia/Shanghai")).timestamp()
        state = ProactiveRuntimeState(last_sent_at=now - 599, waiting_for_response=True)
        early = proactive_decision(now, now - 3600, state, 5)
        state.last_sent_at = now - 600
        due = proactive_decision(now, now - 3600, state, 5)
        self.assertEqual(600, early.effective_interval_seconds)
        self.assertFalse(early.due)
        self.assertTrue(due.due)

    def test_proactive_registry_survives_reconnect_and_applies_rejection_cooldown(self):
        registry = ProactiveRuntimeRegistry()
        now = datetime(2026, 8, 20, 12, 0, tzinfo=ZoneInfo("Asia/Shanghai")).timestamp()
        key = "user|agent|persona"
        registry.record_sent(key, now, "Asia/Shanghai")
        self.assertEqual(1, registry.snapshot(key, now + 1, "Asia/Shanghai").sent_today)
        outcome = registry.record_user_response(
            key, "别再主动找我", now + 2, "Asia/Shanghai", 1440
        )
        state = registry.snapshot(key, now + 3, "Asia/Shanghai")
        decision = proactive_decision(now + 3600, now, state, 5)
        self.assertEqual("rejected", outcome)
        self.assertEqual("rejection_cooldown", decision.reason)
        self.assertTrue(is_proactive_rejection("以后不要再发消息"))
        self.assertEqual(
            {"activeBindings": 1, "waitingForResponse": 0, "rejectionCooldowns": 1},
            registry.summary(now + 3),
        )

    def test_tool_acknowledgement_only_prefixes_success(self):
        self.assertEqual("行，灯已打开", apply_success_acknowledgement("灯已打开", "行", True))
        self.assertEqual("灯具离线", apply_success_acknowledgement("灯具离线", "行", False))
        self.assertEqual("行，灯已打开", apply_success_acknowledgement("行，灯已打开", "行", True))
