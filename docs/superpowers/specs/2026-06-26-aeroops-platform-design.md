# AeroOps Platform — Design Spec

**Date:** 2026-06-26
**Status:** Approved (brainstorming complete) — proceeds to GSD planning
**Repo:** AshraHossain/aerosense-atc (monorepo)

## 1. Goal

Evolve the existing single-app AeroSense ATC system into a monorepo platform with a
shared core and **two deployable apps that mirror the real FAA↔airline operating
structure**, connected by a Collaborative Decision Making (CDM) message seam:

- **AeroSense ATC** — an air-traffic-control sector controller (the FAA/ATC side):
  surveillance, conflict detection, clearances, ICAO phraseology, separation.
  Single-node deployment topology (LangGraph + in-memory backends).
- **AeroCommand AOC** — an airline Operations Control Center (the airline side):
  crew, maintenance, passenger reaccommodation, finance, compliance, human approval.
  Distributed deployment topology (Kafka/Postgres/Redis backends).

The two apps share one core library and the **same agent base, eval harness,
tracing, audit, and HITL machinery**. They differ in (a) which domain agents they
run and (b) which infrastructure adapters are injected.

### Why this structure (decision record)
The difference between the two apps is *infrastructure and domain scope*, not the
fundamentals (agent base, state contract, evals, tracing, audit). Duplicating that
shared 90% across two repos would double the maintenance and test burden and let the
systems drift. So: **one shared `core/`, two app packages, ports-and-adapters for the
swappable infrastructure.** This also seeds a future enterprise platform without
committing to it now (YAGNI on the platform layer).

### Real-industry grounding
- ATC hierarchy: Tower → TRACON → ARTCC (en-route sectors) → ATCSCC (national flow).
  AeroSense models a sector controller; Phase 10 (TFM/GDP/ground-stop) touches ATCSCC
  flow authority.
- Airline AOC/OCC manages one airline's fleet response to disruption. AeroCommand
  models this.
- The seam is **CDM over FAA's TFMS**: flow directives go down (GDP, ground stop,
  miles-in-trail); collaborative responses go up (substitution requests, intent,
  cancellations).

## 2. Architecture

```
aerosense-atc/                  (repo = platform monorepo)
├── core/                       # shared library; imports from NO app package
│   ├── domain/                 #   ATCState, FlightPlan, Clearance, CDM models
│   ├── agents/                 #   agent base (Gemini call, trace, event emit) + agents
│   ├── ports/                  #   interfaces: EventBus, StateStore, Memory, Tracer
│   ├── eval/                   #   eval harness, golden scenarios, LLM-judge
│   ├── audit/                  #   DO-178C-inspired trace/hash, prompt versioning
│   └── hitl/                   #   human-approval gate
├── aerosense/                  # APP A — ATC sector controller (single-node)
│   ├── adapters/               #   in-memory EventBus, dict StateStore, local Memory
│   ├── graph.py                #   LangGraph wiring of the 12 phases
│   └── main.py / api.py
├── aerocommand/                # APP B — airline AOC (distributed)
│   ├── adapters/               #   Kafka EventBus, Postgres StateStore, Redis Memory
│   ├── crew/ maint/ pax/ finance/ compliance/
│   └── main.py / api.py
├── cdm/                        # the seam — shared message contract + transport
│   └── messages.py             #   GDP, GroundStop, MilesInTrail, SubstitutionRequest…
├── docker/                     # compose: aerosense (lite) + aerocommand (full stack)
└── tests/                      # mirrors core/ + each app
```

**Invariant:** `core/` must never import from `aerosense/` or `aerocommand/`. Apps
depend on core; core depends on nobody. This invariant is what makes "swap the
infrastructure, keep the logic" literally true, and it is enforceable with a simple
import-lint test.

### Ports & adapters (the swap points)
Four interfaces in `core/ports/`:

| Port | AeroSense adapter | AeroCommand adapter |
|------|-------------------|---------------------|
| `EventBus` | in-memory queue | Kafka topic |
| `StateStore` | dict / in-memory | Postgres |
| `Memory` | local dir | Redis |
| `Tracer` | OpenTelemetry/LangSmith | OpenTelemetry/LangSmith |

Agents are written against the interface and never know which backend they run on.

### The CDM seam
`cdm/messages.py` holds typed (Pydantic) messages:
- **Down (authority):** `GroundDelayProgram`, `GroundStop`, `MilesInTrail`.
- **Up (collaboration):** `SubstitutionRequest`, `FlightIntent`, `CancellationNotice`.

Transport is itself a port: in-memory queue for local dev, Kafka topic for the
distributed run. The *messages* are identical across both transports.

## 3. Data flow

1. AeroSense ingests raw contacts → runs the 12-phase graph → may emit a flow
   directive (e.g. GDP at a congested sector) as a **CDM down** message.
2. AeroCommand receives the CDM directive → its AOC agents (crew/maint/pax/finance)
   compute the airline's response → emits **CDM up** messages (substitution/cancel).
3. AeroSense reconciles the responses into its sector picture.
4. Every step on both sides writes a trace (Tracer port) and an audit entry; high-risk
   actions pass through the HITL gate before commit.

## 4. Error handling & failure modes

- **LLM failure / timeout:** agents retry with backoff via the orchestration layer;
  on exhaustion they emit a degraded result + escalate (never silently pass).
- **Adapter failure (Kafka/Postgres/Redis down):** AeroCommand surfaces the outage and
  refuses to claim success; AeroSense (in-memory) is unaffected — this is also the
  argument for the single-node profile as a resilient baseline.
- **Unsafe decision:** the HITL gate blocks autonomous execution of high-risk actions
  (e.g. mass diversion) and requires explicit approve/escalate, with an audit entry.
- **Schema drift:** `ATCState` and CDM messages are versioned; additive-only changes
  are safe, renames require a coordinated migration across agents.

## 5. Testing & evaluation strategy

- **Deterministic tests first (no LLM):** routing logic, `ATCState` schema, CDM message
  validation, ICAO separation math, the `core/`-never-imports-apps invariant.
- **Evals before trust:** golden Nominal/Conflict/Emergency scenarios with asserted
  structured outputs + an LLM-judge on the supervisor brief; record a pass rate.
- **Tracing:** every retrieval, reasoning step, tool call, and decision replayable from
  the Tracer port output.
- **Governance:** prompt versioning in `core/audit/`; a Gemini model-version bump must
  re-run the eval suite (model-upgrade regression) before it is accepted.
- Target ≥50 tests per milestone; tests gate each milestone commit.

## 6. Milestones

Each milestone ends with a commit; tests gate each. Implementation happens on
feature branches per the GSD workflow.

- **M0 — Core extraction + test foundation.** Carve out `core/`, define the four ports,
  add the import-invariant lint test, write ~50 deterministic tests against current
  behavior. No behavior change — structure + safety net only.
- **M1 — AeroSense hardening.** Real Tracer (LangSmith/OTel), eval harness with the 3
  golden scenarios, real HITL gate on the 12-phase graph. +50 tests.
- **M2 — CDM seam.** `cdm/messages.py` contract + in-memory transport + the ATC→AOC
  handoff path. +50 tests.
- **M3 — AeroCommand AOC.** crew/maint/pax/finance/compliance agents on the shared
  core, single-node first. +50 tests.
- **M4 — Distributed adapters + Docker.** Kafka/Postgres/Redis adapters behind the
  ports, compose for both profiles, model-upgrade regression. +50 tests.

## 7. Out of scope (YAGNI for now)

- Prometheus/Grafana dashboards (LangSmith covers observability first; add when a
  concrete monitoring need appears).
- Multi-airline AOC, real live ADS-B feeds, real-money/real-trade actions.
- The broader "APEX enterprise platform" — this design seeds it but does not build it.

## 8. Honest labeling

Compliance language is **"DO-178C-inspired traceability"** until real
requirements-to-test traceability exists (M1+). Aviation-safety claims must not
outrun what the tests actually prove.
