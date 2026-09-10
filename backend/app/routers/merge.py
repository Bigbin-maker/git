from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import (
    MergeConflictResolutionRequest,
    MergeRequestActionRequest,
    MergeRequestListResponse,
    MergeRequestMergeResponse,
    MergeRequestOut,
    MergeRequestSubmitRequest,
)
from app.services.merge_service import MergeService


router = APIRouter(prefix="/merge", tags=["merge"])


@router.post("/requests", response_model=MergeRequestOut)
def submit_merge_request(payload: MergeRequestSubmitRequest, db: Session = Depends(get_db)) -> dict:
    try:
        return MergeService(db).submit(payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/requests", response_model=MergeRequestListResponse)
def list_merge_requests(
    role: str = Query("admin"),
    operator: str = Query(""),
    status: str = Query(""),
    db: Session = Depends(get_db),
) -> dict:
    return {"items": MergeService(db).list_requests(role=role, operator=operator, status=status)}


@router.get("/requests/{merge_request_id}", response_model=MergeRequestOut)
def get_merge_request(merge_request_id: int, db: Session = Depends(get_db)) -> dict:
    result = MergeService(db).get(merge_request_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Merge request not found")
    return result


@router.post("/requests/{merge_request_id}/resolve", response_model=MergeRequestOut)
def resolve_merge_conflict(
    merge_request_id: int,
    payload: MergeConflictResolutionRequest,
    db: Session = Depends(get_db),
) -> dict:
    try:
        result = MergeService(db).resolve_conflict(merge_request_id, payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Merge request not found")
    return result


@router.post("/requests/{merge_request_id}/merge", response_model=MergeRequestMergeResponse)
def merge_into_release_branch(
    merge_request_id: int,
    payload: MergeRequestActionRequest,
    db: Session = Depends(get_db),
) -> dict:
    try:
        result = MergeService(db).merge(merge_request_id, payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Merge request not found")
    return result


@router.post("/requests/{merge_request_id}/reject", response_model=MergeRequestOut)
def reject_merge_request(
    merge_request_id: int,
    payload: MergeRequestActionRequest,
    db: Session = Depends(get_db),
) -> dict:
    try:
        result = MergeService(db).reject(merge_request_id, payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Merge request not found")
    return result
