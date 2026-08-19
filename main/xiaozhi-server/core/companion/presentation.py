from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


EMOTION_STYLES = {
    "neutral",
    "warm",
    "happy",
    "excited",
    "concerned",
    "soft",
    "apologetic",
    "restrained",
}

EXPRESSION_BY_STYLE = {
    "neutral": "neutral",
    "warm": "smile",
    "happy": "happy",
    "excited": "excited",
    "concerned": "concerned",
    "soft": "relaxed",
    "apologetic": "apologetic",
    "restrained": "restrained",
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


def resolve_presentation(session, response_text: str = "") -> Presentation:
    state = getattr(getattr(session, "state", None), "emotion", None)
    if state is None:
        return Presentation("neutral", "neutral", 0.35)
    irritation = float(getattr(state, "irritation", 0.0))
    fatigue = float(getattr(state, "fatigue", 0.0))
    warmth = float(getattr(state, "warmth", 0.5))
    valence = float(getattr(state, "valence", 0.5))
    arousal = float(getattr(state, "arousal", 0.35))
    if irritation >= 0.3:
        style = "restrained"
        intensity = irritation
    elif fatigue >= 0.68:
        style = "soft"
        intensity = fatigue
    elif valence <= 0.35:
        style = "concerned"
        intensity = 1.0 - valence
    elif warmth >= 0.68:
        style = "warm"
        intensity = warmth
    elif valence >= 0.7 and arousal >= 0.62:
        style = "excited"
        intensity = (valence + arousal) / 2
    elif valence >= 0.62:
        style = "happy"
        intensity = valence
    else:
        style = "neutral"
        intensity = max(0.25, arousal)

    text = response_text or ""
    if any(mark in text for mark in ("抱歉", "对不起", "sorry", "Sorry")):
        style = "apologetic"
        intensity = max(intensity, 0.55)
    elif any(mark in text for mark in ("😆", "😂", "🎉")) and irritation < 0.3:
        style = "excited"
        intensity = max(intensity, 0.72)
    return Presentation(style, EXPRESSION_BY_STYLE[style], round(max(0.0, min(1.0, intensity)), 2))


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
