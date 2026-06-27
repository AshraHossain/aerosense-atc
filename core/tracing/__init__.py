"""Tracing — OTel-shaped sync span recording (AeroOps M1).

Ported from AutoRedTeam's tracer; adapted to AeroSense's sync, in-memory,
threaded-per-scenario profile.
"""

from core.tracing.tracer import Span, Tracer, get_tracer, traced_node

__all__ = ["Span", "Tracer", "get_tracer", "traced_node"]
