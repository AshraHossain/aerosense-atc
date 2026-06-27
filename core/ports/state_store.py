"""StateStore port — persistence for ATCState and scenario data."""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


class StateStore(ABC):
    """Abstract state persistence.

    Agents read ATCState from store, mutate it, write it back.
    Single key 'scenario' holds the full scenario state (ATCState dict).
    """

    @abstractmethod
    def get(self, key: str) -> Optional[Dict[str, Any]]:
        """Retrieve state by key (e.g. 'scenario'), or None if missing."""
        pass

    @abstractmethod
    def set(self, key: str, value: Dict[str, Any]) -> None:
        """Store state by key (overwrites)."""
        pass

    @abstractmethod
    def update(self, key: str, updates: Dict[str, Any]) -> None:
        """Merge updates into existing state (e.g. {'phase': 3})."""
        pass

    @abstractmethod
    def delete(self, key: str) -> None:
        """Remove state by key."""
        pass

    @abstractmethod
    def exists(self, key: str) -> bool:
        """Check if key exists."""
        pass
