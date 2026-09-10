from __future__ import annotations

import json
import re
from typing import Any


class ModelGenerationService:
    def generate(self, requirements: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        """Legacy requirement-list generator kept for the existing model page."""
        if not requirements:
            return {"elements": [], "relationships": []}

        elements: list[dict[str, Any]] = [
            {
                "id": "BLK-001",
                "name": "宽带通信系统",
                "type": "Block",
                "description": "负责宽带业务接入、链路管理、业务调度和状态监测的系统级模块。",
                "source_requirement": requirements[0]["id"],
                "status": "candidate",
            }
        ]
        relationships: list[dict[str, Any]] = []
        rel_index = 1

        for index, requirement in enumerate(requirements, start=1):
            req_id = requirement["id"]
            uc_id = f"UC-{index:03d}"
            if_id = f"IF-{index:03d}"
            act_id = f"ACT-{index:03d}"
            req_name = str(requirement.get("name") or req_id)

            elements.extend(
                [
                    {
                        "id": req_id,
                        "name": req_name,
                        "type": "Requirement",
                        "description": str(requirement.get("description") or req_name),
                        "source_requirement": req_id,
                        "status": "candidate",
                    },
                    {
                        "id": uc_id,
                        "name": req_name.replace("能力", ""),
                        "type": "UseCase",
                        "description": f"围绕“{req_name}”展开的用户或系统行为场景。",
                        "source_requirement": req_id,
                        "status": "candidate",
                    },
                    {
                        "id": if_id,
                        "name": f"{req_name.replace('能力', '')}接口",
                        "type": "Interface",
                        "description": f"支撑“{req_name}”的数据、控制或状态交互接口。",
                        "source_requirement": req_id,
                        "status": "candidate",
                    },
                    {
                        "id": act_id,
                        "name": f"{req_name.replace('能力', '')}流程",
                        "type": "Activity",
                        "description": f"描述“{req_name}”从触发、处理到反馈的核心流程。",
                        "source_requirement": req_id,
                        "status": "candidate",
                    },
                ]
            )

            for source, target, rel_type, description in [
                (req_id, uc_id, "trace", "需求追溯到用例"),
                (uc_id, "BLK-001", "allocate", "用例分配到系统模块"),
                (uc_id, if_id, "trace", "用例追溯到接口"),
                (if_id, "BLK-001", "allocate", "接口分配到系统模块"),
                (uc_id, act_id, "trace", "用例细化为活动流程"),
            ]:
                relationships.append(
                    {
                        "id": f"REL-{rel_index:03d}",
                        "source": source,
                        "target": target,
                        "type": rel_type,
                        "description": description,
                    }
                )
                rel_index += 1

        return {"elements": elements, "relationships": relationships}

    def generate_project_from_dialogue(
        self,
        conversation: list[dict[str, Any]] | None = None,
        prompt: str = "",
        project_name: str | None = None,
    ) -> dict[str, Any]:
        """Generate a complete SysML project from a free-form AI dialogue context.

        This path is intentionally independent from the old confirmed-requirement
        workflow. It uses the current dialogue text as the project brief and
        returns a complete engineering package that can be pushed to MagicDraw.
        """
        conversation = conversation or []
        brief = self._dialogue_brief(conversation, prompt)
        domain_source = self._latest_user_brief(conversation, prompt)
        domain = self._detect_domain(domain_source)
        if domain == "generic":
            domain = self._detect_domain(brief)
        else:
            brief = domain_source

        llm_project = self._generate_project_with_llm(brief, project_name)
        if llm_project:
            return self._attach_diagram_views(llm_project, brief)

        if self._should_use_curated_project(domain, brief):
            return self._attach_diagram_views(self._curated_project_from_dialogue(domain, brief, project_name), brief)

        return self._attach_diagram_views(self._fallback_project_from_dialogue(brief, project_name), brief)

    def generate_internal_block_diagram(
        self,
        project_name: str,
        prompt: str,
        focus_element: dict[str, Any],
        elements: list[dict[str, Any]],
        relationships: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Generate a focused Internal Block Diagram for the selected Block.

        This is intentionally scoped to IBD only. Use cases remain a system-level
        behavior view and are not generated for module drill-down.
        """
        focus = dict(focus_element or {})
        focus.setdefault("id", "FOCUS-BLK")
        focus.setdefault("name", focus.get("id") or "当前模块")
        focus.setdefault("type", "Block")
        context = {
            "project_name": project_name or "AI_MBSE_Project",
            "prompt": prompt or "",
            "focus_element": focus,
            "elements": [dict(item) for item in elements if isinstance(item, dict)],
            "relationships": [dict(item) for item in relationships if isinstance(item, dict)],
        }
        llm_view = self._generate_internal_block_diagram_with_llm(context)
        if llm_view:
            return llm_view
        return self._fallback_internal_block_diagram(context)

    def _generate_internal_block_diagram_with_llm(self, context: dict[str, Any]) -> dict[str, Any] | None:
        try:
            from app.services.llm_service import LLMService

            prompt = self._llm_internal_block_diagram_prompt(context)
            result = LLMService().chat(
                [
                    {
                        "role": "system",
                        "content": (
                            "你是资深 SysML IBD 建模专家。你只为当前选中的 Block 生成内部模块图，"
                            "不生成用例图，不生成 Actor/UseCase。必须基于当前模型上下文动态分解，不使用固定模板。只返回 JSON。"
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                task_type="model_generation",
            )
            data = self._try_parse_json_object(str(result.get("answer") or ""))
            if not data:
                return None
            return self._normalize_internal_ibd_view(data, context)
        except Exception:
            return None

    def _llm_internal_block_diagram_prompt(self, context: dict[str, Any]) -> str:
        focus = context["focus_element"]
        compact_context = {
            "project_name": context.get("project_name"),
            "prompt": context.get("prompt"),
            "focus_element": focus,
            "related_context": self._related_context_for_focus(focus, context.get("elements") or [], context.get("relationships") or []),
            "all_elements": [
                {
                    "id": item.get("id"),
                    "name": item.get("name"),
                    "type": item.get("type"),
                    "description": item.get("description"),
                    "package": item.get("package"),
                }
                for item in (context.get("elements") or [])
            ],
            "relationships": [
                {
                    "id": item.get("id"),
                    "source": item.get("source"),
                    "target": item.get("target"),
                    "type": item.get("type"),
                    "description": item.get("description"),
                }
                for item in (context.get("relationships") or [])
            ],
        }
        return f"""
请为当前选中的 SysML Block 生成一个内部模块图（Internal Block Diagram, IBD）。

当前下钻 Block：
{json.dumps(focus, ensure_ascii=False)}

当前工程上下文：
{json.dumps(compact_context, ensure_ascii=False)}

严格要求：
1. 只返回一个 JSON 对象，不要 Markdown，不要解释。
2. 只生成 IBD，不允许出现 Actor、UseCase、Requirement、Activity。
3. elements 只能是 Block 或 Interface，表示当前 Block 内部 parts、边界接口或平台资源接口。
4. relationships 只能表达内部连接，优先使用 connector；每条关系必须引用 elements 中存在的 id。
5. 不要把总体模型中的兄弟 Block 直接当成当前 Block 内部模块。只有当前模型已通过 contains 明确表示该 Block 包含某元素时，才可复用该元素。
6. 如果当前模型尚未定义内部结构，请根据当前 Block 的名称、描述、相邻需求、接口和用户原始意图合理生成候选内部组成，并在 rationale 中说明这是 AI 候选分解。
7. 命名应贴合当前 Block 的领域语义。例如当前 Block 是通信载荷，就围绕信号接入、处理、转发、控制、遥测、电源热控等实际内部职责展开；如果是其他系统，则按该系统职责动态分解。
8. 不同 Block 的 IBD 不得只替换文字而复用同一个“输入-处理-控制-输出”模板；必须根据当前 Block 选择不同拓扑，例如链式处理、中心总线、闭环控制、分层地面站、星座网络或网管调度网络。
9. elements 建议 6-10 个；relationships 建议 7-12 条。除主链路外，至少包含 2 条控制/反馈/监测/资源支撑连接，避免所有节点只是线性串联。
10. 所有节点都必须参与至少一条关系，关系说明必须写清楚传递的是数据、控制、能量、状态、策略、遥测或业务流中的哪一种。

JSON Schema：
{{
  "id": "FOCUS-IBD",
  "variant_id": "FOCUS-IBD",
  "variant_name": "当前模块 AI 内部分解",
  "diagram_type": "ibd",
  "name": "当前模块 - 内部模块图（IBD）",
  "description": "这张图表示什么",
  "rationale": "内部结构边界、依据和假设",
  "elements": [
    {{"id": "IBD-BLK-001", "name": "内部处理单元", "type": "Block", "description": "职责说明", "package": "02_Structure", "status": "candidate"}},
    {{"id": "IBD-IF-001", "name": "输入接口", "type": "Interface", "description": "接口说明", "package": "04_Interfaces", "status": "candidate"}}
  ],
  "relationships": [
    {{"id": "DREL-IBD-001", "source": "IBD-IF-001", "target": "IBD-BLK-001", "type": "connector", "description": "连接或流向说明"}}
  ]
}}
""".strip()

    def _normalize_internal_ibd_view(self, data: dict[str, Any], context: dict[str, Any]) -> dict[str, Any] | None:
        raw_view = data.get("diagram_view") or data.get("view") or data
        if isinstance(raw_view, list):
            raw_view = next((item for item in raw_view if isinstance(item, dict)), None)
        if not isinstance(raw_view, dict):
            return None
        raw_view = dict(raw_view)
        raw_view["diagram_type"] = "ibd"
        elements, id_map = self._normalize_diagram_elements(raw_view.get("elements"), "ibd")
        elements = [item for item in elements if item.get("type") in {"Block", "Interface"}]
        if len(elements) < 2:
            return None
        element_ids = {item["id"] for item in elements}
        relationships = self._normalize_diagram_relationships(raw_view.get("relationships"), element_ids, id_map, "ibd")
        if not relationships:
            relationships = self._candidate_internal_connectors(elements, "AI补充的候选内部连接。", "AI-IBD")
        focus = context["focus_element"]
        focus_name = str(focus.get("name") or focus.get("id") or "当前模块")
        focus_fragment = self._safe_id_fragment(str(focus.get("id") or focus_name))
        name = str(raw_view.get("name") or f"{focus_name} - 内部模块图（IBD）").strip()
        layout = self._normalize_or_build_diagram_layout(raw_view.get("layout"), {"name": name}, elements, relationships, "ibd")
        project_name = str(context.get("project_name") or "AI_MBSE_Project")
        return {
            "id": str(raw_view.get("id") or f"AI-{focus_fragment}-IBD").strip(),
            "variant_id": str(raw_view.get("variant_id") or f"AI-{focus_fragment}").strip(),
            "variant_name": str(raw_view.get("variant_name") or f"AI内部分解：{focus_name}").strip(),
            "diagram_type": "ibd",
            "focus_element_id": str(focus.get("id") or "").strip() or None,
            "name": name,
            "description": str(raw_view.get("description") or f"AI 根据当前模型上下文生成的 {focus_name} 内部模块图。").strip(),
            "rationale": str(raw_view.get("rationale") or "该图只展示当前 Block 内部 parts、接口和 connector，不包含模块用例图。").strip(),
            "elements": elements,
            "relationships": relationships,
            "layout": layout,
            "sysml_text": self._render_sysml_text(f"{project_name}_{focus_fragment}_IBD", elements, relationships),
            "trace_links": [],
        }

    def _fallback_internal_block_diagram(self, context: dict[str, Any]) -> dict[str, Any]:
        focus = context["focus_element"]
        elements = context.get("elements") or []
        relationships = context.get("relationships") or []
        focus_name = str(focus.get("name") or focus.get("id") or "当前模块")
        focus_fragment = self._safe_id_fragment(str(focus.get("id") or focus_name))
        existing_parts = self._existing_internal_parts(focus, elements, relationships)
        layout_style = self._internal_layout_style(f"{focus_name} {focus.get('description') or ''}")

        if len(existing_parts) >= 5:
            view_elements = [
                self._diagram_element(
                    str(item.get("id") or f"IBD-BLK-{index:03d}"),
                    str(item.get("name") or item.get("id") or f"内部模块{index}"),
                    "Interface" if item.get("type") == "Interface" else "Block",
                    str(item.get("description") or item.get("name") or ""),
                    "04_Interfaces" if item.get("type") == "Interface" else "02_Structure",
                )
                for index, item in enumerate(existing_parts, start=1)
            ]
            ids = {item["id"] for item in view_elements}
            view_relationships = [
                {
                    "id": f"DREL-{focus_fragment}-IBD-{index:03d}",
                    "source": str(rel.get("source")),
                    "target": str(rel.get("target")),
                    "type": "connector",
                    "description": str(rel.get("description") or f"{focus_name} 内部连接"),
                }
                for index, rel in enumerate(relationships, start=1)
                if rel.get("source") in ids and rel.get("target") in ids and rel.get("source") != rel.get("target")
            ]
            view_relationships = self._ensure_connected_diagram_relationships(
                view_elements,
                view_relationships,
                f"{focus_fragment}-IBD",
                f"AI 根据 {focus_name} 已有子模块补充的候选连接。",
            )
            view_relationships = self._augment_internal_relationships_by_layout(
                view_elements,
                view_relationships,
                layout_style,
                f"{focus_fragment}-IBD",
                f"AI 根据 {focus_name} 架构布局补充的非线性连接。",
            )
            rationale = "当前模型已存在该 Block 的 contains/接口相关元素，系统基于这些元素组织 IBD；缺少连接时由 AI 补充候选 connector。"
        else:
            view_elements, view_relationships, layout_style = self._dynamic_internal_parts_from_focus(context)
            rationale = "当前模型未显式定义足够完整的内部组成，系统根据 Block 名称、描述、相邻需求/接口和用户意图动态生成完整候选 IBD。"

        diagram_name = f"{focus_name} - 内部模块图（IBD）"
        layout = self._build_internal_block_layout(diagram_name, view_elements, view_relationships, layout_style)
        project_name = str(context.get("project_name") or "AI_MBSE_Project")
        return {
            "id": f"AI-{focus_fragment}-IBD",
            "variant_id": f"AI-{focus_fragment}",
            "variant_name": f"AI内部分解：{focus_name}",
            "diagram_type": "ibd",
            "focus_element_id": str(focus.get("id") or "").strip() or None,
            "name": diagram_name,
            "description": f"AI 构建的 {focus_name} 内部 parts、接口和 connector 候选视图。",
            "rationale": rationale,
            "elements": view_elements,
            "relationships": view_relationships,
            "layout": layout,
            "sysml_text": self._render_sysml_text(f"{project_name}_{focus_fragment}_IBD", view_elements, view_relationships),
            "trace_links": [],
        }

    def _existing_internal_parts(
        self,
        focus: dict[str, Any],
        elements: list[dict[str, Any]],
        relationships: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        focus_id = str(focus.get("id") or "")
        element_by_id = {str(item.get("id")): item for item in elements if item.get("id")}
        direct_ids = {
            str(rel.get("target"))
            for rel in relationships
            if str(rel.get("type") or "").lower() == "contains" and str(rel.get("source")) == focus_id and rel.get("target")
        }
        related_interface_ids = {
            endpoint
            for rel in relationships
            for endpoint in [str(rel.get("source") or ""), str(rel.get("target") or "")]
            if (
                (str(rel.get("source") or "") in direct_ids or str(rel.get("target") or "") in direct_ids or str(rel.get("source") or "") == focus_id or str(rel.get("target") or "") == focus_id)
                and element_by_id.get(endpoint, {}).get("type") == "Interface"
            )
        }
        ordered_ids = [item_id for item_id in [*direct_ids, *related_interface_ids] if item_id in element_by_id]
        seen: set[str] = set()
        result: list[dict[str, Any]] = []
        for item_id in ordered_ids:
            if item_id in seen:
                continue
            seen.add(item_id)
            item = element_by_id[item_id]
            if item.get("type") in {"Block", "Interface", "ConstraintBlock"}:
                result.append(item)
        return result[:10]

    def _dynamic_internal_parts_from_focus(self, context: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str]:
        focus = context["focus_element"]
        focus_name = str(focus.get("name") or focus.get("id") or "当前模块")
        focus_fragment = self._safe_id_fragment(str(focus.get("id") or focus_name))
        related_text = " ".join(self._related_context_for_focus(focus, context.get("elements") or [], context.get("relationships") or []))
        seed_text = " ".join(
            [
                str(focus.get("name") or ""),
                str(focus.get("description") or ""),
                str(context.get("prompt") or ""),
                related_text,
            ]
        )
        specs, connector_specs, layout_style = self._internal_architecture_profile(seed_text, focus_name, focus_fragment)
        view_elements = [
            self._diagram_element(element_id, name, element_type, description, "04_Interfaces" if element_type == "Interface" else "02_Structure")
            for element_id, name, element_type, description in specs
        ]
        view_relationships = [
            self._diagram_relationship(f"{focus_fragment}-IBD", index, source, target, "connector", description)
            for index, (source, target, description) in enumerate(connector_specs, start=1)
        ]
        return view_elements, view_relationships, layout_style

    def _internal_architecture_profile(
        self,
        text: str,
        focus_name: str,
        focus_fragment: str,
    ) -> tuple[list[tuple[str, str, str, str]], list[tuple[str, str, str]], str]:
        source = f"{focus_name} {text}"
        normalized = source.lower()
        subject = re.sub(r"(系统|分系统|子系统|模块|Block)$", "", focus_name).strip() or focus_name

        def element_id(kind: str, index: int) -> str:
            prefix = "IF" if kind == "Interface" else "BLK"
            return f"IBD-{prefix}-{focus_fragment}-{index:03d}"

        def build(
            layout_style: str,
            parts: list[tuple[str, str, str]],
            connectors: list[tuple[int, int, str]],
        ) -> tuple[list[tuple[str, str, str, str]], list[tuple[str, str, str]], str]:
            specs = [
                (
                    element_id(element_type, index),
                    name,
                    element_type,
                    description,
                )
                for index, (name, element_type, description) in enumerate(parts, start=1)
            ]
            relationships = [
                (specs[source_index - 1][0], specs[target_index - 1][0], description)
                for source_index, target_index, description in connectors
                if 0 < source_index <= len(specs) and 0 < target_index <= len(specs) and source_index != target_index
            ]
            return specs, relationships, layout_style

        if any(keyword in focus_name for keyword in ["空间段", "星座", "轨道面", "轨道构型", "覆盖"]):
            return build(
                "network",
                [
                    ("轨道壳层与星座构型单元", "Block", f"定义{focus_name}的轨道面、相位、星间几何和覆盖边界。"),
                    ("在轨卫星群管理单元", "Block", "维护单星清单、状态、轨道参数和服务角色。"),
                    ("星间链路与空间路由网络", "Block", "支撑跨星转发、空间路由、链路重构和负载均衡。"),
                    ("用户链路覆盖资源", "Block", "管理用户波束、频率、容量和区域覆盖资源。"),
                    ("馈电链路可见性管理", "Block", "评估网关可见窗口、回传路径和链路余量。"),
                    ("覆盖与容量调度器", "Block", "根据业务需求、星座状态和区域负载生成调度策略。"),
                    ("星座健康与告警汇聚", "Block", "汇聚单星、链路、网关和业务运行状态。"),
                    ("运控/网管接口", "Interface", "与任务运控、网络运营和外部业务系统交互。"),
                ],
                [(1, 2, "轨道构型约束在轨卫星群管理"), (2, 3, "卫星群状态输入空间路由网络"), (3, 4, "空间路由支撑用户链路覆盖"), (3, 5, "空间路由连接馈电链路路径"), (4, 6, "用户覆盖资源输入容量调度器"), (5, 6, "网关可见性输入容量调度器"), (7, 6, "健康状态约束调度策略"), (8, 6, "运控/网管策略输入调度器"), (6, 3, "调度策略回写空间路由网络")],
            )

        specific_non_payload = any(
            keyword in focus_name
            for keyword in [
                "空间段",
                "星座",
                "轨道",
                "卫星平台",
                "单颗卫星",
                "平台",
                "测控站",
                "关口站",
                "信关站",
                "地面站",
                "网关",
                "地面段",
                "星间",
                "链路终端",
                "天线",
                "无线接口",
                "用户终端",
                "用户段",
                "运控",
                "控制中心",
            ]
        )

        if any(keyword in source for keyword in ["通信载荷", "载荷", "基带", "信道", "波束", "功放"]) and not specific_non_payload:
            return build(
                "pipeline_control",
                [
                    ("多波束用户链路接口", "Interface", f"定义{focus_name}面向用户链路的射频输入/输出边界。"),
                    ("低噪声接收与变频链", "Block", "完成低噪声放大、下变频、滤波和增益控制。"),
                    ("数字信道化处理器", "Block", "完成信道化、解调解码、通道映射和业务流提取。"),
                    ("星上交换与路由处理器", "Block", "执行星上交换、路由选择、队列调度和跨链路转发。"),
                    ("功放与馈电发射链", "Block", "完成上变频、功率放大、线性化和馈电/下行发射。"),
                    ("馈电链路接口", "Interface", "连接馈电链路、网关站和地面核心网回传边界。"),
                    ("载荷控制与资源调度单元", "Block", "配置波束、频率、通道、功率和载荷工作模式。"),
                    ("载荷遥测与健康监测单元", "Block", "采集功率、温度、电流、开关状态和告警。"),
                ],
                [(1, 2, "用户链路射频信号进入接收变频链"), (2, 3, "变频后的信号进入数字信道化处理"), (3, 4, "业务流进入星上交换与路由"), (4, 5, "路由结果驱动馈电/下行发射链"), (5, 6, "发射链输出到馈电链路接口"), (7, 3, "资源策略配置到信道化处理器"), (7, 4, "调度策略配置到交换路由处理器"), (8, 7, "健康状态反馈到载荷控制单元"), (8, 5, "功放状态用于保护与降额控制")],
            )

        if any(keyword in focus_name for keyword in ["卫星平台", "单颗卫星", "平台", "星务", "姿轨控", "电源", "热控", "推进"]):
            return build(
                "hub",
                [
                    ("星务计算机/平台数据总线", "Block", f"作为{focus_name}的平台控制、数据交换和模式管理核心。"),
                    ("电源调节与配电单元", "Block", "提供母线电源、负载配电、功率遥测和保护。"),
                    ("姿轨控与导航单元", "Block", "完成姿态确定、轨道控制、指向保持和机动控制。"),
                    ("热控管理单元", "Block", "管理温度采集、加热器、散热器和热控回路。"),
                    ("推进执行单元", "Block", "执行轨道维持、避碰机动、卸载和姿态辅助控制。"),
                    ("测控与星地遥测接口", "Interface", "连接遥测遥控、时间同步和地面运控链路。"),
                    ("载荷服务接口", "Interface", "向通信载荷提供功率、热控、数据和控制服务。"),
                    ("安全模式与故障管理单元", "Block", "执行故障检测、隔离、恢复和安全模式切换。"),
                ],
                [(1, 2, "星务计算机调度平台供配电"), (1, 3, "星务计算机下发姿轨控任务"), (1, 4, "星务计算机同步热控策略"), (1, 5, "星务计算机触发推进机动"), (1, 6, "星务计算机汇聚遥测并接收遥控"), (1, 7, "平台服务通过载荷接口交付"), (8, 1, "故障管理单元监控平台核心状态"), (8, 2, "故障保护约束供配电"), (8, 5, "安全模式限制推进执行")],
            )

        if any(keyword in focus_name for keyword in ["测控站", "关口站", "信关站", "地面站", "网关", "地面段", "核心网"]):
            return build(
                "layered",
                [
                    ("地面天线与跟踪伺服", "Block", f"完成{focus_name}的卫星捕获、跟踪和射频/光学指向。"),
                    ("射频/光电前端", "Block", "完成上下变频、低噪声接收、功放和链路保护。"),
                    ("调制解调与基带处理", "Block", "完成波形处理、同步、编码解码和帧处理。"),
                    ("网关路由与业务汇聚", "Block", "承载业务汇聚、路由转发、QoS和核心网接入。"),
                    ("核心网/互联网接口", "Interface", "连接地面核心网、互联网出口和业务平台。"),
                    ("站控监控与告警单元", "Block", "监控设备状态、告警、配置和自动化运维。"),
                    ("时间频率与同步单元", "Block", "提供站内时频基准、同步分发和时间戳服务。"),
                    ("供配电与环境保障接口", "Interface", "连接供电、机房环境、冷却和安防系统。"),
                ],
                [(1, 2, "天线接收/发射链路连接射频前端"), (2, 3, "射频信号进入基带处理"), (3, 4, "基带业务流进入网关汇聚"), (4, 5, "业务流接入核心网/互联网"), (6, 1, "站控单元控制天线跟踪"), (6, 2, "站控单元配置射频前端"), (6, 4, "站控单元监控业务网关"), (7, 3, "时频同步提供给基带处理"), (8, 6, "环境与电源状态反馈到站控监控")],
            )

        if any(keyword in source for keyword in ["星间", "链路终端", "天线", "用户链路", "馈电链路", "无线接口", "激光"]):
            return build(
                "loop",
                [
                    ("孔径/天线与指向机构", "Block", f"形成{focus_name}的空间指向、波束覆盖和收发孔径。"),
                    ("捕获跟踪与波束控制", "Block", "完成捕获、跟踪、波束赋形、指向保持和切换控制。"),
                    ("射频/光学收发前端", "Block", "完成收发放大、滤波、变频、光电转换或链路保护。"),
                    ("调制解调与链路波形处理", "Block", "完成同步、调制解调、编码解码和链路自适应。"),
                    ("链路控制与切换管理", "Block", "执行链路建立、保持、切换、重构和资源协商。"),
                    ("加密/QoS与业务适配", "Block", "执行安全封装、业务分类、QoS和协议适配。"),
                    ("网络/载荷接口", "Interface", "连接载荷处理、星上路由、用户终端或网关网络。"),
                    ("功率热控与遥测接口", "Interface", "提供供电、热控、遥测遥控和健康管理边界。"),
                ],
                [(1, 2, "孔径姿态状态输入波束控制"), (2, 3, "波束控制驱动收发前端"), (3, 4, "收发前端连接波形处理"), (4, 5, "链路质量反馈给切换管理"), (5, 6, "链路控制策略传递给业务适配"), (6, 7, "适配后的业务接入网络/载荷接口"), (8, 3, "功率热控支撑收发前端"), (8, 5, "遥测状态约束链路控制"), (5, 2, "切换管理回控波束指向")],
            )

        if any(keyword in source for keyword in ["运控", "控制中心", "网络运营", "调度", "管理中心"]):
            return build(
                "network",
                [
                    ("任务规划与策略配置台", "Block", f"定义{focus_name}的任务计划、业务策略和运行约束。"),
                    ("星座状态数据库", "Block", "汇聚轨道、链路、网关、载荷和健康状态。"),
                    ("资源调度与覆盖优化引擎", "Block", "计算星座资源、波束、频率、网关和路由策略。"),
                    ("测控/网管南向接口", "Interface", "下发遥控、网管、调度和配置指令。"),
                    ("故障告警与恢复编排单元", "Block", "执行告警关联、影响分析、隔离、降级和恢复。"),
                    ("运行态势与操作员界面", "Block", "展示星座态势、任务状态和人工确认操作。"),
                    ("仿真评估与方案推演单元", "Block", "对调度方案、故障恢复和容量覆盖进行推演评估。"),
                    ("外部业务/运营接口", "Interface", "连接业务支撑系统、客户运营系统和服务保障平台。"),
                ],
                [(1, 3, "任务策略输入调度优化引擎"), (2, 3, "星座状态支撑优化计算"), (3, 4, "调度结果通过南向接口下发"), (5, 3, "故障恢复约束资源调度"), (2, 5, "状态数据库触发告警关联"), (3, 6, "优化结果展示到态势界面"), (7, 3, "推演结果校核调度方案"), (8, 1, "外部业务需求输入任务规划")],
            )

        if any(keyword in source for keyword in ["用户终端", "终端设备", "用户段"]):
            return build(
                "pipeline_control",
                [
                    ("用户侧业务接口", "Interface", "连接用户设备、业务应用或局域网。"),
                    ("终端协议与会话管理", "Block", "完成接入认证、会话保持、地址管理和业务分类。"),
                    ("卫星调制解调器", "Block", "完成链路同步、调制解调、编码解码和速率自适应。"),
                    ("射频前端与功放", "Block", "完成上下变频、低噪声接收、发射功放和保护。"),
                    ("相控阵/跟踪天线", "Block", "完成波束指向、卫星跟踪和链路切换。"),
                    ("星地无线接口", "Interface", "承载用户终端与低轨卫星之间的无线链路。"),
                    ("终端控制与安全单元", "Block", "执行认证、密钥、策略、终端配置和安全保护。"),
                    ("电源与环境监测接口", "Interface", "连接电池、外部供电、温度和设备健康监测。"),
                ],
                [(1, 2, "用户业务进入协议会话管理"), (2, 3, "业务流进入卫星调制解调器"), (3, 4, "调制信号进入射频前端"), (4, 5, "射频链路驱动天线发射/接收"), (5, 6, "天线形成星地无线链路"), (7, 2, "安全策略约束会话管理"), (7, 3, "链路参数配置调制解调器"), (8, 7, "电源环境状态反馈到终端控制")],
            )

        phrases = self._internal_part_phrases(text, focus_name)
        return build(
            "pipeline_control",
            [
                (f"{subject}输入接口", "Interface", f"接入 {focus_name} 的外部任务、数据、信号、控制或资源输入。"),
                (f"{phrases[0]}接入与整形单元", "Block", f"完成 {phrases[0]} 相关输入接入、格式整形、初步校核或信号调理。"),
                (f"{phrases[1]}处理单元", "Block", f"承担 {phrases[1]} 相关核心处理、转换、分析或计算职责。"),
                (f"{phrases[2]}控制管理单元", "Block", f"执行 {phrases[2]} 相关模式控制、参数配置、调度或策略管理。"),
                (f"{phrases[3]}执行输出单元", "Block", f"将内部处理结果转换为 {phrases[3]} 相关输出、转发、执行或服务交付。"),
                (f"{subject}输出接口", "Interface", f"对外交付 {focus_name} 的处理结果、业务数据、状态或服务输出。"),
                ("状态监测与保护单元", "Block", f"采集 {focus_name} 内部状态、健康遥测、告警和保护动作。"),
                ("平台资源接口", "Interface", f"连接供电、热控、时间同步、遥测遥控或平台支撑资源。"),
            ],
            [(1, 2, "输入边界到接入整形链路"), (2, 3, "接入整形结果进入核心处理"), (3, 4, "处理状态与控制管理交互"), (4, 5, "控制参数驱动执行输出"), (5, 6, "执行输出交付到外部接口"), (7, 3, "健康状态反馈到核心处理"), (7, 4, "告警与保护策略反馈到控制管理"), (8, 7, "平台资源和遥测支撑状态监测")],
        )

    def _internal_layout_style(self, text: str) -> str:
        if any(keyword in text for keyword in ["星座", "空间段", "轨道", "覆盖", "构型"]):
            return "network"
        if any(keyword in text for keyword in ["卫星平台", "平台", "星务", "电源", "热控", "姿轨控", "推进"]):
            return "hub"
        if any(keyword in text for keyword in ["测控站", "关口站", "信关站", "地面站", "网关", "地面段", "核心网"]):
            return "layered"
        if any(keyword in text for keyword in ["星间", "链路终端", "天线", "无线接口", "激光"]):
            return "loop"
        if any(keyword in text for keyword in ["运控", "控制中心", "网络运营", "调度"]):
            return "network"
        if any(keyword in text for keyword in ["数字处理", "处理器", "路由", "交换", "核心网"]):
            return "layered"
        return "pipeline_control"

    def _build_internal_block_layout(
        self,
        diagram_name: str,
        elements: list[dict[str, Any]],
        relationships: list[dict[str, Any]],
        layout_style: str,
    ) -> dict[str, Any]:
        nodes: list[dict[str, Any]] = []

        def node(item: dict[str, Any], x: int, y: int, width: int = 230, height: int = 76) -> dict[str, Any]:
            return {
                "id": item["id"],
                "element_id": item["id"],
                "name": item["name"],
                "label": item["name"],
                "type": item["type"],
                "stereotype_label": "interface" if item["type"] == "Interface" else "part",
                "shape": "soft" if item["type"] == "Interface" else "rect",
                "x": x,
                "y": y,
                "width": width,
                "height": height,
            }

        if layout_style == "hub" and elements:
            center = elements[0]
            nodes.append(node(center, 480, 250, 260, 82))
            coords = [(100, 80), (480, 80), (860, 80), (100, 430), (480, 430), (860, 430), (100, 250)]
            for item, (x, y) in zip(elements[1:], coords):
                nodes.append(node(item, x, y, 245, 76))
            width, height = 1180, 620
        elif layout_style == "layered":
            layer_coords = [(95, 90), (395, 90), (695, 90), (995, 90), (245, 300), (545, 300), (845, 300), (395, 500), (695, 500), (995, 500)]
            for item, (x, y) in zip(elements, layer_coords):
                nodes.append(node(item, x, y, 235, 78))
            width, height = 1240, max(560, 260 + ((len(elements) + 3) // 4) * 180)
        elif layout_style == "loop":
            coords = [(120, 100), (500, 80), (880, 100), (1010, 310), (760, 470), (400, 470), (100, 310), (500, 280)]
            for item, (x, y) in zip(elements, coords):
                nodes.append(node(item, x, y, 240, 78))
            width, height = 1280, 650
        elif layout_style == "network":
            coords = [(480, 95), (120, 250), (480, 250), (840, 250), (120, 435), (480, 435), (840, 435), (300, 620), (660, 620), (1000, 620)]
            for item, (x, y) in zip(elements, coords):
                nodes.append(node(item, x, y, 250, 78))
            width, height = 1280, 780
        else:
            main_count = min(6, len(elements))
            for index, item in enumerate(elements[:main_count]):
                nodes.append(node(item, 70 + index * 225, 110, 205, 76))
            for index, item in enumerate(elements[main_count:]):
                nodes.append(node(item, 260 + index * 330, 330, 245, 78))
            width, height = max(1240, 180 + main_count * 225), 560

        layout = self._diagram_layout(diagram_name, nodes, relationships, width, height)
        layout["diagram_type"] = "ibd"
        return layout

    def _internal_part_phrases(self, text: str, focus_name: str) -> list[str]:
        normalized_text = re.sub(r"(以及|和|与|及)", "，", text)
        raw_phrases = self._brief_phrases(normalized_text)
        cleaned: list[str] = []
        for phrase in raw_phrases:
            for chunk in re.split(r"(?:和|与|及|以及)", phrase):
                item = re.sub(r"(负责|支持|完成|执行|提供|管理|当前|模型|模块|系统|分系统|需求|能力)$", "", chunk).strip()
                item = re.sub(r"^(负责|支持|完成|执行|提供|管理)", "", item).strip()
                if not item or item in focus_name or focus_name in item:
                    continue
                if item not in cleaned:
                    cleaned.append(item[:10])
        fallback_subject = re.sub(r"(系统|分系统|子系统|模块|Block)$", "", focus_name).strip() or focus_name
        fallback = [f"{fallback_subject}输入", f"{fallback_subject}核心", f"{fallback_subject}控制", f"{fallback_subject}输出", f"{fallback_subject}状态"]
        for item in fallback:
            if item not in cleaned:
                cleaned.append(item[:10])
            if len(cleaned) >= 5:
                break
        return cleaned[:5]

    def _ensure_connected_diagram_relationships(
        self,
        elements: list[dict[str, Any]],
        relationships: list[dict[str, Any]],
        prefix: str,
        description: str,
    ) -> list[dict[str, Any]]:
        result = [dict(item) for item in relationships if isinstance(item, dict)]
        existing_pairs = {
            frozenset([str(item.get("source") or ""), str(item.get("target") or "")])
            for item in result
            if item.get("source") and item.get("target")
        }
        used_ids = {str(item.get("id") or "") for item in result}
        next_index = len(result) + 1
        for source, target in zip(elements, elements[1:]):
            pair = frozenset([str(source.get("id") or ""), str(target.get("id") or "")])
            if len(pair) < 2 or pair in existing_pairs:
                continue
            rel_id = f"DREL-{prefix}-{next_index:03d}"
            while rel_id in used_ids:
                next_index += 1
                rel_id = f"DREL-{prefix}-{next_index:03d}"
            result.append(
                {
                    "id": rel_id,
                    "source": source["id"],
                    "target": target["id"],
                    "type": "connector",
                    "description": description,
                }
            )
            existing_pairs.add(pair)
            used_ids.add(rel_id)
            next_index += 1
        return result

    def _augment_internal_relationships_by_layout(
        self,
        elements: list[dict[str, Any]],
        relationships: list[dict[str, Any]],
        layout_style: str,
        prefix: str,
        description: str,
    ) -> list[dict[str, Any]]:
        result = [dict(item) for item in relationships if isinstance(item, dict)]
        used_ids = {str(item.get("id") or "") for item in result}
        pairs = {
            (str(item.get("source") or ""), str(item.get("target") or ""))
            for item in result
            if item.get("source") and item.get("target")
        }

        def add(source_index: int, target_index: int, detail: str) -> None:
            if not (0 <= source_index < len(elements) and 0 <= target_index < len(elements)) or source_index == target_index:
                return
            source = str(elements[source_index].get("id") or "")
            target = str(elements[target_index].get("id") or "")
            if not source or not target or (source, target) in pairs or (target, source) in pairs:
                return
            rel_id = f"DREL-{prefix}-AUG-{len(result) + 1:03d}"
            suffix = 2
            while rel_id in used_ids:
                rel_id = f"DREL-{prefix}-AUG-{len(result) + 1:03d}-{suffix}"
                suffix += 1
            result.append(
                {
                    "id": rel_id,
                    "source": source,
                    "target": target,
                    "type": "connector",
                    "description": detail or description,
                }
            )
            used_ids.add(rel_id)
            pairs.add((source, target))

        if layout_style == "hub":
            for index in range(1, min(len(elements), 8)):
                add(0, index, "中心平台/总线与该内部单元交换控制、数据或资源。")
            add(7, 1, "故障管理或健康监测约束供配电与资源分配。")
            add(7, 4, "故障管理触发执行单元降级或保护。")
        elif layout_style == "network":
            center = 2 if len(elements) > 3 else 0
            for index in range(len(elements)):
                if index != center:
                    add(center, index, "核心调度/状态节点与相关内部单元交换状态和策略。")
            add(0, 3, "上层规划结果驱动下游接口或执行节点。")
            add(4, 2, "故障/状态反馈影响核心调度节点。")
        elif layout_style == "layered":
            for source_index, target_index in [(0, 1), (1, 2), (2, 3), (3, 4), (5, 1), (5, 3), (6, 2), (7, 5)]:
                add(source_index, target_index, "分层架构中相邻处理层或支撑层之间的连接。")
        elif layout_style == "loop":
            for source_index, target_index in [(0, 1), (1, 2), (2, 3), (3, 4), (4, 5), (5, 6), (7, 2), (4, 1), (6, 0)]:
                add(source_index, target_index, "闭环链路控制、状态反馈或接口交互连接。")
        return result

    def _candidate_internal_connectors(self, elements: list[dict[str, Any]], description: str, prefix: str = "IBD-CANDIDATE") -> list[dict[str, Any]]:
        if len(elements) < 2:
            return []
        relationships: list[dict[str, Any]] = []
        for index, (source, target) in enumerate(zip(elements, elements[1:]), start=1):
            relationships.append(
                {
                    "id": f"DREL-{prefix}-{index:03d}",
                    "source": source["id"],
                    "target": target["id"],
                    "type": "connector",
                    "description": description,
                }
            )
        return relationships

    def _related_context_for_focus(
        self,
        focus: dict[str, Any],
        elements: list[dict[str, Any]],
        relationships: list[dict[str, Any]],
    ) -> list[str]:
        focus_id = str(focus.get("id") or "")
        element_by_id = {str(item.get("id")): item for item in elements if item.get("id")}
        related_ids = {
            endpoint
            for rel in relationships
            if str(rel.get("source") or "") == focus_id or str(rel.get("target") or "") == focus_id
            for endpoint in [str(rel.get("source") or ""), str(rel.get("target") or "")]
            if endpoint and endpoint != focus_id
        }
        snippets = [str(focus.get("description") or "")]
        for item_id in list(related_ids)[:12]:
            item = element_by_id.get(item_id)
            if item:
                snippets.append(f"{item.get('type')} {item.get('name')}: {item.get('description')}")
        return [item for item in snippets if str(item).strip()]

    def _safe_id_fragment(self, value: str) -> str:
        cleaned = re.sub(r"[^0-9A-Za-z]+", "-", str(value or "").strip()).strip("-").upper()
        return cleaned or "FOCUS"

    def _fallback_project_from_dialogue(self, brief: str, project_name: str | None = None) -> dict[str, Any]:
        domain = self._detect_domain(brief)
        if domain in {"satellite", "radar", "aircraft", "vehicle"}:
            return self._curated_project_from_dialogue(domain, brief, project_name)

        package_name = self._safe_name(project_name or self._dynamic_project_name(brief))
        elements = self._dynamic_elements_from_brief(brief)
        relationships = self._dynamic_relationships(elements)
        sysml_text = self._render_sysml_text(package_name, elements, relationships)

        return {
            "project_name": package_name,
            "summary": (
                f"大模型未返回可解析的结构化JSON，已根据当前对话文本动态生成候选SysML工程："
                f"{len(elements)}个模型元素、{len(relationships)}条关系。输入摘要：{brief[:180].replace(chr(10), ' ')}"
            ),
            "assumptions": [
                "该工程由对话文本动态抽取生成，建议继续让AI补充更明确的需求、接口、指标和验收条件。",
                "未使用固定行业模板；元素名称和关系来自当前对话中的主题词与功能短语。",
            ],
            "generation_source": "dynamic_fallback",
            "elements": elements,
            "relationships": relationships,
            "sysml_text": sysml_text,
        }

    def _curated_project_from_dialogue(self, domain: str, brief: str, project_name: str | None = None) -> dict[str, Any]:
        package_name = self._safe_name(self._project_name_for_domain(project_name, domain))
        elements = self._project_elements(domain, brief)
        relationships = self._project_relationships(domain)
        return {
            "project_name": package_name,
            "summary": self._project_summary(domain, brief, elements, relationships),
            "assumptions": self._project_assumptions(domain),
            "generation_source": "curated_fallback",
            "elements": elements,
            "relationships": relationships,
            "sysml_text": self._render_sysml_text(package_name, elements, relationships),
        }

    def classify_modeling_intent(
        self,
        conversation: list[dict[str, Any]] | None = None,
        message: str = "",
    ) -> dict[str, Any]:
        message_text = str(message or "").strip()
        brief = self._dialogue_brief(conversation or [], message_text)
        local_result = self._local_modeling_intent(message_text, brief)
        if local_result["confidence"] >= 0.9:
            return local_result

        llm_result = self._classify_modeling_intent_with_llm(brief, message_text)
        return llm_result or local_result

    def _classify_modeling_intent_with_llm(self, brief: str, message: str) -> dict[str, Any] | None:
        try:
            from app.services.llm_service import LLMService

            prompt = f"""
请判断用户最新输入是否要求生成、重建、修改或同步 SysML/MBSE 工程模型。

判定为 false 的情况：
- 寒暄，例如“在吗”“你好”
- 普通问答、解释、排错、咨询
- 只是问系统能力或问如何实现某个功能

判定为 true 的情况：
- 明确要求生成/创建/构建/更新/补充/完善/校验 SysML、MBSE、模型、工程、需求、模块、用例、接口、活动、约束、关系、MagicDraw 工程
- 要求根据当前对话重新生成右侧模型或推送 MagicDraw

最新输入：
{message}

完整上下文：
{brief}

只返回 JSON：
{{"should_generate": false, "intent": "chat", "confidence": 0.0, "reason": "简短原因"}}
""".strip()
            result = LLMService().chat([{"role": "user", "content": prompt}], task_type="intent_classification")
            data = self._try_parse_json_object(str(result.get("answer") or ""))
            if not data:
                return None
            should_generate = bool(data.get("should_generate"))
            confidence = self._clamp_float(data.get("confidence"), 0.0, 1.0)
            intent = str(data.get("intent") or ("sysml_generation" if should_generate else "chat")).strip()
            reason = str(data.get("reason") or ("识别为建模任务" if should_generate else "识别为普通对话")).strip()
            return {
                "should_generate": should_generate,
                "intent": intent or ("sysml_generation" if should_generate else "chat"),
                "confidence": confidence,
                "reason": reason,
            }
        except Exception:
            return None

    def _local_modeling_intent(self, message: str, brief: str) -> dict[str, Any]:
        text = str(message or "").strip()
        compact = re.sub(r"\s+", "", text).lower()
        trivial_inputs = {
            "在吗",
            "你好",
            "您好",
            "hi",
            "hello",
            "hey",
            "谢谢",
            "多谢",
            "收到",
            "ok",
            "好的",
            "你在吗",
        }
        if compact in trivial_inputs or (len(compact) <= 4 and not re.search(r"(画|建|生成|模型|sysml|mbse)", compact, re.IGNORECASE)):
            return {
                "should_generate": False,
                "intent": "chat",
                "confidence": 0.98,
                "reason": "最新输入是寒暄或普通短句，不触发SysML工程生成。",
            }

        model_terms = [
            "sysml",
            "mbse",
            "magicdraw",
            "模型",
            "系统",
            "总体",
            "工程",
            "建模",
            "需求",
            "模块",
            "用例",
            "接口",
            "活动",
            "约束",
            "关系",
            "追溯",
            "画布",
            "右侧",
            "方案",
            "飞机",
            "航空器",
            "飞行器",
            "无人机",
            "卫星",
            "星座",
            "雷达",
        ]
        action_terms = [
            "生成",
            "创建",
            "构建",
            "建立",
            "设计",
            "重建",
            "更新",
            "修改",
            "补充",
            "完善",
            "同步",
            "推送",
            "导入",
            "校验",
            "验证",
            "重新生成",
        ]
        lower_text = text.lower()
        has_model_term = any(term.lower() in lower_text for term in model_terms)
        has_action_term = any(term in text for term in action_terms)
        asks_how = bool(re.search(r"(怎么|如何|为什么|是什么|能不能|是否|介绍|解释|说明|该如何)", text))

        if has_model_term and has_action_term and not asks_how:
            return {
                "should_generate": True,
                "intent": "sysml_generation",
                "confidence": 0.92,
                "reason": "最新输入包含建模对象和生成/修改类动作。",
            }
        if has_model_term and asks_how:
            return {
                "should_generate": False,
                "intent": "chat",
                "confidence": 0.65,
                "reason": "最新输入更像关于建模能力或实现方式的问答，不直接生成工程。",
            }
        if has_action_term and any(term in lower_text for term in ["总体方案", "系统方案", "方案", "project"]):
            return {
                "should_generate": True,
                "intent": "sysml_generation",
                "confidence": 0.9,
                "reason": "最新输入要求生成系统/总体方案，可触发工程模型生成。",
            }
        return {
            "should_generate": False,
            "intent": "chat",
            "confidence": 0.55,
            "reason": "未识别到明确的SysML工程生成或修改意图。",
        }

    def _clamp_float(self, value: Any, low: float, high: float) -> float:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            parsed = low
        return max(low, min(high, parsed))

    def _dynamic_project_name(self, brief: str) -> str:
        title = self._brief_title(brief)
        if not title or title.lower() == "dynamic":
            title = "动态系统"
        return f"{self._safe_name(title)}MBSE工程"

    def _brief_title(self, brief: str) -> str:
        text = re.sub(r"\s+", "", str(brief or ""))
        text = re.sub(r"(请|帮我|根据|对话|结果|生成|一个|一套|总体|方案|系统|工程|模型|SysML|MBSE)", "", text, flags=re.IGNORECASE)
        text = re.split(r"[，。；;,.!?！？\n]", text)[0]
        return text[:18] or "Dynamic"

    def _dynamic_elements_from_brief(self, brief: str) -> list[dict[str, Any]]:
        topic = self._brief_title(brief)
        phrases = self._brief_phrases(brief)
        elements: list[dict[str, Any]] = [
            self._element("BLK-001", f"{topic}系统", "Block", f"根据当前对话抽取的系统根模块：{brief[:120].replace(chr(10), ' ')}"),
        ]

        for index, phrase in enumerate(phrases[:8], start=1):
            elements.append(self._element(f"REQ-{index:03d}", f"{phrase}需求", "Requirement", f"系统应覆盖或满足对话中提到的“{phrase}”相关要求。"))

        for index, phrase in enumerate(phrases[:6], start=1):
            elements.append(self._element(f"BLK-{index + 1:03d}", f"{phrase}子系统", "Block", f"承担“{phrase}”相关功能、资源或状态管理。"))

        for index, phrase in enumerate(phrases[:5], start=1):
            elements.append(self._element(f"UC-{index:03d}", f"执行{phrase}", "UseCase", f"围绕“{phrase}”形成用户、外部系统或内部流程交互场景。"))

        interface_phrases = self._select_interface_phrases(phrases)
        for index, phrase in enumerate(interface_phrases[:5], start=1):
            elements.append(self._element(f"IF-{index:03d}", f"{phrase}接口", "Interface", f"承载“{phrase}”相关数据、控制、状态或资源交互。"))

        for index, phrase in enumerate(phrases[:5], start=1):
            elements.append(self._element(f"ACT-{index:03d}", f"{phrase}流程", "Activity", f"描述“{phrase}”从触发、处理、反馈到闭环确认的活动流程。"))

        constraint_phrases = self._select_constraint_phrases(phrases)
        for index, phrase in enumerate(constraint_phrases[:4], start=1):
            elements.append(self._element(f"CON-{index:03d}", f"{phrase}约束", "ConstraintBlock", f"对“{phrase}”相关性能、资源、可靠性或安全条件进行约束表达。"))

        return elements

    def _brief_phrases(self, brief: str) -> list[str]:
        text = re.sub(r"[：:()（）\[\]【】]", "，", str(brief or ""))
        raw_parts = re.split(r"[\n，,、；;。.!！?？\s]+", text)
        stop_words = {
            "请",
            "帮我",
            "根据",
            "对话",
            "结果",
            "生成",
            "一个",
            "一套",
            "总体",
            "方案",
            "系统",
            "工程",
            "模型",
            "包含",
            "以及",
            "和",
            "与",
            "的",
            "AI",
            "SysML",
            "MBSE",
        }
        phrases: list[str] = []
        for part in raw_parts:
            cleaned = part.strip()
            if not cleaned or cleaned in stop_words:
                continue
            cleaned = re.sub(r"(请|帮我|根据|对话|结果|生成|一个|一套|总体|方案|系统|工程|模型|包含|以及|和|与)", "", cleaned)
            cleaned = re.sub(r"(需求|能力|功能|方案|系统|工程|模型)$", "", cleaned)
            if len(cleaned) < 2 and not re.search(r"[A-Za-z0-9]{2,}", cleaned):
                continue
            if cleaned not in phrases:
                phrases.append(cleaned[:18])

        if not phrases:
            phrases = [self._brief_title(brief)]
        return phrases[:12]

    def _select_interface_phrases(self, phrases: list[str]) -> list[str]:
        preferred = [item for item in phrases if any(key in item for key in ["接口", "通信", "数据", "总线", "链路", "遥测", "控制", "能源", "供电"])]
        return preferred or phrases

    def _select_constraint_phrases(self, phrases: list[str]) -> list[str]:
        preferred = [item for item in phrases if any(key in item for key in ["约束", "指标", "性能", "安全", "可靠", "功耗", "能源", "时延", "精度", "容量"])]
        return preferred or phrases[-4:] or phrases

    def _dynamic_relationships(self, elements: list[dict[str, Any]]) -> list[dict[str, Any]]:
        by_type: dict[str, list[str]] = {}
        for item in elements:
            by_type.setdefault(str(item["type"]), []).append(str(item["id"]))

        relationships: list[dict[str, Any]] = []
        rel_index = 1
        root = by_type.get("Block", [elements[0]["id"]])[0]
        for block_id in by_type.get("Block", [])[1:]:
            relationships.append(self._relationship(rel_index, root, block_id, "contains", "系统根模块包含该动态抽取子系统。"))
            rel_index += 1

        blocks = by_type.get("Block", [root])
        use_cases = by_type.get("UseCase", [])
        activities = by_type.get("Activity", [])
        interfaces = by_type.get("Interface", [])
        constraints = by_type.get("ConstraintBlock", [])

        for index, req_id in enumerate(by_type.get("Requirement", []), start=1):
            block_id = blocks[(index - 1) % len(blocks)]
            relationships.append(self._relationship(rel_index, block_id, req_id, "satisfy", "动态抽取模块满足对应需求。"))
            rel_index += 1
            if use_cases:
                relationships.append(self._relationship(rel_index, req_id, use_cases[(index - 1) % len(use_cases)], "trace", "需求追溯到对应用例。"))
                rel_index += 1
            if constraints:
                relationships.append(self._relationship(rel_index, constraints[(index - 1) % len(constraints)], req_id, "verify", "约束块验证对应需求。"))
                rel_index += 1

        for index, interface_id in enumerate(interfaces, start=1):
            relationships.append(self._relationship(rel_index, interface_id, blocks[index % len(blocks)], "allocate", "接口分配到相关模块。"))
            rel_index += 1

        for index, use_case_id in enumerate(use_cases, start=1):
            if activities:
                relationships.append(self._relationship(rel_index, use_case_id, activities[(index - 1) % len(activities)], "trace", "用例细化为活动流程。"))
                rel_index += 1

        return relationships

    def _relationship(self, index: int, source: str, target: str, rel_type: str, description: str) -> dict[str, Any]:
        return {
            "id": f"REL-{index:03d}",
            "source": source,
            "target": target,
            "type": rel_type,
            "description": description,
        }

    def _generate_project_with_llm(self, brief: str, project_name: str | None = None) -> dict[str, Any] | None:
        try:
            from app.services.llm_service import LLMService

            prompt = self._llm_project_prompt(brief, project_name)
            result = LLMService().chat(
                [
                    {
                        "role": "system",
                        "content": (
                            "你是资深 MBSE/SysML 总体建模专家。你必须根据用户和 AI 的完整对话内容动态生成模型，"
                            "不要套用固定行业模板。只返回 JSON，不要返回 Markdown。"
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                task_type="model_generation",
            )
            data = self._try_parse_json_object(str(result.get("answer") or ""))
            if not data:
                return None
            return self._normalize_llm_project(data, brief, project_name)
        except Exception:
            return None

    def _llm_project_prompt(self, brief: str, project_name: str | None = None) -> str:
        requested_name = str(project_name or "").strip()
        name_rule = (
            f"如用户指定工程名，可使用或规范化为：{requested_name}。"
            if requested_name
            else "请根据对话主题生成简洁、可作为包名的 project_name。"
        )
        return f"""
请基于下面的完整交互上下文重新生成一个 SysML 工程模型。模型内容必须来自对话中的任务目标、指标、边界、功能、接口、约束和 AI 回复，不要使用预置模板。

交互上下文：
{brief}

输出要求：
1. 只输出一个 JSON 对象，不要 Markdown，不要解释。
2. {name_rule}
3. elements 至少覆盖 Requirement、Block、UseCase、Interface、Activity、ConstraintBlock 中的 4 类以上；如果对话信息不足，可合理补充候选项，但 description 必须说明依据或假设。
4. relationships 必须引用 elements 中存在的 id，关系类型优先使用 contains、satisfy、trace、allocate、verify、refine、deriveReqt、dependency。
5. Requirement 的 id 建议使用 REQ-001 形式；Block 使用 BLK-001；UseCase 使用 UC-001；Interface 使用 IF-001；Activity 使用 ACT-001；ConstraintBlock 使用 CON-001。
6. 所有面向用户和 MagicDraw 图面展示的文本必须使用中文，包括 project_name、summary、assumptions、元素 name/description、关系 description、图名和视图说明；id、type、package、relationship type、SysML 关键字等机器字段保持标准英文/编码。

JSON Schema：
{{
  "project_name": "AI_Dynamic_MBSE_Project",
  "summary": "一句话总结本次对话生成的工程模型",
  "assumptions": ["必要的建模假设或待确认项"],
  "elements": [
    {{
      "id": "REQ-001",
      "name": "模型元素名称",
      "type": "Requirement",
      "description": "模型元素说明",
      "package": "01_Requirements",
      "source_requirement": "REQ-001 或 null",
      "status": "candidate"
    }}
  ],
  "relationships": [
    {{
      "id": "REL-001",
      "source": "REQ-001",
      "target": "UC-001",
      "type": "trace",
      "description": "关系说明"
    }}
  ]
}}
""".strip()

    def _try_parse_json_object(self, raw: str) -> dict[str, Any] | None:
        text = str(raw or "").strip()
        if not text:
            return None
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?", "", text.strip(), flags=re.IGNORECASE).strip()
            text = re.sub(r"```$", "", text).strip()
        try:
            data = json.loads(text)
            return data if isinstance(data, dict) else None
        except json.JSONDecodeError:
            pass

        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                data = json.loads(text[start : end + 1])
                return data if isinstance(data, dict) else None
            except json.JSONDecodeError:
                return None
        return None

    def _normalize_llm_project(
        self,
        data: dict[str, Any],
        brief: str,
        project_name: str | None = None,
    ) -> dict[str, Any] | None:
        elements, id_map = self._normalize_project_elements(data.get("elements"))
        if len(elements) < 4:
            return None

        relationships = self._normalize_project_relationships(data.get("relationships"), {item["id"] for item in elements}, id_map)
        if not relationships:
            relationships = self._infer_minimal_relationships(elements)

        package_name = self._safe_name(str(data.get("project_name") or project_name or "").strip() or self._dynamic_project_name(brief))
        assumptions = self._normalize_text_list(data.get("assumptions"))
        summary = str(data.get("summary") or "").strip()
        if not summary:
            summary = f"已根据大模型交互上下文动态生成 SysML 工程：{len(elements)} 个模型元素、{len(relationships)} 条关系。"

        return {
            "project_name": package_name,
            "summary": summary,
            "assumptions": assumptions or ["模型由大模型根据当前对话动态生成，建议继续补充量化指标和验收条件。"],
            "generation_source": "llm",
            "elements": elements,
            "relationships": relationships,
            "sysml_text": self._render_sysml_text(package_name, elements, relationships),
        }

    def _normalize_project_elements(self, raw_elements: Any) -> tuple[list[dict[str, Any]], dict[str, str]]:
        if not isinstance(raw_elements, list):
            return [], {}

        elements: list[dict[str, Any]] = []
        id_map: dict[str, str] = {}
        used_ids: set[str] = set()
        counters: dict[str, int] = {}

        for raw in raw_elements:
            if not isinstance(raw, dict):
                continue
            element_type = self._normalize_element_type(raw.get("type") or raw.get("stereotype") or raw.get("kind"))
            prefix = self._element_prefix(element_type)
            counters[prefix] = counters.get(prefix, 0) + 1
            original_id = str(raw.get("id") or raw.get("local_id") or "").strip()
            element_id = self._normalize_element_id(original_id, prefix, counters[prefix], used_ids)
            name = str(raw.get("name") or raw.get("title") or element_id).strip()
            description = str(raw.get("description") or raw.get("doc") or raw.get("text") or name).strip()
            package = str(raw.get("package") or raw.get("owner") or self._default_element_package(element_type)).strip()
            source_requirement = raw.get("source_requirement") or raw.get("sourceRequirement")
            if element_type == "Requirement" and not source_requirement:
                source_requirement = element_id
            source_requirement_text = str(source_requirement).strip() if source_requirement is not None and str(source_requirement).strip() else None

            elements.append(
                {
                    "id": element_id,
                    "name": name or element_id,
                    "type": element_type,
                    "description": description or name or element_id,
                    "package": package or self._default_element_package(element_type),
                    "source_requirement": source_requirement_text,
                    "status": str(raw.get("status") or raw.get("lifecycleStatus") or "candidate").strip() or "candidate",
                }
            )
            if original_id:
                id_map[original_id] = element_id
            id_map[element_id] = element_id

        return elements, id_map

    def _normalize_project_relationships(
        self,
        raw_relationships: Any,
        element_ids: set[str],
        id_map: dict[str, str],
    ) -> list[dict[str, Any]]:
        if not isinstance(raw_relationships, list):
            return []

        relationships: list[dict[str, Any]] = []
        used_ids: set[str] = set()
        for index, raw in enumerate(raw_relationships, start=1):
            if not isinstance(raw, dict):
                continue
            source = id_map.get(str(raw.get("source") or raw.get("from") or "").strip())
            target = id_map.get(str(raw.get("target") or raw.get("to") or "").strip())
            if not source or not target or source not in element_ids or target not in element_ids or source == target:
                continue
            rel_id = self._normalize_relationship_id(str(raw.get("id") or raw.get("local_id") or ""), index, used_ids)
            relationships.append(
                {
                    "id": rel_id,
                    "source": source,
                    "target": target,
                    "type": self._normalize_relationship_type(raw.get("type") or raw.get("relationType")),
                    "description": str(raw.get("description") or raw.get("doc") or "").strip(),
                }
            )
        return relationships

    def _infer_minimal_relationships(self, elements: list[dict[str, Any]]) -> list[dict[str, Any]]:
        by_type: dict[str, list[str]] = {}
        for item in elements:
            by_type.setdefault(str(item["type"]), []).append(str(item["id"]))

        relationships: list[dict[str, Any]] = []
        root = (by_type.get("Block") or [elements[0]["id"]])[0]
        for index, req_id in enumerate(by_type.get("Requirement", [])[:8], start=1):
            target = (by_type.get("UseCase") or by_type.get("Block") or [root])[(index - 1) % len(by_type.get("UseCase") or by_type.get("Block") or [root])]
            relationships.append(
                {
                    "id": f"REL-{index:03d}",
                    "source": req_id,
                    "target": target,
                    "type": "trace",
                    "description": "根据元素类型自动补充的最小追溯关系。",
                }
            )
        return relationships

    def _normalize_text_list(self, value: Any) -> list[str]:
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str) and value.strip():
            return [value.strip()]
        return []

    def _normalize_element_type(self, value: Any) -> str:
        raw = str(value or "").strip().lower().replace(" ", "")
        aliases = {
            "requirement": "Requirement",
            "req": "Requirement",
            "需求": "Requirement",
            "block": "Block",
            "part": "Block",
            "模块": "Block",
            "actor": "Actor",
            "参与者": "Actor",
            "usecase": "UseCase",
            "use_case": "UseCase",
            "用例": "UseCase",
            "interface": "Interface",
            "接口": "Interface",
            "activity": "Activity",
            "action": "Activity",
            "活动": "Activity",
            "constraint": "ConstraintBlock",
            "constraintblock": "ConstraintBlock",
            "约束": "ConstraintBlock",
        }
        return aliases.get(raw, "Block")

    def _element_prefix(self, element_type: str) -> str:
        return {
            "Requirement": "REQ",
            "Block": "BLK",
            "Actor": "ACTOR",
            "UseCase": "UC",
            "Interface": "IF",
            "Activity": "ACT",
            "ConstraintBlock": "CON",
        }.get(element_type, "ELM")

    def _normalize_element_id(self, value: str, prefix: str, index: int, used_ids: set[str]) -> str:
        cleaned = re.sub(r"[^0-9A-Za-z_-]+", "-", str(value or "").strip()).strip("-_").upper()
        if not cleaned or not cleaned.startswith(f"{prefix}-"):
            cleaned = f"{prefix}-{index:03d}"
        else:
            suffix = cleaned[len(prefix) + 1 :]
            if suffix.isdigit():
                cleaned = f"{prefix}-{int(suffix):03d}"
        base = cleaned
        suffix = 2
        while cleaned in used_ids:
            cleaned = f"{base}-{suffix}"
            suffix += 1
        used_ids.add(cleaned)
        return cleaned

    def _normalize_relationship_id(self, value: str, index: int, used_ids: set[str]) -> str:
        cleaned = re.sub(r"[^0-9A-Za-z_-]+", "-", str(value or "").strip()).strip("-_").upper()
        if not cleaned or not cleaned.startswith("REL-"):
            cleaned = f"REL-{index:03d}"
        base = cleaned
        suffix = 2
        while cleaned in used_ids:
            cleaned = f"{base}-{suffix}"
            suffix += 1
        used_ids.add(cleaned)
        return cleaned

    def _normalize_relationship_type(self, value: Any) -> str:
        raw = str(value or "").strip()
        lowered = raw.lower()
        allowed = {
            "contains",
            "satisfy",
            "trace",
            "allocate",
            "verify",
            "refine",
            "derivereqt",
            "realize",
            "connector",
            "association",
            "include",
            "extend",
            "dependency",
            "controlflow",
            "objectflow",
            "message",
            "transition",
        }
        return lowered if lowered in allowed else (raw or "trace")

    def _dialogue_brief(self, conversation: list[dict[str, Any]], prompt: str) -> str:
        parts = [str(prompt or "").strip()]
        for item in conversation:
            role = str(item.get("role") or "").lower()
            content = str(item.get("content") or item.get("body") or "").strip()
            if role in {"user", "human", "assistant"} and content:
                parts.append(content)
        brief = "\n".join(part for part in parts if part).strip()
        return brief or "生成一个复杂装备总体方案的SysML工程。"

    def _latest_user_brief(self, conversation: list[dict[str, Any]], prompt: str) -> str:
        for item in reversed(conversation or []):
            role = str(item.get("role") or "").lower()
            content = str(item.get("content") or item.get("body") or "").strip()
            if role in {"user", "human"} and content:
                return content
        return str(prompt or "").strip()

    def _detect_domain(self, brief: str) -> str:
        text = str(brief or "")
        if not text.strip():
            return "generic"

        keyword_map = {
            "aircraft": [
                "飞机",
                "航空器",
                "飞行器",
                "民机",
                "客机",
                "运输机",
                "无人机",
                "机载",
                "航电",
                "飞控",
                "机翼",
                "机身",
                "起落架",
                "推进",
                "发动机",
                "适航",
                "aircraft",
                "airplane",
                "aviation",
                "uav",
            ],
            "radar": ["SAR", "雷达", "合成孔径", "成像", "斜距", "方位向", "条带", "聚束", "radar"],
            "satellite": ["卫星", "星座", "低轨", "LEO", "卫星互联网", "宽带卫星", "satellite", "constellation"],
            "vehicle": ["车辆", "无人车", "汽车", "底盘", "vehicle"],
        }
        lines = [line.strip() for line in re.split(r"[\n\r]+", text) if line.strip()]
        scores = {domain: 0 for domain in keyword_map}
        for index, line in enumerate(lines):
            lowered = line.lower()
            uppered = line.upper()
            weight = index + 1
            for domain, keywords in keyword_map.items():
                for keyword in keywords:
                    haystack = uppered if keyword.isupper() else lowered
                    needle = keyword if keyword.isupper() else keyword.lower()
                    if needle in haystack:
                        scores[domain] += weight

        best_domain, best_score = max(scores.items(), key=lambda item: item[1])
        return best_domain if best_score > 0 else "generic"

    def _should_use_curated_project(self, domain: str, brief: str) -> bool:
        if domain == "satellite":
            return any(
                keyword in brief
                for keyword in ["100颗", "一百颗", "低轨", "LEO", "星座", "卫星互联网", "宽带卫星"]
            )
        if domain == "radar":
            return any(keyword in brief for keyword in ["SAR", "雷达", "合成孔径", "成像载荷"])
        if domain == "aircraft":
            return any(keyword in brief for keyword in ["飞机", "航空器", "飞行器", "民机", "客机", "运输机", "无人机", "航电", "飞控", "适航"])
        if domain == "vehicle":
            return any(keyword in brief for keyword in ["车辆", "无人车", "汽车"])
        return False

    def _default_project_name(self, domain: str) -> str:
        if domain == "radar":
            return "SAR雷达载荷MBSE工程"
        if domain == "aircraft":
            return "飞机总体设计MBSE工程"
        if domain == "vehicle":
            return "车辆系统MBSE工程"
        if domain == "satellite":
            return "低轨宽带卫星互联网MBSE工程"
        return "动态系统MBSE工程"

    def _project_name_for_domain(self, project_name: str | None, domain: str) -> str:
        candidate = str(project_name or "").strip()
        generated_defaults = {
            "AI_MBSE_Project",
            "AI_LEO_Satellite_MBSE_Project",
            "AI_SAR_Radar_MBSE_Project",
            "AI_Aircraft_MBSE_Project",
            "AI_Vehicle_MBSE_Project",
        }
        if not candidate or candidate in generated_defaults:
            return self._default_project_name(domain)
        if domain == "satellite" and not self._contains_cjk(candidate) and any(
            token in candidate.lower() for token in ["leo", "satellite", "satcom", "constellation"]
        ):
            return self._default_project_name(domain)
        if domain != "satellite" and any(token in candidate.lower() for token in ["leo", "satellite", "卫星"]):
            return self._default_project_name(domain)
        return candidate

    def _project_summary(
        self,
        domain: str,
        brief: str,
        elements: list[dict[str, Any]],
        relationships: list[dict[str, Any]],
    ) -> str:
        domain_name = {
            "radar": "SAR雷达载荷",
            "aircraft": "飞机总体设计",
            "satellite": "100颗低轨宽带卫星互联网",
            "vehicle": "复杂装备系统",
        }.get(domain, "复杂装备系统")
        clipped = brief[:180].replace("\n", " ")
        return (
            f"已根据对话上下文生成{domain_name}SysML工程："
            f"{len(elements)}个模型元素、{len(relationships)}条关系。"
            f"工程覆盖需求、定义、用例、接口、活动与约束，并保留可追溯关系。"
            f"输入摘要：{clipped}"
        )

    def _project_assumptions(self, domain: str) -> list[str]:
        if domain == "radar":
            return [
                "按SAR雷达总体方案阶段处理，优先建立任务、载荷、处理、接口和约束的可追溯骨架。",
                "分辨率、测绘带宽、重访、数据率、功耗和热控指标先以SysML约束块表达，后续可接入专业仿真工具细化。",
                "默认覆盖条带、聚束和扫描成像模式，并保留平台、数传、星务或机载总线接口。",
                "MagicDraw侧接收同一批元素和关系，并按local_id去重或复用。",
            ]
        if domain == "aircraft":
            return [
                "按飞机总体设计阶段处理，优先建立任务需求、系统边界、功能链路、接口、行为流程和约束的可追溯骨架。",
                "重量、重心、升阻、航程、载荷、推进、供电、热控、可靠性和适航指标先以SysML约束块表达，后续可接入气动、结构、飞控和任务仿真工具细化。",
                "默认系统边界包含机体、推进、飞控、航电、能源、任务载荷、地面保障、外部空域/监管和MagicDraw交付边界。",
                "MagicDraw侧接收同一批元素、关系和分包信息，并按local_id去重或复用。",
            ]
        if domain == "vehicle":
            return [
                "按总体设计阶段处理，优先建立可追溯的系统骨架。",
                "性能指标以占位约束表达，后续可由仿真或专业工具细化。",
                "MagicDraw侧接收同一批元素和关系，并按local_id去重或复用。",
            ]
        return [
            "按总体方案阶段处理，星座基线规模采用100颗低轨宽带通信卫星。",
            "默认系统边界包含空间段、地面段、用户段、外部互联网/核心网、频谱监管环境和MagicDraw交付边界。",
            "轨道高度、轨道面数量、倾角、频段、单星容量、网关数量等指标先以候选约束表达，需由总体设计师继续确认。",
            "后续可接入覆盖分析、链路预算、容量仿真和网络仿真工具细化约束参数。",
            "MagicDraw侧接收同一批元素、关系和分包信息，并按local_id去重或复用。",
        ]

    def _project_elements(self, domain: str, brief: str) -> list[dict[str, Any]]:
        if domain == "radar":
            return self._radar_elements(brief)
        if domain == "aircraft":
            return self._aircraft_elements(brief)
        if domain == "vehicle":
            return self._vehicle_elements(brief)
        return self._satellite_elements(brief)

    def _satellite_elements(self, brief: str) -> list[dict[str, Any]]:
        brief_note = brief[:120].replace("\n", " ")
        return [
            self._element("REQ-001", "星座任务与服务目标", "Requirement", "形成面向宽带互联网接入的低轨星座总体方案，覆盖业务目标、服务区域、容量、时延、可靠性和运维目标。"),
            self._element("REQ-002", "系统边界与外部参与方", "Requirement", "系统边界应明确空间段、地面段、用户段、外部互联网/核心网、监管频谱环境和MagicDraw工程交付边界。"),
            self._element("REQ-003", "100颗卫星星座规模", "Requirement", "星座基线规模为100颗低轨通信卫星，并支持按轨道面、相位和备份策略开展构型设计。"),
            self._element("REQ-004", "轨道覆盖与服务连续性", "Requirement", "星座应支持目标服务区连续覆盖、可见性计算、切换策略、覆盖盲区识别和服务连续性评估。"),
            self._element("REQ-005", "用户链路容量与服务质量", "Requirement", "用户链路应满足宽带吞吐、波束调度、QoS等级、链路预算、拥塞控制和业务保持要求。"),
            self._element("REQ-006", "馈电链路与网关接入", "Requirement", "地面段应提供馈电网关站接入、回传链路、站间协同、网关选择和核心网互联能力。"),
            self._element("REQ-007", "星间链路与空间路由", "Requirement", "空间段应支持星间链路组网、路由更新、链路状态监测、拥塞绕行和故障重构。"),
            self._element("REQ-008", "用户终端接入与鉴权", "Requirement", "用户段应支持终端注册、认证鉴权、卫星选择、会话建立、接入状态监测和业务保持。"),
            self._element("REQ-009", "网络管理与资源调度", "Requirement", "网络运营控制中心应根据业务优先级、波束占用、频谱、网关和星间链路状态执行动态资源调度。"),
            self._element("REQ-010", "遥测遥控与在轨运维", "Requirement", "任务运控中心应支持遥测采集、遥控指令、健康评估、运行计划、星历维护和运维闭环。"),
            self._element("REQ-011", "故障处置与安全隔离", "Requirement", "系统应识别卫星、载荷、链路、网关和网络异常，并支持告警分级、隔离、重构和恢复确认。"),
            self._element("REQ-012", "信息安全与业务隔离", "Requirement", "系统应支持终端认证、密钥管理、业务隔离、控制面保护和跨段数据安全策略。"),
            self._element("REQ-013", "频谱合规与电磁兼容", "Requirement", "系统应满足频率使用、干扰协调、发射功率、旁瓣和电磁兼容约束，并保留监管符合性追溯。"),
            self._element("REQ-014", "模型一致性与MagicDraw交付", "Requirement", "SysML工程应保证需求、结构、行为、接口、约束和追溯关系一致，并能通过Bridge同步到MagicDraw。"),
            self._element("BLK-001", "低轨宽带卫星互联网系统", "Block", f"系统级根模块，来自对话输入：{brief_note}"),
            self._element("BLK-002", "空间段", "Block", "由100颗低轨通信卫星、星座构型、通信载荷、星间链路终端和卫星平台组成。"),
            self._element("BLK-003", "100颗低轨通信星座", "Block", "表示由100颗卫星组成的星座总体构型，承载轨道面、相位、覆盖和备份设计。"),
            self._element("BLK-004", "轨道面与星座构型", "Block", "定义轨道壳层、轨道面数量、面内卫星数、相位关系、星下点轨迹和覆盖几何。"),
            self._element("BLK-005", "低轨通信卫星", "Block", "单星系统，承担载荷承载、星上处理、星间互联、平台资源和遥测遥控功能。"),
            self._element("BLK-006", "宽带通信载荷", "Block", "负责用户波束、馈电波束、频率资源、业务数据转发和链路质量管理。"),
            self._element("BLK-007", "星上数字处理器", "Block", "完成星上交换、缓存、协议处理、QoS标记、路由表下发和业务转发。"),
            self._element("BLK-008", "用户服务链路天线", "Block", "面向用户终端形成可调波束，支撑接入、波束切换和链路质量保持。"),
            self._element("BLK-009", "馈电链路终端", "Block", "连接卫星与馈电网关站，承载回传数据、网关控制和链路状态上报。"),
            self._element("BLK-010", "星间链路终端", "Block", "提供卫星间数据交换、空间路由转发、链路状态上报和故障绕行能力。"),
            self._element("BLK-011", "卫星平台与星务分系统", "Block", "提供供配电、热控、姿轨控、星务管理、时间同步和健康监测能力。"),
            self._element("BLK-012", "地面段", "Block", "由馈电网关站、网络运营控制中心、任务运控中心及外部网络接口组成。"),
            self._element("BLK-013", "馈电网关站", "Block", "完成卫星馈电接入、业务回传、网关选择、站间协同和核心网互联。"),
            self._element("BLK-014", "网络运营控制中心", "Block", "执行资源调度、链路监测、业务策略、网络状态管理和安全策略配置。"),
            self._element("BLK-015", "任务运控中心", "Block", "处理遥测遥控、健康管理、告警处置、运行计划、星历维护和在轨配置。"),
            self._element("BLK-016", "用户段", "Block", "由宽带用户终端、认证接入和用户业务会话组成。"),
            self._element("BLK-017", "宽带用户终端", "Block", "完成用户侧注册、认证、波束跟踪、数据收发、状态上报和业务保持。"),
            self._element("BLK-018", "外部互联网与核心网", "Block", "作为系统外部网络边界，承载互联网业务、核心网策略和外部运营接口。"),
            self._element("UC-001", "引导总体需求澄清", "UseCase", "总体设计师与AI共同明确任务目标、边界、指标、交付物和待确认假设。"),
            self._element("UC-002", "开展星座覆盖与容量设计", "UseCase", "根据100颗星座规模、轨道构型、服务区域和业务模型开展覆盖、容量和可见性设计。"),
            self._element("UC-003", "建立用户宽带会话", "UseCase", "用户终端完成认证、卫星选择、波束接入、承载建立和业务会话保持。"),
            self._element("UC-004", "执行卫星切换与业务保持", "UseCase", "在卫星可见性变化或链路质量下降时执行波束/卫星/网关切换并保持业务连续。"),
            self._element("UC-005", "完成馈电回传与核心网互联", "UseCase", "卫星通过馈电网关站完成互联网业务回传、核心网互联和站间协同。"),
            self._element("UC-006", "执行星间路由转发", "UseCase", "空间段根据链路状态、拥塞和目的网关执行星间路由和数据转发。"),
            self._element("UC-007", "调度波束频谱网关资源", "UseCase", "网络运营控制中心根据业务需求和资源状态调度波束、频谱、网关和星间链路。"),
            self._element("UC-008", "处置故障告警与网络重构", "UseCase", "系统发现异常后完成告警分级、隔离、资源重构、恢复确认和运维闭环。"),
            self._element("UC-009", "同步MagicDraw工程", "UseCase", "AI生成SysML文本、元素、关系和布局后通过Bridge推送到MagicDraw并回显结果。"),
            self._element("IF-001", "用户服务链路接口", "Interface", "连接宽带用户终端与用户服务链路天线，承载业务数据、认证、接入状态和链路测量。"),
            self._element("IF-002", "馈电链路接口", "Interface", "连接馈电链路终端与馈电网关站，承载业务回传、网关控制、链路状态和同步信息。"),
            self._element("IF-003", "星间链路接口", "Interface", "连接星间链路终端，承载空间路由、业务转发、链路状态和故障绕行信息。"),
            self._element("IF-004", "遥测遥控接口", "Interface", "连接任务运控中心与卫星平台/载荷，承载遥测、遥控、健康状态和在轨配置。"),
            self._element("IF-005", "网络管理南向接口", "Interface", "连接网络运营控制中心与空间段、网关站，承载资源策略、链路状态和调度指令。"),
            self._element("IF-006", "网关核心网接口", "Interface", "连接馈电网关站与外部互联网/核心网，承载业务转发、策略控制和运维状态。"),
            self._element("IF-007", "时间频率与星历接口", "Interface", "连接任务运控、卫星平台和网络控制，承载时间同步、频率基准、星历和轨道预报。"),
            self._element("IF-008", "安全认证与密钥接口", "Interface", "连接用户终端、网络控制和安全策略，承载鉴权、密钥更新和业务隔离控制。"),
            self._element("IF-009", "MagicDraw Bridge接口", "Interface", "承载SysML工程交换包、导入状态、创建元素数、关系数和布局回传。"),
            self._element("ACT-001", "总体需求澄清与基线确认流程", "Activity", "AI引导总体设计师明确服务目标、边界、指标、假设、交付物和MagicDraw同步策略。"),
            self._element("ACT-002", "星座构型与覆盖分析流程", "Activity", "定义轨道壳层和100颗卫星分布，计算可见性、覆盖率、重访和切换机会。"),
            self._element("ACT-003", "链路预算与容量校核流程", "Activity", "校核用户链路、馈电链路、星间链路的EIRP、G/T、C/N0、吞吐、时延和余量。"),
            self._element("ACT-004", "用户接入与会话建立流程", "Activity", "完成终端注册、认证鉴权、卫星选择、波束建立、承载配置和业务会话确认。"),
            self._element("ACT-005", "星间路由与切换流程", "Activity", "根据卫星可见性、链路状态和目标网关执行星间路由更新、波束切换和业务保持。"),
            self._element("ACT-006", "网关选择与馈电回传流程", "Activity", "选择可见网关，建立馈电链路，完成业务回传、核心网互联和站间协同。"),
            self._element("ACT-007", "网络资源调度流程", "Activity", "根据业务优先级、资源余量、拥塞状态和策略约束调度波束、频谱、网关和路由。"),
            self._element("ACT-008", "故障检测隔离恢复流程", "Activity", "完成异常检测、告警分级、隔离、链路/路由/网关重构、恢复确认和运维记录。"),
            self._element("ACT-009", "MagicDraw工程同步流程", "Activity", "打包SysML元素、关系、分包和布局，调用Bridge，接收MagicDraw创建/复用结果。"),
            self._element("CON-001", "星座规模约束", "ConstraintBlock", "numSatellites = 100；轨道面数量、面内卫星数和备份策略应与覆盖和容量目标一致。"),
            self._element("CON-002", "轨道壳层与覆盖约束", "ConstraintBlock", "轨道高度、倾角、最小仰角、覆盖率、切换间隔和服务盲区应满足任务剖面要求。"),
            self._element("CON-003", "容量吞吐约束", "ConstraintBlock", "用户并发数、单用户速率、总吞吐、波束容量和网关回传能力应满足业务模型。"),
            self._element("CON-004", "业务时延约束", "ConstraintBlock", "端到端时延、星间转发时延、网关回传时延和切换中断时间应满足宽带业务等级。"),
            self._element("CON-005", "链路预算约束", "ConstraintBlock", "用户链路、馈电链路和星间链路的EIRP、G/T、C/N0、雨衰余量和编码调制应满足链路预算。"),
            self._element("CON-006", "网关可见与切换约束", "ConstraintBlock", "可见网关数量、站间切换、回传容量和地理分布应满足服务连续性和容量目标。"),
            self._element("CON-007", "可用性可靠性约束", "ConstraintBlock", "卫星、载荷、网关、链路和控制中心的可用性、冗余和故障恢复时间应满足总体可靠性目标。"),
            self._element("CON-008", "频谱安全合规约束", "ConstraintBlock", "频率使用、发射功率、干扰协调、认证加密、业务隔离和控制面保护应满足合规与安全目标。"),
        ]

    def _radar_elements(self, brief: str) -> list[dict[str, Any]]:
        brief_note = brief[:120].replace("\n", " ")
        return [
            self._element("REQ-001", "SAR总体任务目标", "Requirement", "形成满足观测区域、成像质量、响应时效和平台适配约束的SAR雷达总体方案。"),
            self._element("REQ-002", "成像模式与任务覆盖", "Requirement", "系统应支持条带、聚束和扫描成像模式，并覆盖指定观测区域与任务剖面。"),
            self._element("REQ-003", "分辨率与测绘带宽", "Requirement", "系统应满足距离向、方位向分辨率、测绘带宽、重访周期和定位精度指标。"),
            self._element("REQ-004", "射频链路与天线性能", "Requirement", "射频前端、功放、低噪声接收和天线阵面应满足频段、带宽、增益、极化和旁瓣约束。"),
            self._element("REQ-005", "波形产生与时序控制", "Requirement", "系统应支持脉冲压缩波形、PRF规划、同步时钟、收发切换和定标时序。"),
            self._element("REQ-006", "回波采集与成像处理", "Requirement", "系统应完成回波采样、量化、缓存、运动补偿、聚焦处理和图像产品生成。"),
            self._element("REQ-007", "数据传输与产品分发", "Requirement", "系统应支持原始回波、快视图像和标准产品的数据管理、压缩、存储与下传。"),
            self._element("REQ-008", "功耗热控与可靠性", "Requirement", "系统应满足峰值功耗、平均功耗、热耗散、工作占空比、冗余和故障检测要求。"),
            self._element("REQ-009", "标校与质量评估", "Requirement", "系统应支持内定标、外定标、图像质量评价、几何校正和辐射校正。"),
            self._element("REQ-010", "模型一致性与可追溯", "Requirement", "SysML工程应保证SAR任务、结构、行为、接口和约束之间可追溯，并能同步到MagicDraw。"),
            self._element("BLK-001", "SAR雷达载荷系统", "Block", f"系统级根模块，来自对话输入：{brief_note}"),
            self._element("BLK-002", "雷达天线子系统", "Block", "承担波束指向、极化控制、阵面校准和射频能量辐射接收。"),
            self._element("BLK-003", "射频收发子系统", "Block", "包含发射功放、接收低噪声放大、上下变频、滤波和收发保护。"),
            self._element("BLK-004", "波形与频率源子系统", "Block", "产生线性调频等SAR波形，提供同步时钟、频率源和PRF控制。"),
            self._element("BLK-005", "数字采集与处理子系统", "Block", "完成ADC采样、缓存、预处理、成像聚焦、压缩和产品生成。"),
            self._element("BLK-006", "任务规划与模式控制", "Block", "根据任务区域、模式、轨迹和资源约束生成观测计划与控制序列。"),
            self._element("BLK-007", "平台接口与姿轨支撑", "Block", "连接卫星或机载平台，接收姿态、轨道、时间同步和供配电资源。"),
            self._element("BLK-008", "数传与存储单元", "Block", "管理原始回波、快视图像、产品文件和下传链路。"),
            self._element("BLK-009", "标校与质量评估单元", "Block", "执行定标、几何校正、辐射校正和图像质量指标评估。"),
            self._element("BLK-010", "供电热控与健康管理", "Block", "管理峰值功耗、热耗散、占空比、冗余切换和故障告警。"),
            self._element("UC-001", "生成SAR总体方案", "UseCase", "总体设计师输入任务指标后生成可评审的SAR雷达总体方案。"),
            self._element("UC-002", "执行成像任务规划", "UseCase", "根据观测区域、成像模式和平台轨迹生成任务计划。"),
            self._element("UC-003", "完成回波采集与处理", "UseCase", "系统按时序发射波形、接收回波并生成SAR图像产品。"),
            self._element("UC-004", "完成标校与质量评估", "UseCase", "对SAR产品执行定标、校正和质量指标评估。"),
            self._element("UC-005", "同步MagicDraw工程", "UseCase", "AI生成SysML文本和结构后通过Bridge推送到MagicDraw并回显结果。"),
            self._element("IF-001", "平台姿轨时间接口", "Interface", "接收姿态、轨道、时间同步、模式控制和任务计划数据。"),
            self._element("IF-002", "射频天线接口", "Interface", "连接天线阵面与射频收发链路，承载发射、接收、校准和保护信号。"),
            self._element("IF-003", "高速采样数据接口", "Interface", "连接接收链路与数字处理单元，承载高码率原始回波数据。"),
            self._element("IF-004", "图像产品数传接口", "Interface", "连接处理单元、存储单元和数传链路，承载图像产品和元数据。"),
            self._element("IF-005", "供电热控接口", "Interface", "连接平台供配电和热控资源，承载功耗、温度和健康状态信息。"),
            self._element("IF-006", "MagicDraw Bridge接口", "Interface", "承载SysML工程交换包、导入状态、创建元素数和关系数回传。"),
            self._element("ACT-001", "需求理解与SAR建模流程", "Activity", "AI解析对话、抽取SAR任务指标、生成候选SysML工程骨架。"),
            self._element("ACT-002", "成像任务规划流程", "Activity", "选择成像模式、计算观测窗口、规划PRF和资源占用。"),
            self._element("ACT-003", "收发与回波采集流程", "Activity", "执行波形发射、回波接收、采样缓存和时序同步。"),
            self._element("ACT-004", "成像处理与产品生成流程", "Activity", "执行运动补偿、距离压缩、方位聚焦、图像校正和产品封装。"),
            self._element("ACT-005", "标校质量闭环流程", "Activity", "执行定标、质量评估、异常识别和参数修正建议。"),
            self._element("CON-001", "成像性能约束", "ConstraintBlock", "距离向分辨率、方位向分辨率、测绘带宽、信噪比和定位精度满足任务指标。"),
            self._element("CON-002", "射频链路约束", "ConstraintBlock", "频段、带宽、峰值功率、天线增益、噪声系数、PRF和占空比满足链路预算。"),
            self._element("CON-003", "资源与热控约束", "ConstraintBlock", "峰值功耗、平均功耗、热耗散、存储容量和下传数据率满足平台资源限制。"),
        ]

    def _aircraft_elements(self, brief: str) -> list[dict[str, Any]]:
        brief_note = brief[:120].replace("\n", " ")
        return [
            self._element("REQ-001", "飞机任务与使用场景", "Requirement", "形成面向总体设计阶段的飞机任务定义，覆盖用途、航程、速度、高度、载荷、机场适应性和运行剖面。"),
            self._element("REQ-002", "系统边界与外部参与方", "Requirement", "系统边界应明确飞机本体、机组/乘员、地面保障、空管、监管适航、任务设备和MagicDraw工程交付边界。"),
            self._element("REQ-003", "总体布局与气动性能", "Requirement", "总体布局应支持机翼、机身、尾翼、进气/排气和操纵面的协调设计，并满足升阻、稳定性和操纵品质要求。"),
            self._element("REQ-004", "重量重心与载荷能力", "Requirement", "系统应建立重量分解、重心包线、有效载荷、燃油/能源和任务设备安装约束。"),
            self._element("REQ-005", "推进与能源供给", "Requirement", "推进系统应满足起飞、爬升、巡航、备降和任务剖面的推力/功率、燃油或电能供给要求。"),
            self._element("REQ-006", "飞控与航电集成", "Requirement", "飞控、导航、通信、监视和座舱/任务航电应形成一致的控制、显示、告警和数据总线架构。"),
            self._element("REQ-007", "结构强度与安全裕度", "Requirement", "机体结构应满足载荷谱、疲劳、损伤容限、环境适应性和安全裕度要求。"),
            self._element("REQ-008", "任务载荷与舱内接口", "Requirement", "任务载荷或客货舱应满足安装、供电、冷却、数据、可达性和安全隔离要求。"),
            self._element("REQ-009", "维护保障与健康管理", "Requirement", "系统应支持状态监测、故障隔离、维护可达性、地面测试和放行判据。"),
            self._element("REQ-010", "适航符合性与模型交付", "Requirement", "SysML工程应支撑需求、结构、接口、行为、约束和验证项追溯，并保留适航符合性证据接口。"),
            self._element("BLK-001", "飞机总体系统", "Block", f"系统级根模块，来自对话输入：{brief_note}"),
            self._element("BLK-002", "机体与总体布局", "Block", "定义机翼、机身、尾翼、起落架舱、舱段和总体布置基线。"),
            self._element("BLK-003", "气动与操稳子系统", "Block", "管理气动外形、操纵面、稳定性、操纵品质和飞行包线。"),
            self._element("BLK-004", "结构与材料子系统", "Block", "管理主承力结构、材料、连接、疲劳和损伤容限设计。"),
            self._element("BLK-005", "推进与燃油能源子系统", "Block", "提供推力或功率，管理燃油、电能、进排气和推进控制。"),
            self._element("BLK-006", "飞控与航电子系统", "Block", "集成飞控计算、导航、通信、监视、座舱显示、告警和数据总线。"),
            self._element("BLK-007", "电源与环控子系统", "Block", "提供供配电、热管理、环控、除冰、防火和环境控制能力。"),
            self._element("BLK-008", "任务载荷与客货舱", "Block", "承载任务设备、乘员/货物、舱内接口和安全隔离。"),
            self._element("BLK-009", "起落架与地面保障", "Block", "支持起降、滑行、制动、转弯、牵引、加注和地面维护。"),
            self._element("BLK-010", "健康管理与维护保障", "Block", "负责状态监测、故障诊断、维护计划、测试接口和放行支持。"),
            self._element("UC-001", "澄清飞机总体需求", "UseCase", "总体设计师输入任务、性能和边界条件后形成可评审的飞机总体需求基线。"),
            self._element("UC-002", "生成总体布局方案", "UseCase", "根据任务剖面、载荷和性能约束生成总体布局、重量重心和系统分解方案。"),
            self._element("UC-003", "执行飞行任务剖面", "UseCase", "飞机按照起飞、爬升、巡航、任务、下降、着陆和备降流程完成任务。"),
            self._element("UC-004", "完成飞控航电协同", "UseCase", "飞控、导航、通信、监视和座舱系统完成指令、状态和告警闭环。"),
            self._element("UC-005", "开展适航验证闭环", "UseCase", "将需求、设计、分析、试验和符合性证据形成可追溯闭环。"),
            self._element("UC-006", "同步MagicDraw工程", "UseCase", "AI生成SysML文本和结构后通过Bridge推送到MagicDraw并回显结果。"),
            self._element("IF-001", "飞控指令与状态接口", "Interface", "承载驾驶/自动飞行指令、控制律输出、舵面反馈和飞行状态。"),
            self._element("IF-002", "航电数据总线接口", "Interface", "承载导航、通信、监视、座舱显示、任务计算和告警数据。"),
            self._element("IF-003", "推进控制接口", "Interface", "承载油门/功率指令、发动机状态、燃油流量、推力或功率反馈。"),
            self._element("IF-004", "电源与热控接口", "Interface", "承载供电、负载管理、温度、冷却、环控和防护状态。"),
            self._element("IF-005", "任务载荷接口", "Interface", "承载任务载荷供电、数据、安装、冷却、控制和安全隔离信息。"),
            self._element("IF-006", "地面保障接口", "Interface", "承载加注、牵引、维护测试、数据装载、健康下载和放行信息。"),
            self._element("IF-007", "MagicDraw Bridge接口", "Interface", "承载SysML工程交换包、导入状态、创建元素数和关系数回传。"),
            self._element("ACT-001", "需求澄清与基线确认流程", "Activity", "澄清任务场景、利益相关方、边界、性能指标和交付约束。"),
            self._element("ACT-002", "总体布局与权衡流程", "Activity", "开展构型选择、重量重心、气动性能、推进匹配和系统分解权衡。"),
            self._element("ACT-003", "任务剖面执行流程", "Activity", "串联地面准备、起飞、爬升、巡航、任务执行、返航、着陆和维护交接。"),
            self._element("ACT-004", "飞控航电闭环流程", "Activity", "完成传感、导航估计、控制律计算、执行机构控制、状态显示和告警。"),
            self._element("ACT-005", "维护诊断与放行流程", "Activity", "采集健康数据、识别故障、隔离影响、执行维护并确认放行条件。"),
            self._element("ACT-006", "适航验证与模型同步流程", "Activity", "将需求、分析、试验和符合性证据同步到SysML/MagicDraw工程。"),
            self._element("CON-001", "重量重心约束", "ConstraintBlock", "最大起飞重量、空重、有效载荷、燃油/能源、重心包线和载荷分布满足总体指标。"),
            self._element("CON-002", "气动性能约束", "ConstraintBlock", "升阻比、失速速度、巡航速度、爬升率、航程、航时和稳定裕度满足任务剖面。"),
            self._element("CON-003", "推进能源约束", "ConstraintBlock", "推重比或功重比、燃油消耗、电能余量、热负荷和冗余能力满足全包线需求。"),
            self._element("CON-004", "飞控安全约束", "ConstraintBlock", "飞控失效、传感器退化、控制律切换、告警和降级模式满足安全目标。"),
            self._element("CON-005", "适航符合性约束", "ConstraintBlock", "需求验证、分析、试验、检查和符合性证据应可追溯到适航条款和设计基线。"),
        ]

    def _vehicle_elements(self, brief: str) -> list[dict[str, Any]]:
        brief_note = brief[:120].replace("\n", " ")
        return [
            self._element("REQ-001", "系统总体任务", "Requirement", "形成满足安全、性能、可靠性和运维约束的复杂装备总体方案。"),
            self._element("REQ-002", "感知与状态监测", "Requirement", "系统应支持关键状态采集、环境感知和异常识别。"),
            self._element("REQ-003", "控制与执行", "Requirement", "系统应支持控制策略生成、执行机构控制和闭环反馈。"),
            self._element("REQ-004", "通信与数据管理", "Requirement", "系统应支持内部通信、外部接口和数据记录。"),
            self._element("REQ-005", "故障诊断与安全", "Requirement", "系统应支持故障检测、降级控制和安全隔离。"),
            self._element("BLK-001", "智能装备系统", "Block", f"系统级根模块，来自对话输入：{brief_note}"),
            self._element("BLK-002", "感知子系统", "Block", "负责环境与状态信息采集。"),
            self._element("BLK-003", "控制子系统", "Block", "负责决策、控制律和闭环控制。"),
            self._element("BLK-004", "执行子系统", "Block", "负责动作执行与反馈。"),
            self._element("BLK-005", "通信与管理子系统", "Block", "负责数据、通信和运维管理。"),
            self._element("UC-001", "生成总体方案", "UseCase", "根据任务输入生成可评审的系统方案。"),
            self._element("UC-002", "执行闭环控制", "UseCase", "感知、决策、执行和反馈形成闭环。"),
            self._element("UC-003", "处理故障降级", "UseCase", "异常发生后执行诊断、告警和安全降级。"),
            self._element("IF-001", "传感数据接口", "Interface", "传递传感器数据和状态量。"),
            self._element("IF-002", "控制指令接口", "Interface", "传递控制命令与执行反馈。"),
            self._element("IF-003", "运维管理接口", "Interface", "传递配置、日志、告警和健康状态。"),
            self._element("ACT-001", "需求理解与建模流程", "Activity", "AI解析对话并生成SysML模型。"),
            self._element("ACT-002", "闭环控制流程", "Activity", "完成感知、决策、执行和反馈。"),
            self._element("ACT-003", "故障诊断流程", "Activity", "完成检测、诊断、降级和恢复确认。"),
            self._element("CON-001", "安全约束", "ConstraintBlock", "系统失效风险应满足总体安全目标。"),
            self._element("CON-002", "性能约束", "ConstraintBlock", "响应时间、精度和可用性满足任务指标。"),
        ]

    def _project_relationships(self, domain: str) -> list[dict[str, Any]]:
        if domain == "radar":
            relations = [
                ("BLK-001", "BLK-002", "contains", "系统包含雷达天线子系统"),
                ("BLK-001", "BLK-003", "contains", "系统包含射频收发子系统"),
                ("BLK-001", "BLK-004", "contains", "系统包含波形与频率源子系统"),
                ("BLK-001", "BLK-005", "contains", "系统包含数字采集与处理子系统"),
                ("BLK-001", "BLK-006", "contains", "系统包含任务规划与模式控制"),
                ("BLK-001", "BLK-007", "contains", "系统包含平台接口与姿轨支撑"),
                ("BLK-001", "BLK-008", "contains", "系统包含数传与存储单元"),
                ("BLK-001", "BLK-009", "contains", "系统包含标校与质量评估单元"),
                ("BLK-001", "BLK-010", "contains", "系统包含供电热控与健康管理"),
                ("BLK-001", "REQ-001", "satisfy", "系统满足SAR总体任务目标"),
                ("BLK-006", "REQ-002", "satisfy", "任务规划满足成像模式与覆盖需求"),
                ("BLK-005", "REQ-003", "satisfy", "数字处理满足分辨率与测绘带宽需求"),
                ("BLK-002", "REQ-004", "satisfy", "天线子系统满足射频性能需求"),
                ("BLK-003", "REQ-004", "satisfy", "射频收发子系统满足射频链路需求"),
                ("BLK-004", "REQ-005", "satisfy", "波形频率源满足时序控制需求"),
                ("BLK-005", "REQ-006", "satisfy", "数字处理子系统满足回波采集与成像处理需求"),
                ("BLK-008", "REQ-007", "satisfy", "数传存储单元满足产品分发需求"),
                ("BLK-010", "REQ-008", "satisfy", "供电热控健康管理满足可靠性需求"),
                ("BLK-009", "REQ-009", "satisfy", "标校质量评估单元满足标校需求"),
                ("IF-006", "REQ-010", "satisfy", "Bridge接口满足模型一致性与可追溯需求"),
                ("REQ-001", "UC-001", "trace", "总体任务追踪到方案生成用例"),
                ("REQ-002", "UC-002", "trace", "覆盖需求追踪到成像任务规划用例"),
                ("REQ-006", "UC-003", "trace", "采集处理需求追踪到回波处理用例"),
                ("REQ-009", "UC-004", "trace", "标校需求追踪到质量评估用例"),
                ("REQ-010", "UC-005", "trace", "模型一致性需求追踪到MagicDraw同步用例"),
                ("UC-001", "ACT-001", "trace", "用例细化为SAR建模流程"),
                ("UC-002", "ACT-002", "trace", "用例细化为任务规划流程"),
                ("UC-003", "ACT-003", "trace", "用例细化为收发采集流程"),
                ("UC-003", "ACT-004", "trace", "用例细化为成像处理流程"),
                ("UC-004", "ACT-005", "trace", "用例细化为标校质量闭环流程"),
                ("IF-001", "BLK-007", "allocate", "平台姿轨时间接口分配到平台接口与姿轨支撑"),
                ("IF-002", "BLK-002", "allocate", "射频天线接口分配到天线子系统"),
                ("IF-002", "BLK-003", "allocate", "射频天线接口分配到射频收发子系统"),
                ("IF-003", "BLK-005", "allocate", "高速采样数据接口分配到数字处理子系统"),
                ("IF-004", "BLK-008", "allocate", "图像产品数传接口分配到数传与存储单元"),
                ("IF-005", "BLK-010", "allocate", "供电热控接口分配到供电热控与健康管理"),
                ("IF-006", "BLK-001", "allocate", "Bridge接口分配到SAR SysML工程根模块"),
                ("CON-001", "REQ-003", "verify", "成像性能约束验证分辨率与测绘带宽需求"),
                ("CON-002", "REQ-004", "verify", "射频链路约束验证射频链路与天线性能需求"),
                ("CON-003", "REQ-008", "verify", "资源与热控约束验证功耗热控可靠性需求"),
            ]
            return [
                {"id": f"REL-{index:03d}", "source": source, "target": target, "type": rel_type, "description": description}
                for index, (source, target, rel_type, description) in enumerate(relations, start=1)
            ]

        if domain == "aircraft":
            relations = [
                ("BLK-001", "BLK-002", "contains", "飞机总体系统包含机体与总体布局"),
                ("BLK-001", "BLK-003", "contains", "飞机总体系统包含气动与操稳子系统"),
                ("BLK-001", "BLK-004", "contains", "飞机总体系统包含结构与材料子系统"),
                ("BLK-001", "BLK-005", "contains", "飞机总体系统包含推进与燃油能源子系统"),
                ("BLK-001", "BLK-006", "contains", "飞机总体系统包含飞控与航电子系统"),
                ("BLK-001", "BLK-007", "contains", "飞机总体系统包含电源与环控子系统"),
                ("BLK-001", "BLK-008", "contains", "飞机总体系统包含任务载荷与客货舱"),
                ("BLK-001", "BLK-009", "contains", "飞机总体系统包含起落架与地面保障"),
                ("BLK-001", "BLK-010", "contains", "飞机总体系统包含健康管理与维护保障"),
                ("BLK-001", "REQ-001", "satisfy", "飞机总体系统满足任务与使用场景需求"),
                ("BLK-001", "REQ-002", "satisfy", "飞机总体系统满足系统边界与外部参与方需求"),
                ("BLK-002", "REQ-003", "satisfy", "总体布局满足气动性能与布置需求"),
                ("BLK-003", "REQ-003", "satisfy", "气动与操稳子系统满足气动性能需求"),
                ("BLK-002", "REQ-004", "satisfy", "总体布局满足重量重心与载荷能力需求"),
                ("BLK-005", "REQ-005", "satisfy", "推进与能源子系统满足推进能源需求"),
                ("BLK-006", "REQ-006", "satisfy", "飞控与航电子系统满足飞控航电集成需求"),
                ("BLK-004", "REQ-007", "satisfy", "结构与材料子系统满足强度与安全裕度需求"),
                ("BLK-008", "REQ-008", "satisfy", "任务载荷与客货舱满足载荷接口需求"),
                ("BLK-010", "REQ-009", "satisfy", "健康管理与维护保障满足维护保障需求"),
                ("IF-007", "REQ-010", "satisfy", "Bridge接口满足模型交付与追溯需求"),
                ("REQ-001", "UC-001", "trace", "任务需求追溯到总体需求澄清用例"),
                ("REQ-002", "UC-001", "trace", "边界需求追溯到总体需求澄清用例"),
                ("REQ-003", "UC-002", "trace", "气动布局需求追溯到总体布局方案用例"),
                ("REQ-004", "UC-002", "trace", "重量重心需求追溯到总体布局方案用例"),
                ("REQ-005", "UC-003", "trace", "推进能源需求追溯到任务剖面执行用例"),
                ("REQ-006", "UC-004", "trace", "飞控航电需求追溯到飞控航电协同用例"),
                ("REQ-007", "UC-005", "trace", "结构强度需求追溯到适航验证闭环用例"),
                ("REQ-008", "UC-003", "trace", "任务载荷需求追溯到任务剖面执行用例"),
                ("REQ-009", "UC-005", "trace", "维护保障需求追溯到适航验证闭环用例"),
                ("REQ-010", "UC-006", "trace", "模型交付需求追溯到MagicDraw同步用例"),
                ("UC-001", "ACT-001", "refine", "总体需求澄清用例细化为需求澄清与基线确认流程"),
                ("UC-002", "ACT-002", "refine", "总体布局方案用例细化为布局与权衡流程"),
                ("UC-003", "ACT-003", "refine", "任务剖面执行用例细化为飞行任务剖面流程"),
                ("UC-004", "ACT-004", "refine", "飞控航电协同用例细化为飞控航电闭环流程"),
                ("UC-005", "ACT-005", "refine", "适航验证闭环用例细化为维护诊断与放行流程"),
                ("UC-005", "ACT-006", "refine", "适航验证闭环用例细化为适航验证与模型同步流程"),
                ("UC-006", "ACT-006", "refine", "MagicDraw同步用例细化为模型同步流程"),
                ("IF-001", "BLK-006", "allocate", "飞控指令与状态接口分配到飞控与航电子系统"),
                ("IF-001", "BLK-003", "allocate", "飞控指令与状态接口分配到气动操稳子系统"),
                ("IF-002", "BLK-006", "allocate", "航电数据总线接口分配到飞控与航电子系统"),
                ("IF-002", "BLK-008", "allocate", "航电数据总线接口连接任务载荷与客货舱"),
                ("IF-003", "BLK-005", "allocate", "推进控制接口分配到推进与燃油能源子系统"),
                ("IF-004", "BLK-007", "allocate", "电源与热控接口分配到电源与环控子系统"),
                ("IF-004", "BLK-005", "allocate", "电源与热控接口连接推进能源负载"),
                ("IF-005", "BLK-008", "allocate", "任务载荷接口分配到任务载荷与客货舱"),
                ("IF-006", "BLK-009", "allocate", "地面保障接口分配到起落架与地面保障"),
                ("IF-006", "BLK-010", "allocate", "地面保障接口连接健康管理与维护保障"),
                ("IF-007", "BLK-001", "allocate", "MagicDraw Bridge接口分配到飞机总体SysML工程根模块"),
                ("CON-001", "REQ-004", "verify", "重量重心约束验证重量重心与载荷能力需求"),
                ("CON-002", "REQ-003", "verify", "气动性能约束验证总体布局与气动性能需求"),
                ("CON-002", "REQ-001", "verify", "气动性能约束验证任务剖面需求"),
                ("CON-003", "REQ-005", "verify", "推进能源约束验证推进与能源供给需求"),
                ("CON-004", "REQ-006", "verify", "飞控安全约束验证飞控与航电集成需求"),
                ("CON-005", "REQ-007", "verify", "适航符合性约束验证结构强度与安全裕度需求"),
                ("CON-005", "REQ-010", "verify", "适航符合性约束验证模型交付与追溯需求"),
            ]
            return [
                {"id": f"REL-{index:03d}", "source": source, "target": target, "type": rel_type, "description": description}
                for index, (source, target, rel_type, description) in enumerate(relations, start=1)
            ]

        if domain == "vehicle":
            relations = [
                ("BLK-001", "BLK-002", "contains", "系统包含感知子系统"),
                ("BLK-001", "BLK-003", "contains", "系统包含控制子系统"),
                ("BLK-001", "BLK-004", "contains", "系统包含执行子系统"),
                ("BLK-001", "BLK-005", "contains", "系统包含通信与管理子系统"),
                ("BLK-001", "REQ-001", "satisfy", "系统满足总体任务"),
                ("BLK-002", "REQ-002", "satisfy", "感知子系统满足状态监测需求"),
                ("BLK-003", "REQ-003", "satisfy", "控制子系统满足控制需求"),
                ("BLK-005", "REQ-004", "satisfy", "通信与管理子系统满足数据管理需求"),
                ("BLK-003", "REQ-005", "satisfy", "控制子系统满足安全降级需求"),
                ("REQ-001", "UC-001", "trace", "总体任务追溯到方案生成用例"),
                ("REQ-003", "UC-002", "trace", "控制需求追溯到闭环控制用例"),
                ("REQ-005", "UC-003", "trace", "故障需求追溯到降级处理用例"),
                ("UC-001", "ACT-001", "trace", "用例细化为建模流程"),
                ("UC-002", "ACT-002", "trace", "用例细化为闭环控制流程"),
                ("UC-003", "ACT-003", "trace", "用例细化为故障诊断流程"),
                ("IF-001", "BLK-002", "allocate", "传感数据接口分配到感知子系统"),
                ("IF-002", "BLK-003", "allocate", "控制指令接口分配到控制子系统"),
                ("IF-002", "BLK-004", "allocate", "控制指令接口分配到执行子系统"),
                ("IF-003", "BLK-005", "allocate", "运维管理接口分配到通信与管理子系统"),
                ("CON-001", "REQ-005", "verify", "安全约束验证故障诊断与安全需求"),
                ("CON-002", "REQ-003", "verify", "性能约束验证控制与执行需求"),
            ]
            return [
                {"id": f"REL-{index:03d}", "source": source, "target": target, "type": rel_type, "description": description}
                for index, (source, target, rel_type, description) in enumerate(relations, start=1)
            ]

        relations = [
            ("BLK-001", "BLK-002", "contains", "系统边界包含空间段"),
            ("BLK-001", "BLK-012", "contains", "系统边界包含地面段"),
            ("BLK-001", "BLK-016", "contains", "系统边界包含用户段"),
            ("BLK-001", "BLK-018", "contains", "系统边界连接外部互联网与核心网"),
            ("BLK-002", "BLK-003", "contains", "空间段包含100颗低轨通信星座"),
            ("BLK-003", "BLK-004", "contains", "星座包含轨道面与构型定义"),
            ("BLK-003", "BLK-005", "contains", "星座由低轨通信卫星组成"),
            ("BLK-005", "BLK-006", "contains", "单星包含宽带通信载荷"),
            ("BLK-005", "BLK-007", "contains", "单星包含星上数字处理器"),
            ("BLK-005", "BLK-008", "contains", "单星包含用户服务链路天线"),
            ("BLK-005", "BLK-009", "contains", "单星包含馈电链路终端"),
            ("BLK-005", "BLK-010", "contains", "单星包含星间链路终端"),
            ("BLK-005", "BLK-011", "contains", "单星包含平台与星务分系统"),
            ("BLK-012", "BLK-013", "contains", "地面段包含馈电网关站"),
            ("BLK-012", "BLK-014", "contains", "地面段包含网络运营控制中心"),
            ("BLK-012", "BLK-015", "contains", "地面段包含任务运控中心"),
            ("BLK-016", "BLK-017", "contains", "用户段包含宽带用户终端"),
            ("BLK-001", "REQ-001", "satisfy", "系统满足星座任务与服务目标"),
            ("BLK-001", "REQ-002", "satisfy", "系统根模块界定总体边界与外部参与方"),
            ("BLK-003", "REQ-003", "satisfy", "100颗低轨通信星座满足规模需求"),
            ("BLK-004", "REQ-004", "satisfy", "轨道构型满足覆盖与服务连续性需求"),
            ("BLK-006", "REQ-005", "satisfy", "宽带通信载荷满足用户容量与QoS需求"),
            ("BLK-013", "REQ-006", "satisfy", "馈电网关站满足馈电链路与网关接入需求"),
            ("BLK-010", "REQ-007", "satisfy", "星间链路终端满足空间路由需求"),
            ("BLK-017", "REQ-008", "satisfy", "用户终端满足接入与鉴权需求"),
            ("BLK-014", "REQ-009", "satisfy", "网络运营控制中心满足资源调度需求"),
            ("BLK-015", "REQ-010", "satisfy", "任务运控中心满足遥测遥控与在轨运维需求"),
            ("BLK-015", "REQ-011", "satisfy", "任务运控中心牵引故障处置与安全隔离闭环"),
            ("BLK-014", "REQ-012", "satisfy", "网络运营控制中心满足信息安全与业务隔离需求"),
            ("BLK-006", "REQ-013", "satisfy", "通信载荷设计满足频谱合规与电磁兼容需求"),
            ("IF-009", "REQ-014", "satisfy", "Bridge接口满足模型一致性与MagicDraw交付需求"),
            ("REQ-001", "UC-001", "trace", "任务目标追溯到总体需求澄清用例"),
            ("REQ-002", "UC-001", "trace", "系统边界追溯到总体需求澄清用例"),
            ("REQ-003", "UC-002", "trace", "100颗星座规模追溯到覆盖容量设计用例"),
            ("REQ-004", "UC-002", "trace", "覆盖连续性追溯到覆盖容量设计用例"),
            ("REQ-005", "UC-003", "trace", "用户链路容量追溯到用户宽带会话用例"),
            ("REQ-005", "UC-004", "trace", "QoS和业务保持追溯到切换用例"),
            ("REQ-006", "UC-005", "trace", "馈电链路需求追溯到馈电回传用例"),
            ("REQ-007", "UC-006", "trace", "星间链路需求追溯到空间路由用例"),
            ("REQ-008", "UC-003", "trace", "用户接入鉴权追溯到用户宽带会话用例"),
            ("REQ-009", "UC-007", "trace", "网络调度需求追溯到资源调度用例"),
            ("REQ-010", "UC-008", "trace", "在轨运维需求追溯到故障告警与重构用例"),
            ("REQ-011", "UC-008", "trace", "故障处置需求追溯到故障告警与重构用例"),
            ("REQ-012", "UC-007", "trace", "安全隔离需求追溯到资源调度和策略控制用例"),
            ("REQ-013", "UC-002", "trace", "频谱合规需求追溯到覆盖容量设计用例"),
            ("REQ-014", "UC-009", "trace", "模型交付需求追溯到MagicDraw同步用例"),
            ("UC-001", "ACT-001", "refine", "需求澄清用例细化为基线确认流程"),
            ("UC-002", "ACT-002", "refine", "覆盖容量设计用例细化为星座构型与覆盖分析流程"),
            ("UC-002", "ACT-003", "refine", "覆盖容量设计用例细化为链路预算与容量校核流程"),
            ("UC-003", "ACT-004", "refine", "用户宽带会话用例细化为用户接入流程"),
            ("UC-004", "ACT-005", "refine", "切换与业务保持用例细化为星间路由与切换流程"),
            ("UC-005", "ACT-006", "refine", "馈电回传用例细化为网关选择与馈电流程"),
            ("UC-006", "ACT-005", "refine", "星间路由用例细化为空间路由与切换流程"),
            ("UC-007", "ACT-007", "refine", "资源调度用例细化为网络资源调度流程"),
            ("UC-008", "ACT-008", "refine", "故障告警与重构用例细化为检测隔离恢复流程"),
            ("UC-009", "ACT-009", "refine", "MagicDraw同步用例细化为工程同步流程"),
            ("IF-001", "BLK-008", "allocate", "用户服务链路接口分配到用户服务链路天线"),
            ("IF-001", "BLK-017", "allocate", "用户服务链路接口分配到宽带用户终端"),
            ("IF-002", "BLK-009", "allocate", "馈电链路接口分配到馈电链路终端"),
            ("IF-002", "BLK-013", "allocate", "馈电链路接口分配到馈电网关站"),
            ("IF-003", "BLK-010", "allocate", "星间链路接口分配到星间链路终端"),
            ("IF-004", "BLK-011", "allocate", "遥测遥控接口分配到卫星平台与星务分系统"),
            ("IF-004", "BLK-015", "allocate", "遥测遥控接口分配到任务运控中心"),
            ("IF-005", "BLK-014", "allocate", "网络管理南向接口分配到网络运营控制中心"),
            ("IF-005", "BLK-006", "allocate", "网络管理南向接口分配到通信载荷资源控制"),
            ("IF-006", "BLK-013", "allocate", "网关核心网接口分配到馈电网关站"),
            ("IF-006", "BLK-018", "allocate", "网关核心网接口连接外部互联网与核心网"),
            ("IF-007", "BLK-015", "allocate", "时间频率与星历接口分配到任务运控中心"),
            ("IF-007", "BLK-011", "allocate", "时间频率与星历接口分配到卫星平台"),
            ("IF-008", "BLK-014", "allocate", "安全认证与密钥接口分配到网络运营控制中心"),
            ("IF-008", "BLK-017", "allocate", "安全认证与密钥接口分配到用户终端"),
            ("IF-009", "BLK-001", "allocate", "Bridge接口分配到SysML工程根模块"),
            ("CON-001", "REQ-003", "verify", "星座规模约束验证100颗卫星需求"),
            ("CON-002", "REQ-004", "verify", "轨道壳层与覆盖约束验证覆盖连续性需求"),
            ("CON-003", "REQ-005", "verify", "容量吞吐约束验证用户链路容量需求"),
            ("CON-004", "REQ-005", "verify", "业务时延约束验证QoS需求"),
            ("CON-005", "REQ-005", "verify", "链路预算约束验证用户链路质量需求"),
            ("CON-005", "REQ-006", "verify", "链路预算约束验证馈电链路需求"),
            ("CON-005", "REQ-007", "verify", "链路预算约束验证星间链路需求"),
            ("CON-006", "REQ-006", "verify", "网关可见与切换约束验证网关接入需求"),
            ("CON-007", "REQ-010", "verify", "可用性可靠性约束验证在轨运维需求"),
            ("CON-007", "REQ-011", "verify", "可用性可靠性约束验证故障处置需求"),
            ("CON-008", "REQ-012", "verify", "频谱安全合规约束验证信息安全需求"),
            ("CON-008", "REQ-013", "verify", "频谱安全合规约束验证频谱合规需求"),
        ]
        return [
            {"id": f"REL-{index:03d}", "source": source, "target": target, "type": rel_type, "description": description}
            for index, (source, target, rel_type, description) in enumerate(relations, start=1)
        ]

    def _attach_diagram_views(self, project: dict[str, Any], brief: str) -> dict[str, Any]:
        result = self._finalize_project(project, brief)
        existing = result.get("diagram_views")
        views: list[dict[str, Any]] = []
        if isinstance(existing, list) and existing:
            views = [dict(item) for item in existing if isinstance(item, dict)]
            source = "已有模型视图"
        elif self._should_generate_diagram_views(brief):
            views = self._generate_diagram_views_with_llm(result, brief)
            source = "AI动态生成"
            if not views:
                views = self._diagram_views_from_project(result, brief)
                source = "当前模型动态派生"
        else:
            source = "关键模块预生成"

        key_ibd_views = self._precompute_key_internal_block_diagrams(result, brief, views)
        behavior_views = self._behavior_diagram_views_from_project(result, brief)
        if key_ibd_views or behavior_views:
            views = self._dedupe_diagram_views([*views, *key_ibd_views, *behavior_views])
        result["diagram_views"] = views
        if views:
            key_count = len(key_ibd_views)
            behavior_count = len(behavior_views)
            suffix = f" 同时通过{source}得到{len(views)}张SysML视图"
            if key_count:
                suffix += f"，其中{key_count}张关键Block内部模块图已预生成，可双击模块直接下钻查看"
            if behavior_count:
                suffix += f"，并补充{behavior_count}张行为图（活动图/顺序图/状态图）"
            suffix += "。"
            result["summary"] = f"{str(result.get('summary') or '').strip()}{suffix}".strip()
        return result

    def _finalize_project(self, project: dict[str, Any], brief: str) -> dict[str, Any]:
        result = dict(project or {})
        elements = [dict(item) for item in (result.get("elements") or []) if isinstance(item, dict)]
        element_ids = {str(item.get("id") or "") for item in elements if item.get("id")}
        relationships = [
            dict(item)
            for item in (result.get("relationships") or [])
            if isinstance(item, dict)
            and str(item.get("source") or "") in element_ids
            and str(item.get("target") or "") in element_ids
            and str(item.get("source") or "") != str(item.get("target") or "")
        ]
        elements = self._localize_project_elements(elements, brief)
        relationships = self._enrich_project_relationships(elements, relationships)
        relationships = self._localize_project_relationships(relationships)
        package_name = self._safe_name(self._localize_project_name(result.get("project_name"), brief))
        summary = str(result.get("summary") or "").strip()
        if not summary or not self._contains_cjk(summary):
            summary = f"已根据当前需求生成 SysML 工程：{len(elements)} 个模型元素、{len(relationships)} 条关系。"
        assumptions = self._localize_text_list(result.get("assumptions"), brief)

        result["project_name"] = package_name
        result["summary"] = summary
        result["assumptions"] = assumptions
        result["elements"] = elements
        result["relationships"] = relationships
        result["sysml_text"] = self._render_sysml_text(package_name, elements, relationships)
        return result

    def _contains_cjk(self, value: Any) -> bool:
        return bool(re.search(r"[\u4e00-\u9fff]", str(value or "")))

    def _localize_project_name(self, value: Any, brief: str) -> str:
        name = str(value or "").strip()
        if name and self._contains_cjk(name):
            return name
        text = str(brief or "")
        if re.search(r"(英文|English|english|保持英文|英文命名)", text):
            return name or self._dynamic_project_name(brief)
        domain = self._detect_domain(text)
        if domain != "generic":
            return self._default_project_name(domain)
        subject = self._diagram_subject(text, "")
        if subject and self._contains_cjk(subject):
            return f"{subject}MBSE工程"
        return self._dynamic_project_name(brief)

    def _localize_text_list(self, value: Any, brief: str) -> list[str]:
        if not isinstance(value, list):
            return ["模型由当前对话动态生成，建议继续补充量化指标、接口口径和验收条件。"]
        result: list[str] = []
        for index, item in enumerate(value[:8], start=1):
            text = str(item or "").strip()
            if not text:
                continue
            if self._contains_cjk(text):
                result.append(text)
            else:
                result.append(f"建模假设{index}来自当前对话上下文，需在评审中补充量化依据。")
        return result or ["模型由当前对话动态生成，建议继续补充量化指标、接口口径和验收条件。"]

    def _localize_project_elements(self, elements: list[dict[str, Any]], brief: str) -> list[dict[str, Any]]:
        subject = self._diagram_subject(brief, "")
        localized: list[dict[str, Any]] = []
        for item in elements:
            next_item = dict(item)
            element_type = str(next_item.get("type") or "Block")
            element_id = str(next_item.get("id") or "")
            name = self._localize_display_name(next_item.get("name"), element_type, element_id, subject)
            next_item["name"] = name
            next_item["description"] = self._localize_description(next_item.get("description"), element_type, name)
            localized.append(next_item)
        return localized

    def _localize_project_relationships(self, relationships: list[dict[str, Any]]) -> list[dict[str, Any]]:
        localized: list[dict[str, Any]] = []
        for item in relationships:
            next_item = dict(item)
            rel_type = str(next_item.get("type") or "trace")
            next_item["description"] = self._localize_relationship_description(next_item.get("description"), rel_type)
            localized.append(next_item)
        return localized

    def _localize_display_name(self, value: Any, element_type: str, element_id: str, subject: str) -> str:
        name = str(value or "").strip()
        if self._contains_cjk(name):
            return name
        local_id = element_id or name
        cleaned = re.sub(r"[_-]+", " ", name).strip()
        cleaned = re.sub(r"^[A-Za-z]+-\d+\s*", "", cleaned).strip()
        normalized = re.sub(r"\s+", " ", cleaned).lower()
        exact = {
            "leo constellation": "低轨通信星座",
            "leo satellite": "低轨通信卫星",
            "satellite": "通信卫星",
            "user terminal": "用户终端",
            "gateway station": "馈电网关站",
            "tt&c station": "遥测遥控站",
            "network core": "网络核心",
            "network control center": "网络运营控制中心",
            "communication payload": "通信载荷",
            "isl terminal": "星间链路终端",
            "inter satellite link": "星间链路",
            "feeder link antenna": "馈电链路天线",
            "phased array antenna": "相控阵天线",
            "internet connector": "互联网连接接口",
            "provide internet connection": "提供互联网连接服务",
            "manage constellation": "星座管理",
            "route data via isl": "星间链路数据路由",
            "isl routing": "星间链路路由",
            "perform coverage optimization": "覆盖优化",
            "user data transmission": "用户数据传输",
            "beam switching and handover": "波束切换与越区切换",
            "beam switching": "波束切换",
            "user link interface": "用户链路接口",
            "feeder link interface": "馈电链路接口",
            "satellite interface": "卫星接口",
            "tt&c interface": "遥测遥控接口",
            "ground network interface": "地面网络接口",
            "link budget constraint": "链路预算约束",
            "masspower constraint": "质量功耗约束",
            "mass power constraint": "质量功耗约束",
            "power constraint": "功耗约束",
            "mass constraint": "质量约束",
        }
        if normalized in exact:
            return exact[normalized]
        for key, label in exact.items():
            if key in normalized:
                return label
        fallback = {
            "Requirement": "需求项",
            "Block": f"{subject or '系统'}结构模块",
            "UseCase": f"{subject or '系统'}能力用例",
            "Activity": f"{subject or '系统'}行为流程",
            "Interface": "接口",
            "ConstraintBlock": "约束",
            "Actor": "外部参与方",
        }.get(element_type, "模型元素")
        suffix = re.sub(r"^[A-Za-z]+-", "", local_id).strip() or "001"
        return f"{fallback}{suffix}"

    def _localize_description(self, value: Any, element_type: str, name: str) -> str:
        text = str(value or "").strip()
        if text and self._contains_cjk(text):
            return text
        templates = {
            "Requirement": f"{name}的需求说明，依据当前对话生成，后续需补充量化验收条件。",
            "Block": f"{name}承担系统结构中的对应职责，后续可细化端口、部件和约束。",
            "UseCase": f"{name}描述系统对外提供或内部协同完成的能力。",
            "Activity": f"{name}描述关键业务步骤、控制流或处置流程。",
            "Interface": f"{name}定义相关模块之间的信息、能量或控制交互边界。",
            "ConstraintBlock": f"{name}用于约束或验证相关需求、结构参数和运行边界。",
            "Actor": f"{name}表示系统边界外参与交互的角色或外部系统。",
        }
        return templates.get(element_type, f"{name}为当前模型中的候选元素，需在后续评审中细化。")

    def _localize_relationship_description(self, value: Any, rel_type: str) -> str:
        text = str(value or "").strip()
        if text and self._contains_cjk(text):
            return text
        mapping = {
            "contains": "系统结构包含该模型元素。",
            "connector": "模块之间存在结构连接、信息流或控制流。",
            "satisfy": "结构或功能元素满足对应需求。",
            "trace": "模型元素之间建立可追溯关系。",
            "allocate": "功能、接口或资源分配到对应结构元素。",
            "verify": "约束或验证项用于校核对应需求。",
            "refine": "模型元素对上层能力或需求进行细化。",
            "derivereqt": "需求之间存在派生关系。",
            "realize": "结构或行为元素实现对应能力。",
            "dependency": "模型元素之间存在依赖关系。",
            "association": "参与者或模型元素与目标能力有关联。",
            "include": "该能力包含必要的子能力。",
            "extend": "该能力在特定条件下扩展目标能力。",
            "controlflow": "行为步骤之间存在控制流转。",
            "objectflow": "行为步骤之间传递对象或数据。",
            "message": "交互参与方之间传递消息或请求。",
            "transition": "状态之间存在触发迁移。",
        }
        return mapping.get(rel_type.lower(), "模型元素之间建立语义关系。")

    def _enrich_project_relationships(
        self,
        elements: list[dict[str, Any]],
        relationships: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if not elements:
            return relationships

        by_type: dict[str, list[str]] = {}
        for item in elements:
            element_id = str(item.get("id") or "")
            if not element_id:
                continue
            by_type.setdefault(str(item.get("type") or "Block"), []).append(element_id)

        blocks = by_type.get("Block", [])
        requirements = by_type.get("Requirement", [])
        use_cases = by_type.get("UseCase", [])
        activities = by_type.get("Activity", [])
        interfaces = by_type.get("Interface", [])
        constraints = by_type.get("ConstraintBlock", [])
        if not blocks:
            return relationships

        enriched: list[dict[str, Any]] = []
        used_existing_ids: set[str] = set()
        next_existing_index = 1
        for item in relationships:
            normalized = self._normalize_enriched_relationship(item)
            if not normalized["id"] or normalized["id"] in used_existing_ids:
                rel_id = f"REL-{next_existing_index:03d}"
                while rel_id in used_existing_ids:
                    next_existing_index += 1
                    rel_id = f"REL-{next_existing_index:03d}"
                normalized["id"] = rel_id
                next_existing_index += 1
            used_existing_ids.add(normalized["id"])
            enriched.append(normalized)
        existing = {
            (
                str(item.get("source") or ""),
                str(item.get("target") or ""),
                str(item.get("type") or "trace"),
            )
            for item in enriched
        }
        used_ids = {str(item.get("id") or "") for item in enriched if item.get("id")}
        connected_ids = {
            endpoint
            for item in enriched
            for endpoint in (str(item.get("source") or ""), str(item.get("target") or ""))
            if endpoint
        }
        next_index = self._next_relationship_index(enriched)

        def add(source: str, target: str, rel_type: str, description: str) -> None:
            nonlocal next_index
            source = str(source or "")
            target = str(target or "")
            rel_type = self._normalize_relationship_type(rel_type)
            if not source or not target or source == target:
                return
            key = (source, target, rel_type)
            if key in existing:
                return
            rel_id = f"REL-{next_index:03d}"
            while rel_id in used_ids:
                next_index += 1
                rel_id = f"REL-{next_index:03d}"
            enriched.append(
                {
                    "id": rel_id,
                    "source": source,
                    "target": target,
                    "type": rel_type,
                    "description": description,
                }
            )
            existing.add(key)
            used_ids.add(rel_id)
            connected_ids.add(source)
            connected_ids.add(target)
            next_index += 1

        root_block = blocks[0]
        for block_id in blocks[1:]:
            if not self._has_relationship(enriched, root_block, block_id, {"contains"}):
                add(root_block, block_id, "contains", "系统结构包含该模块。")

        for index, block_id in enumerate(blocks[1:], start=1):
            previous = blocks[index - 1]
            if not self._has_relationship_between(enriched, previous, block_id, {"connector", "dependency"}):
                add(previous, block_id, "connector", "相邻结构模块之间存在主架构连接。")

        for index, req_id in enumerate(requirements):
            block_id = blocks[index % len(blocks)]
            if not self._has_relationship_to(enriched, req_id, {"satisfy"}):
                add(block_id, req_id, "satisfy", "结构模块满足对应需求。")
            if use_cases and not self._has_relationship_from(enriched, req_id, {"trace", "derivereqt"}):
                add(req_id, use_cases[index % len(use_cases)], "trace", "需求追溯到相关系统能力。")

        for index, use_case_id in enumerate(use_cases):
            block_id = blocks[index % len(blocks)]
            if not self._has_relationship_between(enriched, block_id, use_case_id, {"trace", "allocate", "refine"}):
                add(block_id, use_case_id, "trace", "结构模块支撑该系统能力实现。")
            if activities and not self._has_relationship_from(enriched, use_case_id, {"trace", "refine"}):
                add(use_case_id, activities[index % len(activities)], "trace", "用例由行为流程进一步细化。")

        for index, activity_id in enumerate(activities):
            if use_cases and activity_id not in connected_ids:
                add(use_cases[index % len(use_cases)], activity_id, "trace", "行为流程细化选定用例。")

        for index, interface_id in enumerate(interfaces):
            block_id = blocks[(index + 1) % len(blocks)]
            if not self._has_relationship_connected_to(enriched, interface_id, {"allocate", "connector", "trace"}):
                add(interface_id, block_id, "allocate", "接口分配到相关结构模块。")
            if use_cases and not self._has_relationship_between(enriched, use_cases[index % len(use_cases)], interface_id, {"trace", "dependency"}):
                add(use_cases[index % len(use_cases)], interface_id, "trace", "用例使用或暴露该接口。")

        for index, constraint_id in enumerate(constraints):
            if requirements and not self._has_relationship_from(enriched, constraint_id, {"verify"}):
                add(constraint_id, requirements[index % len(requirements)], "verify", "约束验证相关需求。")

        for element_id in [str(item.get("id") or "") for item in elements if item.get("id")]:
            if element_id in connected_ids:
                continue
            element_type = str(next((item.get("type") for item in elements if str(item.get("id") or "") == element_id), "Block"))
            if element_type == "Requirement":
                add(root_block, element_id, "satisfy", "为孤立需求补充满足关系。")
            elif element_type == "UseCase" and requirements:
                add(requirements[0], element_id, "trace", "为孤立用例补充需求追溯关系。")
            elif element_type == "Interface":
                add(element_id, root_block, "allocate", "为孤立接口补充分配关系。")
            elif element_type == "Activity" and use_cases:
                add(use_cases[0], element_id, "trace", "为孤立行为补充用例追溯关系。")
            elif element_type == "ConstraintBlock" and requirements:
                add(element_id, requirements[0], "verify", "为孤立约束补充验证关系。")
            elif element_id != root_block:
                add(root_block, element_id, "dependency", "为孤立模型元素补充依赖关系。")

        return enriched

    def _normalize_enriched_relationship(self, relationship: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(relationship)
        normalized["id"] = str(normalized.get("id") or normalized.get("local_id") or "").strip()
        normalized["source"] = str(normalized.get("source") or "").strip()
        normalized["target"] = str(normalized.get("target") or "").strip()
        normalized["type"] = self._normalize_relationship_type(normalized.get("type") or normalized.get("relationType"))
        normalized["description"] = str(normalized.get("description") or normalized.get("doc") or "").strip()
        return normalized

    def _next_relationship_index(self, relationships: list[dict[str, Any]]) -> int:
        max_index = 0
        for item in relationships:
            match = re.match(r"^REL-(\d+)$", str(item.get("id") or ""))
            if match:
                max_index = max(max_index, int(match.group(1)))
        return max_index + 1

    def _has_relationship(
        self,
        relationships: list[dict[str, Any]],
        source: str,
        target: str,
        rel_types: set[str],
    ) -> bool:
        return any(
            str(item.get("source") or "") == source
            and str(item.get("target") or "") == target
            and str(item.get("type") or "") in rel_types
            for item in relationships
        )

    def _has_relationship_between(
        self,
        relationships: list[dict[str, Any]],
        first: str,
        second: str,
        rel_types: set[str],
    ) -> bool:
        return any(
            {str(item.get("source") or ""), str(item.get("target") or "")} == {first, second}
            and str(item.get("type") or "") in rel_types
            for item in relationships
        )

    def _has_relationship_from(
        self,
        relationships: list[dict[str, Any]],
        source: str,
        rel_types: set[str],
    ) -> bool:
        return any(str(item.get("source") or "") == source and str(item.get("type") or "") in rel_types for item in relationships)

    def _has_relationship_to(
        self,
        relationships: list[dict[str, Any]],
        target: str,
        rel_types: set[str],
    ) -> bool:
        return any(str(item.get("target") or "") == target and str(item.get("type") or "") in rel_types for item in relationships)

    def _has_relationship_connected_to(
        self,
        relationships: list[dict[str, Any]],
        element_id: str,
        rel_types: set[str],
    ) -> bool:
        return any(
            (
                str(item.get("source") or "") == element_id
                or str(item.get("target") or "") == element_id
            )
            and str(item.get("type") or "") in rel_types
            for item in relationships
        )

    def _precompute_key_internal_block_diagrams(
        self,
        project: dict[str, Any],
        brief: str,
        existing_views: list[dict[str, Any]] | None = None,
        limit: int = 12,
    ) -> list[dict[str, Any]]:
        elements = [dict(item) for item in (project.get("elements") or []) if isinstance(item, dict)]
        relationships = [dict(item) for item in (project.get("relationships") or []) if isinstance(item, dict)]
        key_blocks = self._key_blocks_for_internal_views(elements, relationships, limit=limit)
        if not key_blocks:
            return []

        existing_focus_ids = {
            str(view.get("focus_element_id") or "")
            for view in (existing_views or [])
            if isinstance(view, dict) and str(view.get("diagram_type") or "") == "ibd"
        }
        views: list[dict[str, Any]] = []
        for focus in key_blocks:
            focus_id = str(focus.get("id") or "")
            if not focus_id or focus_id in existing_focus_ids:
                continue
            view = self._fallback_internal_block_diagram(
                {
                    "project_name": str(project.get("project_name") or "AI_MBSE_Project"),
                    "prompt": brief or "",
                    "focus_element": focus,
                    "elements": elements,
                    "relationships": relationships,
                }
            )
            view["id"] = f"FOCUS-{self._safe_id_fragment(focus_id)}-IBD"
            view["variant_id"] = f"FOCUS-{self._safe_id_fragment(focus_id)}"
            view["variant_name"] = f"关键模块预生成：{focus.get('name') or focus_id}"
            view["focus_element_id"] = focus_id
            view["description"] = f"系统生成总体模型时预生成的 {focus.get('name') or focus_id} 内部模块图，双击该模块可直接展示。"
            views.append(view)
        return views

    def _key_blocks_for_internal_views(
        self,
        elements: list[dict[str, Any]],
        relationships: list[dict[str, Any]],
        limit: int = 4,
    ) -> list[dict[str, Any]]:
        blocks = [item for item in elements if item.get("type") == "Block" and item.get("id")]
        if not blocks:
            return []
        by_id = {str(item.get("id")): item for item in blocks}
        contains = [rel for rel in relationships if str(rel.get("type") or "").lower() == "contains"]
        contained_targets = {str(rel.get("target") or "") for rel in contains}
        root_blocks = [item for item in blocks if str(item.get("id") or "") not in contained_targets]
        root = root_blocks[0] if root_blocks else blocks[0]
        root_id = str(root.get("id") or "")
        top_child_ids = [str(rel.get("target") or "") for rel in contains if str(rel.get("source") or "") == root_id]
        top_child_set = set(top_child_ids)
        degree: dict[str, int] = {str(item.get("id")): 0 for item in blocks}
        child_count: dict[str, int] = {str(item.get("id")): 0 for item in blocks}
        for rel in relationships:
            source = str(rel.get("source") or "")
            target = str(rel.get("target") or "")
            if source in degree:
                degree[source] += 1
            if target in degree:
                degree[target] += 1
        for rel in contains:
            source = str(rel.get("source") or "")
            if source in child_count:
                child_count[source] += 1
        signal_words = [
            "分系统",
            "子系统",
            "载荷",
            "平台",
            "链路",
            "网关",
            "控制",
            "处理",
            "管理",
            "中心",
            "网络",
            "服务",
            "接入",
            "路由",
            "执行",
        ]

        def score(item: dict[str, Any]) -> tuple[int, str]:
            item_id = str(item.get("id") or "")
            text = f"{item.get('name') or ''} {item.get('description') or ''}"
            value = degree.get(item_id, 0) + child_count.get(item_id, 0) * 3
            if item_id in top_child_set:
                value += 8
            if item_id == root_id and len(blocks) > 1:
                value -= 6
            value += sum(2 for word in signal_words if word in text)
            return value, str(item.get("name") or item_id)

        ordered_ids = [item_id for item_id in top_child_ids if item_id in by_id]
        remaining = [item for item in blocks if str(item.get("id") or "") not in set(ordered_ids)]
        ranked = sorted(remaining, key=score, reverse=True)
        ordered = [by_id[item_id] for item_id in ordered_ids] + ranked
        result: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in ordered:
            item_id = str(item.get("id") or "")
            if not item_id or item_id in seen:
                continue
            if item_id == root_id and len(blocks) > 1 and len(result) >= max(1, limit - 1):
                continue
            seen.add(item_id)
            result.append(item)
            if len(result) >= limit:
                break
        return result

    def _dedupe_diagram_views(self, views: list[dict[str, Any]]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        seen: set[str] = set()
        for view in views:
            if not isinstance(view, dict):
                continue
            key = str(view.get("id") or f"{view.get('variant_id')}-{view.get('diagram_type')}-{view.get('name')}")
            if key in seen:
                continue
            seen.add(key)
            result.append(view)
        return result

    def _should_generate_diagram_views(self, brief: str) -> bool:
        text = str(brief or "").lower()
        keywords = [
            "用例图",
            "内部模块图",
            "内部块图",
            "内部块",
            "ibd",
            "internal block",
            "通信载荷",
            "宽带通信载荷",
            "载荷分系统",
            "分系统",
            "子系统",
            "模块图",
            "图表",
            "接口图",
            "结构图",
            "多套",
            "备选",
            "方案",
        ]
        return any(keyword.lower() in text for keyword in keywords)

    def _generate_diagram_views_with_llm(self, project: dict[str, Any], brief: str) -> list[dict[str, Any]]:
        try:
            from app.services.llm_service import LLMService

            prompt = self._llm_diagram_prompt(project, brief)
            result = LLMService().chat(
                [
                    {
                        "role": "system",
                        "content": (
                            "你是资深 SysML 建模专家。你必须根据用户当前问题和已生成模型动态生成图，"
                            "不要使用预设行业模板，不要因为出现某个关键词就切换到固定方案。只返回 JSON。"
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                task_type="model_generation",
            )
            data = self._try_parse_json_object(str(result.get("answer") or ""))
            if not data:
                return []
            return self._normalize_llm_diagram_views(data, project, brief)
        except Exception:
            return []

    def _llm_diagram_prompt(self, project: dict[str, Any], brief: str) -> str:
        project_context = {
            "project_name": project.get("project_name"),
            "summary": project.get("summary"),
            "assumptions": project.get("assumptions") or [],
            "elements": [
                {
                    "id": item.get("id"),
                    "name": item.get("name"),
                    "type": item.get("type"),
                    "description": item.get("description"),
                    "package": item.get("package"),
                }
                for item in (project.get("elements") or [])
            ],
            "relationships": [
                {
                    "id": item.get("id"),
                    "source": item.get("source"),
                    "target": item.get("target"),
                    "type": item.get("type"),
                    "description": item.get("description"),
                }
                for item in (project.get("relationships") or [])
            ],
        }
        return f"""
请根据“用户真实意图”和“当前模型元素”动态生成 SysML 用例图和内部模块图（IBD）。

重要要求：
1. 不要套用预置模板；必须从用户问题、对话上下文和当前模型元素判断建模层级。
2. 如果用户是在做“总体方案/系统级方案/星座方案”，图中应体现总体系统边界、主要外部参与方、空间段、地面段、用户段、运控/运营等系统级组成。
3. 只有用户明确要求某个“分系统/载荷/部件内部设计”时，IBD 才聚焦该分系统内部部件。
4. 用例图只表达外部参与者与系统能力；IBD 只表达内部 parts/interfaces/connectors；两者通过 trace_links 关联。
5. 输出必须是一个 JSON 对象，不要 Markdown，不要解释。

用户与AI上下文：
{brief}

当前模型：
{json.dumps(project_context, ensure_ascii=False)}

返回 JSON Schema：
{{
  "variant_id": "BASELINE",
  "variant_name": "根据当前问题动态生成的基线方案",
  "diagram_views": [
    {{
      "id": "AI-USECASE",
      "diagram_type": "use_case",
      "name": "图名",
      "description": "为什么这是当前问题对应的用例图",
      "rationale": "建模层级和边界说明",
      "elements": [
        {{"id": "ACTOR-001", "name": "参与者", "type": "Actor", "description": "说明", "package": "00_Actors", "status": "candidate"}},
        {{"id": "UC-001", "name": "系统能力", "type": "UseCase", "description": "说明", "package": "03_Behavior", "status": "candidate"}}
      ],
      "relationships": [
        {{"id": "DREL-UC-001", "source": "ACTOR-001", "target": "UC-001", "type": "association", "description": "参与者使用该能力"}},
        {{"id": "DREL-UC-002", "source": "UC-001", "target": "UC-002", "type": "include", "description": "必要子能力"}}
      ],
      "trace_links": [
        {{"usecase_id": "UC-001", "element_ids": ["IBD-BLK-001"], "relation": "realize", "description": "该用例由这些内部模块实现"}}
      ]
    }},
    {{
      "id": "AI-IBD",
      "diagram_type": "ibd",
      "name": "图名",
      "description": "为什么这是当前问题对应的内部模块图",
      "rationale": "内部结构边界说明",
      "elements": [
        {{"id": "IBD-BLK-001", "name": "内部模块", "type": "Block", "description": "说明", "package": "02_Structure", "status": "candidate"}},
        {{"id": "IBD-IF-001", "name": "边界接口", "type": "Interface", "description": "说明", "package": "04_Interfaces", "status": "candidate"}}
      ],
      "relationships": [
        {{"id": "DREL-IBD-001", "source": "IBD-BLK-001", "target": "IBD-IF-001", "type": "connector", "description": "连接/流向说明"}}
      ],
      "trace_links": [
        {{"usecase_id": "UC-001", "element_ids": ["IBD-BLK-001"], "relation": "realize", "description": "该用例由这些内部模块实现"}}
      ]
    }}
  ]
}}
""".strip()

    def _normalize_llm_diagram_views(self, data: dict[str, Any], project: dict[str, Any], brief: str) -> list[dict[str, Any]]:
        raw_views = data.get("diagram_views") or data.get("views") or []
        if not isinstance(raw_views, list):
            return []

        variant_id = str(data.get("variant_id") or "BASELINE").strip() or "BASELINE"
        variant_name = str(data.get("variant_name") or "AI动态基线方案").strip() or "AI动态基线方案"
        views: list[dict[str, Any]] = []
        all_element_ids: set[str] = set()
        global_id_map: dict[str, str] = {}

        for raw_view in raw_views:
            if not isinstance(raw_view, dict):
                continue
            diagram_type = self._normalize_diagram_type(raw_view.get("diagram_type") or raw_view.get("type"))
            if diagram_type not in {"use_case", "ibd", "activity", "sequence", "state"}:
                continue
            elements, id_map = self._normalize_diagram_elements(raw_view.get("elements"), diagram_type)
            if not elements:
                continue
            element_ids = {item["id"] for item in elements}
            global_id_map.update(id_map)
            relationships = self._normalize_diagram_relationships(raw_view.get("relationships"), element_ids, id_map, diagram_type)
            layout = self._normalize_or_build_diagram_layout(raw_view.get("layout"), raw_view, elements, relationships, diagram_type)
            view = {
                "id": str(raw_view.get("id") or self._default_diagram_view_id(diagram_type)).strip(),
                "variant_id": str(raw_view.get("variant_id") or variant_id).strip() or variant_id,
                "variant_name": str(raw_view.get("variant_name") or variant_name).strip() or variant_name,
                "diagram_type": diagram_type,
                "name": str(raw_view.get("name") or self._default_diagram_view_name(diagram_type)).strip(),
                "description": str(raw_view.get("description") or "").strip(),
                "rationale": str(raw_view.get("rationale") or "").strip(),
                "elements": elements,
                "relationships": relationships,
                "layout": layout,
                "sysml_text": self._render_sysml_text(
                    f"{project.get('project_name') or 'AI_MBSE_Project'}_{diagram_type}",
                    elements,
                    relationships,
                ),
                "_raw_trace_links": raw_view.get("trace_links") or [],
            }
            all_element_ids.update(element_ids)
            views.append(view)

        if not {"use_case", "ibd"}.issubset({view["diagram_type"] for view in views}):
            return []

        for view in views:
            view["trace_links"] = self._normalize_diagram_trace_links(view.pop("_raw_trace_links", []), all_element_ids, global_id_map)
        return views

    def _default_diagram_view_id(self, diagram_type: str) -> str:
        return {
            "use_case": "AI-USECASE",
            "ibd": "AI-IBD",
            "activity": "AI-ACTIVITY",
            "sequence": "AI-SEQUENCE",
            "state": "AI-STATE",
        }.get(diagram_type, "AI-DIAGRAM")

    def _default_diagram_view_name(self, diagram_type: str) -> str:
        return {
            "use_case": "AI动态用例图",
            "ibd": "AI动态内部模块图（IBD）",
            "activity": "AI动态活动图",
            "sequence": "AI动态顺序图",
            "state": "AI动态状态图",
        }.get(diagram_type, "AI动态图")

    def _normalize_diagram_type(self, value: Any) -> str:
        raw = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
        if raw in {"usecase", "use_case", "用例图", "uc"}:
            return "use_case"
        if raw in {"ibd", "internal_block", "internal_block_diagram", "内部模块图", "内部块图"}:
            return "ibd"
        if raw in {"activity", "activity_diagram", "活动图", "行为图"}:
            return "activity"
        if raw in {"sequence", "sequence_diagram", "顺序图", "时序图", "序列图"}:
            return "sequence"
        if raw in {"state", "state_diagram", "state_machine", "状态图", "状态机图"}:
            return "state"
        return raw

    def _normalize_diagram_elements(self, raw_elements: Any, diagram_type: str) -> tuple[list[dict[str, Any]], dict[str, str]]:
        if not isinstance(raw_elements, list):
            return [], {}
        elements: list[dict[str, Any]] = []
        id_map: dict[str, str] = {}
        used_ids: set[str] = set()
        counters: dict[str, int] = {}
        for raw in raw_elements:
            if not isinstance(raw, dict):
                continue
            element_type = self._normalize_diagram_element_type(raw.get("type") or raw.get("kind"), diagram_type)
            prefix = "ACTOR" if element_type == "Actor" else self._element_prefix(element_type)
            if diagram_type == "ibd" and element_type == "Block":
                prefix = "IBD-BLK"
            if diagram_type == "ibd" and element_type == "Interface":
                prefix = "IBD-IF"
            if diagram_type == "activity" and element_type == "Activity":
                prefix = "BHV-ACT"
            if diagram_type == "sequence" and element_type == "Actor":
                prefix = "BHV-ACTOR"
            if diagram_type == "state" and element_type == "Activity":
                prefix = "BHV-STATE"
            counters[prefix] = counters.get(prefix, 0) + 1
            original_id = str(raw.get("id") or raw.get("local_id") or "").strip()
            element_id = self._normalize_diagram_element_id(original_id, prefix, counters[prefix], used_ids)
            name = str(raw.get("name") or raw.get("title") or element_id).strip()
            description = str(raw.get("description") or raw.get("doc") or raw.get("text") or name).strip()
            package = str(raw.get("package") or self._default_element_package(element_type)).strip()
            elements.append(
                {
                    "id": element_id,
                    "name": name or element_id,
                    "type": element_type,
                    "description": description or name or element_id,
                    "package": package or self._default_element_package(element_type),
                    "source_requirement": None,
                    "status": str(raw.get("status") or "candidate").strip() or "candidate",
                }
            )
            if original_id:
                id_map[original_id] = element_id
            id_map[element_id] = element_id
        return elements, id_map

    def _normalize_diagram_element_type(self, value: Any, diagram_type: str) -> str:
        raw = str(value or "").strip().lower().replace(" ", "").replace("_", "")
        if raw in {"actor", "参与者", "外部参与者"}:
            return "Actor"
        if raw in {"usecase", "用例"}:
            return "UseCase"
        if raw in {"interface", "interfaceblock", "接口", "边界接口"}:
            return "Interface"
        if raw in {"block", "part", "模块", "部件", "内部模块"}:
            return "Block"
        if raw in {"activity", "action", "行为", "活动", "动作", "state", "状态"}:
            return "Activity"
        if diagram_type == "use_case":
            return "UseCase"
        if diagram_type in {"activity", "state"}:
            return "Activity"
        if diagram_type == "sequence" and raw in {"participant", "lifeline", "参与方", "生命线"}:
            return "Block"
        return "Block"

    def _normalize_diagram_element_id(self, value: str, prefix: str, index: int, used_ids: set[str]) -> str:
        cleaned = re.sub(r"[^0-9A-Za-z_-]+", "-", str(value or "").strip()).strip("-_").upper()
        if not cleaned or not cleaned.startswith(f"{prefix}-"):
            cleaned = f"{prefix}-{index:03d}"
        base = cleaned
        suffix = 2
        while cleaned in used_ids:
            cleaned = f"{base}-{suffix}"
            suffix += 1
        used_ids.add(cleaned)
        return cleaned

    def _normalize_diagram_relationships(
        self,
        raw_relationships: Any,
        element_ids: set[str],
        id_map: dict[str, str],
        diagram_type: str,
    ) -> list[dict[str, Any]]:
        if not isinstance(raw_relationships, list):
            return []
        relationships: list[dict[str, Any]] = []
        used_ids: set[str] = set()
        for index, raw in enumerate(raw_relationships, start=1):
            if not isinstance(raw, dict):
                continue
            source = id_map.get(str(raw.get("source") or raw.get("from") or "").strip())
            target = id_map.get(str(raw.get("target") or raw.get("to") or "").strip())
            if not source or not target or source not in element_ids or target not in element_ids or source == target:
                continue
            prefix = {
                "use_case": "DREL-UC",
                "ibd": "DREL-IBD",
                "activity": "DREL-ACT",
                "sequence": "DREL-SEQ",
                "state": "DREL-STATE",
            }.get(diagram_type, "DREL-DG")
            rel_id = self._normalize_diagram_relationship_id(str(raw.get("id") or raw.get("local_id") or ""), prefix, index, used_ids)
            relationships.append(
                {
                    "id": rel_id,
                    "source": source,
                    "target": target,
                    "type": self._normalize_diagram_relationship_type(raw.get("type") or raw.get("relationType"), diagram_type),
                    "description": str(raw.get("description") or raw.get("doc") or "").strip(),
                }
            )
        return relationships

    def _normalize_diagram_relationship_id(self, value: str, prefix: str, index: int, used_ids: set[str]) -> str:
        cleaned = re.sub(r"[^0-9A-Za-z_-]+", "-", str(value or "").strip()).strip("-_").upper()
        if not cleaned or not cleaned.startswith(f"{prefix}-"):
            cleaned = f"{prefix}-{index:03d}"
        base = cleaned
        suffix = 2
        while cleaned in used_ids:
            cleaned = f"{base}-{suffix}"
            suffix += 1
        used_ids.add(cleaned)
        return cleaned

    def _normalize_diagram_relationship_type(self, value: Any, diagram_type: str) -> str:
        raw = str(value or "").strip()
        lowered = raw.lower()
        allowed = {
            "association",
            "include",
            "extend",
            "connector",
            "allocate",
            "realize",
            "trace",
            "dependency",
            "controlflow",
            "objectflow",
            "message",
            "transition",
        }
        if lowered in allowed:
            return lowered
        if diagram_type == "ibd":
            return "connector"
        if diagram_type == "activity":
            return "controlflow"
        if diagram_type == "sequence":
            return "message"
        if diagram_type == "state":
            return "transition"
        return "association"

    def _normalize_or_build_diagram_layout(
        self,
        raw_layout: Any,
        raw_view: dict[str, Any],
        elements: list[dict[str, Any]],
        relationships: list[dict[str, Any]],
        diagram_type: str,
    ) -> dict[str, Any]:
        if isinstance(raw_layout, dict) and isinstance(raw_layout.get("nodes"), list):
            nodes = [dict(node) for node in raw_layout.get("nodes") if isinstance(node, dict)]
            if nodes:
                layout = self._diagram_layout(
                    str(raw_layout.get("diagram_name") or raw_view.get("name") or f"AI_{diagram_type}_View"),
                    nodes,
                    relationships,
                    int(float(raw_layout.get("width") or 1100)),
                    int(float(raw_layout.get("height") or 620)),
                )
                layout["diagram_type"] = diagram_type
                return layout
        return self._build_diagram_layout_from_elements(
            str(raw_view.get("name") or f"AI_{diagram_type}_View"),
            elements,
            relationships,
            diagram_type,
        )

    def _build_diagram_layout_from_elements(
        self,
        diagram_name: str,
        elements: list[dict[str, Any]],
        relationships: list[dict[str, Any]],
        diagram_type: str,
    ) -> dict[str, Any]:
        if diagram_type == "use_case":
            actors = [item for item in elements if item["type"] == "Actor"]
            usecases = [item for item in elements if item["type"] == "UseCase"]
            others = [item for item in elements if item["type"] not in {"Actor", "UseCase"}]
            nodes: list[dict[str, Any]] = []
            for index, item in enumerate(actors):
                side_x = 70 if index % 2 == 0 else 820
                nodes.append(
                    {
                        "id": item["id"],
                        "element_id": item["id"],
                        "name": item["name"],
                        "label": item["name"],
                        "type": "Actor",
                        "stereotype_label": "actor",
                        "shape": "actor",
                        "x": side_x,
                        "y": 110 + (index // 2) * 160,
                        "width": 170,
                        "height": 105,
                    }
                )
            for index, item in enumerate(usecases + others):
                nodes.append(
                    {
                        "id": item["id"],
                        "element_id": item["id"],
                        "name": item["name"],
                        "label": item["name"],
                        "type": item["type"],
                        "stereotype_label": "use case" if item["type"] == "UseCase" else self._layout_stereotype(item["type"]),
                        "shape": "ellipse" if item["type"] == "UseCase" else "rect",
                        "x": 395,
                        "y": 80 + index * 100,
                        "width": 270,
                        "height": 72,
                    }
                )
            height = max(560, 160 + max(len(usecases) + len(others), max(1, len(actors) // 2)) * 105)
            layout = self._diagram_layout(diagram_name, nodes, relationships, 1080, height)
            layout["diagram_type"] = diagram_type
            return layout

        if diagram_type == "activity":
            nodes = []
            for index, item in enumerate(elements):
                nodes.append(
                    {
                        "id": item["id"],
                        "element_id": item["id"],
                        "name": item["name"],
                        "label": item["name"],
                        "type": item["type"],
                        "stereotype_label": "activity" if item["type"] == "Activity" else self._layout_stereotype(item["type"]),
                        "shape": "soft" if item["type"] == "Activity" else "rect",
                        "x": 380,
                        "y": 80 + index * 105,
                        "width": 300,
                        "height": 70,
                    }
                )
            height = max(560, 170 + len(elements) * 105)
            layout = self._diagram_layout(diagram_name, nodes, relationships, 1060, height)
            layout["diagram_type"] = diagram_type
            return layout

        if diagram_type == "sequence":
            participants = [item for item in elements if item["type"] in {"Actor", "Block", "Interface"}]
            steps = [item for item in elements if item not in participants]
            nodes = []
            for index, item in enumerate(participants):
                nodes.append(
                    {
                        "id": item["id"],
                        "element_id": item["id"],
                        "name": item["name"],
                        "label": item["name"],
                        "type": item["type"],
                        "stereotype_label": "lifeline",
                        "shape": "actor" if item["type"] == "Actor" else "rect",
                        "x": 70 + index * 245,
                        "y": 70,
                        "width": 190,
                        "height": 72,
                    }
                )
            for index, item in enumerate(steps):
                nodes.append(
                    {
                        "id": item["id"],
                        "element_id": item["id"],
                        "name": item["name"],
                        "label": item["name"],
                        "type": item["type"],
                        "stereotype_label": self._layout_stereotype(item["type"]),
                        "shape": "soft",
                        "x": 100 + (index % max(1, len(participants))) * 245,
                        "y": 210 + index * 80,
                        "width": 210,
                        "height": 58,
                    }
                )
            width = max(980, 160 + len(participants) * 245)
            height = max(560, 260 + max(len(steps), len(relationships)) * 80)
            layout = self._diagram_layout(diagram_name, nodes, relationships, width, height)
            layout["diagram_type"] = diagram_type
            return layout

        if diagram_type == "state":
            nodes = []
            for index, item in enumerate(elements):
                column = index % 3
                row = index // 3
                nodes.append(
                    {
                        "id": item["id"],
                        "element_id": item["id"],
                        "name": item["name"],
                        "label": item["name"],
                        "type": item["type"],
                        "stereotype_label": "state",
                        "shape": "soft",
                        "x": 110 + column * 290,
                        "y": 120 + row * 150,
                        "width": 230,
                        "height": 78,
                    }
                )
            height = max(520, 250 + ((len(elements) + 2) // 3) * 150)
            layout = self._diagram_layout(diagram_name, nodes, relationships, 1020, height)
            layout["diagram_type"] = diagram_type
            return layout

        nodes = []
        for index, item in enumerate(elements):
            column = index % 4
            row = index // 4
            nodes.append(
                {
                    "id": item["id"],
                    "element_id": item["id"],
                    "name": item["name"],
                    "label": item["name"],
                    "type": item["type"],
                    "stereotype_label": "part" if item["type"] == "Block" else "interface",
                    "shape": "soft" if item["type"] == "Interface" else "rect",
                    "x": 80 + column * 260,
                    "y": 110 + row * 150,
                    "width": 205,
                    "height": 76,
                }
            )
        height = max(520, 230 + ((len(elements) + 3) // 4) * 150)
        layout = self._diagram_layout(diagram_name, nodes, relationships, 1140, height)
        layout["diagram_type"] = diagram_type
        return layout

    def _normalize_diagram_trace_links(self, raw_links: Any, all_element_ids: set[str], id_map: dict[str, str] | None = None) -> list[dict[str, Any]]:
        if not isinstance(raw_links, list):
            return []
        id_map = id_map or {}
        links: list[dict[str, Any]] = []
        for raw in raw_links:
            if not isinstance(raw, dict):
                continue
            raw_usecase_id = str(raw.get("usecase_id") or raw.get("useCaseId") or raw.get("source") or "").strip()
            usecase_id = id_map.get(raw_usecase_id) or raw_usecase_id.upper()
            element_ids = [
                id_map.get(str(item).strip()) or str(item).strip().upper()
                for item in (raw.get("element_ids") or raw.get("elementIds") or raw.get("targets") or [])
                if str(item).strip()
            ]
            valid_targets = [item for item in element_ids if item in all_element_ids]
            if usecase_id in all_element_ids and valid_targets:
                links.append(
                    {
                        "usecase_id": usecase_id,
                        "element_ids": valid_targets,
                        "relation": str(raw.get("relation") or "realize").strip() or "realize",
                        "description": str(raw.get("description") or "").strip(),
                    }
                )
        return links

    def _diagram_views_from_project(self, project: dict[str, Any], brief: str) -> list[dict[str, Any]]:
        elements = [dict(item) for item in (project.get("elements") or []) if isinstance(item, dict)]
        if not elements:
            return []
        usecases = [item for item in elements if item.get("type") == "UseCase"][:6]
        blocks = [item for item in elements if item.get("type") == "Block"][:8]
        interfaces = [item for item in elements if item.get("type") == "Interface"][:4]
        if not usecases or not blocks:
            return []
        actors = [
            self._diagram_element("ACTOR-001", "主要使用方", "Actor", "根据当前问题动态派生的外部使用方。", "00_Actors"),
            self._diagram_element("ACTOR-002", "运维/管理方", "Actor", "根据当前问题动态派生的外部运维或管理方。", "00_Actors"),
        ]
        usecase_elements = [
            self._diagram_element(str(item["id"]), str(item.get("name") or item["id"]), "UseCase", str(item.get("description") or ""), "03_Behavior")
            for item in usecases
        ]
        uc_relationships = []
        for index, item in enumerate(usecase_elements, start=1):
            uc_relationships.append(
                {
                    "id": f"DREL-UC-{index:03d}",
                    "source": actors[(index - 1) % len(actors)]["id"],
                    "target": item["id"],
                    "type": "association",
                    "description": "由当前模型元素动态派生的参与关系。",
                }
            )
        ibd_elements = [
            self._diagram_element(str(item["id"]), str(item.get("name") or item["id"]), "Block", str(item.get("description") or ""), "02_Structure")
            for item in blocks
        ] + [
            self._diagram_element(str(item["id"]), str(item.get("name") or item["id"]), "Interface", str(item.get("description") or ""), "04_Interfaces")
            for item in interfaces
        ]
        ibd_ids = [item["id"] for item in ibd_elements]
        ibd_relationships = [
            {
                "id": f"DREL-IBD-{index:03d}",
                "source": left,
                "target": right,
                "type": "connector",
                "description": "由当前模型结构顺序动态派生的内部连接。",
            }
            for index, (left, right) in enumerate(zip(ibd_ids, ibd_ids[1:]), start=1)
        ]
        trace_links = [
            {
                "usecase_id": usecase["id"],
                "element_ids": [blocks[index % len(blocks)]["id"]],
                "relation": "realize",
                "description": "由当前模型中用例和结构模块动态建立的实现映射。",
            }
            for index, usecase in enumerate(usecase_elements)
        ]
        usecase_view = {
            "id": "AI-USECASE-FALLBACK",
            "variant_id": "BASELINE",
            "variant_name": "当前模型动态派生方案",
            "diagram_type": "use_case",
            "name": "当前模型动态派生用例图",
            "description": "LLM图生成不可用时，根据当前模型中的UseCase动态派生。",
            "rationale": "该图不是行业模板，而是由当前模型元素派生，用于保持图表预览不断裂。",
            "elements": actors + usecase_elements,
            "relationships": uc_relationships,
            "trace_links": trace_links,
        }
        usecase_view["layout"] = self._build_diagram_layout_from_elements(usecase_view["name"], usecase_view["elements"], uc_relationships, "use_case")
        usecase_view["sysml_text"] = self._render_sysml_text(f"{project.get('project_name') or 'AI_MBSE_Project'}_UseCase", usecase_view["elements"], uc_relationships)
        ibd_view = {
            "id": "AI-IBD-FALLBACK",
            "variant_id": "BASELINE",
            "variant_name": "当前模型动态派生方案",
            "diagram_type": "ibd",
            "name": "当前模型动态派生内部模块图（IBD）",
            "description": "LLM图生成不可用时，根据当前模型中的Block和Interface动态派生。",
            "rationale": "该图不是行业模板，而是由当前模型结构元素派生，用于保持图表预览不断裂。",
            "elements": ibd_elements,
            "relationships": ibd_relationships,
            "trace_links": trace_links,
        }
        ibd_view["layout"] = self._build_diagram_layout_from_elements(ibd_view["name"], ibd_elements, ibd_relationships, "ibd")
        ibd_view["sysml_text"] = self._render_sysml_text(f"{project.get('project_name') or 'AI_MBSE_Project'}_IBD", ibd_elements, ibd_relationships)
        return [usecase_view, ibd_view]

    def _behavior_diagram_views_from_project(self, project: dict[str, Any], brief: str) -> list[dict[str, Any]]:
        elements = [dict(item) for item in (project.get("elements") or []) if isinstance(item, dict)]
        if not elements:
            return []
        project_name = str(project.get("project_name") or "AI_MBSE_Project")
        subject = self._diagram_subject(brief, project_name)
        activities = [item for item in elements if item.get("type") == "Activity"]
        usecases = [item for item in elements if item.get("type") == "UseCase"]
        blocks = [item for item in elements if item.get("type") == "Block"]
        interfaces = [item for item in elements if item.get("type") == "Interface"]
        if not (activities or usecases or blocks):
            return []

        activity_elements = [
            self._diagram_element(str(item["id"]), str(item.get("name") or item["id"]), "Activity", str(item.get("description") or ""), "03_Behavior")
            for item in activities[:8]
        ]
        seed_activity_names = [
            f"接收{subject}任务输入",
            "解析任务目标与约束",
            "配置系统资源与链路",
            "执行核心业务处理",
            "监测运行状态",
            "输出服务结果与告警",
        ]
        existing_activity_names = {item["name"] for item in activity_elements}
        for name in seed_activity_names:
            if len(activity_elements) >= 6:
                break
            if name in existing_activity_names:
                continue
            index = len(activity_elements) + 1
            activity_elements.append(
                self._diagram_element(
                    f"BHV-ACT-{index:03d}",
                    name,
                    "Activity",
                    f"{name}是根据当前模型补充的候选行为步骤。",
                    "03_Behavior",
                )
            )
            existing_activity_names.add(name)
        activity_relationships = [
            {
                "id": f"DREL-ACT-{index:03d}",
                "source": left["id"],
                "target": right["id"],
                "type": "controlflow",
                "description": "关键行为步骤之间的控制流转。",
            }
            for index, (left, right) in enumerate(zip(activity_elements, activity_elements[1:]), start=1)
        ]
        activity_view = {
            "id": "AI-ACTIVITY-FLOW",
            "variant_id": "BASELINE",
            "variant_name": "行为视图补充方案",
            "diagram_type": "activity",
            "name": "关键业务活动图",
            "description": "根据当前模型中的 Activity 与系统能力补充生成的关键业务活动图。",
            "rationale": "用于在 MagicDraw 工程中直接呈现行为流程，而不是只停留在结构追溯。",
            "elements": activity_elements,
            "relationships": activity_relationships,
            "trace_links": [],
        }
        activity_view["layout"] = self._build_diagram_layout_from_elements(activity_view["name"], activity_elements, activity_relationships, "activity")
        activity_view["sysml_text"] = self._render_sysml_text(f"{project_name}_Activity", activity_elements, activity_relationships)

        participant_sources = blocks[:4] + interfaces[:2]
        sequence_elements = [
            self._diagram_element(str(item["id"]), str(item.get("name") or item["id"]), str(item.get("type") or "Block"), str(item.get("description") or ""), str(item.get("package") or self._default_element_package(str(item.get("type") or "Block"))))
            for item in participant_sources
        ]
        if len(sequence_elements) < 2:
            sequence_elements.insert(0, self._diagram_element("BHV-ACTOR-001", "外部参与方", "Actor", "与系统发生业务交互的外部角色。", "00_Actors"))
            sequence_elements.append(self._diagram_element("BHV-BLK-001", f"{subject}核心系统", "Block", "承载当前模型核心业务处理的系统边界。", "02_Structure"))
        if len(sequence_elements) < 3 and usecases:
            sequence_elements.append(
                self._diagram_element("BHV-BLK-002", "能力编排模块", "Block", "根据用例补充的交互编排模块。", "02_Structure")
            )
        messages = [str(item.get("name") or item.get("id")) for item in usecases[:5]] or [item["name"] for item in activity_elements[:5]]
        sequence_relationships: list[dict[str, Any]] = []
        if len(sequence_elements) >= 2:
            for index, message in enumerate(messages[: max(1, len(sequence_elements) - 1)], start=1):
                source = sequence_elements[(index - 1) % len(sequence_elements)]["id"]
                target = sequence_elements[index % len(sequence_elements)]["id"]
                if source == target:
                    continue
                sequence_relationships.append(
                    {
                        "id": f"DREL-SEQ-{index:03d}",
                        "source": source,
                        "target": target,
                        "type": "message",
                        "description": f"交互消息：{message}。",
                    }
                )
        sequence_view = {
            "id": "AI-SEQUENCE-FLOW",
            "variant_id": "BASELINE",
            "variant_name": "行为视图补充方案",
            "diagram_type": "sequence",
            "name": "关键交互顺序图",
            "description": "根据当前模型中的结构模块、接口和用例补充生成的关键交互顺序图。",
            "rationale": "用于表达外部参与方、结构模块和接口之间的业务消息顺序。",
            "elements": sequence_elements,
            "relationships": sequence_relationships,
            "trace_links": [],
        }
        sequence_view["layout"] = self._build_diagram_layout_from_elements(sequence_view["name"], sequence_elements, sequence_relationships, "sequence")
        sequence_view["sysml_text"] = self._render_sysml_text(f"{project_name}_Sequence", sequence_elements, sequence_relationships)

        state_names = ["待命与任务接收状态", "资源配置状态", "业务运行状态", "降级重构状态", "故障处置与恢复状态"]
        state_elements = [
            self._diagram_element(
                f"BHV-STATE-{index:03d}",
                name,
                "Activity",
                f"{subject}在{name}下的运行行为和约束。",
                "03_Behavior",
            )
            for index, name in enumerate(state_names, start=1)
        ]
        state_relationships = [
            {
                "id": f"DREL-STATE-{index:03d}",
                "source": left["id"],
                "target": right["id"],
                "type": "transition",
                "description": "运行状态之间的触发迁移。",
            }
            for index, (left, right) in enumerate(zip(state_elements, state_elements[1:]), start=1)
        ]
        state_relationships.append(
            {
                "id": f"DREL-STATE-{len(state_relationships) + 1:03d}",
                "source": state_elements[-1]["id"],
                "target": state_elements[0]["id"],
                "type": "transition",
                "description": "故障处置完成后回到待命或任务接收状态。",
            }
        )
        state_view = {
            "id": "AI-STATE-FLOW",
            "variant_id": "BASELINE",
            "variant_name": "行为视图补充方案",
            "diagram_type": "state",
            "name": "运行状态图",
            "description": "根据当前模型补充生成的系统运行状态图。",
            "rationale": "用于在完整 MagicDraw 工程中体现运行状态、降级重构和故障恢复逻辑。",
            "elements": state_elements,
            "relationships": state_relationships,
            "trace_links": [],
        }
        state_view["layout"] = self._build_diagram_layout_from_elements(state_view["name"], state_elements, state_relationships, "state")
        state_view["sysml_text"] = self._render_sysml_text(f"{project_name}_State", state_elements, state_relationships)
        return [activity_view, sequence_view, state_view]

    def _is_satellite_internet_overall(self, text: str) -> bool:
        source = str(text or "")
        has_constellation_signal = any(
            keyword in source
            for keyword in [
                "100颗",
                "一百颗",
                "低轨",
                "LEO",
                "星座",
                "卫星互联网",
                "宽带卫星互联网",
                "SatelliteInternet",
                "Constellation",
            ]
        )
        has_overall_signal = any(
            keyword in source
            for keyword in [
                "总体",
                "总体方案",
                "系统方案",
                "系统级",
                "空间段",
                "地面段",
                "用户段",
                "星间",
                "馈电",
                "由100颗卫星组成",
            ]
        )
        explicit_payload_only = (
            any(keyword in source for keyword in ["通信载荷分系统", "宽带通信载荷分系统", "载荷分系统"])
            and not any(keyword in source for keyword in ["100颗", "一百颗", "星座", "卫星互联网", "总体", "系统方案"])
        )
        return has_constellation_signal and has_overall_signal and not explicit_payload_only

    def _diagram_subject(self, brief: str, fallback: str | None) -> str:
        if self._is_satellite_internet_overall(f"{brief}\n{fallback or ''}"):
            return "100颗低轨宽带卫星互联网系统"
        text = re.sub(r"\s+", "", str(brief or ""))
        patterns = [
            r"(?:请|帮我|自动|可以|需要)*(?:生成|创建|构建|设计|输出)(?P<subject>.+?)(?:的)?(?:SysML|用例图|内部模块图|内部块图|IBD)",
            r"(?:为|针对)(?P<subject>.+?)(?:生成|创建|构建|设计)",
            r"(?P<subject>.+?)(?:的)?(?:SysML)?(?:用例图|内部模块图|内部块图|IBD)",
        ]
        candidate = ""
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                candidate = match.group("subject")
                break

        if not candidate:
            candidate = str(fallback or "").replace("_", " ")
        candidate = re.split(r"[，,。；;：:（(]", candidate)[0]
        candidate = re.sub(
            r"(请|自动|帮我|实现|生成|创建|构建|设计|输出|SysML|用例图|内部模块图|内部块图|IBD|图表|元素|多套|备选|方案|符合|语法)",
            "",
            candidate,
            flags=re.IGNORECASE,
        )
        candidate = candidate.strip(" 的和与-/\\_")
        if not candidate or candidate.lower() in {"ai mbse project", "ai-mbse-project", "project"}:
            return "目标分系统"
        return candidate[:28]

    def _diagram_domain_profile(self, subject: str, brief: str) -> dict[str, Any]:
        text = f"{subject} {brief}"
        profile: dict[str, Any] = {
            "external_actor": "外部任务系统",
            "operator_actor": "系统操作员",
            "platform_actor": "承载平台",
            "input_name": "任务输入与状态数据",
            "output_name": "业务输出与状态反馈",
            "core_capability": "核心业务处理",
            "functional_parts": [
                "输入接口",
                "输入预处理单元",
                "核心处理单元",
                "功能控制单元",
                "输出执行单元",
                "输出接口",
                "状态监测单元",
                "电源与环境接口",
            ],
            "smart_parts": [
                "多源数据接口",
                "数据适配单元",
                "智能决策单元",
                "任务编排单元",
                "资源调度单元",
                "服务输出接口",
                "模型/规则配置单元",
                "运行监控接口",
            ],
            "reliable_parts": [
                "主输入通道",
                "备输入通道",
                "重构切换单元",
                "主执行通道",
                "备执行通道",
                "健康管理单元",
                "冗余能源接口",
                "环境与遥测接口",
            ],
        }

        if self._is_satellite_internet_overall(text):
            profile.update(
                {
                    "external_actor": "宽带用户终端",
                    "operator_actor": "网络运营控制中心",
                    "platform_actor": "任务运控与星务中心",
                    "input_name": "用户业务、网管策略和星座运行状态",
                    "output_name": "宽带互联网服务、回传数据和星座运维状态",
                    "core_capability": "星座覆盖、星间路由、馈电回传和网络资源调度",
                    "functional_parts": ["用户终端段", "用户链路接入层", "100颗低轨通信星座", "星间链路与星上路由网络", "馈电网关站群", "地面核心网/互联网接口", "网络运营控制中心", "任务运控与星务支持中心"],
                    "smart_parts": ["业务接入接口", "业务分类与鉴权单元", "星座资源调度器", "星间路由控制器", "网关选择与回传控制器", "互联网服务接口", "网络策略配置单元", "星座运行监控接口"],
                    "reliable_parts": ["主用户接入路径", "备用户接入路径", "星间/星地切换控制单元", "主馈电回传路径", "备馈电回传路径", "星座健康管理单元", "冗余网关接口", "任务运控与安全接口"],
                    "baseline_actors": [
                        ("ACTOR-A-001", "宽带用户终端", "发起卫星互联网接入、业务会话和移动场景下的链路保持。"),
                        ("ACTOR-A-002", "地面网关/核心网", "承载馈电回传、核心网接入、互联网出口和网关侧状态反馈。"),
                        ("ACTOR-A-003", "网络运营控制中心", "配置业务策略、资源调度、QoS、网关选择和网络运行规则。"),
                        ("ACTOR-A-004", "任务运控与星务中心", "执行星座测控、轨道维护、健康管理和故障处置。"),
                    ],
                    "baseline_usecases": [
                        ("VUC-A-001", "提供用户宽带接入服务", "面向用户终端建立星地接入链路，提供互联网接入、鉴权和业务承载。"),
                        ("VUC-A-002", "保障100颗星座覆盖与容量", "基于100颗低轨卫星、轨道面和服务区域维持覆盖连续性与系统容量。"),
                        ("VUC-A-003", "执行星间路由与用户切换", "在卫星移动和用户移动条件下完成星间转发、路由更新和会话保持。"),
                        ("VUC-A-004", "完成馈电回传与核心网接入", "通过地面网关站群完成业务回传、核心网/互联网接入和网关选择。"),
                        ("VUC-A-005", "调度网络资源与服务质量", "按业务负载、优先级、波束、频率和网关可用性执行资源调度。"),
                        ("VUC-A-006", "监测星座健康并处置故障", "采集星座、单星、链路、网关和业务状态，执行告警、隔离、重构和恢复。"),
                    ],
                    "baseline_parts": [
                        ("VPART-A-001", "用户终端段", "Interface", "表示用户侧终端、业务接入和移动场景边界。"),
                        ("VPART-A-002", "用户链路接入层", "Block", "承担用户链路接入、鉴权、会话保持和业务承载。"),
                        ("VPART-A-003", "空间段：100颗低轨通信星座", "Block", "由100颗低轨通信卫星组成，承担覆盖、容量和星上转发。"),
                        ("VPART-A-004", "星间链路与星上路由网络", "Block", "支撑星间互联、空间路由、跨星切换和链路重构。"),
                        ("VPART-A-005", "馈电网关站群", "Block", "承担星地馈电链路、网关选择、业务回传和地面汇聚。"),
                        ("VPART-A-006", "地面核心网/互联网接口", "Interface", "连接核心网、外部互联网、业务平台和地面安全域。"),
                        ("VPART-A-007", "网络运营控制中心", "Block", "管理业务策略、资源调度、QoS、波束/频率和网关策略。"),
                        ("VPART-A-008", "任务运控与星务支持中心", "Interface", "提供测控、轨控、健康管理、任务规划和安全运维支撑。"),
                    ],
                    "baseline_connectors": [
                        ("VPART-A-001", "VPART-A-002", "用户业务接入与鉴权请求"),
                        ("VPART-A-002", "VPART-A-003", "用户星地链路与业务承载"),
                        ("VPART-A-003", "VPART-A-004", "星间路由、切换与空间转发"),
                        ("VPART-A-004", "VPART-A-005", "馈电链路与业务回传"),
                        ("VPART-A-005", "VPART-A-006", "核心网/互联网互联"),
                        ("VPART-A-007", "VPART-A-003", "星座资源调度与服务策略"),
                        ("VPART-A-007", "VPART-A-005", "网关选择、QoS和回传策略"),
                        ("VPART-A-008", "VPART-A-007", "测控遥测、任务计划和健康状态"),
                    ],
                    "baseline_trace_links": [
                        {"usecase_id": "VUC-A-001", "element_ids": ["VPART-A-001", "VPART-A-002", "VPART-A-003"], "relation": "realize", "description": "用户终端段、用户链路接入层和空间段共同实现宽带接入服务。"},
                        {"usecase_id": "VUC-A-002", "element_ids": ["VPART-A-003", "VPART-A-004", "VPART-A-007"], "relation": "realize", "description": "100颗低轨通信星座、星间链路和网络运营控制中心共同保障覆盖与容量。"},
                        {"usecase_id": "VUC-A-003", "element_ids": ["VPART-A-003", "VPART-A-004", "VPART-A-007"], "relation": "realize", "description": "空间段、星间路由网络和资源调度策略共同实现路由与切换。"},
                        {"usecase_id": "VUC-A-004", "element_ids": ["VPART-A-004", "VPART-A-005", "VPART-A-006"], "relation": "realize", "description": "星间路由、馈电网关站群和核心网接口共同完成馈电回传。"},
                        {"usecase_id": "VUC-A-005", "element_ids": ["VPART-A-007", "VPART-A-003", "VPART-A-005"], "relation": "allocate", "description": "网络运营控制中心将资源策略分配到星座空间段和网关站群。"},
                        {"usecase_id": "VUC-A-006", "element_ids": ["VPART-A-008", "VPART-A-007", "VPART-A-003"], "relation": "allocate", "description": "任务运控、网络运营和空间段共同支撑健康监测与故障处置。"},
                    ],
                }
            )
        elif any(keyword in text for keyword in ["通信", "载荷", "宽带", "链路", "波束", "网关", "频率"]):
            profile.update(
                {
                    "external_actor": "用户终端/业务终端",
                    "operator_actor": "网络或载荷运控中心",
                    "platform_actor": "卫星平台/承载平台",
                    "input_name": "上行业务信号",
                    "output_name": "下行/回传业务信号",
                    "core_capability": "通信接入、信道处理与链路转发",
                    "functional_parts": ["用户链路接口", "低噪声接收单元", "频率变换单元", "信道选择单元", "功率放大发射单元", "馈电链路接口", "载荷控制单元", "电源与热控接口"],
                    "smart_parts": ["多波束射频接口", "高速采样单元", "数字信道化处理器", "基带解调解码单元", "星上交换路由单元", "资源调度控制器", "调制编码输出单元", "馈电/核心网接口"],
                    "reliable_parts": ["主接收链路", "备接收链路", "射频/数字切换矩阵", "主发射链路", "备发射链路", "健康管理单元", "冗余电源接口", "热控与遥测接口"],
                    "baseline_actors": [
                        ("ACTOR-A-001", "用户终端", "发起宽带接入，发送用户上行业务并接收下行业务。"),
                        ("ACTOR-A-002", "馈电网关站", "承载馈电链路、回传链路和地面核心网接入。"),
                        ("ACTOR-A-003", "载荷运控中心", "下发载荷配置、波束/通道策略并接收健康状态。"),
                        ("ACTOR-A-004", "卫星平台/星务系统", "提供供电、热控、时频、遥测遥控和安全约束。"),
                    ],
                    "baseline_usecases": [
                        ("VUC-A-001", "接收用户上行信号", "通过用户链路接口完成上行射频接入、低噪声放大和输入保护。"),
                        ("VUC-A-002", "完成频率变换与信道选择", "对用户链路执行下变频、滤波、信道选择和通道映射。"),
                        ("VUC-A-003", "执行载荷转发处理", "通过透明转发或数字处理链路建立用户链路到馈电/下行链路的业务路径。"),
                        ("VUC-A-004", "输出下行/馈电业务信号", "完成上变频、功率放大、输出保护和馈电/下行接口交付。"),
                        ("VUC-A-005", "配置载荷工作模式", "接收运控中心的波束、通道、功率、保护和重构策略。"),
                        ("VUC-A-006", "上报遥测与健康状态", "采集功率、温度、电流、开关状态和关键链路告警并上报。"),
                    ],
                    "baseline_parts": [
                        ("VPART-A-001", "用户链路天线接口", "Interface", "定义用户上行/下行射频边界和端口。"),
                        ("VPART-A-002", "低噪声接收单元", "Block", "完成用户上行信号低噪声放大、保护和初级选择。"),
                        ("VPART-A-003", "频率变换与滤波单元", "Block", "完成下变频、滤波、增益控制和频谱整形。"),
                        ("VPART-A-004", "信道选择/交换矩阵", "Block", "建立用户链路、通道资源与馈电链路之间的连接关系。"),
                        ("VPART-A-005", "上变频与高功放单元", "Block", "完成上变频、功率放大、线性化和输出保护。"),
                        ("VPART-A-006", "馈电链路接口", "Interface", "连接馈电网关站，承载回传或下行业务接口。"),
                        ("VPART-A-007", "载荷控制与遥测单元", "Block", "管理载荷配置、遥测采集、告警和重构控制。"),
                        ("VPART-A-008", "电源与热控接口", "Interface", "与卫星平台电源、热控、时频和安全保护接口连接。"),
                    ],
                    "baseline_connectors": [
                        ("VPART-A-001", "VPART-A-002", "用户上行RF输入"),
                        ("VPART-A-002", "VPART-A-003", "低噪声放大后射频信号"),
                        ("VPART-A-003", "VPART-A-004", "变频/滤波后中频或数字通道"),
                        ("VPART-A-004", "VPART-A-005", "选通信道业务流"),
                        ("VPART-A-005", "VPART-A-006", "功放后下行/馈电信号"),
                        ("VPART-A-007", "VPART-A-003", "频率、增益和通道配置"),
                        ("VPART-A-007", "VPART-A-004", "通道选择、保护和重构控制"),
                        ("VPART-A-008", "VPART-A-007", "供电、热控、时频和遥测状态"),
                    ],
                    "baseline_trace_links": [
                        {"usecase_id": "VUC-A-001", "element_ids": ["VPART-A-001", "VPART-A-002"], "relation": "realize", "description": "用户链路接口和低噪声接收链路实现上行接收用例。"},
                        {"usecase_id": "VUC-A-002", "element_ids": ["VPART-A-002", "VPART-A-003", "VPART-A-004"], "relation": "realize", "description": "接收、变频滤波和信道选择部件共同实现频率变换与信道选择。"},
                        {"usecase_id": "VUC-A-003", "element_ids": ["VPART-A-003", "VPART-A-004", "VPART-A-005"], "relation": "realize", "description": "变频、交换矩阵和发射链路共同实现载荷转发处理。"},
                        {"usecase_id": "VUC-A-004", "element_ids": ["VPART-A-005", "VPART-A-006"], "relation": "realize", "description": "上变频高功放和馈电接口实现业务输出。"},
                        {"usecase_id": "VUC-A-005", "element_ids": ["VPART-A-007", "VPART-A-003", "VPART-A-004", "VPART-A-005"], "relation": "allocate", "description": "载荷控制单元将运控配置分配到变频、交换和发射链路。"},
                        {"usecase_id": "VUC-A-006", "element_ids": ["VPART-A-007", "VPART-A-008"], "relation": "allocate", "description": "遥测单元和平台接口支撑健康状态采集与上报。"},
                    ],
                }
            )
        elif any(keyword in text for keyword in ["雷达", "SAR", "成像", "探测", "回波"]):
            profile.update(
                {
                    "external_actor": "任务规划系统",
                    "operator_actor": "雷达载荷操作员",
                    "platform_actor": "平台姿轨控与时频系统",
                    "input_name": "任务指令、姿态和回波数据",
                    "output_name": "探测/成像产品",
                    "core_capability": "波束控制、回波采集与成像处理",
                    "functional_parts": ["天线阵面接口", "收发前端单元", "波束形成单元", "回波采集单元", "成像处理单元", "数据下传接口", "雷达控制单元", "时频与热控接口"],
                    "smart_parts": ["任务数据接口", "场景适配单元", "智能波束控制器", "成像任务编排器", "资源调度单元", "产品生成接口", "算法模型配置单元", "运行监控接口"],
                    "reliable_parts": ["主收发通道", "备收发通道", "通道切换矩阵", "主处理链路", "备处理链路", "健康管理单元", "冗余电源接口", "热控与时频接口"],
                }
            )
        elif any(keyword in text for keyword in ["电源", "供配电", "能源", "电池", "太阳阵"]):
            profile.update(
                {
                    "external_actor": "平台负载",
                    "operator_actor": "电源管理操作员",
                    "platform_actor": "太阳阵/电池组",
                    "input_name": "能源输入与负载需求",
                    "output_name": "受控供配电输出",
                    "core_capability": "能量调节、配电控制与故障保护",
                    "functional_parts": ["能源输入接口", "功率调节单元", "电池充放电管理单元", "配电控制单元", "保护开关单元", "负载输出接口", "电源控制单元", "遥测与热控接口"],
                    "smart_parts": ["能源状态接口", "负载预测单元", "智能能量管理器", "任务供电编排器", "配电资源调度单元", "供电服务接口", "策略配置单元", "运行监控接口"],
                    "reliable_parts": ["主供电通道", "备供电通道", "配电切换单元", "主保护链路", "备保护链路", "故障诊断单元", "冗余能源接口", "遥测与热控接口"],
                }
            )
        elif any(keyword in text for keyword in ["热控", "温度", "散热", "热平衡"]):
            profile.update(
                {
                    "external_actor": "受控设备",
                    "operator_actor": "热控操作员",
                    "platform_actor": "平台热环境",
                    "input_name": "温度遥测与热流状态",
                    "output_name": "热控执行与温度稳定结果",
                    "core_capability": "温度采集、热控决策与执行调节",
                    "functional_parts": ["温度采集接口", "热状态预处理单元", "热控算法单元", "加热器控制单元", "散热执行单元", "热控输出接口", "热控管理单元", "电源与遥测接口"],
                    "smart_parts": ["热状态数据接口", "热模型适配单元", "智能热控决策器", "热控任务编排器", "热资源调度单元", "执行输出接口", "模型参数配置单元", "运行监控接口"],
                    "reliable_parts": ["主测温通道", "备测温通道", "热控切换单元", "主执行通道", "备执行通道", "健康管理单元", "冗余电源接口", "遥测与安全接口"],
                }
            )
        elif any(keyword in text for keyword in ["飞控", "控制律", "姿态", "轨道", "导航", "舵机"]):
            profile.update(
                {
                    "external_actor": "导航与任务系统",
                    "operator_actor": "飞控操作员",
                    "platform_actor": "传感器与执行机构",
                    "input_name": "导航状态与控制指令",
                    "output_name": "姿态/轨迹控制输出",
                    "core_capability": "状态估计、控制律计算与执行控制",
                    "functional_parts": ["导航状态接口", "状态估计单元", "控制律计算单元", "执行分配单元", "执行机构驱动单元", "控制输出接口", "飞控管理单元", "电源与遥测接口"],
                    "smart_parts": ["导航数据接口", "状态融合单元", "智能控制决策器", "飞控任务编排器", "执行资源调度单元", "控制服务接口", "控制律配置单元", "运行监控接口"],
                    "reliable_parts": ["主导航通道", "备导航通道", "控制切换单元", "主执行通道", "备执行通道", "健康管理单元", "冗余电源接口", "安全遥测接口"],
                }
            )
        elif any(keyword in text for keyword in ["推进", "发动机", "燃料", "贮箱", "阀门"]):
            profile.update(
                {
                    "external_actor": "任务控制系统",
                    "operator_actor": "推进操作员",
                    "platform_actor": "推进剂与能源平台",
                    "input_name": "推进指令与压力状态",
                    "output_name": "推力执行与状态反馈",
                    "core_capability": "推进剂管理、阀控执行与安全保护",
                    "functional_parts": ["推进指令接口", "压力温度采集单元", "阀门控制单元", "推进剂管理单元", "推力执行单元", "状态输出接口", "推进控制单元", "电源与安全接口"],
                    "smart_parts": ["状态数据接口", "工况适配单元", "智能推进决策器", "推进任务编排器", "资源调度单元", "推力服务接口", "策略配置单元", "运行监控接口"],
                    "reliable_parts": ["主供给通道", "备供给通道", "阀组切换单元", "主执行链路", "备执行链路", "健康管理单元", "冗余电源接口", "安全遥测接口"],
                }
            )

        return profile

    def _subsystem_diagram_views(self, project_name: str, subject: str, brief: str) -> list[dict[str, Any]]:
        profile = self._diagram_domain_profile(subject, brief)

        def build_parts(prefix: str, names: list[str], descriptions: list[str]) -> list[tuple[str, str, str, str]]:
            result: list[tuple[str, str, str, str]] = []
            for index, name in enumerate(names, start=1):
                element_type = "Interface" if index in {1, 6, 8} else "Block"
                result.append((f"VPART-{prefix}-{index:03d}", name, element_type, descriptions[index - 1]))
            return result

        def build_connectors(prefix: str, labels: list[str]) -> list[tuple[str, str, str]]:
            ids = [f"VPART-{prefix}-{index:03d}" for index in range(1, 9)]
            pairs = [(0, 1), (1, 2), (2, 3), (3, 4), (4, 5), (6, 2), (6, 4), (7, 6)]
            return [(ids[source], ids[target], labels[index]) for index, (source, target) in enumerate(pairs)]

        baseline_parts = profile.get("baseline_parts") or build_parts(
            "A",
            profile["functional_parts"],
            [
                f"接入{profile['input_name']}并定义外部边界。",
                "完成输入整形、转换、过滤或初步校核。",
                f"承担{profile['core_capability']}的主要处理职责。",
                "执行模式控制、参数装订和任务状态协调。",
                f"将核心处理结果转换为{profile['output_name']}。",
                "对外提供输出、服务或数据交付接口。",
                "采集状态并支撑告警、保护和运行评估。",
                "连接电源、热控、遥测或平台环境资源。",
            ],
        )
        baseline_connectors = profile.get("baseline_connectors") or build_connectors(
            "A",
            ["输入接口连接", "预处理数据连接", "核心处理连接", "控制/执行连接", "输出接口连接", "控制与配置连接", "保护与状态控制连接", "供电、热控与遥测连接"],
        )

        variants = [
            {
                "id": "ALT-A",
                "name": f"基线方案：功能链路型{subject}",
                "description": f"以{subject}的输入、处理、控制、输出链路为主线，适合快速形成可审查的工程基线。",
                "rationale": "优先保证边界、接口和功能流清晰，便于设计师、管理员和MagicDraw模型之间快速对齐。",
                "actors": profile.get("baseline_actors") or [
                    ("ACTOR-A-001", profile["external_actor"], f"向{subject}提供任务输入、业务请求或外部环境交互。"),
                    ("ACTOR-A-002", profile["operator_actor"], f"配置{subject}任务参数、运行模式和处理策略。"),
                    ("ACTOR-A-003", profile["platform_actor"], f"提供{subject}运行所需的平台资源、约束和状态反馈。"),
                ],
                "usecases": profile.get("baseline_usecases") or [
                    ("VUC-A-001", f"接收{profile['input_name']}", f"完成{subject}外部输入接入、合法性检查和状态确认。"),
                    ("VUC-A-002", f"执行{profile['core_capability']}", f"依据任务目标完成{subject}核心功能处理。"),
                    ("VUC-A-003", f"输出{profile['output_name']}", f"将处理结果、执行指令或服务输出交付到外部接口。"),
                    ("VUC-A-004", f"监测{subject}运行状态", f"采集关键遥测、健康状态、告警和性能指标。"),
                ],
                "parts": baseline_parts,
                "connectors": baseline_connectors,
                "trace_links": profile.get("baseline_trace_links") or [],
            },
            {
                "id": "ALT-B",
                "name": f"方案B：智能控制型{subject}",
                "description": f"强调{subject}的任务编排、智能决策和资源调度能力，适合面向复杂任务或多模式运行的方案。",
                "rationale": "在功能链路基础上增加策略配置、动态调度和闭环监控，便于后续扩展自动化控制与仿真验证。",
                "actors": [
                    ("ACTOR-B-001", profile["external_actor"], f"提供{subject}任务请求、业务数据或环境输入。"),
                    ("ACTOR-B-002", profile["operator_actor"], "设置策略、优先级、阈值和运行规则。"),
                    ("ACTOR-B-003", profile["platform_actor"], "提供资源约束、平台状态和安全边界。"),
                ],
                "usecases": [
                    ("VUC-B-001", "解析任务与业务约束", f"识别{subject}任务目标、输入条件、资源约束和优先级。"),
                    ("VUC-B-002", "执行智能决策与任务编排", "根据策略和状态生成处理步骤、模式切换和资源分配计划。"),
                    ("VUC-B-003", "动态分配运行资源", "根据负载、故障和优先级调整关键资源。"),
                    ("VUC-B-004", "闭环输出服务与状态", "输出服务结果并回收执行状态，用于下一轮控制决策。"),
                ],
                "parts": build_parts(
                    "B",
                    profile["smart_parts"],
                    [
                        "接入多源任务、状态或业务数据。",
                        "统一数据格式、坐标、时标或语义表达。",
                        "依据规则、模型或算法形成控制决策。",
                        "组织任务步骤、模式转换和执行顺序。",
                        "分配能力、带宽、功率、时间或执行资源。",
                        "对外交付服务结果、控制输出或数据产品。",
                        "管理模型参数、规则库和策略配置。",
                        "持续监控运行状态并形成闭环反馈。",
                    ],
                ),
                "connectors": build_connectors(
                    "B",
                    ["多源数据接入", "数据适配连接", "任务状态输入", "编排控制连接", "资源分配连接", "策略配置连接", "执行策略连接", "运行监控反馈"],
                ),
            },
            {
                "id": "ALT-C",
                "name": f"方案C：高可靠冗余型{subject}",
                "description": f"突出{subject}的故障检测、隔离、主备切换和降级运行能力，适合高可靠或长寿命任务。",
                "rationale": "优先保证异常情况下的功能连续性、可恢复性和审核可追溯性。",
                "actors": [
                    ("ACTOR-C-001", profile["external_actor"], f"在正常或降级模式下继续与{subject}交互。"),
                    ("ACTOR-C-002", profile["operator_actor"], "执行故障确认、隔离、切换和恢复策略。"),
                    ("ACTOR-C-003", profile["platform_actor"], "提供冗余资源、安全保护和平台状态支撑。"),
                ],
                "usecases": [
                    ("VUC-C-001", f"检测{subject}关键故障", "持续监测链路、模块、资源和环境异常。"),
                    ("VUC-C-002", "执行主备切换与隔离", "在故障确认后切换冗余通道并隔离故障部件。"),
                    ("VUC-C-003", "进入降级运行模式", "在资源受限或局部故障下保持关键功能。"),
                    ("VUC-C-004", "上报健康状态与恢复结果", "向操作员或平台回传告警、处置和恢复信息。"),
                ],
                "parts": build_parts(
                    "C",
                    profile["reliable_parts"],
                    [
                        "承担正常情况下的主输入或主服务路径。",
                        "在主路径异常时提供备份输入或备份服务。",
                        "执行通道重构、隔离和主备切换。",
                        "承担正常情况下的主执行或主输出路径。",
                        "在主执行路径异常时接管关键功能。",
                        "完成故障检测、隔离、恢复和降级策略管理。",
                        "提供冗余供电、保护或能源支撑。",
                        "提供环境监测、安全遥测和平台状态交互。",
                    ],
                ),
                "connectors": build_connectors(
                    "C",
                    ["主输入连接", "备份输入连接", "重构控制连接", "主执行连接", "备份输出连接", "健康诊断连接", "保护控制连接", "安全遥测连接"],
                ),
            },
        ]

        views: list[dict[str, Any]] = []
        for variant in variants[:1]:
            if not variant.get("trace_links"):
                variant["trace_links"] = self._diagram_trace_links(variant)
            views.append(self._payload_use_case_view(project_name, variant))
            views.append(self._payload_ibd_view(project_name, variant))
        return views

    def _broadband_payload_diagram_views(self, project_name: str) -> list[dict[str, Any]]:
        variants = [
            {
                "id": "ALT-A",
                "name": "方案A：透明转发型宽带通信载荷",
                "description": "以射频透明转发为主，链路短、实现成熟，适合快速形成工程基线。",
                "rationale": "优先保证射频链路连续性、功放效率和频率转换链路清晰，数字处理深度较低。",
                "actors": [
                    ("ACTOR-A-001", "用户终端", "发起宽带接入、业务数据收发和链路保持。"),
                    ("ACTOR-A-002", "馈电网关站", "提供馈电上行、回传下行和网关侧监控。"),
                    ("ACTOR-A-003", "载荷运控中心", "下发载荷配置、监测状态并执行故障处置。"),
                ],
                "usecases": [
                    ("VUC-A-001", "接收用户上行信号", "完成用户波束接入、低噪声接收和频谱选择。"),
                    ("VUC-A-002", "频率变换与通道选择", "对用户链路执行下变频、滤波、通道选择和频率规划。"),
                    ("VUC-A-003", "功率放大并下行转发", "将处理后的信号经上变频和高功放输出到下行链路。"),
                    ("VUC-A-004", "监测载荷健康状态", "采集功率、温度、开关状态和关键遥测。"),
                ],
                "parts": [
                    ("VPART-A-001", "用户波束天线接口", "Interface", "接入用户上/下行射频信号。"),
                    ("VPART-A-002", "低噪声放大器", "Block", "对用户上行信号进行低噪声放大。"),
                    ("VPART-A-003", "下变频与信道选择单元", "Block", "完成下变频、滤波和通道选择。"),
                    ("VPART-A-004", "透明转发交换矩阵", "Block", "建立用户链路到馈电链路的透明连接。"),
                    ("VPART-A-005", "上变频与高功放", "Block", "完成上变频、功率放大和输出保护。"),
                    ("VPART-A-006", "馈电链路接口", "Interface", "连接网关馈电链路与回传链路。"),
                    ("VPART-A-007", "载荷控制与遥测单元", "Block", "管理载荷配置、遥测采集和保护控制。"),
                    ("VPART-A-008", "电源与热控接口", "Interface", "与平台电源、热控和健康管理接口连接。"),
                ],
            },
            {
                "id": "ALT-B",
                "name": "方案B：数字处理再生型宽带通信载荷",
                "description": "以星上数字处理和再生转发为核心，支持业务路由、带宽调度和灵活波束资源分配。",
                "rationale": "增强星上处理能力，适合高吞吐、动态资源调度和业务隔离要求更高的任务。",
                "actors": [
                    ("ACTOR-B-001", "用户终端", "接入宽带业务并维持会话。"),
                    ("ACTOR-B-002", "网络运营控制中心", "配置带宽、波束、QoS和业务策略。"),
                    ("ACTOR-B-003", "馈电网关站", "承载回传、核心网接入和网络管理南向接口。"),
                ],
                "usecases": [
                    ("VUC-B-001", "解调并解码用户业务", "完成ADC采样、解调、解码和业务帧恢复。"),
                    ("VUC-B-002", "执行星上路由交换", "根据业务策略进行星上交换、排队和转发。"),
                    ("VUC-B-003", "动态分配带宽与波束", "根据业务负载调整波束、载波和时频资源。"),
                    ("VUC-B-004", "编码调制并下行发送", "对业务流重新编码、调制、成形并输出。"),
                ],
                "parts": [
                    ("VPART-B-001", "多波束射频前端", "Interface", "接入多波束用户链路和馈电链路。"),
                    ("VPART-B-002", "高速ADC/DAC单元", "Block", "完成宽带模拟/数字转换。"),
                    ("VPART-B-003", "数字信道化处理器", "Block", "进行信道化、滤波、抽取和重采样。"),
                    ("VPART-B-004", "基带解调解码单元", "Block", "恢复业务帧并执行纠错解码。"),
                    ("VPART-B-005", "星上交换与路由单元", "Block", "处理业务路由、队列和优先级调度。"),
                    ("VPART-B-006", "资源调度控制器", "Block", "管理带宽、波束、载波和QoS策略。"),
                    ("VPART-B-007", "调制编码与成形单元", "Block", "执行下行业务编码、调制和成形。"),
                    ("VPART-B-008", "馈电/核心网接口", "Interface", "连接馈电网关和核心网络。"),
                ],
            },
            {
                "id": "ALT-C",
                "name": "方案C：高可靠冗余型宽带通信载荷",
                "description": "以主备链路、开关矩阵和健康管理为重点，强调故障检测、隔离、重构和降级服务。",
                "rationale": "面向高可用任务和长寿命在轨运行，优先保证故障后的业务连续性和可维护性。",
                "actors": [
                    ("ACTOR-C-001", "用户终端", "在正常和降级模式下保持基本宽带接入。"),
                    ("ACTOR-C-002", "载荷运控中心", "执行故障诊断、隔离、切换和重构策略。"),
                    ("ACTOR-C-003", "卫星平台管理单元", "提供电源、热控、遥测和安全保护。"),
                ],
                "usecases": [
                    ("VUC-C-001", "检测载荷链路故障", "持续监测关键链路、电源、温度和功率指标。"),
                    ("VUC-C-002", "执行主备切换", "在故障确认后切换接收、处理或发射链路。"),
                    ("VUC-C-003", "进入降级通信服务", "在局部故障下维持关键业务和低速服务。"),
                    ("VUC-C-004", "上报健康状态与重构结果", "向运控中心回传告警、处置和恢复结果。"),
                ],
                "parts": [
                    ("VPART-C-001", "主接收链路", "Block", "承担正常用户上行接收。"),
                    ("VPART-C-002", "备接收链路", "Block", "主接收链路故障时接管。"),
                    ("VPART-C-003", "射频开关矩阵", "Block", "实现主备链路和波束通道重构。"),
                    ("VPART-C-004", "主发射链路", "Block", "承担正常下行发射。"),
                    ("VPART-C-005", "备发射链路", "Block", "主发射链路故障时接管。"),
                    ("VPART-C-006", "健康管理单元", "Block", "完成故障检测、隔离和恢复策略。"),
                    ("VPART-C-007", "冗余电源接口", "Interface", "提供主备供电和保护状态。"),
                    ("VPART-C-008", "热控与遥测接口", "Interface", "提供热控状态、温度和关键遥测。"),
                ],
            },
        ]

        views: list[dict[str, Any]] = []
        for variant in variants:
            views.append(self._payload_use_case_view(project_name, variant))
            views.append(self._payload_ibd_view(project_name, variant))
        return views

    def _payload_use_case_view(self, project_name: str, variant: dict[str, Any]) -> dict[str, Any]:
        elements = [
            self._diagram_element(actor_id, name, "Actor", description, "00_Actors")
            for actor_id, name, description in variant["actors"]
        ] + [
            self._diagram_element(usecase_id, name, "UseCase", description, "03_Behavior")
            for usecase_id, name, description in variant["usecases"]
        ]
        relationships: list[dict[str, Any]] = []
        rel_index = 1
        actor_ids = [item[0] for item in variant["actors"]]
        usecase_ids = [item[0] for item in variant["usecases"]]
        for usecase_id in usecase_ids:
            source = actor_ids[(rel_index - 1) % len(actor_ids)]
            relationships.append(self._diagram_relationship(f"{variant['id']}-UC", rel_index, source, usecase_id, "association", "参与该用例"))
            rel_index += 1
        for left, right in zip(usecase_ids, usecase_ids[1:]):
            relationships.append(self._diagram_relationship(f"{variant['id']}-UC", rel_index, left, right, "include", "用例间存在前后依赖"))
            rel_index += 1
        canvas_height = max(560, 170 + len(usecase_ids) * 96)
        layout = self._diagram_layout(
            f"{variant['id']}_UseCase",
            [
                *[
                    {
                        "id": actor_id,
                        "element_id": actor_id,
                        "name": name,
                        "label": name,
                        "type": "Actor",
                        "stereotype_label": "actor",
                        "shape": "actor",
                        "x": 70 if index < 2 else 780,
                        "y": 120 + (index % 2) * 170,
                        "width": 150,
                        "height": 96,
                    }
                    for index, (actor_id, name, _description) in enumerate(variant["actors"])
                ],
                *[
                    {
                        "id": usecase_id,
                        "element_id": usecase_id,
                        "name": name,
                        "label": name,
                        "type": "UseCase",
                        "stereotype_label": "use case",
                        "shape": "ellipse",
                        "x": 360,
                        "y": 82 + index * 104,
                        "width": 250,
                        "height": 70,
                    }
                    for index, (usecase_id, name, _description) in enumerate(variant["usecases"])
                ],
            ],
            relationships,
            1010,
            canvas_height,
        )
        layout["diagram_type"] = "use_case"
        return {
            "id": f"{variant['id']}-USECASE",
            "variant_id": variant["id"],
            "variant_name": variant["name"],
            "diagram_type": "use_case",
            "name": f"{variant['name']} - 用例图",
            "description": variant["description"],
            "rationale": variant["rationale"],
            "elements": elements,
            "relationships": relationships,
            "layout": layout,
            "sysml_text": self._render_sysml_text(f"{project_name}_{variant['id']}_UseCase", elements, relationships),
            "trace_links": variant.get("trace_links") or [],
        }

    def _payload_ibd_view(self, project_name: str, variant: dict[str, Any]) -> dict[str, Any]:
        elements = [
            self._diagram_element(part_id, name, element_type, description, "02_Structure" if element_type == "Block" else "04_Interfaces")
            for part_id, name, element_type, description in variant["parts"]
        ]
        part_ids = [item[0] for item in variant["parts"]]
        connector_specs = variant.get("connectors") or [
            (part_ids[0], part_ids[1], "输入接口连接"),
            (part_ids[1], part_ids[2], "预处理数据连接"),
            (part_ids[2], part_ids[3], "核心处理连接"),
            (part_ids[3], part_ids[4], "控制/执行连接"),
            (part_ids[4], part_ids[5], "输出接口连接"),
            (part_ids[6], part_ids[2], "控制与配置连接"),
            (part_ids[6], part_ids[4], "保护与状态控制连接"),
            (part_ids[7], part_ids[6], "供电、热控与遥测连接"),
        ]
        relationships = [
            self._diagram_relationship(f"{variant['id']}-IBD", index, source, target, "connector", description)
            for index, (source, target, description) in enumerate(connector_specs, start=1)
        ]
        coords = [
            (70, 120),
            (300, 120),
            (530, 120),
            (760, 120),
            (990, 120),
            (1220, 120),
            (530, 325),
            (300, 325),
        ]
        layout = self._diagram_layout(
            f"{variant['id']}_IBD",
            [
                {
                    "id": part_id,
                    "element_id": part_id,
                    "name": name,
                    "label": name,
                    "type": element_type,
                    "stereotype_label": "part" if element_type == "Block" else "interface",
                    "shape": "soft" if element_type == "Interface" else "rect",
                    "x": coords[index][0],
                    "y": coords[index][1],
                    "width": 185,
                    "height": 72,
                }
                for index, (part_id, name, element_type, _description) in enumerate(variant["parts"])
            ],
            relationships,
            1450,
            560,
        )
        layout["diagram_type"] = "ibd"
        return {
            "id": f"{variant['id']}-IBD",
            "variant_id": variant["id"],
            "variant_name": variant["name"],
            "diagram_type": "ibd",
            "name": f"{variant['name']} - 内部模块图（IBD）",
            "description": variant["description"],
            "rationale": variant["rationale"],
            "elements": elements,
            "relationships": relationships,
            "layout": layout,
            "sysml_text": self._render_sysml_text(f"{project_name}_{variant['id']}_IBD", elements, relationships),
            "trace_links": variant.get("trace_links") or [],
        }

    def _diagram_trace_links(self, variant: dict[str, Any]) -> list[dict[str, Any]]:
        usecases = [item[0] for item in variant.get("usecases") or []]
        parts = [item[0] for item in variant.get("parts") or []]
        if not usecases or not parts:
            return []
        buckets = [
            parts[0:2],
            parts[1:4],
            parts[3:6],
            [parts[6], parts[7]] if len(parts) >= 8 else parts[-2:],
        ]
        links: list[dict[str, Any]] = []
        for index, usecase_id in enumerate(usecases):
            element_ids = buckets[index] if index < len(buckets) else parts[max(0, len(parts) - 2) :]
            links.append(
                {
                    "usecase_id": usecase_id,
                    "element_ids": element_ids,
                    "relation": "realize" if index < 3 else "allocate",
                    "description": "该用例由内部模块图中的相关部件和接口共同实现。",
                }
            )
        return links

    def _diagram_element(
        self,
        element_id: str,
        name: str,
        element_type: str,
        description: str,
        package: str,
    ) -> dict[str, Any]:
        return {
            "id": element_id,
            "name": name,
            "type": element_type,
            "description": description,
            "package": package,
            "source_requirement": None,
            "status": "candidate",
        }

    def _diagram_relationship(
        self,
        variant_id: str,
        index: int,
        source: str,
        target: str,
        rel_type: str,
        description: str,
    ) -> dict[str, Any]:
        return {
            "id": f"DREL-{re.sub(r'[^A-Za-z0-9]+', '-', variant_id).strip('-')}-{index:03d}",
            "source": source,
            "target": target,
            "type": rel_type,
            "description": description,
        }

    def _diagram_layout(
        self,
        diagram_name: str,
        nodes: list[dict[str, Any]],
        relationships: list[dict[str, Any]],
        width: int,
        height: int,
    ) -> dict[str, Any]:
        node_map = {item["id"]: item for item in nodes}
        edges: list[dict[str, Any]] = []
        for relationship in relationships:
            source = node_map.get(str(relationship.get("source") or ""))
            target = node_map.get(str(relationship.get("target") or ""))
            if not source or not target:
                continue
            points = self._diagram_edge_points(source, target)
            edges.append(
                {
                    "id": relationship["id"],
                    "relationship_id": relationship["id"],
                    "source": relationship["source"],
                    "target": relationship["target"],
                    "type": relationship.get("type") or "connector",
                    "label": relationship.get("type") or "connector",
                    "points": points,
                    "label_x": (points[0]["x"] + points[-1]["x"]) / 2,
                    "label_y": (points[0]["y"] + points[-1]["y"]) / 2 - 8,
                }
            )
        return {
            "schema": "ai-mbse.diagram-view-layout.v1",
            "diagram_name": diagram_name,
            "layout_source": "backend",
            "width": width,
            "height": height,
            "nodes": nodes,
            "edges": edges,
        }

    def _diagram_edge_points(self, source: dict[str, Any], target: dict[str, Any]) -> list[dict[str, float]]:
        source_x = float(source.get("x") or 0)
        source_y = float(source.get("y") or 0)
        source_w = float(source.get("width") or 180)
        source_h = float(source.get("height") or 72)
        target_x = float(target.get("x") or 0)
        target_y = float(target.get("y") or 0)
        target_w = float(target.get("width") or 180)
        target_h = float(target.get("height") or 72)
        if source_x <= target_x:
            start = {"x": source_x + source_w, "y": source_y + source_h / 2}
            end = {"x": target_x, "y": target_y + target_h / 2}
        else:
            start = {"x": source_x, "y": source_y + source_h / 2}
            end = {"x": target_x + target_w, "y": target_y + target_h / 2}
        mid_x = (start["x"] + end["x"]) / 2
        return [
            start,
            {"x": mid_x, "y": start["y"]},
            {"x": mid_x, "y": end["y"]},
            end,
        ]

    def _layout_stereotype(self, element_type: str) -> str:
        return {
            "Actor": "actor",
            "Activity": "activity",
            "Block": "part",
            "Requirement": "requirement",
            "UseCase": "use case",
            "Interface": "interface",
            "ConstraintBlock": "constraint",
        }.get(element_type, "element")

    def _element(
        self,
        element_id: str,
        name: str,
        element_type: str,
        description: str,
        status: str = "candidate",
        package: str | None = None,
    ) -> dict[str, Any]:
        source_requirement = element_id if element_type == "Requirement" else None
        element_package = package or self._default_element_package(element_type)
        return {
            "id": element_id,
            "name": name,
            "type": element_type,
            "description": description,
            "package": element_package,
            "source_requirement": source_requirement,
            "status": status,
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

    def _render_sysml_text(
        self,
        project_name: str,
        elements: list[dict[str, Any]],
        relationships: list[dict[str, Any]],
    ) -> str:
        names = {item["id"]: f"{self._sysml_identifier(item['type'])}_{self._sysml_identifier(item['id'])}" for item in elements}
        lines = [f"package {self._sysml_identifier(project_name)} {{"]
        grouped: dict[str, list[dict[str, Any]]] = {}
        for item in elements:
            grouped.setdefault(str(item.get("package") or self._default_element_package(str(item.get("type") or ""))), []).append(item)

        for package_name in sorted(grouped):
            lines.append(f"  package {self._sysml_identifier(package_name)} {{")
            for item in grouped[package_name]:
                keyword = self._sysml_keyword(str(item.get("type") or "Element"))
                local_name = names[item["id"]]
                lines.append(f"    {keyword} {local_name} {{ // {item['id']}")
                lines.append(f"      doc \"{self._escape_sysml(item.get('description') or item.get('name') or item['id'])}\";")
                if item.get("source_requirement"):
                    lines.append(f"      attribute sourceRequirement = \"{self._escape_sysml(item['source_requirement'])}\";")
                lines.append(f"      attribute lifecycleStatus = \"{self._escape_sysml(item.get('status') or 'candidate')}\";")
                for attribute in item.get("attributes") or []:
                    attr_name = self._sysml_identifier(str(attribute.get("name") or "attribute"))
                    value_type = self._sysml_identifier(str(attribute.get("value_type") or "UntypedValue"))
                    value = self._escape_sysml(attribute.get("value") or "")
                    unit = self._escape_sysml(attribute.get("unit") or "")
                    lines.append(f"      attribute {attr_name} : {value_type} = \"{value}\";")
                    if unit:
                        lines.append(f"      attribute {attr_name}Unit = \"{unit}\";")
                lines.append("    }")
            lines.append("  }")

        lines.append("  package 06_Traceability {")
        for rel in relationships:
            source = names.get(rel["source"], self._sysml_identifier(rel["source"]))
            target = names.get(rel["target"], self._sysml_identifier(rel["target"]))
            lines.append(
                f"    dependency {self._sysml_identifier(rel['id'])} from {source} to {target} "
                f"{{ // {rel['id']}: {rel['source']} -> {rel['target']}"
            )
            lines.append(f"      attribute relationType = \"{self._escape_sysml(rel.get('type') or 'trace')}\";")
            if rel.get("description"):
                lines.append(f"      doc \"{self._escape_sysml(rel['description'])}\";")
            lines.append("    }")
        lines.append("  }")
        lines.append("}")
        return "\n".join(lines)

    def render_project_text(
        self,
        project_name: str,
        elements: list[dict[str, Any]],
        relationships: list[dict[str, Any]],
    ) -> str:
        return self._render_sysml_text(self._safe_name(project_name), elements, relationships)

    def _sysml_keyword(self, element_type: str) -> str:
        return {
            "Actor": "part def",
            "Requirement": "requirement def",
            "Block": "part def",
            "UseCase": "use case",
            "Interface": "interface def",
            "Activity": "action def",
            "ConstraintBlock": "constraint def",
        }.get(element_type, "item def")

    def _sysml_identifier(self, value: str) -> str:
        normalized = re.sub(r"[^0-9A-Za-z_\u4e00-\u9fff]+", "_", str(value or "Element").strip()).strip("_")
        safe = normalized or "Element"
        return f"E_{safe}" if safe[0].isdigit() else safe

    def _escape_sysml(self, value: Any) -> str:
        return str(value or "").replace("\\", "\\\\").replace('"', '\\"')

    def _safe_name(self, name: str) -> str:
        cleaned = re.sub(r"[^0-9A-Za-z_\u4e00-\u9fff]+", "_", str(name or "").strip()).strip("_")
        return cleaned or "AI_MBSE_Project"
