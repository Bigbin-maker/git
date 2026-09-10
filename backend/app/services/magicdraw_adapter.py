from __future__ import annotations

import csv
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

from app.config import get_settings


class MagicDrawAdapter:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._fallback_reason = ""
        self._bridge_available: bool | None = None
        self._bridge_status: dict[str, Any] | None = None

    def health_check(self) -> dict[str, Any]:
        if not self.settings.magicdraw_enable_bridge:
            return {
                "mode": "exchange",
                "available": True,
                "bridge_available": False,
                "project_open": None,
                "project_name": "",
                "project_path_configured": bool(self.settings.magicdraw_project_path),
                "last_import": {},
                "bridge_response": None,
                "message": "MagicDraw 桥接未启用，将生成本地交换包",
            }
        if self._check_bridge():
            project_open = self._bridge_project_open()
            project_path_configured = bool(self.settings.magicdraw_project_path)
            if project_open is False and not project_path_configured:
                message = "MagicDraw Bridge 已连接，未检测到已打开工程；推送时将直接调用导入接口"
            elif project_open is False and project_path_configured:
                message = "MagicDraw Bridge 已连接，将使用配置的工程路径打开工程"
            else:
                message = "MagicDraw Bridge 已连接"
            return {
                "mode": "bridge",
                "available": True,
                "bridge_available": True,
                "project_open": project_open,
                "project_name": self._bridge_project_name(),
                "project_path_configured": project_path_configured,
                "last_import": self._bridge_last_import(),
                "bridge_response": self._bridge_status or {},
                "message": message,
            }
        return {
            "mode": "exchange",
            "available": True,
            "bridge_available": False,
            "project_open": None,
            "project_name": "",
            "project_path_configured": bool(self.settings.magicdraw_project_path),
            "last_import": {},
            "bridge_response": self._bridge_status,
            "message": f"MagicDraw Bridge 不可用，将生成本地交换包：{self._fallback_reason}",
        }

    def publish_model(
        self,
        elements: list[dict[str, Any]],
        relationships: list[dict[str, Any]],
        package_name: str | None = None,
        diagram_views: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        package = self._safe_name(package_name or self.settings.magicdraw_package_name or "AI_MBSE_Demo")
        payload = self._build_exchange_payload(elements, relationships, package, diagram_views or [])
        files = self._write_exchange_package(payload)

        if self._check_bridge():
            try:
                response = httpx.post(
                    f"{self._base_url()}/models/import",
                    json=payload,
                    timeout=self.settings.magicdraw_import_timeout_sec,
                )
                response.raise_for_status()
                return {
                    "mode": "bridge",
                    "available": True,
                    "message": "已通过 MagicDraw Bridge 推送模型，同时生成本地交换包",
                    "package_name": package,
                    "exchange_payload": payload,
                    "files": files,
                    "bridge_response": self._safe_json(response),
                }
            except httpx.TimeoutException:
                self._fallback_reason = f"MagicDraw Bridge 导入超过 {self.settings.magicdraw_import_timeout_sec} 秒未返回"
                self._bridge_available = False
            except Exception as exc:
                self._fallback_reason = str(exc)
                self._bridge_available = False

        fallback_detail = f"：{self._fallback_reason}" if self._fallback_reason else ""
        return {
            "mode": "exchange",
            "available": True,
            "message": f"MagicDraw Bridge 未完成导入，已生成本地 MagicDraw 交换包{fallback_detail}",
            "package_name": package,
            "exchange_payload": payload,
            "files": files,
            "bridge_response": None,
        }

    def latest_diagram_catalog(self) -> dict[str, Any]:
        export_root = Path(self.settings.magicdraw_export_dir)
        if not export_root.exists():
            return self._empty_diagram_catalog(f"MagicDraw 导出目录不存在：{export_root}")

        try:
            directories = sorted(
                (item for item in export_root.iterdir() if item.is_dir()),
                key=lambda item: item.stat().st_mtime,
                reverse=True,
            )
        except Exception as exc:
            return self._empty_diagram_catalog(f"读取 MagicDraw 导出目录失败：{exc}")

        for package_dir in directories:
            diagram_views_path = package_dir / "diagram_views.json"
            if not diagram_views_path.exists():
                continue
            diagram_views = self._read_json_file(diagram_views_path, [])
            if not isinstance(diagram_views, list) or not diagram_views:
                continue

            payload = self._read_json_file(package_dir / "magicdraw_exchange.json", {})
            payload = payload if isinstance(payload, dict) else {}
            elements = payload.get("elements") if isinstance(payload.get("elements"), list) else []
            relationships = payload.get("relationships") if isinstance(payload.get("relationships"), list) else []
            exported_at = str(payload.get("generated_at") or datetime.fromtimestamp(package_dir.stat().st_mtime).isoformat(timespec="seconds"))
            project_name = str(payload.get("root_package") or package_dir.name)
            return {
                "available": True,
                "message": "已读取最近一次 MagicDraw 图视图导出",
                "project_name": project_name,
                "source_directory": package_dir.name,
                "exported_at": exported_at,
                "element_count": len(elements),
                "relationship_count": len(relationships),
                "diagram_count": len(diagram_views),
                "diagram_views": diagram_views,
            }

        return self._empty_diagram_catalog("未找到包含 diagram_views.json 的 MagicDraw 导出包")

    def save_project(self) -> dict[str, Any]:
        if not self._check_bridge():
            return {
                "mode": "exchange",
                "available": False,
                "saved": False,
                "message": f"MagicDraw Bridge 不可用，无法保存工程：{self._fallback_reason}",
            }
        try:
            save_payload = {
                "project_path": self.settings.magicdraw_project_path,
                "save_dir": str((Path(self.settings.magicdraw_export_dir) / "saved-projects").resolve()),
            }
            response = httpx.post(f"{self._base_url()}/project/save", json=save_payload, timeout=60)
            response.raise_for_status()
            return {
                "mode": "bridge",
                "available": True,
                "message": "MagicDraw 工程保存请求已完成",
                "bridge_response": self._safe_json(response),
            }
        except Exception as exc:
            self._fallback_reason = str(exc)
            self._bridge_available = False
            return {
                "mode": "bridge",
                "available": False,
                "saved": False,
                "message": f"MagicDraw 工程保存失败：{exc}",
            }

    def _empty_diagram_catalog(self, message: str) -> dict[str, Any]:
        return {
            "available": False,
            "message": message,
            "project_name": "",
            "source_directory": "",
            "exported_at": "",
            "element_count": 0,
            "relationship_count": 0,
            "diagram_count": 0,
            "diagram_views": [],
        }

    def _read_json_file(self, path: Path, fallback: Any) -> Any:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return fallback

    def current_model(self) -> dict[str, Any]:
        if not self._check_bridge():
            return {
                "mode": "exchange",
                "available": False,
                "message": f"MagicDraw Bridge 不可用，无法读取当前模型：{self._fallback_reason}",
                "bridge_response": None,
            }
        try:
            response = httpx.get(f"{self._base_url()}/models/current", timeout=60)
            response.raise_for_status()
            return {
                "mode": "bridge",
                "available": True,
                "message": "已读取 MagicDraw 当前模型状态",
                "bridge_response": self._safe_json(response),
            }
        except Exception as exc:
            self._fallback_reason = str(exc)
            self._bridge_available = False
            return {
                "mode": "bridge",
                "available": False,
                "message": f"读取 MagicDraw 当前模型失败：{exc}",
                "bridge_response": None,
            }

    def _check_bridge(self) -> bool:
        if not self.settings.magicdraw_enable_bridge:
            return False
        if self._bridge_available is not None:
            return self._bridge_available
        try:
            response = httpx.get(f"{self._base_url()}/health", timeout=5)
            response.raise_for_status()
            self._bridge_status = self._safe_json(response)
            self._bridge_available = True
        except Exception as exc:
            self._fallback_reason = str(exc)
            self._bridge_status = None
            self._bridge_available = False
        return self._bridge_available

    def _bridge_project_open(self) -> bool | None:
        if not isinstance(self._bridge_status, dict):
            return None
        project_open = self._bridge_status.get("project_open")
        return project_open if isinstance(project_open, bool) else None

    def _bridge_project_name(self) -> str:
        if not isinstance(self._bridge_status, dict):
            return ""
        project_name = self._bridge_status.get("project_name")
        return str(project_name or "")

    def _bridge_last_import(self) -> dict[str, Any]:
        if not isinstance(self._bridge_status, dict):
            return {}
        last_import = self._bridge_status.get("last_import")
        return last_import if isinstance(last_import, dict) else {}

    def _build_exchange_payload(
        self,
        elements: list[dict[str, Any]],
        relationships: list[dict[str, Any]],
        package_name: str,
        diagram_views: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        elements, relationships = self._finalize_primary_model(elements, relationships, package_name)
        diagram_views = [dict(item) for item in (diagram_views or []) if isinstance(item, dict)]
        merged_elements = self._merge_diagram_elements(elements, diagram_views)
        element_map = {item.get("id"): item for item in merged_elements}
        merged_relationships = self._merge_diagram_relationships(relationships, diagram_views, element_map)
        normalized_elements = [self._element_to_magicdraw(item) for item in merged_elements]
        normalized_relationships = [
            self._relationship_to_magicdraw(item, element_map)
            for item in merged_relationships
            if item.get("source") in element_map and item.get("target") in element_map
        ]
        primary_element_map = {item.get("id"): item for item in elements}
        primary_elements = [self._element_to_magicdraw(item) for item in elements]
        primary_relationships = [
            self._relationship_to_magicdraw(item, primary_element_map)
            for item in relationships
            if item.get("source") in primary_element_map and item.get("target") in primary_element_map
        ]
        diagram_layout = self._build_diagram_layout(primary_elements, primary_relationships)
        return {
            "schema": "ai-mbse.magicdraw.exchange.v1",
            "generated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "project_path": self.settings.magicdraw_project_path,
            "root_package": package_name,
            "diagram_name": diagram_layout["diagram_name"],
            "instructions": [
                "Create or reuse root package.",
                "Create nested packages from each element or relationship package field when provided.",
                "Create SysML/UML elements by local_id and stereotype.",
                "Create relationships after all element ids are resolved.",
                "Use diagram_layout as the single source of truth for MagicDraw and frontend canvas placement.",
                "Create additional diagrams from diagram_views when present; each view layout is scoped to its own nodes.",
                "Store ai_mbse_id and source_requirement as tagged values when available.",
            ],
            "elements": normalized_elements,
            "relationships": normalized_relationships,
            "diagram_layout": diagram_layout,
            "diagram_views": self._normalize_diagram_views_for_exchange(diagram_views),
        }

    def _finalize_primary_model(
        self,
        elements: list[dict[str, Any]],
        relationships: list[dict[str, Any]],
        package_name: str,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        try:
            from app.services.model_generation_service import ModelGenerationService

            finalized = ModelGenerationService()._finalize_project(
                {
                    "project_name": package_name,
                    "elements": elements,
                    "relationships": relationships,
                },
                package_name,
            )
            return finalized.get("elements") or elements, finalized.get("relationships") or relationships
        except Exception:
            return elements, relationships

    def _merge_diagram_elements(self, elements: list[dict[str, Any]], diagram_views: list[dict[str, Any]]) -> list[dict[str, Any]]:
        merged: dict[str, dict[str, Any]] = {}
        for element in elements:
            element_id = str(element.get("id") or "")
            if element_id:
                merged[element_id] = dict(element)
        for view in diagram_views:
            for element in view.get("elements") or []:
                if not isinstance(element, dict):
                    continue
                element_id = str(element.get("id") or "")
                if element_id and element_id not in merged:
                    merged[element_id] = dict(element)
        return list(merged.values())

    def _merge_diagram_relationships(
        self,
        relationships: list[dict[str, Any]],
        diagram_views: list[dict[str, Any]],
        element_map: dict[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        merged: dict[str, dict[str, Any]] = {}
        for relationship in relationships:
            rel_id = str(relationship.get("id") or f"{relationship.get('source')}_{relationship.get('type')}_{relationship.get('target')}")
            if rel_id:
                merged[rel_id] = dict(relationship)
        for view in diagram_views:
            view_id = str(view.get("id") or view.get("name") or "VIEW")
            for relationship in view.get("relationships") or []:
                if not isinstance(relationship, dict):
                    continue
                rel_id = str(relationship.get("id") or f"{relationship.get('source')}_{relationship.get('type')}_{relationship.get('target')}")
                if not rel_id:
                    continue
                next_relationship = dict(relationship)
                if rel_id in merged:
                    previous = merged[rel_id]
                    same_semantics = (
                        str(previous.get("source") or "") == str(next_relationship.get("source") or "")
                        and str(previous.get("target") or "") == str(next_relationship.get("target") or "")
                        and str(previous.get("type") or "") == str(next_relationship.get("type") or "")
                    )
                    if same_semantics:
                        continue
                    rel_id = f"{view_id}-{rel_id}"
                    suffix = 2
                    base_rel_id = rel_id
                    while rel_id in merged:
                        rel_id = f"{base_rel_id}-{suffix}"
                        suffix += 1
                    next_relationship["id"] = rel_id
                merged[rel_id] = next_relationship
            usecase_names = {
                str(element.get("id")): str(element.get("name") or element.get("id"))
                for element in view.get("elements") or []
                if isinstance(element, dict) and element.get("type") == "UseCase"
            }
            element_names = {
                str(element.get("id")): str(element.get("name") or element.get("id"))
                for element in view.get("elements") or []
                if isinstance(element, dict)
            }
            for link in view.get("trace_links") or []:
                if not isinstance(link, dict):
                    continue
                source = str(link.get("usecase_id") or "")
                relation = str(link.get("relation") or "allocate")
                for target in link.get("element_ids") or []:
                    target_id = str(target or "")
                    if source not in element_map or target_id not in element_map:
                        continue
                    rel_id = f"DTRACE-{source}-{target_id}"
                    if rel_id in merged:
                        continue
                    description = str(link.get("description") or "")
                    if not description:
                        description = f"{usecase_names.get(source, source)} 追踪到 {element_names.get(target_id, target_id)}"
                    merged[rel_id] = {
                        "id": rel_id,
                        "source": source,
                        "target": target_id,
                        "type": relation,
                        "description": description,
                        "package": "06_Traceability",
                    }
        return list(merged.values())

    def _normalize_diagram_views_for_exchange(self, diagram_views: list[dict[str, Any]]) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for view in diagram_views:
            layout = dict(view.get("layout") or {})
            if not layout.get("diagram_name"):
                layout["diagram_name"] = view.get("name") or view.get("id") or "AI_MBSE_Diagram_View"
            diagram_type = view.get("diagram_type") or layout.get("diagram_type") or "class"
            layout["diagram_type"] = diagram_type
            normalized.append(
                {
                    "id": view.get("id"),
                    "name": view.get("name") or layout.get("diagram_name"),
                    "diagram_type": diagram_type,
                    "focus_element_id": view.get("focus_element_id") or "",
                    "variant_id": view.get("variant_id") or "BASELINE",
                    "variant_name": view.get("variant_name") or "基线方案",
                    "description": view.get("description") or "",
                    "element_ids": [item.get("id") for item in view.get("elements") or [] if isinstance(item, dict) and item.get("id")],
                    "relationship_ids": [item.get("id") for item in view.get("relationships") or [] if isinstance(item, dict) and item.get("id")],
                    "trace_links": view.get("trace_links") or [],
                    "layout": layout,
                }
            )
        return normalized

    def _build_diagram_layout(
        self,
        elements: list[dict[str, Any]],
        relationships: list[dict[str, Any]],
    ) -> dict[str, Any]:
        node_width = 220
        node_height = 72
        margin_x = 70
        margin_y = 80
        column_gap = 285
        row_gap = 118
        row_by_column: dict[int, int] = {}
        nodes: list[dict[str, Any]] = []
        order_hints = self._layout_order_hints(elements, relationships)
        sorted_elements = sorted(
            elements,
            key=lambda item: (
                self._layout_column(str(item.get("type") or "")),
                order_hints.get(str(item.get("local_id") or item.get("id") or item.get("name") or ""), 10**9),
                self._id_sort_key(str(item.get("local_id") or item.get("name") or "")),
            ),
        )
        for element in sorted_elements:
            element_type = str(element.get("type") or "Block")
            column = self._layout_column(element_type)
            row = row_by_column.get(column, 0)
            row_by_column[column] = row + 1
            x = margin_x + column * column_gap
            y = margin_y + row * row_gap
            local_id = str(element.get("local_id") or element.get("name") or "")
            name = str(element.get("name") or local_id or "UnnamedElement")
            label = f"{local_id} - {name}" if local_id and name and not name.startswith(f"{local_id} - ") else name
            nodes.append(
                {
                    "id": local_id,
                    "element_id": local_id,
                    "name": name,
                    "label": label,
                    "type": element_type,
                    "stereotype_label": self._layout_stereotype(element_type),
                    "shape": self._layout_shape(element_type),
                    "column": column,
                    "row": row,
                    "x": x,
                    "y": y,
                    "width": node_width,
                    "height": node_height,
                }
            )

        node_by_id = {node["id"]: node for node in nodes}
        edges: list[dict[str, Any]] = []
        for index, relationship in enumerate(relationships):
            source = node_by_id.get(str(relationship.get("source") or ""))
            target = node_by_id.get(str(relationship.get("target") or ""))
            if not source or not target:
                continue
            geometry = self._layout_edge_geometry(source, target, index)
            rel_id = str(relationship.get("local_id") or relationship.get("name") or f"REL-{index + 1:03d}")
            rel_type = str(relationship.get("type") or relationship.get("stereotype") or "trace")
            edges.append(
                {
                    "id": rel_id,
                    "relationship_id": rel_id,
                    "source": relationship.get("source"),
                    "target": relationship.get("target"),
                    "type": rel_type,
                    "label": rel_type,
                    "points": geometry["points"],
                    "label_x": geometry["label_x"],
                    "label_y": geometry["label_y"],
                }
            )

        max_column = max((int(node["column"]) for node in nodes), default=0)
        max_bottom = max((int(node["y"]) + int(node["height"]) for node in nodes), default=0)
        return {
            "schema": "ai-mbse.diagram-layout.v1",
            "diagram_name": "AI_MBSE_Trace_View",
            "layout_source": "backend",
            "width": max(1180, margin_x * 2 + max_column * column_gap + node_width),
            "height": max(520, max_bottom + margin_y),
            "nodes": nodes,
            "edges": edges,
        }

    def _layout_edge_geometry(self, source: dict[str, Any], target: dict[str, Any], index: int) -> dict[str, Any]:
        offset = (index % 7 - 3) * 6
        source_x = int(source["x"])
        source_y = int(source["y"])
        source_width = int(source["width"])
        source_height = int(source["height"])
        target_x = int(target["x"])
        target_y = int(target["y"])
        target_width = int(target["width"])
        target_height = int(target["height"])
        source_center_x = source_x + source_width // 2
        source_center_y = source_y + source_height // 2
        target_center_x = target_x + target_width // 2
        target_center_y = target_y + target_height // 2

        if abs(target_center_x - source_center_x) >= abs(target_center_y - source_center_y):
            if target_center_x >= source_center_x:
                start_x = source_x + source_width
                end_x = target_x
            else:
                start_x = source_x
                end_x = target_x + target_width
            start_y = source_center_y + offset
            end_y = target_center_y - offset
            mid_x = int((start_x + end_x) / 2)
            points = [
                {"x": start_x, "y": start_y},
                {"x": mid_x, "y": start_y},
                {"x": mid_x, "y": end_y},
                {"x": end_x, "y": end_y},
            ]
            label_x = mid_x
            label_y = int((start_y + end_y) / 2) - 6
        else:
            if target_center_y >= source_center_y:
                start_y = source_y + source_height
                end_y = target_y
            else:
                start_y = source_y
                end_y = target_y + target_height
            start_x = source_center_x + offset
            end_x = target_center_x - offset
            mid_y = int((start_y + end_y) / 2)
            points = [
                {"x": start_x, "y": start_y},
                {"x": start_x, "y": mid_y},
                {"x": end_x, "y": mid_y},
                {"x": end_x, "y": end_y},
            ]
            label_x = int((start_x + end_x) / 2)
            label_y = mid_y - 6
        return {
            "points": points,
            "label_x": label_x,
            "label_y": label_y,
        }

    def _layout_column(self, element_type: str) -> int:
        if element_type == "Requirement":
            return 0
        if element_type == "Block":
            return 1
        if element_type == "UseCase":
            return 2
        if element_type == "Activity":
            return 3
        if element_type == "Interface":
            return 4
        if element_type == "ConstraintBlock":
            return 4
        return 1

    def _layout_order_hints(
        self,
        elements: list[dict[str, Any]],
        relationships: list[dict[str, Any]],
    ) -> dict[str, int]:
        hints: dict[str, list[int]] = {}
        for index, relationship in enumerate(relationships):
            for endpoint in (relationship.get("source"), relationship.get("target")):
                endpoint_id = str(endpoint or "")
                if endpoint_id:
                    hints.setdefault(endpoint_id, []).append(index)
        ordered: dict[str, int] = {}
        for element in elements:
            local_id = str(element.get("local_id") or element.get("id") or element.get("name") or "")
            values = hints.get(local_id)
            if values:
                ordered[local_id] = min(values)
        return ordered

    def _layout_shape(self, element_type: str) -> str:
        if element_type == "Actor":
            return "actor"
        if element_type == "UseCase":
            return "ellipse"
        if element_type == "Interface":
            return "soft"
        return "rect"

    def _layout_stereotype(self, element_type: str) -> str:
        mapping = {
            "Actor": "«actor»",
            "Activity": "«activity»",
            "Block": "«block»",
            "Requirement": "«requirement»",
            "UseCase": "«use case»",
            "Interface": "«interface»",
            "ConstraintBlock": "«constraint»",
        }
        return mapping.get(element_type, "«element»")

    def _id_sort_key(self, value: str) -> tuple[str, int, str]:
        match = re.match(r"^([A-Za-z]+)-(\d+)", value or "")
        if not match:
            return value or "", 10**9, value or ""
        return match.group(1), int(match.group(2)), value

    def _element_to_magicdraw(self, element: dict[str, Any]) -> dict[str, Any]:
        element_type = element.get("type") or "Block"
        mapping = {
            "Actor": {"metaclass": "Actor", "stereotype": ""},
            "Requirement": {"metaclass": "Class", "stereotype": "SysML::Requirements::Requirement"},
            "Block": {"metaclass": "Class", "stereotype": "SysML::Blocks::Block"},
            "UseCase": {"metaclass": "UseCase", "stereotype": ""},
            "Interface": {"metaclass": "Interface", "stereotype": "SysML::PortsAndFlows::InterfaceBlock"},
            "Activity": {"metaclass": "Activity", "stereotype": ""},
            "ConstraintBlock": {"metaclass": "Class", "stereotype": "SysML::ConstraintBlocks::ConstraintBlock"},
        }
        mapped = mapping.get(element_type, mapping["Block"])
        return {
            "local_id": element.get("id"),
            "name": element.get("name") or element.get("id") or "UnnamedElement",
            "type": element_type,
            "package": element.get("package") or self._default_element_package(element_type),
            "metaclass": mapped["metaclass"],
            "stereotype": mapped["stereotype"],
            "documentation": element.get("description", ""),
            "source_requirement": element.get("source_requirement"),
            "status": element.get("status", "candidate"),
            "tags": {
                "ai_mbse_id": element.get("id"),
                "external_id": element.get("external_id"),
                "package": element.get("package") or self._default_element_package(element_type),
            },
        }

    def _default_element_package(self, element_type: str) -> str:
        return {
            "Actor": "00_Actors",
            "Requirement": "01_Requirements",
            "Block": "02_Structure",
            "UseCase": "03_Behavior",
            "Activity": "03_Behavior",
            "Interface": "04_Interfaces",
            "ConstraintBlock": "05_Constraints",
        }.get(element_type, "06_Traceability")

    def _relationship_to_magicdraw(
        self,
        relationship: dict[str, Any],
        element_map: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        rel_type = relationship.get("type") or "trace"
        mapping = {
            "trace": "SysML::Requirements::Trace",
            "deriveReqt": "SysML::Requirements::DeriveReqt",
            "derivereqt": "SysML::Requirements::DeriveReqt",
            "satisfy": "SysML::Requirements::Satisfy",
            "verify": "SysML::Requirements::Verify",
            "refine": "SysML::Requirements::Refine",
            "allocate": "SysML::Allocations::Allocate",
            "realize": "Dependency",
            "connector": "Dependency",
            "association": "Dependency",
            "include": "Dependency",
            "extend": "Dependency",
            "controlflow": "Dependency",
            "objectflow": "Dependency",
            "message": "Dependency",
            "transition": "Dependency",
            "contains": "CompositeAssociation",
            "constrains": "Dependency",
            "drives": "Dependency",
            "dependency": "Dependency",
        }
        source = relationship.get("source")
        target = relationship.get("target")
        return {
            "local_id": relationship.get("id"),
            "name": relationship.get("id") or f"{source}_{rel_type}_{target}",
            "type": rel_type,
            "package": relationship.get("package") or "06_Traceability",
            "metaclass": "Dependency" if rel_type not in {"contains"} else "Association",
            "stereotype": mapping.get(rel_type, "SysML::Requirements::Trace"),
            "source": source,
            "source_name": element_map[source].get("name"),
            "target": target,
            "target_name": element_map[target].get("name"),
            "documentation": relationship.get("description", ""),
        }

    def _write_exchange_package(self, payload: dict[str, Any]) -> dict[str, str]:
        export_root = Path(self.settings.magicdraw_export_dir)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        package_dir = export_root / f"{payload['root_package']}_{stamp}"
        package_dir.mkdir(parents=True, exist_ok=True)

        payload_path = package_dir / "magicdraw_exchange.json"
        layout_path = package_dir / "diagram_layout.json"
        diagram_views_path = package_dir / "diagram_views.json"
        manifest_path = package_dir / "import_manifest.json"
        elements_path = package_dir / "elements.csv"
        relationships_path = package_dir / "relationships.csv"
        readme_path = package_dir / "README.md"

        payload_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        layout_path.write_text(json.dumps(payload.get("diagram_layout", {}), ensure_ascii=False, indent=2), encoding="utf-8")
        diagram_views_path.write_text(json.dumps(payload.get("diagram_views", []), ensure_ascii=False, indent=2), encoding="utf-8")
        manifest_path.write_text(
            json.dumps(
                {
                    "schema": payload["schema"],
                    "root_package": payload["root_package"],
                    "project_path": payload["project_path"],
                    "payload": payload_path.name,
                    "diagram_layout": layout_path.name,
                    "diagram_views": diagram_views_path.name,
                    "elements": elements_path.name,
                    "relationships": relationships_path.name,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        self._write_csv(elements_path, payload["elements"])
        self._write_csv(relationships_path, payload["relationships"])
        readme_path.write_text(self._readme(payload), encoding="utf-8")

        return {
            "directory": str(package_dir),
            "payload": str(payload_path),
            "diagram_layout": str(layout_path),
            "diagram_views": str(diagram_views_path),
            "manifest": str(manifest_path),
            "elements_csv": str(elements_path),
            "relationships_csv": str(relationships_path),
            "readme": str(readme_path),
        }

    def _write_csv(self, path: Path, rows: list[dict[str, Any]]) -> None:
        if not rows:
            path.write_text("", encoding="utf-8")
            return
        fieldnames = list(dict.fromkeys(key for row in rows for key in row.keys() if key != "tags"))
        with path.open("w", encoding="utf-8-sig", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow({key: row.get(key, "") for key in fieldnames})

    def _readme(self, payload: dict[str, Any]) -> str:
        return "\n".join(
            [
                "# MagicDraw Exchange Package",
                "",
                f"- Root package: `{payload['root_package']}`",
                f"- Element count: `{len(payload['elements'])}`",
                f"- Relationship count: `{len(payload['relationships'])}`",
                f"- Diagram layout: `{payload.get('diagram_layout', {}).get('diagram_name', 'AI_MBSE_Trace_View')}`",
                f"- Additional diagram views: `{len(payload.get('diagram_views', []))}`",
                "",
                "Use `magicdraw_exchange.json` as the primary payload for a MagicDraw/Cameo OpenAPI bridge plugin.",
                "`diagram_layout.json` is the shared canvas layout used by both MagicDraw Bridge and the frontend.",
                "`diagram_views.json` contains scoped use-case and internal block diagram layouts.",
                "`elements.csv` and `relationships.csv` are fallback review/import tables.",
                "",
                "Suggested bridge endpoint contract:",
                "",
                "- `GET /api/health` returns bridge status.",
                "- `POST /api/models/import` consumes this JSON payload and creates/reuses model elements in MagicDraw.",
            ]
        )

    def _safe_json(self, response: httpx.Response) -> dict[str, Any]:
        try:
            data = response.json()
            return data if isinstance(data, dict) else {"data": data}
        except Exception:
            return {"text": response.text}

    def _base_url(self) -> str:
        return self.settings.magicdraw_bridge_url.rstrip("/")

    def _safe_name(self, name: str) -> str:
        cleaned = re.sub(r"[^0-9A-Za-z_\u4e00-\u9fff]+", "_", name.strip())
        cleaned = cleaned.strip("_")
        return cleaned or "AI_MBSE_Demo"
