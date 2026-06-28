"""
APEX ATC Platform — Multi-Sector Orchestration & Federated Evaluation (M6)

A federated ATC system where three independent sectors (DEN-TOWER, DEN-TRACON, DEN-ARTCC)
coordinate around a centralized prompt registry, conduct federated evaluations, and resolve
cross-sector conflicts with deterministic arbitration.

Modules:
  - prompt_registry: CentralPromptRegistry (read-only, versioned)
  - eval_coordinator: EvalCoordinator (baseline scenarios, aggregation)
  - sector_manager: SectorManager (lifecycle, health monitoring)
  - federation_bus: FederationBus (pub-sub event routing)
  - crossing_detector: CrossingSector detection (pure Python)
  - handoff_arbitrator: Deterministic conflict arbitration
  - eval_harness: Federated eval orchestration
  - apex_system: Top-level ApexATCSystem orchestrator
"""

__version__ = "3.0.0-apex-atc"
__author__ = "AeroSense Team"

# Phase 1 modules (available now)
from apex.prompt_registry import CentralPromptRegistry, PromptVersion
from apex.eval_coordinator import EvalCoordinator, EvalScenario

# Phase 2+ modules imported lazily to avoid import-time errors
# (they will be available after their phase implementation)

__all__ = [
    "CentralPromptRegistry",
    "PromptVersion",
    "EvalCoordinator",
    "EvalScenario",
]
