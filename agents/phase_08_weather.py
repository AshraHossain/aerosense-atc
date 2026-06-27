"""
Phase 08 — Weather Integration
Integrates weather hazards, identifies affected flights, and recommends reroutes.
"""

from core.state import ATCState, WeatherHazard
from core.prompts import get_prompt
from agents.base import call_gemini, make_trace, emit_event

SYSTEM = get_prompt("phase_08.system").template

SCHEMA = """{
  "weather_hazards": [
    {
      "hazard_id": "WX-001",
      "hazard_type": "thunderstorm",
      "center": {"lat": 40.5, "lon": -75.0, "alt_ft": 25000},
      "radius_nm": 20,
      "severity": "severe",
      "affected_flights": ["AAL123"],
      "recommended_action": "Deviate 30 degrees right of course"
    }
  ],
  "weather_reroutes": [
    {"callsign": "AAL123", "original_route": "DCT COATE", "revised_route": "DCT MERIT"}
  ],
  "wx_summary": "brief summary"
}"""


def phase_08_node(state: ATCState) -> dict:
    flights = state.get("flights", [])
    flight_plans = state.get("flight_plans", {})
    # Simulated weather data embedded in scenario (pulled from raw_contacts metadata)
    raw = state.get("raw_contacts", [])
    wx_data = [c for c in raw if c.get("type") == "weather"]
    events = list(state.get("events", []))

    flight_routes = [
        {
            "callsign": f["callsign"],
            "lat": f["position"]["lat"],
            "lon": f["position"]["lon"],
            "alt_ft": f["position"]["alt_ft"],
            "route": flight_plans.get(f["callsign"], {}).get("route", "DIRECT"),
        }
        for f in flights
    ]

    prompt = (
        f"Analyze weather hazards for {len(flights)} flights.\n\n"
        f"Active flights and routes:\n{flight_routes}\n\n"
        f"Weather reports (SIGMETs/AIRMETs):\n{wx_data if wx_data else 'Standard convective activity in region. One moderate CB at 40.5N 75.0W.'}\n\n"
        f"Output JSON matching:\n{SCHEMA}"
    )

    result = call_gemini(SYSTEM, prompt)
    hazards: list[WeatherHazard] = result.get("weather_hazards", [])
    reroutes: list[dict] = result.get("weather_reroutes", [])

    severe = sum(1 for h in hazards if h.get("severity") == "severe")

    trace = make_trace(
        phase_number=8,
        phase_name="Weather Integration",
        inputs_summary={"flights": len(flights), "wx_reports": len(wx_data) or 1},
        decision=f"Identified {len(hazards)} hazards ({severe} severe); {len(reroutes)} reroutes recommended",
        rationale=result.get("wx_summary", "SIGMET/AIRMET analysis against active routes"),
        outputs_summary={"hazards": len(hazards), "reroutes": len(reroutes)},
    )

    emit_event(events, "phase_08", "weather_assessed",
               {"hazards": len(hazards), "severe": severe, "reroutes": len(reroutes)})

    return {
        **state,
        "current_phase": "phase_08_weather",
        "phases_completed": state.get("phases_completed", []) + ["phase_08"],
        "weather_hazards": hazards,
        "weather_reroutes": reroutes,
        "do178c_traces": state.get("do178c_traces", []) + [trace],
        "events": events,
    }
