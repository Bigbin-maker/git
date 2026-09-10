from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import RequirementAnalyzeRequest, RequirementAnalyzeResponse, RequirementOut, RequirementReviewRequest
from app.services.requirement_service import RequirementService


router = APIRouter(prefix="/requirements", tags=["requirements"])


@router.post("/analyze", response_model=RequirementAnalyzeResponse)
def analyze_requirements(payload: RequirementAnalyzeRequest, db: Session = Depends(get_db)) -> dict:
    requirements = RequirementService(db).analyze_and_store(payload.source_text, payload.scenario)
    return {"requirements": requirements}


@router.get("", response_model=list[RequirementOut])
def list_requirements(db: Session = Depends(get_db)):
    return RequirementService(db).list_requirements()


@router.post("/{requirement_id}/review", response_model=RequirementOut)
def review_requirement(requirement_id: str, payload: RequirementReviewRequest, db: Session = Depends(get_db)):
    try:
        return RequirementService(db).review(requirement_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
