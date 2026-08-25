from __future__ import annotations

import base64
import binascii
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from config.config_loader import get_project_dir
from config.manage_api_client import ManageApiClient
from core.companion.session import CompanionSession
from core.providers.tts.dto.dto import ContentType, SentenceType, TTSMessageDTO


ASSET_URI_PREFIX = "asset://persona-signature/"
SAFE_ASSET_ID = re.compile(r"^[A-Za-z0-9_-]{8,80}$")
CONTENT_EXTENSIONS = {
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/wave": ".wav",
    "audio/vnd.wave": ".wav",
    "audio/mpeg": ".mp3",
    "audio/mp3": ".mp3",
    "audio/ogg": ".ogg",
}


# The source Persona may intentionally write a dramatic interruption such as
# ``怎么知——Ciallo``.  Once ``Ciallo`` is replaced by a separately recorded
# asset, the preceding TTS and the recording become two independent audio
# segments and the unfinished Chinese word sounds like a transport cut-off.
# Keep the authored/displayed response intact, but make the spoken lead-in a
# complete phrase at the exact boundary where a registered recording follows.
_SPOKEN_LEAD_IN_REWRITES = (
    (
        re.compile(r"怎么知(?P<pause>(?:[—–-]{1,3}|…{1,2}))\s*$"),
        r"怎么知道\g<pause>",
    ),
)


def _smooth_spoken_lead_in(value: str) -> str:
    """Complete a dangling spoken phrase immediately before fixed audio."""
    result = value
    for pattern, replacement in _SPOKEN_LEAD_IN_REWRITES:
        result = pattern.sub(replacement, result)
    return result


def render_signature_prompt(session: CompanionSession) -> str:
    """Render runtime-only routing instructions for imported and managed signatures."""
    signatures = getattr(session.persona_spec, "signature_utterances", None) or []
    lines = []
    for item in signatures[:12]:
        if not isinstance(item, dict):
            continue
        display = str(item.get("display_text") or "").strip()
        rule = str(item.get("semantic_rule") or "").strip()
        if not display or not rule:
            continue
        lines.append(
            f"- 招牌表达 {display!r}：{rule[:1000]}；只在语义条件明确满足时原样输出，"
            "不确定时不要使用，不要解释触发规则。"
            "如果先卖关子再说招牌表达，前导句必须是完整可朗读的短句；"
            "禁止用半个词硬接录音，例如应说‘你不说我怎么知道——’，"
            "不要说‘你不说我怎么知——’。"
        )
    if not lines:
        return ""
    return "\n".join(["<signature_utterance_rules>", *lines, "</signature_utterance_rules>"])


def _cache_root(config: dict[str, Any]) -> Path:
    configured = str((config.get("companion") or {}).get("signature_cache_dir") or "").strip()
    path = Path(configured or "data/companion/signature_assets").expanduser()
    if not path.is_absolute():
        path = Path(get_project_dir()) / path
    return path.resolve()


def _asset_uris(session: CompanionSession) -> list[str]:
    result = []
    for signature in session.persona_spec.signature_utterances or []:
        assets = signature.get("assets") if isinstance(signature, dict) else None
        if not isinstance(assets, dict):
            continue
        for uri in assets.values():
            uri = str(uri or "")
            if uri.startswith(ASSET_URI_PREFIX) and uri not in result:
                result.append(uri)
    return result


async def prefetch_signature_assets(
    session: CompanionSession,
    config: dict[str, Any],
    *,
    max_bytes: int = 5 * 1024 * 1024,
) -> int:
    """Resolve portable asset URIs and atomically populate the local audio cache."""
    if ManageApiClient._instance is None:
        return 0
    cache_root = _cache_root(config)
    cache_root.mkdir(parents=True, exist_ok=True)
    resolved: dict[str, str] = {}
    for uri in _asset_uris(session):
        asset_id = uri[len(ASSET_URI_PREFIX) :]
        if not SAFE_ASSET_ID.fullmatch(asset_id):
            continue
        payload = await ManageApiClient._instance._execute_async_request(
            "POST",
            "/config/companion/persona/signature-asset",
            json={
                "agentId": session.identity.agent_id,
                "personaId": session.identity.persona_id,
                "version": session.identity.persona_version,
                "assetId": asset_id,
            },
        )
        if not isinstance(payload, dict):
            continue
        encoded = str(payload.get("audioBase64") or "")
        try:
            audio = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error):
            continue
        if not audio or len(audio) > max_bytes:
            continue
        actual_hash = hashlib.sha256(audio).hexdigest()
        expected_hash = str(payload.get("sha256") or "").lower()
        if expected_hash and actual_hash != expected_hash:
            continue
        content_type = str(payload.get("contentType") or "").lower().split(";", 1)[0].strip()
        extension = CONTENT_EXTENSIONS.get(content_type, ".bin")
        target = cache_root / f"{asset_id}-{actual_hash[:12]}{extension}"
        if not target.exists() or target.stat().st_size != len(audio):
            temporary = target.with_suffix(target.suffix + ".tmp")
            temporary.write_bytes(audio)
            temporary.replace(target)
        resolved[uri] = str(target)
    session.signature_asset_files = resolved
    return len(resolved)


@dataclass(frozen=True)
class SpeechSegment:
    content_type: ContentType
    detail: str
    file: str | None = None


@dataclass(frozen=True)
class _Route:
    alias: str
    display_text: str
    file: str


class SignatureSpeechRouter:
    """Replace an LLM-emitted signature phrase with its registered recording.

    Matching happens on the generated response, not the user query. This leaves
    semantic trigger decisions with the Persona/LLM while making audio playback
    deterministic and independent of TTS provider capabilities.
    """

    def __init__(self, routes: list[_Route]):
        self.routes = sorted(routes, key=lambda item: len(item.alias), reverse=True)
        self.buffer = ""
        self.used: set[str] = set()
        self._tail = max((len(item.alias) for item in self.routes), default=0) + 1

    @classmethod
    def from_session(
        cls,
        session: CompanionSession | None,
        expression_plan: dict[str, Any] | None = None,
    ) -> "SignatureSpeechRouter":
        if session is None:
            return cls([])
        plan = expression_plan or {}
        provider_hint = plan.get("provider_hint") if isinstance(plan.get("provider_hint"), dict) else {}
        styles = [
            str(plan.get("primary_style") or ""),
            str(provider_hint.get("style") or ""),
            "neutral",
        ]
        routes = []
        for signature in session.persona_spec.signature_utterances or []:
            if not isinstance(signature, dict):
                continue
            assets = signature.get("assets")
            if not isinstance(assets, dict) or not assets:
                continue
            style_map = signature.get("style_map") if isinstance(signature.get("style_map"), dict) else {}
            variants = [str(style_map.get(style) or "") for style in styles if style]
            variants.extend(["classic", *[str(key) for key in assets]])
            uri = ""
            for variant in variants:
                candidate = str(assets.get(variant) or "")
                if candidate in session.signature_asset_files:
                    uri = candidate
                    break
            if not uri:
                continue
            display = str(signature.get("display_text") or "").strip()
            aliases = signature.get("explicit_aliases") or []
            if display:
                match = re.match(r"([A-Za-z][A-Za-z0-9._-]{1,40})", display)
                if match:
                    aliases = [match.group(1), *aliases]
            for alias in dict.fromkeys(str(value).strip() for value in aliases if str(value).strip()):
                routes.append(_Route(alias, display or alias, session.signature_asset_files[uri]))
        return cls(routes)

    def feed(self, text: str, *, final: bool = False) -> list[SpeechSegment]:
        if not self.routes:
            return [SpeechSegment(ContentType.TEXT, text)] if text else []
        self.buffer += text or ""
        output: list[SpeechSegment] = []
        while self.buffer:
            route, match = self._first_match(self.buffer)
            if route is None or match is None:
                if final:
                    output.append(SpeechSegment(ContentType.TEXT, self.buffer))
                    self.buffer = ""
                elif len(self.buffer) > self._tail:
                    cut = len(self.buffer) - self._tail
                    output.append(SpeechSegment(ContentType.TEXT, self.buffer[:cut]))
                    self.buffer = self.buffer[cut:]
                break
            if match.start() > 0:
                # This text is for speech only.  The original LLM response is
                # still stored in dialogue history by the caller.
                spoken_prefix = _smooth_spoken_lead_in(
                    self.buffer[: match.start()]
                )
                output.append(SpeechSegment(ContentType.TEXT, spoken_prefix))
                self.buffer = self.buffer[match.start() :]
                continue
            candidate = self.buffer
            display = route.display_text
            display_folded = display.casefold()
            candidate_folded = candidate.casefold()
            if len(candidate) < len(display) and display_folded.startswith(candidate_folded) and not final:
                break
            if candidate_folded.startswith(display_folded):
                consumed = len(display)
            elif not final and display_folded.startswith(candidate_folded):
                break
            else:
                consumed = len(route.alias)
            output.append(SpeechSegment(ContentType.FILE, display, route.file))
            self.used.add(route.alias.casefold())
            self.buffer = self.buffer[consumed:]
        return [segment for segment in output if segment.detail or segment.file]

    def flush(self) -> list[SpeechSegment]:
        return self.feed("", final=True)

    def _first_match(self, value: str):
        winner = (None, None)
        for route in self.routes:
            if route.alias.casefold() in self.used:
                continue
            match = re.search(
                rf"(?<![A-Za-z0-9]){re.escape(route.alias)}(?![A-Za-z0-9])",
                value,
                flags=re.IGNORECASE,
            )
            if match and (winner[1] is None or match.start() < winner[1].start()):
                winner = (route, match)
        return winner


def enqueue_speech_segments(
    tts,
    router: SignatureSpeechRouter,
    text: str,
    *,
    sentence_id: str,
    expression_plan: dict[str, Any] | None,
    turn_id: str | None,
    final: bool = False,
) -> int:
    segments = router.feed(text, final=final)
    for segment in segments:
        tts.tts_text_queue.put(
            TTSMessageDTO(
                sentence_id=sentence_id,
                sentence_type=SentenceType.MIDDLE,
                content_type=segment.content_type,
                content_detail=segment.detail,
                content_file=segment.file,
                expression_plan=expression_plan,
                turn_id=turn_id,
            )
        )
    return len(segments)
