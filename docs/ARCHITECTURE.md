# AeroOps Platform Architecture

**Status:** Complete (M0–M4 + observability)  
**Test coverage:** 232 tests (all milestones)  
**Deployment profiles:** AeroSense (single-node), AeroCommand (distributed)

## Platform Overview

AeroOps is a monorepo with two deployable applications that mirror real FAA↔airline operations:

- **AeroSense ATC** — sector controller (12-phase LangGraph with Google Gemini)
- **AeroCommand AOC** — airline Operations Control Center (crew/maint/pax/finance responses)

Both share a single `core/` library (routing, audit, eval, HITL) and differ only in infrastructure adapters. They communicate via a CDM (Collaborative Decision Making) message seam.

## Logical Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│ core/                                                           │
│ ┌──────────────┬──────────────┬──────────────┬──────────────┐  │
│ │ routing.py   │ state.py     │ audit/       │ eval/        │  │
│ │ (M0)         │ (M0)         │ hash-chain   │ golden seam   │  │
│ │              │              │ (M1)         │ (M1)          │  │
│ ├──────────────┼──────────────┼──────────────┼──────────────┤  │
│ │ hitl/        │ ports/       │ agents/      │ config.py    │  │
│ │ approval     │ EventBus     │ base (M0)    │ constants    │  │
│ │ gate (M1)    │ StateStore   │              │              │  │
│ │              │ Memory       │              │              │  │
│ │              │ Tracer       │              │              │  │
│ │              │ (M4)         │              │              │  │
│ └──────────────┴──────────────┴──────────────┴──────────────┘  │
│ (never imports aerosense/ or aerocommand/)                     │
└─────────────────────────────────────────────────────────────────┘
         │                    │                    │
         │ in-memory          │ Kafka/Postgres/    │ in-memory or
         │ adapters           │ Redis adapters     │ Kafka+...
         ▼                    ▼                    ▼
      AeroSense           AeroCommand           CDM seam
   (single-node)         (distributed)        (M2, leaf)
```

## Module Breakdown

### core/ — Shared (M0–M1)

The heart: all safety-critical and policy logic.

- **routing.py** (M0): Pure-Python routers for emergency bypass (squawk 7700/7600/7500), conflict escalation, supervisor re-check loop. No LLM, no imports from apps.
- **state.py** (M0): `ATCState`, the single shared dict propagated through the 12-phase graph. Contracts the field names; changes ripple across all phases.
- **config.py**: ICAO/FAA constants (separation minima, sector capacity, AGENT_TEMPERATURE).
- **agents/base.py** (M0): Shared Gemini call helper, trace builder, cross-phase event bus.
- **audit/**: DO-178C-inspired hash-chain trace. Every phase decision produces a cryptographic entry; immutable audit trail (M1).
- **eval/**: Golden scenario harness (Nominal/Conflict/Emergency). Frozen pass-rate baseline; re-run after model upgrades to catch regressions (M1).
- **hitl/**: Human-approval gate for high-risk decisions (mass diversions, emergency escalations). Blocks execution, requires explicit approval + audit entry (M1).
- **ports/**: Four abstract interfaces (M4):
  - `EventBus`: pub-sub for CDM and agent events
  - `StateStore`: persistence for scenario state
  - `Memory`: fast cache with TTL
  - `Tracer`: decision audit trail (in-memory, LangSmith, OpenTelemetry)

### aerosense/ — ATC Controller (Single-Node)

Runs the 12-phase graph end-to-end on a single machine with in-memory state.

- **graph.py**: LangGraph wiring of the 12 phases. Imports routers from `core/routing.py`. Each phase:
  1. Reads `ATCState`
  2. Calls Gemini with a phase-specific system prompt + JSON schema
  3. Writes results + trace entry back to state
- **adapters/**: In-memory implementations of all four ports.
  - `InMemoryEventBus`: FIFO queue
  - `InMemoryStateStore`: dict-backed
  - `InMemoryMemory`: dict with TTL
  - `InMemoryTracer`: list-backed (or LangSmith if available)
- **api.py**: FastAPI routes + WebSocket dashboard.

### aerocommand/ — Airline AOC (Distributed)

Airline Operations Control Center that responds to ATC directives (M3).

- **fleet.py** (M3): `FleetFlight` model—validated flight info (origin, destination, priority, cancellable).
- **responder.py** (M3): Deterministic flow reactions:
  - `respond_to_gdp()`: GDP overflow → lowest-priority arrivals → cancel or delay
  - `respond_to_ground_stop()`: ground stop → delay all affected arrivals
  - `respond_to_miles_in_trail()`: MIT constraint → delay flights crossing fix
  - `respond_to_directive()`: dispatcher routing by message type
- **adapters/**: Kafka, Postgres, Redis implementations (M4):
  - `KafkaEventBus`: DOWN/UP topic routing
  - `PostgresStateStore`: JSONB scenario persistence
  - `RedisMemory`: flight cache with TTL
- **crew/, maint/, pax/, finance/, compliance/**: Future AOC agents (not yet built).

### cdm/ — CDM Seam (M2, Leaf Package)

Models the real FAA↔airline CDM protocol. **Deliberately isolated** (never imports `core/` or apps).

- **messages.py** (M2): Pydantic models for typed, validated messages.
  - DOWN (authority): `GroundDelayProgram`, `GroundStop`, `MilesInTrail`
  - UP (collaboration): `SubstitutionRequest`, `FlightIntent`, `CancellationNotice`
  - Direction is derived from message type (unforgeable).
- **transport.py** (M2): `InMemoryCDMTransport` — FIFO queue with filtering by direction/type.
- **seam.py** (M2): `tfm_to_cdm()` translator. Maps ATC-internal `TFMProgram` dict to CDM DOWN message. Takes plain dicts (not core imports) so translation is pure.

### adapters/ — Pluggable Infrastructure (M4)

Four concrete implementations of each port. Swapped at startup based on deployment profile.

**In-memory (local dev, AeroSense):**
- `InMemoryEventBus`, `InMemoryStateStore`, `InMemoryMemory`, `InMemoryTracer`

**Distributed (AeroCommand):**
- `KafkaEventBus`: Kafka topics for DOWN/UP message routing
- `PostgresStateStore`: JSONB column for scenario state, durable across restarts
- `RedisMemory`: Redis cache with optional TTL, shared across pods
- `LangSmithTracer`: End-to-end observability (optional, M1 completion)

## Data Flow

### Nominal Scenario

1. **AeroSense ingests raw contacts** → runs 12-phase graph
   - Phase 1: surveillance/track fusion
   - Phase 2–9: flight plan, sector mgmt, conflict detection, clearance, etc.
   - Phase 10: **traffic-flow mgmt** — detects congestion, emits TFMProgram (GDP, ground-stop, MIT)

2. **Phase 10 → CDM seam**
   ```python
   tfm_program = state.get("tfm_program")
   down_message = tfm_to_cdm(tfm_program, ...)
   event_bus.publish(down_message)  # CDM DOWN
   ```

3. **AeroCommand consumes CDM DOWN**
   ```python
   downs = event_bus.drain(direction=CDMDirection.DOWN)
   for down in downs:
       ups = respond_to_directive(down, fleet)
       event_bus.publish_many(ups)  # CDM UP
   ```

4. **AeroSense reconciles CDM UP**
   ```python
   ups = event_bus.drain(direction=CDMDirection.UP)
   state["aoc_responses"] = ups
   ```

5. **Phase 11–12**: Audit export + supervisor brief

### Error Handling

- **LLM timeout/failure**: Agent retries with exponential backoff; on exhaustion, emits degraded result + escalates.
- **Adapter failure** (Kafka down, Postgres down): AeroCommand surfaces outage, refuses to claim success. AeroSense (in-memory) unaffected.
- **Unsafe decision**: HITL gate blocks execution, requires explicit approve/escalate.
- **Schema drift**: `ATCState` and CDM messages versioned; additive-only changes safe, renames require migration.

## Milestones & Coverage

| Milestone | Focus | Tests | Status |
|-----------|-------|-------|--------|
| M0 | Core extraction + routing | 56 | ✓ Merged |
| M1 | AeroSense hardening (eval/audit/HITL/LangSmith) | 86 | ✓ Merged |
| M2 | CDM seam (messages + transport + translator) | 65 | PR #1 |
| M3 | AOC responder + e2e round-trip | 93 | PR #2, #3 |
| M4 | Distributed adapters + Docker + observability | 19 | PR #4 |
| **E2E Smoke** | Full system integration test | 3 | M4 branch |
| **Total** | — | **232** | — |

## Deployment Profiles

### AeroSense (Single-Node)

```bash
python aerosense/main.py
# Runs at http://localhost:8000
# Uses in-memory adapters
# All state in process memory; no external services required
```

### AeroCommand (Distributed)

```bash
docker-compose up
# Brings up:
#   - Kafka + Zookeeper (CDM messaging)
#   - Postgres (scenario state)
#   - Redis (flight cache)
#   - AeroCommand app at http://localhost:8001
```

**Environment variables:**
```
KAFKA_BOOTSTRAP_SERVERS=kafka:9092
POSTGRES_URL=postgresql://user:pass@postgres:5432/aerosense
REDIS_HOST=redis
REDIS_PORT=6379
LANGSMITH_API_KEY=<optional>  # if using LangSmith tracer
```

## Testing Strategy

- **Deterministic tests (no LLM)**: routing logic, state contracts, CDM message validation, ICAO math. ~200 tests.
- **Evals before trust**: golden scenarios with asserted outputs + LLM-judge on supervisor brief. Re-run after model upgrades.
- **Integration tests**: full round-trip (ATC → CDM DOWN → AOC → CDM UP → reconciliation). ~40 tests.
- **E2E smoke**: all four milestones integrated (M0 routing + M1 audit + M2 seam + M3 responder + M4 ports). 3 tests.

## Key Design Decisions

1. **Monorepo with shared core**: One `core/` avoids duplication of eval/audit/tracing/HITL. Apps differ in scope + adapters, not fundamentals.
2. **Routing deterministic, never in LLM**: Emergency bypass (7700/7600/7500), conflict escalation, supervisor re-check are pure Python in `core/routing.py`. Safety net, testable, immutable.
3. **CDM as a leaf package**: `cdm/` never imports `core/` or apps. Translation is pure (takes plain dicts), not core-coupled. Allows seam to evolve independently.
4. **Ports & adapters**: Four interfaces let AeroSense (in-memory) and AeroCommand (Kafka/Postgres/Redis) share agent logic while injecting different infrastructure. Testable in isolation.
5. **Deterministic tie-breaking**: GDP victim selection sorted by (priority, flight_id) for reproducibility across runs and audit trails.

## Future Work (Out of Scope)

- Prometheus/Grafana dashboards (LangSmith covers observability; add when monitoring need appears)
- Multi-airline AOC (design seeds it but doesn't build it)
- Real ADS-B feeds, real-money actions (integration work, not core platform)
- APEX enterprise platform (design accommodates it, YAGNI for now)

## Files to Read

- **Architecture contract:** [core/state.py](../core/state.py) (ATCState shape)
- **Safety routers:** [core/routing.py](../core/routing.py) (all conditional logic)
- **12-phase graph:** [aerosense/graph.py](../aerosense/graph.py) (agent wiring)
- **CDM seam:** [cdm/messages.py](../cdm/messages.py) + [cdm/seam.py](../cdm/seam.py)
- **AOC responder:** [aerocommand/responder.py](../aerocommand/responder.py) (flow reactions)
- **Port interfaces:** [core/ports/](../core/ports/) (all four)
- **Adapters:** [adapters/](../adapters/) (in-memory, Kafka, Postgres, Redis, LangSmith)
