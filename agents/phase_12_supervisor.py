"""
Phase 12 — Supervisor / Meta-Agent (CrewAI Crew)
Validates all prior phase outputs, assesses system health, and produces the final report.
Uses a CrewAI Crew with two specialist agents: Validator and Reporter.
"""

from core.state import ATCState, SystemHealth
from core.prompts import get_prompt
from agents.base import call_gemini, make_trace, emit_event

# CrewAI imports — used here for the multi-agent crew pattern
try:
    from crewai import Agent, Task, Crew, Process
    from langchain_google_genai import ChatGoogleGenerativeAI
    from core.config import GOOGLE_API_KEY, MODEL_NAME, AGENT_TEMPERATURE
    _CREWAI_AVAILABLE = True
except ImportError:
    _CREWAI_AVAILABLE = False

import os

SYSTEM = get_prompt("phase_12.system").template

SCHEMA = """{
  "system_health": {
    "overall_status": "nominal",
    "phase_statuses": {
      "phase_01": "ok", "phase_02": "ok", "phase_03": "ok",
      "phase_04": "ok", "phase_05": "ok", "phase_06": "ok",
      "phase_07": "ok", "phase_08": "ok", "phase_09": "ok",
      "phase_10": "ok", "phase_11": "ok"
    },
    "anomalies": [],
    "recommendations": []
  },
  "final_report": "Watch supervisor summary...",
  "unresolved_conflicts": [],
  "active_emergencies": []
}"""


def _run_crewai_supervisor(state_summary: dict) -> dict:
    """Run a two-agent CrewAI crew for validation + reporting."""
    llm = ChatGoogleGenerativeAI(
        model=MODEL_NAME,
        google_api_key=GOOGLE_API_KEY,
        temperature=AGENT_TEMPERATURE,
    )

    validator = Agent(
        role="ATC Safety Validator",
        goal="Verify all safety constraints are met and flag any unresolved issues",
        backstory="Expert ATC safety analyst with DO-178C certification experience",
        llm=llm,
        verbose=False,
    )

    reporter = Agent(
        role="Watch Supervisor Reporter",
        goal="Synthesize the traffic picture into a concise watch supervisor brief",
        backstory="Senior ATC watch supervisor with 20 years ARTCC experience",
        llm=llm,
        verbose=False,
    )

    validate_task = Task(
        description=(
            f"Review this ATC scenario state and identify any safety issues:\n{state_summary}\n"
            "List unresolved conflicts, active emergencies, and any constraint violations."
        ),
        agent=validator,
        expected_output="JSON safety assessment with issues list",
    )

    report_task = Task(
        description=(
            "Based on the validator's findings, write a watch supervisor brief covering:\n"
            "- Traffic picture summary\n- Active conflicts and resolution status\n"
            "- Emergencies\n- TFM programs active\n- System health status"
        ),
        agent=reporter,
        expected_output="Concise watch supervisor brief (3-5 sentences)",
        context=[validate_task],
    )

    crew = Crew(
        agents=[validator, reporter],
        tasks=[validate_task, report_task],
        process=Process.sequential,
        verbose=False,
    )
    result = crew.kickoff()
    return {"final_report": str(result), "crew_used": True}


def phase_12_node(state: ATCState) -> dict:
    conflicts = state.get("conflicts", [])
    emergencies = state.get("emergencies", [])
    sectors = state.get("sectors", {})
    clearances = state.get("clearances", [])
    tfm_programs = state.get("tfm_programs", [])
    phases_done = state.get("phases_completed", [])
    events = list(state.get("events", []))

    unresolved = [c for c in conflicts if c.get("severity") in ("alert", "warning")]
    active_emergencies = [e for e in emergencies if e.get("status") == "active"]
    overloaded_sectors = [sid for sid, s in sectors.items() if s.get("load_pct", 0) > 90]

    state_summary = {
        "phases_completed": phases_done,
        "flights": len(state.get("flights", [])),
        "conflicts_total": len(conflicts),
        "unresolved_conflicts": unresolved,
        "active_emergencies": active_emergencies,
        "clearances_issued": len(clearances),
        "tfm_programs": len(tfm_programs),
        "overloaded_sectors": overloaded_sectors,
        "weather_hazards": len(state.get("weather_hazards", [])),
        "handoffs": len(state.get("handoffs", [])),
    }

    # Prefer CrewAI crew; fall back to direct Gemini call
    if _CREWAI_AVAILABLE:
        try:
            crew_result = _run_crewai_supervisor(state_summary)
            final_report = crew_result.get("final_report", "")
        except Exception:
            final_report = None
    else:
        final_report = None

    if not final_report:
        prompt = (
            f"Review this completed ATC scenario and produce a supervisor report.\n\n"
            f"State summary:\n{state_summary}\n\n"
            f"Output JSON matching:\n{SCHEMA}"
        )
        result = call_gemini(SYSTEM, prompt)
        final_report = result.get("final_report", "System nominal.")
        gemini_health = result.get("system_health", {})
    else:
        gemini_health = {}

    # Build system health
    overall = "critical" if unresolved or active_emergencies else \
              "degraded" if overloaded_sectors else "nominal"

    anomalies = (
        [f"Unresolved conflict: {c['conflict_id']}" for c in unresolved] +
        [f"Active emergency: {e['callsign']}" for e in active_emergencies] +
        [f"Sector overload: {s}" for s in overloaded_sectors]
    )

    health = SystemHealth(
        overall_status=gemini_health.get("overall_status", overall),
        phase_statuses={ph: "ok" for ph in phases_done},
        anomalies=gemini_health.get("anomalies", anomalies),
        recommendations=gemini_health.get("recommendations", [
            "Verify resolution of all flagged items before next scan cycle"
        ] if anomalies else ["System nominal — continue standard operations"]),
    )

    trace = make_trace(
        phase_number=12,
        phase_name="Supervisor / Meta-Agent",
        inputs_summary=state_summary,
        decision=f"System status: {health['overall_status'].upper()}",
        rationale=final_report[:200],
        outputs_summary={"anomalies": len(anomalies), "health": health["overall_status"]},
    )

    emit_event(events, "phase_12", "supervisor_complete",
               {"status": health["overall_status"], "anomalies": anomalies,
                "report": final_report[:300]})

    return {
        **state,
        "current_phase": "phase_12_supervisor",
        "phases_completed": phases_done + ["phase_12"],
        "system_health": health,
        "final_report": final_report,
        "do178c_traces": state.get("do178c_traces", []) + [trace],
        "events": events,
    }
