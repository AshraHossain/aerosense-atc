"""AeroOps CDM seam — Collaborative Decision Making messages between AeroSense
(ATC / FAA side) and AeroCommand (airline AOC side).

This package models the real FAA<->airline CDM protocol (run over TFMS):
  - DOWN (flow authority, ATC -> AOC): Ground Delay Program, Ground Stop,
    Miles-in-Trail.
  - UP (collaboration, AOC -> ATC): Substitution Request, Flight Intent,
    Cancellation Notice.

`cdm/` is a deliberate LEAF: it imports only stdlib + Pydantic, never `core/` or
either app. The seam is a trust boundary, so messages are validated Pydantic
models (not the bare TypedDicts used for in-process ATCState). Translation from
ATC-internal TFM programs to wire messages lives in `cdm.seam` and takes plain
dicts, so this package stays decoupled from the evolving `core/` structure.
"""

from cdm.messages import (
    CDMDirection,
    CDMMessageType,
    GroundDelayProgram,
    GroundStop,
    MilesInTrail,
    SubstitutionRequest,
    SlotSwap,
    FlightIntent,
    CancellationNotice,
    DOWN_MESSAGE_TYPES,
    UP_MESSAGE_TYPES,
)
from cdm.transport import InMemoryCDMTransport
from cdm.seam import tfm_to_cdm

__all__ = [
    "CDMDirection",
    "CDMMessageType",
    "GroundDelayProgram",
    "GroundStop",
    "MilesInTrail",
    "SubstitutionRequest",
    "SlotSwap",
    "FlightIntent",
    "CancellationNotice",
    "DOWN_MESSAGE_TYPES",
    "UP_MESSAGE_TYPES",
    "InMemoryCDMTransport",
    "tfm_to_cdm",
]
