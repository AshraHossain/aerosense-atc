"""
AeroSense ATC — Shared LangGraph State
All 12 agent phases read from and write to ATCState.
"""

from typing import TypedDict, Optional


# ── Primitive building blocks ──────────────────────────────────────────────────

class Position(TypedDict):
    lat: float
    lon: float
    alt_ft: int


class FlightTrack(TypedDict):
    callsign: str
    squawk: str
    position: Position
    heading_deg: int
    speed_kts: int
    vertical_rate_fpm: int
    track_quality: float          # 0.0–1.0
    data_sources: list[str]       # e.g. ["adsb", "radar_1"]


class FlightPlan(TypedDict):
    callsign: str
    aircraft_type: str
    origin: str
    destination: str
    route: str
    requested_alt_ft: int
    filed_speed_kts: int
    etd: str
    eta: str
    valid: bool
    validation_notes: str


class Sector(TypedDict):
    sector_id: str
    name: str
    alt_low_ft: int
    alt_high_ft: int
    traffic_count: int
    load_pct: float
    controller: str


class ConflictAlert(TypedDict):
    conflict_id: str
    flight_a: str
    flight_b: str
    conflict_type: str           # "horizontal" | "vertical" | "both"
    horiz_sep_nm: float
    vert_sep_ft: int
    time_to_conflict_min: float
    severity: str                # "advisory" | "warning" | "alert"


class Clearance(TypedDict):
    clearance_id: str
    callsign: str
    clearance_type: str          # "altitude" | "heading" | "speed" | "route"
    instruction: str
    value: str
    reason: str
    resolves_conflict: Optional[str]   # conflict_id or None


class Transmission(TypedDict):
    tx_id: str
    callsign: str
    frequency: str
    text: str                    # ICAO phraseology
    tx_type: str                 # "clearance" | "readback" | "advisory"
    timestamp: str


class HandoffInstruction(TypedDict):
    handoff_id: str
    callsign: str
    from_sector: str
    to_sector: str
    transfer_alt_ft: int
    transfer_freq: str
    special_instructions: str


class WeatherHazard(TypedDict):
    hazard_id: str
    hazard_type: str             # "thunderstorm" | "turbulence" | "icing" | "sigmet"
    center: Position
    radius_nm: int
    severity: str                # "light" | "moderate" | "severe"
    affected_flights: list[str]
    recommended_action: str


class Emergency(TypedDict):
    emergency_id: str
    callsign: str
    emergency_type: str          # "mayday" | "pan_pan" | "fuel" | "medical"
    declared_at: str
    priority_level: int          # 1 = highest
    handling_instructions: str
    status: str                  # "active" | "resolved"


class TFMProgram(TypedDict):
    program_id: str
    tfm_type: str                # "gdp" | "ground_stop" | "miles_in_trail"
    affected_fix: str
    rate_per_hour: int
    reason: str
    active: bool


class DO178CTrace(TypedDict):
    """
    Formal decision trace conforming to DO-178C DAL-C traceability requirements.
    Each phase produces exactly one trace entry per run.
    """
    trace_id: str
    phase_number: int
    phase_name: str
    timestamp: str
    inputs_summary: dict
    decision: str
    rationale: str
    safety_constraints_verified: list[str]
    outputs_summary: dict
    determinism_flag: bool        # True when temperature=0.1 and seed inputs are hashed


class SystemHealth(TypedDict):
    overall_status: str           # "nominal" | "degraded" | "critical"
    phase_statuses: dict[str, str]
    anomalies: list[str]
    recommendations: list[str]


# ── Master state passed through all 12 LangGraph nodes ────────────────────────

class ATCState(TypedDict):
    # ── Scenario metadata ──────────────────────────────
    scenario_id: str
    scenario_name: str
    sim_time: str                 # ISO-8601

    # ── Phase bookkeeping ──────────────────────────────
    current_phase: str
    phases_completed: list[str]

    # ── Phase 01 — Surveillance & Track Fusion ─────────
    raw_contacts: list[dict]
    flights: list[FlightTrack]

    # ── Phase 02 — Flight Plan Parsing ─────────────────
    flight_plans: dict[str, FlightPlan]

    # ── Phase 03 — Sector Management ───────────────────
    sectors: dict[str, Sector]
    sector_assignments: dict[str, str]   # callsign -> sector_id

    # ── Phase 04 — Conflict Detection ──────────────────
    conflicts: list[ConflictAlert]

    # ── Phase 05 — Clearance Generation ────────────────
    clearances: list[Clearance]

    # ── Phase 06 — Pilot Communications ────────────────
    transmissions: list[Transmission]

    # ── Phase 07 — Handoff Coordination ────────────────
    handoffs: list[HandoffInstruction]

    # ── Phase 08 — Weather Integration ─────────────────
    weather_hazards: list[WeatherHazard]
    weather_reroutes: list[dict]

    # ── Phase 09 — Emergency Management ────────────────
    emergencies: list[Emergency]

    # ── Phase 10 — Traffic Flow Management ─────────────
    tfm_programs: list[TFMProgram]

    # ── Phase 11 — Audit & Compliance ──────────────────
    do178c_traces: list[DO178CTrace]

    # ── Phase 12 — Supervisor / Meta-Agent ─────────────
    system_health: SystemHealth
    final_report: str

    # ── Cross-phase event bus ───────────────────────────
    events: list[dict]           # free-form event log for dashboard streaming
