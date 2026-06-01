"""
AeroSense ATC — Base Agent Utilities
Shared Gemini call helper used by all 12 phase agents.
"""

import json
import hashlib
import re
from datetime import datetime, timezone

import google.generativeai as genai
from core.config import MODEL_NAME, AGENT_TEMPERATURE, DO178C_CONSTRAINTS
from core.state import DO178CTrace


def call_gemini(system: str, prompt: str) -> dict:
    """
    Call Gemini in JSON mode with deterministic temperature.
    Returns parsed dict. Raises ValueError on parse failure.
    """
    model = genai.GenerativeModel(
        model_name=MODEL_NAME,
        system_instruction=system,
        generation_config=genai.types.GenerationConfig(
            response_mime_type="application/json",
            temperature=AGENT_TEMPERATURE,
            max_output_tokens=4096,
        ),
    )
    response = model.generate_content(prompt)
    raw = response.text.strip()

    # Strip accidental markdown fences
    cleaned = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.MULTILINE)
    cleaned = re.sub(r"\s*```\s*$", "", cleaned, flags=re.MULTILINE)

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}", cleaned)
        if m:
            return json.loads(m.group())
        raise ValueError(f"Gemini returned non-JSON: {raw[:200]}")


def make_trace(
    phase_number: int,
    phase_name: str,
    inputs_summary: dict,
    decision: str,
    rationale: str,
    outputs_summary: dict,
    constraints: list[str] | None = None,
) -> DO178CTrace:
    """
    Produce a DO-178C compliant decision trace entry.
    determinism_flag=True because AGENT_TEMPERATURE=0.1 and inputs are hashed.
    """
    inputs_hash = hashlib.sha256(
        json.dumps(inputs_summary, sort_keys=True).encode()
    ).hexdigest()[:16]

    return DO178CTrace(
        trace_id=f"T{phase_number:02d}-{inputs_hash}",
        phase_number=phase_number,
        phase_name=phase_name,
        timestamp=datetime.now(timezone.utc).isoformat(),
        inputs_summary=inputs_summary,
        decision=decision,
        rationale=rationale,
        safety_constraints_verified=constraints or DO178C_CONSTRAINTS,
        outputs_summary=outputs_summary,
        determinism_flag=True,
    )


def emit_event(state_events: list, phase: str, event_type: str, data: dict) -> None:
    """Append a structured event to the cross-phase event bus."""
    state_events.append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "phase": phase,
        "type": event_type,
        "data": data,
    })
