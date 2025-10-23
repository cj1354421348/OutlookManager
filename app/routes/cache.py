from __future__ import annotations

from fastapi import APIRouter, Depends

from app.email import email_service
from app.security import require_api_key

router = APIRouter(prefix="/cache", tags=["cache"])


@router.delete("/{email_id}")
async def clear_cache(
    email_id: str,
    _: None = Depends(require_api_key),
) -> dict[str, object]:
    cleared = email_service.clear_cache(email_id)
    return {"message": f"Cache cleared for {email_id}", "cleared": cleared}


@router.delete("")
async def clear_all_cache(
    _: None = Depends(require_api_key),
) -> dict[str, object]:
    cleared = email_service.clear_cache()
    return {"message": "All cache cleared", "cleared": cleared}
