# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import date
from pathlib import Path
from textwrap import wrap

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_ALIGN_VERTICAL, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor
from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "docs"
FIG_DIR = OUT_DIR / "figures_system_summary"
OUT = OUT_DIR / "AI-MBSE-Demo系统总结报告.docx"

BLUE = RGBColor(46, 116, 181)
DARK_BLUE = RGBColor(31, 77, 120)
NAVY = RGBColor(11, 37, 69)
GRAY = RGBColor(89, 101, 121)
BLACK = RGBColor(25, 33, 44)
GREEN = RGBColor(22, 128, 73)
GOLD = RGBColor(180, 112, 18)
RED = RGBColor(185, 28, 28)

FILL_HEADER = "F2F4F7"
FILL_BLUE = "EAF3FF"
FILL_GREEN = "ECFDF3"
FILL_GOLD = "FFF7E6"
FILL_PURPLE = "F4F0FF"
FILL_CALLOUT = "F4F6F9"
BORDER = "D8E2EF"

IMG_BG = "#F8FBFF"
IMG_INK = "#172033"
IMG_MUTED = "#596579"
IMG_LINE = "#91A8C3"
IMG_BLUE = "#2563EB"
IMG_DARK = "#0B2545"
IMG_GREEN = "#16A34A"
IMG_GOLD = "#D97706"
IMG_RED = "#DC2626"
IMG_BOX = "#FFFFFF"
IMG_BOX_BLUE = "#EAF3FF"
IMG_BOX_GREEN = "#ECFDF3"
IMG_BOX_GOLD = "#FFF7E6"
IMG_BOX_PURPLE = "#F4F0FF"


def cn_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = [
        r"C:\Windows\Fonts\msyhbd.ttc" if bold else r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\simhei.ttf",
        r"C:\Windows\Fonts\simsun.ttc",
        r"C:\Windows\Fonts\arial.ttf",
    ]
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size=size)
    return ImageFont.load_default()


def wrap_cn(text: str, max_chars: int) -> list[str]:
    lines: list[str] = []
    for part in str(text).split("\n"):
        if not part:
            lines.append("")
            continue
        current = ""
        for ch in part:
            current += ch
            if len(current) >= max_chars:
                lines.append(current)
                current = ""
        if current:
            lines.append(current)
    return lines or [""]


def draw_round_box(draw: ImageDraw.ImageDraw, xy, fill, outline=IMG_LINE, radius=18, width=2) -> None:
    draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=width)


def text_center(
    draw: ImageDraw.ImageDraw,
    box,
    text: str,
    size: int = 26,
    fill: str = IMG_INK,
    bold: bool = False,
    max_chars: int = 10,
    line_gap: int = 7,
) -> None:
    font = cn_font(size, bold)
    lines = wrap_cn(text, max_chars)
    dims = [draw.textbbox((0, 0), line, font=font) for line in lines]
    heights = [b[3] - b[1] for b in dims]
    widths = [b[2] - b[0] for b in dims]
    total_h = sum(heights) + max(0, len(lines) - 1) * line_gap
    x1, y1, x2, y2 = box
    y = y1 + (y2 - y1 - total_h) / 2
    for idx, line in enumerate(lines):
        draw.text((x1 + (x2 - x1 - widths[idx]) / 2, y), line, font=font, fill=fill)
        y += heights[idx] + line_gap


def text_left(draw: ImageDraw.ImageDraw, xy, text: str, size: int = 24, fill: str = IMG_INK, bold: bool = False, max_chars: int = 36) -> None:
    x, y = xy
    font = cn_font(size, bold)
    for line in wrap_cn(text, max_chars):
        draw.text((x, y), line, font=font, fill=fill)
        y += size + 10


def arrow(draw: ImageDraw.ImageDraw, start, end, color=IMG_LINE, width=4) -> None:
    draw.line([start, end], fill=color, width=width)
    x1, y1 = start
    x2, y2 = end
    if abs(x2 - x1) >= abs(y2 - y1):
        direction = 1 if x2 >= x1 else -1
        pts = [(x2, y2), (x2 - direction * 18, y2 - 9), (x2 - direction * 18, y2 + 9)]
    else:
        direction = 1 if y2 >= y1 else -1
        pts = [(x2, y2), (x2 - 9, y2 - direction * 18), (x2 + 9, y2 - direction * 18)]
    draw.polygon(pts, fill=color)


def canvas(name: str, width: int = 1600, height: int = 940):
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (width, height), IMG_BG)
    draw = ImageDraw.Draw(img)
    return img, draw, FIG_DIR / name


def figure_architecture() -> Path:
    img, draw, path = canvas("figure_01_architecture.png", 1700, 1040)
    draw.text((70, 46), "AI-MBSE-Demo 总体技术架构", font=cn_font(42, True), fill=IMG_INK)
    draw.text((72, 105), "系统采用前端工作台、后端服务编排、AI/RAG 能力、模型草稿闭环、正式模型库和外部工程工具集成的分层架构。", font=cn_font(24), fill=IMG_MUTED)

    layers = [
        ("用户与角色层", "设计师：建模、预览、提交；管理员：审核、冲突处理、合并入库", IMG_BOX_BLUE),
        ("前端交互层", "React + Ant Design + ReactFlow：AI 智能体、SysML 文本、模型画布、入库管理、仿真页面", IMG_BOX),
        ("后端 API 层", "FastAPI 路由：chat、documents、requirements、sysml、merge、magicdraw、impact、simulation、health", IMG_BOX_GREEN),
        ("AI 与知识增强层", "LLMService、RAGService、文档解析与切片、意图识别、工具调用过程展示", IMG_BOX_GOLD),
        ("模型闭环服务层", "ModelGeneration、ModelDraft、DraftValidation、Merge、Impact、SysMLAdapter、MagicDrawAdapter", IMG_BOX_PURPLE),
        ("数据与外部工具层", "SQLite 运行态/模型库、SysML v2 API、MagicDraw/Cameo Bridge、GMAT、MATLAB/Simulink", IMG_BOX),
    ]
    x1, x2 = 105, 1595
    y = 175
    boxes = []
    for title, desc, fill in layers:
        box = (x1, y, x2, y + 112)
        draw_round_box(draw, box, fill)
        draw.text((x1 + 34, y + 24), title, font=cn_font(30, True), fill=IMG_DARK)
        text_left(draw, (x1 + 360, y + 25), desc, size=24, fill=IMG_INK, max_chars=48)
        boxes.append(box)
        y += 130
    for idx in range(len(boxes) - 1):
        arrow(draw, ((x1 + x2) // 2, boxes[idx][3] + 2), ((x1 + x2) // 2, boxes[idx + 1][1] - 10), IMG_BLUE, 4)
    img.save(path)
    return path


def figure_workflow() -> Path:
    img, draw, path = canvas("figure_02_business_workflow.png", 1800, 980)
    draw.text((70, 46), "端到端建模业务流程", font=cn_font(42, True), fill=IMG_INK)
    draw.text((72, 105), "从需求输入到 AI 生成、人工修正、预评审、提交审核、合并入库和工程工具同步的完整闭环。", font=cn_font(24), fill=IMG_MUTED)
    steps = [
        ("需求输入", "文本/附件/项目上下文"),
        ("RAG 增强", "知识库检索与引用"),
        ("AI 建模", "生成元素/关系/SysML"),
        ("人工回路", "修正、采纳或拒绝"),
        ("预评审", "规则检查与评分"),
        ("提交 MR", "设计师发起合并请求"),
        ("管理员审核", "冲突处理/合并/拒绝"),
        ("正式发布", "入库并发布推送"),
    ]
    x, y = 64, 310
    w, h, gap = 194, 128, 24
    for idx, (title, desc) in enumerate(steps):
        fill = [IMG_BOX_BLUE, IMG_BOX_GREEN, IMG_BOX_GOLD, IMG_BOX, IMG_BOX_PURPLE, IMG_BOX_GOLD, IMG_BOX_BLUE, IMG_BOX_GREEN][idx]
        box = (x, y, x + w, y + h)
        draw_round_box(draw, box, fill, radius=18)
        text_center(draw, (x + 12, y + 18, x + w - 12, y + 64), title, size=27, bold=True, max_chars=8)
        text_center(draw, (x + 14, y + 66, x + w - 14, y + h - 14), desc, size=20, fill=IMG_MUTED, max_chars=9)
        if idx < len(steps) - 1:
            arrow(draw, (x + w + 5, y + h // 2), (x + w + gap - 7, y + h // 2), IMG_BLUE, 4)
        x += w + gap

    draw.arc((280, 500, 1260, 810), start=0, end=180, fill=IMG_GOLD, width=5)
    arrow(draw, (282, 655), (265, 652), IMG_GOLD, 4)
    draw.text((500, 720), "预评审发现问题后，可回到草稿继续人工修正或一键修复", font=cn_font(25, True), fill=IMG_GOLD)
    draw.rounded_rectangle((1220, 610, 1690, 800), radius=18, fill="#FFFFFF", outline=IMG_LINE, width=2)
    draw.text((1250, 636), "推送策略", font=cn_font(28, True), fill=IMG_DARK)
    text_left(draw, (1250, 685), "预览推送：生成后即可推到 PREVIEW 包检查效果\n发布推送：管理员合并入库后推到正式包", size=22, fill=IMG_INK, max_chars=28)
    img.save(path)
    return path


def figure_data_model() -> Path:
    img, draw, path = canvas("figure_03_data_model.png", 1700, 1100)
    draw.text((70, 46), "核心数据模型与状态流", font=cn_font(42, True), fill=IMG_INK)
    draw.text((72, 105), "SQLite 同时承担知识库、草稿态、审核态、正式模型库和分析报告的持久化；后端重启默认清空运行态并保留知识库。", font=cn_font(24), fill=IMG_MUTED)

    tables = [
        ("documents\nknowledge_chunks", "文档原文、切片、关键词\n用于 RAG 检索", 95, 220, IMG_BOX_GREEN),
        ("model_drafts", "original_json：AI 初稿\ncurrent_json：人工修正后版本\nstatus：preview/revised/submitted/accepted/rejected", 610, 190, IMG_BOX_GOLD),
        ("model_feedback_logs", "修正、采纳、拒绝、一键修复\n记录 before/after", 610, 460, IMG_BOX),
        ("merge_requests\nmerge_audit_logs", "候选快照、发布快照、变更集、冲突、解决策略、审核日志", 1085, 290, IMG_BOX_BLUE),
        ("sysml_elements\nsysml_relationships", "正式模型库\n入库后状态为 released", 1085, 610, IMG_BOX_PURPLE),
        ("change_scenarios\nimpact_reports", "变更场景、影响拓扑、风险矩阵、建议", 610, 760, IMG_BOX_GREEN),
    ]
    for name, desc, x, y, fill in tables:
        box = (x, y, x + 360, y + 160)
        draw_round_box(draw, box, fill)
        text_center(draw, (x + 18, y + 15, x + 342, y + 68), name, size=25, bold=True, max_chars=22)
        text_center(draw, (x + 22, y + 76, x + 338, y + 145), desc, size=19, fill=IMG_MUTED, max_chars=20, line_gap=4)

    arrow(draw, (455, 300), (610, 270), IMG_GREEN, 5)
    draw.text((470, 235), "检索增强", font=cn_font(22), fill=IMG_MUTED)
    arrow(draw, (790, 350), (790, 460), IMG_GOLD, 5)
    draw.text((815, 405), "反馈闭环", font=cn_font(22), fill=IMG_MUTED)
    arrow(draw, (970, 270), (1085, 350), IMG_BLUE, 5)
    draw.text((980, 300), "提交 MR", font=cn_font(22), fill=IMG_MUTED)
    arrow(draw, (1265, 450), (1265, 610), IMG_BLUE, 5)
    draw.text((1290, 520), "合并入库", font=cn_font(22), fill=IMG_MUTED)
    arrow(draw, (1085, 690), (970, 840), IMG_GREEN, 5)
    draw.text((945, 735), "影响分析", font=cn_font(22), fill=IMG_MUTED)
    img.save(path)
    return path


def figure_merge_publish() -> Path:
    img, draw, path = canvas("figure_04_merge_publish.png", 1700, 960)
    draw.text((70, 46), "设计师-管理员合并发布生命周期", font=cn_font(42, True), fill=IMG_INK)
    draw.text((72, 105), "系统将“预览检查”和“正式发布”拆开：预览不要求管理员合并，正式发布必须经过审核并写入 release/main。", font=cn_font(24), fill=IMG_MUTED)

    lanes = [
        ("设计师账号", 190, IMG_BOX_BLUE),
        ("管理员账号", 480, IMG_BOX_GOLD),
        ("正式模型库 / MagicDraw", 770, IMG_BOX_GREEN),
    ]
    for title, y, fill in lanes:
        draw.rounded_rectangle((80, y, 1620, y + 175), radius=18, fill=fill, outline=IMG_LINE, width=2)
        draw.text((110, y + 18), title, font=cn_font(28, True), fill=IMG_DARK)

    designer_steps = [("生成草稿", 300), ("预览推送", 565), ("提交合并请求", 830), ("查看审核结果", 1110)]
    admin_steps = [("接收 MR", 420), ("解决冲突", 690), ("合并入库", 960)]
    release_steps = [("release/main", 520), ("发布推送", 810), ("工程交付", 1100)]
    for label, x in designer_steps:
        draw_round_box(draw, (x, 245, x + 170, 320), "#FFFFFF")
        text_center(draw, (x + 8, 250, x + 162, 316), label, size=23, bold=True, max_chars=8)
    for label, x in admin_steps:
        draw_round_box(draw, (x, 535, x + 170, 610), "#FFFFFF")
        text_center(draw, (x + 8, 540, x + 162, 606), label, size=23, bold=True, max_chars=8)
    for label, x in release_steps:
        draw_round_box(draw, (x, 825, x + 180, 900), "#FFFFFF")
        text_center(draw, (x + 8, 830, x + 172, 896), label, size=23, bold=True, max_chars=9)

    arrow(draw, (470, 282), (565, 282), IMG_BLUE, 4)
    arrow(draw, (735, 282), (830, 282), IMG_BLUE, 4)
    arrow(draw, (1000, 315), (470, 535), IMG_GOLD, 4)
    arrow(draw, (590, 572), (690, 572), IMG_GOLD, 4)
    arrow(draw, (860, 572), (960, 572), IMG_GOLD, 4)
    arrow(draw, (1045, 610), (610, 825), IMG_GREEN, 4)
    arrow(draw, (700, 862), (810, 862), IMG_GREEN, 4)
    arrow(draw, (990, 862), (1100, 862), IMG_GREEN, 4)
    arrow(draw, (1140, 535), (1150, 320), IMG_GOLD, 4)
    draw.text((1240, 365), "状态回传给设计师\n避免切换账号后丢失上下文", font=cn_font(23), fill=IMG_MUTED)
    img.save(path)
    return path


def figure_external_tools() -> Path:
    img, draw, path = canvas("figure_05_external_tools.png", 1700, 980)
    draw.text((70, 46), "外部工程工具集成拓扑", font=cn_font(42, True), fill=IMG_INK)
    draw.text((72, 105), "后端对外部工具采用“真实接口优先、失败时本地交换包/Mock 兜底”的策略，提高演示和集成调试稳定性。", font=cn_font(24), fill=IMG_MUTED)

    center = (760, 460)
    draw_round_box(draw, (center[0] - 210, center[1] - 88, center[0] + 210, center[1] + 88), IMG_BOX_BLUE)
    text_center(draw, (center[0] - 190, center[1] - 70, center[0] + 190, center[1] + 70), "FastAPI 后端\n服务编排中心", size=29, bold=True, max_chars=12)

    nodes = [
        ("LLM API\n或本地 Mock", 170, 230, IMG_BOX_GOLD),
        ("SysML v2 API\n或 SQLite 落库", 1160, 230, IMG_BOX_GREEN),
        ("MagicDraw Bridge\n127.0.0.1:7010", 1160, 610, IMG_BOX_PURPLE),
        ("GMAT Console\n轨道传播仿真", 170, 610, IMG_BOX),
        ("MATLAB/Simulink\n动态系统仿真", 665, 740, IMG_BOX),
    ]
    for label, x, y, fill in nodes:
        draw_round_box(draw, (x, y, x + 360, y + 135), fill)
        text_center(draw, (x + 18, y + 14, x + 342, y + 120), label, size=25, bold=True, max_chars=16)
    arrow(draw, (550, 420), (440, 365), IMG_GOLD, 5)
    arrow(draw, (970, 420), (1160, 365), IMG_GREEN, 5)
    arrow(draw, (970, 510), (1160, 675), IMG_BLUE, 5)
    arrow(draw, (550, 510), (440, 675), IMG_BLUE, 5)
    arrow(draw, (760, 548), (845, 740), IMG_BLUE, 5)
    img.save(path)
    return path


def figure_screenshot_sheet(name: str, items: list[tuple[str, str]]) -> Path:
    out = FIG_DIR / name
    width, height = 1800, 1260
    img = Image.new("RGB", (width, height), "#FFFFFF")
    draw = ImageDraw.Draw(img)
    draw.text((55, 35), "系统界面截图组", font=cn_font(38, True), fill=IMG_INK)
    draw.text((55, 88), "以下截图来自当前工程的本地演示界面，用于说明主要功能入口和闭环操作。", font=cn_font(22), fill=IMG_MUTED)
    cols, rows = 2, 3
    card_w, card_h = 805, 330
    start_x, start_y = 55, 150
    gap_x, gap_y = 80, 55
    for idx, (filename, caption) in enumerate(items[:6]):
        row, col = divmod(idx, cols)
        x = start_x + col * (card_w + gap_x)
        y = start_y + row * (card_h + gap_y)
        draw.rounded_rectangle((x, y, x + card_w, y + card_h), radius=16, fill="#F8FBFF", outline=IMG_LINE, width=2)
        p = ROOT / "截图" / filename
        if p.exists():
            shot = Image.open(p).convert("RGB")
            shot.thumbnail((card_w - 28, card_h - 72))
            sx = x + (card_w - shot.width) // 2
            sy = y + 16
            img.paste(shot, (sx, sy))
        else:
            draw.text((x + 30, y + 120), f"缺少截图：{filename}", font=cn_font(24, True), fill=IMG_RED)
        draw.text((x + 22, y + card_h - 43), caption, font=cn_font(22, True), fill=IMG_DARK)
    img.save(out)
    return out


def add_field_run(paragraph, field_code: str) -> None:
    run = paragraph.add_run()
    fld_begin = OxmlElement("w:fldChar")
    fld_begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = field_code
    fld_sep = OxmlElement("w:fldChar")
    fld_sep.set(qn("w:fldCharType"), "separate")
    fld_end = OxmlElement("w:fldChar")
    fld_end.set(qn("w:fldCharType"), "end")
    run._r.append(fld_begin)
    run._r.append(instr)
    run._r.append(fld_sep)
    run._r.append(fld_end)


def set_run_font(run, size: float | None = None, bold: bool | None = None, color: RGBColor | None = None) -> None:
    run.font.name = "Calibri"
    run._element.rPr.rFonts.set(qn("w:ascii"), "Calibri")
    run._element.rPr.rFonts.set(qn("w:hAnsi"), "Calibri")
    run._element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")
    if size is not None:
        run.font.size = Pt(size)
    if bold is not None:
        run.bold = bold
    if color is not None:
        run.font.color.rgb = color


def set_paragraph_runs(paragraph, size: float, color: RGBColor | None = None, bold: bool | None = None) -> None:
    for run in paragraph.runs:
        set_run_font(run, size=size, color=color, bold=bold)


def shade_cell(cell, fill: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = tc_pr.find(qn("w:shd"))
    if shd is None:
        shd = OxmlElement("w:shd")
        tc_pr.append(shd)
    shd.set(qn("w:fill"), fill)


def set_cell_margins(cell, top=80, start=120, bottom=80, end=120) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    tc_mar = tc_pr.first_child_found_in("w:tcMar")
    if tc_mar is None:
        tc_mar = OxmlElement("w:tcMar")
        tc_pr.append(tc_mar)
    for key, value in {"top": top, "start": start, "bottom": bottom, "end": end}.items():
        node = tc_mar.find(qn(f"w:{key}"))
        if node is None:
            node = OxmlElement(f"w:{key}")
            tc_mar.append(node)
        node.set(qn("w:w"), str(value))
        node.set(qn("w:type"), "dxa")


def set_cell_text(cell, text: str, bold: bool = False, color: RGBColor | None = None, size: float = 9.2, align=None) -> None:
    cell.text = ""
    cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
    set_cell_margins(cell)
    p = cell.paragraphs[0]
    p.paragraph_format.space_after = Pt(0)
    p.paragraph_format.line_spacing = 1.1
    if align is not None:
        p.alignment = align
    parts = str(text).split("\n")
    for idx, part in enumerate(parts):
        if idx:
            p.add_run().add_break()
        run = p.add_run(part)
        set_run_font(run, size=size, bold=bold, color=color)


def set_table_geometry(table, widths_in: list[float]) -> None:
    table.autofit = False
    table.alignment = WD_TABLE_ALIGNMENT.LEFT
    total = int(sum(widths_in) * 1440)
    tbl_pr = table._tbl.tblPr
    tbl_w = tbl_pr.find(qn("w:tblW"))
    if tbl_w is None:
        tbl_w = OxmlElement("w:tblW")
        tbl_pr.append(tbl_w)
    tbl_w.set(qn("w:w"), str(total))
    tbl_w.set(qn("w:type"), "dxa")
    tbl_ind = tbl_pr.find(qn("w:tblInd"))
    if tbl_ind is None:
        tbl_ind = OxmlElement("w:tblInd")
        tbl_pr.append(tbl_ind)
    tbl_ind.set(qn("w:w"), "120")
    tbl_ind.set(qn("w:type"), "dxa")
    grid = table._tbl.tblGrid
    if grid is None:
        grid = OxmlElement("w:tblGrid")
        table._tbl.insert(1, grid)
    for child in list(grid):
        grid.remove(child)
    for width in widths_in:
        col = OxmlElement("w:gridCol")
        col.set(qn("w:w"), str(int(width * 1440)))
        grid.append(col)
    for row in table.rows:
        for idx, cell in enumerate(row.cells):
            if idx >= len(widths_in):
                continue
            cell.width = Inches(widths_in[idx])
            tc_pr = cell._tc.get_or_add_tcPr()
            tc_w = tc_pr.find(qn("w:tcW"))
            if tc_w is None:
                tc_w = OxmlElement("w:tcW")
                tc_pr.append(tc_w)
            tc_w.set(qn("w:w"), str(int(widths_in[idx] * 1440)))
            tc_w.set(qn("w:type"), "dxa")


def repeat_table_header(table) -> None:
    if not table.rows:
        return
    tr_pr = table.rows[0]._tr.get_or_add_trPr()
    tbl_header = tr_pr.find(qn("w:tblHeader"))
    if tbl_header is None:
        tbl_header = OxmlElement("w:tblHeader")
        tr_pr.append(tbl_header)
    tbl_header.set(qn("w:val"), "true")


def add_table(doc: Document, headers: list[str], rows: list[list[str]], widths: list[float], body_size: float = 8.8):
    table = doc.add_table(rows=1, cols=len(headers))
    table.style = "Table Grid"
    set_table_geometry(table, widths)
    repeat_table_header(table)
    for idx, header in enumerate(headers):
        shade_cell(table.cell(0, idx), FILL_HEADER)
        set_cell_text(table.cell(0, idx), header, bold=True, color=NAVY, size=9.2, align=WD_ALIGN_PARAGRAPH.CENTER)
    for row in rows:
        cells = table.add_row().cells
        for idx, text in enumerate(row):
            set_cell_text(cells[idx], text, size=body_size)
    doc.add_paragraph().paragraph_format.space_after = Pt(2)
    return table


def add_rule(paragraph, color=BORDER) -> None:
    p_pr = paragraph._p.get_or_add_pPr()
    p_bdr = p_pr.find(qn("w:pBdr"))
    if p_bdr is None:
        p_bdr = OxmlElement("w:pBdr")
        p_pr.append(p_bdr)
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), "8")
    bottom.set(qn("w:space"), "6")
    bottom.set(qn("w:color"), color)
    p_bdr.append(bottom)


def add_heading(doc: Document, text: str, level: int = 1):
    p = doc.add_heading(text, level=level)
    if level == 1:
        set_paragraph_runs(p, 16, BLUE, True)
        p.paragraph_format.space_before = Pt(16)
        p.paragraph_format.space_after = Pt(8)
    elif level == 2:
        set_paragraph_runs(p, 13, BLUE, True)
        p.paragraph_format.space_before = Pt(12)
        p.paragraph_format.space_after = Pt(6)
    else:
        set_paragraph_runs(p, 12, DARK_BLUE, True)
        p.paragraph_format.space_before = Pt(8)
        p.paragraph_format.space_after = Pt(4)
    return p


def add_body(doc: Document, text: str, bold_prefix: str | None = None):
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(6)
    p.paragraph_format.line_spacing = 1.1
    if bold_prefix and text.startswith(bold_prefix):
        r1 = p.add_run(bold_prefix)
        set_run_font(r1, 11, True, BLACK)
        r2 = p.add_run(text[len(bold_prefix):])
        set_run_font(r2, 11, False, BLACK)
    else:
        run = p.add_run(text)
        set_run_font(run, 11, False, BLACK)
    return p


def add_bullet(doc: Document, text: str, level: int = 0):
    p = doc.add_paragraph(style="List Bullet" if level == 0 else "List Bullet 2")
    p.paragraph_format.space_after = Pt(4)
    p.paragraph_format.line_spacing = 1.167
    run = p.add_run(text)
    set_run_font(run, 10.5, False, BLACK)
    return p


def add_number(doc: Document, text: str):
    p = doc.add_paragraph(style="List Number")
    p.paragraph_format.space_after = Pt(4)
    p.paragraph_format.line_spacing = 1.167
    run = p.add_run(text)
    set_run_font(run, 10.5, False, BLACK)
    return p


def add_callout(doc: Document, title: str, body: str, fill: str = FILL_CALLOUT) -> None:
    table = doc.add_table(rows=1, cols=1)
    table.style = "Table Grid"
    set_table_geometry(table, [6.5])
    cell = table.cell(0, 0)
    shade_cell(cell, fill)
    set_cell_margins(cell, top=130, bottom=130, start=160, end=160)
    p = cell.paragraphs[0]
    p.paragraph_format.space_after = Pt(4)
    r1 = p.add_run(title)
    set_run_font(r1, 10.5, True, NAVY)
    p2 = cell.add_paragraph()
    p2.paragraph_format.space_after = Pt(0)
    p2.paragraph_format.line_spacing = 1.1
    r2 = p2.add_run(body)
    set_run_font(r2, 10.2, False, BLACK)
    doc.add_paragraph().paragraph_format.space_after = Pt(2)


def add_picture(doc: Document, path: Path, caption: str, width: float = 6.5) -> None:
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.keep_with_next = True
    run = p.add_run()
    run.add_picture(str(path), width=Inches(width))
    cp = doc.add_paragraph()
    cp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    cp.paragraph_format.space_after = Pt(8)
    r = cp.add_run(caption)
    set_run_font(r, 9.4, False, GRAY)


def setup_document() -> Document:
    doc = Document()
    section = doc.sections[0]
    section.page_width = Inches(8.5)
    section.page_height = Inches(11)
    section.top_margin = Inches(1)
    section.bottom_margin = Inches(1)
    section.left_margin = Inches(1)
    section.right_margin = Inches(1)
    section.header_distance = Inches(0.492)
    section.footer_distance = Inches(0.492)

    styles = doc.styles
    normal = styles["Normal"]
    normal.font.name = "Calibri"
    normal._element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")
    normal.font.size = Pt(11)
    normal.paragraph_format.space_after = Pt(6)
    normal.paragraph_format.line_spacing = 1.1

    for style_name in ["List Bullet", "List Bullet 2", "List Number"]:
        style = styles[style_name]
        style.font.name = "Calibri"
        style._element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")
        style.font.size = Pt(10.5)
        style.paragraph_format.space_after = Pt(4)
        style.paragraph_format.line_spacing = 1.167

    return doc


def set_header_footer(doc: Document) -> None:
    section = doc.sections[0]
    header = section.header
    p = header.paragraphs[0]
    p.text = ""
    run = p.add_run("AI-MBSE-Demo 系统总结报告")
    set_run_font(run, 9, False, GRAY)
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    add_rule(p, "E1E7F0")

    footer = section.footer
    p = footer.paragraphs[0]
    p.text = ""
    r1 = p.add_run("内部设计报告资料  |  第 ")
    set_run_font(r1, 9, False, GRAY)
    add_field_run(p, "PAGE")
    r2 = p.add_run(" 页")
    set_run_font(r2, 9, False, GRAY)
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER


def title_page(doc: Document) -> None:
    doc.core_properties.title = "AI-MBSE-Demo系统总结报告"
    doc.core_properties.subject = "AI赋能MBSE系统设计平台总结"
    doc.core_properties.author = "AI-MBSE-Demo 项目组"

    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(42)
    p.paragraph_format.space_after = Pt(4)
    r = p.add_run("AI-MBSE-Demo")
    set_run_font(r, 16, True, BLUE)
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER

    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(8)
    r = p.add_run("AI 赋能 MBSE 系统设计平台总结报告")
    set_run_font(r, 26, True, NAVY)
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER

    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(30)
    r = p.add_run("面向需求理解、模型生成、人机协同、预评审、合并入库、MagicDraw 同步与仿真验证的一体化原型系统")
    set_run_font(r, 12.5, False, GRAY)
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER

    meta = [
        ("报告类型", "系统总结 / 设计报告素材"),
        ("系统版本", "当前本地实现版本（截至 2026-06-29）"),
        ("覆盖范围", "前端工作台、后端服务、SQLite 数据库、AI/RAG、SysML 建模、合并审核、MagicDraw Bridge、GMAT/Simulink 仿真"),
        ("交付形式", "可直接插入设计报告的 Word 文档"),
    ]
    table = doc.add_table(rows=len(meta), cols=2)
    table.style = "Table Grid"
    set_table_geometry(table, [1.55, 4.95])
    for idx, (label, value) in enumerate(meta):
        shade_cell(table.cell(idx, 0), FILL_HEADER)
        set_cell_text(table.cell(idx, 0), label, True, NAVY, 9.4)
        set_cell_text(table.cell(idx, 1), value, False, BLACK, 9.4)

    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(28)
    p.paragraph_format.space_after = Pt(4)
    r = p.add_run(f"生成日期：{date.today().isoformat()}")
    set_run_font(r, 10.5, False, GRAY)
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    doc.add_page_break()


def toc_page(doc: Document) -> None:
    add_heading(doc, "报告结构", 1)
    rows = [
        ["1", "系统建设背景与总体目标", "说明系统要解决的 MBSE 建模效率、追溯、评审和工程工具联动问题。"],
        ["2", "总体架构设计", "从用户、前端、后端、AI/RAG、模型服务、数据和外部工具六层描述实现。"],
        ["3", "核心业务流程", "描述需求输入、建模、人工回路、预评审、合并审核、预览推送和发布推送。"],
        ["4", "前后端模块实现", "总结 React 工作台、FastAPI 路由、服务层与数据层职责。"],
        ["5", "模型草稿、预评审与合并入库", "重点说明 draft、feedback、merge request、release/main 的状态闭环。"],
        ["6", "外部工具与仿真集成", "总结 SysML v2、MagicDraw Bridge、GMAT、Simulink 的接入策略。"],
        ["7", "部署配置、运行状态与后续演进", "列出启动配置、重启清空策略、验证情况和下一步建议。"],
    ]
    add_table(doc, ["序号", "章节", "说明"], rows, [0.55, 2.2, 3.75], body_size=9.0)
    add_callout(
        doc,
        "阅读提示",
        "本文档按照设计报告常用结构组织，可整体放入“系统总体设计”“关键模块设计”“实现与验证”章节，也可以拆分后嵌入现有报告。图号和表号均为正文内描述性编号，便于后续统一编号。",
        FILL_BLUE,
    )
    doc.add_page_break()


def section_overview(doc: Document, figs: dict[str, Path]) -> None:
    add_heading(doc, "1. 系统建设背景与总体目标", 1)
    add_body(
        doc,
        "AI-MBSE-Demo 是一套面向系统工程建模场景的本地原型平台，目标是在传统 MBSE 工具链前增加 AI 赋能的需求理解、模型生成、知识增强、人工确认、规则校验和工程工具同步能力。系统不是单纯的聊天机器人，而是围绕 SysML 模型对象和工程流程建立的闭环工作台：设计师可以通过自然语言和附件输入任务，系统生成候选模型；设计师在可视化界面中检查并修正；管理员对提交的模型变更进行审核合并；最终模型进入正式库并可推送到 MagicDraw/Cameo 或进入仿真验证流程。"
    )
    add_body(
        doc,
        "当前版本重点解决三个设计问题：第一，将 AI 输出从一次性文本转化为可追踪、可修正、可审核的模型草稿；第二，将设计师和管理员的职责分离，形成类似开发分支与发布分支的模型入库机制；第三，将模型工程结果与外部 MBSE/仿真工具打通，使演示平台具备工程落地接口而不仅是界面演示。"
    )
    add_table(
        doc,
        ["建设目标", "实现方式", "当前效果"],
        [
            ["降低建模门槛", "通过 AI 智能体解析自然语言需求，自动生成 Requirement、UseCase、Block、Interface、Activity、ConstraintBlock 等对象。", "用户可从对话直接进入 SysML 工程草稿，并看到模型元素、关系、文本和画布。"],
            ["强化人机协同", "引入 model_drafts 和 model_feedback_logs，保存 AI 原始稿、人工修正稿和反馈记录。", "设计师可修改元素、关系和画布，采纳或拒绝候选模型，形成可追溯闭环。"],
            ["保证入库质量", "加入预评审规则、一键修复、合并请求、冲突识别、管理员审核和发布分支。", "模型必须经过审核合并后才进入正式库；预览推送与发布推送职责清晰。"],
            ["连接工程工具", "通过 SysMLAdapter、MagicDrawAdapter、GMAT/Simulink 适配器连接外部工具。", "MagicDraw 可通过本地 Bridge 导入模型，Bridge 不在线时生成本地交换包；仿真页面可展示真实工具状态。"],
        ],
        [1.4, 2.65, 2.45],
    )
    add_picture(doc, figs["workflow"], "图 1  端到端建模业务流程：AI 生成候选模型后，通过人工回路、预评审和管理员审核进入正式模型库。")


def section_architecture(doc: Document, figs: dict[str, Path]) -> None:
    add_heading(doc, "2. 总体架构设计", 1)
    add_body(
        doc,
        "系统采用分层架构。前端负责人机交互和过程可视化；后端负责 API 编排、业务状态流转和外部工具适配；SQLite 作为原型阶段的统一持久化层，保存知识库、候选草稿、反馈日志、合并请求、正式模型库和分析报告；外部工具通过适配器接入，保证同一套业务流程可以在真实工具在线和离线演示两种状态下运行。"
    )
    add_picture(doc, figs["architecture"], "图 2  系统总体技术架构：从用户角色到外部工程工具的分层关系。")
    add_heading(doc, "2.1 技术栈组成", 2)
    add_table(
        doc,
        ["层次", "主要技术", "说明"],
        [
            ["前端", "React 18、Vite 5、TypeScript、Ant Design 5、ReactFlow", "构建 AI 工作台、模型画布、审核面板、状态指标和仿真页面。"],
            ["后端", "FastAPI、Pydantic、SQLAlchemy、Uvicorn、httpx", "提供 REST API、请求校验、数据库访问、外部 HTTP 调用和服务编排。"],
            ["数据层", "SQLite、SQLAlchemy ORM", "原型阶段统一保存运行态、模型态、知识库和审核态数据。"],
            ["AI 能力", "LLMService、RAGService、本地 Mock 兜底", "支持真实大模型 API，也支持离线 Mock，保证演示稳定。"],
            ["MBSE 接口", "SysML v2 API、MagicDraw/Cameo Bridge 插件", "SysML 正式入库与 MagicDraw 模型导入采用适配器隔离。"],
            ["仿真接口", "GMAT Console、MATLAB/Simulink", "支持轨道传播和动态系统仿真工具的真实调用或演示兜底。"],
        ],
        [1.0, 2.2, 3.3],
    )
    add_heading(doc, "2.2 架构设计特点", 2)
    for item in [
        "业务流程以模型对象为中心，不把 AI 回答作为最终结果，而是把 AI 输出落到可编辑、可校验、可合并的数据结构中。",
        "外部工具接入采用 Adapter 模式，后端业务层不直接依赖 MagicDraw、SysML、GMAT 或 Simulink 的具体调用细节。",
        "前端按设计师和管理员角色区分工作流：设计师侧强调建模、预览和提交；管理员侧强调审核、冲突处理和合并入库。",
        "系统默认在后端重启时清空运行态，前端通过 backend_session_id 感知后端新会话并清理工作台缓存，使演示环境回到等待建模状态。",
    ]:
        add_bullet(doc, item)


def section_frontend_backend(doc: Document, figs: dict[str, Path]) -> None:
    add_heading(doc, "3. 前后端模块实现", 1)
    add_heading(doc, "3.1 前端工作台", 2)
    add_body(
        doc,
        "前端主界面集中在 AgentWorkbench。该页面不是传统表单式流程，而是将 AI 对话、项目管理、模型画布、SysML 文本、MagicDraw 同步、预评审、变更影响和入库管理集成到同一个工作区。设计师可以在左侧对话区输入需求和查看 AI 过程，中间/右侧区域根据当前阶段展示模型、验证、合并或同步状态。"
    )
    add_table(
        doc,
        ["前端模块", "文件位置", "职责"],
        [
            ["应用入口与会话", "frontend/src/App.tsx", "角色登录、页面路由、后端会话 ID 检测、重启后清理本地工作台缓存。"],
            ["AI 工作台", "frontend/src/pages/AgentWorkbench.tsx", "对话、建模、草稿恢复、预览推送、发布推送、审核面板、画布和工作流进度。"],
            ["仪表盘", "frontend/src/pages/Dashboard.tsx", "管理员入口、状态概览和主要功能导航。"],
            ["仿真页面", "frontend/src/pages/SimulationMock.tsx", "GMAT/Simulink 工具状态展示和仿真运行入口。"],
            ["API Client", "frontend/src/api/client.ts", "统一封装后端 REST 接口，避免页面直接拼接请求。"],
            ["类型定义", "frontend/src/types/index.ts", "Health、Draft、MergeRequest、Validation、Simulation 等数据结构。"],
        ],
        [1.25, 2.25, 3.0],
        body_size=8.6,
    )
    add_picture(doc, figs["screens1"], "图 3  主要界面截图组：登录、主工作台、人工回路、预评审、提交请求和管理员审核。")
    add_heading(doc, "3.2 后端服务", 2)
    add_body(
        doc,
        "后端采用 FastAPI + 服务层模式。main.py 负责应用初始化和路由注册；routers 目录定义 API 边界；services 目录承载实际业务逻辑；models.py 定义数据库表；schemas.py 定义请求和响应模型。这样的分层使得前端交互、数据库持久化、AI 调用和外部工具调用之间保持清晰边界。"
    )
    add_table(
        doc,
        ["路由模块", "主要接口", "业务职责"],
        [
            ["health", "GET /api/health", "返回 LLM、SysML、MagicDraw、Simulation、SQLite 状态和 backend_session_id。"],
            ["documents", "POST /documents/upload\nGET /documents\nGET /documents/knowledge-summary", "上传 txt/docx/pdf，抽取内容并写入知识库切片。"],
            ["chat", "POST /chat", "AI 智能体对话、工具路由和过程记录。"],
            ["requirements", "POST /requirements/analyze\nPOST /requirements/{id}/review", "结构化需求分析和逐条人工确认。"],
            ["sysml", "POST /sysml/generate-project\nPATCH /sysml/drafts/*\nPOST /sysml/drafts/{id}/validate/fix/accept/reject", "生成 SysML 工程草稿、修改元素关系、预评审、一键修复、采纳拒绝。"],
            ["merge", "POST /merge/requests\nPOST /merge/requests/{id}/resolve/merge/reject", "提交合并请求、管理员冲突处理、合并入库和拒绝。"],
            ["magicdraw", "GET /magicdraw/status\nPOST /magicdraw/publish", "检查 Bridge 状态、生成交换包或推送到 MagicDraw。"],
            ["impact", "POST /impact/analyze\nPOST /impact/sandbox", "基于模型关系图和规则做变更影响分析。"],
            ["simulation", "GET /simulation/status\nPOST /simulation/run", "GMAT/Simulink 状态检查和仿真运行。"],
        ],
        [1.0, 2.25, 3.25],
        body_size=8.2,
    )


def section_data_ai(doc: Document, figs: dict[str, Path]) -> None:
    add_heading(doc, "4. 数据模型、AI 与知识增强", 1)
    add_picture(doc, figs["data"], "图 4  核心数据模型与状态流：草稿、反馈、合并请求和正式模型库之间的关系。")
    add_heading(doc, "4.1 核心数据表", 2)
    add_table(
        doc,
        ["数据表", "核心字段", "设计作用"],
        [
            ["documents / knowledge_chunks", "filename、content、chunk_index、keywords_json", "保存上传文档和 RAG 切片，为 AI 对话、建模和问答提供上下文。"],
            ["requirements", "id、name、description、type、priority、score、status", "保存结构化需求和人工确认状态，支持传统需求驱动建模链路。"],
            ["model_drafts", "project_name、original_json、current_json、status", "保存 AI 初稿和人工修正后的当前稿，是人机协同和入库审核的核心对象。"],
            ["model_feedback_logs", "draft_id、action、before_json、after_json、operator", "记录修改、采纳、拒绝和一键修复等反馈，形成可追踪闭环。"],
            ["merge_requests / merge_audit_logs", "candidate_json、release_snapshot_json、change_set_json、conflicts_json、resolutions_json", "保存设计师提交的合并请求、变更集、冲突和管理员审核记录。"],
            ["sysml_elements / sysml_relationships", "id、name、type、description、source、target、external_id、status", "正式模型库，用于发布分支、影响分析、MagicDraw 推送和仿真关联。"],
            ["change_scenarios / change_impact_reports", "target、attribute、old/new、risk_level、topology_json、matrix_json", "保存变更影响分析场景、拓扑、矩阵和建议。"],
            ["validation_reports / chat_logs", "score、issues_json、statistics_json、session_id、tool_calls_json", "保存模型预评审结果和智能体对话/工具调用过程。"],
        ],
        [1.55, 2.35, 2.6],
        body_size=8.1,
    )
    add_heading(doc, "4.2 AI 生成与 RAG 机制", 2)
    add_body(
        doc,
        "AI 层由 LLMService 和 RAGService 组成。LLMService 统一封装真实大模型 API 与 Mock 结果，支持聊天、需求分析、SysML 生成、影响分析和模型验证等任务。RAGService 负责文档切片、关键词抽取、知识库检索和上下文格式化，既可检索上传文档，也可检索模型图中的元素、关系和内置知识。"
    )
    for item in [
        "输入阶段：用户可通过对话文本和附件形成建模上下文，系统自动判断是普通问答、知识问答、需求分析、模型生成、影响分析、校验还是仿真任务。",
        "检索阶段：RAGService 根据查询词和模型上下文检索文档切片、模型元素、关系和内置 MBSE 知识，形成用于大模型提示词的上下文。",
        "生成阶段：ModelGenerationService 将对话摘要转化为 project_name、summary、assumptions、elements、relationships 和 sysml_text。",
        "规范化阶段：生成结果经过 ID、元素类型、关系类型、包路径、属性字段和 SysML textual view 规范化，避免 AI 直接输出不可入库结构。",
        "兜底阶段：当真实 LLM 不可用时，系统仍可通过本地规则和领域模板生成演示模型，保障平台可用性。",
    ]:
        add_bullet(doc, item)


def section_human_validation_merge(doc: Document, figs: dict[str, Path]) -> None:
    add_heading(doc, "5. 人机协同、预评审与合并入库", 1)
    add_heading(doc, "5.1 模型草稿闭环", 2)
    add_body(
        doc,
        "系统将 AI 生成结果保存为模型草稿，而不是直接写入正式库。model_drafts.original_json 保存 AI 原始输出，current_json 保存当前人工修正版本。前端对元素、关系、连线和文本的修改都会通过 sysml/drafts 接口写回 current_json，并在 model_feedback_logs 中记录 before/after。这样既能保留 AI 初稿，也能明确人工修改痕迹。"
    )
    add_callout(
        doc,
        "当前已解决的状态保持问题",
        "设计师发起合并请求后切到管理员账号审核，再返回设计师账号时，前端会依据本地 workbench 状态和后端 merge request 中的 draft_id 恢复草稿内容，避免只剩“入库管理”而丢失前面建模结果。",
        FILL_GREEN,
    )
    add_heading(doc, "5.2 模型预评审与一键修复", 2)
    add_body(
        doc,
        "DraftValidationService 提供确定性预评审能力，主要检查元素 ID 重复、空名称、非法元素类型、包路径不一致、候选状态未规范化、关系端点悬空、关系类型不合规以及部分工程属性缺少单位或值类型等问题。报告输出 score、conclusion、statistics 和 issues，前端展示问题列表、严重级别和可修复项。"
    )
    add_body(
        doc,
        "一键修复不是重新生成整套模型，而是基于 issue 中的 fix_action 对 current_json 做局部规范化，例如调整包路径、修正状态、补充关系、修复属性元数据等。修复完成后会重新渲染 sysml_text，并写入 feedback log。"
    )
    add_picture(doc, figs["screens2"], "图 5  闭环操作截图组：审核后入库、发布推送、推送成功、变更影响和 MagicDraw 回传。")
    add_heading(doc, "5.3 合并请求与管理员审核", 2)
    add_body(
        doc,
        "合并机制借鉴软件开发中的分支思路。设计师侧的模型草稿相当于 dev/designer 分支，正式模型库相当于 release/main 分支。提交合并请求时，MergeService 会读取 draft.current_json 作为 candidate_json，同时读取当前 sysml_elements/sysml_relationships 作为 release_snapshot_json，并自动计算 change_set 和 conflicts。"
    )
    add_picture(doc, figs["merge"], "图 6  设计师-管理员合并发布生命周期：预览推送与正式发布分离，正式入库必须经过管理员审核。")
    add_table(
        doc,
        ["状态", "触发操作", "业务含义"],
        [
            ["preview / revised", "生成草稿、人工修改、一键修复", "候选模型仍处于设计师工作区，可预览推送但不能正式发布。"],
            ["submitted", "设计师提交合并请求", "草稿进入待审核状态，管理员可查看变更集与冲突。"],
            ["conflict", "提交时发现同名或关键字段冲突", "管理员必须选择采用候选版本或保留发布版本。"],
            ["pending", "无冲突或冲突已全部解决", "满足合并条件，管理员可执行 merge。"],
            ["accepted / merged", "管理员合并入库", "候选模型写入正式 SysML 模型库，可执行发布推送。"],
            ["rejected", "设计师拒绝草稿或管理员拒绝 MR", "当前候选不再进入正式发布链路，需要重新生成或修正。"],
        ],
        [1.35, 1.95, 3.2],
        body_size=8.8,
    )


def section_external_deploy(doc: Document, figs: dict[str, Path]) -> None:
    add_heading(doc, "6. 外部工具、仿真与部署运行", 1)
    add_picture(doc, figs["external"], "图 7  外部工程工具集成拓扑：后端统一编排 LLM、SysML、MagicDraw、GMAT 和 Simulink。")
    add_heading(doc, "6.1 SysML 与 MagicDraw/Cameo 集成", 2)
    add_body(
        doc,
        "SysMLAdapter 负责正式模型入库。若配置了真实 SysML v2 API，系统会创建/查找项目并提交元素；若真实接口不可用，则在 SQLite 中保存 SysML 元素和关系，保证业务流程不断裂。MagicDrawAdapter 负责把模型转化为 ai-mbse.magicdraw.exchange.v1 交换载荷，包含 root_package、elements、relationships 和 diagram_layout。"
    )
    add_body(
        doc,
        "MagicDraw Bridge 是一个本地 Java 插件，在 MagicDraw/Cameo 进程内启动 127.0.0.1:7010 的 HTTP 服务，提供 /api/health、/api/models/import、/api/models/current 和 /api/project/save。导入时插件会创建或复用 Package、Block、Requirement、UseCase、Interface、Activity 和 Dependency，并按 diagram_layout 创建或更新图。"
    )
    add_callout(
        doc,
        "推送策略",
        "当前系统已将推送拆成两个阶段：预览推送在草稿生成后即可执行，默认写入 PREVIEW_ 项目包，用于设计师检查 MagicDraw 效果；发布推送必须在管理员合并入库后执行，写入正式包，避免未经审核的模型进入正式工程视图。",
        FILL_BLUE,
    )
    add_heading(doc, "6.2 GMAT 与 Simulink 仿真", 2)
    add_body(
        doc,
        "SimulationService 封装 GMAT 和 Simulink 两类工具。GMAT 通过 GmatConsole.exe 执行自动生成的轨道传播脚本，并解析轨道报告中的最终位置、速度、高度和周期等指标。Simulink 通过 MATLAB 命令行 -batch 模式运行；若未提供正式模型路径，系统会生成一阶动态响应演示模型，输出稳态值、峰值、超调量和调节时间。"
    )
    add_table(
        doc,
        ["工具", "配置项", "运行策略"],
        [
            ["LLM", "LLM_API_BASE_URL、LLM_API_KEY、LLM_MODEL_NAME、LLM_ENABLE_REAL_API", "真实 API 可用时调用大模型，不可用时使用 Mock 与规则兜底。"],
            ["SysML v2", "SYSML_API_BASE_URL、SYSML_API_TOKEN、SYSML_ENABLE_REAL_API、SYSML_PROJECT_NAME", "真实接口优先，失败后保存到 SQLite 正式模型库。"],
            ["MagicDraw", "MAGICDRAW_ENABLE_BRIDGE、MAGICDRAW_BRIDGE_URL、MAGICDRAW_PACKAGE_NAME、MAGICDRAW_EXPORT_DIR", "Bridge 在线时直接导入，不在线时生成本地交换包和 CSV/JSON 文件。"],
            ["GMAT", "GMAT_ENABLE_REAL、GMAT_CONSOLE_PATH、GMAT_ROOT_DIR、GMAT_WORK_DIR", "真实 GMAT 可用时执行脚本，否则返回工具不可用或演示状态。"],
            ["Simulink", "SIMULINK_ENABLE_REAL、SIMULINK_MATLAB_PATH、SIMULINK_MODEL_PATH、SIMULINK_WORK_DIR、SIMULINK_TIMEOUT_SEC", "真实 MATLAB/Simulink 可用时运行模型，无模型路径时生成 smoke simulation。"],
        ],
        [1.05, 2.8, 2.65],
        body_size=8.0,
    )
    add_heading(doc, "6.3 启动、重启与状态清理", 2)
    add_body(
        doc,
        "系统通过 scripts/run_backend.bat 和 scripts/run_frontend.bat 启动，默认前端访问地址为 http://localhost:5173，后端健康检查地址为 http://localhost:8000/api/health。当前版本新增后端启动清理策略：RESET_RUNTIME_STATE_ON_STARTUP 默认为 true，后端启动时会清空草稿、需求、聊天、校验、合并、正式模型和影响分析等运行态；RESET_KNOWLEDGE_ON_STARTUP 默认为 false，因此上传文档和知识切片默认保留。"
    )
    add_body(
        doc,
        "前端 App 会读取 health 接口返回的 backend_session_id。当检测到后端会话发生变化时，前端会清理以 ai-mbse-agent-workbench: 开头的 localStorage 工作台缓存，并回到登录/初始页面。这保证每次重启后，整套系统从“等待建模”的干净状态开始，同时不会误删用户选择保留的知识库。"
    )


def section_status_future(doc: Document) -> None:
    add_heading(doc, "7. 当前完成度、验证情况与后续演进", 1)
    add_heading(doc, "7.1 当前完成度", 2)
    add_table(
        doc,
        ["能力项", "当前状态", "说明"],
        [
            ["角色登录与页面权限", "已完成", "设计师进入 AI 工作台，管理员进入管理/审核视图；前端有页面权限控制。"],
            ["AI 对话与知识库", "已完成", "支持上传文档、知识摘要、RAG 检索和智能体工具过程展示。"],
            ["SysML 工程生成", "已完成", "支持从对话生成项目、元素、关系、SysML textual view 和画布布局。"],
            ["草稿编辑与反馈", "已完成", "支持元素/关系更新、新增/删除关系、采纳、拒绝、修正记录。"],
            ["预评审与一键修复", "已完成", "支持规则评分、问题列表和可修复问题自动修复。"],
            ["合并请求与管理员审核", "已完成", "支持 MR、变更集、冲突、解决策略、审核日志、合并和拒绝。"],
            ["预览推送与发布推送", "已完成", "预览推送生成后可用，发布推送要求合并入库。"],
            ["MagicDraw Bridge", "已完成", "本地插件提供 HTTP 服务，可导入模型、读取当前模型、保存工程。"],
            ["仿真接入", "已完成原型", "GMAT/Simulink 具备真实工具调用入口和演示兜底机制。"],
            ["重启清空运行态", "已完成", "后端启动清空运行态，前端感知 session 切换后清空工作台缓存。"],
        ],
        [1.65, 1.05, 3.8],
        body_size=8.4,
    )
    add_heading(doc, "7.2 已验证内容", 2)
    for item in [
        "前端生产构建已通过 tsc -b 与 vite build，说明当前 TypeScript 类型与打包流程无阻断错误。",
        "后端核心模块经过 Python 编译检查，路由、服务层和数据模型能够被解释器加载。",
        "健康检查能够返回 backend_session_id，并反映 LLM、SysML、MagicDraw、Simulation 和 SQLite 状态。",
        "模型草稿恢复、后端重启清空状态、预览推送/发布推送拆分、快捷按钮布局等近期问题已完成修正。",
    ]:
        add_bullet(doc, item)
    add_heading(doc, "7.3 后续演进建议", 2)
    add_table(
        doc,
        ["方向", "建议", "收益"],
        [
            ["工程化测试", "补充 API 级集成测试、草稿状态机测试、MergeService 冲突测试和 MagicDraw 交换包回归测试。", "降低后续功能迭代对核心闭环的回归风险。"],
            ["权限与审计", "从演示角色升级到真实账号、令牌认证、操作审计导出和权限策略配置。", "满足多人协同和工程环境上线要求。"],
            ["模型版本管理", "引入正式版本号、基线快照、差异对比和回滚机制。", "提升 release/main 模型库的可治理性。"],
            ["规则引擎", "将 DraftValidationService 的规则配置化，支持不同型号、领域和组织标准。", "让预评审从固定规则升级为可定制质量门禁。"],
            ["MagicDraw 双向同步", "扩展 current-model 读取后的差异合并和回写策略。", "支持工程师在 MagicDraw 中修改后同步回平台。"],
            ["仿真闭环", "将仿真指标与 SysML 参数、约束块和验证关系绑定。", "形成从需求、结构、行为到仿真结果的可追溯验证链。"],
        ],
        [1.1, 3.0, 2.4],
        body_size=8.4,
    )
    add_callout(
        doc,
        "总结",
        "当前系统已经具备完整的 AI-MBSE 原型闭环：需求/知识输入、AI 生成、人工确认、规则预评审、合并审核、正式入库、MagicDraw 同步和仿真接口。后续重点应从“演示可用”转向“工程可维护”，即加强测试、权限、版本、规则配置和双向同步能力。",
        FILL_GOLD,
    )


def appendix(doc: Document) -> None:
    add_heading(doc, "附录 A：项目目录与关键文件", 1)
    add_table(
        doc,
        ["目录/文件", "内容说明"],
        [
            ["backend/app/main.py", "FastAPI 应用入口、数据库初始化、后端启动清理和路由注册。"],
            ["backend/app/config.py", "环境变量配置，包括 LLM、SysML、MagicDraw、GMAT、Simulink 和重启清理策略。"],
            ["backend/app/models.py", "SQLAlchemy 数据模型，覆盖文档、知识、需求、草稿、反馈、合并、正式模型、校验、影响分析和聊天日志。"],
            ["backend/app/routers", "REST API 路由定义。"],
            ["backend/app/services", "核心业务服务层。"],
            ["frontend/src/App.tsx", "前端会话、角色、页面和后端 session 感知。"],
            ["frontend/src/pages/AgentWorkbench.tsx", "AI 工作台主实现。"],
            ["frontend/src/api/client.ts", "前端 API 封装。"],
            ["magicdraw-bridge-plugin/src/.../AiMbseBridgePlugin.java", "MagicDraw/Cameo 本地桥接插件。"],
            ["scripts/run_backend.bat / scripts/run_frontend.bat", "本地启动脚本。"],
        ],
        [2.45, 4.05],
        body_size=8.7,
    )
    add_heading(doc, "附录 B：核心接口清单", 1)
    add_table(
        doc,
        ["类别", "接口", "说明"],
        [
            ["健康检查", "GET /api/health", "返回服务状态和 backend_session_id。"],
            ["文档知识库", "POST /api/documents/upload\nGET /api/documents\nDELETE /api/documents/knowledge", "文档上传、列表和知识库清空。"],
            ["AI 对话", "POST /api/chat", "智能体对话与工具调用结果。"],
            ["SysML 草稿", "POST /api/sysml/generate-project\nGET /api/sysml/drafts/{id}\nPATCH /api/sysml/drafts/{id}/elements/{eid}\nPATCH /api/sysml/drafts/{id}/relationships/{rid}", "生成、读取和编辑模型草稿。"],
            ["预评审", "POST /api/sysml/drafts/{id}/validate\nPOST /api/sysml/drafts/{id}/fix", "草稿质量检查与一键修复。"],
            ["采纳拒绝", "POST /api/sysml/drafts/{id}/accept\nPOST /api/sysml/drafts/{id}/reject", "人工回路反馈。"],
            ["合并审核", "POST /api/merge/requests\nGET /api/merge/requests\nPOST /api/merge/requests/{id}/resolve\nPOST /api/merge/requests/{id}/merge\nPOST /api/merge/requests/{id}/reject", "提交 MR、查看列表、解决冲突、合并或拒绝。"],
            ["MagicDraw", "GET /api/magicdraw/status\nPOST /api/magicdraw/publish\nGET /api/magicdraw/current-model\nPOST /api/magicdraw/save", "Bridge 状态、推送模型、读取当前模型和保存工程。"],
            ["影响分析", "POST /api/impact/analyze\nPOST /api/impact/sandbox", "基于正式模型或沙箱变更做影响分析。"],
            ["仿真", "GET /api/simulation/status\nPOST /api/simulation/run", "工具状态与仿真运行。"],
        ],
        [1.0, 2.75, 2.75],
        body_size=7.8,
    )


def build() -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    figs = {
        "architecture": figure_architecture(),
        "workflow": figure_workflow(),
        "data": figure_data_model(),
        "merge": figure_merge_publish(),
        "external": figure_external_tools(),
        "screens1": figure_screenshot_sheet(
            "figure_06_screens_main.png",
            [
                ("登陆界面.bmp", "角色登录入口"),
                ("主界面.bmp", "AI 智能体主工作台"),
                ("人为回路确定.png", "人工回路确认"),
                ("校验.png", "模型预评审"),
                ("发起请求.bmp", "发起合并请求"),
                ("管理员审核.bmp", "管理员审核面板"),
            ],
        ),
        "screens2": figure_screenshot_sheet(
            "figure_07_screens_closed_loop.png",
            [
                ("审核后入库.bmp", "审核后入库"),
                ("发布推送.bmp", "发布推送"),
                ("推送成功.bmp", "推送成功反馈"),
                ("变更影响.bmp", "变更影响分析"),
                ("magic回传.bmp", "MagicDraw 回传"),
                ("Snipaste_2026-06-29_20-44-32.png", "MagicDraw 同步结果"),
            ],
        ),
    }

    doc = setup_document()
    set_header_footer(doc)
    title_page(doc)
    toc_page(doc)
    section_overview(doc, figs)
    doc.add_page_break()
    section_architecture(doc, figs)
    doc.add_page_break()
    section_frontend_backend(doc, figs)
    doc.add_page_break()
    section_data_ai(doc, figs)
    doc.add_page_break()
    section_human_validation_merge(doc, figs)
    doc.add_page_break()
    section_external_deploy(doc, figs)
    section_status_future(doc)
    doc.add_page_break()
    appendix(doc)
    doc.save(OUT)
    return OUT


if __name__ == "__main__":
    print(build())
