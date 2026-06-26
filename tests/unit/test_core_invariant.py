"""Import-invariant guard (AeroOps design §2).

Target invariant: `core/` depends on nobody — apps depend on core. That's what
makes "swap the infrastructure, keep the logic" literally true. The full invariant
isn't met yet: `core/graph.py` still imports the 12 agents (it wires them), and
relocating that wiring into the app package is a later M0/M1 step. So this test
locks the *leaf* modules that ARE already clean (routing/state/config) and records
graph.py as the single known, documented exception — a tripwire that fails if a new
app dependency creeps into a clean module."""

import ast
from pathlib import Path

CORE = Path(__file__).resolve().parents[2] / "core"
FORBIDDEN_ROOTS = {"agents", "aerosense", "aerocommand", "api", "simulation"}

# Modules proven not to import any app package. graph.py is intentionally absent —
# it imports agents today and is the known pending extraction.
CLEAN_LEAF_MODULES = ["routing.py", "state.py", "config.py"]


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


def test_clean_leaf_modules_do_not_import_app_packages():
    for name in CLEAN_LEAF_MODULES:
        roots = _imported_roots(CORE / name)
        leaked = roots & FORBIDDEN_ROOTS
        assert not leaked, f"core/{name} illegally imports app package(s): {leaked}"


def test_routing_only_depends_on_state_and_langgraph():
    roots = _imported_roots(CORE / "routing.py")
    # routing may import core.state and langgraph; nothing app-level.
    assert roots & FORBIDDEN_ROOTS == set()


def test_graph_is_the_known_documented_exception():
    # If graph.py ever STOPS importing agents (i.e. the extraction happened),
    # this test should be updated to fold graph.py into the clean set.
    roots = _imported_roots(CORE / "graph.py")
    assert "agents" in roots, (
        "core/graph.py no longer imports agents — the app extraction may be done; "
        "promote graph.py into CLEAN_LEAF_MODULES and tighten the invariant."
    )


def test_clean_leaf_modules_exist():
    for name in CLEAN_LEAF_MODULES:
        assert (CORE / name).exists()
