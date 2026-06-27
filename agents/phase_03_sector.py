"""
Phase 03 — Airspace Sector Management
Assigns aircraft to sectors and computes load metrics.
"""

from core.state import ATCState, Sector
from core.config import SECTORS, SECTOR_OVERLOAD_PCT
from core.prompts import get_prompt
from agents.base import call_gemini, make_trace, emit_event

SYSTEM = get_prompt("phase_03.system").template

SCHEMA = """{
  "sector_assignments": {"AAL123": "HIGH", "UAL456": "EAST"},
  "sectors": {
    "HIGH": {
      "sector_id": "HIGH",
      "name": "High Altitude En-Route",
      "alt_low_ft": 18000,
      "alt_high_ft": 45000,
      "traffic_count": 5,
      "load_pct": 25.0,
      "controller": "CTR-HIGH"
    }
  },
  "overloaded_sectors": [],
  "assignment_notes": "summary"
}"""


def phase_03_node(state: ATCState) -> dict:
    flights = state.get("flights", [])
    events = list(state.get("events", []))

    flight_data = [
        {
            "callsign": f["callsign"],
            "alt_ft": f["position"]["alt_ft"],
            "lat": f["position"]["lat"],
            "lon": f["position"]["lon"],
        }
        for f in flights
    ]

    prompt = (
        f"Assign these {len(flights)} aircraft to sectors and compute loads.\n\n"
        f"Aircraft positions:\n{flight_data}\n\n"
        f"Sector capacities: {SECTORS}\n"
        f"Overload threshold: {SECTOR_OVERLOAD_PCT}%\n\n"
        f"Output JSON matching:\n{SCHEMA}"
    )

    result = call_gemini(SYSTEM, prompt)
    sectors: dict[str, Sector] = result.get("sectors", {})
    assignments: dict[str, str] = result.get("sector_assignments", {})
    overloaded: list[str] = result.get("overloaded_sectors", [])

    trace = make_trace(
        phase_number=3,
        phase_name="Airspace Sector Management",
        inputs_summary={"flight_count": len(flights), "sectors": list(SECTORS.keys())},
        decision=f"Assigned {len(assignments)} aircraft; {len(overloaded)} overloaded sectors",
        rationale=result.get("assignment_notes", "Altitude-based sector assignment"),
        outputs_summary={"assignments": assignments, "overloaded": overloaded},
    )

    emit_event(events, "phase_03", "sectors_assigned",
               {"assignments": assignments, "overloaded": overloaded})

    return {
        **state,
        "current_phase": "phase_03_sector",
        "phases_completed": state.get("phases_completed", []) + ["phase_03"],
        "sectors": sectors,
        "sector_assignments": assignments,
        "do178c_traces": state.get("do178c_traces", []) + [trace],
        "events": events,
    }
