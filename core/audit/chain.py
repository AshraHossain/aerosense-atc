"""Tamper-evident audit chain (AeroOps M1 governance).

Ported from AutoRedTeam's hash-chained audit and adapted to AeroSense's single-node,
in-memory, synchronous profile (no DB, no asyncio — the chain is a list). Each event's
hash folds in the previous event's hash, so editing or deleting any historical entry
breaks every later hash and `verify()` pinpoints where. This is the concrete
machinery behind the repo's "DO-178C-inspired traceability": a decision log you can
prove wasn't altered after the fact.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone

GENESIS_HASH = "0" * 64


def compute_hash(prev_hash: str, *, event_type: str, actor: str,
                 details: dict, created_at: str) -> str:
    """Deterministic event hash; sort_keys makes the JSON canonical so dict
    insertion order never changes the hash."""
    payload = json.dumps(
        {"prev_hash": prev_hash, "event_type": event_type, "actor": actor,
         "details": details, "created_at": created_at},
        sort_keys=True, separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class AuditEvent:
    seq: int
    event_type: str
    actor: str
    details: dict
    prev_hash: str
    hash: str
    created_at: str

    def to_dict(self) -> dict:
        return {
            "seq": self.seq, "event_type": self.event_type, "actor": self.actor,
            "details": self.details, "prev_hash": self.prev_hash,
            "hash": self.hash, "created_at": self.created_at,
        }


@dataclass
class AuditChain:
    """An append-only, hash-chained, in-memory audit log."""

    _events: list[AuditEvent] = field(default_factory=list)

    def record(self, event_type: str, actor: str, details: dict | None = None) -> AuditEvent:
        details = details or {}
        created_at = datetime.now(timezone.utc).isoformat()
        prev_hash = self._events[-1].hash if self._events else GENESIS_HASH
        seq = len(self._events) + 1
        event = AuditEvent(
            seq=seq, event_type=event_type, actor=actor, details=details,
            prev_hash=prev_hash,
            hash=compute_hash(prev_hash, event_type=event_type, actor=actor,
                              details=details, created_at=created_at),
            created_at=created_at,
        )
        self._events.append(event)
        return event

    @property
    def events(self) -> list[AuditEvent]:
        return list(self._events)

    def __len__(self) -> int:
        return len(self._events)

    def verify(self) -> list[str]:
        """Recompute the chain; return human-readable problems (empty = intact).
        Catches mutated fields (hash won't recompute) and broken/missing links."""
        problems: list[str] = []
        expected_prev = GENESIS_HASH
        for ev in self._events:
            if ev.prev_hash != expected_prev:
                problems.append(
                    f"seq={ev.seq}: prev_hash {ev.prev_hash[:12]} != expected "
                    f"{expected_prev[:12]} (inserted/deleted/reordered)")
            recomputed = compute_hash(ev.prev_hash, event_type=ev.event_type,
                                      actor=ev.actor, details=ev.details,
                                      created_at=ev.created_at)
            if recomputed != ev.hash:
                problems.append(f"seq={ev.seq}: stored hash != recomputed (modified)")
            expected_prev = ev.hash
        return problems
