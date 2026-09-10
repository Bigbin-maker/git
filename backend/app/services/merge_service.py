from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models import MergeAuditLog, MergeRequest, ModelDraft, SysMLElement, SysMLRelationship, now_utc
from app.services.sysml_adapter import SysMLAdapter


ELEMENT_CONFLICT_FIELDS = {"type"}
RELATIONSHIP_CONFLICT_FIELDS = {"source", "target", "type"}


class MergeService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def submit(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._ensure_tables()
        draft = self.db.get(ModelDraft, int(payload.get("draft_id") or 0))
        if draft is None:
            raise ValueError("Model draft not found")
        if draft.status in {"rejected"}:
            raise ValueError("Rejected draft cannot be submitted")

        candidate = self._load(draft.current_json)
        candidate = self._normalize_candidate(candidate, draft)
        release_snapshot = self._release_snapshot()
        change_set, conflicts = self._compare(candidate, release_snapshot)
        status = "conflict" if conflicts else "pending"

        existing = (
            self.db.query(MergeRequest)
            .filter(MergeRequest.draft_id == draft.id, MergeRequest.status.in_(["pending", "conflict"]))
            .order_by(MergeRequest.id.desc())
            .first()
        )
        if existing:
            existing.candidate_json = self._dump(candidate)
            existing.release_snapshot_json = self._dump(release_snapshot)
            existing.change_set_json = self._dump(change_set)
            existing.conflicts_json = self._dump(conflicts)
            existing.resolutions_json = "{}"
            existing.status = status
            existing.updated_at = now_utc()
            existing.title = str(payload.get("title") or existing.title or f"{candidate['project_name']} 合并请求")
            existing.description = str(payload.get("description") or existing.description or "")
            mr = existing
        else:
            mr = MergeRequest(
                draft_id=draft.id,
                project_name=candidate["project_name"],
                source_branch=str(payload.get("source_branch") or "dev/designer"),
                target_branch=str(payload.get("target_branch") or "release/main"),
                title=str(payload.get("title") or f"{candidate['project_name']} 合并请求"),
                description=str(payload.get("description") or ""),
                submitter=str(payload.get("submitter") or "designer"),
                status=status,
                candidate_json=self._dump(candidate),
                release_snapshot_json=self._dump(release_snapshot),
                change_set_json=self._dump(change_set),
                conflicts_json=self._dump(conflicts),
            )
            self.db.add(mr)
            self.db.flush()

        draft.status = "submitted"
        draft.updated_at = now_utc()
        self.db.add(draft)
        self._log(
            mr.id,
            "submit",
            operator=mr.submitter,
            role="designer",
            message=f"提交合并请求，状态：{'发现冲突' if conflicts else '待审核'}",
            detail={"change_summary": change_set.get("summary", {}), "conflict_count": len(conflicts)},
        )
        self.db.commit()
        self.db.refresh(mr)
        return self.to_response(mr)

    def list_requests(self, role: str = "admin", operator: str = "", status: str = "") -> list[dict[str, Any]]:
        self._ensure_tables()
        query = self.db.query(MergeRequest)
        if status:
            query = query.filter(MergeRequest.status == status)
        if role != "admin" and operator:
            query = query.filter(MergeRequest.submitter == operator)
        rows = query.order_by(MergeRequest.updated_at.desc(), MergeRequest.id.desc()).all()
        return [self.to_response(item) for item in rows]

    def get(self, merge_request_id: int) -> dict[str, Any] | None:
        self._ensure_tables()
        item = self.db.get(MergeRequest, merge_request_id)
        return self.to_response(item) if item else None

    def resolve_conflict(self, merge_request_id: int, payload: dict[str, Any]) -> dict[str, Any] | None:
        self._ensure_tables()
        mr = self.db.get(MergeRequest, merge_request_id)
        if mr is None:
            return None
        if mr.status in {"merged", "rejected"}:
            raise ValueError("Merged or rejected request cannot be changed")
        if str(payload.get("role") or "") != "admin":
            raise ValueError("Only admin can resolve merge conflicts")

        conflict_id = str(payload.get("conflict_id") or "")
        resolution = str(payload.get("resolution") or "")
        conflicts = self._load_list(mr.conflicts_json)
        if not any(item.get("id") == conflict_id for item in conflicts):
            raise ValueError("Conflict not found")
        if resolution not in {"use_candidate", "keep_release"}:
            raise ValueError("Unsupported conflict resolution")

        resolutions = self._load_dict(mr.resolutions_json)
        resolutions[conflict_id] = {
            "resolution": resolution,
            "operator": str(payload.get("operator") or "admin"),
            "comment": str(payload.get("comment") or ""),
            "resolved_at": now_utc().isoformat(),
        }
        mr.resolutions_json = self._dump(resolutions)
        mr.status = "pending" if self._all_conflicts_resolved(conflicts, resolutions) else "conflict"
        mr.updated_at = now_utc()
        self.db.add(mr)
        self._log(
            mr.id,
            "resolve_conflict",
            operator=str(payload.get("operator") or "admin"),
            role="admin",
            message=f"解决冲突 {conflict_id}：{self._resolution_label(resolution)}",
            detail={"conflict_id": conflict_id, "resolution": resolution, "comment": payload.get("comment") or ""},
        )
        self.db.commit()
        self.db.refresh(mr)
        return self.to_response(mr)

    def merge(self, merge_request_id: int, payload: dict[str, Any]) -> dict[str, Any] | None:
        self._ensure_tables()
        mr = self.db.get(MergeRequest, merge_request_id)
        if mr is None:
            return None
        if str(payload.get("role") or "") != "admin":
            raise ValueError("Only admin can merge into release branch")
        if mr.status in {"merged", "rejected"}:
            raise ValueError("Merge request is already closed")

        candidate = self._load_dict(mr.candidate_json)
        conflicts = self._load_list(mr.conflicts_json)
        resolutions = self._load_dict(mr.resolutions_json)
        unresolved = [item for item in conflicts if item.get("id") not in resolutions]
        if unresolved:
            raise ValueError("All conflicts must be resolved before merge")

        final_elements, final_relationships = self._apply_resolutions(candidate, conflicts, resolutions)
        commit_result = SysMLAdapter(self.db).commit_model(final_elements, final_relationships, status="released")

        draft = self.db.get(ModelDraft, mr.draft_id)
        if draft is not None:
            draft.status = "accepted"
            draft.updated_at = now_utc()
            self.db.add(draft)

        mr.status = "merged"
        mr.reviewer = str(payload.get("operator") or "admin")
        mr.merged_at = now_utc()
        mr.updated_at = now_utc()
        mr.commit_result_json = self._dump(commit_result)
        self.db.add(mr)
        self._log(
            mr.id,
            "merge",
            operator=mr.reviewer,
            role="admin",
            message="合并入库完成，候选模型元素已转正为发布分支权威图谱元素",
            detail={
                "elements_released": len(final_elements),
                "relationships_released": len(final_relationships),
                "comment": payload.get("comment") or "",
            },
        )
        self.db.commit()
        self.db.refresh(mr)
        return {"merge_request": self.to_response(mr), "commit_result": commit_result}

    def reject(self, merge_request_id: int, payload: dict[str, Any]) -> dict[str, Any] | None:
        self._ensure_tables()
        mr = self.db.get(MergeRequest, merge_request_id)
        if mr is None:
            return None
        if str(payload.get("role") or "") != "admin":
            raise ValueError("Only admin can reject merge requests")
        if mr.status == "merged":
            raise ValueError("Merged request cannot be rejected")
        mr.status = "rejected"
        mr.reviewer = str(payload.get("operator") or "admin")
        mr.updated_at = now_utc()
        self.db.add(mr)
        self._log(
            mr.id,
            "reject",
            operator=mr.reviewer,
            role="admin",
            message="管理员拒绝合并请求",
            detail={"comment": payload.get("comment") or ""},
        )
        self.db.commit()
        self.db.refresh(mr)
        return self.to_response(mr)

    def to_response(self, mr: MergeRequest) -> dict[str, Any]:
        conflicts = self._load_list(mr.conflicts_json)
        resolutions = self._load_dict(mr.resolutions_json)
        resolved_conflicts = []
        for item in conflicts:
            conflict = dict(item)
            conflict["resolved"] = conflict.get("id") in resolutions
            conflict["resolution"] = resolutions.get(conflict.get("id"))
            resolved_conflicts.append(conflict)

        logs = [
            {
                "id": item.id,
                "action": item.action,
                "operator": item.operator,
                "role": item.role,
                "message": item.message,
                "detail": self._load_dict(item.detail_json),
                "created_at": item.created_at,
            }
            for item in self.db.query(MergeAuditLog).filter(MergeAuditLog.merge_request_id == mr.id).order_by(MergeAuditLog.created_at.asc(), MergeAuditLog.id.asc()).all()
        ]
        return {
            "id": mr.id,
            "draft_id": mr.draft_id,
            "project_name": mr.project_name,
            "source_branch": mr.source_branch,
            "target_branch": mr.target_branch,
            "title": mr.title,
            "description": mr.description,
            "submitter": mr.submitter,
            "reviewer": mr.reviewer,
            "status": mr.status,
            "change_set": self._load_dict(mr.change_set_json),
            "conflicts": resolved_conflicts,
            "resolutions": resolutions,
            "audit_logs": logs,
            "created_at": mr.created_at,
            "updated_at": mr.updated_at,
            "merged_at": mr.merged_at,
        }

    def _compare(self, candidate: dict[str, Any], release: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        release_elements = {item["id"]: item for item in release["elements"]}
        release_relationships = {item["id"]: item for item in release["relationships"]}
        release_names = {item["name"]: item for item in release["elements"] if item.get("name")}
        changes: dict[str, list[dict[str, Any]]] = {
            "elements_added": [],
            "elements_modified": [],
            "relationships_added": [],
            "relationships_modified": [],
        }
        conflicts: list[dict[str, Any]] = []

        for element in candidate["elements"]:
            existing = release_elements.get(element["id"])
            name_match = release_names.get(element.get("name", ""))
            if existing is None:
                changes["elements_added"].append(self._change_row("element", "add", element, None, element))
                if name_match and name_match["id"] != element["id"]:
                    conflicts.append(
                        self._conflict(
                            "name_collision",
                            "element",
                            element["id"],
                            "name",
                            name_match.get("name"),
                            element.get("name"),
                            f"发布分支已有同名元素 {name_match['id']}，候选分支新增元素 {element['id']} 使用相同名称。",
                        )
                    )
                continue
            diff = self._field_diff(existing, element, ["name", "type", "description", "source_requirement"])
            if diff:
                changes["elements_modified"].append(self._change_row("element", "modify", element, existing, element, diff))
                for field, values in diff.items():
                    if field not in ELEMENT_CONFLICT_FIELDS:
                        continue
                    conflicts.append(
                        self._conflict(
                            "field_conflict",
                            "element",
                            element["id"],
                            field,
                            values["release"],
                            values["candidate"],
                            f"元素 {element['id']} 的 {field} 在发布分支和开发分支不一致。",
                        )
                    )

        for relationship in candidate["relationships"]:
            existing = release_relationships.get(relationship["id"])
            if existing is None:
                changes["relationships_added"].append(self._change_row("relationship", "add", relationship, None, relationship))
                continue
            diff = self._field_diff(existing, relationship, ["source", "target", "type", "description"])
            if diff:
                changes["relationships_modified"].append(self._change_row("relationship", "modify", relationship, existing, relationship, diff))
                for field, values in diff.items():
                    if field not in RELATIONSHIP_CONFLICT_FIELDS:
                        continue
                    conflicts.append(
                        self._conflict(
                            "relationship_conflict",
                            "relationship",
                            relationship["id"],
                            field,
                            values["release"],
                            values["candidate"],
                            f"关系 {relationship['id']} 的 {field} 在发布分支和开发分支不一致。",
                        )
                    )

        changes["summary"] = {
            "elements_added": len(changes["elements_added"]),
            "elements_modified": len(changes["elements_modified"]),
            "relationships_added": len(changes["relationships_added"]),
            "relationships_modified": len(changes["relationships_modified"]),
            "conflicts": len(conflicts),
        }
        return changes, conflicts

    def _apply_resolutions(
        self,
        candidate: dict[str, Any],
        conflicts: list[dict[str, Any]],
        resolutions: dict[str, Any],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        keep_release_objects = {
            (item.get("object_type"), item.get("object_id"))
            for item in conflicts
            if resolutions.get(item.get("id"), {}).get("resolution") == "keep_release"
        }
        elements = [
            {**item, "status": "released"}
            for item in candidate.get("elements") or []
            if ("element", item.get("id")) not in keep_release_objects
        ]
        element_ids = {item.get("id") for item in elements}
        release_ids = {item.id for item in self.db.query(SysMLElement).all()}
        available_ids = element_ids | release_ids
        relationships = [
            dict(item)
            for item in candidate.get("relationships") or []
            if ("relationship", item.get("id")) not in keep_release_objects
            and item.get("source") in available_ids
            and item.get("target") in available_ids
        ]
        return elements, relationships

    def _release_snapshot(self) -> dict[str, Any]:
        return {
            "elements": [
                {
                    "id": item.id,
                    "name": item.name,
                    "type": item.type,
                    "description": item.description,
                    "source_requirement": item.source_requirement,
                    "status": item.status,
                    "external_id": item.external_id,
                }
                for item in self.db.query(SysMLElement).order_by(SysMLElement.id.asc()).all()
            ],
            "relationships": [
                {
                    "id": item.id,
                    "source": item.source,
                    "target": item.target,
                    "type": item.type,
                    "description": item.description,
                }
                for item in self.db.query(SysMLRelationship).order_by(SysMLRelationship.id.asc()).all()
            ],
        }

    def _normalize_candidate(self, payload: dict[str, Any], draft: ModelDraft) -> dict[str, Any]:
        return {
            "project_name": str(payload.get("project_name") or draft.project_name),
            "elements": [self._normalize_element(item) for item in payload.get("elements") or []],
            "relationships": [self._normalize_relationship(item) for item in payload.get("relationships") or []],
        }

    def _normalize_element(self, item: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": str(item.get("id") or ""),
            "name": str(item.get("name") or item.get("id") or ""),
            "type": str(item.get("type") or "Block"),
            "description": str(item.get("description") or ""),
            "package": item.get("package"),
            "source_requirement": item.get("source_requirement"),
            "status": str(item.get("status") or "candidate"),
            "attributes": item.get("attributes") or [],
        }

    def _normalize_relationship(self, item: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": str(item.get("id") or ""),
            "source": str(item.get("source") or ""),
            "target": str(item.get("target") or ""),
            "type": str(item.get("type") or "trace"),
            "description": str(item.get("description") or ""),
        }

    def _field_diff(self, release: dict[str, Any], candidate: dict[str, Any], fields: list[str]) -> dict[str, dict[str, Any]]:
        diff: dict[str, dict[str, Any]] = {}
        for field in fields:
            release_value = release.get(field) or ""
            candidate_value = candidate.get(field) or ""
            if release_value != candidate_value:
                diff[field] = {"release": release_value, "candidate": candidate_value}
        return diff

    def _change_row(
        self,
        object_type: str,
        action: str,
        item: dict[str, Any],
        release: dict[str, Any] | None,
        candidate: dict[str, Any] | None,
        diff: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "id": item.get("id"),
            "object_type": object_type,
            "action": action,
            "name": item.get("name") or item.get("description") or item.get("id"),
            "release": release,
            "candidate": candidate,
            "diff": diff or {},
        }

    def _conflict(
        self,
        conflict_type: str,
        object_type: str,
        object_id: str,
        field: str,
        release_value: Any,
        candidate_value: Any,
        message: str,
    ) -> dict[str, Any]:
        return {
            "id": f"CONFLICT-{object_type}-{object_id}-{field}",
            "type": conflict_type,
            "object_type": object_type,
            "object_id": object_id,
            "field": field,
            "release_value": release_value,
            "candidate_value": candidate_value,
            "message": message,
            "severity": "warning" if conflict_type == "name_collision" else "high",
        }

    def _all_conflicts_resolved(self, conflicts: list[dict[str, Any]], resolutions: dict[str, Any]) -> bool:
        return all(item.get("id") in resolutions for item in conflicts)

    def _log(self, merge_request_id: int, action: str, operator: str, role: str, message: str, detail: dict[str, Any]) -> None:
        self.db.add(
            MergeAuditLog(
                merge_request_id=merge_request_id,
                action=action,
                operator=operator,
                role=role,
                message=message,
                detail_json=self._dump(detail),
            )
        )

    def _ensure_tables(self) -> None:
        bind = self.db.get_bind()
        MergeRequest.__table__.create(bind=bind, checkfirst=True)
        MergeAuditLog.__table__.create(bind=bind, checkfirst=True)

    def _resolution_label(self, resolution: str) -> str:
        return "采用开发分支版本" if resolution == "use_candidate" else "保留发布分支版本"

    def _dump(self, payload: Any) -> str:
        return json.dumps(payload, ensure_ascii=False, default=self._json_default)

    def _load(self, value: str) -> dict[str, Any]:
        return self._load_dict(value)

    def _load_dict(self, value: str) -> dict[str, Any]:
        try:
            data = json.loads(value or "{}")
        except json.JSONDecodeError:
            data = {}
        return data if isinstance(data, dict) else {}

    def _load_list(self, value: str) -> list[dict[str, Any]]:
        try:
            data = json.loads(value or "[]")
        except json.JSONDecodeError:
            data = []
        return [dict(item) for item in data] if isinstance(data, list) else []

    def _json_default(self, value: Any) -> str:
        if isinstance(value, datetime):
            return value.isoformat()
        return str(value)
