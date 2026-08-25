from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from .emotion import EmotionProfile
from .input_signal import derive_user_affect
from .state_models import TurnExpressionPlan, UserTurnSignal


EMOTION_STYLES = {
    "neutral",
    "intimate",
    "joyful",
    "playful",
    "excited",
    "comforting",
    "vulnerable",
    "annoyed",
}

PROVIDER_STYLE_BY_PRIMARY = {
    "neutral": "neutral",
    "intimate": "warm",
    "joyful": "happy",
    "playful": "happy",
    "excited": "excited",
    "comforting": "concerned",
    "vulnerable": "soft",
    "annoyed": "restrained",
}

DEVICE_EXPRESSION_BY_PRIMARY = {
    "neutral": "neutral",
    "intimate": "smile",
    "joyful": "happy",
    "playful": "silly",
    "excited": "excited",
    "comforting": "concerned",
    "vulnerable": "sad",
    "annoyed": "restrained",
}

SPEED_BY_PRIMARY = {
    "neutral": 1.0,
    "intimate": 0.96,
    "joyful": 1.03,
    "playful": 1.04,
    "excited": 1.08,
    "comforting": 0.93,
    "vulnerable": 0.90,
    "annoyed": 0.94,
}

TEXT_GUIDANCE_BY_PRIMARY = {
    "neutral": "自然、平稳，不刻意强调情绪",
    "intimate": "带熟悉感和温度，但不突破当前关系边界",
    "joyful": "真诚地开心，有具体反应但不过度夸张",
    "playful": "轻松、带一点调侃，不强行制造笑点",
    "excited": "节奏稍快、有兴奋感，但保持句子清晰",
    "comforting": "放慢一点，先接住对方，再回应具体事情",
    "vulnerable": "更轻、更短，允许一点低落但不情绪绑架",
    "annoyed": "克制地表达边界，不辱骂、不升级冲突",
}

TEXT_GUIDANCE_BY_MODIFIER = {
    "soft": "语气更轻",
    "restrained": "保持克制",
    "apologetic": "自然承担该承担的部分，不反复道歉",
    "shy": "亲近表达含蓄一点",
}


@dataclass(frozen=True)
class Presentation:
    emotion: str
    expression: str
    intensity: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "emotion": self.emotion,
            "expression": self.expression,
            "intensity": self.intensity,
        }


def _clamp(value: float, minimum=0.0, maximum=1.0) -> float:
    return max(minimum, min(maximum, float(value)))


def resolve_turn_expression_plan(
    session,
    context=None,
    user_signal: UserTurnSignal | None = None,
    response_text: str = "",
    *,
    turn_id: str | None = None,
    source: str = "reply",
) -> TurnExpressionPlan:
    """Resolve the sole product-level expression decision for one turn."""
    turn_state = getattr(session, "turn_preview_state", None)
    state = getattr(turn_state or getattr(session, "state", None), "emotion", None)
    irritation = float(getattr(state, "irritation", 0.0)) if state else 0.0
    fatigue = float(getattr(state, "fatigue", 0.0)) if state else 0.1
    warmth = float(getattr(state, "warmth", 0.5)) if state else 0.5
    valence = float(getattr(state, "valence", 0.55)) if state else 0.55
    arousal = float(getattr(state, "arousal", 0.35)) if state else 0.35
    metadata = getattr(context, "metadata", {}) or {}
    emotion_profile = EmotionProfile.from_persona(
        getattr(session, "persona_spec", None)
    )
    event_types = set(metadata.get("event_types") or ())
    if not event_types:
        event_types = {
            getattr(event, "event_type", "")
            for event in getattr(session, "turn_preview_events", [])
        }
    if user_signal is not None:
        user_affect = derive_user_affect(user_signal)
        signal_emotion = user_affect.dominant
        signal_confidence = user_affect.confidence
        if signal_confidence >= 0.55 and signal_emotion == "HAPPY":
            event_types.add("user_expressed_joy")
        elif signal_confidence >= 0.55 and signal_emotion in {
            "SAD",
            "ANGRY",
            "FEARFUL",
            "DISGUSTED",
            "DISTRESSED",
            "EXHAUSTED",
        }:
            event_types.add("user_expressed_distress")
    response_plan = metadata.get("response_plan") or {}
    dialogue_act = str(response_plan.get("dialogue_act") or "")
    reasons = []
    modifiers = []

    if source == "proactive":
        style = "intimate"
        intensity = max(0.48, min(0.65, warmth))
        modifiers.append("soft")
        reasons.append("proactive_check_in")
    elif "user_insulted_companion" in event_types or dialogue_act == "boundary":
        style = "annoyed"
        intensity = max(0.62, irritation)
        modifiers.append("restrained")
        reasons.append("relationship_boundary")
    elif {"user_expressed_exhaustion", "user_expressed_distress"} & event_types or dialogue_act in {"comfort", "listen"}:
        style = "comforting"
        intensity = 0.62
        modifiers.append("soft")
        reasons.append("user_distress")
    elif "user_expressed_joy" in event_types:
        style = "joyful"
        intensity = max(0.64, valence)
        reasons.append("user_joy")
    elif {"user_showed_care", "user_expressed_gratitude"} & event_types:
        style = "intimate"
        intensity = max(0.62, warmth)
        reasons.append("mutual_care")
    elif "user_apologized" in event_types or dialogue_act == "repair":
        style = "intimate"
        intensity = max(0.5, warmth)
        modifiers.append("soft")
        reasons.append("conflict_repair")
    elif dialogue_act == "banter":
        style = "playful"
        intensity = max(0.55, valence)
        reasons.append("playful_banter")
    elif irritation >= 0.3:
        style = "annoyed"
        intensity = irritation
        modifiers.append("restrained")
        reasons.append("companion_irritation")
    elif fatigue >= 0.68:
        style = "vulnerable"
        intensity = fatigue
        modifiers.append("soft")
        reasons.append("companion_fatigue")
    elif valence <= 0.35:
        style = "vulnerable"
        intensity = 1.0 - valence
        modifiers.append("soft")
        reasons.append("companion_low_mood")
    elif warmth >= 0.68:
        style = "intimate"
        intensity = warmth
        reasons.append("companion_warmth")
    elif valence >= 0.7 and arousal >= 0.62:
        style = "excited"
        intensity = (valence + arousal) / 2
        reasons.append("companion_high_arousal")
    elif valence >= 0.62:
        style = "joyful"
        intensity = valence
        reasons.append("companion_positive_mood")
    else:
        style = "neutral"
        intensity = max(0.25, arousal)
        reasons.append("neutral_baseline")

    text = response_text or ""
    if any(mark in text for mark in ("抱歉", "对不起", "sorry", "Sorry")):
        if "apologetic" not in modifiers:
            modifiers.append("apologetic")
        intensity = max(intensity, 0.55)
        reasons.append("response_apology")
    elif (
        any(mark in text for mark in ("😆", "😂", "🎉"))
        and irritation < 0.3
        and style not in {"comforting", "vulnerable", "annoyed"}
    ):
        style = "excited"
        intensity = max(intensity, 0.72)
        reasons.append("response_excitement")

    provider_style = PROVIDER_STYLE_BY_PRIMARY.get(style, "neutral")
    if "apologetic" in modifiers:
        provider_style = "apologetic"
    overlay = getattr(session, "overlay", {}) or {}
    dynamic_enabled = bool(session is not None and overlay.get("tts_dynamic_emotion", True))
    # Persona expressiveness primarily shapes textual behaviour. Voice stays
    # deliberately subtler, especially for negative styles, to avoid overacting.
    text_intensity = _clamp(intensity * emotion_profile.expressiveness)
    voice_intensity = _clamp(text_intensity * 0.88)
    if style in {"annoyed", "vulnerable"}:
        voice_intensity = min(voice_intensity, emotion_profile.negative_voice_cap)
    speed = 1.0 + (
        SPEED_BY_PRIMARY.get(style, 1.0) - 1.0
    ) * min(emotion_profile.expressiveness, 1.0)
    resolved_turn_id = str(
        turn_id
        or getattr(user_signal, "turn_id", None)
        or metadata.get("turn_id")
        or ""
    )
    return TurnExpressionPlan(
        turn_id=resolved_turn_id,
        primary_style=style,
        modifiers=tuple(dict.fromkeys(modifiers)),
        text_intensity=round(text_intensity, 2),
        intensity=round(voice_intensity, 2),
        speed=round(_clamp(speed, 0.85, 1.15), 2),
        reason_codes=tuple(dict.fromkeys(reasons)),
        device_expression=DEVICE_EXPRESSION_BY_PRIMARY.get(style, "neutral"),
        provider_hint={"style": provider_style},
        dynamic_emotion_enabled=dynamic_enabled,
        source=source,
    )


def presentation_from_plan(plan: TurnExpressionPlan) -> Presentation:
    provider_style = str(plan.provider_hint.get("style") or "neutral")
    return Presentation(provider_style, plan.device_expression, plan.intensity)


def render_expression_plan(plan: TurnExpressionPlan) -> str:
    guidance = TEXT_GUIDANCE_BY_PRIMARY.get(
        plan.primary_style,
        TEXT_GUIDANCE_BY_PRIMARY["neutral"],
    )
    modifier_guidance = [
        TEXT_GUIDANCE_BY_MODIFIER[item]
        for item in plan.modifiers
        if item in TEXT_GUIDANCE_BY_MODIFIER
    ]
    if modifier_guidance:
        guidance += "；" + "；".join(modifier_guidance)
    if plan.text_intensity <= 0.42:
        guidance += "；情绪只轻微带出，不要夸张"
    elif plan.text_intensity >= 0.72:
        guidance += "；表达可以明显一些，但不演戏"
    return (
        "<turn_expression>\n"
        f"本轮统一表达：{guidance}。\n"
        "文本措辞、句长和语气都遵循这一表达；不要复述内部风格名称或本段说明。\n"
        "</turn_expression>"
    )


def resolve_presentation(session, response_text: str = "") -> Presentation:
    """Compatibility facade backed by the unified expression planner."""
    return presentation_from_plan(
        resolve_turn_expression_plan(session, response_text=response_text)
    )


def apply_success_acknowledgement(text: str, prefix: str, successful: bool) -> str:
    """Add a Persona acknowledgement only to a successful immediate tool result."""
    clean_text = str(text or "").strip()
    clean_prefix = str(prefix or "").strip()
    if not successful or not clean_text or not clean_prefix or clean_text.startswith(clean_prefix):
        return clean_text
    return f"{clean_prefix}，{clean_text}"


async def send_presentation(conn, presentation: Presentation):
    try:
        await conn.websocket.send(
            json.dumps(
                {
                    "type": "companion",
                    "event": "presentation",
                    **presentation.to_dict(),
                    "session_id": conn.session_id,
                },
                ensure_ascii=False,
            )
        )
    except Exception as error:
        conn.logger.bind(tag=__name__).warning(f"发送 Companion 表现元数据失败: {error}")
