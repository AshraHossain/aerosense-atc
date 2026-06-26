"""LangSmith tracer tests — in-memory buffer works without LangSmith API key."""

import os
import pytest

# Mock LangSmith if not available
try:
    from adapters.langsmith_tracer import LangSmithTracer
    LANGSMITH_AVAILABLE = True
except ImportError:
    LANGSMITH_AVAILABLE = False


@pytest.mark.skipif(not LANGSMITH_AVAILABLE, reason="langsmith not installed")
class TestLangSmithTracer:
    """Tests for LangSmith tracer integration."""

    def test_langsmith_tracer_requires_api_key(self):
        """LangSmith tracer requires an API key."""
        # Ensure LANGSMITH_API_KEY is not set
        old_key = os.environ.pop("LANGSMITH_API_KEY", None)
        try:
            with pytest.raises(ValueError, match="LANGSMITH_API_KEY"):
                LangSmithTracer()
        finally:
            # Restore the key
            if old_key:
                os.environ["LANGSMITH_API_KEY"] = old_key

    def test_langsmith_tracer_with_explicit_key(self):
        """LangSmith tracer can be initialized with explicit API key."""
        tracer = LangSmithTracer(api_key="test-key-12345")
        assert tracer.api_key == "test-key-12345"
        assert tracer.project_name == "aerosense-atc"

    def test_langsmith_tracer_logs_to_memory(self):
        """Events are buffered in memory regardless of LangSmith connectivity."""
        tracer = LangSmithTracer(api_key="test-key")
        tracer.log("phase_start", {"phase": 1})
        tracer.log("llm_call", {"model": "gemini-2.0", "temperature": 0.1})

        events = tracer.get_trace()
        assert len(events) == 2
        assert events[0]["event_type"] == "phase_start"
        assert events[1]["event_type"] == "llm_call"

    def test_langsmith_tracer_export_json(self):
        """Tracer exports events to JSON."""
        tracer = LangSmithTracer(api_key="test-key")
        tracer.log("decision", {"decision": "route_to_emergency"})

        json_str = tracer.export(format="json")
        assert "decision" in json_str
        assert "route_to_emergency" in json_str

    def test_langsmith_tracer_clear(self):
        """Tracer can clear in-memory events."""
        tracer = LangSmithTracer(api_key="test-key")
        tracer.log("event", {})
        tracer.clear()

        assert len(tracer.get_trace()) == 0
