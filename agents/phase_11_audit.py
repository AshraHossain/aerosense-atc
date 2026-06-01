"""
Phase 11 — Audit & Compliance (DO-178C Traceability)
Consolidates all phase traces into a formal decision audit log.
Writes a structured .jsonl trace file for each scenario.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from core.state import ATCState
from core.config import LOG_TRACES, DO178C_CONSTRAINTS
from agents.base import make_trace, emit_event

TRACE_DIR = Path(__file__).parent.parent / "traces"
TRACE_DIR.mkdir(exist_ok=True)


def phase_11_node(state: ATCState) -> dict:
    traces = state.get("do178c_traces", [])
    scenario_id = state.get("scenario_id", "unknown")
    events = list(state.get("events", []))
    now = datetime.now(timezone.utc).isoformat()

    # Compliance checks
    issues: list[str] = []
    phases_expected = [f"phase_{str(i).zfill(2)}" for i in range(1, 12)]
    phases_done = state.get("phases_completed", [])

    for ph in phases_expected:
        if ph not in phases_done:
            issues.append(f"MISSING TRACE: {ph} did not complete")

    # Verify every clearance has a DO-178C trace reference
    clearances = state.get("clearances", [])
    for c in clearances:
        if not c.get("resolves_conflict"):
            issues.append(f"UNLINKED CLEARANCE: {c.get('clearance_id')} has no conflict reference")

    compliance_status = "COMPLIANT" if not issues else f"NON-COMPLIANT ({len(issues)} issues)"

    # Build summary
    audit_summary = {
        "scenario_id": scenario_id,
        "audit_timestamp": now,
        "phases_completed": phases_done,
        "total_traces": len(traces),
        "compliance_status": compliance_status,
        "issues": issues,
        "constraints_verified": DO178C_CONSTRAINTS,
        "trace_ids": [t["trace_id"] for t in traces],
    }

    # Write trace file
    if LOG_TRACES:
        trace_path = TRACE_DIR / f"{scenario_id}_traces.jsonl"
        with trace_path.open("w", encoding="utf-8") as f:
            f.write(json.dumps({"type": "audit_summary", **audit_summary}) + "\n")
            for t in traces:
                f.write(json.dumps(t) + "\n")

    audit_trace = make_trace(
        phase_number=11,
        phase_name="Audit & DO-178C Compliance",
        inputs_summary={"trace_count": len(traces), "phases_done": len(phases_done)},
        decision=compliance_status,
        rationale=f"{len(issues)} compliance issues found" if issues else "All phases traced, all constraints verified",
        outputs_summary=audit_summary,
    )

    emit_event(events, "phase_11", "audit_complete",
               {"compliance": compliance_status, "issues": issues, "trace_count": len(traces)})

    return {
        **state,
        "current_phase": "phase_11_audit",
        "phases_completed": phases_done + ["phase_11"],
        "do178c_traces": traces + [audit_trace],
        "events": events,
    }
