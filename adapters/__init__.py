"""Pluggable infrastructure adapters.

AeroSense uses in-memory adapters. AeroCommand uses Kafka/Postgres/Redis.
Both resolve the four ports to concrete implementations at startup.
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
