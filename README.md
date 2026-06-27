# AeroSense ATC

A 12-phase multi-agent Air Traffic Control system powered by Google Gemini and LangGraph. Each phase is a dedicated AI agent that processes the shared ATC state — from raw radar contacts through to a DO-178C-inspired supervisor report — with deterministic routing and emergency bypass logic built into the graph.

---

## Platform direction (AeroOps)

AeroSense ATC is being grown into a two-app platform that mirrors the real
FAA↔airline operating structure, connected by a **Collaborative Decision Making
(CDM)** message seam:

- **AeroSense ATC** — the air-traffic-control sector controller (FAA side): single-node,
  LangGraph + in-memory backends.
- **AeroCommand AOC** — the airline Operations Control Center (airline side): crew,
  maintenance, passenger, finance, compliance; distributed Kafka/Postgres/Redis backends.

Both apps share one `core/` library (agent base, evals, tracing, audit, HITL) and
differ only in their domain agents and which infrastructure adapters are injected
(ports & adapters). Full design: [`docs/superpowers/specs/2026-06-26-aeroops-platform-design.md`](docs/superpowers/specs/2026-06-26-aeroops-platform-design.md).
Plan-review / pitched-vs-built comparison lives on the `plan-review` branch.

**Milestone status:** **Platform complete (M0–M4)** — 232 tests, all green.
- ✓ **M0** (56 tests): core extraction, routers, state contract → merged to `master`
- ✓ **M1** (86 tests): evals, audit, HITL, LangSmith observability → merged to `master`
- ✓ **M2** (65 tests): CDM seam (messages + transport + translator) → PR #1
- ✓ **M3** (93 tests): AOC responder + e2e round-trip → PR #2, #3
- ✓ **M4** (19 tests): distributed adapters (Kafka/Postgres/Redis + Docker) → PR #4
- ✓ **E2E Smoke** (3 tests): full system integration proof

[Full architecture guide here.](docs/ARCHITECTURE.md)

---

## Overview

AeroSense ATC models the full ATC decision pipeline as a directed state graph. A single scenario (a set of raw ADS-B/radar contacts) enters at Phase 01 and propagates through all 12 phases, with each agent reading from and writing back to the shared `ATCState`. The final output is a structured system-health assessment and a watch-supervisor brief.

```
Raw Contacts
     │
     ▼
Phase 01 — Surveillance & Track Fusion
     │  (emergency squawk bypass →)
     ▼
Phase 02 — Flight Plan Parsing
     ▼
Phase 03 — Sector Management
     ▼
Phase 04 — Conflict Detection
     │  (alert-level conflict bypass →)
     ▼
Phase 05 — Clearance Generation  ◄─── Emergency bypass lands here
     ▼
Phase 06 — Pilot Communications (ICAO phraseology)
     ▼
Phase 07 — Handoff Coordination
     ▼
Phase 08 — Weather Integration
     │
     │  (Phase 09 — Emergency Management runs as bypass node)
     │
     ▼
Phase 10 — Traffic Flow Management (GDP / ground stop)
     ▼
Phase 11 — Audit & DO-178C Compliance
     ▼
Phase 12 — Supervisor / Meta-Agent (CrewAI crew)
     │  (critical health → re-run Phase 04)
     ▼
   END
```

The graph is compiled once at import time (`core/graph.py`) and reused across all scenario invocations.

---

## Features

- **12 specialised Gemini agents** — each phase has its own system prompt, JSON output schema, and DO-178C trace entry
- **Deterministic routing** — conditional edges handle emergency squawk bypass (7700/7600/7500), alert-level conflict escalation, and supervisor re-check loops
- **DO-178C DAL-C traceability** — every phase produces a cryptographically-hashed decision trace; Phase 11 consolidates them into a `.jsonl` audit file
- **CrewAI supervisor** — Phase 12 runs a two-agent CrewAI crew (Safety Validator + Watch Supervisor Reporter) that falls back to a direct Gemini call if CrewAI is unavailable
- **Three built-in scenarios** — Nominal, Conflict, and Emergency, covering increasing levels of ATC complexity
- **Cross-phase event bus** — structured events emitted by every phase, available for real-time dashboard streaming
- **ICAO standards** — separation minima (5 NM / 1000 ft), phraseology (Doc 9432), sector capacity (ICAO Doc 4444), emergency priority (Annex 2)

---

## Project Structure

```
aerosense-atc/
├── agents/
│   ├── base.py                  # Gemini call helper, DO-178C trace builder, event emitter
│   ├── phase_01_surveillance.py # ADS-B + radar fusion
│   ├── phase_02_flight_plan.py  # Flight plan validation
│   ├── phase_03_sector.py       # Sector assignment & load
│   ├── phase_04_conflict.py     # Separation violation detection
│   ├── phase_05_clearance.py    # Conflict resolution clearances
│   ├── phase_06_comms.py        # ICAO radio phraseology
│   ├── phase_07_handoff.py      # Sector transfer coordination
│   ├── phase_08_weather.py      # Hazard integration & reroutes
│   ├── phase_09_emergency.py    # Mayday / Pan-Pan / squawk handling
│   ├── phase_10_tfm.py          # GDP, ground stop, miles-in-trail
│   ├── phase_11_audit.py        # DO-178C compliance & trace export
│   └── phase_12_supervisor.py   # CrewAI meta-agent + final report
├── core/
│   ├── config.py                # Gemini config, ICAO constants, sector definitions
│   ├── graph.py                 # LangGraph StateGraph — routing & compilation
│   └── state.py                 # ATCState TypedDict + all sub-types
├── simulation/
│   └── scenario_generator.py    # Three synthetic ATC scenarios
├── api/                         # FastAPI server (scaffolding — not yet wired)
├── dashboard/
│   └── index.html               # Operator dashboard (HTML)
├── traces/                      # DO-178C JSONL audit logs (runtime, gitignored)
├── .planning/
│   └── graphs/                  # Graphify knowledge graph (graph.json, graph.html)
├── main.py                      # Entry point (stub)
├── requirements.txt             # Pinned dependencies
└── pyproject.toml               # uv-managed project config
```

---

## Agents at a Glance

| Phase | Agent | Key output |
|-------|-------|-----------|
| 01 | Surveillance & Track Fusion | `flights[]` — deduplicated tracks with quality score |
| 02 | Flight Plan Parsing | `flight_plans{}` — validated plans keyed by callsign |
| 03 | Sector Management | `sectors{}`, `sector_assignments{}` — load & controller |
| 04 | Conflict Detection | `conflicts[]` — advisory / warning / alert with geometry |
| 05 | Clearance Generation | `clearances[]` — altitude/heading/speed instructions |
| 06 | Pilot Communications | `transmissions[]` — ICAO phraseology radio text |
| 07 | Handoff Coordination | `handoffs[]` — sector transfer with frequency & alt |
| 08 | Weather Integration | `weather_hazards[]`, `weather_reroutes[]` |
| 09 | Emergency Management | `emergencies[]` — priority handling, airspace clearing |
| 10 | Traffic Flow Mgmt | `tfm_programs[]` — GDP / ground stop / MIT |
| 11 | Audit & Compliance | `do178c_traces[]` + JSONL file write |
| 12 | Supervisor (CrewAI) | `system_health`, `final_report` |

---

## State Model

All 12 agents share a single `ATCState` TypedDict defined in `core/state.py`. Each phase reads the fields it needs and returns an updated dict merged over the existing state.

Key sub-types:

| Type | Fields |
|------|--------|
| `FlightTrack` | callsign, squawk, position (lat/lon/alt), heading, speed, vrate, quality, sources |
| `ConflictAlert` | pair, type (horizontal/vertical/both), separations, time-to-conflict, severity |
| `Clearance` | instruction, type (altitude/heading/speed/route), conflict reference |
| `Transmission` | ICAO text, frequency, tx_type |
| `DO178CTrace` | phase, timestamp, SHA-256 input hash, decision, rationale, constraints |
| `SystemHealth` | overall_status (nominal/degraded/critical), phase statuses, anomalies |

---

## Safety & Compliance

Every Gemini call runs at `temperature=0.1` for near-deterministic output. Each phase's input is SHA-256 hashed and stored in its trace entry (`determinism_flag=True`).

Eight DO-178C DAL-C constraints are verified on every run:

| ID | Constraint |
|----|-----------|
| SEP-001 | Horizontal separation ≥ 5 NM at all times |
| SEP-002 | Vertical separation ≥ 1000 ft below FL290 |
| SEP-003 | No simultaneous crossing clearances to conflicting aircraft |
| COM-001 | All clearances in ICAO standard phraseology |
| HND-001 | Receiving sector acknowledged before transfer of control |
| EMG-001 | Emergency aircraft given priority over all other traffic |
| TFM-001 | Sector load must not exceed defined capacity |
| AUD-001 | Every decision recorded with rationale before execution |

Phase 11 writes a `.jsonl` trace file to `traces/<scenario_id>_traces.jsonl` containing the audit summary followed by one JSON object per phase trace.

---

## Prerequisites

- Python 3.12+
- A Google Gemini API key with access to `gemini-2.0-flash` (paid tier recommended — the free tier has low per-day/per-minute quotas)

---

## Setup

**Using uv (recommended):**

```bash
uv sync
```

**Using pip:**

```bash
python -m pip install -r requirements.txt
```

**Configure environment:**

```bash
cp .env.example .env
# Edit .env and set GOOGLE_API_KEY
```

`.env.example`:

```
GOOGLE_API_KEY=your_key_here
AEROSENSE_HOST=0.0.0.0
AEROSENSE_PORT=8000
AEROSENSE_LOG_TRACES=true
```

---

## Running a Scenario

```python
from simulation.scenario_generator import generate_scenario
from core.graph import atc_app

# "nominal" | "conflict" | "emergency"
scenario = generate_scenario("conflict")
result = atc_app.invoke(scenario)

print(result["phases_completed"])   # ['phase_01', ..., 'phase_12']
print(result["system_health"])      # {"overall_status": "nominal", ...}
print(result["final_report"])       # Watch supervisor brief
```

**Available scenarios:**

| Key | Name | Description |
|-----|------|-------------|
| `nominal` | Nominal Operations — New York ARTCC | 10 aircraft, cruise/descent, no conflicts |
| `conflict` | Conflict Scenario — Merging Traffic | Converging aircraft at same FL, sector overload |
| `emergency` | Emergency Scenario — Mayday + Weather | Squawk 7700 declaration + severe weather cell |

---

## Routing Logic

The graph has three conditional edge sets:

**Emergency squawk bypass** (after Phase 01)
— If any raw contact squawks 7700/7600/7500, control jumps directly to Phase 09 (Emergency Management), skipping Phases 02–04.

**Alert-level conflict bypass** (after Phase 04)
— If any detected conflict has `severity == "alert"`, control jumps to Phase 09 before returning to Phase 05 for clearance generation.

**Supervisor re-check loop** (after Phase 12)
— If `system_health.overall_status == "critical"`, control returns to Phase 04 for one additional conflict scan before terminating.

---

## Trace Output

With `AEROSENSE_LOG_TRACES=true` (the default), Phase 11 writes:

```
traces/
└── <scenario_id>_traces.jsonl
```

Each file contains one JSON object per line: an audit summary header followed by the DO-178C trace for each completed phase. These files are excluded from version control.

Example trace entry:

```json
{
  "trace_id": "T04-a3f82c1d9e4b7f01",
  "phase_number": 4,
  "phase_name": "Conflict Detection",
  "timestamp": "2025-06-01T06:03:52.000Z",
  "inputs_summary": {"flight_count": 10, "lookahead_min": 15},
  "decision": "Detected 2 conflicts: 1 alerts, 1 warnings",
  "rationale": "Vectored conflict geometry analysis",
  "safety_constraints_verified": ["SEP-001", "SEP-002", "SEP-003"],
  "outputs_summary": {"total": 2, "alerts": 1, "warnings": 1},
  "determinism_flag": true
}
```

---

## Configuration

All tuneable constants live in `core/config.py`:

| Constant | Default | Meaning |
|----------|---------|---------|
| `MODEL_NAME` | `gemini-2.0-flash` | Gemini model used by all agents |
| `AGENT_TEMPERATURE` | `0.1` | Near-deterministic generation |
| `MIN_HORIZONTAL_SEP_NM` | `5.0` | ICAO minimum radar separation |
| `MIN_VERTICAL_SEP_FT` | `1000` | Standard vertical separation |
| `CONFLICT_LOOKAHEAD_MIN` | `15` | Conflict detection lookahead window |
| `SECTOR_OVERLOAD_PCT` | `85` | TFM trigger threshold |

Airspace sectors (EAST, WEST, HIGH, APCH) and radio frequencies are also defined there.

---

## Development Status

| Component | Status |
|-----------|--------|
| LangGraph state graph (12 phases) | Complete |
| Simulation scenario generator | Complete |
| DO-178C trace & audit (Phase 11) | Complete |
| CrewAI supervisor crew (Phase 12) | Complete |
| FastAPI server (`api/`) | Scaffolding |
| WebSocket event streaming | Scaffolding |
| Operator dashboard (`dashboard/`) | HTML skeleton |
| `main.py` entrypoint | Stub |

---

## Known Issues

- **`google.generativeai` is deprecated.** All agents currently use `google-generativeai`. Google has ended support for this package in favour of `google.genai`. Migration is planned.
- **Free-tier Gemini quota** — the free tier for `gemini-2.0-flash` has very low per-minute and per-day limits. A single 12-phase run makes one API call per phase. A paid Gemini API key is recommended for development.

---

## Standards References

- ICAO Doc 4444 — Air Traffic Management (separation minima, sector management)
- ICAO Doc 9432 — Manual of Radiotelephony (phraseology)
- ICAO Annex 2 — Rules of the Air (emergency priority)
- FAA Order 7110.65 — Air Traffic Control (US ATC procedures)
- DO-178C — Software Considerations in Airborne Systems (traceability, DAL-C)
