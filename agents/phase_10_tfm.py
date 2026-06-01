"""
Phase 10 — Traffic Flow Management
Issues ground delay programs, miles-in-trail restrictions, and ground stops
when sector loads exceed capacity thresholds.
"""

from core.state import ATCState, TFMProgram
from core.config import SECTOR_OVERLOAD_PCT
from agents.base import call_gemini, make_trace, emit_event

SYSTEM = """You are an ATC Traffic Flow Management (TFM) Specialist.
Analyze sector loads and issue flow control programs to prevent overloads.
Program types:
  - gdp (Ground Delay Program): Delay departures at origin airports
  - miles_in_trail: Spacing requirement (e.g., 15 MIT on J146)
  - ground_stop: Stop all departures to a fix/airport (last resort)
Use the minimum intervention necessary. Prefer MIT over GDP over ground_stop.
Output only valid JSON."""

SCHEMA = """{
  "tfm_programs": [
    {
      "program_id": "TFM-001",
      "tfm_type": "miles_in_trail",
      "affected_fix": "COATE",
      "rate_per_hour": 20,
      "reason": "EAST sector at 90% capacity",
      "active": true
    }
  ],
  "tfm_notes": "summary of flow actions"
}"""


def phase_10_node(state: ATCState) -> dict:
    sectors = state.get("sectors", {})
    flights = state.get("flights", [])
    events = list(state.get("events", []))

    overloaded = {
        sid: s for sid, s in sectors.items()
        if s.get("load_pct", 0) >= SECTOR_OVERLOAD_PCT
    }

    if not overloaded:
        trace = make_trace(
            phase_number=10,
            phase_name="Traffic Flow Management",
            inputs_summary={"sectors_checked": len(sectors), "overloaded": 0},
            decision="No TFM programs required — all sectors within capacity",
            rationale=f"All sector loads below {SECTOR_OVERLOAD_PCT}% threshold",
            outputs_summary={"programs": 0},
        )
        return {
            **state,
            "current_phase": "phase_10_tfm",
            "phases_completed": state.get("phases_completed", []) + ["phase_10"],
            "tfm_programs": [],
            "do178c_traces": state.get("do178c_traces", []) + [trace],
            "events": events,
        }

    sector_summary = [
        {"sector_id": sid, "load_pct": s["load_pct"], "count": s["traffic_count"]}
        for sid, s in overloaded.items()
    ]

    prompt = (
        f"Issue TFM programs for {len(overloaded)} overloaded sectors.\n\n"
        f"Overloaded sectors:\n{sector_summary}\n\n"
        f"Total active flights: {len(flights)}\n"
        f"Overload threshold: {SECTOR_OVERLOAD_PCT}%\n\n"
        f"Output JSON matching:\n{SCHEMA}"
    )

    result = call_gemini(SYSTEM, prompt)
    programs: list[TFMProgram] = result.get("tfm_programs", [])

    ground_stops = sum(1 for p in programs if p.get("tfm_type") == "ground_stop")

    trace = make_trace(
        phase_number=10,
        phase_name="Traffic Flow Management",
        inputs_summary={"overloaded_sectors": len(overloaded), "flights": len(flights)},
        decision=f"Issued {len(programs)} TFM programs ({ground_stops} ground stops)",
        rationale=result.get("tfm_notes", "Sector capacity management — minimum intervention"),
        outputs_summary={"programs": [p["program_id"] for p in programs]},
    )

    emit_event(events, "phase_10", "tfm_programs_issued",
               {"count": len(programs),
                "programs": [{"id": p["program_id"], "type": p["tfm_type"],
                               "fix": p["affected_fix"]} for p in programs]})

    return {
        **state,
        "current_phase": "phase_10_tfm",
        "phases_completed": state.get("phases_completed", []) + ["phase_10"],
        "tfm_programs": programs,
        "do178c_traces": state.get("do178c_traces", []) + [trace],
        "events": events,
    }
