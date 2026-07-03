"""Airline Management — registration, lifecycle, audit trail.

The AirlineManager provides CRUD operations for airlines in the federation, with
deterministic state transitions and full audit logging. Each airline has:
  - code: IATA 3-letter code (e.g., "AAL" for American Airlines)
  - status: one of "active", "suspended", "inactive" (deterministic FSM)
  - onboarded_at: timestamp of registration
  - deactivated_at: timestamp of deactivation (if inactive)
  - audit_trail: list of (timestamp, action, details) tuples

This module is pure Python, deterministic, and has zero external dependencies
beyond stdlib + typing. It pairs with MultiAirlineStateStore (which handles
per-airline data persistence) but does not import it — that's a ports-and-adapters
boundary.

All state transitions are deterministic:
  - new → active (on registration)
  - active → suspended (on compliance issue)
  - suspended → active (on compliance cleared)
  - any → inactive (on deactivation; irreversible)

Audit trail is immutable: entries are appended, never modified or deleted.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class AirlineStatus(str, Enum):
    """Airline operational status (deterministic state machine)."""
    ACTIVE = "active"
    SUSPENDED = "suspended"
    INACTIVE = "inactive"


@dataclass(frozen=True)
class AuditEntry:
    """Immutable audit log entry."""
    timestamp: str  # ISO 8601
    action: str     # e.g. "registered", "suspended", "reactivated", "deactivated"
    details: str    # e.g. "compliance_violation: fleet_age_exceeded"

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "action": self.action,
            "details": self.details,
        }


@dataclass
class Airline:
    """Airline registration state."""
    code: str                           # 3-letter IATA code (e.g., "AAL")
    status: AirlineStatus               # active | suspended | inactive
    onboarded_at: str                   # ISO 8601 when first registered
    deactivated_at: Optional[str] = None  # ISO 8601 when deactivated (if inactive)
    audit_trail: list[AuditEntry] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "status": self.status.value,
            "onboarded_at": self.onboarded_at,
            "deactivated_at": self.deactivated_at,
            "audit_trail": [e.to_dict() for e in self.audit_trail],
        }


class AirlineManager:
    """CRUD operations for airlines with deterministic lifecycle management."""

    def __init__(self):
        """Initialize empty manager."""
        self._airlines: dict[str, Airline] = {}

    def register(self, code: str, timestamp: Optional[str] = None) -> Airline:
        """Register a new airline.

        Args:
            code: 3-letter IATA code (must be uppercase, must not exist)
            timestamp: ISO 8601 registration time (defaults to now in UTC)

        Returns:
            The new Airline object.

        Raises:
            ValueError: if code already exists or is invalid.
        """
        if code in self._airlines:
            raise ValueError(f"Airline {code} already registered")
        if not isinstance(code, str) or len(code) != 3 or not code.isupper():
            raise ValueError(f"Invalid airline code {code}; must be 3 uppercase letters")

        now = timestamp or datetime.now(timezone.utc).isoformat()
        airline = Airline(
            code=code,
            status=AirlineStatus.ACTIVE,
            onboarded_at=now,
            audit_trail=[AuditEntry(now, "registered", "initial registration")],
        )
        self._airlines[code] = airline
        return airline

    def get(self, code: str) -> Optional[Airline]:
        """Retrieve airline by code."""
        return self._airlines.get(code)

    def list(self) -> list[Airline]:
        """List all registered airlines (in code order for determinism)."""
        return [self._airlines[k] for k in sorted(self._airlines.keys())]

    def suspend(self, code: str, reason: str, timestamp: Optional[str] = None) -> Airline:
        """Suspend an active airline (e.g., for compliance violation).

        Args:
            code: Airline code.
            reason: Reason for suspension (e.g., "compliance_violation: fleet_age_exceeded").
            timestamp: ISO 8601 of suspension (defaults to now in UTC).

        Returns:
            The updated Airline object.

        Raises:
            ValueError: if airline not found or not active.
        """
        airline = self.get(code)
        if not airline:
            raise ValueError(f"Airline {code} not found")
        if airline.status != AirlineStatus.ACTIVE:
            raise ValueError(f"Cannot suspend {code}: status is {airline.status.value}")

        now = timestamp or datetime.now(timezone.utc).isoformat()
        airline.status = AirlineStatus.SUSPENDED
        airline.audit_trail.append(AuditEntry(now, "suspended", reason))
        return airline

    def reactivate(self, code: str, timestamp: Optional[str] = None) -> Airline:
        """Reactivate a suspended airline (e.g., after compliance cleared).

        Args:
            code: Airline code.
            timestamp: ISO 8601 of reactivation (defaults to now in UTC).

        Returns:
            The updated Airline object.

        Raises:
            ValueError: if airline not found or not suspended.
        """
        airline = self.get(code)
        if not airline:
            raise ValueError(f"Airline {code} not found")
        if airline.status != AirlineStatus.SUSPENDED:
            raise ValueError(f"Cannot reactivate {code}: status is {airline.status.value}")

        now = timestamp or datetime.now(timezone.utc).isoformat()
        airline.status = AirlineStatus.ACTIVE
        airline.audit_trail.append(AuditEntry(now, "reactivated", "compliance cleared"))
        return airline

    def deactivate(self, code: str, timestamp: Optional[str] = None) -> Airline:
        """Deactivate an airline (terminal state; irreversible).

        Args:
            code: Airline code.
            timestamp: ISO 8601 of deactivation (defaults to now in UTC).

        Returns:
            The updated Airline object.

        Raises:
            ValueError: if airline not found or already inactive.
        """
        airline = self.get(code)
        if not airline:
            raise ValueError(f"Airline {code} not found")
        if airline.status == AirlineStatus.INACTIVE:
            raise ValueError(f"Airline {code} is already inactive")

        now = timestamp or datetime.now(timezone.utc).isoformat()
        airline.status = AirlineStatus.INACTIVE
        airline.deactivated_at = now
        airline.audit_trail.append(AuditEntry(now, "deactivated", "end of service"))
        return airline

    def count_active(self) -> int:
        """Count airlines with status == active."""
        return sum(1 for a in self._airlines.values() if a.status == AirlineStatus.ACTIVE)

    def count_by_status(self) -> dict[str, int]:
        """Count airlines by status."""
        counts = {s.value: 0 for s in AirlineStatus}
        for a in self._airlines.values():
            counts[a.status.value] += 1
        return counts
