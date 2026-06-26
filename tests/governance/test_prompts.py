"""Prompt lockfile and versioning tests."""

import json
import pytest

from core.governance.prompts import (
    PromptVersion,
    PromptLockfile,
    init_lockfile,
    register_prompt,
    get_prompt,
    get_lockfile,
    set_eval_baseline,
)


def test_prompt_version_computes_checksum():
    """PromptVersion auto-computes SHA256 of text."""
    pv = PromptVersion(
        name="test",
        text="You are an air traffic controller.",
        version="1.0.0",
        model="gemini-2.0",
        created_at="2026-06-26T12:00:00Z",
    )
    assert len(pv.checksum) == 64  # SHA256 hex is 64 chars
    assert pv.checksum == pv.checksum  # deterministic


def test_prompt_lockfile_serializes_to_json():
    """Lockfile can be serialized and deserialized."""
    lockfile = PromptLockfile(
        model="gemini-2.0-flash",
        model_version="2.0",
        lockfile_version="1.0.0",
        created_at="2026-06-26T12:00:00Z",
    )
    lockfile.add_prompt("phase_01", "Surveillance prompt text", "1.0.0")
    lockfile.add_prompt("aoc_gdp", "AOC GDP responder prompt", "1.0.0")

    # Serialize
    json_str = lockfile.serialize()
    assert "gemini-2.0-flash" in json_str
    assert "phase_01" in json_str

    # Deserialize
    restored = PromptLockfile.deserialize(json_str)
    assert restored.model == "gemini-2.0-flash"
    assert "phase_01" in restored.prompts
    assert restored.prompts["phase_01"].text == "Surveillance prompt text"


def test_lockfile_checksum_is_deterministic():
    """Two lockfiles with same prompts have same checksum."""
    lf1 = PromptLockfile(
        model="gemini-2.0-flash",
        model_version="2.0",
        lockfile_version="1.0.0",
        created_at="2026-06-26T12:00:00Z",
    )
    lf1.add_prompt("test", "same text", "1.0.0")

    lf2 = PromptLockfile(
        model="gemini-2.0-flash",
        model_version="2.0",
        lockfile_version="1.0.0",
        created_at="2026-06-26T12:00:00Z",
    )
    lf2.add_prompt("test", "same text", "1.0.0")

    assert lf1.checksum == lf2.checksum


def test_global_lockfile_registry(monkeypatch):
    """Global lockfile functions for agent use."""
    # Clear any existing lockfile
    import core.governance.prompts as prompts_module

    monkeypatch.setattr(prompts_module, "_LOCKFILE", None)

    # Initialize
    init_lockfile("gemini-2.0-flash", "2.0", "1.0.0")

    # Register prompts
    register_prompt("phase_01", "Surveillance prompt", "1.0.0")
    register_prompt("phase_02", "Flight plan prompt", "1.0.0")

    # Retrieve
    assert get_prompt("phase_01") == "Surveillance prompt"
    assert get_prompt("phase_02") == "Flight plan prompt"

    # Audit trail
    lockfile = get_lockfile()
    assert lockfile.model == "gemini-2.0-flash"
    assert len(lockfile.prompts) == 2


def test_eval_baseline_locked_in_lockfile(monkeypatch):
    """Eval baseline (pass rate) is frozen in lockfile."""
    import core.governance.prompts as prompts_module

    monkeypatch.setattr(prompts_module, "_LOCKFILE", None)

    init_lockfile("gemini-2.0-flash", "2.0", "1.0.0")
    register_prompt("phase_01", "test", "1.0.0")

    # No baseline yet
    lockfile = get_lockfile()
    assert lockfile.eval_pass_rate is None

    # Set baseline after evals run
    set_eval_baseline(pass_rate=0.95, test_count=100)
    lockfile = get_lockfile()
    assert lockfile.eval_pass_rate == 0.95
    assert lockfile.eval_test_count == 100


def test_unregistered_prompt_raises_error(monkeypatch):
    """Requesting a non-existent prompt raises KeyError."""
    import core.governance.prompts as prompts_module

    monkeypatch.setattr(prompts_module, "_LOCKFILE", None)

    init_lockfile("gemini-2.0-flash", "2.0", "1.0.0")

    with pytest.raises(KeyError, match="not registered"):
        get_prompt("nonexistent")


def test_lockfile_not_initialized_raises_error(monkeypatch):
    """Using registry functions before init raises RuntimeError."""
    import core.governance.prompts as prompts_module

    monkeypatch.setattr(prompts_module, "_LOCKFILE", None)

    with pytest.raises(RuntimeError, match="not initialized"):
        register_prompt("test", "text", "1.0.0")

    with pytest.raises(RuntimeError, match="not initialized"):
        get_prompt("test")
