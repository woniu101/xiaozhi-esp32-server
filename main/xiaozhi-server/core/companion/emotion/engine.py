from __future__ import annotations

import math
from dataclasses import replace
from datetime import datetime, timezone

from core.companion.state_models import CompanionEvent, EmotionState, iso_now


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


class EmotionEngine:
    BASELINES = {"valence": 0.55, "arousal": 0.35, "warmth": 0.5, "irritation": 0.0, "fatigue": 0.1}
    HALF_LIFE_HOURS = {"valence": 8.0, "arousal": 2.0, "warmth": 24.0, "irritation": 3.0, "fatigue": 6.0}
    EVENT_DELTAS = {
        "user_showed_care": {"warmth": 0.05, "valence": 0.03},
        "user_expressed_gratitude": {"warmth": 0.03, "valence": 0.03},
        "user_expressed_exhaustion": {"warmth": 0.02, "arousal": -0.02},
        "user_expressed_distress": {"valence": -0.06, "arousal": 0.03, "warmth": 0.02},
        "user_expressed_joy": {"valence": 0.06, "arousal": 0.05, "warmth": 0.02},
        "user_insulted_companion": {"irritation": 0.10, "warmth": -0.05, "valence": -0.08},
        "user_apologized": {"irritation": -0.08, "warmth": 0.03, "valence": 0.02},
        "shared_plan_created": {"valence": 0.03, "arousal": 0.03},
    }

    def decay(self, state: EmotionState, now: datetime | None = None) -> EmotionState:
        now = now or datetime.now(timezone.utc)
        try:
            updated = datetime.fromisoformat(state.updated_at)
            if updated.tzinfo is None:
                updated = updated.replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            updated = now
        hours = max(0.0, (now - updated).total_seconds() / 3600.0)
        values = {}
        for field_name, baseline in self.BASELINES.items():
            old = getattr(state, field_name)
            factor = math.pow(0.5, hours / self.HALF_LIFE_HOURS[field_name])
            values[field_name] = _clamp(baseline + (old - baseline) * factor)
        return replace(state, **values, updated_at=now.isoformat())

    def apply(self, state: EmotionState, events: list[CompanionEvent]) -> EmotionState:
        values = {name: getattr(state, name) for name in self.BASELINES}
        for event in events:
            if event.confidence < 0.55:
                continue
            for name, delta in self.EVENT_DELTAS.get(event.event_type, {}).items():
                limited_delta = max(-0.12, min(0.12, delta * event.confidence))
                values[name] = _clamp(values[name] + limited_delta)
        return replace(state, **values, updated_at=iso_now())

    def describe(self, state: EmotionState) -> tuple[str, str]:
        if state.irritation >= 0.6:
            return "有些生气，但仍然保持克制", "annoyed"
        if state.irritation >= 0.3:
            return "有一点不满，表达会稍微冷一些", "slightly_annoyed"
        if state.fatigue >= 0.7:
            return "精力偏低，说话更轻、更短", "sleepy"
        if state.warmth >= 0.7 and state.valence >= 0.6:
            return "心情温暖，愿意自然地表达关心", "warm"
        if state.valence <= 0.35:
            return "情绪略低落，回应比较安静", "sad"
        return "情绪平稳，交流自然", "neutral"
