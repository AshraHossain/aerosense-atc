"""Memory port — fast, ephemeral cache with optional TTL.

Used for flight context, sector overlays, temporary lookups that don't
need to survive a restart.
"""

from abc import ABC, abstractmethod
from typing import Any, Optional


class Memory(ABC):
    """Abstract cache/memory store.

    Supports both permanent and time-limited (TTL) entries.
    Used for flight detail caches, sector memory, decision context.
    """

    @abstractmethod
    def get(self, key: str, default: Any = None) -> Any:
        """Retrieve by key, or return default if missing."""
        pass

    @abstractmethod
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Store a value. ttl is seconds (None = permanent)."""
        pass

    @abstractmethod
    def delete(self, key: str) -> None:
        """Remove by key."""
        pass

    @abstractmethod
    def clear(self) -> None:
        """Clear all entries."""
        pass

    @abstractmethod
    def exists(self, key: str) -> bool:
        """Check if key exists (respecting TTL)."""
        pass
