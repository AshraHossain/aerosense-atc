"""
AeroSense ATC — Global Configuration
"""

import os
from dotenv import load_dotenv
import google.generativeai as genai

load_dotenv()

# ── Google Gemini ──────────────────────────────────────────────────────────────
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "")
if not GOOGLE_API_KEY:
    raise RuntimeError("GOOGLE_API_KEY environment variable is required.")

genai.configure(api_key=GOOGLE_API_KEY)

MODEL_NAME = "gemini-2.0-flash"

# Low temperature for determinism — critical for DO-178C compliance
AGENT_TEMPERATURE = 0.1

# ── Server ─────────────────────────────────────────────────────────────────────
HOST = os.environ.get("AEROSENSE_HOST", "0.0.0.0")
PORT = int(os.environ.get("AEROSENSE_PORT", "8000"))
LOG_TRACES = os.environ.get("AEROSENSE_LOG_TRACES", "true").lower() == "true"

# ── ATC Safety Standards (ICAO Doc 4444 / FAA 7110.65) ────────────────────────
MIN_HORIZONTAL_SEP_NM = 5.0       # Minimum radar separation
MIN_VERTICAL_SEP_FT   = 1000      # Standard vertical separation (FL290 and below)
MIN_VERTICAL_SEP_HI   = 2000      # RVSM: 1000ft; non-RVSM above FL290: 2000ft
CONFLICT_LOOKAHEAD_MIN = 15       # Look 15 minutes ahead for conflicts
SECTOR_OVERLOAD_PCT   = 85        # Trigger TFM at 85% sector capacity

# ── Airspace Sectors (simplified TRACON/ARTCC) ─────────────────────────────────
SECTORS: dict[str, dict] = {
    "EAST": {
        "name": "East Arrival",
        "alt_low_ft": 10_000,
        "alt_high_ft": 18_000,
        "controller": "CTR-EAST",
        "capacity": 12,
    },
    "WEST": {
        "name": "West Arrival",
        "alt_low_ft": 10_000,
        "alt_high_ft": 18_000,
        "controller": "CTR-WEST",
        "capacity": 12,
    },
    "HIGH": {
        "name": "High Altitude En-Route",
        "alt_low_ft": 18_000,
        "alt_high_ft": 45_000,
        "controller": "CTR-HIGH",
        "capacity": 20,
    },
    "APCH": {
        "name": "Approach Control",
        "alt_low_ft": 0,
        "alt_high_ft": 10_000,
        "controller": "APP-CTL",
        "capacity": 8,
    },
}

# ── Frequencies ────────────────────────────────────────────────────────────────
FREQUENCIES: dict[str, str] = {
    "EAST": "124.350",
    "WEST": "119.100",
    "HIGH": "132.850",
    "APCH": "121.500",
    "GUARD": "121.500",
    "ATIS":  "135.175",
}

# ── DO-178C Safety Constraints (referenced in every trace) ────────────────────
DO178C_CONSTRAINTS = [
    "SEP-001: Horizontal separation ≥ 5 NM maintained at all times",
    "SEP-002: Vertical separation ≥ 1000 ft maintained below FL290",
    "SEP-003: No simultaneous crossing clearances to conflicting aircraft",
    "COM-001: All clearances issued in ICAO standard phraseology",
    "HND-001: Receiving sector acknowledged before transfer of control",
    "EMG-001: Emergency aircraft given priority over all other traffic",
    "TFM-001: Sector load must not exceed defined capacity",
    "AUD-001: Every decision recorded with rationale before execution",
]
