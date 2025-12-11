from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.core.traffic_logger import traffic_logger

router = APIRouter(prefix="/api/traffic", tags=["traffic"])

@router.get("/stream")
async def stream_traffic():
    """
    Stream traffic logs in real-time using Server-Sent Events (SSE).
    """
    return StreamingResponse(
        traffic_logger.stream(),
        media_type="text/event-stream"
    )

@router.get("/history")
async def get_traffic_history(limit: int = 100):
    """
    Get recent traffic logs.
    """
    return traffic_logger.get_recent(limit)
