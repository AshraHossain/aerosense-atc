"""Redis Memory adapter for AeroCommand distributed deployment.

Fast cache with TTL support; used for flight context, sector data, temp lookups.
Requires Redis running (usually via docker-compose).
"""

import json
from typing import Any, Optional

import redis

from core.ports import Memory


class RedisMemory(Memory):
    """Redis-backed cache with TTL support."""

    def __init__(self, host: str = "localhost", port: int = 6379, db: int = 0):
        self.client = redis.Redis(host=host, port=port, db=db, decode_responses=True)

    def get(self, key: str, default: Any = None) -> Any:
        value = self.client.get(key)
        if value is None:
            return default
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        serialized = json.dumps(value, default=str)
        if ttl:
            self.client.setex(key, ttl, serialized)
        else:
            self.client.set(key, serialized)

    def delete(self, key: str) -> None:
        self.client.delete(key)

    def clear(self) -> None:
        self.client.flushdb()

    def exists(self, key: str) -> bool:
        return self.client.exists(key) > 0
