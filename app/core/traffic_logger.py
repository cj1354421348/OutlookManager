import asyncio
import collections
import dataclasses
import datetime
import json
import logging
import uuid
from typing import Deque, List, Optional, Set

from starlette.concurrency import run_in_threadpool

# Initialize module-level logger
logger = logging.getLogger(__name__)

@dataclasses.dataclass
class TrafficLogEntry:
    id: str
    timestamp: str
    protocol: str  # "IMAP" or "HTTP"
    account: str
    action: str
    status: str  # "OK", "ERROR", "PENDING"
    duration_ms: float
    details: str

    def to_json(self) -> str:
        return json.dumps(dataclasses.asdict(self))

class TrafficLogger:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.initialized = False
        return cls._instance

    def __init__(self):
        if self.initialized:
            return
        self.history: Deque[TrafficLogEntry] = collections.deque(maxlen=500)
        self.listeners: Set[asyncio.Queue] = set()
        self.initialized = True
        logger.info("TrafficLogger initialized")

    def log(self, protocol: str, account: str, action: str, 
            status: str, duration_ms: float, details: str = "") -> TrafficLogEntry:
        from app.core.time_utils import now
        entry = TrafficLogEntry(
            id=str(uuid.uuid4()),
            timestamp=now().isoformat(),
            protocol=protocol,
            account=account,
            action=action,
            status=status,
            duration_ms=round(duration_ms, 2),
            details=details
        )
        
        self.history.appendleft(entry)
        self._broadcast(entry)
        return entry

    def _broadcast(self, entry: TrafficLogEntry):
        """Broadcast log entry to all SSE listeners in a thread-safe manner"""
        # Safely dispatch to queues without requiring async context
        data = f"data: {entry.to_json()}\n\n"
        to_remove = []
        
        for queue in list(self.listeners):
            try:
                # put_nowait is thread-safe
                queue.put_nowait(data)
            except asyncio.QueueFull:
                to_remove.append(queue)
            except Exception as e:
                logger.warning(f"Failed to put log entry to queue: {e}")
                to_remove.append(queue)
        
        for q in to_remove:
            self.listeners.discard(q)

    async def stream(self):
        queue = asyncio.Queue(maxsize=100)
        self.listeners.add(queue)
        try:
            while True:
                data = await queue.get()
                yield data
        except asyncio.CancelledError:
            self.listeners.discard(queue)
            raise

    def get_recent(self, limit: int = 100) -> List[TrafficLogEntry]:
        return list(self.history)[:limit]

traffic_logger = TrafficLogger()
