import asyncio

from fastapi import APIRouter

from app.repo import check_connectivity
from app.repo.openai_realtime_client import check_reachable as check_realtime_reachable
from app.repo.openai_redactor import check_reachable as check_redaction_reachable

router = APIRouter()


@router.get("/health")
async def health():
    b2_ok = check_connectivity()
    openai_realtime_ok, openai_redaction_ok = await asyncio.gather(
        check_realtime_reachable(),
        check_redaction_reachable(),
    )
    openai_ok = openai_realtime_ok and openai_redaction_ok
    healthy = b2_ok and openai_ok
    return {
        "status": "healthy" if healthy else "degraded",
        "b2_connected": b2_ok,
        "openai_reachable": openai_ok,
        "openai_realtime_reachable": openai_realtime_ok,
        "openai_redaction_reachable": openai_redaction_ok,
    }
