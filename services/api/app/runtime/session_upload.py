"""File-mode pipeline ingest: `POST /sessions/upload`.

The user drops an audio file on `/upload` and we stream it through the
exact same realtime pipeline `/record` uses — `OpenAIRealtimeClient`
for upstream transcription, `RealtimeSessionState` for the redaction
state machine, the same B2 session-bundle layout, the same audit-trail
events. The handler is synchronous from the caller's POV: it returns
when the upload finishes and the session is finalized, then the
frontend redirects to `/sessions/[id]`.

v1 accepts WAV only — see `service/audio_decode.py` for the rationale
and the v2 expansion path.

Layering: `runtime/` owns the HTTP boundary + the OpenAI streaming
coroutine. Decoding lives in `service/audio_decode.py`, transcript +
redaction state lives in `service/realtime_session.py`, the OpenAI
client itself lives in `repo/openai_realtime_client.py`.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging

from fastapi import APIRouter, HTTPException, Request, UploadFile
from pydantic import BaseModel

from app.config import settings
from app.repo import b2_sessions
from app.repo.openai_realtime_client import (
    OpenAIRealtimeClient,
    RealtimeError,
    TranscriptCompleted,
    TranscriptDelta,
)
from app.service.audio_decode import (
    AudioDecodeError,
    decode_to_pcm16_24khz_mono,
    iter_frames,
)
from app.service.realtime_session import RealtimeSessionState
from app.service.sessions import SessionError, start_session
from app.types.sessions import SessionStartRequest

logger = logging.getLogger(__name__)

router = APIRouter()

# Pace upstream sends so we don't blast the OpenAI socket faster than it
# can VAD. ~100 ms of audio per frame; sleep ~50 ms between sends. Net
# effect: a 30 s file uploads in ~15 s wall time, fast enough for an
# interactive request but slow enough to leave headroom for transcript
# deltas to land.
INTER_FRAME_SLEEP_S = 0.05

# Cap the post-commit drain so a hanging upstream doesn't pin the
# request forever. Realtime transcription usually finalizes within a
# couple of seconds of `commit` once VAD closes the last turn.
POST_COMMIT_DRAIN_TIMEOUT_S = 30.0


class SessionUploadResponse(BaseModel):
    session_id: str
    segment_count: int
    detection_count: int
    duration_ms_received: int


async def _drain_until_completed(
    client: OpenAIRealtimeClient,
    state: RealtimeSessionState,
) -> None:
    """Consume upstream events; populate state until the buffer drains.

    The file-mode path does not have a long-lived caller listening for
    deltas — we ignore `TranscriptDelta`s here and only mutate state on
    `TranscriptCompleted`. This matches `/record`'s behavior: deltas are
    a UI nicety; durable persistence happens on segment completion.
    """
    async for evt in client.iter_events():
        if isinstance(evt, TranscriptDelta):
            continue
        if isinstance(evt, TranscriptCompleted):
            state.add_completed_segment(evt.text, duration_ms=0)
        elif isinstance(evt, RealtimeError):
            logger.warning("Realtime upstream error during /sessions/upload: %s", evt.message)


@router.post("/sessions/upload", response_model=SessionUploadResponse)
async def upload_session_audio(
    request: Request,
    file: UploadFile,
) -> SessionUploadResponse:
    if not settings.openai_api_key:
        raise HTTPException(
            status_code=503,
            detail=(
                "OPENAI_API_KEY is not configured — realtime features disabled. "
                "Add it to .env and restart the API."
            ),
        )

    # Read with the same chunked size guard the legacy /upload route uses.
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > settings.max_file_size:
            raise HTTPException(status_code=413, detail="File too large")
        chunks.append(chunk)
    file_data = b"".join(chunks)

    content_type = file.content_type or "application/octet-stream"
    try:
        decoded = decode_to_pcm16_24khz_mono(file_data, content_type)
    except AudioDecodeError as e:
        logger.info("Pipeline-mode upload rejected: %s", e.detail)
        raise HTTPException(status_code=e.status_code, detail=e.detail) from None

    # Create a fresh session with the env defaults — the file-mode upload
    # currently exposes no per-session toggles (the dropzone is the
    # entire UI). Operators tighten this via SESSION_STORE_ORIGINALS_DEFAULT.
    try:
        created = start_session(SessionStartRequest())
        state = RealtimeSessionState(created.session_id)
    except SessionError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail) from None

    # We persist the originally-uploaded WAV (playable file) rather than
    # the in-memory resampled PCM. Override the per-state buffering so
    # `append_audio_chunk` still updates byte counters + emits
    # `audio.received` audit events but does not balloon memory.
    persist_audio = state.manifest.store_original_audio
    state.manifest.store_original_audio = False

    pump_failed: dict[str, str] = {}

    try:
        async with OpenAIRealtimeClient(model=state.manifest.model) as client:
            async def _pump() -> None:
                try:
                    await _drain_until_completed(client, state)
                except Exception as e:
                    pump_failed["message"] = str(e)
                    logger.exception("Realtime drain failed: %s", e)

            pump = asyncio.create_task(_pump())
            try:
                for frame in iter_frames(decoded.pcm16):
                    state.append_audio_chunk(frame)
                    await client.send_audio(frame)
                    if INTER_FRAME_SLEEP_S > 0:
                        await asyncio.sleep(INTER_FRAME_SLEEP_S)
                await client.commit()
                # Give the upstream a bounded window to finalize the last
                # segment. The drain coroutine returns when the OpenAI
                # socket closes on async-with exit; we don't wait for
                # that — POST_COMMIT_DRAIN_TIMEOUT_S is enough for the
                # transcription.completed event.
                deadline = (
                    asyncio.get_event_loop().time() + POST_COMMIT_DRAIN_TIMEOUT_S
                )
                while asyncio.get_event_loop().time() < deadline:
                    if pump.done():
                        break
                    await asyncio.sleep(0.1)
            finally:
                pump.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await pump
    except RuntimeError as e:
        # Upstream auth / network — surface clearly so the UI shows the
        # right error.
        state.mark_errored(str(e))
        raise HTTPException(status_code=502, detail=str(e)) from None
    except Exception as e:
        logger.exception("Pipeline-mode upload crashed: %s", e)
        state.mark_errored(str(e))
        raise HTTPException(
            status_code=500, detail="Realtime ingest failed"
        ) from None

    # Restore the requested audio-storage flag and write the original WAV
    # (the playable file the user uploaded) directly to B2 if opted in.
    state.manifest.store_original_audio = persist_audio
    if persist_audio:
        try:
            b2_sessions.put_audio(state.manifest.session_id, "wav", file_data)
            state.manifest.audio_extension = "wav"
        except RuntimeError as e:
            logger.warning("Could not persist original WAV: %s", e)
    state.finalize(audio_extension=None)

    if pump_failed:
        logger.warning(
            "Pipeline-mode upload finished with drain error: %s",
            pump_failed["message"],
        )

    return SessionUploadResponse(
        session_id=state.manifest.session_id,
        segment_count=state.manifest.segment_count,
        detection_count=state.manifest.detection_count,
        duration_ms_received=decoded.duration_ms,
    )
