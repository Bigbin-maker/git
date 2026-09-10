import json
from typing import Any

from sqlalchemy.orm import Session

from app.models import Requirement, ReviewLog
from app.services.llm_service import LLMService


class RequirementService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.llm = LLMService()

    def analyze_and_store(self, source_text: str, scenario: str) -> list[dict[str, Any]]:
        requirements = self.llm.analyze_requirements(source_text, scenario)
        for item in requirements:
            self._upsert_requirement(item)
        self.db.commit()
        return requirements

    def list_requirements(self) -> list[Requirement]:
        return self.db.query(Requirement).order_by(Requirement.id.asc()).all()

    def review(self, requirement_id: str, payload: Any) -> Requirement:
        requirement = self.db.get(Requirement, requirement_id)
        if not requirement:
            raise ValueError(f"Requirement {requirement_id} not found")

        old_value = json.dumps(self._to_dict(requirement), ensure_ascii=False)
        if payload.action == "confirm":
            requirement.status = "confirmed"
        elif payload.action == "reject":
            requirement.status = "rejected"
        elif payload.action == "update":
            for field in ["name", "description", "type", "priority", "score", "suggestion"]:
                value = getattr(payload, field, None)
                if value is not None:
                    setattr(requirement, field, value)
            requirement.status = "confirmed"

        self.db.add(
            ReviewLog(
                object_type="requirement",
                object_id=requirement_id,
                action=payload.action,
                old_value=old_value,
                new_value=json.dumps(self._to_dict(requirement), ensure_ascii=False),
                operator=payload.operator,
            )
        )
        self.db.commit()
        self.db.refresh(requirement)
        return requirement

    def _upsert_requirement(self, item: dict[str, Any]) -> Requirement:
        requirement = self.db.get(Requirement, item["id"])
        if requirement is None:
            requirement = Requirement(id=item["id"])
        for field in ["name", "description", "type", "priority", "source", "score", "suggestion", "status"]:
            setattr(requirement, field, item.get(field, getattr(requirement, field, None)))
        self.db.add(requirement)
        return requirement

    def _to_dict(self, requirement: Requirement) -> dict[str, Any]:
        return {
            "id": requirement.id,
            "name": requirement.name,
            "description": requirement.description,
            "type": requirement.type,
            "priority": requirement.priority,
            "source": requirement.source,
            "score": requirement.score,
            "suggestion": requirement.suggestion,
            "status": requirement.status,
        }
