from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

from sqlalchemy.orm import Session

from app.models import ChatLog
from app.services.impact_service import ImpactService
from app.services.llm_service import LLMService
from app.services.model_generation_service import ModelGenerationService
from app.services.rag_service import RAGService
from app.services.requirement_service import RequirementService
from app.services.simulation_service import SimulationService
from app.services.validation_service import ValidationService


class AgentService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.llm = LLMService()
        self.rag = RAGService(db)

    def run(
        self,
        session_id: str,
        message: str,
        task_type: str,
        conversation: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        if task_type == "direct_chat":
            result = self.run_direct_chat(message, conversation)
            self._log(session_id, message, result)
            return result
        if task_type == "knowledge_qa":
            result = self.run_knowledge_qa(message, conversation)
            self._log(session_id, message, result)
            return result

        handlers = {
            "requirement_analysis": self.run_requirement_analysis,
            "model_generation": self.run_model_generation,
            "impact_analysis": self.run_impact_analysis,
            "validation": self.run_validation,
            "simulation": self.run_simulation,
        }
        handler = handlers.get(task_type)
        result = handler(message) if handler else self.run_chat(message, conversation)
        self._log(session_id, message, result)
        return result

    def stream(
        self,
        session_id: str,
        message: str,
        task_type: str,
        conversation: list[dict[str, Any]] | None = None,
    ) -> Iterator[str]:
        if task_type == "direct_chat":
            yield from self._stream_direct_chat(session_id, message, conversation)
            return
        if task_type == "knowledge_qa":
            yield from self._stream_knowledge_chat(session_id, message, conversation)
            return
        if task_type != "chat":
            result = self.run(session_id, message, task_type, conversation)
            yield from self._stream_text_result(result)
            return

        latest_user_text = self._latest_user_text(message)
        if self.rag.classify_intent(latest_user_text) == "knowledge_qa":
            yield from self._stream_knowledge_chat(session_id, message, conversation, auto_selected=True)
            return

        yield from self._stream_direct_chat(session_id, message, conversation, auto_selected=True)

    def run_chat(self, message: str, conversation: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        latest_user_text = self._latest_user_text(message)
        if self.rag.classify_intent(latest_user_text) == "knowledge_qa":
            result = self.run_knowledge_qa(message, conversation)
            result["tool_calls"].insert(0, {"tool": "mode_classifier", "status": "success", "summary": "自动识别为知识库问答"})
            return result
        result = self.run_direct_chat(message, conversation)
        result["tool_calls"].insert(0, {"tool": "mode_classifier", "status": "success", "summary": "自动识别为直接问答"})
        return result

    def run_direct_chat(self, message: str, conversation: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        answer = self.llm.chat(self._chat_messages(message, conversation), "chat")["answer"]
        return {
            "answer": answer,
            "tool_calls": [{"tool": "llm_chat", "status": "success", "summary": "直接调用大模型生成问答回复"}],
            "artifacts": {"mode": "direct_chat"},
        }

    def run_knowledge_qa(self, message: str, conversation: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        latest_user_text = self._latest_user_text(message)
        retrieval = self.rag.retrieve(latest_user_text)
        answer = self.llm.chat(self._knowledge_messages(message, conversation, retrieval), "knowledge_qa")["answer"]
        knowledge = retrieval.get("knowledge", [])
        document_count = len(retrieval.get("documents") or [])
        graph_count = len(retrieval.get("graph") or [])
        return {
            "answer": answer,
            "tool_calls": [
                {
                    "tool": "knowledge_retrieval",
                    "status": "success",
                    "summary": f"检索到 {len(knowledge)} 条知识依据（文档 {document_count} 条，模型图谱 {graph_count} 条）",
                },
                {"tool": "llm_knowledge_answer", "status": "success", "summary": "基于知识库上下文生成回答"},
            ],
            "artifacts": retrieval,
        }

    def run_requirement_analysis(self, message: str) -> dict[str, Any]:
        knowledge = self.rag.search(message)
        requirements = RequirementService(self.db).analyze_and_store(message, "宽带通信")
        return {
            "answer": f"已完成需求分析，生成 {len(requirements)} 条结构化需求。",
            "tool_calls": [
                {"tool": "rag_search", "status": "success", "summary": f"检索到 {len(knowledge)} 条相关设计知识"},
                {"tool": "requirement_analysis_skill", "status": "success", "summary": "生成结构化需求并写入待确认列表"},
            ],
            "artifacts": {"requirements": requirements},
        }

    def run_model_generation(self, message: str) -> dict[str, Any]:
        requirements = [
            {
                "id": item.id,
                "name": item.name,
                "description": item.description,
                "type": item.type,
                "priority": item.priority,
                "source": item.source,
                "score": item.score,
                "suggestion": item.suggestion,
                "status": item.status,
            }
            for item in RequirementService(self.db).list_requirements()
            if item.status == "confirmed"
        ]
        model = ModelGenerationService().generate(requirements)
        return {
            "answer": f"已生成 {len(model['elements'])} 个候选 SysML 元素和 {len(model['relationships'])} 条关系。",
            "tool_calls": [
                {"tool": "model_generation_skill", "status": "success", "summary": "根据已确认需求生成候选模型"},
                {"tool": "sysml_candidate_builder", "status": "success", "summary": "生成追溯关系图"},
            ],
            "artifacts": model,
        }

    def run_impact_analysis(self, message: str) -> dict[str, Any]:
        result = ImpactService(self.db).analyze("REQ-001", message, 3)
        return {
            "answer": result["summary"],
            "tool_calls": [
                {"tool": "graph_bfs", "status": "success", "summary": "基于本地模型关系图执行 BFS 影响传播"},
            ],
            "artifacts": result,
        }

    def run_validation(self, message: str) -> dict[str, Any]:
        report = ValidationService(self.db).run()
        return {
            "answer": report["conclusion"],
            "tool_calls": [
                {"tool": "validation_rules", "status": "success", "summary": "完成模型预评审规则检查"},
            ],
            "artifacts": report,
        }

    def run_simulation(self, message: str) -> dict[str, Any]:
        result = SimulationService().run("BLK-001")
        return {
            "answer": result["message"],
            "tool_calls": [
                {"tool": "simulation_adapter", "status": "success", "summary": "调用仿真适配器并返回结果"},
            ],
            "artifacts": result,
        }

    def _stream_direct_chat(
        self,
        session_id: str,
        message: str,
        conversation: list[dict[str, Any]] | None = None,
        auto_selected: bool = False,
    ) -> Iterator[str]:
        answer_parts: list[str] = []
        tool_calls: list[dict[str, Any]] = []
        if auto_selected:
            tool_calls.append({"tool": "mode_classifier", "status": "success", "summary": "自动识别为直接问答"})

        for delta in self.llm.stream_chat(self._chat_messages(message, conversation), "chat"):
            answer_parts.append(delta)
            yield self._stream_event({"type": "delta", "content": delta})

        tool_calls.append({"tool": "llm_chat", "status": "success", "summary": "直接调用大模型生成问答回复"})
        result = {"answer": "".join(answer_parts), "tool_calls": tool_calls, "artifacts": {"mode": "direct_chat"}}
        self._log(session_id, message, result)
        yield self._stream_event(
            {
                "type": "done",
                "answer": result["answer"],
                "tool_calls": tool_calls,
                "artifacts": result["artifacts"],
            }
        )

    def _stream_knowledge_chat(
        self,
        session_id: str,
        message: str,
        conversation: list[dict[str, Any]] | None = None,
        auto_selected: bool = False,
    ) -> Iterator[str]:
        latest_user_text = self._latest_user_text(message)
        retrieval = self.rag.retrieve(latest_user_text)
        answer_parts: list[str] = []
        tool_calls: list[dict[str, Any]] = []
        if auto_selected:
            tool_calls.append({"tool": "mode_classifier", "status": "success", "summary": "自动识别为知识库问答"})

        knowledge = retrieval.get("knowledge", [])
        document_count = len(retrieval.get("documents") or [])
        graph_count = len(retrieval.get("graph") or [])
        tool_calls.append(
            {
                "tool": "knowledge_retrieval",
                "status": "success",
                "summary": f"检索到 {len(knowledge)} 条知识依据（文档 {document_count} 条，模型图谱 {graph_count} 条）",
            }
        )

        for delta in self.llm.stream_chat(self._knowledge_messages(message, conversation, retrieval), "knowledge_qa"):
            answer_parts.append(delta)
            yield self._stream_event({"type": "delta", "content": delta})

        tool_calls.append({"tool": "llm_knowledge_answer", "status": "success", "summary": "基于知识库上下文生成回答"})
        result = {"answer": "".join(answer_parts), "tool_calls": tool_calls, "artifacts": retrieval}
        self._log(session_id, message, result)
        yield self._stream_event(
            {
                "type": "done",
                "answer": result["answer"],
                "tool_calls": tool_calls,
                "artifacts": retrieval,
            }
        )

    def _log(self, session_id: str, message: str, result: dict[str, Any]) -> None:
        self.db.add(
            ChatLog(
                session_id=session_id,
                message=message,
                answer=str(result.get("answer") or ""),
                tool_calls_json=json.dumps(result.get("tool_calls", []), ensure_ascii=False),
            )
        )
        self.db.commit()

    def _stream_text_result(self, result: dict[str, Any]) -> Iterator[str]:
        answer = str(result.get("answer") or "")
        for index in range(0, len(answer), 8):
            yield self._stream_event({"type": "delta", "content": answer[index : index + 8]})
        yield self._stream_event(
            {
                "type": "done",
                "answer": answer,
                "tool_calls": result.get("tool_calls", []),
                "artifacts": result.get("artifacts", {}),
            }
        )

    def _chat_messages(self, message: str, conversation: list[dict[str, Any]] | None = None) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = [{"role": "system", "content": self._chat_system_prompt()}]
        for item in conversation or []:
            role = str(item.get("role") or "").strip().lower()
            content = str(item.get("content") or "").strip()
            if role not in {"user", "assistant"} or not content:
                continue
            messages.append({"role": role, "content": content})

        current = message.strip()
        if current and (not messages or messages[-1]["role"] != "user" or messages[-1]["content"] != current):
            messages.append({"role": "user", "content": current})

        return [messages[0], *messages[-11:]] if len(messages) > 1 else [messages[0], {"role": "user", "content": current}]

    def _knowledge_messages(
        self,
        message: str,
        conversation: list[dict[str, Any]] | None,
        retrieval: dict[str, Any],
    ) -> list[dict[str, str]]:
        latest = self._latest_user_text(message)
        context = self.rag.format_context(retrieval)
        messages: list[dict[str, str]] = [
            {
                "role": "system",
                "content": (
                    "你是AI赋能MBSE系统设计平台中的知识库问答助手。"
                    "必须优先依据给定知识库上下文回答；上下文不足时明确说明缺口，不要编造成熟数据。"
                    "回答应区分关键需求、接口关系、依据来源和待确认项；不得声称已经生成或推送SysML工程。"
                ),
            }
        ]
        for item in (conversation or [])[-6:]:
            role = str(item.get("role") or "").strip().lower()
            content = str(item.get("content") or "").strip()
            if role in {"user", "assistant"} and content:
                messages.append({"role": role, "content": content})

        messages.append(
            {
                "role": "user",
                "content": (
                    f"知识库上下文：\n{context}\n\n"
                    f"用户问题：{latest}\n\n"
                    "请基于上述上下文回答，并在末尾用一句话说明主要依据来自文档、模型图谱还是内置领域知识。"
                ),
            }
        )
        return messages

    def _chat_system_prompt(self) -> str:
        model_name = self.llm._model_name()
        return (
            "你是AI赋能MBSE系统设计平台中的MBSE助理。工作流必须遵循："
            "1. 普通对话和寒暄只自然回应，不自动展开建模。"
            "2. 对新需求，先帮助用户理解和澄清总体需求、系统边界、功能链路、接口、行为流程、约束、验收与假设。"
            "3. 信息不足时提出少量关键问题；信息较充分时提示用户可点击“生成”进入SysML工程生成。"
            "4. 只有用户明确要求生成/修改工程，或前端调用SysML生成接口时，才视为进入建模阶段；普通chat不得声称已经生成SysML、MagicDraw工程或已经推送。"
            "5. 对变更类问题，分析变更对需求、功能、结构、接口、行为、约束、验证、追溯关系和MagicDraw交付物的影响路径、风险和建议动作。"
            "6. 如果用户消息包含“用户输入：”字段，以该字段后的内容作为最新真实意图；其他字段只是上下文和回答约束。"
            f"7. 当前后端配置的直接问答大模型为“{model_name}”。当用户询问你是什么模型、当前接入什么模型或平台使用什么大模型时，"
            f"只回答“我是当前系统接入的 {model_name} 大模型。”，不要展开MBSE助理职责、不要解释建模能力、不要追问用户。"
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

    def _stream_event(self, payload: dict[str, Any]) -> str:
        return json.dumps(payload, ensure_ascii=False) + "\n"
