from fastapi import APIRouter

from app.schemas import SimulationRunRequest, SimulationRunResponse
from app.services.simulation_service import SimulationService


router = APIRouter(prefix="/simulation", tags=["simulation"])


@router.get("/status")
def simulation_status() -> dict:
    return SimulationService().status()


@router.post("/run", response_model=SimulationRunResponse)
def run_simulation(payload: SimulationRunRequest) -> dict:
    return SimulationService().run(payload.model_id, payload.tool)
