from __future__ import annotations

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import FileResponse, RedirectResponse

from app.config import SESSION_COOKIE_NAME
from app.services.security import require_api_key, security_service

router = APIRouter(tags=["web"])


@router.get("/")
async def root(request: Request):
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    if not session_id or not security_service.get_session(session_id):
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    return FileResponse("static/index.html")


@router.get("/login")
async def login_page(request: Request):
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    if session_id and security_service.get_session(session_id):
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    return FileResponse("static/login.html")


@router.get("/api")
async def api_status(
    _: None = Depends(require_api_key),
) -> dict[str, object]:
    return {
        "message": "Outlook邮件API服务正在运行",
        "version": "1.0.0",
        "endpoints": {
            "get_accounts": "GET /accounts",
            "register_account": "POST /accounts",
            "get_emails": "GET /emails/{email_id}?refresh=true",
            "get_dual_view_emails": "GET /emails/{email_id}/dual-view",
            "get_email_detail": "GET /emails/{email_id}/{message_id}",
            "clear_cache": "DELETE /emails/cache/{email_id}",
            "clear_all_cache": "DELETE /emails/cache",
        },
    }
