from __future__ import annotations

import hashlib
import hmac
import secrets
from typing import Any, Dict, Optional

from fastapi import HTTPException, Request, status

from app.config import (
    APP_PASSWORD,
    APP_USERNAME,
    SESSION_COOKIE_NAME,
    SESSION_COOKIE_SAMESITE,
    SESSION_COOKIE_SECURE,
    logger,
)

from .api_keys import ApiKeyStore
from .failures import FailureRegistry
from .sessions import SessionStore


class SecurityService:
    def __init__(self) -> None:
        self.sessions = SessionStore()
        self.login_failures = FailureRegistry()
        self.api_key_failures = FailureRegistry()
        self.api_key_store = ApiKeyStore()

    @staticmethod
    def _hash_api_key(api_key: str) -> str:
        return hashlib.sha256(api_key.encode("utf-8")).hexdigest()

    @staticmethod
    def _client_ip(request: Request) -> str:
        client = request.client
        return client.host if client else "unknown"

    async def require_session(self, request: Request) -> Dict[str, float]:
        session_id = request.cookies.get(SESSION_COOKIE_NAME)
        if not session_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未登录")

        session = self.sessions.get(session_id)
        if not session:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="会话无效")

        request.state.session = session
        return session

    async def require_api_key(self, request: Request) -> None:
        ip = self._client_ip(request)
        if self.api_key_failures.is_locked(ip):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="API Key 已被临时锁定")

        header = request.headers.get("Authorization")
        stored_hash = self.api_key_store.get_hash()

        if not stored_hash:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="API Key 未配置")

        if not header or not header.startswith("Key "):
            self.api_key_failures.register_failure(ip)
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="缺少 API Key")

        provided_key = header[4:].strip()
        if not provided_key:
            self.api_key_failures.register_failure(ip)
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="无效的 API Key")

        provided_hash = self._hash_api_key(provided_key)
        if not hmac.compare_digest(provided_hash, stored_hash):
            self.api_key_failures.register_failure(ip)
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="API Key 不正确")

        self.api_key_failures.reset(ip)

    async def require_authenticated_request(self, request: Request) -> Dict[str, float]:
        session = await self.require_session(request)
        await self.require_api_key(request)
        return session

    def login(self, request: Request, username: str, password: str) -> str:
        ip = self._client_ip(request)
        if self.login_failures.is_locked(ip):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="登录已被临时锁定")

        if username != APP_USERNAME or password != APP_PASSWORD:
            self.login_failures.register_failure(ip)
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")

        self.login_failures.reset(ip)
        return self.sessions.create(username)

    def logout(self, session_id: Optional[str]) -> None:
        if session_id:
            self.sessions.remove(session_id)

    def get_session(self, session_id: Optional[str]) -> Optional[Dict[str, float]]:
        if not session_id:
            return None
        return self.sessions.get(session_id)

    def get_security_stats(self) -> Dict[str, Any]:
        return {
            "failed_password_attempts": self.login_failures.total_failures(),
            "failed_api_key_attempts": self.api_key_failures.total_failures(),
            "locked_login_ips": self.login_failures.locked_ips(),
            "locked_api_key_ips": self.api_key_failures.locked_ips(),
        }

    def get_api_key(self) -> Optional[str]:
        return self.api_key_store.get_plain()

    def set_api_key(self, api_key: Optional[str], timestamp: str) -> str:
        new_key = api_key or secrets.token_urlsafe(32)
        hashed = self._hash_api_key(new_key)
        self.api_key_store.update(new_key, hashed, timestamp)
        return new_key

    def delete_api_key(self) -> None:
        self.api_key_store.clear()


security_service = SecurityService()

__all__ = ["SecurityService", "security_service"]
