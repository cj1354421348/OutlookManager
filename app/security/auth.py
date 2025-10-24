from __future__ import annotations

from typing import Dict, Optional

from fastapi import HTTPException, Request, status

from app.config import APP_PASSWORD, APP_USERNAME, SESSION_COOKIE_NAME

from .failures import FailureRegistry
from .sessions import SessionStore


def require_session(store: SessionStore, request: Request) -> Dict[str, float]:
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    if not session_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录")

    session = store.get(session_id)
    if not session:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="会话无效")

    request.state.session = session
    return session


def login(
    store: SessionStore,
    failures: FailureRegistry,
    request: Request,
    username: str,
    password: str,
) -> str:
    ip = client_ip(request)
    if failures.is_locked(ip):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="登录已被临时锁定")

    if username != APP_USERNAME or password != APP_PASSWORD:
        failures.register_failure(ip)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")

    failures.reset(ip)
    return store.create(username)


def logout(store: SessionStore, session_id: Optional[str]) -> None:
    if session_id:
        store.remove(session_id)


def get_session(store: SessionStore, session_id: Optional[str]) -> Optional[Dict[str, float]]:
    if not session_id:
        return None
    return store.get(session_id)


def client_ip(request: Request) -> str:
    client = request.client
    return client.host if client else "unknown"


__all__ = [
    "client_ip",
    "get_session",
    "login",
    "logout",
    "require_session",
]
