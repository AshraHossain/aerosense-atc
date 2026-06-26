# AeroCommand AOC — Build Scope

**Date:** 2026-06-26
**Status:** Scope (follows the approved [AeroOps platform design](2026-06-26-aeroops-platform-design.md))
**Relationship:** AeroCommand AOC is **Milestone M3** of the AeroOps plan — not a standalone project.

---

## 1. The honest sequencing (read this first)

AeroCommand cannot be built first. It is the airline-side app that runs on the
shared `core/` and consumes CDM messages from AeroSense. Its prerequisites:

| Milestone | Delivers | Status |
|---|---|---|
| **M0** | `core/` extraction, 4 ports, import-invariant lint, ~50 deterministic tests | **not started** (repo `tests/` is empty) |
| **M1** | AeroSense hardening: real tracer, eval harness, HITL gate | not started |
| **M2** | CDM seam: `cdm/messages.py` + in-memory transport + ATC→AOC handoff | not started |
| **M3** | **AeroCommand AOC** — crew/maint/pax/finance/compliance agents | **this doc** |
| **M4** | Kafka/Postgres/Redis adapters, Docker for both profiles | not started |

**Highest-value next action is M0, not M3.** The repo is safety-framed (ATC,
"DO-178C-inspired") but has no tests at all; the deterministic routers in
`core/graph.py` (emergency squawk bypass, conflict escalation) and the `ATCState`
schema are the highest-ROI things to lock down first, and they need no LLM calls.

## 2. The accelerator the design spec didn't have

The platform design (written earlier today) assumes `core/eval`, `core/audit`, and
tracing get built from scratch in M0–M1. They don't have to be. The **AutoRedTeam**
project (`D:\AI_Models\projects\AutoRedTeam`) just shipped production-ready versions
of exactly this machinery, with 263 passing tests. They port almost directly into
`core/` (Anthropic→Gemini is a provider swap; the patterns are model-agnostic):

| AeroOps `core/` need | Port from AutoRedTeam | Change required |
|---|---|---|
| `core/eval/` harness | `app/evals/` — metrics + golden dataset + frozen baseline + regression gate | Swap dataset to ATC golden scenarios (Nominal/Conflict/Emergency); metrics code is unchanged |
| `core/audit/` traceability | `app/governance/audit.py` — hash-chained tamper-evident log | Reuse as-is; it's the DO-178C-inspired trace the spec wants |
| prompt versioning | `app/governance/prompts.py` — registry + sha256 lockfile | Reuse; register the 12 phase prompts |
| model-upgrade gate | `app/governance/model_upgrade.py` | Reuse; gates a `gemini-2.0-flash` version bump against the eval baseline (spec §5 asks for exactly this) |
| `Tracer` port | `app/tracing/tracer.py` — OTel-shaped span recorder w/ contextvar propagation | Already an interface-shaped emit; make it the `Tracer` port's local adapter |
| HITL gate | AutoRedTeam's `interrupt_before` + ApprovalRequest pattern | Reuse the LangGraph pattern |

**Implication:** M0–M1's eval/tracing/audit/governance work is largely *adaptation*,
not invention. That meaningfully de-risks the path to M3.

## 3. AeroCommand AOC (M3) — concrete scope

Once M0–M2 land, AeroCommand is an app package mirroring AeroSense's shape but with
airline-ops domain agents, single-node first (in-memory adapters), Kafka/PG/Redis
deferred to M4.

### Agents (`aerocommand/`)
Triggered when a CDM **down** directive (GDP / GroundStop / MilesInTrail) arrives:

| Agent | Decides | Key output |
|---|---|---|
| **Crew** | legality of crew under the delay (FAR 117 duty/rest) | crew-legal or reassign/deadhead need |
| **Maintenance** | aircraft airworthiness / MEL impact of the schedule shift | swap aircraft or accept |
| **Passenger** | reaccommodation / misconnect exposure | rebooking plan, IROPS cost |
| **Finance** | cost of comply-vs-cancel-vs-substitute | $ per option, recommended |
| **Compliance** | DOT tarmac-delay rule, FAR limits, audit completeness | block/allow + audit entry |

An AOC supervisor reconciles the five into a response, which becomes CDM **up**
messages (`SubstitutionRequest` / `CancellationNotice` / `FlightIntent`). High-cost
or mass-disruption actions pass the HITL gate before emit (spec §4).

### CDM contract consumed/produced (`cdm/messages.py`, built in M2)
- Consumes (down): `GroundDelayProgram`, `GroundStop`, `MilesInTrail`.
- Produces (up): `SubstitutionRequest`, `FlightIntent`, `CancellationNotice`.

### M3 tests (≥50, deterministic-first)
- FAR 117 crew-legality math; MEL/airworthiness rules; tarmac-delay thresholds —
  all pure functions, no LLM.
- CDM round-trip: a GDP in produces a valid substitution/cancel out.
- HITL gate blocks a mass-diversion without approval.
- Eval: golden IROPS scenario (e.g. a ground stop at a hub) with asserted AOC
  response shape + an LLM-judge on the supervisor brief.

## 4. Recommendation

1. **Do M0 next** (core extraction + ~50 deterministic tests), porting AutoRedTeam's
   audit/prompt/tracer code into `core/` to skip reinventing it.
2. Then M1 (eval harness on the 3 ATC golden scenarios — also ported), M2 (CDM seam).
3. **Then** M3 AeroCommand AOC as scoped above.

Building M3 before M0–M2 means writing airline agents against a `core/` and a CDM
contract that don't exist — so they'd be throwaway. The fastest *real* path to
AeroCommand is to do the foundation first, reusing what's already proven.

## 5. Honest labeling (carried from the platform design)
"DO-178C-inspired traceability" until real requirements-to-test traceability exists.
Aviation-safety claims must not outrun what the tests prove.
