from __future__ import annotations

import json
import re
import threading
from dataclasses import dataclass
from pathlib import Path


VOICE_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")


@dataclass(frozen=True, slots=True)
class Voice:
    voice_id: str
    name: str
    prompt_audio: Path
    languages: str = "普通话"
    prompt_text: str = ""

    def public_dict(self, default_voice_id: str) -> dict[str, object]:
        return {
            "voice_id": self.voice_id,
            "name": self.name,
            "languages": self.languages,
            "prompt_text": self.prompt_text,
            "default": self.voice_id == default_voice_id,
        }


class VoiceRegistry:
    def __init__(self, root_dir: Path, config_path: Path) -> None:
        self.root_dir = root_dir.resolve()
        self.config_path = config_path
        self.default_voice_id = ""
        self._voices: dict[str, Voice] = {}
        self._lock = threading.RLock()
        self.reload()

    def _read_payload(self) -> dict[str, object]:
        payload = json.loads(self.config_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("voices.json must contain an object")
        return payload

    def reload(self) -> None:
        with self._lock:
            self._reload_unlocked()

    def _reload_unlocked(self) -> None:
        payload = self._read_payload()
        default_voice_id = str(payload.get("default_voice", "")).strip()
        raw_voices = payload.get("voices")
        if not isinstance(raw_voices, dict) or not raw_voices:
            raise ValueError("voices.json must define at least one voice")

        voices: dict[str, Voice] = {}
        for voice_id, item in raw_voices.items():
            if not isinstance(item, dict):
                raise ValueError(f"voice {voice_id!r} must be an object")
            clean_id = str(voice_id).strip()
            if not VOICE_ID_PATTERN.fullmatch(clean_id):
                raise ValueError(f"voice_id is invalid: {clean_id!r}")
            relative_path = Path(str(item.get("prompt_audio", "")))
            if relative_path.is_absolute() or ".." in relative_path.parts:
                raise ValueError(f"voice {clean_id!r} uses an unsafe prompt_audio path")
            audio_path = (self.root_dir / relative_path).resolve()
            try:
                audio_path.relative_to(self.root_dir)
            except ValueError as exc:
                raise ValueError(f"voice {clean_id!r} escapes the bundle directory") from exc
            if not audio_path.is_file():
                raise FileNotFoundError(f"prompt audio not found for {clean_id!r}: {audio_path}")
            voices[clean_id] = Voice(
                voice_id=clean_id,
                name=str(item.get("name") or clean_id),
                prompt_audio=audio_path,
                languages=str(item.get("languages") or "普通话"),
                prompt_text=str(item.get("prompt_text") or ""),
            )

        if default_voice_id not in voices:
            raise ValueError("default_voice must reference an existing voice")
        self.default_voice_id = default_voice_id
        self._voices = voices

    def _write_payload_unlocked(self, payload: dict[str, object]) -> None:
        temporary = self.config_path.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self.config_path)

    def resolve(self, voice_id: str | None) -> Voice:
        with self._lock:
            selected = voice_id or self.default_voice_id
            try:
                return self._voices[selected]
            except KeyError as exc:
                raise KeyError(f"unknown voice_id: {selected}") from exc

    def list_public(self) -> list[dict[str, object]]:
        with self._lock:
            voices = sorted(
                self._voices.values(),
                key=lambda voice: (voice.voice_id != self.default_voice_id, voice.name),
            )
            return [voice.public_dict(self.default_voice_id) for voice in voices]

    def register(
        self,
        voice_id: str,
        name: str,
        languages: str,
        prompt_text: str,
        audio: bytes,
    ) -> dict[str, object]:
        if not VOICE_ID_PATTERN.fullmatch(voice_id):
            raise ValueError("voice_id must contain only letters, digits, dot, underscore or hyphen")
        if len(audio) < 44 or not audio.startswith(b"RIFF") or audio[8:12] != b"WAVE":
            raise ValueError("prompt audio must be a valid WAV file")

        with self._lock:
            payload = self._read_payload()
            raw_voices = payload.setdefault("voices", {})
            if not isinstance(raw_voices, dict):
                raise ValueError("voices.json voices must be an object")

            relative_path = Path("reference") / f"{voice_id}.wav"
            audio_path = self.root_dir / relative_path
            audio_path.parent.mkdir(parents=True, exist_ok=True)
            audio_temporary = audio_path.with_suffix(".wav.tmp")
            audio_temporary.write_bytes(audio)
            audio_temporary.replace(audio_path)

            raw_voices[voice_id] = {
                "name": name,
                "prompt_audio": relative_path.as_posix(),
                "languages": languages,
                "prompt_text": prompt_text,
            }
            self._write_payload_unlocked(payload)
            self._reload_unlocked()
            return self._voices[voice_id].public_dict(self.default_voice_id)

    def delete(self, voice_id: str) -> None:
        with self._lock:
            if voice_id == self.default_voice_id:
                raise ValueError("the default voice cannot be deleted")
            payload = self._read_payload()
            raw_voices = payload.get("voices")
            if not isinstance(raw_voices, dict) or voice_id not in raw_voices:
                raise KeyError(f"unknown voice_id: {voice_id}")
            item = raw_voices.pop(voice_id)
            self._write_payload_unlocked(payload)
            self._reload_unlocked()

            relative_path = Path(str(item.get("prompt_audio", ""))) if isinstance(item, dict) else Path()
            managed_path = Path("reference") / f"{voice_id}.wav"
            if relative_path.as_posix() == managed_path.as_posix():
                audio_path = (self.root_dir / relative_path).resolve()
                if audio_path.is_file():
                    audio_path.unlink()
