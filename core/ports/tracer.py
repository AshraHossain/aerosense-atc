"""Tracer port — decision audit trail for DO-178C-inspired compliance.

Every agent decision, every tool call, every retrieval is logged with:
- timestamp
- phase / agent name
- decision / output
- metadata (model, confidence, retry count)
- cryptographic hash (immutable audit)
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class Tracer(ABC):
    """Abstract audit trace recorder.

    Enables replay, audit, and model-upgrade regression testing.
    """

    @abstractmethod
    def log(self, event_type: str, metadata: Dict[str, Any]) -> None:
        """Log an event with structured metadata.

        Args:
            event_type: e.g. 'phase_start', 'llm_call', 'decision', 'tool_use'
            metadata: arbitrary dict (timestamp/hash added automatically)
        """
        pass

    @abstractmethod
    def get_trace(self) -> List[Dict[str, Any]]:
        """Retrieve the full trace as a list of events (ordered by time)."""
        pass

    @abstractmethod
    def export(self, format: str = "json") -> str:
        """Export trace to a string (JSON, CSV, etc.)."""
        pass

    @abstractmethod
    def clear(self) -> None:
        """Clear all trace events (for test isolation)."""
        pass
