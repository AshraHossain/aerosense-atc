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

from core.state import ATCState

# Squawk codes that signal an emergency and trigger the Phase 09 bypass.
EMERGENCY_SQUAWKS = ("7700", "7600", "7500")  # general / radio-fail / hijack


def route_after_surveillance(state: ATCState) -> str:
    """Skip to emergency if a mayday squawk is detected in raw contacts."""
    for c in state.get("raw_contacts", []):
        if c.get("squawk") in EMERGENCY_SQUAWKS:
            return "phase_09_emergency"
    return "phase_02_flight_plan"


def route_after_conflict(state: ATCState) -> str:
    """Skip directly to emergency handling if any alert-level conflict exists."""
    for c in state.get("conflicts", []):
        if c.get("severity") == "alert":
            return "phase_09_emergency"
    return "phase_05_clearance"


def route_after_emergency(state: ATCState) -> str:
    """After emergency handling, resume normal flow at clearance generation."""
    return "phase_05_clearance"


def route_after_supervisor(state: ATCState) -> str:
    """Supervisor triggers one conflict re-check if system health is critical;
    otherwise the graph terminates."""
    health = state.get("system_health", {})
    if health.get("overall_status") == "critical":
        return "phase_04_conflict"  # one re-check loop
    return END
