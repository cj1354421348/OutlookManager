from __future__ import annotations

import threading
import time
from typing import Any, Dict, Optional, Tuple

from app.config import CACHE_EXPIRE_TIME


class EmailCache:
    def __init__(self, expire_seconds: int = CACHE_EXPIRE_TIME) -> None:
        self._store: Dict[str, Tuple[Any, float]] = {}
        self._expire_seconds = expire_seconds
        self._lock = threading.Lock()

    def get(self, key: str, force_refresh: bool = False) -> Optional[Any]:
        if force_refresh:
            self.invalidate(key)
            return None

        with self._lock:
            cached = self._store.get(key)
            if not cached:
                return None
            data, timestamp = cached
            if time.time() - timestamp >= self._expire_seconds:
                self._store.pop(key, None)
                return None
            return data

    def set(self, key: str, data: Any) -> None:
        with self._lock:
            self._store[key] = (data, time.time())

    def invalidate(self, key: str) -> None:
        with self._lock:
            self._store.pop(key, None)

    def clear(self, prefix: Optional[str] = None) -> int:
        with self._lock:
            if prefix is None:
                count = len(self._store)
                self._store.clear()
                return count
            keys = [key for key in self._store if key.startswith(prefix)]
            for key in keys:
                self._store.pop(key, None)
            return len(keys)


email_cache = EmailCache()
