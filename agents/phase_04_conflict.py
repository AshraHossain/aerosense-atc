"""
Phase 04 — Conflict Detection & Resolution Advisories
Detects separation violations and classifies severity per ICAO Doc 4444.
"""

from core.state import ATCState, ConflictAlert
from core.config import MIN_HORIZONTAL_SEP_NM, MIN_VERTICAL_SEP_FT, CONFLICT_LOOKAHEAD_MIN
from core.prompts import get_prompt
from agents.base import call_gemini, make_trace, emit_event

SYSTEM = get_prompt("phase_04.system").template

SCHEMA = """{
  "conflicts": [
    {
      "conflict_id": "CFL-001",
      "flight_a": "AAL123",
      "flight_b": "UAL456",
      "conflict_type": "horizontal",
      "horiz_sep_nm": 3.2,
      "vert_sep_ft": 2000,
      "time_to_conflict_min": 8.5,
      "severity": "warning"
    }
  ],
  "analysis_notes": "summary of analysis"
}"""


def phase_04_node(state: ATCState) -> dict:
    flights = state.get("flights", [])
    events = list(state.get("events", []))

    flight_vectors = [
        {
            "callsign": f["callsign"],
            "lat": f["position"]["lat"],
            "lon": f["position"]["lon"],
            "alt_ft": f["position"]["alt_ft"],
            "heading_deg": f["heading_deg"],
            "speed_kts": f["speed_kts"],
            "vertical_rate_fpm": f["vertical_rate_fpm"],
        }
        for f in flights
    ]

    prompt = (
        f"Detect conflicts among {len(flights)} aircraft within {CONFLICT_LOOKAHEAD_MIN} minutes.\n\n"
        f"Standards: horizontal ≥ {MIN_HORIZONTAL_SEP_NM} NM, vertical ≥ {MIN_VERTICAL_SEP_FT} ft\n\n"
        f"Flight vectors:\n{flight_vectors}\n\n"
        f"Output JSON matching:\n{SCHEMA}"
    )

    result = call_gemini(SYSTEM, prompt)
    conflicts: list[ConflictAlert] = result.get("conflicts", [])

    alert_count   = sum(1 for c in conflicts if c.get("severity") == "alert")
    warning_count = sum(1 for c in conflicts if c.get("severity") == "warning")

    trace = make_trace(
        phase_number=4,
        phase_name="Conflict Detection",
        inputs_summary={"flight_count": len(flights), "lookahead_min": CONFLICT_LOOKAHEAD_MIN},
        decision=f"Detected {len(conflicts)} conflicts: {alert_count} alerts, {warning_count} warnings",
        rationale=result.get("analysis_notes", "Vectored conflict geometry analysis"),
        outputs_summary={"total": len(conflicts), "alerts": alert_count, "warnings": warning_count},
    )

    emit_event(events, "phase_04", "conflicts_detected",
               {"conflicts": [{"id": c["conflict_id"], "severity": c["severity"],
                                "pair": [c["flight_a"], c["flight_b"]]} for c in conflicts]})

    return {
        **state,
        "current_phase": "phase_04_conflict",
        "phases_completed": state.get("phases_completed", []) + ["phase_04"],
        "conflicts": conflicts,
        "do178c_traces": state.get("do178c_traces", []) + [trace],
        "events": events,
    }
