"""
Phase 07 — Sector Handoff Coordination
Identifies aircraft approaching sector boundaries and coordinates transfers.
DO-178C HND-001: Receiving sector must acknowledge before transfer of control.
"""

from core.state import ATCState, HandoffInstruction
from core.config import FREQUENCIES
from core.prompts import get_prompt
from agents.base import call_gemini, make_trace, emit_event

SYSTEM = get_prompt("phase_07.system").template

SCHEMA = """{
  "handoffs": [
    {
      "handoff_id": "HND-001",
      "callsign": "AAL123",
      "from_sector": "HIGH",
      "to_sector": "EAST",
      "transfer_alt_ft": 18000,
      "transfer_freq": "124.350",
      "special_instructions": "Cleared direct COATE after transfer"
    }
  ],
  "handoff_notes": "summary"
}"""


def phase_07_node(state: ATCState) -> dict:
    flights = state.get("flights", [])
    sectors = state.get("sectors", {})
    assignments = state.get("sector_assignments", {})
    events = list(state.get("events", []))

    descending = [
        {
            "callsign": f["callsign"],
            "current_sector": assignments.get(f["callsign"], "HIGH"),
            "alt_ft": f["position"]["alt_ft"],
            "vertical_rate_fpm": f["vertical_rate_fpm"],
            "heading_deg": f["heading_deg"],
        }
        for f in flights
        if f["vertical_rate_fpm"] < -500 or f["vertical_rate_fpm"] > 500
    ]

    if not descending:
        trace = make_trace(
            phase_number=7,
            phase_name="Sector Handoff Coordination",
            inputs_summary={"flights_checked": len(flights), "handoff_candidates": 0},
            decision="No handoffs required — all aircraft level within sectors",
            rationale="No aircraft approaching sector boundaries",
            outputs_summary={"handoffs": 0},
        )
        return {
            **state,
            "current_phase": "phase_07_handoff",
            "phases_completed": state.get("phases_completed", []) + ["phase_07"],
            "handoffs": [],
            "do178c_traces": state.get("do178c_traces", []) + [trace],
            "events": events,
        }

    prompt = (
        f"Generate handoff instructions for {len(descending)} aircraft approaching sector boundaries.\n\n"
        f"Aircraft:\n{descending}\n\n"
        f"Sector definitions: EAST/WEST=10k-18k ft, HIGH=18k-45k ft, APCH=0-10k ft\n"
        f"Sector frequencies: {FREQUENCIES}\n\n"
        f"Output JSON matching:\n{SCHEMA}"
    )

    result = call_gemini(SYSTEM, prompt)
    handoffs: list[HandoffInstruction] = result.get("handoffs", [])

    trace = make_trace(
        phase_number=7,
        phase_name="Sector Handoff Coordination",
        inputs_summary={"candidates": len(descending), "total_flights": len(flights)},
        decision=f"Initiated {len(handoffs)} sector handoffs",
        rationale=result.get("handoff_notes", "Altitude-crossing sector boundary detection"),
        outputs_summary={"handoffs": [h["handoff_id"] for h in handoffs]},
    )

    emit_event(events, "phase_07", "handoffs_initiated",
               {"count": len(handoffs),
                "transfers": [{"callsign": h["callsign"], "from": h["from_sector"],
                                "to": h["to_sector"]} for h in handoffs]})

    return {
        **state,
        "current_phase": "phase_07_handoff",
        "phases_completed": state.get("phases_completed", []) + ["phase_07"],
        "handoffs": handoffs,
        "do178c_traces": state.get("do178c_traces", []) + [trace],
        "events": events,
    }
