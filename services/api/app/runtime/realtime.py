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


async def _send_json(ws: WebSocket, payload: dict) -> None:
    """Best-effort send. The browser may have already disconnected — a
    closed socket must never crash the bridge (the trailing `finalized`
    notification and any late event are both non-critical for the client)."""
    with contextlib.suppress(Exception):
        await ws.send_text(json.dumps(payload))


async def _drain_openai_events(
    client: OpenAIRealtimeClient,
    state: RealtimeSessionState,
    ws: WebSocket,
    completed: asyncio.Event,
) -> None:
    """Pump typed events from OpenAI back to the browser.

    Completed segments are recorded into `state` (for persistence) even if
    the browser is gone; `completed` is set so the teardown path knows the
    final transcript has arrived after a `commit()`.
    """
    async for evt in client.iter_events():
        if isinstance(evt, TranscriptDelta):
            await _send_json(ws, {"type": "delta", "text": evt.text})
        elif isinstance(evt, TranscriptCompleted):
            # The state machine derives segment timing from the wall-clock
            # position of audio received so far (the transcription event
            # carries no per-segment duration).
            payload = await state.add_completed_segment(evt.text)
            await _send_json(ws, payload)
            completed.set()
        elif isinstance(evt, RealtimeError):
            logger.warning("Realtime upstream error: %s", evt.message)
            await _send_json(ws, {"type": "error", "message": evt.message})


@router.websocket("/ws/sessions/{session_id}")
async def realtime_ws(ws: WebSocket, session_id: str) -> None:
    await ws.accept()
    try:
        state = RealtimeSessionState(session_id)
    except SessionError as e:
        await ws.send_text(json.dumps({"type": "error", "message": e.detail}))
        await ws.close(code=1008)
        return

    client_connected = True
    errored = False
    completed = asyncio.Event()
    try:
        async with OpenAIRealtimeClient(model=state.manifest.model) as client:
            pump = asyncio.create_task(
                _drain_openai_events(client, state, ws, completed)
            )
            try:
                while True:
                    msg = await ws.receive()
                    if msg.get("type") == "websocket.disconnect":
                        client_connected = False
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
                            break
            finally:
                # `gpt-realtime-whisper` transcribes only on commit, so the
                # final utterance arrives *after* the receive loop exits. Flush
                # the buffer and wait for that completed event before tearing
                # the connection down — otherwise the transcript is lost. Done
                # even on an abrupt disconnect so the partial turn is salvaged.
                if state.manifest.audio_bytes_received > 0:
                    with contextlib.suppress(Exception):
                        await client.commit()
                        await asyncio.wait_for(completed.wait(), timeout=15)
                pump.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await pump
    except WebSocketDisconnect:
        client_connected = False
    except RuntimeError as e:
        # Most likely: OPENAI_API_KEY not set.
        await _send_json(ws, {"type": "error", "message": str(e)})
        state.mark_errored(str(e))
        with contextlib.suppress(Exception):
            await ws.close(code=1011)
        return
    except Exception as e:
        logger.exception("Realtime bridge crashed: %s", e)
        state.mark_errored(str(e))
        errored = True

    # Persist the redacted bundle + opt-in originals + manifest. Skip when the
    # session already failed — `finalize` would overwrite the `errored` status.
    if not errored:
        state.finalize(audio_extension="webm")
        if client_connected:
            await _send_json(
                ws,
                {
                    "type": "finalized",
                    "session_id": state.manifest.session_id,
                    "segment_count": state.manifest.segment_count,
                    "detection_count": state.manifest.detection_count,
                },
            )
    with contextlib.suppress(Exception):
        await ws.close()
