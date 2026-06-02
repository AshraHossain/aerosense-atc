from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from simulation.scenario_generator import generate_scenario, list_scenarios

router = APIRouter()

# Injected by api/__init__.py after the event loop is available.
_start_run = None


class RunRequest(BaseModel):
    scenario_key: str = "nominal"


@router.post("/api/scenario/run")
async def run_scenario(body: RunRequest):
    import asyncio
    scenario = generate_scenario(body.scenario_key)
    _start_run(scenario, asyncio.get_running_loop())
    return {
        "scenario_id":   scenario["scenario_id"],
        "scenario_name": scenario["scenario_name"],
    }


@router.get("/api/scenarios")
async def get_scenarios():
    return list_scenarios()


@router.get("/api/health")
async def health():
    return {"status": "ok"}
