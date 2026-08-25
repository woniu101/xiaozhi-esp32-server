from __future__ import annotations

from dataclasses import replace
import json
import math
import uuid

from .state_models import CompanionEvent, UserAffect, UserTurnSignal


EMOTION_ALIASES = {
    "🙂": "HAPPY",
    "😔": "SAD",
    "😡": "ANGRY",
    "😶": "NEUTRAL",
    "😰": "FEARFUL",
    "🤢": "DISGUSTED",
    "😲": "SURPRISED",
    "EMO_UNKNOWN": "UNKNOWN",
    "FEAR": "FEARFUL",
}

EMOTION_COORDINATES = {
    "HAPPY": (0.82, 0.68),
    "SAD": (0.20, 0.28),
    "ANGRY": (0.18, 0.82),
    "FEARFUL": (0.18, 0.76),
    "DISGUSTED": (0.22, 0.56),
    "SURPRISED": (0.55, 0.82),
    "NEUTRAL": (0.50, 0.35),
    "UNKNOWN": (0.50, 0.35),
}

TEXT_AFFECT_BY_EVENT = {
    "user_expressed_joy": ("HAPPY", 0.82, 0.68),
    "user_expressed_exhaustion": ("EXHAUSTED", 0.32, 0.18),
    "user_expressed_distress": ("DISTRESSED", 0.20, 0.62),
    "user_insulted_companion": ("ANGRY", 0.18, 0.78),
    "user_apologized": ("APOLOGETIC", 0.42, 0.35),
}


def normalize_emotion_label(value) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    upper = EMOTION_ALIASES.get(text, text.upper())
    return upper if upper in EMOTION_COORDINATES else "UNKNOWN"


def _bounded_number(value, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(parsed):
        return default
    return max(0.0, min(1.0, parsed))


def parse_user_turn_signal(
    value,
    *,
    turn_id: str | None = None,
    source: str = "voice",
) -> UserTurnSignal:
    """Normalize legacy strings and ASR JSON without leaking JSON into the LLM text."""
    if isinstance(value, UserTurnSignal):
        if turn_id and value.turn_id != turn_id:
            return replace(value, turn_id=turn_id)
        return value

    data = None
    if isinstance(value, dict):
        data = value
    else:
        raw = str(value or "").strip()
        if raw.startswith("{") and raw.endswith("}"):
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    data = parsed
            except json.JSONDecodeError:
                pass

    if data is None:
        return UserTurnSignal(
            turn_id=turn_id or uuid.uuid4().hex,
            text=str(value or "").strip(),
            source=source,
        )

    text = str(data.get("content") or data.get("text") or "").strip()
    emotion = normalize_emotion_label(
        data.get("emotion_label") or data.get("emotion")
    )
    valence, arousal = EMOTION_COORDINATES.get(emotion or "UNKNOWN", (0.5, 0.35))
    explicit_confidence = data.get("emotion_confidence", data.get("emotionConfidence"))
    # FunASR labels do not currently expose probabilities. A conservative
    # calibrated default lets them influence a turn without treating them as fact.
    confidence = _bounded_number(
        explicit_confidence,
        0.55 if emotion == "NEUTRAL" else (0.65 if emotion and emotion != "UNKNOWN" else 0.0),
    )
    return UserTurnSignal(
        turn_id=turn_id or str(data.get("turn_id") or uuid.uuid4().hex),
        text=text,
        source=str(data.get("source") or source)[:24],
        speaker=str(data.get("speaker") or "").strip()[:100] or None,
        language=str(data.get("language") or "").strip()[:24] or None,
        acoustic_emotion=emotion,
        acoustic_confidence=confidence,
        valence=valence,
        arousal=arousal,
    )


def enrich_text_affect(
    signal: UserTurnSignal,
    events: list[CompanionEvent],
) -> UserTurnSignal:
    """Attach the strongest deterministic text affect while preserving ASR data."""
    best = None
    for event in events:
        mapping = TEXT_AFFECT_BY_EVENT.get(event.event_type)
        if mapping and (best is None or event.confidence > best[0]):
            best = (event.confidence, mapping)
    if best is None:
        return signal
    confidence, (label, valence, arousal) = best
    acoustic_weight = signal.acoustic_confidence
    text_weight = max(0.0, min(1.0, confidence))
    total = acoustic_weight + text_weight
    if total > 0:
        valence = (signal.valence * acoustic_weight + valence * text_weight) / total
        arousal = (signal.arousal * acoustic_weight + arousal * text_weight) / total
    return replace(
        signal,
        text_emotion=label,
        text_confidence=text_weight,
        valence=max(0.0, min(1.0, valence)),
        arousal=max(0.0, min(1.0, arousal)),
    )


def derive_user_affect(signal: UserTurnSignal) -> UserAffect:
    """Fuse ASR and text observations without turning them into companion mood."""
    acoustic = signal.acoustic_emotion
    textual = signal.text_emotion
    acoustic_confidence = _bounded_number(signal.acoustic_confidence, 0.0)
    text_confidence = _bounded_number(signal.text_confidence, 0.0)
    candidates = [
        (text_confidence, textual),
        (acoustic_confidence, acoustic),
    ]
    confidence, dominant = max(candidates, key=lambda item: item[0])
    if not dominant or confidence < 0.35:
        dominant = "NEUTRAL"
        confidence = max(confidence, 0.0)
    conflicting = bool(
        acoustic
        and textual
        and acoustic not in {"UNKNOWN", "NEUTRAL"}
        and textual not in {"UNKNOWN", "NEUTRAL"}
        and acoustic != textual
        and min(acoustic_confidence, text_confidence) >= 0.55
    )
    return UserAffect(
        dominant=dominant,
        confidence=confidence,
        valence=_bounded_number(signal.valence, 0.5),
        arousal=_bounded_number(signal.arousal, 0.35),
        acoustic_emotion=acoustic,
        text_emotion=textual,
        conflicting_sources=conflicting,
    )
