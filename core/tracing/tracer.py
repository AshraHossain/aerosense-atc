"""A small sync tracer (AeroOps M1 — "trace every retrieval, reasoning step, tool
call, and decision").

Ported from AutoRedTeam's async OTel-shaped tracer, adapted to AeroSense's profile:
every phase node, the Gemini call, and the LangGraph orchestration here are
synchronous (no asyncio), and there is no database — state lives in `ATCState` and
is streamed to the dashboard over websockets. So spans are kept in-memory, with the
same OTel-shaped row (trace_id/span_id/parent_span_id/attributes) AutoRedTeam used,
behind a `threading.Lock`: the websocket handler runs each scenario in its own
background thread, so concurrent campaigns must not corrupt each other's span list.

Parent/trace context uses `contextvars`, which — same as AutoRedTeam's asyncio-task
isolation — also isolates correctly across OS threads (each thread gets its own
context), so two scenarios running in two threads never see each other's parent
span.
"""

from __future__ import annotations

import functools
import threading
import time
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime, timezone

_current_trace_id: ContextVar[str | None] = ContextVar("current_trace_id", default=None)
_current_span_id: ContextVar[str | None] = ContextVar("current_span_id", default=None)


@dataclass
class Span:
    span_id: str
    trace_id: str
    parent_span_id: str | None
    name: str
    kind: str  # node | llm | tool | decision
    start_time: datetime
    status: str = "ok"
    end_time: datetime | None = None
    duration_ms: float | None = None
    attributes: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "span_id": self.span_id, "trace_id": self.trace_id,
            "parent_span_id": self.parent_span_id, "name": self.name,
            "kind": self.kind, "status": self.status,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration_ms": self.duration_ms, "attributes": self.attributes,
        }


class Tracer:
    """In-memory span recorder. Thread-safe append; `spans_for`/`tree_for` filter
    by trace_id so concurrent runs (and concurrent tests) don't see each other's
    spans even though they share one Tracer instance."""

    def __init__(self) -> None:
        self._spans: list[Span] = []
        self._lock = threading.Lock()

    @contextmanager
    def span(self, name: str, kind: str = "node",
            trace_id: str | None = None, attributes: dict | None = None):
        span_id = str(uuid.uuid4())
        resolved_trace_id = _current_trace_id.get() or trace_id or span_id
        parent_span_id = _current_span_id.get()
        rec = Span(
            span_id=span_id, trace_id=resolved_trace_id, parent_span_id=parent_span_id,
            name=name, kind=kind, start_time=datetime.now(timezone.utc),
            attributes=dict(attributes or {}),
        )
        trace_token = _current_trace_id.set(resolved_trace_id)
        span_token = _current_span_id.set(span_id)
        # perf_counter, not monotonic: on Windows, monotonic() is GetTickCount64-based
        # (~15.6ms resolution), so short spans can measure as exactly 0ms. perf_counter
        # is QueryPerformanceCounter-based (sub-microsecond) — the correct stdlib tool
        # for measuring an elapsed interval rather than telling wall-clock progression.
        t0 = time.perf_counter()
        try:
            yield rec
        except Exception as exc:
            rec.status = "error"
            rec.attributes["error_type"] = type(exc).__name__
            rec.attributes["error"] = str(exc)[:500]
            raise
        finally:
            rec.end_time = datetime.now(timezone.utc)
            rec.duration_ms = (time.perf_counter() - t0) * 1000
            _current_span_id.reset(span_token)
            _current_trace_id.reset(trace_token)
            with self._lock:
                self._spans.append(rec)

    def record_decision(self, name: str, trace_id: str | None = None,
                        attributes: dict | None = None) -> Span:
        """Zero-duration span for a routing decision, parented to the current span."""
        now = datetime.now(timezone.utc)
        rec = Span(
            span_id=str(uuid.uuid4()),
            trace_id=_current_trace_id.get() or trace_id or str(uuid.uuid4()),
            parent_span_id=_current_span_id.get(),
            name=name, kind="decision", start_time=now, end_time=now,
            duration_ms=0.0, attributes=dict(attributes or {}),
        )
        with self._lock:
            self._spans.append(rec)
        return rec

    def spans_for(self, trace_id: str) -> list[Span]:
        with self._lock:
            return [s for s in self._spans if s.trace_id == trace_id]

    def tree_for(self, trace_id: str) -> list[dict]:
        """Nest spans_for(trace_id) by parent_span_id into a forest of dicts."""
        spans = sorted(self.spans_for(trace_id), key=lambda s: s.start_time)
        nodes = {s.span_id: {**s.to_dict(), "children": []} for s in spans}
        roots: list[dict] = []
        for s in spans:
            node = nodes[s.span_id]
            parent = nodes.get(s.parent_span_id) if s.parent_span_id else None
            (parent["children"] if parent is not None else roots).append(node)
        return roots

    def clear(self) -> None:
        """Test/debug helper — drop all recorded spans."""
        with self._lock:
            self._spans.clear()


_TRACER: Tracer | None = None


def get_tracer() -> Tracer:
    """Process-wide tracer used by the live graph and call_gemini."""
    global _TRACER
    if _TRACER is None:
        _TRACER = Tracer()
    return _TRACER


def traced_node(name: str):
    """Decorator for a sync LangGraph node `fn(state) -> dict`. Uses
    state['scenario_id'] as the trace id so every span for one scenario run
    shares a trace, matching AutoRedTeam's campaign_id pattern."""
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(state):
            trace_id = state.get("scenario_id") if isinstance(state, dict) else None
            with get_tracer().span(name=name, kind="node", trace_id=trace_id):
                return fn(state)
        return wrapper
    return decorator
