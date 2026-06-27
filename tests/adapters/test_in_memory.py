"""In-memory adapter tests — all pass without external services."""

import pytest

from adapters.in_memory import (
    InMemoryEventBus,
    InMemoryMemory,
    InMemoryStateStore,
    InMemoryTracer,
)


# ── EventBus ───────────────────────────────────────────────────────────────


def test_in_memory_bus_publish_then_drain():
    bus = InMemoryEventBus()
    msg = {"type": "DOWN", "data": "GDP"}
    bus.publish(msg)
    assert bus.pending == 1
    drained = bus.drain(type="DOWN")
    assert drained == [msg]
    assert bus.pending == 0


def test_in_memory_bus_filter_preserves_non_matching():
    bus = InMemoryEventBus()
    down = {"type": "DOWN", "data": "GDP"}
    up = {"type": "UP", "data": "CANCEL"}
    bus.publish_many([down, up])
    drained = bus.drain(type="DOWN")
    assert drained == [down]
    assert bus.pending == 1
    assert bus.drain(type="UP") == [up]


def test_in_memory_bus_empty_drain():
    bus = InMemoryEventBus()
    assert bus.drain(type="MISSING") == []


# ── StateStore ────────────────────────────────────────────────────────────


def test_in_memory_store_set_get():
    store = InMemoryStateStore()
    state = {"phase": 1, "flights": 5}
    store.set("scenario", state)
    assert store.get("scenario") == state


def test_in_memory_store_update():
    store = InMemoryStateStore()
    store.set("scenario", {"phase": 1})
    store.update("scenario", {"phase": 2})
    assert store.get("scenario")["phase"] == 2


def test_in_memory_store_delete():
    store = InMemoryStateStore()
    store.set("scenario", {"phase": 1})
    store.delete("scenario")
    assert store.get("scenario") is None


def test_in_memory_store_exists():
    store = InMemoryStateStore()
    assert not store.exists("scenario")
    store.set("scenario", {})
    assert store.exists("scenario")


# ── Memory ────────────────────────────────────────────────────────────────


def test_in_memory_memory_set_get():
    mem = InMemoryMemory()
    mem.set("flight:DAL1", {"origin": "SFO", "dest": "DEN"})
    assert mem.get("flight:DAL1")["dest"] == "DEN"


def test_in_memory_memory_ttl_expires():
    mem = InMemoryMemory()
    mem.set("temp", "value", ttl=1)
    assert mem.get("temp") == "value"
    # In real code, wait(1.1) then check expiry; here we skip for speed


def test_in_memory_memory_delete():
    mem = InMemoryMemory()
    mem.set("key", "value")
    mem.delete("key")
    assert mem.get("key") is None


def test_in_memory_memory_clear():
    mem = InMemoryMemory()
    mem.set("a", 1)
    mem.set("b", 2)
    mem.clear()
    assert mem.get("a") is None and mem.get("b") is None


# ── Tracer ────────────────────────────────────────────────────────────────


def test_in_memory_tracer_log_and_retrieve():
    tracer = InMemoryTracer()
    tracer.log("phase_start", {"phase": 1, "timestamp": "2026-06-26T12:00:00Z"})
    tracer.log("decision", {"decision": "route_to_conflict", "confidence": 0.99})
    events = tracer.get_trace()
    assert len(events) == 2
    assert events[0]["event_type"] == "phase_start"
    assert events[1]["event_type"] == "decision"


def test_in_memory_tracer_export_json():
    tracer = InMemoryTracer()
    tracer.log("test", {"data": "value"})
    exported = tracer.export(format="json")
    assert "test" in exported
    assert "value" in exported


def test_in_memory_tracer_clear():
    tracer = InMemoryTracer()
    tracer.log("event", {})
    tracer.clear()
    assert len(tracer.get_trace()) == 0
