from __future__ import annotations

import json
import re
from typing import Any

from sqlalchemy.orm import Session

from app.models import Document, KnowledgeChunk, Requirement, SysMLElement, SysMLRelationship


class RAGService:
    """SQLite-backed knowledge retrieval for the demo.

    The implementation is deliberately dependency-light: uploaded documents are
    chunked into a local table, while SysML tables provide a small graph index.
    The public methods are shaped so Chroma/Neo4j can replace the internals later.
    """

    def __init__(self, db: Session | None = None) -> None:
        self.db = db

    def classify_intent(self, query: str) -> str:
        text = self._latest_user_text(query)
        normalized = re.sub(r"[\s，。！？!?,.;；：:]+", "", text.strip().lower())
        if normalized in {"在吗", "你在吗", "你好", "您好", "hi", "hello", "hey", "哈喽", "收到", "好的", "ok"}:
            return "direct_chat"
        if self._looks_like_identity_question(text):
            return "direct_chat"
        if self._looks_like_knowledge_question(text):
            return "knowledge_qa"
        return "direct_chat"

    def should_search(self, query: str) -> bool:
        return self.classify_intent(query) == "knowledge_qa"

    def index_document(self, document: Document) -> int:
        if not self.db:
            return 0

        self.db.query(KnowledgeChunk).filter(KnowledgeChunk.document_id == document.id).delete()
        chunks = self._split_chunks(document.content)
        for index, chunk in enumerate(chunks):
            keywords = sorted(self._query_terms(f"{document.filename}\n{chunk}"))[:40]
            self.db.add(
                KnowledgeChunk(
                    document_id=document.id,
                    title=document.filename,
                    content=chunk,
                    chunk_index=index,
                    keywords_json=json.dumps(keywords, ensure_ascii=False),
                )
            )
        self.db.commit()
        return len(chunks)

    def knowledge_summary(self) -> dict[str, Any]:
        if not self.db:
            return {"document_count": 0, "chunk_count": 0, "latest_documents": []}
        self.ensure_indexed_documents()
        latest = self.db.query(Document).order_by(Document.id.desc()).limit(5).all()
        return {
            "document_count": self.db.query(Document).count(),
            "chunk_count": self.db.query(KnowledgeChunk).count(),
            "latest_documents": latest,
        }

    def ensure_indexed_documents(self) -> int:
        if not self.db:
            return 0
        indexed_ids = {
            row[0]
            for row in self.db.query(KnowledgeChunk.document_id).distinct().all()
            if row[0] is not None
        }
        missing = self.db.query(Document).filter(~Document.id.in_(indexed_ids)).all()
        total = 0
        for document in missing:
            total += self.index_document(document)
        return total

    def retrieve(self, query: str, limit: int = 8) -> dict[str, Any]:
        text = self._latest_user_text(query)
        document_hits = self._search_document_chunks(text, limit=limit)
        graph_hits = self._search_graph(text, limit=limit)
        seed_hits = self._search_seed_knowledge(text, limit=4)
        combined = self._dedupe_hits([*document_hits, *graph_hits, *seed_hits])
        combined.sort(key=lambda item: float(item.get("score") or 0), reverse=True)
        knowledge = combined[:limit]
        return {
            "mode": "knowledge_qa",
            "query": text,
            "knowledge": knowledge,
            "documents": document_hits[:limit],
            "graph": graph_hits[:limit],
            "seed": seed_hits[:limit],
            "summary": f"检索到 {len(knowledge)} 条知识依据",
        }

    def search(self, query: str) -> list[dict[str, Any]]:
        return self.retrieve(query).get("knowledge", [])

    def format_context(self, retrieval: dict[str, Any], limit: int = 8) -> str:
        items = retrieval.get("knowledge") or []
        if not items:
            return "未检索到明确知识库依据。"
        lines = []
        for index, item in enumerate(items[:limit], start=1):
            source = item.get("source") or item.get("source_type") or "知识库"
            title = item.get("title") or "未命名知识"
            summary = item.get("summary") or item.get("content") or ""
            lines.append(f"{index}. [{source}] {title}\n{summary}")
        return "\n\n".join(lines)

    def _looks_like_knowledge_question(self, text: str) -> bool:
        has_engineering_scope = bool(
            re.search(
                r"(MBSE|SysML|MagicDraw|Cameo|需求|接口|约束|指标|模型|架构|链路|载荷|分系统|卫星|星座|通信|宽带|雷达|地面站|仿真|验证|追溯)",
                text,
                re.IGNORECASE,
            )
        )
        asks_knowledge = bool(
            re.search(r"(哪些|有什么|是什么|如何|怎么|说明|介绍|解释|列出|关键|依据|接口|需求|关系|约束|指标)", text, re.IGNORECASE)
        )
        generate_or_execute = bool(re.search(r"(生成|创建|建立|构建|推送|同步|运行|导出|保存)", text, re.IGNORECASE))
        return has_engineering_scope and asks_knowledge and not generate_or_execute

    def _looks_like_identity_question(self, text: str) -> bool:
        normalized = re.sub(r"[\s，。！？!?,.;；：:]+", "", text.strip().lower())
        direct_identity_phrases = {
            "你是谁",
            "你叫什么",
            "你叫啥",
            "你是什么",
            "你是啥",
            "你是什么模型",
            "你是哪个模型",
            "你是哪一个模型",
            "你是什么大模型",
            "你用的什么模型",
            "你用的是哪个模型",
            "你用的是什么大模型",
        }
        if normalized in direct_identity_phrases:
            return True

        asks_model_identity = bool(
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
        )
        asks_assistant_identity = bool(re.search(r"你.*(是谁|叫什么|什么身份|什么助手|什么系统)", normalized, re.IGNORECASE))
        return asks_model_identity or asks_assistant_identity

    def _search_document_chunks(self, query: str, limit: int) -> list[dict[str, Any]]:
        if not self.db:
            return []
        terms = self._query_terms(query)
        hits: list[dict[str, Any]] = []
        for chunk in self.db.query(KnowledgeChunk).order_by(KnowledgeChunk.id.desc()).limit(500).all():
            score = self._score_text(query, terms, f"{chunk.title}\n{chunk.content}\n{chunk.keywords_json}")
            if score <= 0:
                continue
            hits.append(
                {
                    "title": chunk.title,
                    "summary": self._summarize(chunk.content),
                    "source": f"文档片段 #{chunk.document_id}-{chunk.chunk_index + 1}",
                    "source_type": "document",
                    "document_id": chunk.document_id,
                    "chunk_id": chunk.id,
                    "score": round(score, 3),
                }
            )
        hits.sort(key=lambda item: float(item["score"]), reverse=True)
        return hits[:limit]

    def _search_graph(self, query: str, limit: int) -> list[dict[str, Any]]:
        if not self.db:
            return []

        terms = self._query_terms(query)
        hits: list[dict[str, Any]] = []
        element_scores: dict[str, float] = {}
        element_names: dict[str, str] = {}

        for requirement in self.db.query(Requirement).limit(500).all():
            text = f"{requirement.id} {requirement.name} {requirement.description} {requirement.type} {requirement.priority}"
            score = self._score_text(query, terms, text)
            if score > 0:
                hits.append(
                    {
                        "title": f"需求：{requirement.name}",
                        "summary": f"{requirement.id} | {requirement.type} | {requirement.description}",
                        "source": "需求库",
                        "source_type": "graph",
                        "element_id": requirement.id,
                        "score": round(score + 0.4, 3),
                    }
                )

        for element in self.db.query(SysMLElement).limit(800).all():
            text = f"{element.id} {element.name} {element.type} {element.description} {element.source_requirement or ''}"
            score = self._score_text(query, terms, text)
            element_names[element.id] = element.name
            if score > 0:
                element_scores[element.id] = score
                hits.append(
                    {
                        "title": f"模型元素：{element.name}",
                        "summary": f"{element.id} | {element.type} | {element.description}",
                        "source": "模型图谱",
                        "source_type": "graph",
                        "element_id": element.id,
                        "score": round(score + 0.6, 3),
                    }
                )

        for relationship in self.db.query(SysMLRelationship).limit(1200).all():
            source_name = element_names.get(relationship.source, relationship.source)
            target_name = element_names.get(relationship.target, relationship.target)
            text = (
                f"{relationship.id} {relationship.type} {relationship.description} "
                f"{relationship.source} {source_name} {relationship.target} {target_name}"
            )
            score = self._score_text(query, terms, text)
            if relationship.source in element_scores or relationship.target in element_scores:
                score = max(score, 0.75 + 0.2 * max(element_scores.get(relationship.source, 0), element_scores.get(relationship.target, 0)))
            if score <= 0:
                continue
            hits.append(
                {
                    "title": f"模型关系：{source_name} -> {target_name}",
                    "summary": f"{relationship.type} | {relationship.description or '模型元素之间存在追溯或结构关系。'}",
                    "source": "模型图谱",
                    "source_type": "graph",
                    "relationship_id": relationship.id,
                    "score": round(score, 3),
                }
            )

        hits.sort(key=lambda item: float(item["score"]), reverse=True)
        return hits[:limit]

    def _search_seed_knowledge(self, query: str, limit: int) -> list[dict[str, Any]]:
        terms = self._query_terms(query)
        hits = []
        for item in self._seed_knowledge():
            text = f"{item['title']} {item['summary']} {' '.join(item['keywords'])}"
            score = self._score_text(query, terms, text)
            if score > 0:
                hits.append(
                    {
                        "title": item["title"],
                        "summary": item["summary"],
                        "source": "内置领域知识",
                        "source_type": "seed",
                        "score": round(score, 3),
                    }
                )
        hits.sort(key=lambda item: float(item["score"]), reverse=True)
        return hits[:limit]

    def _seed_knowledge(self) -> list[dict[str, Any]]:
        return [
            {
                "title": "低轨通信卫星宽带载荷关键需求",
                "summary": "宽带载荷通常关注高吞吐量、多波束覆盖、频率/带宽规划、EIRP/G/T、链路可用度、星上处理能力、载荷功耗、热控约束、可靠性和在轨可重构能力。",
                "keywords": {"低轨", "通信卫星", "宽带", "载荷", "需求", "多波束", "吞吐量", "功耗", "热控", "链路"},
            },
            {
                "title": "宽带载荷典型接口",
                "summary": "宽带载荷常见接口包括与天线分系统的射频/波束接口、与星上处理单元的高速数据接口、与供配电分系统的功率接口、与热控分系统的散热接口、与测控/数管分系统的遥测遥控接口，以及与地面网关的业务链路接口。",
                "keywords": {"接口", "天线", "星上处理", "电源", "热控", "测控", "数管", "地面网关", "宽带载荷"},
            },
            {
                "title": "MBSE 追溯建模经验",
                "summary": "Requirement、UseCase、Block、Interface 与 ConstraintBlock 之间应建立 satisfy、trace、allocate、verify 等关系，用于支撑需求到结构、行为、接口和验证证据的追溯。",
                "keywords": {"mbse", "sysml", "需求", "模型", "建模", "requirement", "usecase", "block", "interface", "trace"},
            },
            {
                "title": "MagicDraw/Cameo 推送契约",
                "summary": "候选 SysML 元素推送到 MagicDraw/Cameo 前，应保留本地 ID、类型、包路径、追溯关系和导入响应，方便回查和增量同步。",
                "keywords": {"magicdraw", "cameo", "sysml", "推送", "导入", "追溯", "同步"},
            },
        ]

    def _split_chunks(self, content: str, max_chars: int = 520, overlap: int = 80) -> list[str]:
        text = re.sub(r"[ \t\r\f\v]+", " ", str(content or "")).strip()
        if not text:
            return ["该文档未解析出可检索文本。"]
        chunks: list[str] = []
        start = 0
        while start < len(text):
            end = min(len(text), start + max_chars)
            boundary = max(
                text.rfind("\n", start, end),
                text.rfind("。", start, end),
                text.rfind("；", start, end),
                text.rfind("？", start, end),
                text.rfind("！", start, end),
                text.rfind(".", start, end),
                text.rfind(";", start, end),
            )
            if boundary > start + max_chars * 0.45:
                end = boundary + 1
            chunk = re.sub(r"\n{3,}", "\n\n", text[start:end]).strip()
            if chunk:
                chunks.append(chunk)
            if end >= len(text):
                break
            start = max(0, end - overlap)
        return chunks or [text]

    def _score_text(self, query: str, terms: set[str], text: str) -> float:
        haystack = str(text or "").lower()
        score = 0.0
        for term in terms:
            if term and term in haystack:
                score += 1.0 + min(len(term), 12) / 8
        compact_query = re.sub(r"\s+", "", query.lower())
        if compact_query and compact_query in re.sub(r"\s+", "", haystack):
            score += 3.0
        return score

    def _query_terms(self, text: str) -> set[str]:
        normalized = str(text or "").lower()
        terms = set(re.findall(r"[\u4e00-\u9fff]{2,}|[a-z0-9][a-z0-9_\-/+.]{1,}", normalized))
        domain_terms = [
            "低轨",
            "通信卫星",
            "宽带",
            "宽带载荷",
            "载荷",
            "分系统",
            "需求",
            "接口",
            "关键需求",
            "模型",
            "图谱",
            "sysml",
            "mbse",
            "magicdraw",
            "天线",
            "电源",
            "热控",
            "链路",
            "多波束",
            "吞吐量",
            "星上处理",
        ]
        for term in domain_terms:
            if term.lower() in normalized:
                terms.add(term.lower())
        chinese = re.findall(r"[\u4e00-\u9fff]+", normalized)
        for block in chinese:
            if len(block) > 4:
                for index in range(0, len(block) - 1):
                    terms.add(block[index : index + 2])
        return {term for term in terms if len(term) >= 2}

    def _summarize(self, text: str, max_chars: int = 260) -> str:
        normalized = re.sub(r"\s+", " ", str(text or "")).strip()
        if len(normalized) <= max_chars:
            return normalized
        return f"{normalized[:max_chars].rstrip()}..."

    def _dedupe_hits(self, hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
        seen: set[str] = set()
        result = []
        for item in hits:
            key = f"{item.get('source_type')}::{item.get('title')}::{item.get('summary')}"
            if key in seen:
                continue
            seen.add(key)
            result.append(item)
        return result

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
