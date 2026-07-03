"""FairAllocation tests — percentage-based fairness (M5 Phase 4). No LLM."""

from datetime import datetime, timedelta, timezone

import pytest

from aerocommand.fleet import FleetFlight
from aerocommand.fair_allocation import FairAllocator, AllocationQuota, AllocationPlan

T0 = datetime(2026, 6, 26, 12, 0, tzinfo=timezone.utc)


def flight(fid, dest="KDEN", arr_min=0):
    return FleetFlight(
        flight_id=fid,
        origin="KSFO",
        destination=dest,
        scheduled_arrival=T0 + timedelta(minutes=arr_min),
        priority=0,
        cancellable=True,
        route_fixes=[],
    )


# ── AllocationQuota ────────────────────────────────────────────────────────


def test_allocation_quota_creation():
    quota = AllocationQuota(airline_code="DAL", allocated_slots=4, current_arrivals=5)
    assert quota.airline_code == "DAL"
    assert quota.allocated_slots == 4
    assert quota.current_arrivals == 5
    assert quota.overflow == 1  # 5 - 4


def test_allocation_quota_no_overflow():
    quota = AllocationQuota(airline_code="UAL", allocated_slots=5, current_arrivals=3)
    assert quota.overflow == 0


def test_allocation_quota_zero_overflow():
    quota = AllocationQuota(airline_code="SWA", allocated_slots=3, current_arrivals=3)
    assert quota.overflow == 0


# ── FairAllocator: Equal Strategy ──────────────────────────────────────────


def test_allocator_equal_two_airlines():
    """Equal split: 10 slots / 2 airlines = 5 each."""
    allocator = FairAllocator()
    airlines = {
        "DAL": [flight("DAL_1", dest="KDEN"), flight("DAL_2", dest="KDEN"), flight("DAL_3", dest="KDEN")],
        "UAL": [flight("UAL_1", dest="KDEN"), flight("UAL_2", dest="KDEN"), flight("UAL_3", dest="KDEN")],
    }

    plan = allocator.allocate("KDEN", capacity=10, airlines=airlines, strategy="equal")

    assert plan.element == "KDEN"
    assert plan.total_capacity == 10
    assert plan.strategy == "equal"
    assert plan.quotas["DAL"].allocated_slots == 5
    assert plan.quotas["UAL"].allocated_slots == 5
    assert plan.total_allocated == 10
    assert plan.total_overflow == 0  # both fit their quotas


def test_allocator_equal_three_airlines():
    """Equal split: 9 slots / 3 airlines = 3 each."""
    allocator = FairAllocator()
    airlines = {
        "DAL": [flight(f"DAL_{i}", dest="KDEN") for i in range(4)],
        "UAL": [flight(f"UAL_{i}", dest="KDEN") for i in range(4)],
        "SWA": [flight(f"SWA_{i}", dest="KDEN") for i in range(4)],
    }

    plan = allocator.allocate("KDEN", capacity=9, airlines=airlines, strategy="equal")

    assert plan.quotas["DAL"].allocated_slots == 3
    assert plan.quotas["UAL"].allocated_slots == 3
    assert plan.quotas["SWA"].allocated_slots == 3
    assert plan.total_allocated == 9
    assert plan.total_overflow == 3  # each airline has 4, fits only 3


def test_allocator_equal_uneven_airlines():
    """Uneven distribution: 10 slots / 3 airlines = 3 each (1 slot left over)."""
    allocator = FairAllocator()
    airlines = {
        "DAL": [flight(f"DAL_{i}", dest="KDEN") for i in range(5)],
        "UAL": [flight(f"UAL_{i}", dest="KDEN") for i in range(5)],
        "SWA": [flight(f"SWA_{i}", dest="KDEN") for i in range(5)],
    }

    plan = allocator.allocate("KDEN", capacity=10, airlines=airlines, strategy="equal")

    # 10 // 3 = 3 per airline, 1 slot remains
    assert plan.quotas["DAL"].allocated_slots == 3
    assert plan.quotas["UAL"].allocated_slots == 3
    assert plan.quotas["SWA"].allocated_slots == 3
    assert plan.total_allocated == 9


def test_allocator_equal_no_airlines():
    """Empty airline dict produces empty allocation plan."""
    allocator = FairAllocator()
    plan = allocator.allocate("KDEN", capacity=10, airlines={}, strategy="equal")

    assert plan.quotas == {}
    assert plan.total_allocated == 0
    assert plan.total_overflow == 0


# ── FairAllocator: Proportional Strategy ───────────────────────────────────


def test_allocator_proportional_equal_load():
    """Proportional split with equal load: each gets 50% * 10 = 5."""
    allocator = FairAllocator()
    airlines = {
        "DAL": [flight(f"DAL_{i}", dest="KDEN") for i in range(5)],
        "UAL": [flight(f"UAL_{i}", dest="KDEN") for i in range(5)],
    }

    plan = allocator.allocate("KDEN", capacity=10, airlines=airlines, strategy="proportional")

    assert plan.strategy == "proportional"
    assert plan.quotas["DAL"].allocated_slots == 5
    assert plan.quotas["UAL"].allocated_slots == 5
    assert plan.total_allocated == 10


def test_allocator_proportional_unequal_load():
    """Proportional with unequal load: DAL 70%, UAL 30%."""
    allocator = FairAllocator()
    airlines = {
        "DAL": [flight(f"DAL_{i}", dest="KDEN") for i in range(7)],
        "UAL": [flight(f"UAL_{i}", dest="KDEN") for i in range(3)],
    }

    plan = allocator.allocate("KDEN", capacity=10, airlines=airlines, strategy="proportional")

    # DAL: 7/10 * 10 = 7, UAL: 3/10 * 10 = 3
    assert plan.quotas["DAL"].allocated_slots == 7
    assert plan.quotas["UAL"].allocated_slots == 3


def test_allocator_proportional_zero_arrivals():
    """No arrivals at this airport: zero slots allocated."""
    allocator = FairAllocator()
    airlines = {
        "DAL": [flight(f"DAL_{i}", dest="KORD") for i in range(5)],  # different airport
        "UAL": [flight(f"UAL_{i}", dest="KORD") for i in range(5)],  # different airport
    }

    plan = allocator.allocate("KDEN", capacity=10, airlines=airlines, strategy="proportional")

    assert plan.total_arrivals == 0
    assert plan.quotas["DAL"].allocated_slots == 0
    assert plan.quotas["UAL"].allocated_slots == 0


def test_allocator_proportional_single_airline():
    """Single airline gets 100% of capacity."""
    allocator = FairAllocator()
    airlines = {
        "DAL": [flight(f"DAL_{i}", dest="KDEN") for i in range(10)],
    }

    plan = allocator.allocate("KDEN", capacity=10, airlines=airlines, strategy="proportional")

    assert plan.quotas["DAL"].allocated_slots == 10


def test_allocator_proportional_mixed_destinations():
    """Count only arrivals at the target airport."""
    allocator = FairAllocator()
    airlines = {
        "DAL": [
            flight("DAL_1", dest="KDEN"),
            flight("DAL_2", dest="KDEN"),
            flight("DAL_3", dest="KORD"),  # different destination, not counted
        ],
        "UAL": [
            flight("UAL_1", dest="KDEN"),
            flight("UAL_2", dest="KDEN"),
            flight("UAL_3", dest="KDEN"),
        ],
    }

    plan = allocator.allocate("KDEN", capacity=10, airlines=airlines, strategy="proportional")

    # At KDEN: DAL 2/5, UAL 3/5
    # DAL: 2/5 * 10 = 4, UAL: 3/5 * 10 = 6
    assert plan.quotas["DAL"].allocated_slots == 4
    assert plan.quotas["UAL"].allocated_slots == 6
    assert plan.total_arrivals == 5  # only KDEN arrivals


# ── FairAllocator: Preset Strategy ─────────────────────────────────────────


def test_allocator_preset_50_50_split():
    """Preset 50/50 split."""
    allocator = FairAllocator(percentages={"DAL": 50, "UAL": 50})
    airlines = {
        "DAL": [flight(f"DAL_{i}", dest="KDEN") for i in range(10)],
        "UAL": [flight(f"UAL_{i}", dest="KDEN") for i in range(10)],
    }

    plan = allocator.allocate("KDEN", capacity=10, airlines=airlines, strategy="preset")

    assert plan.strategy == "preset"
    assert plan.quotas["DAL"].allocated_slots == 5
    assert plan.quotas["UAL"].allocated_slots == 5


def test_allocator_preset_custom_percentages():
    """Preset 70/20/10 split."""
    allocator = FairAllocator(percentages={"DAL": 70, "UAL": 20, "SWA": 10})
    airlines = {
        "DAL": [flight(f"DAL_{i}", dest="KDEN") for i in range(10)],
        "UAL": [flight(f"UAL_{i}", dest="KDEN") for i in range(10)],
        "SWA": [flight(f"SWA_{i}", dest="KDEN") for i in range(10)],
    }

    plan = allocator.allocate("KDEN", capacity=100, airlines=airlines, strategy="preset")

    assert plan.quotas["DAL"].allocated_slots == 70
    assert plan.quotas["UAL"].allocated_slots == 20
    assert plan.quotas["SWA"].allocated_slots == 10


def test_allocator_preset_missing_airline_raises():
    """Raise error if percentages missing an airline."""
    allocator = FairAllocator(percentages={"DAL": 50, "UAL": 50})  # missing SWA
    airlines = {
        "DAL": [flight("DAL_1", dest="KDEN")],
        "UAL": [flight("UAL_1", dest="KDEN")],
        "SWA": [flight("SWA_1", dest="KDEN")],
    }

    with pytest.raises(ValueError):
        allocator.allocate("KDEN", capacity=10, airlines=airlines, strategy="preset")


def test_allocator_preset_percentages_not_100_raises():
    """Raise error if percentages don't sum to ~100%."""
    allocator = FairAllocator(percentages={"DAL": 50, "UAL": 40})  # only 90%
    airlines = {
        "DAL": [flight("DAL_1", dest="KDEN")],
        "UAL": [flight("UAL_1", dest="KDEN")],
    }

    with pytest.raises(ValueError):
        allocator.allocate("KDEN", capacity=10, airlines=airlines, strategy="preset")


def test_allocator_preset_100_percent_accepted():
    """100% exactly is accepted."""
    allocator = FairAllocator(percentages={"DAL": 50, "UAL": 50})
    airlines = {
        "DAL": [flight("DAL_1", dest="KDEN")],
        "UAL": [flight("UAL_1", dest="KDEN")],
    }

    plan = allocator.allocate("KDEN", capacity=10, airlines=airlines, strategy="preset")
    assert plan.quotas["DAL"].allocated_slots == 5


# ── FairAllocator: Generic allocate() ──────────────────────────────────────


def test_allocate_routes_to_equal():
    """allocate() with strategy='equal' routes to equal strategy."""
    allocator = FairAllocator()
    airlines = {"DAL": [flight("DAL_1", dest="KDEN")], "UAL": [flight("UAL_1", dest="KDEN")]}

    plan = allocator.allocate("KDEN", capacity=10, airlines=airlines, strategy="equal")
    assert plan.strategy == "equal"


def test_allocate_routes_to_proportional():
    """allocate() with strategy='proportional' routes to proportional strategy."""
    allocator = FairAllocator()
    airlines = {"DAL": [flight("DAL_1", dest="KDEN")], "UAL": [flight("UAL_1", dest="KDEN")]}

    plan = allocator.allocate("KDEN", capacity=10, airlines=airlines, strategy="proportional")
    assert plan.strategy == "proportional"


def test_allocate_routes_to_preset():
    """allocate() with strategy='preset' routes to preset strategy."""
    allocator = FairAllocator(percentages={"DAL": 50, "UAL": 50})
    airlines = {"DAL": [flight("DAL_1", dest="KDEN")], "UAL": [flight("UAL_1", dest="KDEN")]}

    plan = allocator.allocate("KDEN", capacity=10, airlines=airlines, strategy="preset")
    assert plan.strategy == "preset"


def test_allocate_unknown_strategy_raises():
    """Unknown strategy raises ValueError."""
    allocator = FairAllocator()
    airlines = {"DAL": [flight("DAL_1", dest="KDEN")]}

    with pytest.raises(ValueError):
        allocator.allocate("KDEN", capacity=10, airlines=airlines, strategy="unknown")


def test_allocation_plan_properties():
    """AllocationPlan properties compute correctly."""
    quota1 = AllocationQuota(airline_code="DAL", allocated_slots=5, current_arrivals=6)
    quota2 = AllocationQuota(airline_code="UAL", allocated_slots=5, current_arrivals=4)

    plan = AllocationPlan(
        element="KDEN",
        total_capacity=10,
        total_arrivals=10,
        strategy="equal",
        quotas={"DAL": quota1, "UAL": quota2},
    )

    assert plan.total_allocated == 10  # 5 + 5
    assert plan.total_overflow == 1  # 1 from DAL + 0 from UAL
