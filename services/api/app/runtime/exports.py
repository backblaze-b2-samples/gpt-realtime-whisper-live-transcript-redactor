"""Export endpoints — generate redacted TXT / SRT / VTT for a session."""

import logging

from fastapi import APIRouter, HTTPException

from app.service.exports import generate_export
from app.service.sessions import SessionError
from app.types import ExportInfo, ExportRequest

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/sessions/{session_id}/exports", response_model=ExportInfo)
async def create_export_endpoint(session_id: str, req: ExportRequest):
    try:
        info = generate_export(session_id, req.format)
    except SessionError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail) from None
    logger.info(
        "Export generated: session=%s format=%s size=%d",
        session_id,
        req.format,
        info.size_bytes,
    )
    return info
