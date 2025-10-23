from __future__ import annotations

from fastapi import Request

from .service import security_service


async def require_session(request: Request) -> dict[str, float]:
    return await security_service.require_session(request)


async def require_api_key(request: Request) -> None:
    await security_service.require_api_key(request)


async def require_authenticated_request(request: Request) -> dict[str, float]:
    return await security_service.require_authenticated_request(request)


__all__ = ["require_session", "require_api_key", "require_authenticated_request"]
