from __future__ import annotations

import secrets
import threading
import time
from typing import Dict, Optional


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


__all__ = ["SessionStore"]
