"""
Phase 01 — Surveillance & Track Fusion
Fuses raw ADS-B and radar contacts into unified flight tracks.
"""

from core.state import ATCState, FlightTrack, Position
from core.prompts import get_prompt
from agents.base import call_gemini, make_trace, emit_event

SYSTEM = get_prompt("phase_01.system").template

SCHEMA = """{
  "flights": [
    {
      "callsign": "AAL123",
      "squawk": "2456",
      "position": {"lat": 40.1, "lon": -74.5, "alt_ft": 25000},
      "heading_deg": 270,
      "speed_kts": 420,
      "vertical_rate_fpm": 0,
      "track_quality": 0.97,
      "data_sources": ["adsb", "radar_1"]
    }
  ],
  "fusion_notes": "Brief summary of fusion actions"
}"""


def phase_01_node(state: ATCState) -> dict:
    raw = state.get("raw_contacts", [])
    events = list(state.get("events", []))

    prompt = (
        f"Fuse these raw radar/ADS-B contacts into unified flight tracks.\n\n"
        f"Raw contacts ({len(raw)} total):\n{raw}\n\n"
        f"Output JSON matching this schema:\n{SCHEMA}"
    )

    result = call_gemini(SYSTEM, prompt)
    flights: list[FlightTrack] = result.get("flights", [])

    trace = make_trace(
        phase_number=1,
        phase_name="Surveillance & Track Fusion",
        inputs_summary={"raw_contact_count": len(raw)},
        decision=f"Fused {len(raw)} contacts into {len(flights)} tracks",
        rationale=result.get("fusion_notes", "Multi-source fusion applied"),
        outputs_summary={"track_count": len(flights)},
    )

    emit_event(events, "phase_01", "tracks_fused",
               {"track_count": len(flights), "flights": [f["callsign"] for f in flights]})

    return {
        **state,
        "current_phase": "phase_01_surveillance",
        "phases_completed": state.get("phases_completed", []) + ["phase_01"],
        "flights": flights,
        "do178c_traces": state.get("do178c_traces", []) + [trace],
        "events": events,
    }
