"""AeroSense ATC — the air-traffic-control app (FAA side) of the AeroOps platform.

This package wires the 12 phase agents into the LangGraph state machine. It is an
*app*: it depends on `core/` (state, routing) and on the `agents/` it orchestrates.
`core/` never imports from here — that one-way dependency is the platform invariant
(enforced by tests/unit/test_core_invariant.py).
"""
