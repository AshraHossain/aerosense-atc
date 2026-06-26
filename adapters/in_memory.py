"""In-memory adapters for single-node AeroSense deployment.

All four ports implemented as simple, thread-safe in-memory stores.
"""

import json
import time
from collections import deque
from datetime import datetime
from typing import Any, Dict, List, Optional

from core.ports import EventBus, Memory, StateStore, Tracer


class InMemoryEventBus(EventBus):
    """FIFO queue-based event bus (like InMemoryCDMTransport but generic)."""

    def __init__(self):
        self._queue = deque()

    def publish(self, message: Any) -> None:
        self._queue.append(message)

    def publish_many(self, messages: List[Any]) -> None:
        self._queue.extend(messages)

    def drain(self, **filters) -> List[Any]:
        """Remove and return messages matching filters.

        For CDM messages: filters={'direction': CDMDirection.DOWN, ...}
        For dicts: filters={'type': 'DOWN'}
        Non-matching messages are preserved in order.
        """
        drained = []
        remaining = deque()
        for msg in self._queue:
            matches = True
            for k, v in filters.items():
                # Support both dict-like and object-like access
                msg_val = msg.get(k) if isinstance(msg, dict) else getattr(msg, k, None)
                if msg_val != v:
                    matches = False
                    break
            if matches:
                drained.append(msg)
            else:
                remaining.append(msg)
        self._queue = remaining
        return drained

    @property
    def pending(self) -> int:
        return len(self._queue)


class InMemoryStateStore(StateStore):
    """Simple dict-backed state store."""

    def __init__(self):
        self._store: Dict[str, Dict[str, Any]] = {}

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        return self._store.get(key)

    def set(self, key: str, value: Dict[str, Any]) -> None:
        self._store[key] = value.copy()

    def update(self, key: str, updates: Dict[str, Any]) -> None:
        if key not in self._store:
            self._store[key] = {}
        self._store[key].update(updates)

    def delete(self, key: str) -> None:
        self._store.pop(key, None)

    def exists(self, key: str) -> bool:
        return key in self._store


class InMemoryMemory(Memory):
    """Dict-backed cache with TTL support."""

    def __init__(self):
        self._store: Dict[str, tuple] = {}  # key -> (value, expiry_time or None)

    def get(self, key: str, default: Any = None) -> Any:
        if key not in self._store:
            return default
        value, expiry = self._store[key]
        if expiry is not None and time.time() > expiry:
            del self._store[key]
            return default
        return value

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        expiry = time.time() + ttl if ttl else None
        self._store[key] = (value, expiry)

    def delete(self, key: str) -> None:
        self._store.pop(key, None)

    def clear(self) -> None:
        self._store.clear()

    def exists(self, key: str) -> bool:
        return self.get(key) is not None


class InMemoryTracer(Tracer):
    """Simple list-backed audit trace."""

    def __init__(self):
        self._events: List[Dict[str, Any]] = []

    def log(self, event_type: str, metadata: Dict[str, Any]) -> None:
        event = {
            "timestamp": datetime.utcnow().isoformat(),
            "event_type": event_type,
            **metadata,
        }
        self._events.append(event)

    def get_trace(self) -> List[Dict[str, Any]]:
        return self._events.copy()

    def export(self, format: str = "json") -> str:
        if format == "json":
            return json.dumps(self._events, indent=2, default=str)
        raise ValueError(f"unsupported format: {format}")

    def clear(self) -> None:
        self._events.clear()
