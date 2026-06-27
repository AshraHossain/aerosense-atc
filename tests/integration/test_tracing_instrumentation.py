"""Integration tests: a real graph run must produce a real trace — node spans
for all 12 phases, llm spans nested under the 11 that call Gemini, and decision
spans from the routers. Mocks only the network boundary (genai.GenerativeModel),
so call_gemini's own tracing code, the graph wiring, and the routers all run for
real."""

from unittest.mock import MagicMock, patch

import pytest

from aerosense.graph import atc_app
from core.tracing.tracer import get_tracer
from simulation.scenario_generator import generate_scenario


def _invoke(scenario: dict):
    """atc_app now carries a checkpointer (for the HITL gate), which requires a
    thread_id in config; scenario_id is already unique per generated scenario."""
    config = {"configurable": {"thread_id": scenario["scenario_id"]}}
    return atc_app.invoke(scenario, config=config)


def _mock_gemini_returning_empty_json():
    """Patch the genai model used inside agents.base.call_gemini so every phase's
    LLM call returns `{}` — every phase node tolerates missing keys via .get(...,
    default), so this drives the graph to completion deterministically and fast,
    without a real Gemini call."""
    mock_response = MagicMock()
    mock_response.text = "{}"
    mock_model = MagicMock()
    mock_model.generate_content.return_value = mock_response
    return patch("agents.base.genai.GenerativeModel", return_value=mock_model)


def test_full_nominal_run_produces_a_trace():
    scenario = generate_scenario("nominal")
    with _mock_gemini_returning_empty_json():
        _invoke(scenario)
    spans = get_tracer().spans_for(scenario["scenario_id"])
    assert len(spans) > 0


def test_full_nominal_run_has_a_node_span_for_every_visited_phase():
    # phase_09_emergency is reached only via the routers' conditional bypass, so a
    # genuinely nominal run (no emergency squawk, no alert conflict) never visits
    # it — that IS the intended behavior, not a gap. Expect the other 11.
    scenario = generate_scenario("nominal")
    with _mock_gemini_returning_empty_json():
        _invoke(scenario)
    spans = get_tracer().spans_for(scenario["scenario_id"])
    node_names = {s.name for s in spans if s.kind == "node"}
    expected = {
        "phase_01_surveillance", "phase_02_flight_plan", "phase_03_sector",
        "phase_04_conflict", "phase_05_clearance", "phase_06_comms",
        "phase_07_handoff", "phase_08_weather", "phase_10_tfm",
        "phase_11_audit", "phase_12_supervisor",
    }
    assert expected <= node_names, expected - node_names
    assert "phase_09_emergency" not in node_names


def test_full_nominal_run_llm_spans_cover_the_unconditional_callers():
    # Phases 05/06/07/09/10 each have an early-return guard and skip the Gemini
    # call when their upstream data is empty — which it is here, since every
    # mocked response is `{}`. Only 01/02/03/04/08/12 call Gemini unconditionally
    # regardless of input, so assert exactly those appear as llm-span parents,
    # rather than asserting a fixed total that depends on incidental cascading.
    scenario = generate_scenario("nominal")
    with _mock_gemini_returning_empty_json():
        _invoke(scenario)
    spans = get_tracer().spans_for(scenario["scenario_id"])
    by_id = {s.span_id: s for s in spans}
    llm_parent_names = {
        by_id[s.parent_span_id].name for s in spans
        if s.kind == "llm" and s.parent_span_id in by_id
    }
    assert llm_parent_names == {
        "phase_01_surveillance", "phase_02_flight_plan", "phase_03_sector",
        "phase_04_conflict", "phase_08_weather", "phase_12_supervisor",
    }


def test_llm_spans_are_parented_under_a_node_span():
    scenario = generate_scenario("nominal")
    with _mock_gemini_returning_empty_json():
        _invoke(scenario)
    spans = get_tracer().spans_for(scenario["scenario_id"])
    by_id = {s.span_id: s for s in spans}
    for s in spans:
        if s.kind == "llm":
            assert s.parent_span_id in by_id
            assert by_id[s.parent_span_id].kind == "node"


def test_full_run_has_decision_spans():
    scenario = generate_scenario("nominal")
    with _mock_gemini_returning_empty_json():
        _invoke(scenario)
    spans = get_tracer().spans_for(scenario["scenario_id"])
    decisions = {s.name for s in spans if s.kind == "decision"}
    assert "route_after_surveillance" in decisions
    assert "route_after_conflict" in decisions
    assert "route_after_supervisor" in decisions


def test_nominal_decision_does_not_bypass_to_emergency():
    scenario = generate_scenario("nominal")
    with _mock_gemini_returning_empty_json():
        _invoke(scenario)
    spans = get_tracer().spans_for(scenario["scenario_id"])
    surveillance_decision = next(
        s for s in spans if s.kind == "decision" and s.name == "route_after_surveillance"
    )
    assert surveillance_decision.attributes["chosen"] == "phase_02_flight_plan"


def test_emergency_scenario_decision_records_emergency_bypass():
    scenario = generate_scenario("emergency")
    with _mock_gemini_returning_empty_json():
        _invoke(scenario)
    spans = get_tracer().spans_for(scenario["scenario_id"])
    surveillance_decision = next(
        s for s in spans if s.kind == "decision" and s.name == "route_after_surveillance"
    )
    assert surveillance_decision.attributes["chosen"] == "phase_09_emergency"
    assert surveillance_decision.attributes["matched_squawk"] == "7700"


def test_emergency_scenario_has_emergency_node_span():
    scenario = generate_scenario("emergency")
    with _mock_gemini_returning_empty_json():
        _invoke(scenario)
    spans = get_tracer().spans_for(scenario["scenario_id"])
    node_names = {s.name for s in spans if s.kind == "node"}
    assert "phase_09_emergency" in node_names


def test_all_node_spans_ok_status_on_clean_run():
    scenario = generate_scenario("nominal")
    with _mock_gemini_returning_empty_json():
        _invoke(scenario)
    spans = get_tracer().spans_for(scenario["scenario_id"])
    assert all(s.status == "ok" for s in spans)


def test_tree_for_scenario_has_root_nodes():
    scenario = generate_scenario("nominal")
    with _mock_gemini_returning_empty_json():
        _invoke(scenario)
    tree = get_tracer().tree_for(scenario["scenario_id"])
    assert len(tree) > 0
    assert tree[0]["kind"] == "node"


def test_two_scenarios_do_not_share_spans():
    s1 = generate_scenario("nominal")
    s2 = generate_scenario("nominal")
    with _mock_gemini_returning_empty_json():
        _invoke(s1)
        _invoke(s2)
    spans1 = get_tracer().spans_for(s1["scenario_id"])
    spans2 = get_tracer().spans_for(s2["scenario_id"])
    ids1 = {s.span_id for s in spans1}
    ids2 = {s.span_id for s in spans2}
    assert ids1.isdisjoint(ids2)


def test_single_node_instrumentation_in_isolation():
    """Lower-level check: traced_node + call_gemini together produce exactly one
    node span with one llm child, without running the whole graph."""
    from agents.phase_08_weather import phase_08_node
    from core.tracing.tracer import traced_node

    state = {"scenario_id": "single-node-test", "flights": [], "flight_plans": {},
             "raw_contacts": [], "events": []}
    wrapped = traced_node("phase_08_weather")(phase_08_node)
    with _mock_gemini_returning_empty_json():
        wrapped(state)
    spans = get_tracer().spans_for("single-node-test")
    assert len(spans) == 2
    node = next(s for s in spans if s.kind == "node")
    llm = next(s for s in spans if s.kind == "llm")
    assert llm.parent_span_id == node.span_id
