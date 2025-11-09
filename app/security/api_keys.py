from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from app.config import SECURITY_FILE, logger


@dataclass
class SecurityState:
    api_key_plain: Optional[str] = None
    api_key_hash: Optional[str] = None
    updated_at: Optional[str] = None
    token_health_enabled: bool = True


class ApiKeyStore:
    def __init__(self, file_path: str = SECURITY_FILE) -> None:
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
                token_health_enabled=bool(data.get("token_health_enabled", True)),
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to load security configuration: %s", exc)

    def _persist(self) -> None:
        try:
            with self._path.open("w", encoding="utf-8") as fh:
                json.dump(self._state.__dict__, fh, indent=2, ensure_ascii=False)
        except Exception as exc:  # noqa: BLE001
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

    def token_health_enabled(self) -> bool:
        with self._lock:
            return bool(self._state.token_health_enabled)

    def set_token_health_enabled(self, enabled: bool) -> None:
        with self._lock:
            self._state.token_health_enabled = bool(enabled)
            self._persist()


__all__ = ["ApiKeyStore", "SecurityState"]
