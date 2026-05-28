from fastapi import APIRouter

from app.repo import check_connectivity
from app.repo.openai_realtime_client import check_reachable

router = APIRouter()


@router.get("/health")
async def health():
    b2_ok = check_connectivity()
    openai_ok = await check_reachable()
    healthy = b2_ok and openai_ok
    return {
        "status": "healthy" if healthy else "degraded",
        "b2_connected": b2_ok,
        "openai_reachable": openai_ok,
    }
