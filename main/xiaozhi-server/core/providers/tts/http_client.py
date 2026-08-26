import json
from dataclasses import dataclass
from typing import Mapping

import aiohttp


MAX_AUDIO_RESPONSE_BYTES = 32 * 1024 * 1024
MAX_JSON_RESPONSE_BYTES = 64 * 1024
MAX_ERROR_RESPONSE_BYTES = 8 * 1024


@dataclass(frozen=True)
class HttpAudioResponse:
    status_code: int
    content: bytes
    text: str
    headers: Mapping[str, str]


def client_timeout(seconds: float) -> aiohttp.ClientTimeout:
    return aiohttp.ClientTimeout(
        total=seconds,
        connect=min(10.0, seconds),
        sock_read=seconds,
    )


def validate_content_length(headers: Mapping[str, str], max_bytes: int) -> int | None:
    raw_length = headers.get("Content-Length")
    if raw_length is None:
        return None
    try:
        content_length = int(raw_length)
    except (TypeError, ValueError) as exc:
        raise ValueError("远端服务返回了无效的 Content-Length") from exc
    if content_length < 0:
        raise ValueError("远端服务返回了无效的 Content-Length")
    if content_length > max_bytes:
        raise ValueError(
            f"远端服务响应过大: {content_length} bytes，限制为 {max_bytes} bytes"
        )
    return content_length


async def read_bounded(response, max_bytes: int) -> bytes:
    validate_content_length(response.headers, max_bytes)
    content = bytearray()
    async for chunk in response.content.iter_chunked(min(65536, max_bytes + 1)):
        content.extend(chunk)
        if len(content) > max_bytes:
            response.close()
            raise ValueError(f"远端服务响应超过 {max_bytes} bytes 限制")
    return bytes(content)


def decode_response_body(response, content: bytes) -> str:
    charset = getattr(response, "charset", None) or "utf-8"
    try:
        return content.decode(charset, errors="replace")
    except LookupError:
        return content.decode("utf-8", errors="replace")


async def post_audio(
    url,
    payload,
    timeout,
    accept="audio/wav",
    max_bytes=MAX_AUDIO_RESPONSE_BYTES,
) -> HttpAudioResponse:
    async with aiohttp.ClientSession(timeout=client_timeout(timeout)) as session:
        async with session.post(
            url,
            json=payload,
            headers={"Accept": accept},
            allow_redirects=False,
        ) as response:
            response_limit = (
                max_bytes if response.status == 200 else MAX_ERROR_RESPONSE_BYTES
            )
            content = await read_bounded(response, response_limit)
            text = ""
            if response.status != 200:
                text = decode_response_body(response, content)
            return HttpAudioResponse(
                status_code=response.status,
                content=content,
                text=text,
                headers=dict(response.headers),
            )


async def get_json(url, timeout) -> tuple[int, dict]:
    async with aiohttp.ClientSession(timeout=client_timeout(timeout)) as session:
        async with session.get(
            url,
            headers={"Accept": "application/json"},
            allow_redirects=False,
        ) as response:
            try:
                content = await read_bounded(response, MAX_JSON_RESPONSE_BYTES)
                payload = json.loads(decode_response_body(response, content))
            except (UnicodeError, ValueError, json.JSONDecodeError):
                payload = {}
            return response.status, payload if isinstance(payload, dict) else {}
