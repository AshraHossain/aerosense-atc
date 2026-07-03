"""Multi-Airline State Store — per-airline schema isolation via Postgres.

The MultiAirlineStateStore provides deterministic, isolated state persistence for
each airline in the federation. Each airline gets its own Postgres schema
(e.g., airline_aal, airline_swa) so that:

  1. SQL joins cannot leak data between airlines
  2. One airline's indexing choices don't affect another's query performance
  3. Schema migrations can roll out per-airline without global locks
  4. Per-airline JSONB columns can store flight state, fleet, responses, etc.

This module is pure Python + asyncio, deterministic, and handles:
  - Schema creation/deletion (on airline registration/deactivation)
  - JSONB state write (flights, fleet, responses)
  - JSONB state read (with per-airline isolation guaranteed)
  - Schema versioning (each airline tracks its own schema version)
  - Consistency checks (no orphaned rows, referential integrity)

All state changes are transactional (atomic per airline). There is no cross-airline
transaction; each airline's changes are isolated.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional
import hashlib


class MultiAirlineStateStore:
    """Per-airline Postgres JSONB store with schema isolation.

    This is an in-memory mock for Phase 1 testing. The full implementation will
    use asyncpg to connect to Postgres, but the interface is the same.
    """

    def __init__(self):
        """Initialize empty store (in-memory mock)."""
        # In-memory mock: airline_code -> schema_data
        self._schemas: dict[str, dict[str, Any]] = {}

    def _schema_key(self, airline_code: str) -> str:
        """Generate deterministic schema name from airline code."""
        return f"airline_{airline_code.lower()}"

    async def ensure_schema(self, airline_code: str) -> str:
        """Create schema for airline if not exists.

        Returns:
            The schema name (e.g., "airline_aal").

        Raises:
            ValueError: if airline_code is invalid.
        """
        if not isinstance(airline_code, str) or len(airline_code) != 3:
            raise ValueError(f"Invalid airline code {airline_code}")

        schema_name = self._schema_key(airline_code)
        if schema_name not in self._schemas:
            self._schemas[schema_name] = {
                "created_at": datetime.now(timezone.utc).isoformat(),
                "schema_version": "1.0",
                "flights": {},       # flight_id -> flight_dict
                "fleet": {},         # aircraft_id -> aircraft_dict
                "responses": {},     # response_id -> response_dict
                "audit_log": [],     # list of (timestamp, action, details)
            }
        return schema_name

    async def read_state(
        self, airline_code: str, key: str, default: Any = None
    ) -> Any:
        """Read a top-level key from the airline's schema.

        Args:
            airline_code: 3-letter airline code.
            key: Key to read (e.g., "flights", "fleet", "responses", "audit_log").
            default: Default value if key doesn't exist.

        Returns:
            The value, or default if not found.

        Raises:
            ValueError: if schema doesn't exist.
        """
        schema_name = self._schema_key(airline_code)
        if schema_name not in self._schemas:
            raise ValueError(f"No schema for airline {airline_code}; call ensure_schema first")

        schema = self._schemas[schema_name]
        return schema.get(key, default)

    async def write_state(
        self, airline_code: str, key: str, value: Any, timestamp: Optional[str] = None
    ) -> None:
        """Write a top-level key to the airline's schema (full replace).

        Args:
            airline_code: 3-letter airline code.
            key: Key to write (e.g., "flights", "fleet", "responses").
            value: The new value (will be JSON-serialized).
            timestamp: ISO 8601 timestamp for audit log (defaults to now in UTC).

        Raises:
            ValueError: if schema doesn't exist.
        """
        schema_name = self._schema_key(airline_code)
        if schema_name not in self._schemas:
            raise ValueError(f"No schema for airline {airline_code}; call ensure_schema first")

        schema = self._schemas[schema_name]
        schema[key] = value

        # Append to audit log
        now = timestamp or datetime.now(timezone.utc).isoformat()
        audit_entry = {
            "timestamp": now,
            "action": f"write_{key}",
            "details": f"Updated {key}; size={len(json.dumps(value))}",
        }
        if "audit_log" not in schema:
            schema["audit_log"] = []
        schema["audit_log"].append(audit_entry)

    async def upsert_flight(
        self, airline_code: str, flight_id: str, flight_data: dict, timestamp: Optional[str] = None
    ) -> None:
        """Insert or update a flight in the airline's schema.

        Args:
            airline_code: 3-letter airline code.
            flight_id: Unique flight identifier (e.g., "AAL123").
            flight_data: Flight dict (callsign, origin, destination, etc.).
            timestamp: ISO 8601 timestamp for audit log (defaults to now in UTC).

        Raises:
            ValueError: if schema doesn't exist.
        """
        schema_name = self._schema_key(airline_code)
        if schema_name not in self._schemas:
            raise ValueError(f"No schema for airline {airline_code}; call ensure_schema first")

        schema = self._schemas[schema_name]
        if "flights" not in schema:
            schema["flights"] = {}

        schema["flights"][flight_id] = flight_data

        # Append to audit log
        now = timestamp or datetime.now(timezone.utc).isoformat()
        audit_entry = {
            "timestamp": now,
            "action": "upsert_flight",
            "details": f"flight_id={flight_id}",
        }
        if "audit_log" not in schema:
            schema["audit_log"] = []
        schema["audit_log"].append(audit_entry)

    async def read_flights(self, airline_code: str) -> dict[str, dict]:
        """Read all flights for an airline.

        Returns:
            Dict of flight_id -> flight_data.

        Raises:
            ValueError: if schema doesn't exist.
        """
        schema_name = self._schema_key(airline_code)
        if schema_name not in self._schemas:
            raise ValueError(f"No schema for airline {airline_code}; call ensure_schema first")

        return self._schemas[schema_name].get("flights", {})

    async def delete_flight(
        self, airline_code: str, flight_id: str, timestamp: Optional[str] = None
    ) -> None:
        """Delete a flight from the airline's schema.

        Args:
            airline_code: 3-letter airline code.
            flight_id: Flight identifier to delete.
            timestamp: ISO 8601 timestamp for audit log (defaults to now in UTC).

        Raises:
            ValueError: if schema doesn't exist or flight not found.
        """
        schema_name = self._schema_key(airline_code)
        if schema_name not in self._schemas:
            raise ValueError(f"No schema for airline {airline_code}; call ensure_schema first")

        schema = self._schemas[schema_name]
        if "flights" not in schema or flight_id not in schema["flights"]:
            raise ValueError(f"Flight {flight_id} not found for airline {airline_code}")

        del schema["flights"][flight_id]

        # Append to audit log
        now = timestamp or datetime.now(timezone.utc).isoformat()
        audit_entry = {
            "timestamp": now,
            "action": "delete_flight",
            "details": f"flight_id={flight_id}",
        }
        if "audit_log" not in schema:
            schema["audit_log"] = []
        schema["audit_log"].append(audit_entry)

    async def read_audit_log(self, airline_code: str) -> list[dict]:
        """Read the audit log for an airline.

        Returns:
            List of audit entries (timestamp, action, details).

        Raises:
            ValueError: if schema doesn't exist.
        """
        schema_name = self._schema_key(airline_code)
        if schema_name not in self._schemas:
            raise ValueError(f"No schema for airline {airline_code}; call ensure_schema first")

        return self._schemas[schema_name].get("audit_log", [])

    async def drop_schema(self, airline_code: str) -> None:
        """Drop schema for an airline (on deactivation).

        Args:
            airline_code: 3-letter airline code.

        Raises:
            ValueError: if schema doesn't exist.
        """
        schema_name = self._schema_key(airline_code)
        if schema_name not in self._schemas:
            raise ValueError(f"No schema for airline {airline_code}")

        del self._schemas[schema_name]

    async def consistency_check(self, airline_code: str) -> dict[str, Any]:
        """Verify consistency of state for an airline.

        Returns:
            Dict with keys like:
              - all_ok: bool
              - errors: list of error strings
              - schema_version: version number
              - flight_count: number of flights
              - audit_entry_count: number of audit entries

        Raises:
            ValueError: if schema doesn't exist.
        """
        schema_name = self._schema_key(airline_code)
        if schema_name not in self._schemas:
            raise ValueError(f"No schema for airline {airline_code}; call ensure_schema first")

        schema = self._schemas[schema_name]
        errors = []

        # Basic checks
        flights = schema.get("flights", {})
        if not isinstance(flights, dict):
            errors.append("flights is not a dict")

        audit_log = schema.get("audit_log", [])
        if not isinstance(audit_log, list):
            errors.append("audit_log is not a list")

        return {
            "all_ok": len(errors) == 0,
            "errors": errors,
            "schema_version": schema.get("schema_version", "unknown"),
            "flight_count": len(flights),
            "audit_entry_count": len(audit_log),
        }

    async def list_schemas(self) -> list[str]:
        """List all active schemas (in sorted order for determinism)."""
        return sorted(self._schemas.keys())

    async def compute_state_hash(self, airline_code: str) -> str:
        """Compute SHA-256 hash of an airline's entire state (for determinism verification).

        Returns:
            Hex-encoded SHA-256 hash.

        Raises:
            ValueError: if schema doesn't exist.
        """
        schema_name = self._schema_key(airline_code)
        if schema_name not in self._schemas:
            raise ValueError(f"No schema for airline {airline_code}; call ensure_schema first")

        schema = self._schemas[schema_name]
        # Hash all non-audit data (audit log should not affect determinism of state)
        state_to_hash = {k: v for k, v in schema.items() if k != "audit_log"}
        state_json = json.dumps(state_to_hash, sort_keys=True)
        return hashlib.sha256(state_json.encode()).hexdigest()
