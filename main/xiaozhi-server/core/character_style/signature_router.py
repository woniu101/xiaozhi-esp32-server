import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.character_style.models import (
    SignatureItem,
    SignatureSegment,
    SignatureSegmentType,
)
from core.character_style.signature_asset import resolve_signature_audio


_SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_ASCII_WORD = re.compile(r"[A-Za-z0-9_]")


@dataclass(frozen=True)
class _Candidate:
    text: str
    folded: str
    item: SignatureItem


@dataclass(frozen=True)
class _Match:
    start: int
    end: int
    candidate: _Candidate


class SignatureRouter:
    """Route only text already emitted by the LLM into TEXT/FILE segments."""

    def __init__(self, items: list[SignatureItem]):
        candidates: list[_Candidate] = []
        for item in items:
            seen: set[str] = set()
            for trigger in (item.display_text, *item.aliases):
                folded = trigger.lower()
                if not trigger or folded in seen:
                    continue
                seen.add(folded)
                candidates.append(_Candidate(trigger, folded, item))
        self._candidates = sorted(
            candidates,
            key=lambda candidate: (-len(candidate.text), candidate.text.lower(), candidate.item.item_id),
        )
        self._max_trigger_length = max((len(item.text) for item in self._candidates), default=0)
        self._buffer = ""
        self._played: set[str] = set()

    @property
    def enabled(self) -> bool:
        return bool(self._candidates)

    @property
    def played_item_ids(self) -> frozenset[str]:
        return frozenset(self._played)

    def feed(self, text: str | None) -> list[SignatureSegment]:
        if text:
            self._buffer += text
        return self._drain(final=False)

    def flush(self) -> list[SignatureSegment]:
        return self._drain(final=True)

    def _drain(self, final: bool) -> list[SignatureSegment]:
        if not self._buffer:
            return []
        if not self._candidates:
            value = self._buffer
            self._buffer = ""
            return [_text_segment(value)]

        output: list[SignatureSegment] = []
        while self._buffer:
            match, deferred_at = self._find_earliest(final)
            if match is not None:
                _append_text(output, self._buffer[: match.start])
                matched_text = self._buffer[match.start : match.end]
                item = match.candidate.item
                if item.item_id in self._played:
                    _append_text(output, matched_text)
                else:
                    self._played.add(item.item_id)
                    output.append(
                        SignatureSegment(
                            SignatureSegmentType.FILE,
                            matched_text,
                            item.audio_path,
                        )
                    )
                self._buffer = self._buffer[match.end :]
                continue

            if final:
                cutoff = len(self._buffer)
            else:
                cutoff = max(0, len(self._buffer) - self._max_trigger_length)
                if deferred_at is not None:
                    cutoff = min(cutoff, deferred_at)
            if cutoff <= 0:
                break
            _append_text(output, self._buffer[:cutoff])
            self._buffer = self._buffer[cutoff:]

        return output

    def _find_earliest(self, final: bool) -> tuple[_Match | None, int | None]:
        folded_buffer = self._buffer.lower()
        for start in range(len(self._buffer)):
            valid: list[_Candidate] = []
            partial = False
            suffix = folded_buffer[start:]
            for candidate in self._candidates:
                if not _start_boundary_ok(self._buffer, start, candidate.text):
                    continue
                if suffix and len(suffix) < len(candidate.folded) and candidate.folded.startswith(suffix):
                    partial = True
                    continue
                end = start + len(candidate.text)
                if end > len(self._buffer) or folded_buffer[start:end] != candidate.folded:
                    continue
                if not _end_boundary_ok(self._buffer, end, candidate.text, final):
                    if end == len(self._buffer) and not final and _ends_ascii_word(candidate.text):
                        partial = True
                    continue
                valid.append(candidate)

            if valid:
                selected = valid[0]
                if not final and any(
                    len(candidate.text) > len(selected.text)
                    and candidate.folded.startswith(folded_buffer[start:])
                    for candidate in self._candidates
                ):
                    return None, start
                return _Match(start, start + len(selected.text), selected), None
            if partial and not final:
                return None, start
        return None, None


def create_signature_router(
    character_style: dict[str, Any] | None,
    storage_root: str | Path = "data",
) -> SignatureRouter:
    if not isinstance(character_style, dict) or character_style.get("active") is not True:
        return SignatureRouter([])
    config = character_style.get("signature_config")
    if not isinstance(config, dict) or config.get("enabled") is not True:
        return SignatureRouter([])
    asset_root = character_style.get("asset_root")
    if not isinstance(asset_root, str):
        return SignatureRouter([])

    items: list[SignatureItem] = []
    raw_items = config.get("items")
    if not isinstance(raw_items, list):
        return SignatureRouter([])
    for raw in raw_items[:50]:
        if not isinstance(raw, dict) or raw.get("enabled") is not True:
            continue
        item_id = raw.get("id")
        display_text = raw.get("display_text")
        aliases = raw.get("aliases", [])
        audio_path = raw.get("audio_path")
        if not isinstance(item_id, str) or not _SAFE_ID.fullmatch(item_id):
            continue
        if not isinstance(display_text, str) or not 0 < len(display_text) <= 300:
            continue
        if not isinstance(aliases, list) or len(aliases) > 20:
            continue
        safe_aliases = tuple(
            value
            for value in aliases
            if isinstance(value, str) and 0 < len(value) <= 300
        )
        if not isinstance(audio_path, str):
            continue
        resolved_audio = resolve_signature_audio(storage_root, asset_root, audio_path)
        if resolved_audio is None:
            continue
        items.append(SignatureItem(item_id, display_text, safe_aliases, resolved_audio))
    return SignatureRouter(items)


def _append_text(output: list[SignatureSegment], value: str) -> None:
    if not value:
        return
    if output and output[-1].segment_type is SignatureSegmentType.TEXT:
        previous = output[-1]
        output[-1] = SignatureSegment(SignatureSegmentType.TEXT, previous.text + value)
    else:
        output.append(_text_segment(value))


def _text_segment(value: str) -> SignatureSegment:
    return SignatureSegment(SignatureSegmentType.TEXT, value)


def _starts_ascii_word(value: str) -> bool:
    return bool(value and _ASCII_WORD.fullmatch(value[0]))


def _ends_ascii_word(value: str) -> bool:
    return bool(value and _ASCII_WORD.fullmatch(value[-1]))


def _start_boundary_ok(buffer: str, start: int, trigger: str) -> bool:
    return not (
        _starts_ascii_word(trigger)
        and start > 0
        and _ASCII_WORD.fullmatch(buffer[start - 1])
    )


def _end_boundary_ok(buffer: str, end: int, trigger: str, final: bool) -> bool:
    if not _ends_ascii_word(trigger):
        return True
    if end < len(buffer):
        return not bool(_ASCII_WORD.fullmatch(buffer[end]))
    return final
