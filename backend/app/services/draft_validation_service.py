from __future__ import annotations

import json
import re
from copy import deepcopy
from typing import Any

from sqlalchemy.orm import Session

from app.models import ModelDraft, ModelFeedbackLog, now_utc
from app.services.model_generation_service import ModelGenerationService


class DraftValidationService:
    VALID_ELEMENT_TYPES = {"Requirement", "Block", "UseCase", "Activity", "Interface", "ConstraintBlock"}
    VALID_RELATIONSHIP_TYPES = {"contains", "satisfy", "trace", "refine", "allocate", "verify", "dependency"}

    METRIC_RULES = [
        ("发射功率", "PowerValue", "dBW", ["发射功率", "功率"]),
        ("带宽", "BandwidthValue", "MHz", ["带宽", "宽带"]),
        ("频率", "FrequencyValue", "GHz", ["频率", "频段"]),
        ("时延", "DurationValue", "ms", ["时延", "延迟"]),
        ("吞吐量", "DataRateValue", "Gbps", ["吞吐", "容量", "速率"]),
        ("轨道高度", "LengthValue", "km", ["轨道高度", "高度"]),
        ("轨道倾角", "AngleValue", "deg", ["倾角"]),
        ("可用性", "RatioValue", "%", ["可用性", "可靠性"]),
    ]

    def __init__(self, db: Session) -> None:
        self.db = db
        self.generator = ModelGenerationService()

    def validate(self, draft_id: int) -> dict[str, Any] | None:
        draft = self.db.get(ModelDraft, draft_id)
        if draft is None:
            return None
        return self._validate_payload(draft_id, self._load(draft.current_json), include_internal=False)

    def fix(self, draft_id: int, issue_ids: list[str], operator: str = "demo-user") -> dict[str, Any] | None:
        draft = self.db.get(ModelDraft, draft_id)
        if draft is None:
            return None
        if draft.status in {"accepted", "rejected"}:
            raise ValueError(f"Draft {draft.id} is {draft.status} and cannot be fixed")

        before = self._load(draft.current_json)
        payload = deepcopy(before)
        report = self._validate_payload(draft_id, payload, include_internal=True)
        fixable = [issue for issue in report["issues"] if issue.get("fixable")]
        selected_ids = set(issue_ids or [issue["id"] for issue in fixable])
        selected = [issue for issue in fixable if issue["id"] in selected_ids]
        if not selected:
            return {
                "draft": self._draft_response(draft, payload),
                "report": self._validate_payload(draft_id, payload, include_internal=False),
                "fixed_issue_ids": [],
            }

        fixed_ids: list[str] = []
        for issue in selected:
            changed = self._apply_fix(payload, issue)
            if changed:
                fixed_ids.append(issue["id"])

        payload["sysml_text"] = self.generator.render_project_text(
            payload.get("project_name") or draft.project_name,
            payload.get("elements") or [],
            payload.get("relationships") or [],
        )
        draft.current_json = self._dump(payload)
        draft.status = "revised"
        draft.updated_at = now_utc()
        self.db.add(draft)
        self.db.add(
            ModelFeedbackLog(
                draft_id=draft.id,
                action="fix",
                object_type="validation_report",
                object_id=",".join(fixed_ids),
                before_json=self._dump(before),
                after_json=self._dump(payload),
                operator=operator or "demo-user",
                comment=f"预评审一键修复 {len(fixed_ids)} 项问题",
            )
        )
        self.db.commit()
        self.db.refresh(draft)

        return {
            "draft": self._draft_response(draft, payload),
            "report": self._validate_payload(draft_id, payload, include_internal=False),
            "fixed_issue_ids": fixed_ids,
        }

    def _validate_payload(self, draft_id: int, payload: dict[str, Any], include_internal: bool) -> dict[str, Any]:
        elements = [dict(item) for item in payload.get("elements") or []]
        relationships = [dict(item) for item in payload.get("relationships") or []]
        element_ids = [str(item.get("id") or "") for item in elements]
        element_id_set = set(element_ids)
        element_map = {str(item.get("id") or ""): item for item in elements}
        by_type: dict[str, list[dict[str, Any]]] = {}
        for item in elements:
            by_type.setdefault(str(item.get("type") or ""), []).append(item)

        issues: list[dict[str, Any]] = []

        duplicate_ids = {item_id for item_id in element_ids if item_id and element_ids.count(item_id) > 1}
        for element_id in sorted(duplicate_ids):
            self._add_issue(
                issues,
                "error",
                "element.duplicate_id",
                "element",
                element_id,
                f"元素ID重复：{element_id}",
                "请人工调整重复元素ID，避免入库覆盖。",
                False,
            )

        for item in elements:
            element_id = str(item.get("id") or "")
            element_type = str(item.get("type") or "")
            name = str(item.get("name") or "")
            expected_package = self.generator._default_element_package(element_type)
            if not name.strip():
                self._add_issue(issues, "error", "element.empty_name", "element", element_id, "元素名称为空。", "请补充元素名称。", False)
            if element_type not in self.VALID_ELEMENT_TYPES:
                self._add_issue(
                    issues,
                    "warning",
                    "element.invalid_type",
                    "element",
                    element_id,
                    f"元素类型 {element_type or '空'} 不在规范类型集合内。",
                    "建议人工选择 Requirement / Block / UseCase / Activity / Interface / ConstraintBlock。",
                    False,
                )
            if element_type in self.VALID_ELEMENT_TYPES and item.get("package") != expected_package:
                self._add_issue(
                    issues,
                    "warning",
                    "element.package_mismatch",
                    "element",
                    element_id,
                    f"{element_id} 包路径与元素类型不匹配。",
                    f"建议移动到规范包路径 {expected_package}。",
                    True,
                    "normalize_package",
                    {"package": expected_package},
                    include_internal,
                )
            if str(item.get("status") or "") == "candidate":
                self._add_issue(
                    issues,
                    "info",
                    "element.candidate_status",
                    "element",
                    element_id,
                    f"{element_id} 仍处于候选状态。",
                    "建议在预评审后规范化为 reviewed。",
                    True,
                    "normalize_status",
                    {"status": "reviewed"},
                    include_internal,
                )
            self._check_attribute_rules(issues, item, include_internal)

        for rel in relationships:
            rel_id = str(rel.get("id") or "")
            source = str(rel.get("source") or "")
            target = str(rel.get("target") or "")
            rel_type = str(rel.get("type") or "")
            if source not in element_id_set or target not in element_id_set:
                self._add_issue(
                    issues,
                    "error",
                    "relationship.dangling_endpoint",
                    "relationship",
                    rel_id,
                    f"{rel_id} 引用了不存在的端点：{source} -> {target}。",
                    "建议删除该无效关系，或人工重新选择端点。",
                    True,
                    "delete_relationship",
                    {},
                    include_internal,
                )
            if rel_type not in self.VALID_RELATIONSHIP_TYPES:
                self._add_issue(
                    issues,
                    "warning",
                    "relationship.invalid_type",
                    "relationship",
                    rel_id,
                    f"{rel_id} 关系类型 {rel_type or '空'} 不符合规范。",
                    "建议规范化为 trace。",
                    True,
                    "normalize_relationship_type",
                    {"type": "trace"},
                    include_internal,
                )

        relation_tuples = [
            (str(rel.get("id") or ""), str(rel.get("source") or ""), str(rel.get("target") or ""), str(rel.get("type") or ""))
            for rel in relationships
        ]
        blocks = by_type.get("Block", [])
        requirements = by_type.get("Requirement", [])
        interfaces = by_type.get("Interface", [])
        constraints = by_type.get("ConstraintBlock", [])

        first_block = str(blocks[0].get("id")) if blocks else ""
        first_requirement = str(requirements[0].get("id")) if requirements else ""

        for req in requirements:
            req_id = str(req.get("id") or "")
            has_satisfy = any(rel_type == "satisfy" and target == req_id and element_map.get(source, {}).get("type") == "Block" for _, source, target, rel_type in relation_tuples)
            if not has_satisfy:
                self._add_issue(
                    issues,
                    "warning",
                    "rule.requirement_missing_satisfy",
                    "element",
                    req_id,
                    f"{req_id} 尚未被 Block satisfy。",
                    "建议新增 Block -> Requirement 的 satisfy 关系。",
                    bool(first_block),
                    "add_relationship",
                    {"source": first_block, "target": req_id, "type": "satisfy", "description": "预评审自动补充：模块满足需求"},
                    include_internal,
                )

        for interface in interfaces:
            interface_id = str(interface.get("id") or "")
            has_allocate = any(
                rel_type in {"allocate", "dependency"} and interface_id in {source, target} and (element_map.get(source, {}).get("type") == "Block" or element_map.get(target, {}).get("type") == "Block")
                for _, source, target, rel_type in relation_tuples
            )
            if not has_allocate:
                self._add_issue(
                    issues,
                    "warning",
                    "rule.interface_missing_allocate",
                    "element",
                    interface_id,
                    f"{interface_id} 尚未 allocate 到模块。",
                    "建议新增 Interface -> Block 的 allocate 关系。",
                    bool(first_block),
                    "add_relationship",
                    {"source": interface_id, "target": first_block, "type": "allocate", "description": "预评审自动补充：接口分配到模块"},
                    include_internal,
                )

        for constraint in constraints:
            constraint_id = str(constraint.get("id") or "")
            has_verify = any(rel_type == "verify" and source == constraint_id and target in {str(item.get("id")) for item in requirements} for _, source, target, rel_type in relation_tuples)
            if not has_verify:
                self._add_issue(
                    issues,
                    "warning",
                    "rule.constraint_missing_verify",
                    "element",
                    constraint_id,
                    f"{constraint_id} 尚未 verify 任何需求。",
                    "建议新增 ConstraintBlock -> Requirement 的 verify 关系。",
                    bool(first_requirement),
                    "add_relationship",
                    {"source": constraint_id, "target": first_requirement, "type": "verify", "description": "预评审自动补充：约束验证需求"},
                    include_internal,
                )

        expected_text = self.generator.render_project_text(payload.get("project_name") or "AI_MBSE_Project", elements, relationships)
        if payload.get("sysml_text") != expected_text:
            self._add_issue(
                issues,
                "info",
                "sysml.text_out_of_sync",
                "draft",
                str(draft_id),
                "SysML textual view 与当前结构化模型不完全同步。",
                "建议重新渲染 SysML textual view。",
                True,
                "rerender_sysml_text",
                {},
                include_internal,
            )

        statistics = {
            "element_count": len(elements),
            "relationship_count": len(relationships),
            "error_count": sum(1 for item in issues if item["severity"] == "error"),
            "warning_count": sum(1 for item in issues if item["severity"] == "warning"),
            "info_count": sum(1 for item in issues if item["severity"] == "info"),
            "fixable_count": sum(1 for item in issues if item.get("fixable")),
        }
        score = self._score(issues)
        return {
            "draft_id": draft_id,
            "score": score,
            "conclusion": self._conclusion(score, statistics),
            "issues": issues,
            "statistics": statistics,
        }

    def _check_attribute_rules(self, issues: list[dict[str, Any]], element: dict[str, Any], include_internal: bool) -> None:
        element_id = str(element.get("id") or "")
        attributes = [dict(item) for item in element.get("attributes") or []]
        for attribute in attributes:
            if not str(attribute.get("value_type") or "").strip():
                attr_name = str(attribute.get("name") or "属性")
                self._add_issue(
                    issues,
                    "warning",
                    "attribute.untyped",
                    "element",
                    element_id,
                    f"{attr_name}属性未定义类型 (Untyped value types)。",
                    "建议补充 value_type 与单位，确保参数可校验。",
                    True,
                    "set_attribute_type",
                    self._attribute_payload(attr_name, element, attribute),
                    include_internal,
                )

        text = f"{element.get('name') or ''} {element.get('description') or ''}"
        existing_names = {str(item.get("name") or "") for item in attributes}
        generated_count = 0
        for attr_name, value_type, unit, keywords in self.METRIC_RULES:
            if generated_count >= 2:
                break
            if not any(keyword in text for keyword in keywords):
                continue
            if any(attr_name in existing for existing in existing_names):
                continue
            message_name = "天线发射功率" if attr_name == "发射功率" and "天线" in text else attr_name
            self._add_issue(
                issues,
                "warning",
                "attribute.untyped",
                "element",
                element_id,
                f"{message_name}属性未定义类型 (Untyped value types)。",
                f"建议规范化为 {value_type}，单位 {unit}。",
                True,
                "set_attribute_type",
                {"name": attr_name, "value_type": value_type, "unit": unit, "value": ""},
                include_internal,
            )
            generated_count += 1

    def _attribute_payload(self, attr_name: str, element: dict[str, Any], attribute: dict[str, Any]) -> dict[str, Any]:
        text = f"{element.get('name') or ''} {element.get('description') or ''} {attr_name}"
        for name, value_type, unit, keywords in self.METRIC_RULES:
            if any(keyword in text for keyword in keywords):
                return {**attribute, "name": attr_name, "value_type": value_type, "unit": attribute.get("unit") or unit}
        return {**attribute, "name": attr_name, "value_type": "RealValue", "unit": attribute.get("unit") or ""}

    def _apply_fix(self, payload: dict[str, Any], issue: dict[str, Any]) -> bool:
        action = issue.get("fix_action")
        object_id = str(issue.get("object_id") or "")
        fix_payload = issue.get("_fix_payload") or {}
        elements = payload.get("elements") or []
        relationships = payload.get("relationships") or []

        if action == "normalize_package":
            item = self._find(elements, object_id)
            if not item:
                return False
            item["package"] = fix_payload.get("package") or self.generator._default_element_package(str(item.get("type") or ""))
            return True
        if action == "normalize_status":
            item = self._find(elements, object_id)
            if not item:
                return False
            item["status"] = fix_payload.get("status") or "reviewed"
            return True
        if action == "delete_relationship":
            before_count = len(relationships)
            payload["relationships"] = [item for item in relationships if str(item.get("id") or "") != object_id]
            return len(payload["relationships"]) != before_count
        if action == "normalize_relationship_type":
            item = self._find(relationships, object_id)
            if not item:
                return False
            item["type"] = fix_payload.get("type") or "trace"
            return True
        if action == "add_relationship":
            relationship = {
                "id": self._next_relationship_id(relationships),
                "source": fix_payload.get("source"),
                "target": fix_payload.get("target"),
                "type": fix_payload.get("type") or "trace",
                "description": fix_payload.get("description") or "预评审自动补充关系",
            }
            if not relationship["source"] or not relationship["target"]:
                return False
            relationships.append(relationship)
            payload["relationships"] = relationships
            return True
        if action == "set_attribute_type":
            item = self._find(elements, object_id)
            if not item:
                return False
            attrs = [dict(attr) for attr in item.get("attributes") or []]
            attr_name = fix_payload.get("name") or "属性"
            existing = next((attr for attr in attrs if str(attr.get("name") or "") == attr_name), None)
            if existing:
                existing.update(fix_payload)
            else:
                attrs.append(fix_payload)
            item["attributes"] = attrs
            return True
        if action == "rerender_sysml_text":
            return True
        return False

    def _add_issue(
        self,
        issues: list[dict[str, Any]],
        severity: str,
        rule_id: str,
        object_type: str,
        object_id: str,
        message: str,
        suggestion: str,
        fixable: bool,
        fix_action: str | None = None,
        fix_payload: dict[str, Any] | None = None,
        include_internal: bool = False,
    ) -> None:
        issue = {
            "id": f"ISSUE-{len(issues) + 1:03d}",
            "severity": severity,
            "rule_id": rule_id,
            "object_type": object_type,
            "object_id": object_id,
            "message": message,
            "suggestion": suggestion,
            "fixable": fixable,
            "fix_action": fix_action,
        }
        if include_internal:
            issue["_fix_payload"] = fix_payload or {}
        issues.append(issue)

    def _draft_response(self, draft: ModelDraft, payload: dict[str, Any]) -> dict[str, Any]:
        normalized = {
            "draft_id": draft.id,
            "draft_status": draft.status,
            "project_name": payload.get("project_name") or draft.project_name,
            "summary": payload.get("summary") or draft.summary,
            "assumptions": payload.get("assumptions") or [],
            "generation_source": payload.get("generation_source") or draft.generation_source,
            "elements": payload.get("elements") or [],
            "relationships": payload.get("relationships") or [],
            "sysml_text": payload.get("sysml_text") or "",
        }
        return normalized

    def _find(self, items: list[dict[str, Any]], item_id: str) -> dict[str, Any] | None:
        return next((item for item in items if str(item.get("id") or "") == item_id), None)

    def _next_relationship_id(self, relationships: list[dict[str, Any]]) -> str:
        used = {str(item.get("id") or "") for item in relationships}
        max_index = 0
        for relationship_id in used:
            match = re.match(r"REL-(\d+)$", relationship_id)
            if match:
                max_index = max(max_index, int(match.group(1)))
        index = max_index + 1
        while f"REL-{index:03d}" in used:
            index += 1
        return f"REL-{index:03d}"

    def _score(self, issues: list[dict[str, Any]]) -> int:
        penalty = 0
        for issue in issues:
            if issue["severity"] == "error":
                penalty += 15
            elif issue["severity"] == "warning":
                penalty += 7
            else:
                penalty += 3
        return max(40, 100 - penalty)

    def _conclusion(self, score: int, statistics: dict[str, int]) -> str:
        if statistics["error_count"]:
            return f"发现 {statistics['error_count']} 项错误，建议修复后再采纳。"
        if statistics["warning_count"]:
            return f"存在 {statistics['warning_count']} 项警告，可通过一键修复或人工确认后采纳。"
        if score >= 95:
            return "模型预评审通过，未发现明显规则问题。"
        return "模型基本符合规范，建议复核提示项后采纳。"

    def _dump(self, payload: Any) -> str:
        return json.dumps(payload, ensure_ascii=False)

    def _load(self, value: str) -> dict[str, Any]:
        try:
            data = json.loads(value or "{}")
        except json.JSONDecodeError:
            data = {}
        return data if isinstance(data, dict) else {}
