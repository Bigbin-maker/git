from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.validation_service import ValidationService


router = APIRouter(prefix="/validation", tags=["validation"])


@router.post("/run")
def run_validation(db: Session = Depends(get_db)) -> dict:
    return ValidationService(db).run()


@router.get("/history")
def validation_history(db: Session = Depends(get_db)) -> list[dict]:
    return ValidationService(db).history()
