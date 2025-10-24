from __future__ import annotations

import hashlib
import hmac
import secrets
from typing import Optional

from fastapi import HTTPException, Request, status

from .api_keys import ApiKeyStore
from .failures import FailureRegistry
from .auth import client_ip


def require_api_key(
    request: Request,
    store: ApiKeyStore,
    failures: FailureRegistry,
) -> None:
    ip = client_ip(request)
    if failures.is_locked(ip):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="API Key 已被临时锁定")

    header = request.headers.get("Authorization")
    stored_hash = store.get_hash()

    if not stored_hash:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="API Key 未配置")

    if not header or not header.startswith("Key "):
        failures.register_failure(ip)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="缺少 API Key")

    provided_key = header[4:].strip()
    if not provided_key:
        failures.register_failure(ip)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="无效的 API Key")

    provided_hash = hash_api_key(provided_key)
    if not hmac.compare_digest(provided_hash, stored_hash):
        failures.register_failure(ip)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="API Key 不正确")

    failures.reset(ip)


def get_api_key(store: ApiKeyStore) -> Optional[str]:
    return store.get_plain()


def set_api_key(store: ApiKeyStore, api_key: Optional[str], timestamp: str) -> str:
    new_key = api_key or secrets.token_urlsafe(32)
    hashed = hash_api_key(new_key)
    store.update(new_key, hashed, timestamp)
    return new_key


def delete_api_key(store: ApiKeyStore) -> None:
    store.clear()


def hash_api_key(api_key: str) -> str:
    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


__all__ = [
    "delete_api_key",
    "get_api_key",
    "hash_api_key",
    "require_api_key",
    "set_api_key",
]
