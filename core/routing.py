"""AeroSense ATC — deterministic conditional routers.

These are the safety-critical heart of the system: pure-Python routing decisions
(emergency squawk bypass, alert-level conflict escalation, supervisor re-check
loop) that must NEVER move into an LLM prompt. They live in this leaf module —
importing only `core.state` and langgraph's `END` sentinel — so they can be tested
in isolation without pulling in the 12 agents, Gemini, or an API key.

Extracted verbatim from core/graph.py (M0, behavior-preserving). graph.py now
imports them from here.
"""

from langgraph.graph import END

from core.hitl import get_approval_gate
from core.state import ATCState
from core.tracing import get_tracer

# Squawk codes that signal an emergency and trigger the Phase 09 bypass.
EMERGENCY_SQUAWKS = ("7700", "7600", "7500")  # general / radio-fail / hijack


def requires_tfm_approval(tfm_programs: list[dict]) -> bool:
    """True iff any active ground_stop is among the proposed TFM programs.
    A ground_stop ("stop ALL departures to a fix/airport") is the single most
    disruptive action Phase 10 can take — the high-risk autonomous action the
    AeroOps design names as needing a human gate before it takes effect."""
    return any(p.get("tfm_type") == "ground_stop" and p.get("active")
              for p in tfm_programs)


def route_after_surveillance(state: ATCState) -> str:
    """Skip to emergency if a mayday squawk is detected in raw contacts."""
    chosen = "phase_02_flight_plan"
    matched_squawk = None
    for c in state.get("raw_contacts", []):
        if c.get("squawk") in EMERGENCY_SQUAWKS:
            chosen, matched_squawk = "phase_09_emergency", c.get("squawk")
            break
    get_tracer().record_decision(
        "route_after_surveillance", trace_id=state.get("scenario_id"),
        attributes={"chosen": chosen, "matched_squawk": matched_squawk},
    )
    return chosen


def route_after_conflict(state: ATCState) -> str:
    """Skip directly to emergency handling if any alert-level conflict exists."""
    chosen = "phase_05_clearance"
    alert_conflict_id = None
    for c in state.get("conflicts", []):
        if c.get("severity") == "alert":
            chosen, alert_conflict_id = "phase_09_emergency", c.get("conflict_id")
            break
    get_tracer().record_decision(
        "route_after_conflict", trace_id=state.get("scenario_id"),
        attributes={"chosen": chosen, "alert_conflict_id": alert_conflict_id},
    )
    return chosen


def route_after_emergency(state: ATCState) -> str:
    """After emergency handling, resume normal flow at clearance generation."""
    get_tracer().record_decision(
        "route_after_emergency", trace_id=state.get("scenario_id"),
        attributes={"chosen": "phase_05_clearance"},
    )
    return "phase_05_clearance"


def route_after_supervisor(state: ATCState) -> str:
    """Supervisor triggers one conflict re-check if system health is critical;
    otherwise the graph terminates."""
    health = state.get("system_health", {})
    critical = health.get("overall_status") == "critical"
    chosen = "phase_04_conflict" if critical else "END"
    get_tracer().record_decision(
        "route_after_supervisor", trace_id=state.get("scenario_id"),
        attributes={"chosen": chosen, "overall_status": health.get("overall_status")},
    )
    return "phase_04_conflict" if critical else END


def route_after_tfm(state: ATCState) -> str:
    """Gate a proposed ground_stop behind human approval before Phase 11/12 see
    it. Writes the ApprovalRequest HERE (before the graph interrupts at
    hitl_gate) — the same lesson AutoRedTeam's HITL gate taught: the graph is
    compiled with interrupt_before=["hitl_gate"], so hitl_gate_node does not run
    until approved, meaning a write there would never be visible while paused."""
    tfm_programs = state.get("tfm_programs", [])
    needs_approval = requires_tfm_approval(tfm_programs)
    approval_id = None
    if needs_approval:
        ground_stops = [p for p in tfm_programs
                        if p.get("tfm_type") == "ground_stop" and p.get("active")]
        req = get_approval_gate().request(
            trace_id=state.get("scenario_id", ""),
            payload={"tfm_programs": ground_stops},
            reason=f"{len(ground_stops)} active ground_stop program(s) proposed",
        )
        approval_id = req.id
    chosen = "hitl_gate" if needs_approval else "phase_11_audit"
    get_tracer().record_decision(
        "route_after_tfm", trace_id=state.get("scenario_id"),
        attributes={"chosen": chosen, "approval_id": approval_id,
                    "program_count": len(tfm_programs)},
    )
    return chosen
