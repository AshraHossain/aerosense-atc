"""Audit — tamper-evident hash-chained decision log (AeroOps M1 governance).

The concrete machinery behind "DO-178C-inspired traceability". Ported from
AutoRedTeam's audit; adapted to AeroSense's in-memory single-node profile.
"""

from core.audit.chain import GENESIS_HASH, AuditChain, AuditEvent, compute_hash

__all__ = ["GENESIS_HASH", "AuditChain", "AuditEvent", "compute_hash"]
