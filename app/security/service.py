from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import Request

from .api_guard import delete_api_key, get_api_key, require_api_key, set_api_key
from .api_keys import ApiKeyStore
from .auth import get_session, login, logout, require_session
from .failures import FailureRegistry
from .sessions import SessionStore
from .stats import build_security_stats


class SecurityService:
    def __init__(self) -> None:
        self.sessions = SessionStore()
        self.login_failures = FailureRegistry()
        self.api_key_failures = FailureRegistry()
        self.api_key_store = ApiKeyStore()

    async def require_session(self, request: Request) -> Dict[str, float]:
        return require_session(self.sessions, request)

    async def require_api_key(self, request: Request) -> None:
        require_api_key(request, self.api_key_store, self.api_key_failures)

    async def require_authenticated_request(self, request: Request) -> Dict[str, float]:
        session = await self.require_session(request)
        await self.require_api_key(request)
        return session

    def login(self, request: Request, username: str, password: str) -> str:
        return login(self.sessions, self.login_failures, request, username, password)

    def logout(self, session_id: Optional[str]) -> None:
        logout(self.sessions, session_id)

    def get_session(self, session_id: Optional[str]) -> Optional[Dict[str, float]]:
        return get_session(self.sessions, session_id)

    def get_security_stats(self) -> Dict[str, Any]:
        return build_security_stats(self.login_failures, self.api_key_failures)

    def get_api_key(self) -> Optional[str]:
        return get_api_key(self.api_key_store)

    def set_api_key(self, api_key: Optional[str], timestamp: str) -> str:
        return set_api_key(self.api_key_store, api_key, timestamp)

    def delete_api_key(self) -> None:
        delete_api_key(self.api_key_store)

    def is_token_health_enabled(self) -> bool:
        return self.api_key_store.token_health_enabled()

    def set_token_health_enabled(self, enabled: bool) -> bool:
        self.api_key_store.set_token_health_enabled(enabled)
        return enabled

    def get_token_health_interval(self) -> int:
        return self.api_key_store.get_token_health_interval()

    def set_token_health_interval(self, minutes: int) -> int:
        return self.api_key_store.set_token_health_interval(minutes)


security_service = SecurityService()

__all__ = ["SecurityService", "security_service"]
