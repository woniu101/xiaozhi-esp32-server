from __future__ import annotations

import asyncio
import base64
import binascii
import os
import queue
import threading
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response, StreamingResponse

from .runtime import SAMPLE_RATE, IndexRuntime
from .schemas import TTSRequest, VoiceRegistrationRequest
from .voice_registry import VoiceRegistry


ROOT_DIR = Path(__file__).resolve().parent.parent
REGISTRY = VoiceRegistry(ROOT_DIR, ROOT_DIR / "voices" / "voices.json")
RUNTIME = IndexRuntime(ROOT_DIR)
MAX_PENDING = max(1, int(os.getenv("INDEXTTS_MAX_PENDING", "4")))
QUEUE_WAIT_SECONDS = max(0.1, float(os.getenv("INDEXTTS_QUEUE_WAIT_SECONDS", "10")))
MAX_VOICE_AUDIO_BYTES = max(1, int(os.getenv("INDEXTTS_MAX_VOICE_AUDIO_MB", "20"))) * 1024 * 1024
SLOTS = asyncio.Semaphore(MAX_PENDING)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await asyncio.to_thread(RUNTIME.load)
    yield


app = FastAPI(
    title="IndexTTS2.5 Companion API",
    version="1.1.0",
    lifespan=lifespan,
)


async def acquire_slot() -> None:
    try:
        await asyncio.wait_for(SLOTS.acquire(), timeout=QUEUE_WAIT_SECONDS)
    except TimeoutError as exc:
        raise HTTPException(status_code=503, detail="inference queue is full") from exc


def resolve_voice(request: TTSRequest):
    try:
        return REGISTRY.resolve(request.voice_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/health/live")
async def health_live() -> dict[str, object]:
    return {"status": "live", "service": "indextts2.5"}


@app.get("/health/ready")
async def health_ready() -> dict[str, object]:
    status = RUNTIME.status()
    if not RUNTIME.ready:
        raise HTTPException(status_code=503, detail=status)
    return {"status": "ready", **status}


@app.get("/v1/capabilities")
async def capabilities() -> dict[str, object]:
    return {
        "model": "IndexTTS-2.5",
        "sample_rate": SAMPLE_RATE,
        "audio": {"non_stream": "wav_s16le_mono", "stream": "pcm_s16le_mono"},
        "streaming": {"supported": True, "mode": "segment"},
        "voice_management": {
            "supported": True,
            "register": "POST /v1/voices",
            "delete": "DELETE /v1/voices/{voice_id}",
            "max_audio_bytes": MAX_VOICE_AUDIO_BYTES,
        },
        "emotion": {
            "type": "vector",
            "dimensions": [
                "happy",
                "angry",
                "sad",
                "afraid",
                "disgusted",
                "melancholic",
                "surprised",
                "calm",
            ],
            "alpha": {"min": 0.0, "max": 1.0},
        },
        "limits": {"max_text_length": 300, "max_pending_requests": MAX_PENDING},
    }


@app.get("/v1/voices")
async def voices() -> dict[str, object]:
    return {"default_voice_id": REGISTRY.default_voice_id, "voices": REGISTRY.list_public()}


@app.post("/v1/voices", status_code=201)
async def register_voice(request: VoiceRegistrationRequest) -> dict[str, object]:
    try:
        audio = base64.b64decode(request.audio_base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(status_code=422, detail="audio_base64 is invalid") from exc
    if len(audio) > MAX_VOICE_AUDIO_BYTES:
        raise HTTPException(status_code=413, detail="prompt audio is too large")
    try:
        voice = await asyncio.to_thread(
            REGISTRY.register,
            request.voice_id,
            request.name,
            request.languages,
            request.prompt_text,
            audio,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"voice": voice}


@app.delete("/v1/voices/{voice_id}")
async def delete_voice(voice_id: str) -> dict[str, object]:
    try:
        await asyncio.to_thread(REGISTRY.delete, voice_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"deleted": voice_id}


@app.post("/v1/tts")
async def synthesize(request: TTSRequest) -> Response:
    voice = resolve_voice(request)
    request_id = request.request_id or str(uuid.uuid4())
    await acquire_slot()
    try:
        wav, metrics = await asyncio.to_thread(RUNTIME.infer_wav, request, voice)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"inference failed: {type(exc).__name__}: {exc}") from exc
    finally:
        SLOTS.release()
    return Response(
        content=wav,
        media_type="audio/wav",
        headers={
            "X-Request-ID": request_id,
            "X-Voice-ID": voice.voice_id,
            "X-Sample-Rate": str(metrics["sample_rate"]),
            "X-Audio-Seconds": str(metrics["audio_seconds"]),
            "X-Inference-Seconds": str(metrics["inference_seconds"]),
            "X-RTF": str(metrics["rtf"]),
        },
    )


@app.post("/v1/tts/stream")
async def synthesize_stream(request: TTSRequest) -> StreamingResponse:
    voice = resolve_voice(request)
    request_id = request.request_id or str(uuid.uuid4())
    await acquire_slot()

    async def body() -> AsyncIterator[bytes]:
        items: queue.Queue[tuple[str, object]] = queue.Queue(maxsize=4)
        stopped = threading.Event()

        def put(kind: str, value: object) -> bool:
            while not stopped.is_set():
                try:
                    items.put((kind, value), timeout=0.2)
                    return True
                except queue.Full:
                    continue
            return False

        def producer() -> None:
            try:
                for chunk in RUNTIME.infer_pcm_chunks(request, voice):
                    if not put("data", chunk):
                        return
            except Exception as exc:
                put("error", exc)
            finally:
                put("done", None)

        thread = threading.Thread(target=producer, name=f"tts-{request_id}", daemon=True)
        thread.start()
        try:
            while True:
                kind, value = await asyncio.to_thread(items.get)
                if kind == "data":
                    yield value
                elif kind == "error":
                    raise value
                else:
                    break
        finally:
            stopped.set()
            SLOTS.release()

    return StreamingResponse(
        body(),
        media_type="application/octet-stream",
        headers={
            "X-Request-ID": request_id,
            "X-Voice-ID": voice.voice_id,
            "X-Sample-Rate": str(SAMPLE_RATE),
            "X-Audio-Format": "pcm_s16le_mono",
            "X-Streaming-Mode": "segment",
        },
    )
