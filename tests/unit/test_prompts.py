"""Prompt registry + lockfile tests, and proof that each phase agent actually
sources its SYSTEM prompt from the registry (so the lock governs real behaviour,
not a decorative copy)."""

import hashlib
import importlib

import pytest

from core.prompts import LOCKS, PromptTemplate, all_prompts, get_prompt, verify_locks

AGENT_MODULES = {
    "phase_01.system": "agents.phase_01_surveillance",
    "phase_02.system": "agents.phase_02_flight_plan",
    "phase_03.system": "agents.phase_03_sector",
    "phase_04.system": "agents.phase_04_conflict",
    "phase_05.system": "agents.phase_05_clearance",
    "phase_06.system": "agents.phase_06_comms",
    "phase_07.system": "agents.phase_07_handoff",
    "phase_08.system": "agents.phase_08_weather",
    "phase_09.system": "agents.phase_09_emergency",
    "phase_10.system": "agents.phase_10_tfm",
    "phase_12.system": "agents.phase_12_supervisor",
}


def test_eleven_phase_prompts_registered():
    # Phase 11 (Audit) has no Gemini call — pure compliance aggregation.
    assert {p.name for p in all_prompts()} == set(AGENT_MODULES)


def test_phase_11_has_no_registered_prompt():
    with pytest.raises(KeyError):
        get_prompt("phase_11.system")


def test_get_prompt_returns_template():
    p = get_prompt("phase_04.system")
    assert isinstance(p, PromptTemplate)
    assert p.version == "1.0.0"
    assert "conflict" in p.template.lower()


def test_get_unknown_prompt_raises():
    with pytest.raises(KeyError, match="Unknown prompt"):
        get_prompt("phase_99.system")


def test_sha256_matches_manual_hash():
    p = get_prompt("phase_01.system")
    assert p.sha256 == hashlib.sha256(p.template.encode("utf-8")).hexdigest()


def test_locks_cover_every_prompt():
    assert set(LOCKS) == {p.name for p in all_prompts()}


def test_verify_locks_passes_for_live_registry():
    assert verify_locks() == []


def test_verify_locks_detects_drift(monkeypatch):
    import core.prompts as prompts_mod

    tampered = PromptTemplate("phase_04.system", "1.0.0", "completely different text")
    new_registry = dict(prompts_mod._REGISTRY)
    new_registry["phase_04.system"] = tampered
    monkeypatch.setattr(prompts_mod, "_REGISTRY", new_registry)

    broken = verify_locks()
    assert any("phase_04.system" in b for b in broken)


def test_versions_are_semver_like():
    for p in all_prompts():
        parts = p.version.split(".")
        assert len(parts) == 3 and all(x.isdigit() for x in parts)


def test_templates_mention_json_output_contract():
    # Every phase prompt instructs the model to emit JSON-only — a shared
    # behavioural contract worth pinning.
    for p in all_prompts():
        assert "json" in p.template.lower()


def test_prompt_template_is_frozen():
    p = get_prompt("phase_09.system")
    with pytest.raises(Exception):
        p.version = "2.0.0"  # type: ignore[misc]


def test_conflict_prompt_demands_never_miss_alert():
    # Safety-relevant phrasing worth pinning explicitly for phase_04.
    assert "never miss" in get_prompt("phase_04.system").template.lower()


def test_tfm_prompt_prefers_minimum_intervention():
    assert "minimum intervention" in get_prompt("phase_10.system").template.lower()


def test_emergency_prompt_lists_all_squawk_codes():
    template = get_prompt("phase_09.system").template
    for code in ("7700", "7600", "7500"):
        assert code in template


@pytest.mark.parametrize("prompt_name,module_path", list(AGENT_MODULES.items()))
def test_agent_uses_registry_prompt(prompt_name, module_path):
    module = importlib.import_module(module_path)
    assert module.SYSTEM == get_prompt(prompt_name).template


@pytest.mark.parametrize("prompt_name", list(AGENT_MODULES))
def test_agent_prompt_hash_matches_lock(prompt_name):
    assert get_prompt(prompt_name).sha256 == LOCKS[prompt_name]
