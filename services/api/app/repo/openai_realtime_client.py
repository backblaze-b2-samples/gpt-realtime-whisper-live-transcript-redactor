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

# OpenAI Realtime requires 24kHz mono PCM16 input. The GA API expresses the
# format as a MIME-typed object (`{"type": "audio/pcm", "rate": 24000}`)
# rather than the beta-era `"pcm16"` string.
INPUT_SAMPLE_RATE = 24000
INPUT_FORMAT = "audio/pcm"


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
        self._ws: websockets.ClientConnection | None = None

    async def __aenter__(self) -> OpenAIRealtimeClient:
        if not settings.openai_api_key:
            raise RuntimeError(
                "OPENAI_API_KEY is not configured — realtime features disabled"
            )
        # GA transcription sessions connect with `intent=transcription` (no
        # speech-to-speech model in the query string — the transcription model
        # is set in the session payload below) and must NOT send the beta
        # `OpenAI-Beta: realtime=v1` header, which now triggers
        # `beta_api_shape_disabled`.
        url = f"{settings.openai_realtime_url}?intent=transcription"
        headers = {
            "Authorization": f"Bearer {settings.openai_api_key}",
            "User-Agent": "b2ai-gpt-realtime-whisper-live-transcript-redactor",
        }
        self._ws = await websockets.connect(url, additional_headers=headers)
        # Configure the session for transcription-only use. The GA shape nests
        # input config under `session.audio.input` and tags the session
        # `type: "transcription"`.
        #
        # NOTE: `gpt-realtime-whisper` does not support server-side turn
        # detection ("Turn detection is not supported for this transcription
        # model"), so we omit `turn_detection` and rely on explicit
        # `commit()` calls (the bridge commits on `stop`) to flush the input
        # buffer for transcription.
        await self._ws.send(
            json.dumps(
                {
                    "type": "session.update",
                    "session": {
                        "type": "transcription",
                        "audio": {
                            "input": {
                                "format": {
                                    "type": INPUT_FORMAT,
                                    "rate": INPUT_SAMPLE_RATE,
                                },
                                "transcription": {"model": self.model},
                            }
                        },
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

    A non-blocking HEAD on the configured REST endpoint is enough; the
    realtime WebSocket uses a separate URL, but both dependencies share
    the same API key and OpenAI REST base in proxied environments.
    Returns False on any error; never raises.
    """
    if not settings.openai_api_key:
        return False
    try:
        import httpx
    except ImportError:
        return False
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            api_base = settings.openai_api_base.rstrip("/")
            resp = await client.head(
                f"{api_base}/models",
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
