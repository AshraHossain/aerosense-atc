"""EventBus port — publish/drain for CDM and agent event messages."""

from abc import ABC, abstractmethod
from typing import Any, List, Optional


class EventBus(ABC):
    """Abstract event bus for pub-sub message flow.

    Two usage patterns:
    - Pub/sub: publish(msg), drain filters and removes messages
    - Streaming: for agents that consume events from upstream phases
    """

    @abstractmethod
    def publish(self, message: Any) -> None:
        """Publish a message (e.g. CDM directive or agent event)."""
        pass

    @abstractmethod
    def publish_many(self, messages: List[Any]) -> None:
        """Batch publish."""
        pass

    @abstractmethod
    def drain(self, **filters) -> List[Any]:
        """Remove and return messages matching filters (e.g. direction=DOWN).

        Filters depend on message type (CDM messages filter by direction/type).
        Non-matching messages are preserved in order.
        """
        pass

    @property
    @abstractmethod
    def pending(self) -> int:
        """Current queue depth."""
        pass
