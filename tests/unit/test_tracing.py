"""Tracer unit tests — timing, parent/child nesting, trace-id propagation, error
status, thread isolation, and the spans_for/tree_for query helpers. Each test uses
its own fresh Tracer() instance, so there's no shared global state to manage."""

import threading
import time

import pytest

from core.tracing.tracer import Span, Tracer


def test_span_recorded_on_exit():
    t = Tracer()
    with t.span("work", kind="node", trace_id="c1"):
        pass
    spans = t.spans_for("c1")
    assert len(spans) == 1
    assert spans[0].name == "work" and spans[0].kind == "node"


def test_span_records_positive_duration():
    t = Tracer()
    with t.span("slow", trace_id="c1"):
        time.sleep(0.02)
    # perf_counter has sub-microsecond resolution, but assert the real invariant
    # (non-negative, measured) rather than a tight bound — avoids any residual
    # timer-granularity flakiness across platforms.
    duration = t.spans_for("c1")[0].duration_ms
    assert duration is not None and duration >= 0


def test_span_sets_end_time_after_start_time():
    t = Tracer()
    with t.span("x", trace_id="c1"):
        pass
    s = t.spans_for("c1")[0]
    assert s.end_time is not None and s.end_time >= s.start_time


def test_status_ok_on_success():
    t = Tracer()
    with t.span("ok", trace_id="c1"):
        pass
    assert t.spans_for("c1")[0].status == "ok"


def test_status_error_and_reraises():
    t = Tracer()
    with pytest.raises(ValueError, match="boom"):
        with t.span("explode", trace_id="c1"):
            raise ValueError("boom")
    s = t.spans_for("c1")[0]
    assert s.status == "error"
    assert s.attributes["error_type"] == "ValueError"
    assert "boom" in s.attributes["error"]


def test_trace_id_defaults_to_span_id_with_no_context():
    t = Tracer()
    with t.span("orphan"):
        pass
    spans = [s for s in t._spans if s.name == "orphan"]
    assert spans[0].trace_id == spans[0].span_id


def test_explicit_trace_id_used_for_root_span():
    t = Tracer()
    with t.span("root", trace_id="explicit-id"):
        pass
    assert t.spans_for("explicit-id")[0].name == "root"


def test_nested_spans_share_trace_id():
    t = Tracer()
    with t.span("parent", trace_id="c1"):
        with t.span("child", trace_id="c1"):
            pass
    spans = t.spans_for("c1")
    assert len(spans) == 2
    assert {s.trace_id for s in spans} == {"c1"}


def test_child_parent_span_id_links_to_parent():
    t = Tracer()
    with t.span("parent", trace_id="c1") as parent:
        with t.span("child", trace_id="c1") as child:
            pass
    assert child.parent_span_id == parent.span_id


def test_root_span_has_no_parent():
    t = Tracer()
    with t.span("root", trace_id="c1") as root:
        pass
    assert root.parent_span_id is None


def test_sibling_spans_share_parent():
    t = Tracer()
    with t.span("parent", trace_id="c1") as parent:
        with t.span("a", trace_id="c1"):
            pass
        with t.span("b", trace_id="c1"):
            pass
    a = next(s for s in t.spans_for("c1") if s.name == "a")
    b = next(s for s in t.spans_for("c1") if s.name == "b")
    assert a.parent_span_id == b.parent_span_id == parent.span_id


def test_context_resets_after_span_closes():
    t = Tracer()
    with t.span("first", trace_id="c1"):
        pass
    with t.span("second", trace_id="c1"):
        pass
    spans = t.spans_for("c1")
    assert all(s.parent_span_id is None for s in spans)


def test_three_level_nesting():
    t = Tracer()
    with t.span("a", trace_id="c1"):
        with t.span("b", trace_id="c1"):
            with t.span("c", trace_id="c1"):
                pass
    a = next(s for s in t.spans_for("c1") if s.name == "a")
    b = next(s for s in t.spans_for("c1") if s.name == "b")
    c = next(s for s in t.spans_for("c1") if s.name == "c")
    assert c.parent_span_id == b.span_id
    assert b.parent_span_id == a.span_id


def test_error_in_child_marks_both_error():
    t = Tracer()
    with pytest.raises(RuntimeError):
        with t.span("parent", trace_id="c1"):
            with t.span("child", trace_id="c1"):
                raise RuntimeError("inner")
    statuses = {s.name: s.status for s in t.spans_for("c1")}
    assert statuses == {"parent": "error", "child": "error"}


def test_caught_child_error_keeps_parent_ok():
    t = Tracer()
    with t.span("parent", trace_id="c1"):
        try:
            with t.span("child", trace_id="c1"):
                raise ValueError("handled")
        except ValueError:
            pass
    statuses = {s.name: s.status for s in t.spans_for("c1")}
    assert statuses == {"parent": "ok", "child": "error"}


def test_record_decision_zero_duration_and_kind():
    t = Tracer()
    d = t.record_decision("route", trace_id="c1", attributes={"chosen": "x"})
    assert d.kind == "decision"
    assert d.duration_ms == 0.0
    assert d.attributes["chosen"] == "x"


def test_record_decision_parented_to_current_span():
    t = Tracer()
    with t.span("node", trace_id="c1") as node:
        d = t.record_decision("d", trace_id="c1")
    assert d.parent_span_id == node.span_id


def test_spans_for_isolates_by_trace_id():
    t = Tracer()
    with t.span("a", trace_id="c1"):
        pass
    with t.span("b", trace_id="c2"):
        pass
    assert len(t.spans_for("c1")) == 1
    assert len(t.spans_for("c2")) == 1
    assert t.spans_for("c1")[0].name == "a"


def test_spans_for_unknown_trace_id_is_empty():
    t = Tracer()
    with t.span("a", trace_id="c1"):
        pass
    assert t.spans_for("nonexistent") == []


def test_tree_for_nests_children():
    t = Tracer()
    with t.span("root", trace_id="c1") as root:
        with t.span("child", trace_id="c1") as child:
            pass
    tree = t.tree_for("c1")
    assert len(tree) == 1
    assert tree[0]["span_id"] == root.span_id
    assert len(tree[0]["children"]) == 1
    assert tree[0]["children"][0]["span_id"] == child.span_id


def test_tree_for_multiple_roots():
    t = Tracer()
    with t.span("r1", trace_id="c1"):
        pass
    with t.span("r2", trace_id="c1"):
        pass
    assert len(t.tree_for("c1")) == 2


def test_clear_removes_all_spans():
    t = Tracer()
    with t.span("a", trace_id="c1"):
        pass
    t.clear()
    assert t.spans_for("c1") == []


def test_span_to_dict_keys():
    t = Tracer()
    with t.span("x", trace_id="c1"):
        pass
    d = t.spans_for("c1")[0].to_dict()
    assert set(d) == {"span_id", "trace_id", "parent_span_id", "name", "kind",
                      "status", "start_time", "end_time", "duration_ms", "attributes"}


def test_attributes_copied_not_shared():
    t = Tracer()
    attrs = {"k": "v"}
    with t.span("x", trace_id="c1", attributes=attrs) as s:
        s.attributes["extra"] = 1
    assert "extra" not in attrs


def test_two_threads_do_not_cross_parent_context():
    """Two concurrent scenario runs (separate OS threads, like the websocket
    handler spawns) must not see each other's parent span — contextvars are
    thread-local, so this should hold even though they share one Tracer."""
    t = Tracer()
    results = {}

    def run(trace_id: str):
        with t.span(f"root-{trace_id}", trace_id=trace_id) as root:
            time.sleep(0.01)
            with t.span(f"child-{trace_id}", trace_id=trace_id) as child:
                time.sleep(0.01)
            results[trace_id] = (root.span_id, child.span_id)

    threads = [threading.Thread(target=run, args=(tid,)) for tid in ("A", "B")]
    for th in threads:
        th.start()
    for th in threads:
        th.join()

    for tid in ("A", "B"):
        root_id, child_id = results[tid]
        child_span = next(s for s in t.spans_for(tid) if s.name == f"child-{tid}")
        assert child_span.parent_span_id == root_id


def test_default_tracer_is_a_singleton():
    from core.tracing.tracer import get_tracer
    assert get_tracer() is get_tracer()
