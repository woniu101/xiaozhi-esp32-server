from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re
from threading import Lock
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


REJECTION_PATTERN = re.compile(
    r"别再?(?:主动|提醒|问候|找我|发消息)|"
    r"不要再?(?:主动|提醒|问候|找我|发消息)|"
    r"关闭主动|不用(?:主动|提醒|问候)|别烦我"
)


@dataclass(frozen=True)
class ProactiveDecision:
    due: bool
    reason: str
    effective_interval_seconds: int


@dataclass
class ProactiveRuntimeState:
    local_day: str = ""
    sent_today: int = 0
    last_sent_at: float = 0.0
    waiting_for_response: bool = False
    unanswered_count: int = 0
    cooldown_until: float = 0.0


def _timezone(name: str | None):
    try:
        return ZoneInfo(str(name or "Asia/Shanghai"))
    except ZoneInfoNotFoundError:
        return ZoneInfo("Asia/Shanghai")


def local_day(timestamp: float, timezone_name: str | None) -> str:
    return datetime.fromtimestamp(timestamp, _timezone(timezone_name)).date().isoformat()


def _clock_minutes(value: str, fallback: str) -> int:
    text = str(value or fallback)
    if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", text):
        text = fallback
    hours, minutes = text.split(":", 1)
    return int(hours) * 60 + int(minutes)


def in_quiet_hours(
    timestamp: float,
    start: str = "23:00",
    end: str = "08:00",
    timezone_name: str = "Asia/Shanghai",
) -> bool:
    current = datetime.fromtimestamp(timestamp, _timezone(timezone_name))
    minute = current.hour * 60 + current.minute
    start_minute = _clock_minutes(start, "23:00")
    end_minute = _clock_minutes(end, "08:00")
    if start_minute == end_minute:
        return False
    if start_minute < end_minute:
        return start_minute <= minute < end_minute
    return minute >= start_minute or minute < end_minute


def proactive_decision(
    now: float,
    last_user_turn: float,
    state: ProactiveRuntimeState,
    interval_minutes: int,
    *,
    daily_limit: int = 3,
    max_unanswered: int = 3,
    quiet_start: str = "23:00",
    quiet_end: str = "08:00",
    timezone_name: str = "Asia/Shanghai",
) -> ProactiveDecision:
    base_interval = max(300, min(604800, int(interval_minutes) * 60))
    effective_unanswered = max(0, int(state.unanswered_count)) + (
        1 if state.waiting_for_response else 0
    )
    effective_interval = min(
        604800,
        base_interval * (2 ** min(3, effective_unanswered)),
    )
    if now < float(state.cooldown_until or 0):
        return ProactiveDecision(False, "rejection_cooldown", effective_interval)
    if state.sent_today >= max(1, min(20, int(daily_limit))):
        return ProactiveDecision(False, "daily_limit", effective_interval)
    if effective_unanswered >= max(1, min(10, int(max_unanswered))):
        return ProactiveDecision(False, "unanswered_limit", effective_interval)
    if in_quiet_hours(now, quiet_start, quiet_end, timezone_name):
        return ProactiveDecision(False, "quiet_hours", effective_interval)
    last_trigger = max(float(last_user_turn or 0), float(state.last_sent_at or 0))
    if now - last_trigger < effective_interval:
        return ProactiveDecision(False, "interval", effective_interval)
    return ProactiveDecision(True, "due", effective_interval)


def proactive_due(
    now: float,
    last_user_turn: float,
    last_proactive_message: float,
    interval_minutes: int,
) -> bool:
    """Compatibility helper for the original interval-only scheduler contract."""
    interval_seconds = max(300, min(604800, int(interval_minutes) * 60))
    last_trigger = max(float(last_user_turn or 0), float(last_proactive_message or 0))
    return now - last_trigger >= interval_seconds


def is_proactive_rejection(text: str) -> bool:
    return bool(REJECTION_PATTERN.search(str(text or "")))


class ProactiveRuntimeRegistry:
    """Process-local state shared by reconnects for the same Companion binding."""

    def __init__(self):
        self._values: dict[str, ProactiveRuntimeState] = {}
        self._lock = Lock()

    def snapshot(self, key: str, now: float, timezone_name: str) -> ProactiveRuntimeState:
        with self._lock:
            value = self._values.setdefault(key, ProactiveRuntimeState())
            self._roll_day(value, now, timezone_name)
            return ProactiveRuntimeState(**value.__dict__)

    def record_sent(self, key: str, now: float, timezone_name: str):
        with self._lock:
            value = self._values.setdefault(key, ProactiveRuntimeState())
            self._roll_day(value, now, timezone_name)
            if value.waiting_for_response:
                value.unanswered_count += 1
            value.waiting_for_response = True
            value.sent_today += 1
            value.last_sent_at = now

    def record_user_response(
        self,
        key: str,
        text: str,
        now: float,
        timezone_name: str,
        rejection_cooldown_minutes: int,
    ) -> str:
        with self._lock:
            value = self._values.setdefault(key, ProactiveRuntimeState())
            self._roll_day(value, now, timezone_name)
            if not value.waiting_for_response:
                return "ordinary_turn"
            rejected = is_proactive_rejection(text)
            value.waiting_for_response = False
            value.unanswered_count = 0
            if rejected:
                minutes = max(60, min(43200, int(rejection_cooldown_minutes)))
                value.cooldown_until = max(value.cooldown_until, now + minutes * 60)
                return "rejected"
            return "responded"

    def summary(self, now: float | None = None) -> dict[str, int]:
        current = float(now if now is not None else datetime.now().timestamp())
        with self._lock:
            values = list(self._values.values())
            return {
                "activeBindings": len(values),
                "waitingForResponse": sum(1 for value in values if value.waiting_for_response),
                "rejectionCooldowns": sum(1 for value in values if value.cooldown_until > current),
            }

    def _roll_day(self, value: ProactiveRuntimeState, now: float, timezone_name: str):
        day = local_day(now, timezone_name)
        if value.local_day != day:
            value.local_day = day
            value.sent_today = 0


proactive_registry = ProactiveRuntimeRegistry()
