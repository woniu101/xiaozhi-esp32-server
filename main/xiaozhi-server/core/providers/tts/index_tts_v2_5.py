import math
import uuid

import requests

from config.logger import setup_logging
from core.providers.tts.base import TTSProviderBase
from core.utils.tts import convert_percentage_to_range


TAG = __name__
logger = setup_logging()


# IndexTTS2.5 emotion order:
# happy, angry, sad, afraid, disgusted, melancholic, surprised, calm.
DEFAULT_EMOTION_VECTOR_MAP = {
    "neutral": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.65],
    "warm": [0.30, 0.0, 0.0, 0.0, 0.0, 0.05, 0.05, 0.55],
    "happy": [0.75, 0.0, 0.0, 0.0, 0.0, 0.0, 0.15, 0.20],
    "excited": [0.85, 0.0, 0.0, 0.0, 0.0, 0.0, 0.45, 0.05],
    "concerned": [0.0, 0.0, 0.25, 0.15, 0.0, 0.40, 0.0, 0.45],
    "soft": [0.10, 0.0, 0.05, 0.0, 0.0, 0.15, 0.0, 0.70],
    "apologetic": [0.0, 0.0, 0.35, 0.05, 0.0, 0.40, 0.0, 0.45],
    "restrained": [0.0, 0.05, 0.05, 0.0, 0.0, 0.20, 0.0, 0.65],
}


def _finite_float(value, default, minimum, maximum):
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(parsed):
        return default
    return max(minimum, min(maximum, parsed))


def _as_bool(value, default=False):
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() in ("true", "1", "yes", "on")


def _normalize_language(value):
    text = str(value or "ZH").strip()
    aliases = {
        "中文": "ZH",
        "普通话": "ZH",
        "zh": "ZH",
        "zh-cn": "ZH",
        "英语": "EN",
        "英文": "EN",
        "en": "EN",
        "日语": "JP",
        "ja": "JP",
        "jp": "JP",
        "韩语": "KR",
        "ko": "KR",
        "kr": "KR",
    }
    return aliases.get(text.lower(), aliases.get(text, text.upper()))


def _emotion_vectors(configured):
    result = {key: list(value) for key, value in DEFAULT_EMOTION_VECTOR_MAP.items()}
    if not isinstance(configured, dict):
        return result
    for style, vector in configured.items():
        if style not in result or not isinstance(vector, (list, tuple)) or len(vector) != 8:
            continue
        parsed = []
        for value in vector:
            try:
                item = float(value)
            except (TypeError, ValueError):
                parsed = []
                break
            if not math.isfinite(item):
                parsed = []
                break
            parsed.append(max(0.0, min(1.2, item)))
        if parsed:
            result[style] = parsed
    return result


class TTSProvider(TTSProviderBase):
    """Adapter for the dedicated IndexTTS2.5 Companion API service."""

    def __init__(self, config, delete_audio_file):
        super().__init__(config, delete_audio_file)
        base_url = str(config.get("api_url") or "http://127.0.0.1:8092").strip().rstrip("/")
        self.api_url = base_url if base_url.endswith("/v1/tts") else f"{base_url}/v1/tts"
        self.voice = str(config.get("private_voice") or config.get("voice") or "tuniang-normal").strip()
        self.lang = _normalize_language(config.get("language") or config.get("lang") or "ZH")
        self.speed = _finite_float(config.get("speed", 1.0), 1.0, 0.5, 2.0)
        if "ttsRate" in config:
            self.speed = round(
                convert_percentage_to_range(
                    config["ttsRate"], min_val=0.5, max_val=2.0, base_val=self.speed
                ),
                2,
            )
        self.emotion_alpha = _finite_float(config.get("emotion_alpha", 0.85), 0.85, 0.0, 1.0)
        self.normalize_emotion = _as_bool(config.get("normalize_emotion"), True)
        self.text_normalization = _as_bool(config.get("text_normalization"), True)
        self.emotion_vector_map = _emotion_vectors(config.get("emotion_vector_map"))
        self.audio_file_type = "wav"

    def build_request(self, text):
        payload = {
            "request_id": uuid.uuid4().hex,
            "text": text,
            "voice_id": self.voice,
            "lang": self.lang,
            "speed": self.speed,
            "text_normalization": self.text_normalization,
        }
        if self.current_dynamic_emotion_enabled:
            # Presentation intensity changes how strongly the selected direction is
            # applied, while the provider keeps the same stable eight-axis contract.
            alpha = self.emotion_alpha * (0.4 + 0.6 * self.current_emotion_intensity)
            payload["emotion"] = {
                "vector": list(
                    self.emotion_vector_map.get(
                        self.current_emotion_style,
                        self.emotion_vector_map["neutral"],
                    )
                ),
                "alpha": round(max(0.0, min(1.0, alpha)), 4),
                "normalize": self.normalize_emotion,
            }
        return payload

    async def text_to_speak(self, text, output_file):
        response = requests.post(
            self.api_url,
            json=self.build_request(text),
            headers={"Accept": "audio/wav"},
            timeout=self.tts_timeout,
        )
        if response.status_code != 200:
            details = (response.text or "").strip().replace("\n", " ")[:500]
            error_msg = (
                f"IndexTTS2.5 TTS请求失败: {response.status_code}"
                + (f" - {details}" if details else "")
            )
            logger.bind(tag=TAG).error(error_msg)
            raise RuntimeError(error_msg)
        if output_file:
            with open(output_file, "wb") as file:
                file.write(response.content)
            return None
        return response.content
