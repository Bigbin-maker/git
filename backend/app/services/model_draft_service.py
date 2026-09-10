from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

from sqlalchemy.orm import Session

from app.models import ModelDraft, ModelFeedbackLog, now_utc
from app.services.model_generation_service import ModelGenerationService
from app.services.sysml_adapter import SysMLAdapter


class ModelDraftService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.generator = ModelGenerationService()

    def create_from_generated(self, generated: dict[str, Any], source_prompt: str = "") -> dict[str, Any]:
        payload = self._normalize_payload(generated)
        draft = ModelDraft(
            project_name=payload["project_name"],
            source_prompt=source_prompt,
            summary=payload.get("summary", ""),
            assumptions_json=json.dumps(payload.get("assumptions") or [], ensure_ascii=False),
            generation_source=payload.get("generation_source") or "unknown",
            original_json=self._dump(payload),
            current_json=self._dump(payload),
            status="preview",
        )
        self.db.add(draft)
        self.db.commit()
        self.db.refresh(draft)
        return self.to_response(draft)

    def get(self, draft_id: int) -> ModelDraft | None:
        return self.db.get(ModelDraft, draft_id)

    def get_response(self, draft_id: int) -> dict[str, Any] | None:
        draft = self.get(draft_id)
        return self.to_response(draft) if draft else None

    def update_relationship(
        self,
        draft_id: int,
        relationship_id: str,
        update: dict[str, Any],
    ) -> dict[str, Any] | None:
        draft = self.get(draft_id)
        if draft is None:
            return None
        self._ensure_editable(draft)

        payload = self._load(draft.current_json)
        relationships = payload.get("relationships") or []
        target_index = next((index for index, item in enumerate(relationships) if item.get("id") == relationship_id), -1)
        if target_index < 0:
            raise ValueError(f"Relationship {relationship_id} does not exist in draft {draft_id}")

        element_ids = {str(item.get("id")) for item in payload.get("elements") or []}
        source = str(update.get("source") or "").strip()
        target = str(update.get("target") or "").strip()
        if source not in element_ids or target not in element_ids:
            raise ValueError("source and target must reference existing draft elements")

        before = deepcopy(relationships[target_index])
        relationships[target_index] = {
            **relationships[target_index],
            "source": source,
            "target": target,
            "type": str(update.get("type") or relationships[target_index].get("type") or "trace").strip() or "trace",
            "description": str(update.get("description") or ""),
        }
        payload["relationships"] = relationships
        payload["sysml_text"] = self.generator.render_project_text(payload["project_name"], payload.get("elements") or [], relationships)

        draft.current_json = self._dump(payload)
        draft.summary = payload.get("summary", draft.summary)
        draft.assumptions_json = self._dump(payload.get("assumptions") or [])
        draft.generation_source = payload.get("generation_source") or draft.generation_source
        draft.status = "revised"
        draft.updated_at = now_utc()
        self.db.add(draft)
        self._log_feedback(
            draft_id=draft.id,
            action="revise",
            object_type="relationship",
            object_id=relationship_id,
            before=before,
            after=relationships[target_index],
            operator=str(update.get("operator") or "demo-user"),
            comment=str(update.get("comment") or "用户在预览区调整连接线"),
        )
        self.db.commit()
        self.db.refresh(draft)
        return self.to_response(draft)

    def update_element(
        self,
        draft_id: int,
        element_id: str,
        update: dict[str, Any],
    ) -> dict[str, Any] | None:
        draft = self.get(draft_id)
        if draft is None:
            return None
        self._ensure_editable(draft)

        payload = self._load(draft.current_json)
        elements = payload.get("elements") or []
        target_index = next((index for index, item in enumerate(elements) if item.get("id") == element_id), -1)
        if target_index < 0:
            raise ValueError(f"Element {element_id} does not exist in draft {draft_id}")

        before = deepcopy(elements[target_index])
        element_type = str(update.get("type") or before.get("type") or "Block").strip() or "Block"
        elements[target_index] = {
            **elements[target_index],
            "name": str(update.get("name") or before.get("name") or element_id).strip() or element_id,
            "type": element_type,
            "description": str(update.get("description") or ""),
            "package": update.get("package") or before.get("package") or self.generator._default_element_package(element_type),
            "source_requirement": update.get("source_requirement") or None,
            "status": str(update.get("status") or before.get("status") or "candidate").strip() or "candidate",
        }
        payload["elements"] = elements
        payload["sysml_text"] = self.generator.render_project_text(payload["project_name"], elements, payload.get("relationships") or [])

        self._save_revision(
            draft=draft,
            payload=payload,
            action="revise",
            object_type="element",
            object_id=element_id,
            before=before,
            after=elements[target_index],
            operator=str(update.get("operator") or "demo-user"),
            comment=str(update.get("comment") or "用户在预览区修改元素"),
        )
        return self.to_response(draft)

    def create_relationship(self, draft_id: int, data: dict[str, Any]) -> dict[str, Any] | None:
        draft = self.get(draft_id)
        if draft is None:
            return None
        self._ensure_editable(draft)

        payload = self._load(draft.current_json)
        elements = payload.get("elements") or []
        element_ids = {str(item.get("id")) for item in elements}
        source = str(data.get("source") or "").strip()
        target = str(data.get("target") or "").strip()
        if source not in element_ids or target not in element_ids:
            raise ValueError("source and target must reference existing draft elements")

        relationships = payload.get("relationships") or []
        relationship = {
            "id": self._next_relationship_id(relationships),
            "source": source,
            "target": target,
            "type": str(data.get("type") or "trace").strip() or "trace",
            "description": str(data.get("description") or ""),
        }
        relationships.append(relationship)
        payload["relationships"] = relationships
        payload["sysml_text"] = self.generator.render_project_text(payload["project_name"], elements, relationships)

        self._save_revision(
            draft=draft,
            payload=payload,
            action="add",
            object_type="relationship",
            object_id=relationship["id"],
            before={},
            after=relationship,
            operator=str(data.get("operator") or "demo-user"),
            comment=str(data.get("comment") or "用户在预览区新增连接线"),
        )
        return self.to_response(draft)

    def delete_relationship(
        self,
        draft_id: int,
        relationship_id: str,
        operator: str = "demo-user",
        comment: str = "",
    ) -> dict[str, Any] | None:
        draft = self.get(draft_id)
        if draft is None:
            return None
        self._ensure_editable(draft)

        payload = self._load(draft.current_json)
        relationships = payload.get("relationships") or []
        target_index = next((index for index, item in enumerate(relationships) if item.get("id") == relationship_id), -1)
        if target_index < 0:
            raise ValueError(f"Relationship {relationship_id} does not exist in draft {draft_id}")

        before = deepcopy(relationships[target_index])
        del relationships[target_index]
        payload["relationships"] = relationships
        payload["sysml_text"] = self.generator.render_project_text(payload["project_name"], payload.get("elements") or [], relationships)

        self._save_revision(
            draft=draft,
            payload=payload,
            action="delete",
            object_type="relationship",
            object_id=relationship_id,
            before=before,
            after={},
            operator=operator,
            comment=comment or "用户在预览区删除连接线",
        )
        return self.to_response(draft)

    def accept(self, draft_id: int, operator: str = "demo-user", comment: str = "") -> dict[str, Any] | None:
        draft = self.get(draft_id)
        if draft is None:
            return None

        payload = self._load(draft.current_json)
        payload["elements"] = [{**item, "status": "accepted"} for item in payload.get("elements") or []]
        payload["sysml_text"] = self.generator.render_project_text(
            payload["project_name"],
            payload.get("elements") or [],
            payload.get("relationships") or [],
        )
        commit_result = SysMLAdapter(self.db).commit_model(payload.get("elements") or [], payload.get("relationships") or [])

        draft.current_json = self._dump(payload)
        draft.status = "accepted"
        draft.updated_at = now_utc()
        self.db.add(draft)
        self._log_feedback(
            draft_id=draft.id,
            action="accept",
            object_type="draft",
            object_id=str(draft.id),
            before=self._load(draft.original_json),
            after=payload,
            operator=operator,
            comment=comment or "用户采纳预览模型并入库",
        )
        self.db.commit()
        self.db.refresh(draft)
        return {"draft": self.to_response(draft), "commit_result": commit_result}

    def reject(self, draft_id: int, operator: str = "demo-user", comment: str = "") -> dict[str, Any] | None:
        draft = self.get(draft_id)
        if draft is None:
            return None

        payload = self._load(draft.current_json)
        draft.status = "rejected"
        draft.updated_at = now_utc()
        self.db.add(draft)
        self._log_feedback(
            draft_id=draft.id,
            action="reject",
            object_type="draft",
            object_id=str(draft.id),
            before=self._load(draft.original_json),
            after=payload,
            operator=operator,
            comment=comment or "用户拒绝候选模型",
        )
        self.db.commit()
        self.db.refresh(draft)
        return self.to_response(draft)

    def to_response(self, draft: ModelDraft) -> dict[str, Any]:
        payload = self._load(draft.current_json)
        payload = self._normalize_payload(payload)
        payload["draft_id"] = draft.id
        payload["draft_status"] = draft.status
        return payload

    def _normalize_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        project_name = str(payload.get("project_name") or "AI_MBSE_Project")
        elements = [dict(item) for item in payload.get("elements") or []]
        relationships = [dict(item) for item in payload.get("relationships") or []]
        diagram_views = [dict(item) for item in payload.get("diagram_views") or []]
        sysml_text = str(payload.get("sysml_text") or "").strip()
        if not sysml_text:
            sysml_text = self.generator.render_project_text(project_name, elements, relationships)
        return {
            "project_name": project_name,
            "summary": str(payload.get("summary") or ""),
            "assumptions": list(payload.get("assumptions") or []),
            "generation_source": str(payload.get("generation_source") or "unknown"),
            "elements": elements,
            "relationships": relationships,
            "sysml_text": sysml_text,
            "diagram_views": diagram_views,
        }

    def _save_revision(
        self,
        draft: ModelDraft,
        payload: dict[str, Any],
        action: str,
        object_type: str,
        object_id: str,
        before: Any,
        after: Any,
        operator: str,
        comment: str,
    ) -> None:
        draft.current_json = self._dump(payload)
        draft.summary = payload.get("summary", draft.summary)
        draft.assumptions_json = self._dump(payload.get("assumptions") or [])
        draft.generation_source = payload.get("generation_source") or draft.generation_source
        draft.status = "revised"
        draft.updated_at = now_utc()
        self.db.add(draft)
        self._log_feedback(
            draft_id=draft.id,
            action=action,
            object_type=object_type,
            object_id=object_id,
            before=before,
            after=after,
            operator=operator,
            comment=comment,
        )
        self.db.commit()
        self.db.refresh(draft)

    def _ensure_editable(self, draft: ModelDraft) -> None:
        if draft.status in {"accepted", "rejected"}:
            raise ValueError(f"Draft {draft.id} is {draft.status} and cannot be edited")

    def _next_relationship_id(self, relationships: list[dict[str, Any]]) -> str:
        used = {str(item.get("id") or "") for item in relationships}
        max_index = 0
        for relationship_id in used:
            if not relationship_id.startswith("REL-"):
                continue
            try:
                max_index = max(max_index, int(relationship_id.split("-", 1)[1]))
            except ValueError:
                continue
        index = max_index + 1
        while f"REL-{index:03d}" in used:
            index += 1
        return f"REL-{index:03d}"

    def _log_feedback(
        self,
        draft_id: int,
        action: str,
        object_type: str,
        object_id: str,
        before: Any,
        after: Any,
        operator: str,
        comment: str,
    ) -> None:
        self.db.add(
            ModelFeedbackLog(
                draft_id=draft_id,
                action=action,
                object_type=object_type,
                object_id=object_id,
                before_json=self._dump(before),
                after_json=self._dump(after),
                operator=operator or "demo-user",
                comment=comment,
            )
        )

    def _dump(self, payload: Any) -> str:
        return json.dumps(payload, ensure_ascii=False)

    def _load(self, value: str) -> dict[str, Any]:
        try:
            data = json.loads(value or "{}")
        except json.JSONDecodeError:
            data = {}
        return data if isinstance(data, dict) else {}
