"""OpenAI Realtime API wrapper — the only place that touches OpenAI.

We use `websockets` directly rather than the high-level Python SDK so the
sample stays slim (one async websocket dependency, no chain of
abstractions) and so swapping providers comes down to replacing this one
file. The session orchestrator (`service/realtime_session.py`) reads
typed events from `iter_events()` and never sees the raw protocol.
"""

from __future__ import annotations

import base64
import json
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass

import websockets

from app.config import settings

logger = logging.getLogger(__name__)

# OpenAI Realtime requires 24kHz mono PCM16 input.
INPUT_SAMPLE_RATE = 24000
INPUT_FORMAT = "pcm16"


@dataclass
class TranscriptDelta:
    """Incremental transcription chunk (not yet finalized)."""

    text: str


@dataclass
class TranscriptCompleted:
    """A finalized utterance — caller will run redaction and persist."""

    text: str


@dataclass
class RealtimeError:
    message: str


RealtimeEvent = TranscriptDelta | TranscriptCompleted | RealtimeError


class OpenAIRealtimeClient:
    """Minimal async wrapper around the OpenAI Realtime websocket.

    Usage:
        async with OpenAIRealtimeClient() as client:
            await client.send_audio(pcm16_bytes)
            async for evt in client.iter_events():
                ...
    """

    def __init__(self, model: str | None = None) -> None:
        self.model = model or settings.openai_realtime_model
        self._ws: websockets.WebSocketClientProtocol | None = None

    async def __aenter__(self) -> OpenAIRealtimeClient:
        if not settings.openai_api_key:
            raise RuntimeError(
                "OPENAI_API_KEY is not configured — realtime features disabled"
            )
        url = f"{settings.openai_realtime_url}?model={self.model}"
        headers = {
            "Authorization": f"Bearer {settings.openai_api_key}",
            "OpenAI-Beta": "realtime=v1",
            "User-Agent": "b2ai-gpt-realtime-whisper-live-transcript-redactor",
        }
        self._ws = await websockets.connect(url, extra_headers=headers)
        # Configure the session for transcription-only use.
        await self._ws.send(
            json.dumps(
                {
                    "type": "session.update",
                    "session": {
                        "modalities": ["text"],
                        "input_audio_format": INPUT_FORMAT,
                        "input_audio_transcription": {"model": self.model},
                        "turn_detection": {"type": "server_vad"},
                    },
                }
            )
        )
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._ws is not None:
            await self._ws.close()
            self._ws = None

    async def send_audio(self, pcm16: bytes) -> None:
        """Append a PCM16 chunk to the current input buffer."""
        if self._ws is None:
            raise RuntimeError("client is not connected")
        b64 = base64.b64encode(pcm16).decode("ascii")
        await self._ws.send(
            json.dumps({"type": "input_audio_buffer.append", "audio": b64})
        )

    async def commit(self) -> None:
        """Force a turn boundary (server VAD usually handles this)."""
        if self._ws is None:
            raise RuntimeError("client is not connected")
        await self._ws.send(json.dumps({"type": "input_audio_buffer.commit"}))

    async def iter_events(self) -> AsyncIterator[RealtimeEvent]:
        """Yield typed events translated from the OpenAI protocol."""
        if self._ws is None:
            raise RuntimeError("client is not connected")
        async for raw in self._ws:
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                logger.warning("Non-JSON message from OpenAI Realtime — skipped")
                continue
            mtype = msg.get("type", "")
            if mtype == "conversation.item.input_audio_transcription.delta":
                yield TranscriptDelta(text=msg.get("delta", ""))
            elif mtype == "conversation.item.input_audio_transcription.completed":
                yield TranscriptCompleted(text=msg.get("transcript", ""))
            elif mtype == "error":
                err = msg.get("error", {})
                yield RealtimeError(
                    message=err.get("message", "unknown realtime error")
                )


async def check_reachable() -> bool:
    """Cheap sanity check for the dashboard's AI-service health probe.

    A non-blocking HEAD on the public REST endpoint is enough — failing
    here means either no key, no network, or upstream outage. Returns
    False on any error; never raises.
    """
    if not settings.openai_api_key:
        return False
    try:
        import httpx
    except ImportError:
        return False
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.head(
                "https://api.openai.com/v1/models",
                headers={
                    "Authorization": f"Bearer {settings.openai_api_key}",
                    "User-Agent": (
                        "b2ai-gpt-realtime-whisper-live-transcript-redactor"
                    ),
                },
            )
        # 401 still counts as "reachable" — the service is up, the key is
        # just bad. That's a config problem we want surfaced separately.
        return resp.status_code < 500
    except Exception:
        return False
