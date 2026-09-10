from __future__ import annotations

import json
from collections import Counter, defaultdict
from typing import Any

from sqlalchemy.orm import Session

from app.models import SysMLElement, SysMLRelationship, ValidationReport


class ValidationService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def run(self) -> dict[str, Any]:
        elements = self.db.query(SysMLElement).all()
        relationships = self.db.query(SysMLRelationship).all()
        element_map = {item.id: item for item in elements}
        by_type = defaultdict(list)
        for item in elements:
            by_type[item.type].append(item)

        issues: list[dict[str, Any]] = []

        for item in elements:
            if not item.name.strip():
                issues.append(self._issue("high", "empty_name", item.id, "元素名称为空。", "请补充元素名称。"))

        for item_type, grouped in by_type.items():
            names = [item.name for item in grouped if item.name.strip()]
            duplicates = {name for name, count in Counter(names).items() if count > 1}
            for item in grouped:
                if item.name in duplicates:
                    issues.append(
                        self._issue(
                            "medium",
                            "duplicate_name",
                            item.id,
                            f"{item_type} 类型中存在重复名称：{item.name}。",
                            "建议调整同类型元素命名，避免评审歧义。",
                        )
                    )

        relation_lookup = [(rel.source, rel.target, rel.type) for rel in relationships]

        for item in by_type["Requirement"]:
            has_trace = any(
                item.id in (source, target) and rel_type in {"trace", "satisfy"}
                for source, target, rel_type in relation_lookup
            )
            if not has_trace:
                issues.append(
                    self._issue(
                        "medium",
                        "trace_missing",
                        item.id,
                        "该需求尚未建立 trace 或 satisfy 关系。",
                        "建议为该需求关联 UseCase 或 Block。",
                    )
                )

        for item in by_type["UseCase"]:
            has_block = any(
                item.id in (source, target)
                and (element_map.get(source).type == "Block" or element_map.get(target).type == "Block")
                for source, target, _ in relation_lookup
                if source in element_map and target in element_map
            )
            if not has_block:
                issues.append(
                    self._issue(
                        "medium",
                        "usecase_block_missing",
                        item.id,
                        "该 UseCase 尚未关联 Block。",
                        "建议通过 allocate 关系关联承载模块。",
                    )
                )

        for item in by_type["Interface"]:
            has_block = any(
                item.id in (source, target)
                and (element_map.get(source).type == "Block" or element_map.get(target).type == "Block")
                for source, target, _ in relation_lookup
                if source in element_map and target in element_map
            )
            if not has_block:
                issues.append(
                    self._issue(
                        "medium",
                        "interface_block_missing",
                        item.id,
                        "该 Interface 尚未关联 Block。",
                        "建议补充接口与系统模块之间的 connect 关系。",
                    )
                )

        for item in elements:
            if item.status == "candidate":
                issues.append(
                    self._issue(
                        "low",
                        "candidate_not_confirmed",
                        item.id,
                        "该元素仍处于候选状态。",
                        "建议完成人工确认后再进入发布评审。",
                    )
                )

        statistics = {
            "requirement_count": len(by_type["Requirement"]),
            "block_count": len(by_type["Block"]),
            "usecase_count": len(by_type["UseCase"]),
            "interface_count": len(by_type["Interface"]),
            "activity_count": len(by_type["Activity"]),
            "relationship_count": len(relationships),
        }
        score = self._score(issues)
        conclusion = self._conclusion(score, issues)

        report = ValidationReport(
            score=score,
            conclusion=conclusion,
            issues_json=json.dumps(issues, ensure_ascii=False),
            statistics_json=json.dumps(statistics, ensure_ascii=False),
        )
        self.db.add(report)
        self.db.commit()
        self.db.refresh(report)

        return {
            "id": report.id,
            "score": score,
            "conclusion": conclusion,
            "issues": issues,
            "statistics": statistics,
            "created_at": report.created_at,
        }

    def history(self) -> list[dict[str, Any]]:
        reports = self.db.query(ValidationReport).order_by(ValidationReport.id.desc()).limit(10).all()
        return [
            {
                "id": report.id,
                "score": report.score,
                "conclusion": report.conclusion,
                "issues": json.loads(report.issues_json),
                "statistics": json.loads(report.statistics_json),
                "created_at": report.created_at,
            }
            for report in reports
        ]

    def _issue(self, level: str, issue_type: str, element_id: str, message: str, suggestion: str) -> dict[str, str]:
        return {
            "level": level,
            "type": issue_type,
            "element_id": element_id,
            "message": message,
            "suggestion": suggestion,
        }

    def _score(self, issues: list[dict[str, Any]]) -> int:
        penalty = 0
        for issue in issues:
            if issue["level"] == "high":
                penalty += 15
            elif issue["level"] == "medium":
                penalty += 7
            else:
                penalty += 3
        return max(60, 100 - penalty)

    def _conclusion(self, score: int, issues: list[dict[str, Any]]) -> str:
        medium_or_high = sum(1 for issue in issues if issue["level"] in {"medium", "high"})
        if score >= 90:
            return "模型基本可评审，未发现阻断性问题。"
        if score >= 80:
            return f"模型基本可评审，但存在 {medium_or_high} 个中高风险问题。"
        return f"模型需要补充完善，当前存在 {medium_or_high} 个中高风险问题。"
