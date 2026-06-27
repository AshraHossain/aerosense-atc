# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

AeroSense ATC is a 12-phase multi-agent Air Traffic Control pipeline built on **LangGraph** with **Google Gemini** (`gemini-2.0-flash`) as the model for every agent. A single scenario (raw ADS-B/radar contacts) enters at Phase 01 and propagates through all 12 phases over a shared `ATCState`, ending in a DO-178C-inspired audit trace and a watch-supervisor brief. The graph is compiled once at import time and reused for every scenario.

> A platform refactor is planned (shared `core/` + two apps `aerosense/` ATC and `aerocommand/` AOC connected by a CDM message seam). The committed design lives in `docs/superpowers/specs/`. Until milestones land, the structure below is the live code.

## Commands

```bash
# Run (serves dashboard + API at http://localhost:8000)
python main.py
# or on Windows, which also installs deps and checks GOOGLE_API_KEY:
start.bat

# Install deps — requirements.txt is the source of truth for the running app
pip install -r requirements.txt
# (pyproject.toml + uv.lock also exist; `uv sync` works but the two lists drift —
#  the app imports google.generativeai, which only requirements.txt pins.)

# Tests (pytest + pytest-asyncio configured; tests/ is currently EMPTY)
pytest
pytest tests/path/to/test_file.py::test_name   # single test
pytest -k "routing"                              # by keyword

# Lint / format (both declared as deps)
ruff check .
black .
```

Requires **Python 3.12+** and a `GOOGLE_API_KEY` (Gemini, from https://aistudio.google.com/app/apikey) in `.env` (see `.env.example`). `.env` is gitignored — never commit it.

## Architecture (the big picture)

The system is a `StateGraph` defined in `aerosense/graph.py` (moved here from `core/graph.py` in M0 so `core/` stays a leaf). Understanding three files explains most of it:

- **`core/state.py`** — `ATCState`, the single shared dict that every phase reads from and writes back to. This is the contract; changing its shape affects all 12 agents.
- **`core/routing.py`** — the **deterministic conditional routers** (pure Python, no LLM): the safety-critical heart, testable in isolation. **`aerosense/graph.py`** imports these routers and wires the 12 phase nodes into the graph. The routers:
  - `route_after_surveillance` — **emergency squawk bypass**: any contact squawking 7700/7600/7500 jumps straight to Phase 09, skipping normal flow.
  - `route_after_conflict` — **alert-level conflict** escalates directly to Phase 09.
  - `route_after_emergency` — emergency handling rejoins normal flow at Phase 05 (clearance).
  - `route_after_supervisor` — Phase 12 can loop back to Phase 04 once if `system_health` is `critical`, else `END`.
- **`agents/base.py`** — shared agent machinery: the Gemini call helper, the DO-178C trace builder (each phase emits a cryptographically-hashed decision trace), and the cross-phase event emitter. Every `phase_NN_*.py` follows the same shape: read `ATCState`, call Gemini with a phase-specific system prompt + JSON schema, write results + a trace entry back.

The 12 phases (`agents/phase_01..phase_12`): surveillance/track-fusion → flight-plan parse → sector mgmt → conflict detection → clearance gen → ICAO comms → handoff → weather → emergency (runs as a bypass node) → traffic-flow mgmt (GDP/ground-stop) → audit/DO-178C export → supervisor (a CrewAI two-agent crew that falls back to a direct Gemini call if CrewAI is unavailable). There are also extra agent dirs (`planner`, `safety_judge`, `digital_twin`, `backtracker`, `fallback`, `ingestor`, `clearance`) that are part of the evolving design.

**Safety constants live in `core/config.py`** — ICAO/FAA separation minima (5 NM horizontal, 1000/2000 ft vertical), conflict look-ahead, sector capacity, and the `SECTORS` map. `AGENT_TEMPERATURE = 0.1` is deliberately low for determinism. Treat these as the system's source of truth for ATC rules.

**API/UI:** `api/` (routes + websocket) is mounted by `main.py` via `from api import app`. `simulation/scenario_generator.py` produces the three built-in scenarios (Nominal, Conflict, Emergency). The dashboard streams the cross-phase event bus over websockets.

## Conventions that matter here

- **Routing is deterministic and must stay that way.** Emergency/conflict bypass logic is pure Python in `core/routing.py` (extracted from `core/graph.py` in M0 so it's testable without importing the 12 agents or Gemini), not an LLM decision — it is the testable safety net. Don't move routing into agent prompts.
- **Every phase writes a trace.** Use `agents/base.py`'s trace builder so the Phase 11 audit export stays complete; a phase that skips its trace breaks DO-178C-inspired traceability.
- **`ATCState` is the integration contract.** Freeze/extend it deliberately — additive changes are safe, renames ripple across all 12 phases.
- **`requirements.txt` vs `pyproject.toml` drift** is a known wart: the app runs on `requirements.txt` (Gemini). If you touch deps, reconcile both.
- **M0 + M1 done on `master`.** M0: `core/` is a true leaf (graph wiring in `aerosense/graph.py`), routers in `core/routing.py`, import-invariant enforced recursively (`tests/unit/test_core_invariant.py`). M1: `core/eval/` golden safety-check harness + frozen baseline; `core/audit/` hash-chained DO-178C trace log; `core/prompts.py` versioned registry + sha256 lockfile wired into all 11 Gemini-calling phases; `core/tracing/` sync OTel-shaped span tracer (perf_counter-based — Windows `monotonic()` has ~15.6ms granularity, wrong tool for span duration) wired into `call_gemini`, every graph node, and all routers; `core/hitl/` — real human-approval gate: an active `ground_stop` pauses the compiled graph (`MemorySaver` + `interrupt_before=["hitl_gate"]`) via `route_after_tfm`, resumes on `ApprovalGate.approve()`. `api/websocket/__init__.py` updated for the now-required `thread_id` config and to distinguish a real pause from completion.
- **`cdm/` is the seam, a deliberate leaf (M2).** Models the FAA↔airline CDM protocol as validated Pydantic messages (down: GDP/GroundStop/MilesInTrail; up: Substitution/FlightIntent/Cancellation), with an in-memory transport and `tfm_to_cdm()`. Imports only stdlib + Pydantic — **never `core/` or either app** — so translation takes plain dicts, not a `core` import. The seam is a trust boundary, hence real runtime validation where the rest of the repo uses zero-overhead `TypedDict`.
- **`aerocommand/` is the AOC app (M3).** Deterministic airline reaction to inbound CDM flow directives (fleet/responder logic) — the actual "AeroCommand" the original pitch asked for, built on the shared `core/` rather than a second repo.
- **M4: distributed adapters + `core/resilience.py` + Docker.** Retry/timeout/circuit-breaker primitives, concrete adapter implementations behind `core/ports.py`.
- **⚠ Known duplication, unresolved as of this merge (2026-06-26):** `core/governance/prompts.py` (a model-scoped `PromptLockfile`/`PromptVersion`) and `adapters/langsmith_tracer.py` (a `Tracer`-port LangSmith adapter) were built in parallel with this repo's `core/prompts.py` and `core/tracing/`, covering the same M1 concerns with different designs. Evidence from comparing them: `core/prompts.py`/`core/tracing/` are integrated into the live 12-phase pipeline (every agent's `SYSTEM` is asserted equal to its registry entry; the tracer wraps real graph runs) — `core/governance/prompts.py`'s tests use fabricated prompt text, never the real agents, and `adapters/langsmith_tracer.py` is unwired into the graph and requires an external LangSmith account (its own tests skip without the `langsmith` package). Recommendation: keep `core/prompts.py`/`core/tracing/` as the production path; treat `core/governance/` and `adapters/langsmith_tracer.py` as optional/inert unless something actually needs LangSmith or model-scoped lockfiles later — don't wire both. Not deleted here; that's a call for whoever owns the roadmap.
