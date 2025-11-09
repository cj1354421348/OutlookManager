from __future__ import annotations

from datetime import datetime
from typing import Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse

from app.config import SESSION_COOKIE_NAME, SESSION_COOKIE_SAMESITE, SESSION_COOKIE_SECURE
from app.models import ApiKeyRequest, LoginRequest, TokenHealthSettings
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


@router.get("/token-health", response_model=TokenHealthSettings)
async def get_token_health_settings(request: Request, session: Dict[str, float] = Depends(require_session)) -> TokenHealthSettings:
    return TokenHealthSettings(
        enabled=security_service.is_token_health_enabled(),
        interval_minutes=security_service.get_token_health_interval(),
    )


@router.post("/token-health", response_model=TokenHealthSettings)
async def set_token_health_settings(
    request: Request,
    payload: TokenHealthSettings,
    session: Dict[str, float] = Depends(require_session),
) -> TokenHealthSettings:
    enabled = security_service.set_token_health_enabled(payload.enabled)
    interval = security_service.set_token_health_interval(payload.interval_minutes)
    scheduler = getattr(request.app.state, "token_health_scheduler", None)
    if scheduler:
        scheduler.trigger_immediate()
    return TokenHealthSettings(enabled=enabled, interval_minutes=interval)


@router.post("/token-health/run-now")
async def trigger_token_health_run(request: Request, session: Dict[str, float] = Depends(require_session)) -> Dict[str, Any]:
    scheduler = getattr(request.app.state, "token_health_scheduler", None)
    if not scheduler:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Scheduler not initialized")
    scheduler.trigger_immediate()
    status_payload = scheduler.status()
    return {
        "message": "Token health check triggered",
        "running": status_payload.running,
        "last_started_at": status_payload.last_started_at,
        "last_completed_at": status_payload.last_completed_at,
    }


@router.get("/token-health/status")
async def get_token_health_status(request: Request, session: Dict[str, float] = Depends(require_session)) -> Dict[str, Any]:
    scheduler = getattr(request.app.state, "token_health_scheduler", None)
    if not scheduler:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Scheduler not initialized")
    status_payload = scheduler.status()
    result = status_payload.last_result
    return {
        "running": status_payload.running,
        "last_started_at": status_payload.last_started_at,
        "last_completed_at": status_payload.last_completed_at,
        "last_result": {
            "total": result.total if result else 0,
            "success": result.success if result else 0,
            "failures": result.failures if result else 0,
            "newly_expired": result.newly_expired if result else 0,
        }
        if result
        else None,
    }
