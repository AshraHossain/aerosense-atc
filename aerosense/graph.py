"""
AeroSense ATC — LangGraph Orchestration
12-phase StateGraph with deterministic routing and emergency bypass.

Lives in the `aerosense/` app package (not `core/`) because it imports the 12
agents: per the AeroOps invariant, app code may depend on core + agents, but
`core/` must depend on neither. The deterministic routers it wires come from
`core.routing` (testable in isolation); this module only assembles them.
"""

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import StateGraph, END

from core.hitl import hitl_gate_node
from core.state import ATCState
from core.routing import (
    route_after_surveillance,
    route_after_conflict,
    route_after_emergency,
    route_after_supervisor,
    route_after_tfm,
)
from core.tracing import traced_node
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


# ── Build the graph ────────────────────────────────────────────────────────────

def build_atc_graph() -> StateGraph:
    workflow = StateGraph(ATCState)

    # Register all 12 nodes, each wrapped in a "node" span (traced_node uses
    # state["scenario_id"] as the trace id, so every span for one scenario run —
    # including the nested "llm" spans from call_gemini — shares one trace).
    workflow.add_node("phase_01_surveillance", traced_node("phase_01_surveillance")(phase_01_node))
    workflow.add_node("phase_02_flight_plan",  traced_node("phase_02_flight_plan")(phase_02_node))
    workflow.add_node("phase_03_sector",       traced_node("phase_03_sector")(phase_03_node))
    workflow.add_node("phase_04_conflict",     traced_node("phase_04_conflict")(phase_04_node))
    workflow.add_node("phase_05_clearance",    traced_node("phase_05_clearance")(phase_05_node))
    workflow.add_node("phase_06_comms",        traced_node("phase_06_comms")(phase_06_node))
    workflow.add_node("phase_07_handoff",      traced_node("phase_07_handoff")(phase_07_node))
    workflow.add_node("phase_08_weather",      traced_node("phase_08_weather")(phase_08_node))
    workflow.add_node("phase_09_emergency",    traced_node("phase_09_emergency")(phase_09_node))
    workflow.add_node("phase_10_tfm",          traced_node("phase_10_tfm")(phase_10_node))
    workflow.add_node("phase_11_audit",        traced_node("phase_11_audit")(phase_11_node))
    workflow.add_node("phase_12_supervisor",   traced_node("phase_12_supervisor")(phase_12_node))
    workflow.add_node("hitl_gate",             traced_node("hitl_gate")(hitl_gate_node))

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

    # Linear: phases 5 → 6 → 7 → 8 → 10
    workflow.add_edge("phase_05_clearance", "phase_06_comms")
    workflow.add_edge("phase_06_comms",     "phase_07_handoff")
    workflow.add_edge("phase_07_handoff",   "phase_08_weather")
    workflow.add_edge("phase_08_weather",   "phase_10_tfm")

    # Conditional: an active ground_stop (the most disruptive TFM action) pauses
    # for human approval before Phase 11/12 see it; everything else proceeds.
    workflow.add_conditional_edges(
        "phase_10_tfm",
        route_after_tfm,
        {"hitl_gate": "hitl_gate", "phase_11_audit": "phase_11_audit"},
    )
    workflow.add_edge("hitl_gate",      "phase_11_audit")
    workflow.add_edge("phase_11_audit", "phase_12_supervisor")

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


# Process-wide checkpointer. There is only one compile() call site (this module
# is imported once), so — unlike a multi-route API where fire and resume might
# each build a fresh graph — there's no risk of two MemorySavers existing for the
# same run; this one instance is all any caller ever sees as `atc_app`.
_CHECKPOINTER = MemorySaver()

# Compiled app — import this in main.py and agent tests. interrupt_before pauses
# the graph the moment it would run hitl_gate (i.e. only when route_after_tfm
# chose it); every other scenario completes in a single invoke()/stream() call
# exactly as before this gate existed.
atc_app = build_atc_graph().compile(checkpointer=_CHECKPOINTER, interrupt_before=["hitl_gate"])
