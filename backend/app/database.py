from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import get_settings


settings = get_settings()

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if settings.database_url.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)


def reset_runtime_state(clear_knowledge: bool = False) -> None:
    from app.models import (
        ChangeImpactReport,
        ChangeScenario,
        ChatLog,
        Document,
        KnowledgeChunk,
        MergeAuditLog,
        MergeRequest,
        ModelDraft,
        ModelFeedbackLog,
        Requirement,
        ReviewLog,
        SysMLElement,
        SysMLRelationship,
        ValidationReport,
    )

    tables = [
        MergeAuditLog,
        MergeRequest,
        ModelFeedbackLog,
        ModelDraft,
        ChangeImpactReport,
        ChangeScenario,
        ValidationReport,
        ReviewLog,
        ChatLog,
        SysMLRelationship,
        SysMLElement,
        Requirement,
    ]
    if clear_knowledge:
        tables = [KnowledgeChunk, Document, *tables]

    db = SessionLocal()
    try:
        for table in tables:
            db.query(table).delete()
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
