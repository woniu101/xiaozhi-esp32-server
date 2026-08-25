from __future__ import annotations

import math
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from typing import Any

from core.companion.state_models import CompanionEvent, CompanionMood


def _clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, float(value)))


def _number(value: Any, default: float, minimum: float, maximum: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(parsed):
        return default
    return max(minimum, min(maximum, parsed))


def _datetime(value: str | None, fallback: datetime) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except (TypeError, ValueError):
        return fallback


@dataclass(frozen=True)
class EmotionProfile:
    """Persona-tunable dynamics. Values are bounded before runtime use."""

    reactivity: float = 1.0
    recovery_rate: float = 1.0
    expressiveness: float = 1.0
    minimum_hold_seconds: float = 90.0
    repeat_damping: float = 0.65
    repeat_window_seconds: float = 900.0
    negative_mood_cap: float = 0.75
    negative_voice_cap: float = 0.68

    def to_dict(self) -> dict[str, float]:
        return {
            "reactivity": self.reactivity,
            "recovery_rate": self.recovery_rate,
            "expressiveness": self.expressiveness,
            "minimum_hold_seconds": self.minimum_hold_seconds,
            "repeat_damping": self.repeat_damping,
            "repeat_window_seconds": self.repeat_window_seconds,
            "negative_mood_cap": self.negative_mood_cap,
            "negative_voice_cap": self.negative_voice_cap,
        }

    @classmethod
    def from_persona(cls, persona=None) -> "EmotionProfile":
        logic = getattr(persona, "emotional_logic", persona)
        logic = logic if isinstance(logic, dict) else {}
        if isinstance(logic.get("emotional_logic"), dict):
            logic = logic["emotional_logic"]
        nested = logic.get("mood_profile") or logic.get("emotion_profile") or {}
        values = {**logic, **nested} if isinstance(nested, dict) else logic
        return cls(
            reactivity=_number(values.get("reactivity"), 1.0, 0.4, 1.6),
            recovery_rate=_number(values.get("recovery_rate"), 1.0, 0.4, 2.0),
            expressiveness=_number(values.get("expressiveness"), 1.0, 0.35, 1.35),
            minimum_hold_seconds=_number(
                values.get("minimum_hold_seconds"), 90.0, 0.0, 600.0
            ),
            repeat_damping=_number(values.get("repeat_damping"), 0.65, 0.3, 1.0),
            repeat_window_seconds=_number(
                values.get("repeat_window_seconds"), 900.0, 30.0, 3600.0
            ),
            negative_mood_cap=_number(
                values.get("negative_mood_cap"), 0.75, 0.45, 0.85
            ),
            negative_voice_cap=_number(
                values.get("negative_voice_cap"), 0.68, 0.35, 0.75
            ),
        )


class EmotionEngine:
    BASELINES = {
        "valence": 0.55,
        "arousal": 0.35,
        "warmth": 0.5,
        "irritation": 0.0,
        "fatigue": 0.1,
    }
    HALF_LIFE_HOURS = {
        "valence": 8.0,
        "arousal": 2.0,
        "warmth": 24.0,
        "irritation": 3.0,
        "fatigue": 6.0,
    }
    # User distress affects the companion's caring stance, not by copying the
    # user's sadness into the companion as its own dominant mood.
    EVENT_DELTAS = {
        "user_showed_care": {"warmth": 0.05, "valence": 0.03},
        "user_expressed_gratitude": {"warmth": 0.03, "valence": 0.03},
        "user_expressed_exhaustion": {"warmth": 0.025, "arousal": -0.02},
        "user_expressed_distress": {
            "valence": -0.015,
            "arousal": -0.01,
            "warmth": 0.03,
        },
        "user_expressed_joy": {"valence": 0.06, "arousal": 0.05, "warmth": 0.02},
        "user_insulted_companion": {"irritation": 0.10, "warmth": -0.05, "valence": -0.08},
        "user_apologized": {"irritation": -0.08, "warmth": 0.03, "valence": 0.02},
        "shared_plan_created": {"valence": 0.03, "arousal": 0.03},
    }

    def decay(
        self,
        state: CompanionMood,
        now: datetime | None = None,
        profile: EmotionProfile | None = None,
    ) -> CompanionMood:
        now = now or datetime.now(timezone.utc)
        profile = profile or EmotionProfile()
        updated = _datetime(state.updated_at, now)
        hours = max(0.0, (now - updated).total_seconds() / 3600.0)
        values = {}
        for field_name, baseline in self.BASELINES.items():
            old = _clamp(getattr(state, field_name))
            half_life = self.HALF_LIFE_HOURS[field_name] / profile.recovery_rate
            factor = math.pow(0.5, hours / half_life)
            values[field_name] = _clamp(baseline + (old - baseline) * factor)
        if (now - _datetime(state.last_event_at, now)).total_seconds() > profile.repeat_window_seconds:
            last_event_type, last_event_at, repeat_count = None, None, 0
        else:
            last_event_type, last_event_at, repeat_count = (
                state.last_event_type,
                state.last_event_at,
                max(0, int(state.repeat_count or 0)),
            )
        dominant, intensity, held_until = self._resolve_dominant(
            state,
            values,
            now,
            profile,
            candidate=self._candidate_mood(values),
        )
        return replace(
            state,
            **values,
            dominant=dominant,
            intensity=intensity,
            held_until=held_until,
            last_event_type=last_event_type,
            last_event_at=last_event_at,
            repeat_count=repeat_count,
            updated_at=now.isoformat(),
        )

    def apply(
        self,
        state: CompanionMood,
        events: list[CompanionEvent],
        profile: EmotionProfile | None = None,
        now: datetime | None = None,
    ) -> CompanionMood:
        now = now or datetime.now(timezone.utc)
        profile = profile or EmotionProfile()
        values = {name: _clamp(getattr(state, name)) for name in self.BASELINES}
        last_type = state.last_event_type
        last_at = _datetime(state.last_event_at, now)
        repeat_count = max(0, int(state.repeat_count or 0))
        strongest: tuple[float, str] | None = None
        boundary_interrupt = False
        for event in events:
            confidence = _clamp(event.confidence)
            if confidence < 0.55 or event.event_type not in self.EVENT_DELTAS:
                continue
            if event.event_type == "user_insulted_companion" and confidence >= 0.75:
                boundary_interrupt = True
            within_window = (now - last_at).total_seconds() <= profile.repeat_window_seconds
            if event.event_type == last_type and within_window:
                repeat_count += 1
            else:
                last_type = event.event_type
                repeat_count = 1
            last_at = now
            repetition_factor = math.pow(
                profile.repeat_damping,
                min(max(repeat_count - 1, 0), 4),
            )
            for name, delta in self.EVENT_DELTAS[event.event_type].items():
                limited_delta = max(
                    -0.12,
                    min(
                        0.12,
                        delta * confidence * profile.reactivity * repetition_factor,
                    ),
                )
                values[name] = _clamp(values[name] + limited_delta)
            score = confidence * repetition_factor
            if strongest is None or score > strongest[0]:
                strongest = (score, event.event_type)
        values["irritation"] = min(values["irritation"], profile.negative_mood_cap)
        strongest_event = strongest[1] if strongest else None
        candidate = self._candidate_mood(values, strongest_event)
        dominant, intensity, held_until = self._resolve_dominant(
            state,
            values,
            now,
            profile,
            candidate=candidate,
            force_switch=boundary_interrupt,
        )
        return replace(
            state,
            **values,
            dominant=dominant,
            intensity=intensity,
            held_until=held_until,
            last_event_type=last_type,
            last_event_at=last_at.isoformat() if strongest else state.last_event_at,
            repeat_count=repeat_count if strongest else state.repeat_count,
            updated_at=now.isoformat(),
        )

    def describe(self, state: CompanionMood) -> tuple[str, str]:
        values = {name: getattr(state, name) for name in self.BASELINES}
        derived = self._candidate_mood(values)
        dominant = state.dominant or derived
        if dominant == "neutral" and derived != "neutral":
            dominant = derived
        if dominant == "annoyed":
            return "有一点不满，但会克制地表达边界", "annoyed"
        if dominant == "tired":
            return "精力偏低，说话更轻、更短", "sleepy"
        if dominant == "warm":
            return "心情温暖，愿意自然地表达关心", "warm"
        if dominant == "joyful":
            return "心情不错，回应会更轻快", "happy"
        if dominant == "low":
            return "情绪略低落，回应比较安静", "sad"
        return "情绪平稳，交流自然", "neutral"

    def _candidate_mood(self, values: dict[str, float], event_type: str | None = None) -> str:
        if event_type == "user_insulted_companion" or values["irritation"] >= 0.3:
            return "annoyed"
        if values["fatigue"] >= 0.7:
            return "tired"
        if event_type == "user_expressed_joy" or (
            values["valence"] >= 0.67 and values["arousal"] >= 0.48
        ):
            return "joyful"
        if event_type in {
            "user_showed_care",
            "user_expressed_gratitude",
            "user_apologized",
        } or values["warmth"] >= 0.68:
            return "warm"
        if values["valence"] <= 0.32:
            return "low"
        return "neutral"

    def _mood_intensity(self, dominant: str, values: dict[str, float]) -> float:
        return _clamp(
            {
                "annoyed": values["irritation"],
                "tired": values["fatigue"],
                "joyful": (values["valence"] + values["arousal"]) / 2,
                "warm": values["warmth"],
                "low": 1.0 - values["valence"],
                "neutral": max(0.2, abs(values["valence"] - 0.5)),
            }.get(dominant, 0.25)
        )

    def _resolve_dominant(
        self,
        state: CompanionMood,
        values: dict[str, float],
        now: datetime,
        profile: EmotionProfile,
        *,
        candidate: str,
        force_switch: bool = False,
    ) -> tuple[str, float, str | None]:
        current = state.dominant or "neutral"
        candidate_intensity = self._mood_intensity(candidate, values)
        current_intensity = _clamp(state.intensity)
        held_until_value = state.held_until
        hold_active = _datetime(held_until_value, now) > now if held_until_value else False
        if (
            candidate != current
            and current != "neutral"
            and hold_active
            and not force_switch
            and candidate_intensity < current_intensity + 0.18
        ):
            return current, self._mood_intensity(current, values), held_until_value
        if candidate != current:
            held_until_value = (
                now + timedelta(seconds=profile.minimum_hold_seconds)
            ).isoformat()
        elif held_until_value and not hold_active:
            held_until_value = None
        return candidate, candidate_intensity, held_until_value
