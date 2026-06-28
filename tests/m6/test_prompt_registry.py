"""
Tests for APEX CentralPromptRegistry (Phase 1)

Coverage:
  - PromptVersion creation, hashing, integrity
  - CentralPromptRegistry access patterns
  - Sector + phase lookups
  - Registry freezing
  - Hash stability (determinism)
"""

import pytest
import hashlib
from apex.prompt_registry import (
    PromptVersion,
    CentralPromptRegistry,
    build_test_registry,
)


# ── PromptVersion Tests ────────────────────────────────────────────────────────

class TestPromptVersion:
    """PromptVersion immutability and hashing."""

    def test_prompt_version_creation(self):
        """Create a valid PromptVersion."""
        text = "You are a test processor."
        expected_hash = hashlib.sha256(text.encode()).hexdigest()

        pv = PromptVersion(
            name="phase_01_surveillance",
            version="1.0.0",
            text=text,
            sha256_hash=expected_hash,
            metadata={"test": "true"},
        )

        assert pv.name == "phase_01_surveillance"
        assert pv.version == "1.0.0"
        assert pv.text == text
        assert pv.sha256_hash == expected_hash
        assert pv.metadata["test"] == "true"

    def test_prompt_version_hash_mismatch(self):
        """Creating PromptVersion with wrong hash raises ValueError."""
        text = "You are a test processor."
        wrong_hash = "0" * 64

        with pytest.raises(ValueError, match="hash mismatch"):
            PromptVersion(
                name="phase_01_surveillance",
                version="1.0.0",
                text=text,
                sha256_hash=wrong_hash,
                metadata={},
            )

    def test_prompt_version_is_frozen(self):
        """PromptVersion dataclass is frozen (immutable)."""
        pv = PromptVersion(
            name="phase_01_surveillance",
            version="1.0.0",
            text="Test text",
            sha256_hash=hashlib.sha256(b"Test text").hexdigest(),
            metadata={},
        )

        with pytest.raises((AttributeError, TypeError)):
            pv.version = "2.0.0"

    def test_prompt_version_hash_stability(self):
        """Hash is stable across multiple calls."""
        text = "Same text produces same hash."
        hash1 = hashlib.sha256(text.encode()).hexdigest()
        hash2 = hashlib.sha256(text.encode()).hexdigest()

        assert hash1 == hash2

        pv1 = PromptVersion(
            name="phase_01_surveillance",
            version="1.0.0",
            text=text,
            sha256_hash=hash1,
            metadata={},
        )
        pv2 = PromptVersion(
            name="phase_01_surveillance",
            version="1.0.0",
            text=text,
            sha256_hash=hash2,
            metadata={},
        )

        assert pv1.sha256_hash == pv2.sha256_hash

    def test_prompt_version_metadata_dict(self):
        """Metadata can be any dict."""
        pv = PromptVersion(
            name="phase_01_surveillance",
            version="1.0.0",
            text="Test",
            sha256_hash=hashlib.sha256(b"Test").hexdigest(),
            metadata={"author": "Alice", "date": "2026-06-26", "notes": "v1 baseline"},
        )

        assert pv.metadata["author"] == "Alice"
        assert pv.metadata["date"] == "2026-06-26"


# ── CentralPromptRegistry Tests ────────────────────────────────────────────────

class TestCentralPromptRegistry:
    """CentralPromptRegistry read-only contract and access patterns."""

    def test_registry_creation(self):
        """Create an empty registry."""
        registry = build_test_registry()
        assert registry is not None
        assert not registry.is_frozen()

    def test_registry_list_sectors_empty(self):
        """Empty registry has no sectors."""
        registry = build_test_registry()
        assert registry.list_sectors() == []

    def test_registry_freeze(self):
        """Registry can be frozen (read-only mode)."""
        registry = build_test_registry()
        assert not registry.is_frozen()

        registry.freeze()
        assert registry.is_frozen()

    def test_registry_get_nonexistent_sector(self):
        """Getting a non-existent sector raises KeyError."""
        registry = build_test_registry()

        with pytest.raises(KeyError, match="Sector"):
            registry.get("DEN-TOWER", "phase_01_surveillance")

    def test_registry_get_nonexistent_phase(self):
        """Getting a non-existent phase raises KeyError."""
        registry = build_test_registry()

        with pytest.raises(KeyError, match="Sector"):
            registry.get("DEN-TOWER", "phase_01_surveillance")

    def test_registry_with_mock_prompts(self):
        """Registry with mock prompts can be queried."""
        text1 = "Surveillance system text"
        text2 = "Flight plan analyzer text"
        hash1 = hashlib.sha256(text1.encode()).hexdigest()
        hash2 = hashlib.sha256(text2.encode()).hexdigest()

        pv1 = PromptVersion(
            name="phase_01_surveillance",
            version="1.0.0",
            text=text1,
            sha256_hash=hash1,
            metadata={},
        )
        pv2 = PromptVersion(
            name="phase_02_flight_plan",
            version="1.0.0",
            text=text2,
            sha256_hash=hash2,
            metadata={},
        )

        prompts = {
            "DEN-TOWER": {
                "phase_01_surveillance": pv1,
                "phase_02_flight_plan": pv2,
            }
        }
        registry = build_test_registry(prompts)

        # Can retrieve phases
        retrieved = registry.get("DEN-TOWER", "phase_01_surveillance")
        assert retrieved.name == "phase_01_surveillance"
        assert retrieved.version == "1.0.0"
        assert retrieved.text == text1

    def test_registry_list_phases(self):
        """List all phases for a sector."""
        text1 = "Surveillance"
        text2 = "Flight plan"
        hash1 = hashlib.sha256(text1.encode()).hexdigest()
        hash2 = hashlib.sha256(text2.encode()).hexdigest()

        pv1 = PromptVersion(
            name="phase_01_surveillance",
            version="1.0.0",
            text=text1,
            sha256_hash=hash1,
            metadata={},
        )
        pv2 = PromptVersion(
            name="phase_02_flight_plan",
            version="1.0.0",
            text=text2,
            sha256_hash=hash2,
            metadata={},
        )

        registry = build_test_registry(
            {"DEN-TOWER": {"phase_01_surveillance": pv1, "phase_02_flight_plan": pv2}}
        )

        phases = registry.list_phases("DEN-TOWER")
        assert "phase_01_surveillance" in phases
        assert "phase_02_flight_plan" in phases

    def test_registry_get_all_phases(self):
        """Get all phases for a sector."""
        text1 = "Surveillance"
        text2 = "Flight plan"
        hash1 = hashlib.sha256(text1.encode()).hexdigest()
        hash2 = hashlib.sha256(text2.encode()).hexdigest()

        pv1 = PromptVersion(
            name="phase_01_surveillance",
            version="1.0.0",
            text=text1,
            sha256_hash=hash1,
            metadata={},
        )
        pv2 = PromptVersion(
            name="phase_02_flight_plan",
            version="1.0.0",
            text=text2,
            sha256_hash=hash2,
            metadata={},
        )

        registry = build_test_registry(
            {"DEN-TOWER": {"phase_01_surveillance": pv1, "phase_02_flight_plan": pv2}}
        )

        all_phases = registry.get_all_phases("DEN-TOWER")
        assert len(all_phases) == 2
        assert all_phases["phase_01_surveillance"].name == "phase_01_surveillance"
        assert all_phases["phase_02_flight_plan"].name == "phase_02_flight_plan"

    def test_registry_version_for_phase(self):
        """Get version string for a phase."""
        text = "Test prompt"
        hash_val = hashlib.sha256(text.encode()).hexdigest()

        pv = PromptVersion(
            name="phase_01_surveillance",
            version="1.5.2",
            text=text,
            sha256_hash=hash_val,
            metadata={},
        )

        registry = build_test_registry({"DEN-TOWER": {"phase_01_surveillance": pv}})
        version = registry.version_for_phase("DEN-TOWER", "phase_01_surveillance")

        assert version == "1.5.2"

    def test_registry_hash_for_phase(self):
        """Get hash for a phase."""
        text = "Test prompt"
        hash_val = hashlib.sha256(text.encode()).hexdigest()

        pv = PromptVersion(
            name="phase_01_surveillance",
            version="1.0.0",
            text=text,
            sha256_hash=hash_val,
            metadata={},
        )

        registry = build_test_registry({"DEN-TOWER": {"phase_01_surveillance": pv}})
        retrieved_hash = registry.hash_for_phase("DEN-TOWER", "phase_01_surveillance")

        assert retrieved_hash == hash_val

    def test_registry_three_sectors(self):
        """Registry with 3 sectors (DEN-TOWER, DEN-TRACON, DEN-ARTCC)."""
        text = "Universal prompt"
        hash_val = hashlib.sha256(text.encode()).hexdigest()

        pv = PromptVersion(
            name="phase_01_surveillance",
            version="1.0.0",
            text=text,
            sha256_hash=hash_val,
            metadata={"shared": "true"},
        )

        prompts = {
            "DEN-TOWER": {"phase_01_surveillance": pv},
            "DEN-TRACON": {"phase_01_surveillance": pv},
            "DEN-ARTCC": {"phase_01_surveillance": pv},
        }
        registry = build_test_registry(prompts)

        sectors = registry.list_sectors()
        assert len(sectors) == 3
        assert "DEN-TOWER" in sectors
        assert "DEN-TRACON" in sectors
        assert "DEN-ARTCC" in sectors

        # All three can retrieve the same prompt
        for sector_id in ["DEN-TOWER", "DEN-TRACON", "DEN-ARTCC"]:
            pv_retrieved = registry.get(sector_id, "phase_01_surveillance")
            assert pv_retrieved.sha256_hash == hash_val

    def test_registry_repr(self):
        """Registry has readable repr."""
        registry = build_test_registry()
        repr_str = repr(registry)

        assert "CentralPromptRegistry" in repr_str
        assert "frozen=False" in repr_str


# ── Cross-registry determinism tests ───────────────────────────────────────────

class TestRegistryDeterminism:
    """Hash stability and deterministic lookups."""

    def test_same_prompt_same_hash(self):
        """Two PromptVersions with same text have same hash."""
        text = "Identical prompt text"
        pv1 = PromptVersion(
            name="phase_01_surveillance",
            version="1.0.0",
            text=text,
            sha256_hash=hashlib.sha256(text.encode()).hexdigest(),
            metadata={},
        )
        pv2 = PromptVersion(
            name="phase_01_surveillance",
            version="1.0.0",
            text=text,
            sha256_hash=hashlib.sha256(text.encode()).hexdigest(),
            metadata={},
        )

        assert pv1.sha256_hash == pv2.sha256_hash

    def test_different_prompt_different_hash(self):
        """Different text produces different hashes."""
        text1 = "First prompt"
        text2 = "Second prompt"

        pv1 = PromptVersion(
            name="phase_01_surveillance",
            version="1.0.0",
            text=text1,
            sha256_hash=hashlib.sha256(text1.encode()).hexdigest(),
            metadata={},
        )
        pv2 = PromptVersion(
            name="phase_01_surveillance",
            version="1.0.0",
            text=text2,
            sha256_hash=hashlib.sha256(text2.encode()).hexdigest(),
            metadata={},
        )

        assert pv1.sha256_hash != pv2.sha256_hash

    def test_registry_lookup_determinism(self):
        """Multiple lookups of same phase return identical data."""
        text = "Test prompt"
        hash_val = hashlib.sha256(text.encode()).hexdigest()

        pv = PromptVersion(
            name="phase_01_surveillance",
            version="1.0.0",
            text=text,
            sha256_hash=hash_val,
            metadata={},
        )

        registry = build_test_registry({"DEN-TOWER": {"phase_01_surveillance": pv}})

        # Lookup 3 times, should be identical
        lookup1 = registry.get("DEN-TOWER", "phase_01_surveillance")
        lookup2 = registry.get("DEN-TOWER", "phase_01_surveillance")
        lookup3 = registry.get("DEN-TOWER", "phase_01_surveillance")

        assert lookup1.text == lookup2.text == lookup3.text
        assert lookup1.sha256_hash == lookup2.sha256_hash == lookup3.sha256_hash
