from __future__ import annotations

import threading
import time
from collections import defaultdict
from dataclasses import dataclass

from app.config import LOCK_DURATION_SECONDS, LOCK_THRESHOLD, logger


@dataclass
class FailureEntry:
    count: int = 0
    locked_until: float = 0.0


class FailureRegistry:
    def __init__(self) -> None:
        self._store: dict[str, FailureEntry] = defaultdict(FailureEntry)
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


__all__ = ["FailureEntry", "FailureRegistry"]
