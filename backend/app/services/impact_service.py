from __future__ import annotations

import json
import re
from collections import defaultdict, deque
from typing import Any

from sqlalchemy.orm import Session

from app.models import ChangeImpactReport, ChangeScenario, SysMLElement, SysMLRelationship


RISK_RANK = {"low": 1, "medium": 2, "high": 3}
RISK_LABEL = {"low": "低", "medium": "中", "high": "高"}


class ImpactService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def analyze(self, element_id: str, change_description: str, depth: int = 3) -> dict[str, Any]:
        report = self.sandbox(
            {
                "target_id": element_id,
                "change_description": change_description,
                "depth": depth,
            }
        )
        return {
            "summary": report["summary"],
            "risk_level": RISK_LABEL[report["risk_level"]],
            "direct_impacts": [self._legacy_row(item) for item in report["direct_impacts"]],
            "indirect_impacts": [self._legacy_row(item) for item in report["indirect_impacts"]],
            "paths": report["paths"],
            "suggestions": report["suggestions"],
        }

    def sandbox(self, payload: dict[str, Any]) -> dict[str, Any]:
        elements = self._normalize_elements(payload.get("elements") or [])
        relationships = self._normalize_relationships(payload.get("relationships") or [])
        if not elements:
            elements = [self._element_to_dict(item) for item in self.db.query(SysMLElement).all()]
        if not relationships:
            relationships = [self._relationship_to_dict(item) for item in self.db.query(SysMLRelationship).all()]

        depth = max(1, min(int(payload.get("depth") or 3), 5))
        target = self._resolve_target(payload, elements)
        task_profile = self._classify_task_profile(payload, elements)
        base_risk = self._base_change_risk(payload)
        change = self._change_dict(payload, target)
        target_node = self._target_node(change, target, base_risk)

        graph_rows, graph_edges, graph_paths = self._trace_graph(target, elements, relationships, depth, base_risk)
        rule_rows, rule_edges = self._apply_engineering_rules(payload, target, elements, task_profile, base_risk)
        matrix = self._dedupe_rows([*graph_rows, *rule_rows])
        topology = self._build_topology(target_node, matrix, graph_edges, rule_edges)

        direct = [row for row in matrix if row["directness"] == "direct"]
        indirect = [row for row in matrix if row["directness"] == "indirect"]
        risk_level = self._overall_risk(matrix, base_risk)
        summary = self._summary(change, task_profile, direct, indirect, risk_level)
        suggestions = self._suggestions(matrix, risk_level)
        assumptions = self._assumptions(elements, relationships, rule_rows, graph_rows)

        report = {
            "scenario_id": None,
            "report_id": None,
            "summary": summary,
            "risk_level": risk_level,
            "task_profile": task_profile,
            "change": change,
            "topology": topology,
            "direct_impacts": direct,
            "indirect_impacts": indirect,
            "impact_matrix": matrix,
            "paths": graph_paths or [[target_node["id"], row["node_id"]] for row in matrix[:8]],
            "suggestions": suggestions,
            "assumptions": assumptions,
        }
        self._store_report(payload, report)
        return report

    def _resolve_target(self, payload: dict[str, Any], elements: list[dict[str, Any]]) -> dict[str, Any] | None:
        target_id = str(payload.get("target_id") or "").strip()
        if target_id:
            for item in elements:
                if item["id"] == target_id:
                    return item

        terms = self._tokens(
            " ".join(
                [
                    str(payload.get("target_name") or ""),
                    str(payload.get("attribute_name") or ""),
                    str(payload.get("change_description") or ""),
                ]
            )
        )
        best: tuple[int, dict[str, Any] | None] = (0, None)
        for item in elements:
            haystack = f"{item.get('id', '')} {item.get('name', '')} {item.get('type', '')} {item.get('description', '')}".lower()
            score = sum(3 if term and term in str(item.get("name", "")).lower() else 1 for term in terms if term and term in haystack)
            if score > best[0]:
                best = (score, item)
        if best[1]:
            return best[1]
        return elements[0] if elements else None

    def _trace_graph(
        self,
        target: dict[str, Any] | None,
        elements: list[dict[str, Any]],
        relationships: list[dict[str, Any]],
        depth: int,
        base_risk: str,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[list[str]]]:
        if not target:
            return [], [], []

        by_id = {item["id"]: item for item in elements}
        adjacency: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for rel in relationships:
            source = rel.get("source")
            target_id = rel.get("target")
            if not source or not target_id:
                continue
            adjacency[source].append({"next": target_id, "rel": rel, "direction": "out"})
            adjacency[target_id].append({"next": source, "rel": rel, "direction": "in"})

        start_id = target["id"]
        queue = deque([(start_id, [start_id], 0)])
        visited = {start_id: 0}
        rows: list[dict[str, Any]] = []
        edges: list[dict[str, Any]] = []
        paths: list[list[str]] = []

        while queue:
            current, path, current_depth = queue.popleft()
            if current_depth >= depth:
                continue
            for edge in adjacency.get(current, []):
                next_id = str(edge["next"])
                rel = edge["rel"]
                next_depth = current_depth + 1
                next_path = [*path, next_id]
                if next_id not in visited or next_depth < visited[next_id]:
                    visited[next_id] = next_depth
                    queue.append((next_id, next_path, next_depth))
                if next_id == start_id or next_id not in by_id:
                    continue

                element = by_id[next_id]
                directness = "direct" if next_depth == 1 else "indirect"
                severity = self._merge_risk(base_risk, self._relationship_risk(rel.get("type", ""), next_depth))
                path_labels = [self._element_label(by_id.get(item_id, {"id": item_id, "name": item_id})) for item_id in next_path]
                row = {
                    "id": f"graph-{rel.get('id') or current}-{next_id}",
                    "node_id": next_id,
                    "affected_object": self._element_label(element),
                    "object_type": element.get("type") or "ModelElement",
                    "impact_type": self._impact_type_for_element(element, rel.get("type", "")),
                    "directness": directness,
                    "path": " -> ".join(path_labels),
                    "severity": severity,
                    "reason": f"通过 {rel.get('type') or 'dependency'} 关系追溯到该模型元素。",
                    "recommendation": self._recommendation_for_element(element),
                    "evidence": "SysML 关系追溯",
                }
                rows.append(row)
                edges.append(
                    {
                        "id": f"edge-{rel.get('id') or current}-{next_id}",
                        "source": current,
                        "target": next_id,
                        "label": str(rel.get("type") or "trace"),
                        "type": str(rel.get("type") or "trace"),
                        "directness": directness,
                        "severity": severity,
                    }
                )
                paths.append(next_path)

        return rows, edges, paths

    def _apply_engineering_rules(
        self,
        payload: dict[str, Any],
        target: dict[str, Any] | None,
        elements: list[dict[str, Any]],
        task_profile: str,
        base_risk: str,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        search_text = " ".join(
            [
                str(payload.get("target_name") or ""),
                str(payload.get("attribute_name") or ""),
                str(payload.get("change_description") or ""),
                str(payload.get("unit") or ""),
                str(target.get("name") if target else ""),
                str(target.get("description") if target else ""),
            ]
        )
        rules = [rule for rule in self._rule_catalog(task_profile) if self._rule_matches(rule, search_text)]
        if not rules:
            rules = [self._generic_rule(task_profile)]

        target_id = str(target.get("id") if target else "CHANGE")
        target_label = self._element_label(target) if target else "变更对象"
        rows: list[dict[str, Any]] = []
        edges: list[dict[str, Any]] = []
        for rule in rules[:3]:
            for directness in ("direct", "indirect"):
                for index, item in enumerate(rule.get(directness, []), start=1):
                    matched = self._find_matching_element(elements, item["keywords"])
                    node_id = str(matched.get("id") if matched else f"VIR-{rule['id']}-{directness}-{index}")
                    affected = self._element_label(matched) if matched else item["object"]
                    severity = self._merge_risk(base_risk, item.get("severity", "medium"))
                    via = item.get("via") or rule.get("via") or "工程约束"
                    path = f"{target_label} -> {affected}" if directness == "direct" else f"{target_label} -> {via} -> {affected}"
                    rows.append(
                        {
                            "id": f"rule-{rule['id']}-{directness}-{index}",
                            "node_id": node_id,
                            "affected_object": affected,
                            "object_type": matched.get("type") if matched else item.get("object_type", "AnalysisNode"),
                            "impact_type": item["impact_type"],
                            "directness": directness,
                            "path": path,
                            "severity": severity,
                            "reason": item["reason"],
                            "recommendation": item["recommendation"],
                            "evidence": f"工程规则：{rule['name']}",
                        }
                    )
                    edges.append(
                        {
                            "id": f"rule-edge-{rule['id']}-{directness}-{index}",
                            "source": target_id,
                            "target": node_id,
                            "label": item["impact_type"],
                            "type": "engineering_rule",
                            "directness": directness,
                            "severity": severity,
                        }
                    )
        return rows, edges

    def _build_topology(
        self,
        target_node: dict[str, Any],
        matrix: list[dict[str, Any]],
        graph_edges: list[dict[str, Any]],
        rule_edges: list[dict[str, Any]],
    ) -> dict[str, Any]:
        nodes = {target_node["id"]: target_node}
        for row in matrix:
            level = 1 if row["directness"] == "direct" else 2
            nodes.setdefault(
                row["node_id"],
                {
                    "id": row["node_id"],
                    "label": row["affected_object"],
                    "type": row["object_type"],
                    "level": level,
                    "category": row["impact_type"],
                    "risk": row["severity"],
                    "source": "graph" if row["evidence"].startswith("SysML") else "rule",
                },
            )

        edges = [edge for edge in [*graph_edges, *rule_edges] if edge["source"] in nodes and edge["target"] in nodes]
        if not edges:
            edges = [
                {
                    "id": f"topology-{index}",
                    "source": target_node["id"],
                    "target": row["node_id"],
                    "label": row["impact_type"],
                    "type": "impact",
                    "directness": row["directness"],
                    "severity": row["severity"],
                }
                for index, row in enumerate(matrix, start=1)
            ]
        return {"nodes": list(nodes.values()), "edges": edges}

    def _store_report(self, payload: dict[str, Any], report: dict[str, Any]) -> None:
        try:
            self._ensure_change_tables()
            change = report["change"]
            scenario = ChangeScenario(
                project_name=change.get("project_name") or "",
                target_id=change.get("target_id"),
                target_name=change.get("target_name") or "",
                attribute_name=change.get("attribute_name") or "",
                old_value=change.get("old_value") or "",
                new_value=change.get("new_value") or "",
                unit=change.get("unit") or "",
                change_description=payload.get("change_description") or "",
                task_context=payload.get("task_context") or "",
            )
            self.db.add(scenario)
            self.db.flush()
            stored_report = ChangeImpactReport(
                scenario_id=scenario.id,
                risk_level=report["risk_level"],
                summary=report["summary"],
                topology_json=json.dumps(report["topology"], ensure_ascii=False),
                matrix_json=json.dumps(report["impact_matrix"], ensure_ascii=False),
                suggestions_json=json.dumps(report["suggestions"], ensure_ascii=False),
            )
            self.db.add(stored_report)
            self.db.commit()
            report["scenario_id"] = scenario.id
            report["report_id"] = stored_report.id
        except Exception:
            self.db.rollback()

    def _ensure_change_tables(self) -> None:
        bind = self.db.get_bind()
        ChangeScenario.__table__.create(bind=bind, checkfirst=True)
        ChangeImpactReport.__table__.create(bind=bind, checkfirst=True)

    def _rule_catalog(self, task_profile: str) -> list[dict[str, Any]]:
        rules = [
            {
                "id": "power",
                "name": "功率与供电链路",
                "keywords": ["功率", "发射功率", "eirp", "dbw", "供电", "电源", "功耗", "放大器", "power", "transmit power", "amplifier"],
                "via": "功耗预算",
                "direct": [
                    self._rule_item("电源分系统 / 功率预算", ["电源", "供电", "功耗", "能源"], "功耗与供电裕度", "high", "目标功率上调会直接增加供电能力和功率预算压力。", "重新核算峰值功耗、母线功率和电源裕度。"),
                    self._rule_item("载荷射频链路", ["载荷", "射频", "天线", "通信"], "链路预算", "medium", "射频输出变化会改变链路预算、器件工作点和接口约束。", "复核链路预算、放大器工作区间和射频接口。"),
                    self._rule_item("电磁兼容约束", ["电磁", "频谱", "兼容", "EMC", "合规"], "EMC / 频谱合规", "medium", "更高发射功率可能增加邻频干扰和电磁兼容风险。", "补充频谱合规和电磁兼容校核。"),
                ],
                "indirect": [
                    self._rule_item("热控分系统", ["热控", "散热", "温度", "热"], "热耗与散热需求", "high", "功耗增加会转化为热耗，推高散热和热平衡设计要求。", "重新计算热耗、散热面积和温度裕度。", via="功耗预算"),
                    self._rule_item("结构与质量预算", ["结构", "质量", "重量", "安装"], "质量 / 安装约束", "medium", "电源和热控器件可能带来质量、安装空间和布线变化。", "复核质量预算、安装空间和线缆路径。", via="电源与热控调整"),
                ],
            },
            {
                "id": "bandwidth",
                "name": "带宽与数据链路",
                "keywords": ["带宽", "速率", "吞吐", "容量", "mbps", "gbps", "数据率", "链路", "bandwidth", "throughput", "capacity", "data rate", "link"],
                "via": "数据流量预算",
                "direct": [
                    self._rule_item("通信载荷处理链路", ["载荷", "处理", "通信", "宽带"], "处理吞吐", "high", "带宽或速率提升会直接增加载荷处理、调制解调和缓存压力。", "复核处理吞吐、缓存深度和调制编码方案。"),
                    self._rule_item("星间 / 星地链路接口", ["星间", "星地", "链路", "接口", "回传"], "接口容量", "high", "链路容量变化会影响接口速率、协议和链路预算。", "同步更新接口速率、链路预算和协议约束。"),
                    self._rule_item("网络管理与资源调度", ["网络", "调度", "资源", "路由"], "资源调度", "medium", "更高业务容量会改变路由、队列和资源调度策略。", "复核路由策略、QoS 队列和资源分配规则。"),
                ],
                "indirect": [
                    self._rule_item("电源与热控裕度", ["电源", "热控", "功耗", "散热"], "功耗 / 热耗", "medium", "处理吞吐增加通常会带来功耗和热耗上升。", "联动校核功率预算和热控裕度。", via="处理吞吐提升"),
                    self._rule_item("地面站与运控系统", ["地面", "网关", "运控", "测控"], "地面资源", "medium", "链路容量变化可能扩大地面接收、存储和运维压力。", "复核地面站吞吐、存储和运行计划。", via="链路容量调整"),
                ],
            },
            {
                "id": "orbit",
                "name": "轨道与覆盖任务",
                "keywords": ["轨道", "高度", "倾角", "轨道面", "覆盖", "重访", "星座", "相位", "orbit", "altitude", "inclination", "coverage", "revisit"],
                "via": "覆盖与几何约束",
                "direct": [
                    self._rule_item("星座构型与覆盖需求", ["星座", "覆盖", "轨道", "构型"], "覆盖性能", "high", "轨道参数变化会直接改变覆盖、重访和可见时间窗口。", "重新开展覆盖与容量仿真。"),
                    self._rule_item("链路预算与传播损耗", ["链路", "预算", "传播", "通信"], "传播损耗", "medium", "轨道高度变化会改变自由空间损耗和可见时间。", "联动复核链路预算和通信可用性。"),
                ],
                "indirect": [
                    self._rule_item("地面站资源", ["地面", "网关", "测控", "站"], "站网可见性", "medium", "可见窗口变化会影响地面站排班和任务规划。", "更新地面站可见性、冲突和调度计划。", via="覆盖窗口变化"),
                    self._rule_item("姿态控制与热环境", ["姿态", "热控", "太阳", "能源"], "环境与姿控", "medium", "轨道几何变化可能改变光照、热环境和姿态控制需求。", "复核姿态控制、能源收支和热环境边界。", via="轨道环境变化"),
                ],
            },
            {
                "id": "interface",
                "name": "接口与协议一致性",
                "keywords": ["接口", "协议", "数据格式", "端口", "总线", "icd", "消息", "遥测", "遥控", "interface", "protocol", "data format", "port", "bus", "message"],
                "via": "接口契约",
                "direct": [
                    self._rule_item("上游模块", ["上游", "源", "载荷", "模块"], "接口契约", "medium", "接口变化会直接影响调用方、数据生产方或连接端。", "更新 ICD、端口定义和数据格式。"),
                    self._rule_item("下游模块", ["下游", "目标", "处理", "终端"], "数据兼容", "medium", "接口变化会影响消费方解析、状态机和异常处理。", "补充兼容性测试和异常处理用例。"),
                ],
                "indirect": [
                    self._rule_item("验证与测试基线", ["验证", "测试", "用例", "verify"], "测试回归", "medium", "接口协议变化会牵引验证用例和回归测试范围。", "重建接口一致性测试和回归测试清单。", via="接口契约调整"),
                ],
            },
        ]

        if task_profile == "remote_sensing":
            rules.append(
                {
                    "id": "remote-sensing",
                    "name": "遥感成像任务",
                    "keywords": ["分辨率", "成像", "相机", "sar", "幅宽", "谱段", "遥感", "图像", "resolution", "imaging", "camera", "swath", "spectral", "remote sensing", "image"],
                    "via": "成像质量约束",
                    "direct": [
                        self._rule_item("载荷成像链路", ["载荷", "成像", "相机", "SAR"], "成像质量", "high", "成像指标变化会直接影响光机电载荷和成像处理链路。", "复核载荷参数、成像模式和处理吞吐。"),
                        self._rule_item("数传与存储系统", ["数传", "存储", "下传", "数据"], "数据量", "medium", "分辨率或幅宽提升会扩大原始数据量。", "重新核算存储容量、压缩比和下传窗口。"),
                    ],
                    "indirect": [
                        self._rule_item("姿态稳定与轨控", ["姿态", "稳定", "轨控"], "指向稳定", "medium", "成像质量约束会牵引姿态稳定度和轨控精度。", "复核指向精度、稳定度和姿态机动计划。", via="成像质量约束"),
                    ],
                }
            )
        elif task_profile == "navigation":
            rules.append(
                {
                    "id": "navigation",
                    "name": "导航定位任务",
                    "keywords": ["导航", "定位", "授时", "钟", "完好性", "精度", "gnss", "navigation", "positioning", "timing", "clock", "integrity", "accuracy"],
                    "via": "导航服务性能",
                    "direct": [
                        self._rule_item("导航载荷与星载钟", ["导航", "钟", "授时", "载荷"], "定位 / 授时精度", "high", "导航指标变化会直接牵引载荷稳定性和时间基准。", "复核星载钟稳定度、信号体制和误差预算。"),
                        self._rule_item("地面监测与定轨", ["地面", "定轨", "监测"], "定轨与完好性", "medium", "精度或完好性变化会影响地面监测与定轨流程。", "更新定轨、监测和完好性校核流程。"),
                    ],
                    "indirect": [
                        self._rule_item("用户终端兼容", ["用户", "终端", "兼容"], "终端兼容性", "medium", "信号或服务指标变化可能影响终端兼容性。", "补充终端兼容性验证。", via="导航服务性能调整"),
                    ],
                }
            )
        return rules

    def _generic_rule(self, task_profile: str) -> dict[str, Any]:
        return {
            "id": f"generic-{task_profile}",
            "name": "通用 MBSE 追溯规则",
            "keywords": [],
            "via": "模型追溯关系",
            "direct": [
                self._rule_item("关联需求", ["需求", "REQ", "requirement"], "需求一致性", "medium", "变更对象需要回看其上游需求是否仍然成立。", "检查相关需求、阈值和验收准则。"),
                self._rule_item("接口与约束", ["接口", "约束", "IF", "CON"], "接口 / 约束一致性", "medium", "模型参数变化通常会牵引接口契约或约束条件。", "复核接口定义、约束表达式和参数单位。"),
            ],
            "indirect": [
                self._rule_item("验证用例与交付基线", ["验证", "测试", "用例", "UC", "ACT"], "验证回归", "medium", "上游变更会影响验证用例、仿真场景和交付基线。", "更新验证矩阵、仿真输入和回归测试清单。", via="需求与约束更新"),
            ],
        }

    def _rule_item(
        self,
        object_name: str,
        keywords: list[str],
        impact_type: str,
        severity: str,
        reason: str,
        recommendation: str,
        via: str = "",
    ) -> dict[str, Any]:
        return {
            "object": object_name,
            "keywords": keywords,
            "impact_type": impact_type,
            "severity": severity,
            "reason": reason,
            "recommendation": recommendation,
            "via": via,
        }

    def _rule_matches(self, rule: dict[str, Any], text: str) -> bool:
        lowered = text.lower()
        return any(keyword.lower() in lowered for keyword in rule.get("keywords", []))

    def _find_matching_element(self, elements: list[dict[str, Any]], keywords: list[str]) -> dict[str, Any] | None:
        best: tuple[int, dict[str, Any] | None] = (0, None)
        for item in elements:
            haystack = f"{item.get('id', '')} {item.get('name', '')} {item.get('type', '')} {item.get('description', '')}".lower()
            score = sum(1 for keyword in keywords if keyword.lower() in haystack)
            if score > best[0]:
                best = (score, item)
        return best[1]

    def _classify_task_profile(self, payload: dict[str, Any], elements: list[dict[str, Any]]) -> str:
        explicit_text = " ".join(
            [
                str(payload.get("project_name") or ""),
                str(payload.get("task_context") or ""),
                str(payload.get("change_description") or ""),
            ]
        ).lower()
        explicit_profile = self._match_task_profile(explicit_text)
        if explicit_profile != "general_system":
            return explicit_profile
        model_text = " ".join(f"{item.get('name', '')} {item.get('description', '')}" for item in elements[:40]).lower()
        return self._match_task_profile(model_text)

    def _match_task_profile(self, text: str) -> str:
        if any(word in text for word in ["遥感", "成像", "sar", "相机", "分辨率", "remote sensing", "imaging", "camera", "resolution"]):
            return "remote_sensing"
        if any(word in text for word in ["导航", "定位", "授时", "gnss", "完好性", "navigation", "positioning", "timing", "clock", "integrity"]):
            return "navigation"
        if any(word in text for word in ["通信", "宽带", "链路", "星间", "星地", "频谱", "载荷", "卫星", "星座", "communication", "link", "broadband", "payload", "constellation"]):
            return "communication_satellite"
        if any(word in text for word in ["无人机", "飞控", "飞机", "姿态控制", "uav", "aircraft", "flight control"]):
            return "flight_control"
        return "general_system"

    def _base_change_risk(self, payload: dict[str, Any]) -> str:
        old_value = self._parse_number(payload.get("old_value"))
        new_value = self._parse_number(payload.get("new_value"))
        text = f"{payload.get('attribute_name', '')} {payload.get('change_description', '')} {payload.get('unit', '')}".lower()
        if old_value is None or new_value is None:
            return "medium" if any(word in text for word in ["接口", "协议", "轨道", "功率", "带宽", "安全", "约束", "interface", "protocol", "orbit", "power", "bandwidth", "safety", "constraint"]) else "low"

        delta = abs(new_value - old_value)
        if "db" in text or "功率" in text or "power" in text:
            if delta >= 3:
                return "high"
            if delta >= 1:
                return "medium"
            return "low"
        if old_value == 0:
            return "medium" if delta else "low"
        ratio = delta / abs(old_value)
        if ratio >= 0.3:
            return "high"
        if ratio >= 0.1:
            return "medium"
        return "low"

    def _relationship_risk(self, relationship_type: str, depth: int) -> str:
        rel_type = relationship_type.lower()
        if rel_type in {"satisfy", "verify", "allocate"}:
            return "high" if depth == 1 else "medium"
        if rel_type in {"refine", "trace", "dependency"}:
            return "medium"
        return "low"

    def _overall_risk(self, matrix: list[dict[str, Any]], base_risk: str) -> str:
        risk = base_risk
        high_count = sum(1 for row in matrix if row["severity"] == "high")
        medium_count = sum(1 for row in matrix if row["severity"] == "medium")
        for row in matrix:
            risk = self._merge_risk(risk, row["severity"])
        if high_count >= 2 or len(matrix) >= 8:
            return "high"
        if medium_count >= 3 and risk == "medium":
            return "medium"
        return risk

    def _summary(
        self,
        change: dict[str, Any],
        task_profile: str,
        direct: list[dict[str, Any]],
        indirect: list[dict[str, Any]],
        risk_level: str,
    ) -> str:
        value_text = ""
        if change.get("old_value") or change.get("new_value"):
            value_text = f"（{change.get('old_value') or '未给定'} -> {change.get('new_value') or '未给定'}{change.get('unit') or ''}）"
        return (
            f"沙箱分析完成：{change.get('target_name') or '选中对象'}"
            f"{change.get('attribute_name') or '参数'}{value_text} 在 {task_profile} 场景下触发 "
            f"{len(direct)} 项直接影响、{len(indirect)} 项间接影响，综合风险为{RISK_LABEL[risk_level]}。"
        )

    def _suggestions(self, matrix: list[dict[str, Any]], risk_level: str) -> list[str]:
        suggestions = [
            "本次结果停留在沙箱预演，不会直接修改正式 SysML 模型库。",
            "建议先处理高风险直接影响，再复核间接影响链路中的约束和验证项。",
        ]
        for row in matrix:
            if row["severity"] == "high":
                suggestions.append(f"{row['affected_object']}：{row['recommendation']}")
            if len(suggestions) >= 5:
                break
        if risk_level == "high":
            suggestions.append("建议形成变更评审记录，并在采纳前同步更新需求、接口、约束和验证矩阵。")
        return suggestions

    def _assumptions(
        self,
        elements: list[dict[str, Any]],
        relationships: list[dict[str, Any]],
        rule_rows: list[dict[str, Any]],
        graph_rows: list[dict[str, Any]],
    ) -> list[str]:
        assumptions = [
            f"当前分析基于 {len(elements)} 个模型元素和 {len(relationships)} 条关系进行。",
            "影响传播深度按用户设置限制，结果用于预评审和方案比较。",
        ]
        if rule_rows and not graph_rows:
            assumptions.append("当前模型图谱关系不足，系统使用工程规则生成候选影响节点。")
        elif rule_rows:
            assumptions.append("除 SysML 关系追溯外，系统补充使用工程规则识别潜在跨专业影响。")
        return assumptions

    def _change_dict(self, payload: dict[str, Any], target: dict[str, Any] | None) -> dict[str, Any]:
        return {
            "project_name": payload.get("project_name") or "",
            "target_id": target.get("id") if target else payload.get("target_id"),
            "target_name": payload.get("target_name") or (target.get("name") if target else ""),
            "attribute_name": payload.get("attribute_name") or "变更属性",
            "old_value": str(payload.get("old_value") or ""),
            "new_value": str(payload.get("new_value") or ""),
            "unit": str(payload.get("unit") or ""),
            "description": payload.get("change_description") or "",
        }

    def _target_node(self, change: dict[str, Any], target: dict[str, Any] | None, base_risk: str) -> dict[str, Any]:
        node_id = str(change.get("target_id") or "CHANGE")
        label = f"{change.get('target_name') or node_id}\n{change.get('attribute_name') or '变更'}"
        return {
            "id": node_id,
            "label": label,
            "type": target.get("type") if target else "Change",
            "level": 0,
            "category": "变更源",
            "risk": base_risk,
            "source": "input",
        }

    def _normalize_elements(self, items: list[Any]) -> list[dict[str, Any]]:
        elements = []
        for item in items:
            data = dict(item)
            element_id = str(data.get("id") or "").strip()
            if not element_id:
                continue
            elements.append(
                {
                    "id": element_id,
                    "name": str(data.get("name") or element_id),
                    "type": str(data.get("type") or "Block"),
                    "description": str(data.get("description") or ""),
                    "package": data.get("package"),
                    "source_requirement": data.get("source_requirement"),
                    "status": str(data.get("status") or "candidate"),
                    "attributes": data.get("attributes") or [],
                }
            )
        return elements

    def _normalize_relationships(self, items: list[Any]) -> list[dict[str, Any]]:
        relationships = []
        for item in items:
            data = dict(item)
            source = str(data.get("source") or "").strip()
            target = str(data.get("target") or "").strip()
            if not source or not target:
                continue
            relationships.append(
                {
                    "id": str(data.get("id") or f"{source}-{target}"),
                    "source": source,
                    "target": target,
                    "type": str(data.get("type") or "trace"),
                    "description": str(data.get("description") or ""),
                }
            )
        return relationships

    def _dedupe_rows(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        best: dict[tuple[str, str, str], dict[str, Any]] = {}
        for row in rows:
            key = (row["node_id"], row["directness"], row["impact_type"])
            existing = best.get(key)
            if not existing or RISK_RANK[row["severity"]] > RISK_RANK[existing["severity"]]:
                best[key] = row
        return sorted(best.values(), key=lambda item: (item["directness"] != "direct", -RISK_RANK[item["severity"]], item["affected_object"]))

    def _impact_type_for_element(self, element: dict[str, Any], relationship_type: str) -> str:
        element_type = str(element.get("type") or "").lower()
        if element_type == "requirement":
            return "需求一致性"
        if element_type == "interface":
            return "接口一致性"
        if element_type == "constraintblock":
            return "约束校核"
        if element_type == "usecase":
            return "业务流程 / 用例"
        if relationship_type.lower() == "verify":
            return "验证回归"
        if relationship_type.lower() == "allocate":
            return "功能分配"
        return "模型追溯"

    def _recommendation_for_element(self, element: dict[str, Any]) -> str:
        element_type = str(element.get("type") or "").lower()
        if element_type == "requirement":
            return "检查需求阈值、验收准则和下游满足关系。"
        if element_type == "interface":
            return "复核接口速率、协议、数据格式和 ICD。"
        if element_type == "constraintblock":
            return "重新计算约束表达式、单位和裕度。"
        if element_type == "usecase":
            return "补充用例流程、异常分支和验证场景。"
        return "复核该元素的属性、连接关系和相关验证项。"

    def _merge_risk(self, left: str, right: str) -> str:
        return left if RISK_RANK.get(left, 1) >= RISK_RANK.get(right, 1) else right

    def _parse_number(self, value: Any) -> float | None:
        match = re.search(r"-?\d+(?:\.\d+)?", str(value or ""))
        return float(match.group(0)) if match else None

    def _tokens(self, text: str) -> list[str]:
        lowered = text.lower()
        pieces = [piece.strip() for piece in re.split(r"[\s,，。；;:/\\|()\[\]{}]+", lowered) if len(piece.strip()) >= 2]
        keywords = [
            "功率",
            "发射功率",
            "带宽",
            "链路",
            "接口",
            "轨道",
            "高度",
            "倾角",
            "覆盖",
            "质量",
            "热控",
            "电源",
            "载荷",
            "导航",
            "成像",
        ]
        return list(dict.fromkeys([*pieces, *[keyword for keyword in keywords if keyword in lowered]]))

    def _element_label(self, item: dict[str, Any] | None) -> str:
        if not item:
            return "变更对象"
        element_id = str(item.get("id") or "")
        name = str(item.get("name") or element_id)
        return f"{element_id} {name}".strip()

    def _element_to_dict(self, item: SysMLElement) -> dict[str, Any]:
        return {
            "id": item.id,
            "name": item.name,
            "type": item.type,
            "description": item.description,
            "source_requirement": item.source_requirement,
            "status": item.status,
            "attributes": [],
        }

    def _relationship_to_dict(self, item: SysMLRelationship) -> dict[str, Any]:
        return {
            "id": item.id,
            "source": item.source,
            "target": item.target,
            "type": item.type,
            "description": item.description,
        }

    def _legacy_row(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": row.get("node_id"),
            "name": row.get("affected_object"),
            "type": row.get("object_type"),
            "description": row.get("reason"),
            "status": row.get("severity"),
        }
