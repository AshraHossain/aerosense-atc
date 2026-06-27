"""
Phase 06 — Pilot Communications
Formats clearances into ICAO-standard phraseology radio transmissions.
"""

from datetime import datetime, timezone
from core.state import ATCState, Transmission
from core.config import FREQUENCIES
from core.prompts import get_prompt
from agents.base import call_gemini, make_trace, emit_event

SYSTEM = get_prompt("phase_06.system").template

SCHEMA = """{
  "transmissions": [
    {
      "tx_id": "TX-001",
      "callsign": "AAL123",
      "frequency": "132.850",
      "text": "American One Twenty Three, climb and maintain flight level three five zero, traffic.",
      "tx_type": "clearance",
      "timestamp": "2024-01-15T14:32:00Z"
    }
  ]
}"""


def phase_06_node(state: ATCState) -> dict:
    clearances = state.get("clearances", [])
    sector_assignments = state.get("sector_assignments", {})
    events = list(state.get("events", []))
    now = datetime.now(timezone.utc).isoformat()

    if not clearances:
        trace = make_trace(
            phase_number=6,
            phase_name="Pilot Communications",
            inputs_summary={"clearances": 0},
            decision="No transmissions required — no clearances to issue",
            rationale="No clearances from Phase 05",
            outputs_summary={"transmissions": 0},
        )
        return {
            **state,
            "current_phase": "phase_06_comms",
            "phases_completed": state.get("phases_completed", []) + ["phase_06"],
            "transmissions": [],
            "do178c_traces": state.get("do178c_traces", []) + [trace],
            "events": events,
        }

    clearance_context = [
        {
            "callsign": c["callsign"],
            "instruction": c["instruction"],
            "reason": c["reason"],
            "sector": sector_assignments.get(c["callsign"], "HIGH"),
            "frequency": FREQUENCIES.get(sector_assignments.get(c["callsign"], "HIGH"), "132.850"),
        }
        for c in clearances
    ]

    prompt = (
        f"Format {len(clearances)} clearances as ICAO radio transmissions.\n\n"
        f"Clearances:\n{clearance_context}\n\n"
        f"Simulation time: {now}\n\n"
        f"Output JSON matching:\n{SCHEMA}"
    )

    result = call_gemini(SYSTEM, prompt)
    transmissions: list[Transmission] = result.get("transmissions", [])

    trace = make_trace(
        phase_number=6,
        phase_name="Pilot Communications",
        inputs_summary={"clearances": len(clearances)},
        decision=f"Formatted {len(transmissions)} radio transmissions",
        rationale="ICAO Doc 9432 phraseology applied",
        outputs_summary={"transmissions": [t["tx_id"] for t in transmissions]},
    )

    emit_event(events, "phase_06", "transmissions_formatted",
               {"count": len(transmissions),
                "texts": [t["text"] for t in transmissions]})

    return {
        **state,
        "current_phase": "phase_06_comms",
        "phases_completed": state.get("phases_completed", []) + ["phase_06"],
        "transmissions": transmissions,
        "do178c_traces": state.get("do178c_traces", []) + [trace],
        "events": events,
    }
