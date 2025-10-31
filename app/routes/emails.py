from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.accounts import account_service
from app.email import email_service
from app.models import DualViewEmailResponse, EmailDetailsResponse, EmailListResponse
from app.security import require_api_key

router = APIRouter(prefix="/emails", tags=["emails"])


@router.get("/{email_id}", response_model=EmailListResponse)
async def get_emails(
    email_id: str,
    folder: str = Query("all", regex="^(inbox|junk|all)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=500),
    refresh: bool = Query(False, description="强制刷新缓存"),
    _: None = Depends(require_api_key),
) -> EmailListResponse:
    credentials = account_service.get_credentials(email_id, require_active=True)
    return await email_service.list_emails(credentials, folder, page, page_size, refresh)


@router.get("/{email_id}/dual-view", response_model=DualViewEmailResponse)
async def get_dual_view_emails(
    email_id: str,
    inbox_page: int = Query(1, ge=1),
    junk_page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    _: None = Depends(require_api_key),
) -> DualViewEmailResponse:
    credentials = account_service.get_credentials(email_id, require_active=True)
    inbox_response = await email_service.list_emails(credentials, "inbox", inbox_page, page_size)
    junk_response = await email_service.list_emails(credentials, "junk", junk_page, page_size)
    return DualViewEmailResponse(
        email_id=email_id,
        inbox_emails=inbox_response.emails,
        junk_emails=junk_response.emails,
        inbox_total=inbox_response.total_emails,
        junk_total=junk_response.total_emails,
    )


@router.get("/{email_id}/{message_id}", response_model=EmailDetailsResponse)
async def get_email_detail(
    email_id: str,
    message_id: str,
    _: None = Depends(require_api_key),
) -> EmailDetailsResponse:
    credentials = account_service.get_credentials(email_id, require_active=True)
    return await email_service.get_email_details(credentials, message_id)
