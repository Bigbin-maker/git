from uuid import uuid4

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.llm_service import LLMService
from app.services.magicdraw_adapter import MagicDrawAdapter
from app.services.simulation_service import SimulationService
from app.services.sysml_adapter import SysMLAdapter


router = APIRouter(tags=["health"])
BACKEND_SESSION_ID = str(uuid4())


@router.get("/health")
def health_check(db: Session = Depends(get_db)) -> dict:
    database = {"available": True, "message": "正常"}
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:
        database = {"available": False, "message": str(exc)}

    return {
        "status": "ok" if database["available"] else "degraded",
        "backend_session_id": BACKEND_SESSION_ID,
        "llm": LLMService().health_check(),
        "sysml": SysMLAdapter(db).health_check(),
        "magicdraw": MagicDrawAdapter().health_check(),
        "simulation": SimulationService().status(),
        "database": database,
    }
