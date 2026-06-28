"""ResponderPool — per-airline responder isolation (M5 Phase 2).

Each airline has its own responder instance with its own fleet state. When a flow
directive (GDP) arrives, all subscribed airlines drain the same event independently
and produce their own responses. This achieves per-airline isolation: one airline's
failure or override does not affect federation behavior.

The pool uses a Kafka pub-sub pattern: one DOWN topic (e.g. 'gdp-down') with
multiple subscribers, one per airline. Each subscriber reads, processes independently,
and publishes its UP response to a per-airline topic.
"""

from __future__ import annotations

from typing import Callable
from dataclasses import dataclass, field

from cdm.messages import _CDMBase, CDMDirection
from aerocommand.fleet import FleetFlight
from aerocommand.responder import respond_to_directive


@dataclass
class AirlineResponder:
    """One airline's responder and its fleet state.

    Attributes:
        airline_code: IATA/ICAO airline code (e.g. 'DAL', 'UAL', 'SWA')
        fleet: list of FleetFlight — this airline's flights
        response_callback: optional hook called when responses are generated
    """

    airline_code: str
    fleet: list[FleetFlight] = field(default_factory=list)
    response_callback: Callable[[str, list[_CDMBase]], None] | None = None

    def process_directive(
        self, directive: _CDMBase
    ) -> list[_CDMBase]:
        """Process a single directive with this airline's fleet.

        Returns:
            list of UP responses (CancellationNotice, FlightIntent, etc.)

        Raises:
            ValueError if directive is not DOWN or is unrecognized.
        """
        if directive.direction != CDMDirection.DOWN:
            raise ValueError(
                f"{self.airline_code}: responder only reacts to DOWN directives, "
                f"got {directive.direction}"
            )

        responses = respond_to_directive(
            directive, self.fleet, issuer=self.airline_code
        )

        # Invoke callback if registered, e.g. to publish to Kafka
        if self.response_callback:
            self.response_callback(self.airline_code, responses)

        return responses


@dataclass
class ResponderPool:
    """Pool of per-airline responders.

    When a DOWN directive arrives on a shared event bus (Kafka topic), each airline
    in the pool processes it independently with its own responder and fleet state.

    Attributes:
        responders: dict mapping airline_code -> AirlineResponder
    """

    responders: dict[str, AirlineResponder] = field(default_factory=dict)

    def add_airline(
        self,
        airline_code: str,
        fleet: list[FleetFlight] | None = None,
        response_callback: Callable[[str, list[_CDMBase]], None] | None = None,
    ) -> AirlineResponder:
        """Register a new airline to the pool.

        Args:
            airline_code: unique identifier (e.g. 'DAL')
            fleet: initial list of flights (defaults to empty)
            response_callback: optional hook called with (airline_code, responses)

        Returns:
            the newly created AirlineResponder

        Raises:
            ValueError if airline_code already exists.
        """
        if airline_code in self.responders:
            raise ValueError(f"airline {airline_code} already in pool")

        responder = AirlineResponder(
            airline_code=airline_code,
            fleet=fleet or [],
            response_callback=response_callback,
        )
        self.responders[airline_code] = responder
        return responder

    def remove_airline(self, airline_code: str) -> None:
        """Deregister an airline from the pool.

        Args:
            airline_code: identifier to remove

        Raises:
            KeyError if airline not found.
        """
        del self.responders[airline_code]

    def get_airline(self, airline_code: str) -> AirlineResponder:
        """Retrieve an airline's responder.

        Args:
            airline_code: identifier to look up

        Returns:
            the AirlineResponder

        Raises:
            KeyError if airline not found.
        """
        return self.responders[airline_code]

    def process_directive(self, directive: _CDMBase) -> dict[str, list[_CDMBase]]:
        """Broadcast a DOWN directive to all airlines in the pool.

        Each airline processes the directive independently with its own fleet state.

        Args:
            directive: a DOWN message (GDP, GroundStop, MilesInTrail)

        Returns:
            dict mapping airline_code -> list of UP responses

        Raises:
            ValueError if directive is not DOWN.
        """
        if directive.direction != CDMDirection.DOWN:
            raise ValueError(
                f"pool only accepts DOWN directives, got {directive.direction}"
            )

        results: dict[str, list[_CDMBase]] = {}
        # Process in sorted airline code order for determinism
        for airline_code in sorted(self.responders.keys()):
            responder = self.responders[airline_code]
            responses = responder.process_directive(directive)
            results[airline_code] = responses

        return results

    def airlines(self) -> list[str]:
        """Return sorted list of all airline codes in the pool."""
        return sorted(self.responders.keys())

    def airline_count(self) -> int:
        """Return number of airlines in the pool."""
        return len(self.responders)
