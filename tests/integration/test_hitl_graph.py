"""Integration tests: a real ground_stop proposal must pause the COMPILED graph
at hitl_gate, and an approval must resume it to completion. Mocks only the
network boundary, keyed by which phase's system prompt is in play, so phase_03
can report an overloaded sector and phase_10 can propose the ground_stop that
triggers the gate — everything else returns an empty/neutral response.
"""

import json
from unittest.mock import MagicMock, patch

from aerosense.graph import atc_app
from core.hitl import get_approval_gate
from simulation.scenario_generator import generate_scenario

_OVERLOADED_SECTORS_RESPONSE = json.dumps({
    "sectors": {"HIGH": {"sector_id": "HIGH", "name": "High Altitude En-Route",
                         "alt_low_ft": 18000, "alt_high_ft": 45000,
                         "traffic_count": 20, "load_pct": 95.0, "controller": "CTR-HIGH"}},
    "sector_assignments": {}, "overloaded_sectors": ["HIGH"],
    "assignment_notes": "HIGH at 95% capacity",
})

_GROUND_STOP_RESPONSE = json.dumps({
    "tfm_programs": [{"program_id": "TFM-GATE-1", "tfm_type": "ground_stop",
                      "affected_fix": "COATE", "rate_per_hour": 0,
                      "reason": "Test-induced sector overload", "active": True}],
    "tfm_notes": "Ground stop issued — last resort per minimum-intervention policy",
})

# Distinctive substrings from each phase's system prompt (core/prompts.py) used to
# route the mock's canned response without needing to mock 11 separate call sites.
_RESPONSES_TRIGGERING_GATE = {
    "Sector Manager": _OVERLOADED_SECTORS_RESPONSE,
    "Traffic Flow Management": _GROUND_STOP_RESPONSE,
}


def _mock_gemini_keyed_by_system(responses: dict[str, str]):
    def factory(**kwargs):
        system = kwargs.get("system_instruction") or ""
        json_text = "{}"
        for key, text in responses.items():
            if key in system:
                json_text = text
                break
        model = MagicMock()
        model.generate_content.return_value = MagicMock(text=json_text)
        return model
    return patch("agents.base.genai.GenerativeModel", side_effect=factory)


def _run_to_gate(scenario_id_suffix: str):
    """Run a scenario through to the gate; returns (scenario, config)."""
    scenario = generate_scenario("nominal")
    scenario["scenario_id"] = f"{scenario['scenario_id']}-{scenario_id_suffix}"
    config = {"configurable": {"thread_id": scenario["scenario_id"]}}
    with _mock_gemini_keyed_by_system(_RESPONSES_TRIGGERING_GATE):
        atc_app.invoke(scenario, config=config)
    return scenario, config


def test_active_ground_stop_pauses_at_hitl_gate():
    scenario, config = _run_to_gate("pause-1")
    snapshot = atc_app.get_state(config)
    assert snapshot.next == ("hitl_gate",)


def test_pause_writes_a_pending_approval():
    scenario, config = _run_to_gate("pause-2")
    pending = get_approval_gate().pending_for(scenario["scenario_id"])
    assert len(pending) == 1
    assert pending[0].payload["tfm_programs"][0]["program_id"] == "TFM-GATE-1"


def test_phase_11_and_12_have_not_run_while_paused():
    scenario, config = _run_to_gate("pause-3")
    state = atc_app.get_state(config).values
    assert "phase_11" not in state.get("phases_completed", [])
    assert "phase_12" not in state.get("phases_completed", [])


def test_approval_resumes_graph_to_completion():
    scenario, config = _run_to_gate("resume-1")
    pending = get_approval_gate().pending_for(scenario["scenario_id"])
    get_approval_gate().approve(pending[0].id, decided_by="ctrl-high")

    with _mock_gemini_keyed_by_system(_RESPONSES_TRIGGERING_GATE):
        final = atc_app.invoke(None, config=config)

    assert "phase_12" in final["phases_completed"]
    snapshot = atc_app.get_state(config)
    assert snapshot.next == ()  # fully completed, nothing pending


def test_rejection_leaves_graph_paused_but_marks_request_rejected():
    scenario, config = _run_to_gate("reject-1")
    pending = get_approval_gate().pending_for(scenario["scenario_id"])
    rejected = get_approval_gate().reject(pending[0].id, decided_by="ctrl-high")
    assert rejected.status == "rejected"
    # Rejecting doesn't itself resume the graph — that's a caller-level policy
    # decision (e.g. cancel the run); the gate's job is only to record the
    # decision. Graph remains paused until something calls .invoke(None, ...).
    snapshot = atc_app.get_state(config)
    assert snapshot.next == ("hitl_gate",)


def test_scenario_without_ground_stop_never_pauses():
    """Negative control: the same nominal scenario, with NO overloaded sector in
    the mocked response, must run to completion in a single invoke — proving the
    gate doesn't fire for the common case."""
    scenario = generate_scenario("nominal")
    scenario["scenario_id"] = f"{scenario['scenario_id']}-no-gate"
    config = {"configurable": {"thread_id": scenario["scenario_id"]}}

    def factory(**kwargs):
        model = MagicMock()
        model.generate_content.return_value = MagicMock(text="{}")
        return model

    with patch("agents.base.genai.GenerativeModel", side_effect=factory):
        final = atc_app.invoke(scenario, config=config)

    assert "phase_12" in final["phases_completed"]
    assert atc_app.get_state(config).next == ()
    assert get_approval_gate().pending_for(scenario["scenario_id"]) == []
