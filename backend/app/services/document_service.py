from __future__ import annotations

import re
import zipfile
from io import BytesIO
from xml.etree import ElementTree

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.models import Document, KnowledgeChunk


class DocumentService:
    def __init__(self, db: Session) -> None:
        self.db = db

    async def save_upload(self, file: UploadFile) -> Document:
        content_bytes = await file.read()
        content = self._extract_content(file.filename or "uploaded.txt", content_bytes)
        document = Document(filename=file.filename or "uploaded.txt", content=content)
        self.db.add(document)
        self.db.commit()
        self.db.refresh(document)
        from app.services.rag_service import RAGService

        RAGService(self.db).index_document(document)
        return document

    async def extract_upload(self, file: UploadFile) -> dict[str, str]:
        content_bytes = await file.read()
        filename = file.filename or "uploaded.txt"
        return {"filename": filename, "content": self._extract_content(filename, content_bytes)}

    def list_documents(self) -> list[Document]:
        return self.db.query(Document).order_by(Document.id.desc()).all()

    def get_document(self, document_id: int) -> Document | None:
        return self.db.get(Document, document_id)

    def knowledge_summary(self) -> dict:
        from app.services.rag_service import RAGService

        return RAGService(self.db).knowledge_summary()

    def reset_knowledge_base(self) -> dict:
        chunks = self.db.query(KnowledgeChunk).count()
        documents = self.db.query(Document).count()
        self.db.query(KnowledgeChunk).delete()
        self.db.query(Document).delete()
        self.db.commit()
        return {"deleted_documents": documents, "deleted_chunks": chunks}

    def _extract_content(self, filename: str, content_bytes: bytes) -> str:
        lower = filename.lower()
        if lower.endswith(".docx"):
            return self._extract_docx(content_bytes)
        if lower.endswith(".pdf"):
            return self._extract_pdf(content_bytes)
        return content_bytes.decode("utf-8", errors="ignore")

    def _extract_docx(self, content_bytes: bytes) -> str:
        with zipfile.ZipFile(BytesIO(content_bytes)) as archive:
            xml = archive.read("word/document.xml")
        root = ElementTree.fromstring(xml)
        namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        body = root.find("w:body", namespace)
        if body is None:
            texts = [node.text or "" for node in root.findall(".//w:t", namespace)]
            return re.sub(r"\s+", " ", "".join(texts)).strip()

        lines: list[str] = []
        for child in list(body):
            tag = child.tag.rsplit("}", 1)[-1]
            if tag == "p":
                text = self._docx_node_text(child, namespace)
                if text:
                    lines.append(text)
            elif tag == "tbl":
                for row in child.findall(".//w:tr", namespace):
                    cells = [
                        self._docx_node_text(cell, namespace)
                        for cell in row.findall("./w:tc", namespace)
                    ]
                    cells = [cell for cell in cells if cell]
                    if cells:
                        lines.append(" | ".join(cells))
        return "\n".join(lines).strip()

    def _docx_node_text(self, node: ElementTree.Element, namespace: dict[str, str]) -> str:
        texts = [item.text or "" for item in node.findall(".//w:t", namespace)]
        return re.sub(r"\s+", " ", "".join(texts)).strip()

    def _extract_pdf(self, content_bytes: bytes) -> str:
        try:
            from pypdf import PdfReader

            reader = PdfReader(BytesIO(content_bytes))
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
            return re.sub(r"\s+", " ", text).strip() or "PDF 文件已上传，但未解析出可检索文本。"
        except Exception:
            return "PDF 文件已上传。当前环境未安装 PDF 文本解析器，复杂版式解析可在后续接入正式文档解析器。"
