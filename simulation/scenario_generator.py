"""
AeroSense ATC - Synthetic Scenario Generator
Generates realistic ATC scenarios without a live ADS-B feed.
Three built-in scenarios of increasing complexity.
"""

import random
import uuid
from datetime import datetime, timezone


def _flt(callsign, squawk, lat, lon, alt, hdg, spd, vrate, sources=None):
    return {
        "callsign": callsign,
        "squawk": squawk,
        "position": {"lat": lat, "lon": lon, "alt_ft": alt},
        "heading_deg": hdg,
        "speed_kts": spd,
        "vertical_rate_fpm": vrate,
        "track_quality": round(random.uniform(0.88, 0.99), 2),
        "data_sources": sources or ["adsb", "radar_1"],
        "type": "aircraft",
    }


SCENARIOS = {
    "nominal": {
        "name": "Nominal Operations - New York ARTCC",
        "description": "10 aircraft in cruise/descent, no conflicts, standard handoffs expected.",
        "contacts": [
            _flt("AAL123", "2456", 41.2, -74.5, 35000, 270, 450, 0),
            _flt("UAL456", "3127", 40.8, -73.9, 33000, 255, 440, -200),
            _flt("DAL321", "1803", 40.5, -74.8, 31000, 280, 430, 0),
            _flt("SWA789", "0741", 40.1, -75.2, 28000, 260, 420, -500),
            _flt("JBU202", "2201", 41.5, -73.5, 38000, 265, 460, 0),
            _flt("FDX901", "4401", 40.9, -74.1, 25000, 90,  400, -800),
            _flt("UPS312", "3301", 41.1, -74.9, 27000, 85,  390, -600),
            _flt("AAL550", "2789", 40.3, -73.7, 36000, 270, 455, 0),
            _flt("N12345", "1200", 40.6, -74.3, 8500,  260, 130, -300, ["radar_1"]),
            _flt("N67890", "1200", 40.7, -74.6, 6500,  270, 120, -400, ["radar_1"]),
        ],
    },

    "conflict": {
        "name": "Conflict Scenario - Merging Traffic",
        "description": "Two high-altitude aircraft on converging courses; sector overload on HIGH.",
        "contacts": [
            _flt("AAL123", "2456", 41.0, -74.0, 35000, 270, 450, 0),
            _flt("UAL456", "3127", 41.2, -76.0, 35000, 90,  450, 0),   # converging, same FL
            _flt("DAL321", "1803", 40.5, -74.8, 31000, 275, 430, 0),
            _flt("SWA789", "0741", 40.8, -74.2, 35000, 265, 445, 0),
            _flt("JBU202", "2201", 41.5, -73.5, 37000, 270, 460, 0),
            _flt("FDX901", "4401", 40.2, -74.5, 33000, 80,  400, 0),
            _flt("AAL550", "2789", 41.3, -75.1, 35000, 95,  440, 0),   # third potential conflict
            _flt("UAL789", "3456", 40.9, -73.8, 34000, 260, 435, 0),
            _flt("DAL100", "1901", 40.6, -74.7, 35000, 270, 450, 0),
            _flt("NKS221", "5512", 41.1, -74.4, 35000, 265, 430, 0),
            _flt("B6044",  "7890", 40.4, -74.1, 31000, 280, 420, -300),
            _flt("AAL999", "1234", 40.7, -75.0, 29000, 270, 410, -500),
        ],
    },

    "emergency": {
        "name": "Emergency Scenario - Mayday + Weather",
        "description": "Aircraft declares Mayday (squawk 7700), severe weather cell, sector overload.",
        "contacts": [
            _flt("UAL789", "7700", 40.8, -74.2, 22000, 270, 300, -2000),  # Mayday - rapid descent
            _flt("AAL123", "2456", 41.0, -74.5, 35000, 270, 450, 0),
            _flt("DAL321", "1803", 40.5, -74.8, 31000, 265, 430, 0),
            _flt("SWA789", "0741", 40.2, -73.9, 28000, 280, 420, -500),
            _flt("JBU202", "2201", 41.4, -73.6, 38000, 265, 460, 0),
            _flt("FDX901", "4401", 40.9, -74.1, 25000, 90,  400, -800),
            _flt("AAL550", "2789", 40.6, -74.4, 33000, 270, 445, 0),
            _flt("NKS221", "5512", 41.2, -74.7, 35000, 268, 435, 0),
            _flt("DAL100", "1901", 40.3, -75.1, 29000, 272, 415, -400),
            {
                "type": "weather",
                "hazard_type": "thunderstorm",
                "position": {"lat": 40.5, "lon": -75.0, "alt_ft": 30000},
                "radius_nm": 25,
                "severity": "severe",
                "sigmet": "SIGMET NOVEMBER 3 VALID 1430/1830Z - ISOLD SEV TS OVR NJ/PA MOVG NE AT 20KT",
            },
        ],
    },
}


def generate_scenario(scenario_key: str = "nominal") -> dict:
    """Return an ATCState-compatible initial state dict for the given scenario."""
    if scenario_key not in SCENARIOS:
        scenario_key = "nominal"

    scn = SCENARIOS[scenario_key]
    scenario_id = f"{scenario_key}-{uuid.uuid4().hex[:8]}"
    sim_time = datetime.now(timezone.utc).isoformat()

    return {
        "scenario_id": scenario_id,
        "scenario_name": scn["name"],
        "sim_time": sim_time,
        "current_phase": "init",
        "phases_completed": [],
        "raw_contacts": scn["contacts"],
        "flights": [],
        "flight_plans": {},
        "sectors": {},
        "sector_assignments": {},
        "conflicts": [],
        "clearances": [],
        "transmissions": [],
        "handoffs": [],
        "weather_hazards": [],
        "weather_reroutes": [],
        "emergencies": [],
        "tfm_programs": [],
        "do178c_traces": [],
        "system_health": {
            "overall_status": "nominal",
            "phase_statuses": {},
            "anomalies": [],
            "recommendations": [],
        },
        "final_report": "",
        "events": [
            {
                "timestamp": sim_time,
                "phase": "init",
                "type": "scenario_started",
                "data": {
                    "scenario_id": scenario_id,
                    "scenario_name": scn["name"],
                    "contact_count": len(scn["contacts"]),
                    "description": scn["description"],
                },
            }
        ],
    }


def list_scenarios() -> list:
    return [
        {"key": k, "name": v["name"], "description": v["description"]}
        for k, v in SCENARIOS.items()
    ]
