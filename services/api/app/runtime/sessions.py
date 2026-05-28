"""FastAPI routes for the sessions library + detail pages."""

import logging

from fastapi import APIRouter, HTTPException

from app.service.sessions import (
    SessionError,
    get_redacted_transcript,
    get_session,
    get_session_activity,
    get_session_stats,
    list_session_summaries,
    start_session,
)
from app.service.sessions import (
    delete_session as delete_session_svc,
)
from app.types import (
    DailySessionCount,
    SessionManifest,
    SessionStartRequest,
    SessionStartResponse,
    SessionStats,
    SessionSummary,
)
from app.types.transcripts import Transcript

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/sessions", response_model=SessionStartResponse)
async def create_session_endpoint(req: SessionStartRequest):
    try:
        return start_session(req)
    except SessionError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail) from None


@router.get("/sessions", response_model=list[SessionSummary])
async def list_sessions_endpoint(limit: int = 100):
    try:
        return list_session_summaries(limit=limit)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None


@router.get("/sessions/stats", response_model=SessionStats)
async def session_stats_endpoint():
    return get_session_stats()


@router.get("/sessions/stats/activity", response_model=list[DailySessionCount])
async def session_activity_endpoint(days: int = 7):
    if days < 1 or days > 90:
        raise HTTPException(status_code=400, detail="Days must be between 1 and 90")
    return get_session_activity(days=days)


@router.get("/sessions/{session_id}", response_model=SessionManifest)
async def get_session_endpoint(session_id: str):
    try:
        return get_session(session_id)
    except SessionError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail) from None


@router.get("/sessions/{session_id}/transcript", response_model=Transcript)
async def get_session_transcript_endpoint(session_id: str):
    try:
        return get_redacted_transcript(session_id)
    except SessionError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail) from None


@router.delete("/sessions/{session_id}")
async def delete_session_endpoint(session_id: str):
    try:
        deleted = delete_session_svc(session_id)
    except SessionError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail) from None
    logger.info("Session deleted: id=%s objects=%d", session_id, deleted)
    return {"deleted": True, "session_id": session_id, "objects_removed": deleted}
