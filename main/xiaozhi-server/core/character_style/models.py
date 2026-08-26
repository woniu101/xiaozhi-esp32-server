from dataclasses import dataclass
from enum import Enum


class SignatureSegmentType(Enum):
    TEXT = "TEXT"
    FILE = "FILE"


@dataclass(frozen=True)
class SignatureItem:
    item_id: str
    display_text: str
    aliases: tuple[str, ...]
    audio_path: str


@dataclass(frozen=True)
class SignatureSegment:
    segment_type: SignatureSegmentType
    text: str
    audio_file: str | None = None
