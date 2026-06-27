"""
Phase 09 — Emergency Management
Handles Mayday/Pan-Pan declarations, squawk 7700/7600/7500.
DO-178C EMG-001: Emergency aircraft given absolute priority.
"""

from datetime import datetime, timezone
from core.state import ATCState, Emergency
from core.config import DO178C_CONSTRAINTS
from core.prompts import get_prompt
from agents.base import call_gemini, make_trace, emit_event

SYSTEM = get_prompt("phase_09.system").template

SCHEMA = """{
  "emergencies": [
    {
      "emergency_id": "EMG-001",
      "callsign": "UAL789",
      "emergency_type": "mayday",
      "declared_at": "2024-01-15T14:33:00Z",
      "priority_level": 1,
      "handling_instructions": "Cleared direct to KJFK, descend at pilot's discretion. Runway 31L reserved. CFR on standby.",
      "status": "active"
    }
  ],
  "airspace_cleared": ["UAL456", "DAL321"],
  "notifications": ["CFR notified", "ATCSCC notified"],
  "emergency_notes": "summary"
}"""


def phase_09_node(state: ATCState) -> dict:
    flights = state.get("flights", [])
    raw_contacts = state.get("raw_contacts", [])
    existing_emergencies = state.get("emergencies", [])
    events = list(state.get("events", []))
    now = datetime.now(timezone.utc).isoformat()

    # Detect emergency squawks
    emergency_squawks = {
        "7700": "mayday",
        "7600": "radio_failure",
        "7500": "hijack",
    }
    emergency_flights = [
        {"callsign": f["callsign"], "squawk": f["squawk"],
         "type": emergency_squawks.get(f["squawk"], "pan_pan"),
         "position": f["position"]}
        for f in flights
        if f.get("squawk") in emergency_squawks
    ]

    # Also check raw contacts for declared emergencies
    declared = [c for c in raw_contacts if c.get("emergency")]
    all_emergency_data = emergency_flights + declared

    if not all_emergency_data and not existing_emergencies:
        trace = make_trace(
            phase_number=9,
            phase_name="Emergency Management",
            inputs_summary={"emergency_squawks": 0, "existing": 0},
            decision="No emergencies — normal operations continue",
            rationale="No emergency squawks or declarations detected",
            outputs_summary={"emergencies": 0},
        )
        return {
            **state,
            "current_phase": "phase_09_emergency",
            "phases_completed": state.get("phases_completed", []) + ["phase_09"],
            "emergencies": existing_emergencies,
            "do178c_traces": state.get("do178c_traces", []) + [trace],
            "events": events,
        }

    nearby_traffic = [
        {"callsign": f["callsign"], "position": f["position"]}
        for f in flights
        if f.get("squawk") not in emergency_squawks
    ]

    prompt = (
        f"Handle aviation emergency at simulation time {now}.\n\n"
        f"Emergency aircraft:\n{all_emergency_data}\n\n"
        f"Nearby traffic to clear:\n{nearby_traffic}\n\n"
        f"Safety constraint: {DO178C_CONSTRAINTS[4]}\n\n"  # EMG-001
        f"Output JSON matching:\n{SCHEMA}"
    )

    result = call_gemini(SYSTEM, prompt)
    emergencies: list[Emergency] = result.get("emergencies", [])
    cleared: list[str] = result.get("airspace_cleared", [])
    notifications: list[str] = result.get("notifications", [])

    trace = make_trace(
        phase_number=9,
        phase_name="Emergency Management",
        inputs_summary={"emergency_count": len(all_emergency_data), "nearby_traffic": len(nearby_traffic)},
        decision=f"Managing {len(emergencies)} emergencies; cleared {len(cleared)} aircraft from area",
        rationale=result.get("emergency_notes", "Emergency priority handling per ICAO Annex 2"),
        outputs_summary={"emergencies": [e["emergency_id"] for e in emergencies],
                         "cleared": cleared, "notifications": notifications},
        constraints=[DO178C_CONSTRAINTS[4]],  # EMG-001
    )

    emit_event(events, "phase_09", "emergency_declared",
               {"emergencies": [{"callsign": e["callsign"], "type": e["emergency_type"],
                                  "priority": e["priority_level"]} for e in emergencies],
                "cleared": cleared})

    return {
        **state,
        "current_phase": "phase_09_emergency",
        "phases_completed": state.get("phases_completed", []) + ["phase_09"],
        "emergencies": emergencies,
        "do178c_traces": state.get("do178c_traces", []) + [trace],
        "events": events,
    }
