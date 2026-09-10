from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Requirement
from app.schemas import (
    DraftValidationFixRequest,
    DraftValidationFixResponse,
    DraftValidationReport,
    DiagramView,
    InternalBlockDiagramGenerateRequest,
    ModelDraftAcceptResponse,
    ModelDraftElementUpdateRequest,
    ModelDraftFeedbackRequest,
    ModelDraftRelationshipCreateRequest,
    ModelDraftRelationshipUpdateRequest,
    SysMLCommitRequest,
    SysMLGenerateRequest,
    SysMLIntentRequest,
    SysMLIntentResponse,
    SysMLProjectGenerateRequest,
    SysMLProjectGenerateResponse,
)
from app.services.draft_validation_service import DraftValidationService
from app.services.model_draft_service import ModelDraftService
from app.services.model_generation_service import ModelGenerationService
from app.services.sysml_adapter import SysMLAdapter


router = APIRouter(prefix="/sysml", tags=["sysml"])


@router.post("/generate")
def generate_sysml(payload: SysMLGenerateRequest, db: Session = Depends(get_db)) -> dict:
    query = db.query(Requirement).filter(Requirement.status == "confirmed")
    if payload.requirement_ids:
        query = query.filter(Requirement.id.in_(payload.requirement_ids))
    requirements = [
        {
            "id": item.id,
            "name": item.name,
            "description": item.description,
            "type": item.type,
            "priority": item.priority,
            "source": item.source,
            "score": item.score,
            "suggestion": item.suggestion,
            "status": item.status,
        }
        for item in query.order_by(Requirement.id.asc()).all()
    ]
    return ModelGenerationService().generate(requirements)


@router.post("/generate-project", response_model=SysMLProjectGenerateResponse)
def generate_sysml_project(payload: SysMLProjectGenerateRequest, db: Session = Depends(get_db)) -> dict:
    generated = ModelGenerationService().generate_project_from_dialogue(
        conversation=[item.model_dump() for item in payload.conversation],
        prompt=payload.prompt,
        project_name=payload.project_name,
    )
    return ModelDraftService(db).create_from_generated(generated, source_prompt=payload.prompt)


@router.post("/internal-block-diagram", response_model=DiagramView)
def generate_internal_block_diagram(payload: InternalBlockDiagramGenerateRequest) -> dict:
    return ModelGenerationService().generate_internal_block_diagram(
        project_name=payload.project_name,
        prompt=payload.prompt,
        focus_element=payload.focus_element.model_dump(),
        elements=[item.model_dump() for item in payload.elements],
        relationships=[item.model_dump() for item in payload.relationships],
    )


@router.post("/classify-intent", response_model=SysMLIntentResponse)
def classify_sysml_intent(payload: SysMLIntentRequest) -> dict:
    return ModelGenerationService().classify_modeling_intent(
        conversation=[item.model_dump() for item in payload.conversation],
        message=payload.message,
    )


@router.post("/commit")
def commit_sysml(payload: SysMLCommitRequest, db: Session = Depends(get_db)) -> dict:
    adapter = SysMLAdapter(db)
    return adapter.commit_model(
        [item.model_dump() for item in payload.elements],
        [item.model_dump() for item in payload.relationships],
    )


@router.get("/drafts/{draft_id}", response_model=SysMLProjectGenerateResponse)
def get_model_draft(draft_id: int, db: Session = Depends(get_db)) -> dict:
    result = ModelDraftService(db).get_response(draft_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Model draft not found")
    return result


@router.patch("/drafts/{draft_id}/relationships/{relationship_id}", response_model=SysMLProjectGenerateResponse)
def update_model_draft_relationship(
    draft_id: int,
    relationship_id: str,
    payload: ModelDraftRelationshipUpdateRequest,
    db: Session = Depends(get_db),
) -> dict:
    try:
        result = ModelDraftService(db).update_relationship(draft_id, relationship_id, payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Model draft not found")
    return result


@router.patch("/drafts/{draft_id}/elements/{element_id}", response_model=SysMLProjectGenerateResponse)
def update_model_draft_element(
    draft_id: int,
    element_id: str,
    payload: ModelDraftElementUpdateRequest,
    db: Session = Depends(get_db),
) -> dict:
    try:
        result = ModelDraftService(db).update_element(draft_id, element_id, payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Model draft not found")
    return result


@router.post("/drafts/{draft_id}/relationships", response_model=SysMLProjectGenerateResponse)
def create_model_draft_relationship(
    draft_id: int,
    payload: ModelDraftRelationshipCreateRequest,
    db: Session = Depends(get_db),
) -> dict:
    try:
        result = ModelDraftService(db).create_relationship(draft_id, payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Model draft not found")
    return result


@router.delete("/drafts/{draft_id}/relationships/{relationship_id}", response_model=SysMLProjectGenerateResponse)
def delete_model_draft_relationship(
    draft_id: int,
    relationship_id: str,
    db: Session = Depends(get_db),
) -> dict:
    try:
        result = ModelDraftService(db).delete_relationship(draft_id, relationship_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Model draft not found")
    return result


@router.post("/drafts/{draft_id}/validate", response_model=DraftValidationReport)
def validate_model_draft(draft_id: int, db: Session = Depends(get_db)) -> dict:
    result = DraftValidationService(db).validate(draft_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Model draft not found")
    return result


@router.post("/drafts/{draft_id}/fix", response_model=DraftValidationFixResponse)
def fix_model_draft_issues(
    draft_id: int,
    payload: DraftValidationFixRequest,
    db: Session = Depends(get_db),
) -> dict:
    try:
        result = DraftValidationService(db).fix(draft_id, payload.issue_ids, operator=payload.operator)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Model draft not found")
    return result


@router.post("/drafts/{draft_id}/accept", response_model=ModelDraftAcceptResponse)
def accept_model_draft(
    draft_id: int,
    payload: ModelDraftFeedbackRequest | None = None,
    db: Session = Depends(get_db),
) -> dict:
    feedback = payload or ModelDraftFeedbackRequest()
    result = ModelDraftService(db).accept(draft_id, operator=feedback.operator, comment=feedback.comment)
    if result is None:
        raise HTTPException(status_code=404, detail="Model draft not found")
    return result


@router.post("/drafts/{draft_id}/reject", response_model=SysMLProjectGenerateResponse)
def reject_model_draft(
    draft_id: int,
    payload: ModelDraftFeedbackRequest | None = None,
    db: Session = Depends(get_db),
) -> dict:
    feedback = payload or ModelDraftFeedbackRequest()
    result = ModelDraftService(db).reject(draft_id, operator=feedback.operator, comment=feedback.comment)
    if result is None:
        raise HTTPException(status_code=404, detail="Model draft not found")
    return result


@router.get("/elements")
def get_elements(db: Session = Depends(get_db)) -> list[dict]:
    return SysMLAdapter(db).get_elements()


@router.get("/graph")
def get_graph(db: Session = Depends(get_db)) -> dict:
    return SysMLAdapter(db).get_graph()
