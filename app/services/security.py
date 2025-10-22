from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import HTTPException, Request, status

from app.config import (
    APP_PASSWORD,
    APP_USERNAME,
    LOCK_DURATION_SECONDS,
    LOCK_THRESHOLD,
    SECURITY_FILE,
    SESSION_COOKIE_NAME,
    SESSION_COOKIE_SAMESITE,
    SESSION_COOKIE_SECURE,
    logger,
)


@dataclass
class FailureEntry:
    count: int = 0
    locked_until: float = 0.0


class FailureRegistry:
    def __init__(self) -> None:
        self._store: Dict[str, FailureEntry] = defaultdict(FailureEntry)
        self._lock = threading.Lock()
        self._total_failures = 0

    def register_failure(self, ip: str) -> None:
        with self._lock:
            entry = self._store[ip]
            entry.count += 1
            self._total_failures += 1
            if entry.count >= LOCK_THRESHOLD:
                entry.locked_until = time.time() + LOCK_DURATION_SECONDS
                logger.warning("IP %s locked for %s seconds", ip, LOCK_DURATION_SECONDS)

    def reset(self, ip: str) -> None:
        with self._lock:
            if ip in self._store:
                self._store[ip] = FailureEntry()

    def is_locked(self, ip: str) -> bool:
        with self._lock:
            entry = self._store.get(ip)
            if not entry:
                return False
            if entry.locked_until > time.time():
                return True
            if entry.locked_until and entry.locked_until <= time.time():
                self._store[ip] = FailureEntry()
            return False

    def locked_ips(self) -> list[str]:
        with self._lock:
            now = time.time()
            return [ip for ip, entry in self._store.items() if entry.locked_until > now]

    def total_failures(self) -> int:
        with self._lock:
            return self._total_failures


class SessionStore:
    def __init__(self) -> None:
        self._sessions: Dict[str, Dict[str, float]] = {}
        self._lock = threading.Lock()

    def create(self, username: str) -> str:
        session_id = secrets.token_urlsafe(32)
        now = time.time()
        with self._lock:
            self._sessions[session_id] = {
                "username": username,
                "created_at": now,
                "last_active": now,
            }
        return session_id

    def get(self, session_id: str) -> Optional[Dict[str, float]]:
        with self._lock:
            session = self._sessions.get(session_id)
            if session:
                session["last_active"] = time.time()
            return session

    def remove(self, session_id: str) -> None:
        with self._lock:
            self._sessions.pop(session_id, None)


@dataclass
class SecurityState:
    api_key_plain: Optional[str] = None
    api_key_hash: Optional[str] = None
    updated_at: Optional[str] = None


class ApiKeyStore:
    def __init__(self, file_path: str) -> None:
        self._path = Path(file_path)
        self._lock = threading.Lock()
        self._state = SecurityState()
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            with self._path.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
            self._state = SecurityState(
                api_key_plain=data.get("api_key_plain"),
                api_key_hash=data.get("api_key_hash"),
                updated_at=data.get("updated_at"),
            )
        except Exception as exc:
            logger.error("Failed to load security configuration: %s", exc)

    def _persist(self) -> None:
        try:
            with self._path.open("w", encoding="utf-8") as fh:
                json.dump(self._state.__dict__, fh, indent=2, ensure_ascii=False)
        except Exception as exc:
            logger.error("Failed to persist security configuration: %s", exc)

    def get_plain(self) -> Optional[str]:
        with self._lock:
            return self._state.api_key_plain

    def get_hash(self) -> Optional[str]:
        with self._lock:
            return self._state.api_key_hash

    def update(self, plain_key: Optional[str], hashed_key: Optional[str], updated_at: Optional[str]) -> None:
        with self._lock:
            self._state.api_key_plain = plain_key
            self._state.api_key_hash = hashed_key
            self._state.updated_at = updated_at
            self._persist()

    def clear(self) -> None:
        self.update(None, None, None)


class SecurityService:
    def __init__(self) -> None:
        self.sessions = SessionStore()
        self.login_failures = FailureRegistry()
        self.api_key_failures = FailureRegistry()
        self.api_key_store = ApiKeyStore(SECURITY_FILE)

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


async def require_session(request: Request) -> Dict[str, float]:
    return await security_service.require_session(request)


async def require_api_key(request: Request) -> None:
    await security_service.require_api_key(request)


async def require_authenticated_request(request: Request) -> Dict[str, float]:
    return await security_service.require_authenticated_request(request)
