from __future__ import annotations

import json
import re
import time
from collections.abc import Iterator
from typing import Any

import httpx

from app.config import get_settings


class LLMService:
    def __init__(self) -> None:
        self.settings = get_settings()

    def health_check(self) -> dict:
        if not self._can_use_real_api():
            return {"mode": "mock", "available": True}
        try:
            headers = {"Authorization": f"Bearer {self.settings.llm_api_key}"}
            url = f"{self.settings.llm_api_base_url.rstrip('/')}/models"
            response = httpx.get(url, headers=headers, timeout=3)
            response.raise_for_status()
            return {"mode": "real", "available": True}
        except Exception:
            return {"mode": "mock", "available": True}

    def chat(self, messages: list[dict], task_type: str = "chat") -> dict:
        if self._can_use_real_api():
            try:
                headers = {"Authorization": f"Bearer {self.settings.llm_api_key}"}
                payload = {
                    "model": self._model_name(),
                    "messages": messages,
                    "temperature": 0.2,
                }
                url = f"{self.settings.llm_api_base_url.rstrip('/')}/chat/completions"
                timeout = 120 if task_type == "model_generation" else 30
                response = httpx.post(url, headers=headers, json=payload, timeout=timeout)
                response.raise_for_status()
                data = response.json()
                answer = data["choices"][0]["message"]["content"]
                return {"mode": "real", "answer": answer}
            except Exception:
                pass

        latest = messages[-1]["content"] if messages else ""
        answer = self._mock_chat_answer(latest, task_type)
        return {"mode": "mock", "answer": answer}

    def stream_chat(self, messages: list[dict], task_type: str = "chat") -> Iterator[str]:
        if self._can_use_real_api():
            try:
                headers = {"Authorization": f"Bearer {self.settings.llm_api_key}"}
                payload = {
                    "model": self._model_name(),
                    "messages": messages,
                    "temperature": 0.2,
                    "stream": True,
                }
                url = f"{self.settings.llm_api_base_url.rstrip('/')}/chat/completions"
                emitted = ""
                with httpx.stream("POST", url, headers=headers, json=payload, timeout=60) as response:
                    response.raise_for_status()
                    for line in response.iter_lines():
                        chunk = self._stream_delta_from_line(line)
                        if chunk:
                            chunk = self._merge_stream_chunk(emitted, chunk)
                        if chunk:
                            emitted += chunk
                            yield chunk
                return
            except Exception:
                pass

        latest = messages[-1]["content"] if messages else ""
        answer = self._mock_chat_answer(latest, task_type)
        for chunk in self._chunk_text(answer):
            yield chunk
            time.sleep(0.025)

    def analyze_requirements(self, text: str, scenario: str) -> list[dict]:
        if self._can_use_real_api():
            prompt = (
                "请从以下需求文本中提取结构化需求，返回 JSON 数组。字段："
                "id,name,description,type,priority,source,score,suggestion,status。"
                f"\n场景：{scenario}\n需求文本：{text}"
            )
            result = self.chat([{"role": "user", "content": prompt}], task_type="requirement_analysis")
            parsed = self._try_parse_json_array(result.get("answer", ""))
            if parsed:
                normalized = self._normalize_requirements(parsed)
                if normalized:
                    return normalized

        return self._mock_requirements()

    def generate_sysml_model(self, requirements: list[dict]) -> dict:
        from app.services.model_generation_service import ModelGenerationService

        return ModelGenerationService().generate(requirements)

    def analyze_impact(self, element: dict, graph: dict, change_description: str) -> dict:
        name = element.get("name", element.get("id", "该元素"))
        return {
            "summary": f"{name} 的变更将沿追溯关系影响相关用例、模块和接口。",
            "suggestions": [
                "建议补充变更后的量化指标。",
                "建议检查相关接口和模块的容量约束。",
            ],
        }

    def validate_model(self, graph: dict) -> dict:
        return {
            "conclusion": "模型基本可评审，建议继续补充关键接口参数和性能约束。",
        }

    def _can_use_real_api(self) -> bool:
        return (
            self.settings.llm_enable_real_api
            and bool(self.settings.llm_api_base_url)
            and bool(self.settings.llm_api_key)
        )

    def _model_name(self) -> str:
        return (self.settings.llm_model_name or "deepseek-chat").strip().strip('"').strip("'")

    def _stream_delta_from_line(self, line: str) -> str:
        text = line.strip()
        if not text:
            return ""
        if text.startswith("data:"):
            text = text[5:].strip()
        if not text or text == "[DONE]":
            return ""
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return ""
        choices = data.get("choices") or []
        if not choices:
            return ""
        first = choices[0] or {}
        delta = first.get("delta") or {}
        if isinstance(delta, dict) and delta.get("content"):
            return str(delta["content"])
        message = first.get("message") or {}
        if isinstance(message, dict) and message.get("content"):
            return str(message["content"])
        return ""

    def _chunk_text(self, text: str, size: int = 8) -> Iterator[str]:
        for index in range(0, len(text), size):
            yield text[index : index + size]

    def _merge_stream_chunk(self, emitted: str, incoming: str) -> str:
        if not incoming:
            return ""
        if not emitted:
            return incoming
        if incoming == emitted:
            return ""
        if incoming.startswith(emitted):
            return incoming[len(emitted) :]
        if len(incoming) > 12 and emitted.endswith(incoming):
            return ""
        return incoming

    def _try_parse_json_array(self, raw: str) -> list[dict] | None:
        try:
            start = raw.find("[")
            end = raw.rfind("]")
            if start >= 0 and end > start:
                data = json.loads(raw[start : end + 1])
                if isinstance(data, list):
                    return data
        except Exception:
            return None
        return None

    def _normalize_requirements(self, items: list[dict]) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for index, item in enumerate(items, start=1):
            if not isinstance(item, dict):
                continue

            raw_id = str(item.get("id") or item.get("编号") or item.get("需求编号") or "").strip()
            req_id = raw_id if raw_id.upper().startswith("REQ-") else f"REQ-{index:03d}"
            name = str(item.get("name") or item.get("需求名称") or item.get("title") or f"结构化需求 {index}").strip()
            description = str(
                item.get("description") or item.get("需求描述") or item.get("text") or item.get("内容") or name
            ).strip()
            req_type = str(item.get("type") or item.get("需求类型") or "功能需求").strip()
            priority = str(item.get("priority") or item.get("优先级") or "中").strip()
            score = self._normalize_score(item.get("score") or item.get("规范性评分"))
            suggestion = str(item.get("suggestion") or item.get("AI 建议") or "建议补充量化指标和验收条件。").strip()

            normalized.append(
                {
                    "id": req_id,
                    "name": name or f"结构化需求 {index}",
                    "description": description or name or f"结构化需求 {index}",
                    "type": req_type or "功能需求",
                    "priority": priority if priority in {"高", "中", "低"} else "中",
                    "source": str(item.get("source") or item.get("来源") or "用户输入").strip() or "用户输入",
                    "score": score,
                    "suggestion": suggestion or "建议补充量化指标和验收条件。",
                    "status": self._normalize_status(item.get("status") or item.get("状态")),
                }
            )
        return normalized

    def _normalize_score(self, value: Any) -> int:
        try:
            score = int(float(value))
        except (TypeError, ValueError):
            score = 85
        return max(0, min(100, score))

    def _normalize_status(self, value: Any) -> str:
        raw = str(value or "").strip().lower()
        if raw in {"confirmed", "已确认"}:
            return "confirmed"
        if raw in {"rejected", "已拒绝"}:
            return "rejected"
        return "pending"

    def _mock_chat_answer(self, message: str, task_type: str) -> str:
        latest = self._latest_user_text(message)
        if task_type == "requirement_analysis":
            return "已完成需求结构化分析，生成 5 条候选需求，可进入人在回路确认。"
        if task_type == "model_generation":
            return "已根据确认需求生成候选 SysML 元素，包括 Requirement、UseCase、Block、Interface 和 Activity。"
        if task_type == "impact_analysis":
            return "已基于本地追溯图完成影响传播分析，输出直接影响、间接影响和风险等级。"
        if task_type == "validation":
            return "已完成模型预评审，当前模型基本可评审，建议补充接口约束和追溯关系说明。"
        if task_type == "simulation":
            return "仿真工具未安装，当前返回 Mock 仿真结果，用于展示接口预留能力。"
        if task_type == "knowledge_qa":
            return self._mock_knowledge_answer(message)
        if self._is_identity_question(latest):
            return f"我是当前 AI-MBSE 系统接入的 {self._model_name()} 大模型。"
        if self._is_greeting(latest):
            return "在的。我会先作为 MBSE 助理帮你理解和澄清需求；只有你明确要求或点击“生成”后，才会进入 SysML 建模和 MagicDraw 推送。你可以先描述系统目标、边界、接口，或提出某个变更影响问题。"
        if self._is_impact_question(latest):
            return (
                "收到，这是变更影响分析问题。我会先沿 MBSE 追溯链检查：受影响需求、功能链路、结构模块、接口、行为流程、约束、验证项和 MagicDraw 交付物。"
                "建议你补充：变更对象、变更内容、期望生效范围和必须保持不变的约束。"
            )
        return (
            f"已收到：{latest}。我会先帮助你做需求理解与澄清，而不是直接建模。"
            "我们可以按总体目标、系统边界、参与方、功能链路、接口、行为流程、约束和验收标准逐步确认；确认充分后再点击“生成”形成 SysML 工程。"
        )

    def _mock_knowledge_answer(self, message: str) -> str:
        question_match = re.search(r"用户问题：(.+?)(?:\n\n|$)", message, re.S)
        question = (question_match.group(1).strip() if question_match else self._latest_user_text(message)) or "当前问题"
        context_match = re.search(r"知识库上下文：(.+?)\n\n用户问题：", message, re.S)
        context = context_match.group(1).strip() if context_match else ""
        source_lines = [
            re.sub(r"\s+", " ", line).strip()
            for line in context.splitlines()
            if line.strip() and re.match(r"^\d+\.", line.strip())
        ][:4]

        if "宽带" in question and "载荷" in question and ("需求" in question or "接口" in question):
            basis = "；".join(source_lines) if source_lines else "内置领域知识和当前模型图谱"
            return (
                "基于知识库检索，低轨通信卫星的宽带载荷分系统可优先关注以下内容：\n\n"
                "关键需求：\n"
                "1. 高吞吐量与多业务承载能力，明确总容量、单波束容量和业务优先级。\n"
                "2. 多波束覆盖与波束调度能力，约束覆盖范围、重访/切换策略和资源分配规则。\n"
                "3. 频率、带宽、EIRP、G/T、链路裕量和可用度等射频与链路性能指标。\n"
                "4. 星上处理、载荷功耗、热控、可靠性、在轨可重构和故障降级能力。\n\n"
                "典型接口：\n"
                "1. 与天线分系统的射频、波束指向和校准接口。\n"
                "2. 与星上处理/数管单元的高速数据、时钟同步和控制接口。\n"
                "3. 与供配电分系统的电源、保护和功耗遥测接口。\n"
                "4. 与热控分系统的热耗、安装面和温度监测接口。\n"
                "5. 与测控和地面网关的遥测遥控、业务链路和状态上报接口。\n\n"
                f"主要依据：{basis}。建议下一步把这些需求转成 Requirement，并把接口建成 Interface/Block 间的可追溯关系。"
            )

        if source_lines:
            bullets = "\n".join(f"- {line}" for line in source_lines)
            return (
                f"基于知识库检索，针对“{question}”可以先参考以下依据：\n\n"
                f"{bullets}\n\n"
                "建议把上述依据进一步拆成需求、接口、约束和验证项；如果要进入建模，请再点击“生成”。"
            )

        return (
            f"针对“{question}”，当前知识库未检索到足够明确的依据。"
            "建议先上传需求文档、接口控制文档或历史设计报告，再使用知识库问答。"
        )

    def _latest_user_text(self, message: str) -> str:
        text = str(message or "").strip()
        marker = "用户输入："
        if marker in text:
            tail = text.split(marker, 1)[1].strip()
            for next_marker in ["\n\n附件上下文：", "\n附件上下文："]:
                if next_marker in tail:
                    tail = tail.split(next_marker, 1)[0].strip()
            return tail or text
        return text

    def _is_greeting(self, text: str) -> bool:
        normalized = re.sub(r"[\s，。！？!?.,;；：:]+", "", text.strip().lower())
        return normalized in {"在吗", "你在吗", "你好", "您好", "hi", "hello", "hey", "哈喽", "收到", "好的", "ok"}

    def _is_impact_question(self, text: str) -> bool:
        return bool(re.search(r"(变更|修改|调整|变化|影响|波及|追溯|依赖|风险|冲突)", text))

    def _is_identity_question(self, text: str) -> bool:
        normalized = re.sub(r"[\s，。！？!?,.;；：:]+", "", str(text or "").strip().lower())
        if normalized in {
            "你是谁",
            "你叫什么",
            "你是什么",
            "你是啥",
            "你是什么模型",
            "你是哪个模型",
            "你是什么大模型",
            "你用的什么模型",
            "你用的是哪个模型",
            "你用的是什么大模型",
        }:
            return True
        return bool(
            re.search(
                r"(你|当前|现在|目前|系统|平台|后端|接入|调用|使用|用的|用的是).*(什么|哪个|哪一个).*(模型|大模型|llm|deepseek|gpt|版本)",
                normalized,
                re.IGNORECASE,
            )
            or re.search(
                r"(你|当前|现在|目前|系统|平台|后端|接入|调用|使用|用的|用的是).*(模型|大模型|llm|deepseek|gpt).*(什么|哪个|哪一个|版本)",
                normalized,
                re.IGNORECASE,
            )
            or re.search(r"你.*(是谁|叫什么|什么身份|什么助手|什么系统)", normalized, re.IGNORECASE)
        )

    def _mock_requirements(self) -> list[dict[str, Any]]:
        return [
            {
                "id": "REQ-001",
                "name": "用户接入能力",
                "description": "系统应支持宽带用户终端接入认证、接入状态管理和在线状态监测。",
                "type": "功能需求",
                "priority": "高",
                "source": "用户输入",
                "score": 88,
                "suggestion": "建议补充最大并发接入数量和认证时延指标。",
                "status": "pending",
            },
            {
                "id": "REQ-002",
                "name": "链路资源管理能力",
                "description": "系统应支持链路资源分配、链路质量监测和资源状态维护。",
                "type": "功能需求",
                "priority": "高",
                "source": "用户输入",
                "score": 86,
                "suggestion": "建议明确链路质量阈值和资源回收策略。",
                "status": "pending",
            },
            {
                "id": "REQ-003",
                "name": "业务调度能力",
                "description": "系统应根据业务优先级进行资源调度，并保障关键业务传输质量。",
                "type": "性能需求",
                "priority": "高",
                "source": "用户输入",
                "score": 90,
                "suggestion": "建议补充关键业务等级和调度响应时间。",
                "status": "pending",
            },
            {
                "id": "REQ-004",
                "name": "网络状态监测能力",
                "description": "系统应对用户接入状态、链路质量和网络运行状态进行实时监测。",
                "type": "功能需求",
                "priority": "中",
                "source": "用户输入",
                "score": 84,
                "suggestion": "建议明确监测周期和状态同步接口。",
                "status": "pending",
            },
            {
                "id": "REQ-005",
                "name": "故障告警能力",
                "description": "系统应在链路质量下降或关键服务异常时触发告警并支持运维追溯。",
                "type": "可靠性需求",
                "priority": "中",
                "source": "用户输入",
                "score": 87,
                "suggestion": "建议补充告警等级、升级规则和恢复确认机制。",
                "status": "pending",
            },
        ]
