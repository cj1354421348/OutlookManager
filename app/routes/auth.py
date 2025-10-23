from __future__ import annotations

from datetime import datetime
from typing import Dict

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.config import SESSION_COOKIE_NAME, SESSION_COOKIE_SAMESITE, SESSION_COOKIE_SECURE
from app.models import ApiKeyRequest, LoginRequest
from app.security import require_session, security_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login")
async def login(request: Request, payload: LoginRequest) -> JSONResponse:
    session_id = security_service.login(request, payload.username, payload.password)
    response = JSONResponse({"message": "登录成功"})
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_id,
        httponly=True,
        secure=SESSION_COOKIE_SECURE,
        samesite=SESSION_COOKIE_SAMESITE,
        path="/",
    )
    return response


@router.post("/logout")
async def logout(request: Request, session: Dict[str, float] = Depends(require_session)) -> JSONResponse:
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    security_service.logout(session_id)
    response = JSONResponse({"message": "已退出"})
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    return response


@router.get("/session")
async def get_session_info(session: Dict[str, float] = Depends(require_session)) -> Dict[str, str]:
    return {"username": session.get("username", "")}


@router.get("/security-stats")
async def security_stats(session: Dict[str, float] = Depends(require_session)) -> Dict[str, object]:
    return security_service.get_security_stats()


@router.get("/api-key")
async def get_api_key(session: Dict[str, float] = Depends(require_session)) -> Dict[str, str | None]:
    return {"api_key": security_service.get_api_key()}


@router.post("/api-key")
async def set_api_key(
    payload: ApiKeyRequest,
    session: Dict[str, float] = Depends(require_session),
) -> Dict[str, str]:
    new_key = security_service.set_api_key(payload.api_key, datetime.utcnow().isoformat())
    return {"api_key": new_key}


@router.delete("/api-key")
async def delete_api_key(session: Dict[str, float] = Depends(require_session)) -> Dict[str, None]:
    security_service.delete_api_key()
    return {"api_key": None}