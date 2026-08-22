from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator


EmotionValue = Annotated[float, Field(ge=0.0, le=1.2)]


class EmotionSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    vector: list[EmotionValue]
    alpha: float = Field(default=1.0, ge=0.0, le=1.0)
    normalize: bool = True

    @field_validator("vector")
    @classmethod
    def validate_vector_length(cls, value: list[float]) -> list[float]:
        if len(value) != 8:
            raise ValueError("emotion.vector must contain exactly 8 values")
        return value


class TTSRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str | None = Field(default=None, max_length=100)
    text: str = Field(min_length=1, max_length=300)
    voice_id: str | None = Field(default=None, max_length=80)
    lang: str = Field(default="zh", min_length=2, max_length=16)
    speed: float = Field(default=1.0, ge=0.5, le=2.0)
    interval_silence_ms: int = Field(default=80, ge=0, le=1000)
    max_text_tokens_per_segment: int = Field(default=120, ge=20, le=240)
    text_normalization: bool = True
    emotion: EmotionSpec | None = None

    @field_validator("text")
    @classmethod
    def strip_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("text must not be blank")
        return value

    @field_validator("lang")
    @classmethod
    def normalize_lang(cls, value: str) -> str:
        return value.strip().lower()


class VoiceRegistrationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    voice_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
    name: str = Field(min_length=1, max_length=100)
    languages: str = Field(default="普通话", min_length=1, max_length=100)
    prompt_text: str = Field(default="", max_length=500)
    audio_base64: str = Field(min_length=16, max_length=30_000_000)

    @field_validator("voice_id", "name", "languages", "prompt_text")
    @classmethod
    def strip_text_fields(cls, value: str) -> str:
        return value.strip()
