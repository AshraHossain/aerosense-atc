"""Tests for AirlineManager — CRUD, lifecycle, audit trail.

All tests are deterministic and use fixed timestamps for reproducibility.
"""

import pytest
from datetime import datetime, timezone

from aerocommand.airline_manager import (
    AirlineManager,
    AirlineStatus,
    Airline,
    AuditEntry,
)


class TestAirlineManagerCRUD:
    """Test basic CRUD operations."""

    def test_register_new_airline(self):
        """Register a new airline and verify state."""
        mgr = AirlineManager()
        ts = "2025-01-01T00:00:00+00:00"
        airline = mgr.register("AAL", timestamp=ts)

        assert airline.code == "AAL"
        assert airline.status == AirlineStatus.ACTIVE
        assert airline.onboarded_at == ts
        assert airline.deactivated_at is None
        assert len(airline.audit_trail) == 1
        assert airline.audit_trail[0].action == "registered"

    def test_register_duplicate_raises(self):
        """Registering the same code twice raises ValueError."""
        mgr = AirlineManager()
        mgr.register("AAL")
        with pytest.raises(ValueError, match="already registered"):
            mgr.register("AAL")

    def test_register_invalid_code_raises(self):
        """Invalid codes raise ValueError."""
        mgr = AirlineManager()
        with pytest.raises(ValueError, match="Invalid airline code"):
            mgr.register("aa")  # too short
        with pytest.raises(ValueError, match="Invalid airline code"):
            mgr.register("AAAL")  # too long
        with pytest.raises(ValueError, match="Invalid airline code"):
            mgr.register("aal")  # lowercase

    def test_get_existing_airline(self):
        """Retrieve an airline by code."""
        mgr = AirlineManager()
        mgr.register("AAL")
        airline = mgr.get("AAL")
        assert airline is not None
        assert airline.code == "AAL"

    def test_get_nonexistent_returns_none(self):
        """Retrieve a non-existent airline returns None."""
        mgr = AirlineManager()
        assert mgr.get("ZZZ") is None

    def test_list_all_airlines(self):
        """List all registered airlines in code order."""
        mgr = AirlineManager()
        mgr.register("SWA")
        mgr.register("AAL")
        mgr.register("UAL")

        airlines = mgr.list()
        assert len(airlines) == 3
        # Must be in sorted code order (determinism)
        assert [a.code for a in airlines] == ["AAL", "SWA", "UAL"]

    def test_list_empty(self):
        """List with no airlines returns empty list."""
        mgr = AirlineManager()
        assert mgr.list() == []


class TestAirlineLifecycle:
    """Test state transitions: active → suspended → active → inactive."""

    def test_suspend_active_airline(self):
        """Suspend an active airline."""
        mgr = AirlineManager()
        mgr.register("AAL")
        ts = "2025-01-02T00:00:00+00:00"
        reason = "compliance_violation: fleet_age_exceeded"

        airline = mgr.suspend("AAL", reason, timestamp=ts)

        assert airline.status == AirlineStatus.SUSPENDED
        assert airline.deactivated_at is None  # Not yet deactivated
        assert len(airline.audit_trail) == 2
        assert airline.audit_trail[1].action == "suspended"
        assert airline.audit_trail[1].details == reason

    def test_suspend_nonexistent_raises(self):
        """Suspending a non-existent airline raises."""
        mgr = AirlineManager()
        with pytest.raises(ValueError, match="not found"):
            mgr.suspend("ZZZ", "test")

    def test_suspend_already_suspended_raises(self):
        """Suspending an already-suspended airline raises."""
        mgr = AirlineManager()
        mgr.register("AAL")
        mgr.suspend("AAL", "test")
        with pytest.raises(ValueError, match="Cannot suspend"):
            mgr.suspend("AAL", "test2")

    def test_suspend_inactive_raises(self):
        """Suspending an inactive airline raises."""
        mgr = AirlineManager()
        mgr.register("AAL")
        mgr.deactivate("AAL")
        with pytest.raises(ValueError, match="Cannot suspend"):
            mgr.suspend("AAL", "test")

    def test_reactivate_suspended_airline(self):
        """Reactivate a suspended airline."""
        mgr = AirlineManager()
        mgr.register("AAL")
        mgr.suspend("AAL", "test")
        ts = "2025-01-03T00:00:00+00:00"

        airline = mgr.reactivate("AAL", timestamp=ts)

        assert airline.status == AirlineStatus.ACTIVE
        assert len(airline.audit_trail) == 3
        assert airline.audit_trail[2].action == "reactivated"

    def test_reactivate_nonexistent_raises(self):
        """Reactivating a non-existent airline raises."""
        mgr = AirlineManager()
        with pytest.raises(ValueError, match="not found"):
            mgr.reactivate("ZZZ")

    def test_reactivate_active_raises(self):
        """Reactivating an active airline raises."""
        mgr = AirlineManager()
        mgr.register("AAL")
        with pytest.raises(ValueError, match="Cannot reactivate"):
            mgr.reactivate("AAL")

    def test_reactivate_inactive_raises(self):
        """Reactivating an inactive airline raises."""
        mgr = AirlineManager()
        mgr.register("AAL")
        mgr.deactivate("AAL")
        with pytest.raises(ValueError, match="Cannot reactivate"):
            mgr.reactivate("AAL")

    def test_deactivate_active_airline(self):
        """Deactivate an active airline (terminal state)."""
        mgr = AirlineManager()
        mgr.register("AAL")
        ts = "2025-01-04T00:00:00+00:00"

        airline = mgr.deactivate("AAL", timestamp=ts)

        assert airline.status == AirlineStatus.INACTIVE
        assert airline.deactivated_at == ts
        assert len(airline.audit_trail) == 2
        assert airline.audit_trail[1].action == "deactivated"

    def test_deactivate_suspended_airline(self):
        """Deactivate a suspended airline (also terminal)."""
        mgr = AirlineManager()
        mgr.register("AAL")
        mgr.suspend("AAL", "test")
        ts = "2025-01-04T00:00:00+00:00"

        airline = mgr.deactivate("AAL", timestamp=ts)

        assert airline.status == AirlineStatus.INACTIVE
        assert airline.deactivated_at == ts

    def test_deactivate_nonexistent_raises(self):
        """Deactivating a non-existent airline raises."""
        mgr = AirlineManager()
        with pytest.raises(ValueError, match="not found"):
            mgr.deactivate("ZZZ")

    def test_deactivate_already_inactive_raises(self):
        """Deactivating an already-inactive airline raises."""
        mgr = AirlineManager()
        mgr.register("AAL")
        mgr.deactivate("AAL")
        with pytest.raises(ValueError, match="already inactive"):
            mgr.deactivate("AAL")

    def test_full_lifecycle_sequence(self):
        """Test full sequence: active → suspended → active → inactive."""
        mgr = AirlineManager()
        ts_reg = "2025-01-01T00:00:00+00:00"
        ts_sus = "2025-01-02T00:00:00+00:00"
        ts_rea = "2025-01-03T00:00:00+00:00"
        ts_dea = "2025-01-04T00:00:00+00:00"

        mgr.register("AAL", timestamp=ts_reg)
        assert mgr.get("AAL").status == AirlineStatus.ACTIVE

        mgr.suspend("AAL", "test", timestamp=ts_sus)
        assert mgr.get("AAL").status == AirlineStatus.SUSPENDED

        mgr.reactivate("AAL", timestamp=ts_rea)
        assert mgr.get("AAL").status == AirlineStatus.ACTIVE

        mgr.deactivate("AAL", timestamp=ts_dea)
        assert mgr.get("AAL").status == AirlineStatus.INACTIVE
        assert mgr.get("AAL").deactivated_at == ts_dea

        # Audit trail should have all 4 events
        trail = mgr.get("AAL").audit_trail
        assert len(trail) == 4
        assert trail[0].action == "registered"
        assert trail[1].action == "suspended"
        assert trail[2].action == "reactivated"
        assert trail[3].action == "deactivated"


class TestAuditTrail:
    """Test audit trail immutability and completeness."""

    def test_audit_entry_frozen(self):
        """AuditEntry is frozen (immutable)."""
        entry = AuditEntry(
            timestamp="2025-01-01T00:00:00+00:00",
            action="registered",
            details="test",
        )
        with pytest.raises(AttributeError):
            entry.action = "modified"

    def test_audit_trail_accumulated(self):
        """Audit trail accumulates all actions."""
        mgr = AirlineManager()
        mgr.register("AAL")
        mgr.suspend("AAL", "reason1")
        # Second suspend should raise since status is already suspended
        with pytest.raises(ValueError):
            mgr.suspend("AAL", "reason2")
        # Verify audit trail has exactly 2 entries (register + suspend)
        assert len(mgr.get("AAL").audit_trail) == 2

    def test_audit_to_dict(self):
        """AuditEntry.to_dict() serializes correctly."""
        entry = AuditEntry(
            timestamp="2025-01-01T00:00:00+00:00",
            action="registered",
            details="test",
        )
        d = entry.to_dict()
        assert d["timestamp"] == "2025-01-01T00:00:00+00:00"
        assert d["action"] == "registered"
        assert d["details"] == "test"

    def test_airline_to_dict(self):
        """Airline.to_dict() serializes including audit trail."""
        mgr = AirlineManager()
        mgr.register("AAL")
        airline = mgr.get("AAL")

        d = airline.to_dict()
        assert d["code"] == "AAL"
        assert d["status"] == "active"
        assert "onboarded_at" in d
        assert isinstance(d["audit_trail"], list)
        assert len(d["audit_trail"]) >= 1


class TestAirlineStatusCounts:
    """Test counting airlines by status."""

    def test_count_active_empty(self):
        """Count active on empty manager returns 0."""
        mgr = AirlineManager()
        assert mgr.count_active() == 0

    def test_count_active_mixed(self):
        """Count active with mixed statuses."""
        mgr = AirlineManager()
        mgr.register("AAL")
        mgr.register("SWA")
        mgr.register("UAL")
        mgr.suspend("SWA", "test")

        assert mgr.count_active() == 2

    def test_count_by_status(self):
        """Count all airlines by status."""
        mgr = AirlineManager()
        mgr.register("AAL")
        mgr.register("SWA")
        mgr.register("UAL")
        mgr.suspend("SWA", "test")
        mgr.deactivate("UAL")

        counts = mgr.count_by_status()
        assert counts["active"] == 1
        assert counts["suspended"] == 1
        assert counts["inactive"] == 1

    def test_count_by_status_empty(self):
        """Count by status on empty manager."""
        mgr = AirlineManager()
        counts = mgr.count_by_status()
        assert counts["active"] == 0
        assert counts["suspended"] == 0
        assert counts["inactive"] == 0


class TestAirlineManagerDeterminism:
    """Test determinism: same inputs → same outputs."""

    def test_register_same_code_same_ts_is_deterministic(self):
        """Registering the same airline twice at the same time produces the same state."""
        ts = "2025-01-01T00:00:00+00:00"

        mgr1 = AirlineManager()
        a1 = mgr1.register("AAL", timestamp=ts)

        mgr2 = AirlineManager()
        a2 = mgr2.register("AAL", timestamp=ts)

        assert a1.to_dict() == a2.to_dict()

    def test_list_order_is_deterministic(self):
        """List order is always sorted code order."""
        mgr = AirlineManager()
        codes = ["SWA", "AAL", "UAL", "DAL"]
        for code in codes:
            mgr.register(code)

        # Insert in random order
        airlines_list = mgr.list()
        codes_list = [a.code for a in airlines_list]
        assert codes_list == sorted(codes)

    def test_lifecycle_with_fixed_timestamps_is_deterministic(self):
        """Same lifecycle with same timestamps produces same result."""
        ts_reg = "2025-01-01T00:00:00+00:00"
        ts_sus = "2025-01-02T00:00:00+00:00"
        ts_rea = "2025-01-03T00:00:00+00:00"
        ts_dea = "2025-01-04T00:00:00+00:00"

        mgr1 = AirlineManager()
        mgr1.register("AAL", timestamp=ts_reg)
        mgr1.suspend("AAL", "reason", timestamp=ts_sus)
        mgr1.reactivate("AAL", timestamp=ts_rea)
        mgr1.deactivate("AAL", timestamp=ts_dea)

        mgr2 = AirlineManager()
        mgr2.register("AAL", timestamp=ts_reg)
        mgr2.suspend("AAL", "reason", timestamp=ts_sus)
        mgr2.reactivate("AAL", timestamp=ts_rea)
        mgr2.deactivate("AAL", timestamp=ts_dea)

        assert mgr1.get("AAL").to_dict() == mgr2.get("AAL").to_dict()


class TestAirlineManagerEdgeCases:
    """Test edge cases and error handling."""

    def test_register_with_none_timestamp_uses_current(self):
        """Register with timestamp=None uses current time."""
        mgr = AirlineManager()
        before = datetime.now(timezone.utc).isoformat()
        airline = mgr.register("AAL")
        after = datetime.now(timezone.utc).isoformat()

        # The timestamp should be between before and after
        assert before <= airline.onboarded_at <= after

    def test_multiple_managers_are_independent(self):
        """Two AirlineManager instances don't share state."""
        mgr1 = AirlineManager()
        mgr2 = AirlineManager()

        mgr1.register("AAL")
        assert mgr1.get("AAL") is not None
        assert mgr2.get("AAL") is None

    def test_get_returns_same_object_reference(self):
        """get() returns the same object (not a copy)."""
        mgr = AirlineManager()
        mgr.register("AAL")
        a1 = mgr.get("AAL")
        a2 = mgr.get("AAL")
        assert a1 is a2
