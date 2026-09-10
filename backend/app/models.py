from datetime import datetime

from sqlalchemy import DateTime, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def now_utc() -> datetime:
    return datetime.utcnow()


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    filename: Mapped[str] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    title: Mapped[str] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text)
    chunk_index: Mapped[int] = mapped_column(Integer, default=0)
    keywords_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)


class ModelDraft(Base):
    __tablename__ = "model_drafts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_name: Mapped[str] = mapped_column(Text)
    source_prompt: Mapped[str] = mapped_column(Text, default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    assumptions_json: Mapped[str] = mapped_column(Text, default="[]")
    generation_source: Mapped[str] = mapped_column(Text, default="unknown")
    original_json: Mapped[str] = mapped_column(Text)
    current_json: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, default="preview")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc, onupdate=now_utc)


class ModelFeedbackLog(Base):
    __tablename__ = "model_feedback_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    draft_id: Mapped[int] = mapped_column(Integer)
    action: Mapped[str] = mapped_column(Text)
    object_type: Mapped[str] = mapped_column(Text, default="")
    object_id: Mapped[str] = mapped_column(Text, default="")
    before_json: Mapped[str] = mapped_column(Text, default="")
    after_json: Mapped[str] = mapped_column(Text, default="")
    comment: Mapped[str] = mapped_column(Text, default="")
    operator: Mapped[str] = mapped_column(Text, default="demo-user")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)


class MergeRequest(Base):
    __tablename__ = "merge_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    draft_id: Mapped[int] = mapped_column(Integer)
    project_name: Mapped[str] = mapped_column(Text, default="")
    source_branch: Mapped[str] = mapped_column(Text, default="dev/designer")
    target_branch: Mapped[str] = mapped_column(Text, default="release/main")
    title: Mapped[str] = mapped_column(Text, default="")
    description: Mapped[str] = mapped_column(Text, default="")
    submitter: Mapped[str] = mapped_column(Text, default="designer")
    reviewer: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(Text, default="pending")
    candidate_json: Mapped[str] = mapped_column(Text, default="{}")
    release_snapshot_json: Mapped[str] = mapped_column(Text, default="{}")
    change_set_json: Mapped[str] = mapped_column(Text, default="{}")
    conflicts_json: Mapped[str] = mapped_column(Text, default="[]")
    resolutions_json: Mapped[str] = mapped_column(Text, default="{}")
    commit_result_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc, onupdate=now_utc)
    merged_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class MergeAuditLog(Base):
    __tablename__ = "merge_audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    merge_request_id: Mapped[int] = mapped_column(Integer)
    action: Mapped[str] = mapped_column(Text)
    operator: Mapped[str] = mapped_column(Text, default="demo-user")
    role: Mapped[str] = mapped_column(Text, default="designer")
    message: Mapped[str] = mapped_column(Text, default="")
    detail_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)


class ChangeScenario(Base):
    __tablename__ = "change_scenarios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_name: Mapped[str] = mapped_column(Text, default="")
    target_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_name: Mapped[str] = mapped_column(Text, default="")
    attribute_name: Mapped[str] = mapped_column(Text, default="")
    old_value: Mapped[str] = mapped_column(Text, default="")
    new_value: Mapped[str] = mapped_column(Text, default="")
    unit: Mapped[str] = mapped_column(Text, default="")
    change_description: Mapped[str] = mapped_column(Text, default="")
    task_context: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(Text, default="sandbox")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)


class ChangeImpactReport(Base):
    __tablename__ = "change_impact_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scenario_id: Mapped[int] = mapped_column(Integer)
    risk_level: Mapped[str] = mapped_column(Text, default="low")
    summary: Mapped[str] = mapped_column(Text, default="")
    topology_json: Mapped[str] = mapped_column(Text, default="{}")
    matrix_json: Mapped[str] = mapped_column(Text, default="[]")
    suggestions_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)


class Requirement(Base):
    __tablename__ = "requirements"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text)
    type: Mapped[str] = mapped_column(Text)
    priority: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(Text)
    score: Mapped[int] = mapped_column(Integer)
    suggestion: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc, onupdate=now_utc)


class SysMLElement(Base):
    __tablename__ = "sysml_elements"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    type: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text)
    source_requirement: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, default="candidate")
    external_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc, onupdate=now_utc)


class SysMLRelationship(Base):
    __tablename__ = "sysml_relationships"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    source: Mapped[str] = mapped_column(Text)
    target: Mapped[str] = mapped_column(Text)
    type: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)


class ReviewLog(Base):
    __tablename__ = "review_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    object_type: Mapped[str] = mapped_column(Text)
    object_id: Mapped[str] = mapped_column(Text)
    action: Mapped[str] = mapped_column(Text)
    old_value: Mapped[str] = mapped_column(Text, default="")
    new_value: Mapped[str] = mapped_column(Text, default="")
    operator: Mapped[str] = mapped_column(Text, default="demo-user")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)


class ValidationReport(Base):
    __tablename__ = "validation_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    score: Mapped[int] = mapped_column(Integer)
    conclusion: Mapped[str] = mapped_column(Text)
    issues_json: Mapped[str] = mapped_column(Text)
    statistics_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)


class ChatLog(Base):
    __tablename__ = "chat_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(Text)
    message: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)
    tool_calls_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc)
