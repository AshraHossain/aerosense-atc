"""Import-invariant guard (AeroOps design §2).

The invariant: `core/` depends on nobody — apps depend on core. That one-way
dependency is what makes "swap the infrastructure, keep the logic" literally true.

As of M0 the graph wiring moved from `core/graph.py` to `aerosense/graph.py`, so
`core/` is now a true leaf and this test enforces the FULL invariant: no module in
`core/` may import any app package. It also checks the allowed direction holds —
`aerosense/graph.py` imports `core` (and the agents it orchestrates)."""

import ast
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CORE = REPO / "core"
FORBIDDEN_ROOTS = {"agents", "aerosense", "aerocommand", "api", "simulation"}


def _imported_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            roots.add(node.module.split(".")[0])
    return roots


def _core_modules() -> list[Path]:
    return sorted(p for p in CORE.glob("*.py"))


def test_no_core_module_imports_an_app_package():
    offenders = {}
    for path in _core_modules():
        leaked = _imported_roots(path) & FORBIDDEN_ROOTS
        if leaked:
            offenders[path.name] = leaked
    assert not offenders, f"core/ modules illegally import app packages: {offenders}"


def test_core_graph_no_longer_lives_in_core():
    # The wiring moved to aerosense/. If this file reappears, the invariant is at
    # risk again — re-run the relocation rather than re-adding it to core.
    assert not (CORE / "graph.py").exists()


def test_core_has_expected_leaf_modules():
    names = {p.name for p in _core_modules()}
    assert {"routing.py", "state.py", "config.py"} <= names


def test_app_graph_depends_on_core_and_agents():
    roots = _imported_roots(REPO / "aerosense" / "graph.py")
    assert "core" in roots, "app graph should import core (the allowed direction)"
    assert "agents" in roots, "app graph wires the agents"


def test_routing_module_stays_pure():
    roots = _imported_roots(CORE / "routing.py")
    assert roots & FORBIDDEN_ROOTS == set()
