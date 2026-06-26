"""Safety-constant tests. core/config.py holds the ICAO/FAA separation minima and
sector definitions that the whole system treats as ground truth. A typo here is a
safety bug, so the constants are pinned to their regulatory values."""

from core import config


def test_horizontal_separation_is_5nm():
    # ICAO Doc 4444 / FAA 7110.65 radar separation minimum.
    assert config.MIN_HORIZONTAL_SEP_NM == 5.0


def test_vertical_separation_standard_is_1000ft():
    assert config.MIN_VERTICAL_SEP_FT == 1000


def test_vertical_separation_high_is_2000ft():
    assert config.MIN_VERTICAL_SEP_HI == 2000


def test_conflict_lookahead_is_15min():
    assert config.CONFLICT_LOOKAHEAD_MIN == 15


def test_sector_overload_threshold_is_85pct():
    assert config.SECTOR_OVERLOAD_PCT == 85


def test_agent_temperature_is_low_for_determinism():
    assert config.AGENT_TEMPERATURE <= 0.2


def test_model_is_gemini_flash():
    assert config.MODEL_NAME == "gemini-2.0-flash"


def test_four_sectors_defined():
    assert set(config.SECTORS) == {"EAST", "WEST", "HIGH", "APCH"}


def test_each_sector_has_required_fields():
    for sid, sector in config.SECTORS.items():
        for field in ("name", "alt_low_ft", "alt_high_ft", "controller", "capacity"):
            assert field in sector, f"{sid} missing {field}"


def test_sector_altitude_bands_are_ordered():
    for sid, sector in config.SECTORS.items():
        assert sector["alt_low_ft"] < sector["alt_high_ft"], f"{sid} band inverted"


def test_high_sector_has_largest_capacity():
    caps = {sid: s["capacity"] for sid, s in config.SECTORS.items()}
    assert caps["HIGH"] == max(caps.values())


def test_frequencies_cover_all_sectors():
    for sid in config.SECTORS:
        assert sid in config.FREQUENCIES, f"no frequency for sector {sid}"


def test_guard_frequency_is_121_5():
    # 121.5 MHz is the international aeronautical emergency (guard) frequency.
    assert config.FREQUENCIES["GUARD"] == "121.500"


def test_do178c_constraints_present():
    assert len(config.DO178C_CONSTRAINTS) >= 8
    joined = " ".join(config.DO178C_CONSTRAINTS)
    assert "SEP-001" in joined and "EMG-001" in joined
