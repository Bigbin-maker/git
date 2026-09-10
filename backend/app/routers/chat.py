from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import ChatRequest, ChatResponse
from app.services.agent_service import AgentService


router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
def chat(payload: ChatRequest, db: Session = Depends(get_db)) -> dict:
    return AgentService(db).run(payload.session_id, payload.message, payload.task_type, [item.model_dump() for item in payload.conversation])


@router.post("/stream")
def chat_stream(payload: ChatRequest, db: Session = Depends(get_db)) -> StreamingResponse:
    return StreamingResponse(
        AgentService(db).stream(payload.session_id, payload.message, payload.task_type, [item.model_dump() for item in payload.conversation]),
        media_type="application/x-ndjson",
    )
