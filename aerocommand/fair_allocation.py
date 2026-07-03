"""FairAllocation — percentage-based capacity fairness (M5 Phase 4).

When a GDP overflows (more flights want to land than capacity allows), distribute
slots fairly across N airlines based on percentage allocation rules. No airline gets
monopoly on the available slots; each airline's "share" is proportional to its current
load or a pre-assigned percentage.

Two allocation strategies:
  1. Equal split: each airline gets capacity / N slots
  2. Proportional: each airline's share = (its arrivals / total arrivals) * capacity
  3. Preset percentages: each airline has a pre-assigned percentage quota

The allocator is deterministic: tie-breaks by airline code alphabetical order.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from aerocommand.fleet import FleetFlight


@dataclass
class AllocationQuota:
    """One airline's capacity quota at an airport.

    Attributes:
        airline_code: the airline identifier
        allocated_slots: number of slots assigned to this airline
        current_arrivals: number of this airline's arrivals currently at the airport
        overflow: how many flights this airline must cancel/delay
    """

    airline_code: str
    allocated_slots: int
    current_arrivals: int
    overflow: int = 0

    def __post_init__(self):
        """Compute overflow: current arrivals exceeding allocated slots."""
        self.overflow = max(0, self.current_arrivals - self.allocated_slots)


@dataclass
class AllocationPlan:
    """The result of fair allocation at one airport for one GDP.

    Attributes:
        element: airport code (e.g. 'KDEN')
        total_capacity: total slots available
        total_arrivals: total flights arriving across all airlines
        strategy: allocation strategy used
        quotas: dict mapping airline_code -> AllocationQuota
        total_allocated: sum of all slots allocated
        total_overflow: sum of all overflows
    """

    element: str
    total_capacity: int
    total_arrivals: int
    strategy: str
    quotas: dict[str, AllocationQuota] = field(default_factory=dict)

    @property
    def total_allocated(self) -> int:
        """Sum of all allocated slots."""
        return sum(q.allocated_slots for q in self.quotas.values())

    @property
    def total_overflow(self) -> int:
        """Sum of all overflows across airlines."""
        return sum(q.overflow for q in self.quotas.values())


class FairAllocator:
    """Distribute GDP capacity fairly across multiple airlines.

    Supports three strategies:
      - 'equal': equal split (capacity / N)
      - 'proportional': by current load (airline_arrivals / total_arrivals * capacity)
      - 'preset': by pre-assigned percentages

    All strategies apply deterministic tie-breaks (airline code alphabetical).
    """

    def __init__(
        self,
        percentages: dict[str, float] | None = None,
    ):
        """Initialize the allocator.

        Args:
            percentages: optional dict mapping airline_code -> percentage (0-100).
                Used only in 'preset' strategy.
        """
        self.percentages = percentages or {}

    def allocate_equal(
        self, element: str, capacity: int, airlines: dict[str, list[FleetFlight]]
    ) -> AllocationPlan:
        """Allocate capacity equally across all airlines.

        Args:
            element: airport code
            capacity: total available slots
            airlines: dict mapping airline_code -> list of FleetFlight

        Returns:
            AllocationPlan with equal quotas
        """
        airline_codes = sorted(airlines.keys())
        num_airlines = len(airline_codes)

        if num_airlines == 0:
            return AllocationPlan(
                element=element,
                total_capacity=capacity,
                total_arrivals=0,
                strategy="equal",
                quotas={},
            )

        slots_per_airline = capacity // num_airlines
        quotas: dict[str, AllocationQuota] = {}

        for code in airline_codes:
            arrivals = len(
                [f for f in airlines[code] if f.destination == element]
            )
            quota = AllocationQuota(
                airline_code=code,
                allocated_slots=slots_per_airline,
                current_arrivals=arrivals,
            )
            quotas[code] = quota

        total_arrivals = sum(q.current_arrivals for q in quotas.values())
        return AllocationPlan(
            element=element,
            total_capacity=capacity,
            total_arrivals=total_arrivals,
            strategy="equal",
            quotas=quotas,
        )

    def allocate_proportional(
        self, element: str, capacity: int, airlines: dict[str, list[FleetFlight]]
    ) -> AllocationPlan:
        """Allocate capacity proportional to each airline's current load.

        Each airline gets: (its_arrivals / total_arrivals) * capacity slots.

        Args:
            element: airport code
            capacity: total available slots
            airlines: dict mapping airline_code -> list of FleetFlight

        Returns:
            AllocationPlan with proportional quotas
        """
        airline_codes = sorted(airlines.keys())
        quotas: dict[str, AllocationQuota] = {}

        # Count arrivals per airline
        arrivals_by_code: dict[str, int] = {}
        for code in airline_codes:
            arrivals_by_code[code] = len(
                [f for f in airlines[code] if f.destination == element]
            )

        total_arrivals = sum(arrivals_by_code.values())

        if total_arrivals == 0:
            # No arrivals; allocate nothing
            for code in airline_codes:
                quotas[code] = AllocationQuota(
                    airline_code=code,
                    allocated_slots=0,
                    current_arrivals=0,
                )
        else:
            # Allocate proportionally
            for code in airline_codes:
                proportion = arrivals_by_code[code] / total_arrivals
                slots = int(proportion * capacity)
                quota = AllocationQuota(
                    airline_code=code,
                    allocated_slots=slots,
                    current_arrivals=arrivals_by_code[code],
                )
                quotas[code] = quota

        return AllocationPlan(
            element=element,
            total_capacity=capacity,
            total_arrivals=total_arrivals,
            strategy="proportional",
            quotas=quotas,
        )

    def allocate_preset(
        self, element: str, capacity: int, airlines: dict[str, list[FleetFlight]]
    ) -> AllocationPlan:
        """Allocate capacity using preset percentages.

        Each airline's slot count = (its percentage / 100) * capacity.

        Args:
            element: airport code
            capacity: total available slots
            airlines: dict mapping airline_code -> list of FleetFlight

        Returns:
            AllocationPlan with preset quotas

        Raises:
            ValueError if percentages don't sum to ~100 or are missing airlines.
        """
        airline_codes = sorted(airlines.keys())

        # Validate percentages
        if not all(code in self.percentages for code in airline_codes):
            missing = [c for c in airline_codes if c not in self.percentages]
            raise ValueError(f"missing percentages for airlines: {missing}")

        total_pct = sum(self.percentages[code] for code in airline_codes)
        if not (99 <= total_pct <= 101):  # allow ±1 rounding
            raise ValueError(f"percentages sum to {total_pct}%, must be ~100%")

        quotas: dict[str, AllocationQuota] = {}
        for code in airline_codes:
            pct = self.percentages[code]
            slots = int((pct / 100.0) * capacity)
            arrivals = len(
                [f for f in airlines[code] if f.destination == element]
            )
            quota = AllocationQuota(
                airline_code=code,
                allocated_slots=slots,
                current_arrivals=arrivals,
            )
            quotas[code] = quota

        total_arrivals = sum(q.current_arrivals for q in quotas.values())
        return AllocationPlan(
            element=element,
            total_capacity=capacity,
            total_arrivals=total_arrivals,
            strategy="preset",
            quotas=quotas,
        )

    def allocate(
        self,
        element: str,
        capacity: int,
        airlines: dict[str, list[FleetFlight]],
        strategy: Literal["equal", "proportional", "preset"] = "equal",
    ) -> AllocationPlan:
        """Allocate capacity using the specified strategy.

        Args:
            element: airport code
            capacity: total available slots
            airlines: dict mapping airline_code -> list of FleetFlight
            strategy: 'equal', 'proportional', or 'preset'

        Returns:
            AllocationPlan

        Raises:
            ValueError if strategy is unknown or preset is missing percentages.
        """
        if strategy == "equal":
            return self.allocate_equal(element, capacity, airlines)
        elif strategy == "proportional":
            return self.allocate_proportional(element, capacity, airlines)
        elif strategy == "preset":
            return self.allocate_preset(element, capacity, airlines)
        else:
            raise ValueError(f"unknown strategy: {strategy}")
