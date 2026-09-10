from pathlib import Path
import re
import zipfile
from io import BytesIO
from xml.etree import ElementTree


ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "docs" / "generated" / "低轨通信卫星宽带载荷分系统关键需求与接口说明.docx"
NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}


def node_text(node):
    return re.sub(r"\s+", " ", "".join(t.text or "" for t in node.findall(".//w:t", NS))).strip()


def extract(content_bytes):
    with zipfile.ZipFile(BytesIO(content_bytes)) as archive:
        xml = archive.read("word/document.xml")
    root = ElementTree.fromstring(xml)
    body = root.find("w:body", NS)
    lines = []
    for child in list(body):
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            text = node_text(child)
            if text:
                lines.append(text)
        elif tag == "tbl":
            for row in child.findall(".//w:tr", NS):
                cells = [node_text(cell) for cell in row.findall("./w:tc", NS)]
                cells = [cell for cell in cells if cell]
                if cells:
                    lines.append(" | ".join(cells))
    return "\n".join(lines).strip()


def split(content, max_chars=520, overlap=80):
    text = re.sub(r"[ \t\r\f\v]+", " ", str(content or "")).strip()
    if not text:
        return ["该文档未解析出可检索文本。"]
    chunks = []
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


content = extract(PATH.read_bytes())
chunks = split(content)
print("chars", len(content))
print("chunks", len(chunks))
print("lengths", [len(chunk) for chunk in chunks])
print("first", chunks[0][:300].replace("\n", " / "))
