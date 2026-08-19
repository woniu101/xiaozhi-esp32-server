from __future__ import annotations


def proactive_due(
    now: float,
    last_user_turn: float,
    last_proactive_message: float,
    interval_minutes: int,
) -> bool:
    """Return whether an online session has been idle long enough for a check-in."""
    interval_seconds = max(300, min(604800, int(interval_minutes) * 60))
    last_trigger = max(float(last_user_turn or 0), float(last_proactive_message or 0))
    return now - last_trigger >= interval_seconds
