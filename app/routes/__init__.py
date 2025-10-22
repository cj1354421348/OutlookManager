from __future__ import annotations

from fastapi import APIRouter

from . import accounts, auth, cache, emails, web

routers: list[APIRouter] = [
    auth.router,
    accounts.router,
    emails.router,
    cache.router,
    web.router,
]

__all__ = ["routers"]
