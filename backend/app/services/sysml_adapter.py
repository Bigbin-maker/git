from __future__ import annotations

from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import SysMLElement, SysMLRelationship


class SysMLAdapter:
    _cached_project_id: str | None = None
    _cached_project_name: str | None = None

    def __init__(self, db: Session) -> None:
        self.db = db
        self.settings = get_settings()
        self._fallback_reason = ""
        self._real_api_available: bool | None = None

    def health_check(self) -> dict:
        if not self.settings.sysml_enable_real_api:
            return {"mode": "mock", "available": True, "message": "真实 SysML API 未启用"}
        if self._check_real_api():
            return {
                "mode": "real",
                "available": True,
                "message": "SysML v2 REST API 已连接，项目接口 /projects 可用",
            }
        return {"mode": "mock", "available": True, "message": f"SysML API 不可用，使用 Mock：{self._fallback_reason}"}

    def commit_model(self, elements: list[dict], relationships: list[dict], status: str = "committed") -> dict:
        if self._check_real_api():
            try:
                project = self._ensure_project()
                commit = self._create_commit(project["@id"], elements)
                saved_elements = self._save_elements_after_commit(elements, project, commit, status=status)
                saved_relationships = [self._relationship_to_dict(self._upsert_relationship(item)) for item in relationships]
                return {
                    "mode": "real",
                    "message": (
                        f"已通过 SysML v2 API 创建提交，Project={project['@id']}，"
                        f"Commit={commit.get('@id', 'unknown')}；追溯关系已本地保存"
                    ),
                    "elements": saved_elements,
                    "relationships": saved_relationships,
                    "project": project,
                    "commit": commit,
                }
            except Exception as exc:
                self._fallback_reason = str(exc)
                self._real_api_available = False

        saved_elements = [
            self._element_to_dict(self._upsert_element({**item, "status": status})) for item in elements
        ]
        saved_relationships = [self._relationship_to_dict(self._upsert_relationship(item)) for item in relationships]
        return {
            "mode": "mock",
            "message": f"SysML API 调用失败或未启用，已切换为 Mock 模式，本地保存成功：{self._fallback_reason}",
            "elements": saved_elements,
            "relationships": saved_relationships,
        }

    def create_element(self, element: dict) -> dict:
        result = self.commit_model([element], [])
        return {"mode": result["mode"], "element": result["elements"][0]}

    def create_relationship(self, relationship: dict) -> dict:
        saved = self._upsert_relationship(relationship)
        return {"mode": "mock", "relationship": self._relationship_to_dict(saved)}

    def get_elements(self) -> list[dict]:
        return [self._element_to_dict(item) for item in self.db.query(SysMLElement).order_by(SysMLElement.id).all()]

    def get_graph(self) -> dict:
        nodes = [
            {
                "id": item.id,
                "label": item.name,
                "type": item.type,
                "status": item.status,
                "source_requirement": item.source_requirement,
            }
            for item in self.db.query(SysMLElement).order_by(SysMLElement.id).all()
        ]
        edges = [
            {
                "id": item.id,
                "source": item.source,
                "target": item.target,
                "type": item.type,
                "label": item.type,
                "description": item.description,
            }
            for item in self.db.query(SysMLRelationship).order_by(SysMLRelationship.id).all()
        ]
        return {"nodes": nodes, "edges": edges}

    def fallback_reason(self) -> str:
        return self._fallback_reason

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.settings.sysml_api_token:
            headers["Authorization"] = f"Bearer {self.settings.sysml_api_token}"
        return headers

    def _check_real_api(self) -> bool:
        if not self.settings.sysml_enable_real_api:
            return False
        if self._real_api_available is not None:
            return self._real_api_available
        try:
            response = httpx.get(
                f"{self._base_url()}/projects",
                headers=self._headers(),
                timeout=8,
            )
            response.raise_for_status()
            self._real_api_available = isinstance(response.json(), list)
        except Exception as exc:
            self._fallback_reason = str(exc)
            self._real_api_available = False
        return self._real_api_available

    def _ensure_project(self) -> dict[str, Any]:
        configured_project_id = self.settings.sysml_project_id.strip()
        if configured_project_id:
            project = self._get_project(configured_project_id)
            SysMLAdapter._cached_project_id = project["@id"]
            SysMLAdapter._cached_project_name = project.get("name")
            return project

        if SysMLAdapter._cached_project_id:
            return {
                "@id": SysMLAdapter._cached_project_id,
                "name": SysMLAdapter._cached_project_name or self.settings.sysml_project_name,
            }

        project_name = self.settings.sysml_project_name.strip() or "AI-MBSE-Demo"
        project = self._find_project_by_name(project_name)
        if project is None:
            project = self._create_project(project_name)
        SysMLAdapter._cached_project_id = project["@id"]
        SysMLAdapter._cached_project_name = project.get("name")
        return project

    def _find_project_by_name(self, project_name: str) -> dict[str, Any] | None:
        response = httpx.get(f"{self._base_url()}/projects", headers=self._headers(), timeout=8)
        response.raise_for_status()
        for project in response.json():
            if project.get("name") == project_name or project_name in project.get("alias", []):
                return project
        return None

    def _get_project(self, project_id: str) -> dict[str, Any]:
        response = httpx.get(f"{self._base_url()}/projects/{project_id}", headers=self._headers(), timeout=8)
        response.raise_for_status()
        return response.json()

    def _create_project(self, project_name: str) -> dict[str, Any]:
        payload = {
            "@type": "Project",
            "name": project_name,
            "description": "AI-MBSE-Demo generated project for local MBSE demonstration.",
        }
        response = httpx.post(f"{self._base_url()}/projects", headers=self._headers(), json=payload, timeout=15)
        response.raise_for_status()
        return response.json()

    def _create_commit(self, project_id: str, elements: list[dict]) -> dict[str, Any]:
        commit_body = {
            "@type": "Commit",
            "change": [
                {
                    "@type": "DataVersion",
                    "payload": self._to_sysml_payload(element),
                }
                for element in elements
                if element.get("name")
            ],
        }
        if not commit_body["change"]:
            return {"@id": "no-op", "change": []}
        response = httpx.post(
            f"{self._base_url()}/projects/{project_id}/commits",
            headers=self._headers(),
            json=commit_body,
            timeout=20,
        )
        response.raise_for_status()
        return response.json()

    def _to_sysml_payload(self, element: dict[str, Any]) -> dict[str, Any]:
        type_map = {
            "Requirement": "RequirementDefinition",
            "Block": "PartDefinition",
            "UseCase": "UseCaseDefinition",
            "Interface": "InterfaceDefinition",
            "Activity": "ActionDefinition",
        }
        return {
            "@type": type_map.get(element.get("type"), "PartDefinition"),
            "name": self._safe_sysml_name(element.get("name") or element.get("id") or "UnnamedElement"),
        }

    def _save_elements_after_commit(self, elements: list[dict], project: dict, commit: dict, status: str = "committed") -> list[dict]:
        external_ids = self._extract_external_ids(commit, len(elements))
        remote_elements = self._fetch_commit_elements(project["@id"], commit.get("@id"))
        saved: list[dict] = []
        for index, element in enumerate(elements):
            fallback_id = f"{project['@id']}:{commit.get('@id', 'unknown')}:{element['id']}"
            external_id = (
                self._match_remote_element_id(element, remote_elements)
                or (external_ids[index] if index < len(external_ids) and external_ids[index] else None)
                or fallback_id
            )
            saved.append(
                self._element_to_dict(
                    self._upsert_element({**element, "external_id": external_id, "status": status})
                )
            )
        return saved

    def _extract_external_ids(self, commit: dict[str, Any], expected_count: int) -> list[str | None]:
        changes = commit.get("change") or []
        external_ids: list[str | None] = []
        for change in changes[:expected_count]:
            identity = change.get("identity") or {}
            payload = change.get("payload") or {}
            external_ids.append(identity.get("@id") or payload.get("@id") or change.get("@id"))
        return external_ids

    def _fetch_commit_elements(self, project_id: str, commit_id: str | None) -> list[dict[str, Any]]:
        if not commit_id or commit_id == "no-op":
            return []
        try:
            response = httpx.get(
                f"{self._base_url()}/projects/{project_id}/commits/{commit_id}/elements",
                headers=self._headers(),
                timeout=20,
            )
            response.raise_for_status()
            data = response.json()
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def _match_remote_element_id(self, element: dict[str, Any], remote_elements: list[dict[str, Any]]) -> str | None:
        expected_name = self._safe_sysml_name(element.get("name") or element.get("id") or "UnnamedElement")
        expected_type = self._to_sysml_payload(element)["@type"]
        for remote in remote_elements:
            if remote.get("name") == expected_name and remote.get("@type") == expected_type:
                return remote.get("@id") or remote.get("elementId")
        for remote in remote_elements:
            if remote.get("name") == expected_name:
                return remote.get("@id") or remote.get("elementId")
        return None

    def _safe_sysml_name(self, name: str) -> str:
        cleaned = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in name.strip())
        if not cleaned:
            return "UnnamedElement"
        if cleaned[0].isdigit():
            cleaned = f"Element_{cleaned}"
        return cleaned

    def _base_url(self) -> str:
        return self.settings.sysml_api_base_url.rstrip("/")

    def _upsert_element(self, element: dict[str, Any]) -> SysMLElement:
        item = self.db.get(SysMLElement, element["id"])
        if item is None:
            item = SysMLElement(id=element["id"])
        item.name = element.get("name", "")
        item.type = element.get("type", "")
        item.description = element.get("description", "")
        item.source_requirement = element.get("source_requirement")
        item.status = element.get("status", "committed")
        item.external_id = element.get("external_id")
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        return item

    def _upsert_relationship(self, relationship: dict[str, Any]) -> SysMLRelationship:
        item = self.db.get(SysMLRelationship, relationship["id"])
        if item is None:
            item = SysMLRelationship(id=relationship["id"])
        item.source = relationship.get("source", "")
        item.target = relationship.get("target", "")
        item.type = relationship.get("type", "")
        item.description = relationship.get("description", "")
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        return item

    def _element_to_dict(self, item: SysMLElement) -> dict[str, Any]:
        return {
            "id": item.id,
            "name": item.name,
            "type": item.type,
            "description": item.description,
            "source_requirement": item.source_requirement,
            "status": item.status,
            "external_id": item.external_id,
        }

    def _relationship_to_dict(self, item: SysMLRelationship) -> dict[str, Any]:
        return {
            "id": item.id,
            "source": item.source,
            "target": item.target,
            "type": item.type,
            "description": item.description,
        }
