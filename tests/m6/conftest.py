"""
M6 test fixtures and configuration.
"""

import pytest
from apex.prompt_registry import CentralPromptRegistry, PromptVersion, build_test_registry
from apex.eval_coordinator import EvalCoordinator, EvalScenario
from core.state import FlightTrack, Sector


# ── Fixtures: Prompt Registry ──────────────────────────────────────────────────

@pytest.fixture
def empty_registry() -> CentralPromptRegistry:
    """Empty registry for testing."""
    return build_test_registry()


@pytest.fixture
def test_prompt_version() -> PromptVersion:
    """A sample versioned prompt."""
    return PromptVersion(
        name="phase_01_surveillance",
        version="1.0.0",
        text="You are a test surveillance processor.",
        sha256_hash="abc" + "0" * 61,  # Dummy hash, won't verify
        metadata={"test": "true"},
    )


@pytest.fixture
def mock_registry() -> CentralPromptRegistry:
    """Mock registry with test prompts (won't pass hash verification)."""
    # For now, use an empty registry since hash verification is strict
    return build_test_registry()


# ── Fixtures: Eval Coordinator ────────────────────────────────────────────────

@pytest.fixture
def eval_coordinator() -> EvalCoordinator:
    """A fresh EvalCoordinator."""
    return EvalCoordinator()


@pytest.fixture
def nominal_scenario() -> EvalScenario:
    """Nominal scenario fixture."""
    return EvalScenario.nominal()


@pytest.fixture
def conflict_scenario() -> EvalScenario:
    """Conflict scenario fixture."""
    return EvalScenario.conflict()


@pytest.fixture
def emergency_scenario() -> EvalScenario:
    """Emergency scenario fixture."""
    return EvalScenario.emergency()


# ── Fixtures: Sector definitions ───────────────────────────────────────────────

@pytest.fixture
def sector_high() -> Sector:
    """High-altitude sector."""
    return {
        "sector_id": "HIGH",
        "name": "High Altitude En-Route",
        "alt_low_ft": 18000,
        "alt_high_ft": 45000,
        "traffic_count": 5,
        "load_pct": 50.0,
        "controller": "CTR-HIGH",
    }


@pytest.fixture
def sector_approach() -> Sector:
    """Approach control sector."""
    return {
        "sector_id": "APCH",
        "name": "Approach Control",
        "alt_low_ft": 0,
        "alt_high_ft": 10000,
        "traffic_count": 8,
        "load_pct": 100.0,
        "controller": "APP-CTL",
    }


# ── Fixtures: Flight tracks ────────────────────────────────────────────────────

@pytest.fixture
def track_aal123() -> FlightTrack:
    """Sample aircraft track (AAL123)."""
    return {
        "callsign": "AAL123",
        "squawk": "1234",
        "position": {"lat": 39.861389, "lon": -104.673056, "alt_ft": 35000},
        "heading_deg": 90,
        "speed_kts": 450,
        "vertical_rate_fpm": 0,
        "track_quality": 1.0,
        "data_sources": ["adsb"],
    }


@pytest.fixture
def track_dal456() -> FlightTrack:
    """Sample aircraft track (DAL456)."""
    return {
        "callsign": "DAL456",
        "squawk": "2456",
        "position": {"lat": 39.861389, "lon": -104.5, "alt_ft": 25000},
        "heading_deg": 90,
        "speed_kts": 400,
        "vertical_rate_fpm": 0,
        "track_quality": 1.0,
        "data_sources": ["adsb"],
    }
