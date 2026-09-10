from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import ChangeImpactSandboxRequest, ChangeImpactSandboxResponse, ImpactAnalysisRequest, ImpactAnalysisResponse
from app.services.impact_service import ImpactService


router = APIRouter(prefix="/impact", tags=["impact"])


@router.post("/analyze", response_model=ImpactAnalysisResponse)
def analyze_impact(payload: ImpactAnalysisRequest, db: Session = Depends(get_db)) -> dict:
    return ImpactService(db).analyze(payload.element_id, payload.change_description, payload.depth)


@router.post("/sandbox", response_model=ChangeImpactSandboxResponse)
def sandbox_change_impact(payload: ChangeImpactSandboxRequest, db: Session = Depends(get_db)) -> dict:
    return ImpactService(db).sandbox(payload.model_dump())
