# Graph Report - aerosense-atc  (2026-06-01)

## Corpus Check
- 45 files · ~7,758 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 112 nodes · 118 edges · 45 communities (35 shown, 10 thin omitted)
- Extraction: 69% EXTRACTED · 31% INFERRED · 0% AMBIGUOUS · INFERRED: 37 edges (avg confidence: 0.8)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `ca5798ee`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- [[_COMMUNITY_Community 0|Community 0]]
- [[_COMMUNITY_Community 1|Community 1]]
- [[_COMMUNITY_Community 2|Community 2]]
- [[_COMMUNITY_Community 3|Community 3]]
- [[_COMMUNITY_Community 4|Community 4]]
- [[_COMMUNITY_Community 5|Community 5]]
- [[_COMMUNITY_Community 6|Community 6]]
- [[_COMMUNITY_Community 7|Community 7]]
- [[_COMMUNITY_Community 8|Community 8]]
- [[_COMMUNITY_Community 9|Community 9]]
- [[_COMMUNITY_Community 10|Community 10]]
- [[_COMMUNITY_Community 11|Community 11]]
- [[_COMMUNITY_Community 12|Community 12]]
- [[_COMMUNITY_Community 13|Community 13]]
- [[_COMMUNITY_Community 14|Community 14]]
- [[_COMMUNITY_Community 15|Community 15]]
- [[_COMMUNITY_Community 17|Community 17]]

## God Nodes (most connected - your core abstractions)
1. `make_trace()` - 15 edges
2. `emit_event()` - 14 edges
3. `call_gemini()` - 13 edges
4. `phase_12_node()` - 6 edges
5. `phase_01_node()` - 4 edges
6. `phase_02_node()` - 4 edges
7. `phase_03_node()` - 4 edges
8. `phase_04_node()` - 4 edges
9. `phase_05_node()` - 4 edges
10. `phase_06_node()` - 4 edges

## Surprising Connections (you probably didn't know these)
- `make_trace()` --calls--> `DO178CTrace`  [INFERRED]
  agents/base.py → core/state.py
- `phase_12_node()` --calls--> `SystemHealth`  [INFERRED]
  agents/phase_12_supervisor.py → core/state.py
- `phase_01_node()` --calls--> `call_gemini()`  [INFERRED]
  agents/phase_01_surveillance.py → agents/base.py
- `phase_02_node()` --calls--> `call_gemini()`  [INFERRED]
  agents/phase_02_flight_plan.py → agents/base.py
- `phase_03_node()` --calls--> `call_gemini()`  [INFERRED]
  agents/phase_03_sector.py → agents/base.py

## Communities (45 total, 10 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.21
Nodes (16): ATCState, Clearance, ConflictAlert, DO178CTrace, Emergency, FlightPlan, FlightTrack, HandoffInstruction (+8 more)

### Community 1 - "Community 1"
Cohesion: 0.18
Nodes (9): AeroSense ATC — LangGraph Orchestration 12-phase StateGraph with deterministic r, Skip to emergency if mayday detected in raw contacts., Skip directly to emergency handling if any alert-level conflict., After emergency handling, resume normal flow at clearance generation., Supervisor can trigger a re-run of conflict detection if it finds     unresolved, route_after_conflict(), route_after_emergency(), route_after_supervisor() (+1 more)

### Community 2 - "Community 2"
Cohesion: 0.4
Nodes (5): phase_12_node(), Phase 12 — Supervisor / Meta-Agent (CrewAI Crew) Validates all prior phase outpu, Run a two-agent CrewAI crew for validation + reporting., _run_crewai_supervisor(), SystemHealth

### Community 3 - "Community 3"
Cohesion: 0.33
Nodes (3): generate_scenario(), AeroSense ATC - Synthetic Scenario Generator Generates realistic ATC scenarios w, Return an ATCState-compatible initial state dict for the given scenario.

### Community 4 - "Community 4"
Cohesion: 0.4
Nodes (4): make_trace(), Produce a DO-178C compliant decision trace entry.     determinism_flag=True beca, phase_11_node(), Phase 11 — Audit & Compliance (DO-178C Traceability) Consolidates all phase trac

### Community 5 - "Community 5"
Cohesion: 0.4
Nodes (4): emit_event(), Append a structured event to the cross-phase event bus., phase_08_node(), Phase 08 — Weather Integration Integrates weather hazards, identifies affected f

### Community 6 - "Community 6"
Cohesion: 0.5
Nodes (3): call_gemini(), AeroSense ATC — Base Agent Utilities Shared Gemini call helper used by all 12 ph, Call Gemini in JSON mode with deterministic temperature.     Returns parsed dict

## Knowledge Gaps
- **27 isolated node(s):** `AeroSense ATC — Base Agent Utilities Shared Gemini call helper used by all 12 ph`, `Call Gemini in JSON mode with deterministic temperature.     Returns parsed dict`, `Produce a DO-178C compliant decision trace entry.     determinism_flag=True beca`, `Append a structured event to the cross-phase event bus.`, `Phase 01 — Surveillance & Track Fusion Fuses raw ADS-B and radar contacts into u` (+22 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **10 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `make_trace()` connect `Community 4` to `Community 0`, `Community 2`, `Community 5`, `Community 6`, `Community 7`, `Community 8`, `Community 9`, `Community 10`, `Community 11`, `Community 12`, `Community 13`, `Community 14`, `Community 15`?**
  _High betweenness centrality (0.156) - this node is a cross-community bridge._
- **Why does `DO178CTrace` connect `Community 0` to `Community 4`?**
  _High betweenness centrality (0.101) - this node is a cross-community bridge._
- **Why does `emit_event()` connect `Community 5` to `Community 2`, `Community 4`, `Community 6`, `Community 7`, `Community 8`, `Community 9`, `Community 10`, `Community 11`, `Community 12`, `Community 13`, `Community 14`, `Community 15`?**
  _High betweenness centrality (0.056) - this node is a cross-community bridge._
- **Are the 13 inferred relationships involving `make_trace()` (e.g. with `DO178CTrace` and `phase_01_node()`) actually correct?**
  _`make_trace()` has 13 INFERRED edges - model-reasoned connections that need verification._
- **Are the 12 inferred relationships involving `emit_event()` (e.g. with `phase_01_node()` and `phase_02_node()`) actually correct?**
  _`emit_event()` has 12 INFERRED edges - model-reasoned connections that need verification._
- **Are the 11 inferred relationships involving `call_gemini()` (e.g. with `phase_01_node()` and `phase_02_node()`) actually correct?**
  _`call_gemini()` has 11 INFERRED edges - model-reasoned connections that need verification._
- **Are the 4 inferred relationships involving `phase_12_node()` (e.g. with `call_gemini()` and `SystemHealth`) actually correct?**
  _`phase_12_node()` has 4 INFERRED edges - model-reasoned connections that need verification._