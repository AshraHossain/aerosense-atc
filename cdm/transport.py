"""CDM transport — the wire the seam messages travel over.

`CDMTransport` is the port; `InMemoryCDMTransport` is the single-node adapter used
by AeroSense locally and by the whole test suite. The Kafka adapter (M4) will
implement the same `publish`/`drain` surface, so nothing above the port changes
when the topology does.

In-memory transport is intentionally a plain FIFO queue — ponytail: a deque is the
whole feature; reach for Kafka only when there is a real cross-process need (M4).
"""

from __future__ import annotations

from collections import deque
from typing import Iterable, Optional, Protocol

from cdm.messages import CDMDirection, CDMMessageType, _CDMBase


class CDMTransport(Protocol):
    def publish(self, message: _CDMBase) -> None: ...
    def drain(
        self,
        direction: Optional[CDMDirection] = None,
        message_type: Optional[CDMMessageType] = None,
    ) -> list[_CDMBase]: ...


class InMemoryCDMTransport:
    """FIFO in-process bus. `drain` removes and returns matching messages in the
    order published; non-matching messages stay queued."""

    def __init__(self) -> None:
        self._q: deque[_CDMBase] = deque()

    def publish(self, message: _CDMBase) -> None:
        self._q.append(message)

    def publish_many(self, messages: Iterable[_CDMBase]) -> None:
        for m in messages:
            self.publish(m)

    def __len__(self) -> int:
        return len(self._q)

    @property
    def pending(self) -> int:
        return len(self._q)

    def drain(
        self,
        direction: Optional[CDMDirection] = None,
        message_type: Optional[CDMMessageType] = None,
    ) -> list[_CDMBase]:
        """Pop and return messages matching the filter, preserving FIFO order.
        With no filter, drains everything."""
        taken: list[_CDMBase] = []
        kept: deque[_CDMBase] = deque()
        while self._q:
            msg = self._q.popleft()
            if direction is not None and msg.direction != direction:
                kept.append(msg)
                continue
            if message_type is not None and msg.message_type != message_type:
                kept.append(msg)
                continue
            taken.append(msg)
        # restore the non-matching messages in their original order
        self._q = kept
        return taken
