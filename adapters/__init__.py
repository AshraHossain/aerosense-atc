"""Pluggable infrastructure adapters.

AeroSense uses in-memory adapters. AeroCommand uses Kafka/Postgres/Redis.
Both resolve the four ports to concrete implementations at startup.

Observability: LangSmith tracer for end-to-end auditing (optional).
"""

from .in_memory import (
    InMemoryEventBus,
    InMemoryMemory,
    InMemoryStateStore,
    InMemoryTracer,
)

__all__ = [
    "InMemoryEventBus",
    "InMemoryStateStore",
    "InMemoryMemory",
    "InMemoryTracer",
]

# Optional LangSmith tracer
try:
    from .langsmith_tracer import LangSmithTracer
    __all__.append("LangSmithTracer")
except ImportError:
    pass
