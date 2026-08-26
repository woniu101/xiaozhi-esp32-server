import os
import wave
from pathlib import Path


MAX_AUDIO_BYTES = 5 * 1024 * 1024
MIN_DURATION_SECONDS = 0.2
MAX_DURATION_SECONDS = 15.0


def character_style_data_dir(config: dict, project_root: str | os.PathLike) -> str:
    """Return the shared data root used by both manager-api and voice runtime."""
    configured = config.get("character_style_data_dir")
    if not isinstance(configured, str) or not configured.strip():
        configured = config.get("log", {}).get("data_dir", "data")
    value = Path(configured.strip()).expanduser()
    if not value.is_absolute():
        value = Path(project_root) / value
    return str(value.resolve())


def resolve_signature_audio(
    storage_root: str | os.PathLike,
    asset_root: str,
    audio_path: str,
) -> str | None:
    """Resolve and validate a server-managed signature WAV without trusting DB paths."""
    if not _safe_relative(asset_root) or not _safe_relative(audio_path):
        return None
    if Path(audio_path).suffix.lower() != ".wav":
        return None

    storage = Path(storage_root).expanduser().resolve()
    style_root = (storage / asset_root).resolve()
    audio = (style_root / audio_path).resolve()
    if not _is_within(style_root, storage) or not _is_within(audio, style_root):
        return None
    if not audio.is_file():
        return None
    try:
        size = audio.stat().st_size
        if size < 44 or size > MAX_AUDIO_BYTES:
            return None
        with wave.open(str(audio), "rb") as wav:
            channels = wav.getnchannels()
            sample_width = wav.getsampwidth()
            sample_rate = wav.getframerate()
            frames = wav.getnframes()
            if wav.getcomptype() != "NONE":
                return None
            if channels != 1 or sample_width != 2:
                return None
            if sample_rate < 8_000 or sample_rate > 96_000 or frames <= 0:
                return None
            duration = frames / float(sample_rate)
            if not MIN_DURATION_SECONDS <= duration <= MAX_DURATION_SECONDS:
                return None
            if len(wav.readframes(frames)) != frames * channels * sample_width:
                return None
    except (OSError, EOFError, wave.Error, ZeroDivisionError):
        return None
    return str(audio)


def _safe_relative(value: str) -> bool:
    if not isinstance(value, str) or not value or "\x00" in value or "\\" in value:
        return False
    path = Path(value)
    return not path.is_absolute() and all(part not in ("", ".", "..") for part in path.parts)


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False
