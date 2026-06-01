"""
AeroSense ATC — LangGraph Orchestration
12-phase StateGraph with deterministic routing and emergency bypass.
"""

from langgraph.graph import StateGraph, END

from core.state import ATCState
from agents.phase_01_surveillance  import phase_01_node
from agents.phase_02_flight_plan   import phase_02_node
from agents.phase_03_sector        import phase_03_node
from agents.phase_04_conflict      import phase_04_node
from agents.phase_05_clearance     import phase_05_node
from agents.phase_06_comms         import phase_06_node
from agents.phase_07_handoff       import phase_07_node
from agents.phase_08_weather       import phase_08_node
from agents.phase_09_emergency     import phase_09_node
from agents.phase_10_tfm           import phase_10_node
from agents.phase_11_audit         import phase_11_node
from agents.phase_12_supervisor    import phase_12_node


# ── Conditional routers ────────────────────────────────────────────────────────

def route_after_surveillance(state: ATCState) -> str:
    """Skip to emergency if mayday detected in raw contacts."""
    for c in state.get("raw_contacts", []):
        if c.get("squawk") in ("7700", "7600", "7500"):
            return "phase_09_emergency"
    return "phase_02_flight_plan"


def route_after_conflict(state: ATCState) -> str:
    """Skip directly to emergency handling if any alert-level conflict."""
    for c in state.get("conflicts", []):
        if c.get("severity") == "alert":
            return "phase_09_emergency"
    return "phase_05_clearance"


def route_after_emergency(state: ATCState) -> str:
    """After emergency handling, resume normal flow at clearance generation."""
    return "phase_05_clearance"


def route_after_supervisor(state: ATCState) -> str:
    """
    Supervisor can trigger a re-run of conflict detection if it finds
    unresolved separation issues. Otherwise the graph terminates.
    """
    health = state.get("system_health", {})
    if health.get("overall_status") == "critical":
        return "phase_04_conflict"   # one re-check loop
    return END


# ── Build the graph ────────────────────────────────────────────────────────────

def build_atc_graph() -> StateGraph:
    workflow = StateGraph(ATCState)

    # Register all 12 nodes
    workflow.add_node("phase_01_surveillance", phase_01_node)
    workflow.add_node("phase_02_flight_plan",  phase_02_node)
    workflow.add_node("phase_03_sector",       phase_03_node)
    workflow.add_node("phase_04_conflict",     phase_04_node)
    workflow.add_node("phase_05_clearance",    phase_05_node)
    workflow.add_node("phase_06_comms",        phase_06_node)
    workflow.add_node("phase_07_handoff",      phase_07_node)
    workflow.add_node("phase_08_weather",      phase_08_node)
    workflow.add_node("phase_09_emergency",    phase_09_node)
    workflow.add_node("phase_10_tfm",          phase_10_node)
    workflow.add_node("phase_11_audit",        phase_11_node)
    workflow.add_node("phase_12_supervisor",   phase_12_node)

    # Entry point
    workflow.set_entry_point("phase_01_surveillance")

    # Conditional: emergency squawk bypass
    workflow.add_conditional_edges(
        "phase_01_surveillance",
        route_after_surveillance,
        {
            "phase_09_emergency":   "phase_09_emergency",
            "phase_02_flight_plan": "phase_02_flight_plan",
        },
    )

    # Linear: phases 2 → 3 → 4
    workflow.add_edge("phase_02_flight_plan", "phase_03_sector")
    workflow.add_edge("phase_03_sector",      "phase_04_conflict")

    # Conditional: alert-level conflict bypasses to emergency
    workflow.add_conditional_edges(
        "phase_04_conflict",
        route_after_conflict,
        {
            "phase_09_emergency": "phase_09_emergency",
            "phase_05_clearance": "phase_05_clearance",
        },
    )

    # Conditional: emergency → resume at clearance
    workflow.add_conditional_edges(
        "phase_09_emergency",
        route_after_emergency,
        {"phase_05_clearance": "phase_05_clearance"},
    )

    # Linear: phases 5 → 6 → 7 → 8 → 10 → 11 → 12
    workflow.add_edge("phase_05_clearance", "phase_06_comms")
    workflow.add_edge("phase_06_comms",     "phase_07_handoff")
    workflow.add_edge("phase_07_handoff",   "phase_08_weather")
    workflow.add_edge("phase_08_weather",   "phase_10_tfm")
    workflow.add_edge("phase_10_tfm",       "phase_11_audit")
    workflow.add_edge("phase_11_audit",     "phase_12_supervisor")

    # Conditional: supervisor can loop back to conflict check or terminate
    workflow.add_conditional_edges(
        "phase_12_supervisor",
        route_after_supervisor,
        {
            "phase_04_conflict": "phase_04_conflict",
            END: END,
        },
    )

    return workflow


# Compiled app — import this in main.py and agent tests
atc_app = build_atc_graph().compile()
