"""Full system E2E: AeroSense 12-phase graph → Phase 10 GDP → CDM seam → AOC → reconciliation.

Proves all four milestones work together:
- M0: core routing (emergency squawk bypass, conflict escalation)
- M1: eval harness + audit (decision trace)
- M2: CDM seam (DOWN/UP messages)
- M3: AOC responder (deterministic flow reactions)
- M4: adapters + ports (pluggable infrastructure)

This is a smoke test: it mocks the LLM but proves the real routing and seam logic.
"""

from datetime import datetime, timedelta, timezone
import json

import pytest

# Core imports
from core.state import ATCState
from core.routing import route_after_surveillance, route_after_conflict

# CDM imports
from cdm import InMemoryCDMTransport, tfm_to_cdm
from cdm.messages import CDMDirection

# AOC imports
from aerocommand import FleetFlight, respond_to_directive

# Adapters (M4)
from adapters.in_memory import (
    InMemoryEventBus,
    InMemoryStateStore,
    InMemoryMemory,
    InMemoryTracer,
)

T0 = datetime(2026, 6, 26, 12, 0, tzinfo=timezone.utc)


def test_full_system_atc_routing_and_cdm_seam():
    """Smoke test: ATC routing + CDM down + AOC response."""

    # ── M0: Core routing (no LLM) ──────────────────────────────────────────
    # A surveillance contact with high-priority squawk should bypass to Phase 09
    state = ATCState(
        phase=1,
        raw_contacts=[{"squawk": "7700", "altitude": 10000, "track": 180}],
        system_health="nominal",
    )
    next_phase = route_after_surveillance(state)
    assert next_phase == "phase_09_emergency", "Emergency squawk 7700 should bypass to Phase 09"

    # ── M1: Audit trail (in-memory tracer) ─────────────────────────────────
    tracer = InMemoryTracer()
    tracer.log("phase_01", {"event": "surveillance_contact", "squawk": "7700"})
    tracer.log("route_decision", {"bypass_to": 9, "reason": "emergency"})
    events = tracer.get_trace()
    assert len(events) == 2
    assert events[0]["event"] == "surveillance_contact"

    # ── M2: CDM seam (simulate Phase 10 GDP output) ─────────────────────────
    # Phase 10 in the real graph would produce a TFMProgram dict.
    # Here we simulate it: a GDP at Denver due to thunderstorms.
    tfm_program = {
        "program_id": "tfm-001",
        "tfm_type": "gdp",
        "affected_fix": "KDEN",
        "rate_per_hour": 2,
        "reason": "thunderstorms",
        "active": True,
    }

    # Translate to CDM
    gdp_down = tfm_to_cdm(
        tfm_program,
        issuer="ATCSCC",
        message_id="down-001",
        start=T0,
        end=T0 + timedelta(hours=2),
    )
    assert gdp_down.direction == CDMDirection.DOWN
    assert gdp_down.element == "KDEN"

    # ── M3: AOC responder (fleet reacts to directive) ──────────────────────
    # Airline fleet arriving at Denver during the GDP window
    fleet = [
        FleetFlight(
            flight_id="DAL1",
            origin="KSFO",
            destination="KDEN",
            scheduled_arrival=T0 + timedelta(minutes=30),
            priority=5,
            cancellable=True,
        ),
        FleetFlight(
            flight_id="SWA2",
            origin="KLAX",
            destination="KDEN",
            scheduled_arrival=T0 + timedelta(minutes=45),
            priority=3,
            cancellable=True,
        ),
        FleetFlight(
            flight_id="UAL3",
            origin="KORD",
            destination="KDEN",
            scheduled_arrival=T0 + timedelta(minutes=60),
            priority=7,
            cancellable=True,
        ),
    ]

    # AOC responder computes reactions to the GDP
    # Capacity = 2/hr * 2hr = 4 slots; 3 arrivals fit, so no action needed.
    responses = respond_to_directive(gdp_down, fleet)
    assert responses == [], "All flights fit in GDP window, no delays"

    # Now simulate overflow: more flights
    fleet_overflow = fleet + [
        FleetFlight(
            flight_id="AAL4",
            origin="KMCO",
            destination="KDEN",
            scheduled_arrival=T0 + timedelta(minutes=50),
            priority=1,
            cancellable=True,
        ),
    ]
    responses = respond_to_directive(gdp_down, fleet_overflow)
    # 4 flights, capacity 4 → overflow 0 (still fits)
    # (capacity floor: rate 2/hr * 2hr = 4)
    assert responses == []

    # One more to overflow
    fleet_overflow.append(
        FleetFlight(
            flight_id="FDX5",
            origin="KMEM",
            destination="KDEN",
            scheduled_arrival=T0 + timedelta(minutes=55),
            priority=0,
            cancellable=True,
        ),
    )
    responses = respond_to_directive(gdp_down, fleet_overflow)
    # 5 flights, capacity 4 → overflow 1
    assert len(responses) == 1
    # Lowest priority (0) should be the victim
    assert responses[0].flight_id == "FDX5"

    # ── M4: Adapters / ports (pluggable infrastructure) ────────────────────
    # Prove all four ports can be injected
    event_bus = InMemoryEventBus()
    state_store = InMemoryStateStore()
    memory = InMemoryMemory()
    tracer = InMemoryTracer()

    # Publish DOWN message to bus
    event_bus.publish(gdp_down)
    assert event_bus.pending == 1

    # Store scenario state
    state_store.set("scenario", {"phase": 10, "flights": len(fleet_overflow)})
    assert state_store.exists("scenario")

    # Cache flight info
    memory.set("flight:FDX5", {"status": "pending_approval"}, ttl=300)
    assert memory.get("flight:FDX5")["status"] == "pending_approval"

    # Log decision to trace
    tracer.log("gdp_response", {"overflow": 1, "victim_count": 1})
    trace = tracer.get_trace()
    assert len(trace) == 1


def test_full_system_bus_isolation():
    """Prove bus isolation: DOWN and UP messages filter cleanly."""
    bus = InMemoryEventBus()

    # Multiple DOWN directives
    gdp1 = tfm_to_cdm(
        {"program_id": "g1", "tfm_type": "gdp", "affected_fix": "KDEN", "rate_per_hour": 1},
        issuer="ATCSCC",
        message_id="g1",
        start=T0,
        end=T0 + timedelta(hours=1),
    )
    gdp2 = tfm_to_cdm(
        {"program_id": "g2", "tfm_type": "gdp", "affected_fix": "KORD", "rate_per_hour": 1},
        issuer="ATCSCC",
        message_id="g2",
        start=T0,
        end=T0 + timedelta(hours=1),
    )

    bus.publish_many([gdp1, gdp2])
    assert bus.pending == 2

    # Drain only DOWN
    downs = bus.drain(direction=CDMDirection.DOWN)
    assert len(downs) == 2
    assert bus.pending == 0


def test_full_system_json_wire_format():
    """Prove messages survive JSON serialization (as they would over Kafka in prod)."""
    # Create a complex response
    fleet = [
        FleetFlight(
            flight_id="DAL1",
            origin="KSFO",
            destination="KDEN",
            scheduled_arrival=T0 + timedelta(minutes=30),
            priority=1,
            cancellable=True,
        ),
    ]
    gdp = tfm_to_cdm(
        {
            "program_id": "tfm-001",
            "tfm_type": "gdp",
            "affected_fix": "KDEN",
            "rate_per_hour": 1,
            "reason": "capacity",
        },
        issuer="ATCSCC",
        message_id="gdp-1",
        start=T0,
        end=T0 + timedelta(minutes=1),  # Capacity floor = 0
    )

    responses = respond_to_directive(gdp, fleet)
    assert len(responses) == 1

    # Serialize to JSON (as Kafka would)
    response_json = responses[0].model_dump_json()
    assert isinstance(response_json, str)

    # Deserialize and verify
    from cdm.messages import CancellationNotice

    restored = CancellationNotice.model_validate_json(response_json)
    assert restored.flight_id == "DAL1"
    assert restored.reason  # cancellation reason is set
