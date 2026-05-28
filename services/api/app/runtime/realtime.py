"""Realtime WebSocket bridge: browser PCM frames -> OpenAI Realtime -> UI.

The browser opens `/ws/sessions/{session_id}` after creating a session
via `POST /sessions`. We receive binary PCM16 chunks (24kHz mono) and
text control frames; we forward audio to OpenAI Realtime, run redaction
on each completed utterance, and stream JSON events back. Final
persistence (transcripts, redaction manifest, audio if opt-in) happens
on `stop` or on disconnect.

Structural-test boundary: WebSocket frame handling MUST live here, in
`runtime/`, not in `service/`. The service layer (`realtime_session.py`)
is a pure state machine with no network I/O.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.repo.openai_realtime_client import (
    OpenAIRealtimeClient,
    RealtimeError,
    TranscriptCompleted,
    TranscriptDelta,
)
from app.service.realtime_session import RealtimeSessionState
from app.service.sessions import SessionError

logger = logging.getLogger(__name__)

router = APIRouter()


async def _drain_openai_events(
    client: OpenAIRealtimeClient,
    state: RealtimeSessionState,
    ws: WebSocket,
) -> None:
    """Pump typed events from OpenAI back to the browser."""
    async for evt in client.iter_events():
        if isinstance(evt, TranscriptDelta):
            await ws.send_text(
                json.dumps({"type": "delta", "text": evt.text})
            )
        elif isinstance(evt, TranscriptCompleted):
            # Realtime API doesn't surface per-segment durations on the
            # transcription event; use a placeholder 0ms and let the
            # state machine track wall-clock duration via audio bytes.
            payload = state.add_completed_segment(evt.text, duration_ms=0)
            await ws.send_text(json.dumps(payload))
        elif isinstance(evt, RealtimeError):
            logger.warning("Realtime upstream error: %s", evt.message)
            await ws.send_text(
                json.dumps({"type": "error", "message": evt.message})
            )


@router.websocket("/ws/sessions/{session_id}")
async def realtime_ws(ws: WebSocket, session_id: str) -> None:
    await ws.accept()
    try:
        state = RealtimeSessionState(session_id)
    except SessionError as e:
        await ws.send_text(json.dumps({"type": "error", "message": e.detail}))
        await ws.close(code=1008)
        return

    try:
        async with OpenAIRealtimeClient(model=state.manifest.model) as client:
            pump = asyncio.create_task(_drain_openai_events(client, state, ws))
            try:
                while True:
                    msg = await ws.receive()
                    if msg.get("type") == "websocket.disconnect":
                        break
                    if "bytes" in msg and msg["bytes"] is not None:
                        chunk: bytes = msg["bytes"]
                        state.append_audio_chunk(chunk)
                        await client.send_audio(chunk)
                    elif "text" in msg and msg["text"] is not None:
                        try:
                            ctrl = json.loads(msg["text"])
                        except json.JSONDecodeError:
                            continue
                        if ctrl.get("type") == "stop":
                            await client.commit()
                            break
            finally:
                pump.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await pump
    except WebSocketDisconnect:
        pass
    except RuntimeError as e:
        # Most likely: OPENAI_API_KEY not set.
        await ws.send_text(json.dumps({"type": "error", "message": str(e)}))
        state.mark_errored(str(e))
        await ws.close(code=1011)
        return
    except Exception as e:
        logger.exception("Realtime bridge crashed: %s", e)
        state.mark_errored(str(e))

    # Persist redacted bundle + opt-in originals + manifest.
    state.finalize(audio_extension="webm")
    await ws.send_text(
        json.dumps(
            {
                "type": "finalized",
                "session_id": state.manifest.session_id,
                "segment_count": state.manifest.segment_count,
                "detection_count": state.manifest.detection_count,
            }
        )
    )
    with contextlib.suppress(Exception):
        await ws.close()
