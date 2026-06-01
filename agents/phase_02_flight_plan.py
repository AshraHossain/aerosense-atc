"""
Phase 02 — Flight Plan Parsing & Validation
Parses ICAO flight plans and validates routes, altitudes, and speeds.
"""

from core.state import ATCState, FlightPlan
from agents.base import call_gemini, make_trace, emit_event

SYSTEM = """You are an ATC Flight Plan Analyst.
Parse and validate ICAO flight plans. Check for:
- Valid origin/destination ICAO codes
- Feasible route waypoints
- Altitude within aircraft performance envelope
- Filed speed appropriate for aircraft type
Flag any anomalies in validation_notes.
Output only valid JSON."""

SCHEMA = """{
  "flight_plans": {
    "AAL123": {
      "callsign": "AAL123",
      "aircraft_type": "B738",
      "origin": "KJFK",
      "destination": "KLAX",
      "route": "HAPIE DCT COATE J146 DUSTY DCT",
      "requested_alt_ft": 35000,
      "filed_speed_kts": 450,
      "etd": "14:30Z",
      "eta": "17:45Z",
      "valid": true,
      "validation_notes": ""
    }
  },
  "validation_summary": "X of Y plans valid"
}"""


def phase_02_node(state: ATCState) -> dict:
    flights = state.get("flights", [])
    raw_plans = state.get("raw_contacts", [])
    events = list(state.get("events", []))

    callsigns = [f["callsign"] for f in flights]

    prompt = (
        f"Parse and validate flight plans for these tracked aircraft: {callsigns}\n\n"
        f"Raw data available:\n{raw_plans}\n\n"
        f"If a flight plan is missing, generate a plausible one based on callsign.\n"
        f"Output JSON matching:\n{SCHEMA}"
    )

    result = call_gemini(SYSTEM, prompt)
    flight_plans: dict[str, FlightPlan] = result.get("flight_plans", {})

    invalid = [cs for cs, fp in flight_plans.items() if not fp.get("valid")]
    trace = make_trace(
        phase_number=2,
        phase_name="Flight Plan Parsing & Validation",
        inputs_summary={"callsigns": callsigns, "plan_count": len(flight_plans)},
        decision=f"Validated {len(flight_plans)} plans; {len(invalid)} invalid",
        rationale=result.get("validation_summary", "ICAO flight plan validation applied"),
        outputs_summary={"valid": len(flight_plans) - len(invalid), "invalid": invalid},
    )

    emit_event(events, "phase_02", "plans_validated",
               {"total": len(flight_plans), "invalid": invalid})

    return {
        **state,
        "current_phase": "phase_02_flight_plan",
        "phases_completed": state.get("phases_completed", []) + ["phase_02"],
        "flight_plans": flight_plans,
        "do178c_traces": state.get("do178c_traces", []) + [trace],
        "events": events,
    }
