from dataclasses import dataclass
from typing import Mapping

import aiohttp


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


async def post_audio(url, payload, timeout, accept="audio/wav") -> HttpAudioResponse:
    async with aiohttp.ClientSession(timeout=client_timeout(timeout)) as session:
        async with session.post(
            url,
            json=payload,
            headers={"Accept": accept},
        ) as response:
            content = await response.read()
            text = ""
            if response.status >= 400:
                charset = response.charset or "utf-8"
                try:
                    text = content.decode(charset, errors="replace")
                except LookupError:
                    text = content.decode("utf-8", errors="replace")
            return HttpAudioResponse(
                status_code=response.status,
                content=content,
                text=text,
                headers=dict(response.headers),
            )


async def get_json(url, timeout) -> tuple[int, dict]:
    async with aiohttp.ClientSession(timeout=client_timeout(timeout)) as session:
        async with session.get(url, headers={"Accept": "application/json"}) as response:
            try:
                payload = await response.json(content_type=None)
            except (aiohttp.ContentTypeError, ValueError):
                payload = {}
            return response.status, payload if isinstance(payload, dict) else {}
