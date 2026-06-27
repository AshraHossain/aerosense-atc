"""
Phase 05 — Clearance Generation
Generates ATC clearances to resolve conflicts, maintaining ICAO separation standards.
DO-178C constraint: no simultaneous crossing clearances to conflicting pairs.
"""

from core.state import ATCState, Clearance
from core.config import DO178C_CONSTRAINTS
from core.prompts import get_prompt
from agents.base import call_gemini, make_trace, emit_event

SYSTEM = get_prompt("phase_05.system").template

SCHEMA = """{
  "clearances": [
    {
      "clearance_id": "CLR-001",
      "callsign": "AAL123",
      "clearance_type": "altitude",
      "instruction": "Climb and maintain FL350",
      "value": "35000",
      "reason": "Conflict resolution with UAL456",
      "resolves_conflict": "CFL-001"
    }
  ],
  "resolution_notes": "summary"
}"""


def phase_05_node(state: ATCState) -> dict:
    conflicts = state.get("conflicts", [])
    flights = state.get("flights", [])
    flight_plans = state.get("flight_plans", {})
    events = list(state.get("events", []))

    if not conflicts:
        trace = make_trace(
            phase_number=5,
            phase_name="Clearance Generation",
            inputs_summary={"conflicts": 0},
            decision="No clearances required — no active conflicts",
            rationale="No conflicts detected in Phase 04",
            outputs_summary={"clearances": 0},
        )
        emit_event(events, "phase_05", "clearances_issued", {"count": 0})
        return {
            **state,
            "current_phase": "phase_05_clearance",
            "phases_completed": state.get("phases_completed", []) + ["phase_05"],
            "clearances": [],
            "do178c_traces": state.get("do178c_traces", []) + [trace],
            "events": events,
        }

    flight_context = {
        f["callsign"]: {
            "alt_ft": f["position"]["alt_ft"],
            "heading_deg": f["heading_deg"],
            "speed_kts": f["speed_kts"],
            "requested_alt": flight_plans.get(f["callsign"], {}).get("requested_alt_ft"),
        }
        for f in flights
    }

    prompt = (
        f"Generate clearances to resolve {len(conflicts)} conflicts.\n\n"
        f"Active conflicts:\n{conflicts}\n\n"
        f"Current flight states:\n{flight_context}\n\n"
        f"Safety constraints:\n{DO178C_CONSTRAINTS[:4]}\n\n"
        f"Output JSON matching:\n{SCHEMA}"
    )

    result = call_gemini(SYSTEM, prompt)
    clearances: list[Clearance] = result.get("clearances", [])

    trace = make_trace(
        phase_number=5,
        phase_name="Clearance Generation",
        inputs_summary={"conflicts": len(conflicts), "flights": len(flights)},
        decision=f"Issued {len(clearances)} clearances resolving {len(conflicts)} conflicts",
        rationale=result.get("resolution_notes", "Minimum-intervention conflict resolution"),
        outputs_summary={"clearances": [c["clearance_id"] for c in clearances]},
        constraints=DO178C_CONSTRAINTS[:4],
    )

    emit_event(events, "phase_05", "clearances_issued",
               {"count": len(clearances),
                "details": [{"callsign": c["callsign"], "type": c["clearance_type"],
                              "instruction": c["instruction"]} for c in clearances]})

    return {
        **state,
        "current_phase": "phase_05_clearance",
        "phases_completed": state.get("phases_completed", []) + ["phase_05"],
        "clearances": clearances,
        "do178c_traces": state.get("do178c_traces", []) + [trace],
        "events": events,
    }
