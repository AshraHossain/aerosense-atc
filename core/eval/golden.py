"""Golden safety-evaluation fixtures + checks.

These are self-contained golden states (kept in core/ so the eval stays a leaf —
no import of the app-level `simulation/` package) that capture the *safety-relevant*
properties of the three scenarios. Each EvalCheck asserts that the deterministic
safety layer (core.routing) does the right thing — e.g. a 7700 squawk MUST trigger
the emergency bypass. tests/integration cross-validates the same checks against the
real simulation scenarios.

Why deterministic-only: the routers are the safety-critical, LLM-free heart. Their
correct behaviour on these scenarios is knowable ground truth, so the pass-rate is
honest. Phase-agent output quality (LLM) is evaluated separately with an LLM-judge.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from core.routing import (
    route_after_conflict,
    route_after_supervisor,
    route_after_surveillance,
)

# --- Golden states (minimal, safety-focused) --------------------------------- #
GOLDEN_NOMINAL = {
    "scenario": "nominal",
    "raw_contacts": [
        {"callsign": "AAL123", "squawk": "2456"},
        {"callsign": "UAL456", "squawk": "3127"},
        {"callsign": "N12345", "squawk": "1200"},
    ],
    "conflicts": [],
    "system_health": {"overall_status": "nominal"},
}

GOLDEN_EMERGENCY = {
    "scenario": "emergency",
    "raw_contacts": [
        {"callsign": "UAL789", "squawk": "7700"},   # Mayday
        {"callsign": "AAL123", "squawk": "2456"},
    ],
    "conflicts": [],
    "system_health": {"overall_status": "degraded"},
}

GOLDEN_CONFLICT = {
    "scenario": "conflict",
    "raw_contacts": [
        {"callsign": "AAL123", "squawk": "2456"},
        {"callsign": "UAL456", "squawk": "3127"},
    ],
    # alert-level conflict synthesized: two aircraft, same FL, converging
    "conflicts": [
        {"conflict_id": "C1", "flight_a": "AAL123", "flight_b": "UAL456",
         "severity": "alert", "horiz_sep_nm": 3.0, "vert_sep_ft": 0},
    ],
    "system_health": {"overall_status": "critical"},
}

GOLDEN_STATES = {
    "nominal": GOLDEN_NOMINAL,
    "emergency": GOLDEN_EMERGENCY,
    "conflict": GOLDEN_CONFLICT,
}


@dataclass(frozen=True)
class EvalCheck:
    name: str
    category: str                      # "routing" | "structure"
    predicate: Callable[[], bool]
    description: str


# --- Safety routing checks (the heart of the eval) --------------------------- #
def _checks() -> list[EvalCheck]:
    return [
        # Emergency bypass MUST fire on a mayday squawk.
        EvalCheck(
            "emergency_squawk_triggers_bypass", "routing",
            lambda: route_after_surveillance(GOLDEN_EMERGENCY) == "phase_09_emergency",
            "7700 in raw_contacts routes straight to Phase 09",
        ),
        # Nominal traffic must NOT be diverted to emergency.
        EvalCheck(
            "nominal_proceeds_to_flight_plan", "routing",
            lambda: route_after_surveillance(GOLDEN_NOMINAL) == "phase_02_flight_plan",
            "no emergency squawk → normal flow",
        ),
        # Conflict scenario has no emergency squawk at surveillance.
        EvalCheck(
            "conflict_no_emergency_at_surveillance", "routing",
            lambda: route_after_surveillance(GOLDEN_CONFLICT) == "phase_02_flight_plan",
            "conflict is detected later (Phase 04), not at surveillance",
        ),
        # Alert-level conflict MUST escalate to emergency handling.
        EvalCheck(
            "alert_conflict_escalates", "routing",
            lambda: route_after_conflict(GOLDEN_CONFLICT) == "phase_09_emergency",
            "alert-severity conflict bypasses to Phase 09",
        ),
        # Nominal: no conflicts → proceed to clearance.
        EvalCheck(
            "nominal_no_conflict_to_clearance", "routing",
            lambda: route_after_conflict(GOLDEN_NOMINAL) == "phase_05_clearance",
            "no conflicts → clearance generation",
        ),
        # Critical health loops back for a conflict re-check.
        EvalCheck(
            "critical_health_rechecks", "routing",
            lambda: route_after_supervisor(GOLDEN_CONFLICT) == "phase_04_conflict",
            "critical system health triggers one conflict re-check",
        ),
        # Nominal health terminates cleanly.
        EvalCheck(
            "nominal_health_terminates", "routing",
            lambda: route_after_supervisor(GOLDEN_NOMINAL) != "phase_04_conflict",
            "nominal health → END (no re-check loop)",
        ),
        # --- structure checks: golden states are well-formed ---
        EvalCheck(
            "emergency_has_mayday_contact", "structure",
            lambda: any(c.get("squawk") == "7700" for c in GOLDEN_EMERGENCY["raw_contacts"]),
            "emergency golden state actually contains a mayday squawk",
        ),
        EvalCheck(
            "conflict_has_alert_severity", "structure",
            lambda: any(c.get("severity") == "alert" for c in GOLDEN_CONFLICT["conflicts"]),
            "conflict golden state contains an alert-severity conflict",
        ),
        EvalCheck(
            "nominal_has_no_emergency_squawk", "structure",
            lambda: not any(c.get("squawk") in ("7700", "7600", "7500")
                            for c in GOLDEN_NOMINAL["raw_contacts"]),
            "nominal golden state has no emergency squawks",
        ),
        EvalCheck(
            "all_contacts_have_squawk", "structure",
            lambda: all("squawk" in c for s in GOLDEN_STATES.values()
                        for c in s["raw_contacts"]),
            "every golden contact carries a squawk code",
        ),
    ]


CHECKS: list[EvalCheck] = _checks()
