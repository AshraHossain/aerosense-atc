"""LangSmith-backed Tracer for end-to-end observability.

Every LLM call, tool use, and decision is traced to LangSmith for audit and
debugging. Implements the Tracer port; can be swapped in at startup.
"""

import os
from typing import Any, Dict, List, Optional
from datetime import datetime

try:
    from langsmith import Client
    from langsmith.schemas import Run, RunTree
except ImportError:
    raise ImportError("langsmith not installed; pip install langsmith")

from core.ports import Tracer


class LangSmithTracer(Tracer):
    """Wraps LangSmith Client for the Tracer port interface."""

    def __init__(
        self,
        project_name: str = "aerosense-atc",
        api_key: Optional[str] = None,
        api_url: Optional[str] = None,
    ):
        """Initialize LangSmith client.

        Args:
            project_name: LangSmith project name (default: aerosense-atc)
            api_key: LANGSMITH_API_KEY (reads from env if not provided)
            api_url: LANGSMITH_ENDPOINT (reads from env if not provided)
        """
        self.project_name = project_name
        self.api_key = api_key or os.getenv("LANGSMITH_API_KEY")
        self.api_url = api_url or os.getenv("LANGSMITH_ENDPOINT")

        if not self.api_key:
            raise ValueError(
                "LANGSMITH_API_KEY required; set env var or pass api_key= to constructor"
            )

        self.client = Client(api_key=self.api_key, endpoint=self.api_url)
        self._current_run: Optional[RunTree] = None
        self._events: List[Dict[str, Any]] = []

    def log(self, event_type: str, metadata: Dict[str, Any]) -> None:
        """Log an event to both in-memory buffer and LangSmith.

        Args:
            event_type: e.g., 'phase_start', 'llm_call', 'decision'
            metadata: arbitrary dict with event details
        """
        event = {
            "timestamp": datetime.utcnow().isoformat(),
            "event_type": event_type,
            **metadata,
        }
        self._events.append(event)

        # Send to LangSmith as a child run
        if event_type == "llm_call":
            self._log_llm_call(metadata)
        elif event_type == "tool_use":
            self._log_tool_use(metadata)
        elif event_type == "decision":
            self._log_decision(metadata)
        else:
            # Generic event as a tag/metadata
            if self._current_run:
                self._current_run.add_metadata(
                    {event_type: metadata}
                )

    def _log_llm_call(self, metadata: Dict[str, Any]) -> None:
        """Log an LLM call to LangSmith."""
        if not self._current_run:
            return

        model = metadata.get("model", "unknown")
        input_text = metadata.get("prompt", "")[:200]  # truncate for clarity
        output_text = metadata.get("output", "")[:200]

        # Create a child run for the LLM call
        run = self.client.create_run(
            name=f"llm_{model}",
            run_type="llm",
            project_name=self.project_name,
            inputs={"prompt": input_text},
            metadata={"temperature": metadata.get("temperature", 0.1)},
        )
        run.end(outputs={"response": output_text})

    def _log_tool_use(self, metadata: Dict[str, Any]) -> None:
        """Log a tool call to LangSmith."""
        if not self._current_run:
            return

        tool_name = metadata.get("tool", "unknown")
        run = self.client.create_run(
            name=f"tool_{tool_name}",
            run_type="tool",
            project_name=self.project_name,
            inputs=metadata.get("input", {}),
        )
        run.end(outputs=metadata.get("output", {}))

    def _log_decision(self, metadata: Dict[str, Any]) -> None:
        """Log a decision (routing, approval, etc.) to LangSmith."""
        if not self._current_run:
            return

        decision = metadata.get("decision", "unknown")
        self._current_run.add_metadata({"decision": decision})

    def get_trace(self) -> List[Dict[str, Any]]:
        """Retrieve in-memory trace events."""
        return self._events.copy()

    def export(self, format: str = "json") -> str:
        """Export trace as JSON."""
        if format == "json":
            import json

            return json.dumps(self._events, indent=2, default=str)
        raise ValueError(f"unsupported format: {format}")

    def clear(self) -> None:
        """Clear in-memory trace (LangSmith history is not cleared)."""
        self._events.clear()

    def start_run(self, name: str, **metadata) -> None:
        """Start a new top-level run for a scenario execution."""
        self._current_run = self.client.create_run(
            name=name,
            run_type="chain",
            project_name=self.project_name,
            metadata=metadata,
        )

    def end_run(self, outputs: Optional[Dict[str, Any]] = None) -> None:
        """End the current run."""
        if self._current_run:
            self._current_run.end(outputs=outputs or {})
            self._current_run = None
