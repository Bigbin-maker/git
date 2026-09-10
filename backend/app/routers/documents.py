from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import DocumentExtractResponse, DocumentOut, KnowledgeBaseSummary
from app.services.document_service import DocumentService


router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("/upload", response_model=DocumentOut)
async def upload_document(file: UploadFile = File(...), db: Session = Depends(get_db)):
    return await DocumentService(db).save_upload(file)


@router.post("/extract", response_model=DocumentExtractResponse)
async def extract_document(file: UploadFile = File(...), db: Session = Depends(get_db)):
    return await DocumentService(db).extract_upload(file)


@router.get("", response_model=list[DocumentOut])
def list_documents(db: Session = Depends(get_db)):
    return DocumentService(db).list_documents()


@router.get("/knowledge-summary", response_model=KnowledgeBaseSummary)
def knowledge_summary(db: Session = Depends(get_db)):
    return DocumentService(db).knowledge_summary()


@router.delete("/knowledge")
def reset_knowledge_base(db: Session = Depends(get_db)):
    return DocumentService(db).reset_knowledge_base()


@router.get("/{document_id}", response_model=DocumentOut)
def get_document(document_id: int, db: Session = Depends(get_db)):
    document = DocumentService(db).get_document(document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    return document
