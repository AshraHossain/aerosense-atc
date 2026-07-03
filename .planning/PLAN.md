# M5: AeroSense MultiAirline — Comprehensive Execution Plan

**Status:** Planning complete (5 phases, 50+ tests)  
**Date:** 2026-06-26  
**Goal:** Build deterministic multi-airline AOC support with per-airline state isolation, Kafka pub-sub, cross-airline slot negotiation, and fair capacity allocation.

---

## Executive Summary

M5 extends AeroCommand from single-airline (M3) to multi-airline federation. The core challenge is **state isolation per airline** while **sharing slot/capacity arbitration** across airlines. All code is deterministic (no LLM, no randomness) and testable in isolation.

**Deliverables:**
1. `airline_manager.py` — CRUD, onboarding, federation state
2. `multi_store.py` — per-airline Postgres schemas + state isolation
3. `responder_pool.py` — per-airline responder instances + routing
4. `slot_negotiation.py` — cross-airline swap arbitration (deterministic tie-break)
5. `fair_allocation.py` — percentage-based capacity fairness + monopoly prevention
6. 50+ tests across all phases (all green)
7. Updated `ARCHITECTURE.md` with multi-airline section
8. Integration tests + E2E scenarios

---

## Phase Breakdown

### Phase 1: AirlineManager + MultiAirlineStateStore (20 tests)

**Goal:** Enable multiple airlines to coexist in a shared ATC system with deterministic per-airline state isolation.

**Requirements:**
- `airline_manager.py`: Airline registration, lifecycle (active/suspended/inactive), audit trail
- `multi_store.py`: Per-airline Postgres JSONB tables + migration framework
- `__init__.py` updates to wire dependencies
- Unit tests: 20 tests covering:
  - Airline CRUD (create, read, list, deactivate)
  - State isolation (one airline's flights don't leak to another)
  - Schema versioning (migrations apply per-airline)
  - Audit trail (all changes logged)

**Key Files to Create:**
- `aerocommand/airline_manager.py` (150–200 lines)
- `aerocommand/multi_store.py` (250–350 lines)
- `tests/m5/test_airline_manager.py` (300–400 lines)
- `tests/m5/test_multi_store.py` (350–450 lines)

**Key Files to Modify:**
- `aerocommand/__init__.py` (expose `AirlineManager`, `MultiAirlineStateStore`)
- `core/ports.py` or new `core/multi_ports.py` (interface contracts if needed)

**Acceptance Criteria:**
- All 20 tests pass
- Airline isolation verified: flight added to Airline A does not appear in Airline B's query
- Schema migrations are per-airline (one airline can be on v1, another on v2)
- Audit trail records all airline lifecycle events

---

### Phase 2: ResponderPool for Per-Airline Response Isolation (25 tests)

**Goal:** Instantiate one `responder` per airline so that each airline reacts independently to ATC directives without interference.

**Requirements:**
- `responder_pool.py`: Pool management (create, route, destroy)
- Routes DOWN directives to the correct airline's responder
- Each responder reads/writes its own airline's state
- Unit + integration tests: 25 tests covering:
  - Pool CRUD (add airline, remove airline, list active)
  - Routing (a GDP directive routes to the right airline)
  - Isolation (two airlines react independently to the same GDP)
  - Responder lifecycle (cleanup on airline deactivation)
  - Event emission (responder events tagged with airline_id)

**Key Files to Create:**
- `aerocommand/responder_pool.py` (200–300 lines)
- `tests/m5/test_responder_pool.py` (350–450 lines)

**Key Files to Modify:**
- `aerocommand/__init__.py` (expose `ResponderPool`)
- `aerocommand/responder.py` (add optional `airline_id` param, preserve backward compat)
- `cdm/transport.py` or new `cdm/multi_transport.py` (route inbound messages to airline)

**Acceptance Criteria:**
- All 25 tests pass
- Two airlines receiving the same GDP directive produce independent reactions (different delays/cancellations)
- Pool teardown is clean (no dangling state)
- Events from each responder are labeled with airline_id

---

### Phase 3: Cross-Airline Slot Negotiation (20 tests)

**Goal:** Enable airlines to negotiate slot swaps (e.g., "Airline A's 10:00 slot for Airline B's 10:15 slot") with deterministic arbitration when both want the same slot.

**Requirements:**
- `slot_negotiation.py`: Slot objects, swap proposal, arbitration logic
- Deterministic tie-break: by airline_code (lexicographic, not random)
- Swap validation (is the requested slot available? Can the other airline accept it?)
- Atomic swap execution (all-or-nothing)
- Unit + integration tests: 20 tests covering:
  - Slot creation and tracking
  - Swap proposal (A→B, B→A proposals)
  - Tie-break (two airlines want the same slot → determined by airline_code)
  - Swap execution (atomicity: both flights move or neither does)
  - Rejection (one airline refuses the swap)
  - Audit trail (all proposals + outcomes recorded)

**Key Files to Create:**
- `aerocommand/slot_negotiation.py` (250–350 lines)
- `tests/m5/test_slot_negotiation.py` (350–450 lines)

**Key Files to Modify:**
- `aerocommand/__init__.py` (expose `SlotNegotiator`)
- Integrate with `multi_store.py` (read/write swap state)

**Acceptance Criteria:**
- All 20 tests pass
- Deterministic tie-break: same two airlines + same slot → always same winner
- Atomicity verified: if one airline backs out, neither gets the slot
- Audit trail complete for all proposals and outcomes

---

### Phase 4: Fair Capacity Allocation (15 tests)

**Goal:** Ensure no single airline monopolizes shared ATC capacity; allocate fairly by percentage with hard limits.

**Requirements:**
- `fair_allocation.py`: Allocation logic, percentage-based fairness, anti-monopoly checks
- Allocation formula: each airline gets `(fleet_size / total_fleet_size) * capacity` with floor of 10% and ceiling of 60%
- Anti-monopoly: if an airline would exceed 60%, overflow goes to a shared pool (next-airline in round-robin)
- Rebalancing on fleet size changes (add/remove flights)
- Unit + integration tests: 15 tests covering:
  - Allocation math (3 airlines, 10/15/25 flights → 3/5/7 capacity shares)
  - Anti-monopoly (airline trying to claim >60% is capped)
  - Overflow routing (overflow goes to next airline in queue)
  - Rebalancing (add new airline → re-allocate)
  - Edge cases (1 airline, all zero-size airlines)

**Key Files to Create:**
- `aerocommand/fair_allocation.py` (200–300 lines)
- `tests/m5/test_fair_allocation.py` (250–350 lines)

**Key Files to Modify:**
- `aerocommand/__init__.py` (expose `FairAllocator`)
- `responder.py` or `responder_pool.py` (call allocator before issuing responses)

**Acceptance Criteria:**
- All 15 tests pass
- Fairness verified: no airline claims >60% without overflow
- Rebalancing is correct: adding a new airline re-allocates fairly
- Overflow routing is round-robin (repeatable, not random)

---

### Phase 5: Integration + E2E Tests (50+ tests total, mostly in this phase)

**Goal:** Wire all 4 components together and prove they work end-to-end with realistic ATC scenarios.

**Requirements:**
- Integrated scenario: "Parallel Universes" (2–3 airlines, shared slot, capacity contention)
- Full flow: TFM directive → responder pool → isolation check → allocation fairness
- Failover: one airline goes down → others unaffected
- State consistency: Postgres remains consistent across all 4 components
- Integration + E2E tests: 30+ tests covering:
  - Full scenario flow (create airlines → issue directives → verify isolation)
  - Capacity fairness (3 airlines, allocation math, overflow)
  - Slot negotiation in context (real flight swaps under allocation constraints)
  - Failover (airline deactivation → state cleanup → others unaffected)
  - Kafka pub-sub integration (DOWN topic → multiple airline subscribers)
  - Postgres consistency (no orphaned rows, no conflicts)
  - Idempotency (re-running same directive twice is safe)

**Key Files to Create:**
- `tests/m5/test_multiairline_scenario.py` (500–700 lines) — comprehensive E2E
- Update `ARCHITECTURE.md` with multi-airline section (150–200 lines)
- Update `README.md` with new flight command examples (if applicable)

**Key Files to Modify:**
- `aerocommand/__init__.py` (final assembly of all components)
- `cdm/transport.py` or new `cdm/multi_transport.py` (multi-airline Kafka routing)
- `adapters/kafka_event_bus.py` (DOWN topic subscriber per airline, UP aggregation)

**Acceptance Criteria:**
- All 30+ integration + E2E tests pass
- 265 inherited tests (M0–M4) still pass (no regression)
- Total test count ≥ 50 for M5 + ≥ 265 inherited
- ARCHITECTURE.md updated with multi-airline design
- Scenario: two airlines, one shared slot, one tries to exceed capacity → all correct outcomes

---

## Technical Design Decisions

### 1. **State Isolation: Per-Airline Postgres Schemas**
   - **Why:** True isolation (one airline's data cannot leak via SQL joins or views)
   - **How:** Create schema `airline_<code>` on first registration, migrate on airline activation
   - **Consistency:** Foreign key constraint validates but only within the schema

### 2. **Deterministic Tie-Break: Airline Code (Lexicographic)**
   - **Why:** Reproducible arbitration (no randomness, no clock-dependency)
   - **How:** When two airlines want the same slot, `min(airline_a.code, airline_b.code)` wins
   - **Test:** Same two airlines + same scenario → always same winner

### 3. **Kafka Pub-Sub: One DOWN Topic → N Subscribers**
   - **Why:** Multicast (ATC sends one directive, all airlines receive it)
   - **How:** DOWN topic has one partition; responder_pool subscribes and routes
   - **Scaling:** UP (response) topic aggregates all airlines' responses

### 4. **Fair Allocation: Percentage + Hard Ceiling**
   - **Why:** Prevents monopoly while respecting fleet size
   - **How:** Each airline = (fleet_size / total) * capacity, capped at 60%, floored at 10%
   - **Overflow:** Excess capacity → round-robin queue (next airline in order)

### 5. **Atomicity: All-or-Nothing Swaps**
   - **Why:** No partial swaps (data integrity)
   - **How:** Wrap swap execution in a Postgres transaction; rollback on any error
   - **Test:** Both airlines confirm or one refuses → no slot change

---

## Test Coverage Breakdown

| Phase | Tests | Focus |
|-------|-------|-------|
| 1 | 20 | Airline CRUD, state isolation, schema versioning |
| 2 | 25 | Responder pool, routing, isolation |
| 3 | 20 | Slot negotiation, tie-break, atomicity |
| 4 | 15 | Capacity allocation, fairness, overflow |
| 5 | 30+ | Integration, E2E, failover, consistency |
| **Inherited** | **265** | M0–M4 (no regression) |
| **Total** | **≥295** | All green |

---

## Dependency Order

```
Phase 1 ← (AirlineManager, MultiAirlineStateStore)
  ↓
Phase 2 ← (ResponderPool uses Phase 1)
  ↓
Phase 3 ← (SlotNegotiator uses Phase 1, isolated via MultiAirlineStateStore)
  ↓
Phase 4 ← (FairAllocator uses Phase 1, used by Phase 2)
  ↓
Phase 5 ← (Integration: wires 1–4 + adds E2E tests)
```

---

## Success Criteria

- [ ] All 50+ M5 tests pass (green)
- [ ] All 265 inherited tests still pass (M0–M4 regression-free)
- [ ] One airline failure ≠ federation failure (isolation + failover tested)
- [ ] Deterministic tie-break verified (same input → same output, always)
- [ ] Fair allocation verified (no airline >60%, overflow round-robin)
- [ ] Per-airline Postgres schemas created + migrated correctly
- [ ] Kafka pub-sub routes DOWN to all airlines, aggregates UP correctly
- [ ] ARCHITECTURE.md updated with multi-airline section
- [ ] Code passes lint (ruff) + format (black)
- [ ] Release tag `v2.0.0-aerosense-multiairline` created after all tests pass

---

## Timeline (Estimated)

| Phase | Est. Duration | Est. Lines | Notes |
|-------|---------------|-----------|-------|
| 1 | 1–1.5 days | 500–600 | Foundation; tight test coverage |
| 2 | 1–1.5 days | 400–500 | Builds on Phase 1; isolation testing |
| 3 | 1–1.5 days | 400–500 | Algorithmic; determinism testing critical |
| 4 | 0.5–1 day | 300–400 | Math-heavy; allocation tests |
| 5 | 1–2 days | 500–800 | Integration, E2E, documentation |
| **Total** | **5–7 days (equivalent)** | **~2500 LOC** | Executable agent work |

---

## Known Constraints

1. **No LLM calls:** All code is deterministic (responder, allocation, negotiation).
2. **Postgres required:** Per-airline schemas need a running Postgres instance.
3. **Kafka optional for Phase 1–4:** Phase 5 integration test will require Kafka (docker-compose ready).
4. **Inheritance:** Must not break existing M0–M4 tests (e.g., single-airline responder must still work).
5. **Backward compatibility:** `responder.py` should accept optional `airline_id` to avoid rewriting M0–M4 tests.

---

## Next Steps

1. **Execute Phase 1:** Implement `airline_manager.py` + `multi_store.py`, write 20 tests, verify isolation.
2. **Verify Phase 1:** All 20 tests pass, state isolation confirmed.
3. **Iterate Phases 2–5:** Follow the same pattern for each phase.
4. **Final Verification:** All 50+ M5 + 265 inherited tests pass.
5. **Documentation + Release:** Update ARCHITECTURE.md, create v2.0.0 tag, push to release/aerosense-multiairline.

