"""Audit-chain tests — pure hash logic (no shared state) + chain append/verify and
tamper detection. Each AuditChain is constructed fresh, so tests never contaminate
each other."""

import pytest

from core.audit.chain import (
    GENESIS_HASH,
    AuditChain,
    AuditEvent,
    compute_hash,
)


# ----------------------------- pure hash logic ----------------------------- #
def _h(prev="p", **ov):
    base = dict(event_type="e", actor="a", details={"k": 1}, created_at="2026-01-01T00:00:00+00:00")
    base.update(ov)
    return compute_hash(prev, **base)


def test_hash_deterministic():
    assert _h() == _h()


def test_hash_is_64_hex():
    h = _h()
    assert len(h) == 64
    int(h, 16)


def test_hash_depends_on_prev():
    assert _h(prev="A") != _h(prev="B")


def test_hash_depends_on_event_type():
    assert _h(event_type="x") != _h(event_type="y")


def test_hash_depends_on_actor():
    assert _h(actor="ctrl-1") != _h(actor="ctrl-2")


def test_hash_depends_on_details():
    assert _h(details={"k": 1}) != _h(details={"k": 2})


def test_hash_independent_of_detail_key_order():
    a = compute_hash("p", event_type="e", actor="a", details={"x": 1, "y": 2}, created_at="t")
    b = compute_hash("p", event_type="e", actor="a", details={"y": 2, "x": 1}, created_at="t")
    assert a == b


# --------------------------------- chain ----------------------------------- #
def test_empty_chain_verifies():
    assert AuditChain().verify() == []


def test_empty_chain_len_zero():
    assert len(AuditChain()) == 0


def test_record_returns_event():
    chain = AuditChain()
    ev = chain.record("clearance.issued", "CTR-EAST", {"callsign": "AAL123"})
    assert isinstance(ev, AuditEvent)
    assert ev.seq == 1
    assert ev.event_type == "clearance.issued"


def test_first_event_chains_from_genesis():
    chain = AuditChain()
    ev = chain.record("e", "a")
    assert ev.prev_hash == GENESIS_HASH


def test_seq_increments():
    chain = AuditChain()
    a = chain.record("a", "x")
    b = chain.record("b", "x")
    assert (a.seq, b.seq) == (1, 2)


def test_consecutive_events_link():
    chain = AuditChain()
    a = chain.record("a", "x")
    b = chain.record("b", "x")
    assert b.prev_hash == a.hash


def test_single_event_chain_verifies():
    chain = AuditChain()
    chain.record("emergency.declared", "CTR-HIGH", {"callsign": "UAL789", "squawk": "7700"})
    assert chain.verify() == []


def test_many_events_verify():
    chain = AuditChain()
    for i in range(10):
        chain.record(f"event.{i}", "system", {"i": i})
    assert chain.verify() == []
    assert len(chain) == 10


def test_events_property_is_a_copy():
    chain = AuditChain()
    chain.record("a", "x")
    events = chain.events
    events.clear()
    assert len(chain) == 1  # mutating the returned list must not affect the chain


def test_verify_detects_mutated_details():
    chain = AuditChain()
    chain.record("a", "x", {"amount": 100})
    chain.record("b", "x")
    # Tamper with the first event's details (frozen dataclass, but the dict is mutable).
    chain.events[0].details["amount"] = 999
    chain._events[0].details["amount"] = 999
    problems = chain.verify()
    assert any("seq=1" in p for p in problems)


def test_verify_detects_broken_link():
    chain = AuditChain()
    chain.record("a", "x")
    chain.record("b", "x")
    # Rebuild event 2 with a corrupted prev_hash to simulate tampering/reorder.
    bad = AuditEvent(seq=2, event_type="b", actor="x", details={},
                     prev_hash="f" * 64, hash=chain._events[1].hash,
                     created_at=chain._events[1].created_at)
    chain._events[1] = bad
    problems = chain.verify()
    assert any("seq=2" in p for p in problems)


def test_verify_detects_deleted_event():
    chain = AuditChain()
    chain.record("a", "x")
    chain.record("b", "x")
    chain.record("c", "x")
    del chain._events[1]  # delete the middle event
    # remaining seq=3 event's prev_hash no longer matches its predecessor
    assert chain.verify() != []


def test_audit_event_to_dict_keys():
    chain = AuditChain()
    d = chain.record("a", "x", {"k": 1}).to_dict()
    assert set(d) == {"seq", "event_type", "actor", "details", "prev_hash",
                      "hash", "created_at"}


def test_independent_chains_do_not_share_state():
    c1, c2 = AuditChain(), AuditChain()
    c1.record("a", "x")
    assert len(c1) == 1 and len(c2) == 0


def test_atc_decision_log_example():
    """A realistic ATC decision sequence verifies end-to-end."""
    chain = AuditChain()
    chain.record("surveillance.fused", "system", {"flights": 10})
    chain.record("conflict.detected", "system", {"pair": ["AAL123", "UAL456"], "sev": "alert"})
    chain.record("clearance.issued", "CTR-HIGH", {"callsign": "AAL123", "instruction": "climb FL370"})
    chain.record("emergency.declared", "CTR-HIGH", {"callsign": "UAL789", "type": "mayday"})
    assert chain.verify() == []
    assert len(chain) == 4
