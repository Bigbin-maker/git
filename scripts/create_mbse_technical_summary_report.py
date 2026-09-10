from __future__ import annotations

from datetime import date
from pathlib import Path
from textwrap import wrap

from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches, Pt, RGBColor
from PIL import Image, ImageDraw, ImageFont

from create_mbse_framework_doc import (
    BLUE,
    DARK_BLUE,
    GRAY,
    LIGHT_BLUE,
    LIGHT_GRAY,
    NAVY,
    add_body,
    add_callout,
    add_heading,
    add_rule,
    add_table,
    set_cell_text,
    set_run_font,
    set_table_geometry,
    setup_document,
    shade_cell,
)


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "AI_MBSE_系统建设技术总结报告.docx"
FIG_DIR = ROOT / "docs" / "figures_mbse_summary"

BG = "#F8FBFF"
BOX = "#FFFFFF"
BOX_BLUE = "#EAF3FF"
BOX_GREEN = "#ECFDF3"
BOX_GOLD = "#FFF7E6"
BOX_PURPLE = "#F4F0FF"
INK = "#172033"
MUTED = "#596579"
LINE = "#9AB2D0"
ACCENT = "#2563EB"
GREEN = "#16A34A"
GOLD = "#D97706"
RED = "#DC2626"


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = [
        r"C:\Windows\Fonts\msyhbd.ttc" if bold else r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\simhei.ttf",
        r"C:\Windows\Fonts\simsun.ttc",
    ]
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size=size)
    return ImageFont.load_default()


def draw_round_box(draw: ImageDraw.ImageDraw, xy, fill, outline=LINE, radius=18, width=2):
    draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=width)


def text_center(draw: ImageDraw.ImageDraw, box, text: str, size=28, fill=INK, bold=False, max_chars=12):
    f = font(size, bold)
    lines: list[str] = []
    for part in text.split("\n"):
        lines.extend(wrap(part, max_chars) or [""])
    heights = []
    widths = []
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=f)
        widths.append(bbox[2] - bbox[0])
        heights.append(bbox[3] - bbox[1])
    total_h = sum(heights) + max(0, len(lines) - 1) * 8
    x1, y1, x2, y2 = box
    y = y1 + (y2 - y1 - total_h) / 2
    for idx, line in enumerate(lines):
        draw.text((x1 + (x2 - x1 - widths[idx]) / 2, y), line, font=f, fill=fill)
        y += heights[idx] + 8


def arrow(draw: ImageDraw.ImageDraw, start, end, color=LINE, width=4):
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


def save_canvas(name: str, width=1600, height=900):
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (width, height), BG)
    return img, ImageDraw.Draw(img), FIG_DIR / name


def architecture_figure() -> Path:
    img, draw, path = save_canvas("figure_01_architecture.png", 1600, 960)
    draw.text((70, 48), "AI-MBSE 系统总体技术架构", font=font(40, True), fill=INK)
    draw.text((72, 102), "从设计师交互到知识增强、草稿闭环、模型入库与外部工具集成的分层结构", font=font(24), fill=MUTED)

    layers = [
        ("前端交互层", "项目工作区 / AI 智能体 / SysML textual view / 模型画布 / 预评审报告", BOX_BLUE),
        ("应用编排层", "FastAPI 路由 / API Client / 工作区状态 / 操作调度", BOX),
        ("AI 与知识增强层", "LLMService / RAGService / 文档切片 / 图谱与知识检索", BOX_GREEN),
        ("草稿与人为回路层", "model_drafts / 人工修改 / 采纳拒绝 / feedback logs", BOX_GOLD),
        ("建模与校验服务层", "ModelGeneration / DraftValidation / SysMLAdapter / MagicDraw Bridge", BOX_PURPLE),
        ("数据与外部工具层", "SQLite 模型库 / SysML v2 API / MagicDraw / 仿真工具", BOX),
    ]
    x1, x2 = 110, 1490
    y = 160
    boxes = []
    for title, desc, fill in layers:
        box = (x1, y, x2, y + 105)
        draw_round_box(draw, box, fill)
        draw.text((x1 + 32, y + 22), title, font=font(28, True), fill=NAVY)
        draw.text((x1 + 330, y + 28), desc, font=font(24), fill=INK)
        boxes.append(box)
        y += 122
    for idx in range(len(boxes) - 1):
        arrow(draw, ((x1 + x2) // 2, boxes[idx][3] + 2), ((x1 + x2) // 2, boxes[idx + 1][1] - 8), ACCENT, 4)
    img.save(path)
    return path


def workflow_figure() -> Path:
    img, draw, path = save_canvas("figure_02_workflow.png", 1680, 900)
    draw.text((70, 45), "端到端业务流程", font=font(40, True), fill=INK)
    draw.text((72, 98), "AI 生成候选方案，设计师确认与修复后才进入正式模型库", font=font(24), fill=MUTED)
    steps = [
        ("输入需求", "文本/附件/项目上下文"),
        ("RAG 增强", "文档片段与模型知识"),
        ("生成草稿", "元素/关系/SysML 文本"),
        ("人工修改", "元素与连接线修正"),
        ("预评审", "规则检查与报告"),
        ("一键修复", "规范化草稿"),
        ("采纳入库", "写入正式模型库"),
        ("工具同步", "MagicDraw/仿真/导出"),
    ]
    y = 285
    w, h, gap = 170, 116, 24
    x = 65
    for idx, (title, desc) in enumerate(steps):
        fill = [BOX_BLUE, BOX_GREEN, BOX_GOLD, BOX, BOX_PURPLE, BOX_GREEN, BOX_BLUE, BOX][idx]
        box = (x, y, x + w, y + h)
        draw_round_box(draw, box, fill, radius=16)
        text_center(draw, (x + 12, y + 16, x + w - 12, y + 62), title, size=25, bold=True, max_chars=7)
        text_center(draw, (x + 12, y + 62, x + w - 12, y + h - 12), desc, size=19, fill=MUTED, max_chars=8)
        if idx < len(steps) - 1:
            arrow(draw, (x + w + 4, y + h // 2), (x + w + gap - 6, y + h // 2), ACCENT, 4)
        x += w + gap
    # Feedback loop
    draw.arc((260, 450, 1180, 780), start=0, end=180, fill=GOLD, width=5)
    arrow(draw, (262, 615), (252, 612), GOLD, 4)
    draw.text((530, 700), "校验发现问题后回到草稿继续修正", font=font(25, True), fill=GOLD)
    img.save(path)
    return path


def dataflow_figure() -> Path:
    img, draw, path = save_canvas("figure_03_dataflow.png", 1600, 940)
    draw.text((70, 48), "草稿、反馈与模型库的数据流", font=font(40, True), fill=INK)
    draw.text((72, 102), "original_json 保存 AI 初稿，current_json 保存人工修正后的当前模型，采纳时才写入正式模型库", font=font(23), fill=MUTED)
    boxes = {
        "AI 生成结果\noriginal_json": (95, 240, 395, 360, BOX_GOLD),
        "当前草稿\ncurrent_json": (620, 240, 920, 360, BOX_BLUE),
        "反馈日志\nmodel_feedback_logs": (620, 500, 920, 620, BOX_GREEN),
        "正式模型库\nsysml_elements / relationships": (1135, 240, 1500, 360, BOX_PURPLE),
        "外部工具\nSysML API / MagicDraw": (1135, 500, 1500, 620, BOX),
    }
    for label, (x1, y1, x2, y2, fill) in boxes.items():
        draw_round_box(draw, (x1, y1, x2, y2), fill)
        text_center(draw, (x1 + 18, y1 + 16, x2 - 18, y2 - 16), label, size=24, bold=True, max_chars=15)
    arrow(draw, (395, 300), (620, 300), ACCENT, 5)
    draw.text((430, 260), "创建草稿", font=font(22), fill=MUTED)
    arrow(draw, (770, 360), (770, 500), GREEN, 5)
    draw.text((792, 420), "修改/采纳/修复\n都记录 before/after", font=font(21), fill=MUTED)
    arrow(draw, (920, 300), (1135, 300), ACCENT, 5)
    draw.text((965, 260), "采纳后入库", font=font(22), fill=MUTED)
    arrow(draw, (1318, 360), (1318, 500), ACCENT, 5)
    draw.text((1340, 420), "推送与交换", font=font(22), fill=MUTED)
    img.save(path)
    return path


def validation_figure() -> Path:
    img, draw, path = save_canvas("figure_04_validation.png", 1600, 920)
    draw.text((70, 48), "模型预评审与一键修复闭环", font=font(40, True), fill=INK)
    draw.text((72, 102), "确定性规则先发现问题，可修复项由 fixer 更新草稿并重新渲染 SysML 文本", font=font(23), fill=MUTED)
    center = (800, 470)
    nodes = [
        ("候选草稿", 800, 180, BOX_GOLD),
        ("规则校验", 1110, 350, BOX_PURPLE),
        ("预评审报告", 1110, 610, BOX_BLUE),
        ("一键修复", 800, 750, BOX_GREEN),
        ("人工确认", 490, 610, BOX),
        ("采纳入库", 490, 350, BOX_BLUE),
    ]
    for label, cx, cy, fill in nodes:
        box = (cx - 145, cy - 55, cx + 145, cy + 55)
        draw_round_box(draw, box, fill)
        text_center(draw, box, label, size=27, bold=True, max_chars=8)
    arrow(draw, (800, 235), (1048, 330), ACCENT, 5)
    arrow(draw, (1110, 405), (1110, 555), ACCENT, 5)
    arrow(draw, (1048, 640), (870, 725), GREEN, 5)
    arrow(draw, (730, 725), (560, 640), GREEN, 5)
    arrow(draw, (490, 555), (490, 405), GOLD, 5)
    arrow(draw, (560, 330), (730, 235), ACCENT, 5)
    draw.text((635, 450), "修复后回写 current_json\n并重算 SysML textual view", font=font(24, True), fill=GOLD)
    img.save(path)
    return path


def add_title_block(doc):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(6)
    p.paragraph_format.space_after = Pt(4)
    run = p.add_run("AI 赋能 MBSE 系统建设技术总结报告")
    set_run_font(run, 23, True, NAVY)

    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(12)
    run = p.add_run("面向人员权限、RAG 知识库、大模型交互、人为回路、自动化校验与模型入库的原型系统建设总结")
    set_run_font(run, 13.2, False, GRAY)

    meta = [
        ("报告类型", "技术总结报告"),
        ("系统对象", "AI-MBSE-Demo 原型系统"),
        ("总结范围", "总体框架、端到端流程、核心模块实现、数据闭环、校验修复机制与后续演进"),
        ("报告日期", date.today().isoformat()),
    ]
    table = doc.add_table(rows=len(meta), cols=2)
    table.style = "Table Grid"
    set_table_geometry(table, [1.35, 5.15])
    for idx, (label, value) in enumerate(meta):
        shade_cell(table.cell(idx, 0), LIGHT_GRAY)
        set_cell_text(table.cell(idx, 0), label, bold=True, color=NAVY)
        set_cell_text(table.cell(idx, 1), value)
    rule = doc.add_paragraph()
    rule.paragraph_format.space_before = Pt(8)
    add_rule(rule)


def add_figure(doc, image_path: Path, caption: str):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run()
    run.add_picture(str(image_path), width=Inches(6.5))
    cp = doc.add_paragraph()
    cp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    cp.paragraph_format.space_after = Pt(8)
    r = cp.add_run(caption)
    set_run_font(r, 9.5, False, GRAY)


def add_paragraphs(doc, paragraphs: list[str]):
    for text in paragraphs:
        add_body(doc, text)


def build_report():
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    figures = [
        architecture_figure(),
        workflow_figure(),
        dataflow_figure(),
        validation_figure(),
    ]

    doc = setup_document()
    add_title_block(doc)

    add_heading(doc, "摘要", 1)
    add_paragraphs(
        doc,
        [
            "本报告总结了 AI-MBSE-Demo 原型系统的建设过程和技术实现。该系统面向基于模型的系统工程设计活动，围绕“知识增强理解需求、AI 生成候选模型、设计师参与确认、系统自动校验修复、模型采纳入库、外部工具同步”的主线，构建了一套能够支撑低轨通信卫星等复杂系统建模场景的智能化 MBSE 工作台。",
            "在建设过程中，我没有把系统设计成一个单纯的大模型聊天界面，也没有让大模型直接决定最终模型结果，而是把大模型能力嵌入到可控的工程流程中。系统中所有 AI 生成结果首先进入草稿状态，设计师可以进行人工修改，系统可以执行预评审校验并给出一键修复建议，只有当设计师点击采纳后，当前草稿才进入正式模型库。这一设计使系统同时具备生成效率、人工可控性和工程可追溯性。",
            "目前系统已经形成较完整的原型闭环，包括人员与项目工作区、RAG 知识库构建、大模型问答与建模意图识别、SysML 候选模型生成、人工回路确认、自动化预评审校验、一键修复、模型入库、MagicDraw 同步和仿真入口等功能。本报告将从总体框架、业务流程、核心模块、数据流转、规则校验机制和后续演进方向几个方面进行总结。",
        ],
    )

    add_heading(doc, "1. 建设背景与目标", 1)
    add_paragraphs(
        doc,
        [
            "MBSE 建模过程通常包含需求澄清、系统边界识别、模块分解、接口定义、约束建模、模型评审、工具同步和仿真验证等环节。传统流程高度依赖工程师经验，模型构建和评审周期较长，且知识资料、设计对话、模型元素和评审反馈往往分散在不同工具和文档中。引入大模型之后，如果只是让模型回答问题或生成一段文本，无法真正嵌入系统工程流程；如果让模型直接生成并入库，又会带来模型质量不可控和责任边界不清的问题。",
            "基于这个背景，我把系统目标确定为“AI 辅助、人工确认、规则约束、模型闭环”。AI 的作用是提高需求理解、知识检索和候选建模效率；设计师的作用是进行工程判断和最终确认；规则引擎的作用是对模型进行稳定、可复现的预评审；模型库的作用是保存最终被确认的工程模型。通过这样的分工，系统既能体现大模型的智能化能力，又不破坏 MBSE 对一致性、可追溯性和规范性的要求。",
            "在技术实现上，我采用前后端分离方式组织系统。前端负责项目工作区、AI 智能体交互、模型预览、人工修改和报告展示；后端负责大模型调用、RAG 检索、SysML 模型生成、草稿管理、反馈日志、模型校验、一键修复和模型入库；数据库负责保存知识库、草稿、反馈和正式模型；外部接口负责连接 SysML v2 API、MagicDraw Bridge 和仿真工具链。",
        ],
    )

    add_heading(doc, "2. 总体技术架构", 1)
    add_paragraphs(
        doc,
        [
            "系统总体上可以划分为七个层次。最上层是前端交互层，包括项目管理侧栏、AI 智能体、知识库操作条、SysML textual view、模型画布、人工修改面板和预评审报告弹窗。这个层次直接面向设计师，负责承载从需求输入到模型确认的所有操作。",
            "第二层是应用编排层，它由前端 API client、FastAPI 路由和项目级工作区状态共同组成。它不直接处理复杂业务逻辑，而是把用户动作分发到聊天、文档、SysML、MagicDraw、仿真等服务中，并把结果重新组织成前端可以展示的状态。",
            "第三层是 AI 与知识增强层，包括 LLMService、RAGService、文档切片、轻量检索和模型图谱知识。该层负责把大模型的语言理解能力和知识库的资料检索能力结合起来，使系统能够回答专业问题，并为后续模型生成提供上下文支持。",
            "第四层是草稿与人为回路层，这是系统可控性的核心。所有 AI 生成结果都会进入 model_drafts 表，原始生成结果保存为 original_json，人工修改和一键修复后的当前版本保存为 current_json。设计师的修改、采纳、拒绝和修复动作都会写入 model_feedback_logs，从而形成可追溯的人机协同记录。",
            "第五层是建模与校验服务层，包括 ModelGenerationService、DraftValidationService 和 SysMLAdapter。ModelGenerationService 负责生成元素、关系和 SysML 文本；DraftValidationService 负责对草稿执行预评审规则和一键修复；SysMLAdapter 负责把被采纳的模型写入本地模型库或远程 SysML v2 项目。",
            "最底层是数据与外部工具层。SQLite 数据库保存文档、知识片段、草稿、反馈、正式模型元素和关系；SysML v2 API、MagicDraw Bridge 和仿真工具承担专业工程工具链集成。整体架构如下图所示。",
        ],
    )
    add_figure(doc, figures[0], "图 1  AI-MBSE 系统总体技术架构")

    add_heading(doc, "3. 端到端业务流程", 1)
    add_paragraphs(
        doc,
        [
            "系统运行时，设计师首先进入项目工作区。项目工作区是系统组织上下文的基本单位，同一个项目内会保存对应的聊天记录、知识问答过程、候选模型、人工修改结果、预评审报告、同步状态和仿真摘要。这样做的原因是 MBSE 工作天然围绕项目展开，如果所有对话和模型结果混在一起，后续很难追溯某个模型是基于哪一次需求、哪份文档和哪次人工修改形成的。",
            "在需求输入阶段，设计师可以直接在 AI 智能体中输入自然语言，也可以上传临时附件或知识库文档。临时附件只进入当前轮对话上下文，适合临时补充一段材料；知识库文档则会被解析、切片并长期保存，后续可以被 RAG 检索。系统通过这种区分避免了“所有上传都变成长期知识”的问题。",
            "当设计师提出普通问题时，系统可以直接调用大模型或结合知识库检索进行回答。当设计师明确要求生成、重建或完善 SysML 模型时，系统会识别建模意图，并将当前对话、附件摘要和必要知识上下文送入模型生成服务。模型生成服务输出结构化 elements、relationships 和 sysml_text，前端同时展示 textual view 和模型画布。",
            "生成结果不会直接进入模型库，而是作为候选草稿停留在预览与确认界面。设计师可以修改元素名称、类型、描述和包路径，也可以修改已有连接线、新增连接线或删除连接线。每一次修改都会更新 current_json，并重新渲染 SysML textual view，保证图、文本和结构化模型保持一致。",
            "在确认之前，设计师可以点击执行模型校验。系统根据内置规则生成《预评审报告》，指出错误、警告和提示，例如关系端点不存在、需求缺少 satisfy、接口缺少 allocate、属性未定义类型等。对可自动修复的问题，设计师可以点击一键修复，系统会更新草稿、重算 SysML 文本并记录修复反馈。只有当设计师点击采纳后，当前草稿才进入正式模型库，并可以继续推送 MagicDraw 或进入仿真流程。该流程如下图所示。",
        ],
    )
    add_figure(doc, figures[1], "图 2  从需求输入到模型入库和外部同步的端到端流程")

    add_heading(doc, "4. 核心模块建设总结", 1)
    add_heading(doc, "4.1 人员权限与项目工作区", 2)
    add_paragraphs(
        doc,
        [
            "人员权限与项目工作区是我最先搭建的基础能力之一。最初系统更像一个普通对话界面，但随着功能逐渐增加，单一对话已经无法承载 MBSE 场景中的项目边界。因此我把左侧“对话”概念调整为“项目”，让每个项目拥有独立的聊天、草稿、预评审报告和同步结果。",
            "在当前原型中，权限控制主要体现为项目级操作限制。例如系统内置的基线项目对普通设计师是受保护的，设计师可以新建自己的工作项目，但不能随意删除基线项目。虽然这还不是完整的后端权限体系，但它已经为后续接入真实用户表、角色表、项目授权表和审计日志预留了结构基础。",
            "这一模块的搭建顺序是先定义项目对象，再把前端工作区状态挂到项目 ID 上，最后把生成结果、MagicDraw 同步结果、预评审报告等状态都纳入项目级容器。这样设计的好处是后续无论扩展多少功能，都不会破坏项目隔离。",
        ],
    )

    add_heading(doc, "4.2 RAG 知识库构建", 2)
    add_paragraphs(
        doc,
        [
            "RAG 知识库模块解决的是大模型专业知识不足和回答依据不透明的问题。设计师在卫星通信、SysML 建模和系统工程场景中经常需要参考文献、标准、方案文档和已有模型资料。如果只依赖大模型自身知识，回答可能缺少依据；如果每次都把整篇文献塞进上下文，又会造成上下文过长和检索效率低的问题。",
            "我在实现时先建立 documents 表保存上传文档，再建立 knowledge_chunks 表保存切片结果。对于 PDF 文档，我接入 pypdf 进行正文抽取，解决了早期 PDF 上传后只有一个片段的问题。随后 RAGService 会根据用户问题检索文档片段、模型图谱和内置种子知识，并将结果组织为大模型可用的上下文。",
            "在前端，我专门把“上传临时附件”和“上传知识库”分开。临时附件只进入当前对话，不会污染长期知识库；知识库上传才会写入 documents 和 knowledge_chunks。系统还提供知识库状态展示和重置功能，设计师可以看到当前文档数和片段数，也可以在测试后手动清空知识库。",
        ],
    )

    add_heading(doc, "4.3 大模型交互与建模意图识别", 2)
    add_paragraphs(
        doc,
        [
            "大模型交互模块是系统的智能入口。我将其拆分为普通问答、知识库问答和建模意图识别几个部分。普通问答用于需求澄清和方案讨论，知识库问答用于结合上传文献进行专业回答，建模意图识别则用于判断用户输入是否应该触发 SysML 工程生成。",
            "在实现上，我封装了 LLMService，用统一配置管理模型 API 地址、模型名称、真实或 Mock 模式以及异常处理。前端通过 chat/stream 接口接收流式输出，使设计师可以看到回答逐步生成。为了避免误触发模型生成，我还加入了本地规则和大模型辅助分类结合的意图识别方式。",
            "这一模块的关键不是简单调用大模型，而是把大模型放到系统工作流中。它既要能回答“宽带载荷分系统有哪些需求和接口”这样的问题，也要能在用户明确要求生成方案时，把上下文组织成建模输入。后续如果继续增强，可以让大模型参与预评审解释、修复理由生成和反馈样本整理。",
        ],
    )

    add_heading(doc, "4.4 SysML 候选模型生成", 2)
    add_paragraphs(
        doc,
        [
            "SysML 生成模块是系统从问答走向工程建模的关键步骤。我没有让大模型只输出一段自然语言方案，而是要求它输出结构化模型，至少包含模型元素、模型关系和 SysML textual view。元素包括 Requirement、Block、UseCase、Activity、Interface 和 ConstraintBlock；关系包括 contains、satisfy、trace、refine、allocate、verify 等。",
            "生成服务的实现分为多层兜底。理想情况下，大模型返回可解析的结构化 JSON；如果模型输出不可解析，系统会根据输入文本动态抽取主题词生成模型；如果识别到典型领域，如卫星、雷达、飞机、车辆等，则使用更完整的领域模板生成候选模型。这样可以保证系统在大模型输出不稳定时仍然有可演示的结果。",
            "生成后的模型会立即渲染为 SysML textual view，同时在右侧模型画布中显示类似 MagicDraw 的需求图视图。此时生成结果只是候选草稿，保存到 model_drafts 中，而不会写入正式模型库。这个设计保证了 AI 输出可以被审查、修改和校验。",
        ],
    )

    add_heading(doc, "4.5 人为回路与反馈日志", 2)
    add_paragraphs(
        doc,
        [
            "人为回路是整个系统最重要的安全边界。AI 生成结果并不天然等于工程正确结果，因此我将模型生成后的状态定义为候选草稿。设计师可以对草稿进行元素编辑、连接线修改、新增连接线和删除连接线。每次修改都会作用于结构化模型本身，而不是只改变前端画布显示。",
            "为了支撑这个过程，我新增了 model_drafts 和 model_feedback_logs 两张表。model_drafts 中的 original_json 保存 AI 初稿，current_json 保存当前草稿；model_feedback_logs 记录每一次人为操作，包括 revise、add、delete、accept、reject 和 fix。日志中保存 before_json 和 after_json，因此后续可以追踪某个模型从 AI 初稿到最终采纳版本的变化过程。",
            "这个机制也为后续大模型微调提供了数据基础。采纳可以视为正反馈，拒绝可以视为负反馈，人工修改和一键修复可以视为偏好修正样本。相比只记录最终模型，记录修改过程更有价值，因为它体现了设计师希望模型如何从“不规范”变为“规范”。",
        ],
    )

    add_figure(doc, figures[2], "图 3  草稿、反馈日志与正式模型库之间的数据流")

    add_heading(doc, "4.6 模型预评审与智能化校验", 2)
    add_paragraphs(
        doc,
        [
            "模型预评审模块是在人为确认基础上进一步增加的质量保障机制。我的设计思路是：校验不应该完全依赖大模型主观判断，而应该先由确定性规则引擎完成稳定检查，再由大模型在后续阶段承担解释、补充建议和复杂修复辅助。这样可以保证同一个草稿在同一套规则下得到一致的校验结果。",
            "当前 DraftValidationService 会直接读取 model_drafts.current_json，对候选草稿执行规则检查。检查内容包括关系端点是否存在、关系类型是否合法、元素包路径是否与类型匹配、需求是否被 Block satisfy、接口是否 allocate 到模块、约束是否 verify 需求、元素是否仍为 candidate 状态、SysML 文本是否与结构化模型同步，以及功率、带宽、频率、时延等工程属性是否缺少类型定义。",
            "校验结果以《预评审报告》的形式返回。报告中包含评分、结论、错误/警告/提示统计、问题列表、规则 ID、对象 ID、问题描述、修复建议以及是否支持自动修复。对可自动修复的问题，我为其绑定 fix_action，例如 normalize_package、normalize_status、add_relationship、set_attribute_type 和 rerender_sysml_text。设计师点击一键修复后，系统会更新 current_json、重新渲染 SysML textual view，并写入 action=fix 的反馈日志。",
        ],
    )
    add_figure(doc, figures[3], "图 4  模型预评审与一键修复闭环")

    add_heading(doc, "4.7 模型入库、MagicDraw 同步与仿真入口", 2)
    add_paragraphs(
        doc,
        [
            "模型入库是候选草稿转为正式模型的边界动作。设计师点击采纳后，系统不会使用 AI 原始生成结果入库，而是使用 current_json，也就是经过人工修改和预评审修复后的当前草稿。后端通过 SysMLAdapter.commit_model 将元素写入 sysml_elements，将关系写入 sysml_relationships。如果配置了真实 SysML v2 API，系统会优先向远程项目创建提交；如果真实 API 不可用，则降级到本地 SQLite 保存。",
            "MagicDraw 同步位于采纳之后。这样设计的原因是 MagicDraw 属于专业建模工具，如果未确认的候选方案直接推送，会把不可靠模型带入外部工具链。当前系统在前端限制未采纳草稿不能推送 MagicDraw，采纳后才允许生成交换包或调用 MagicDraw Bridge。",
            "仿真入口目前作为后续扩展点保留。系统已经具备统一的 simulation/run 接口，可以根据模型 ID 调用 Mock 仿真或外部仿真工具。未来可以把仿真结果反向写入模型约束和验证报告中，形成设计、建模、校验、仿真和反馈的完整闭环。",
        ],
    )

    add_heading(doc, "5. 关键技术产物与数据表", 1)
    add_paragraphs(
        doc,
        [
            "系统的关键技术产物不是单一页面或单一接口，而是一组围绕模型生命周期组织起来的数据对象。知识库文档通过 documents 和 knowledge_chunks 保存；AI 生成模型通过 model_drafts 保存；设计师和系统的修改过程通过 model_feedback_logs 保存；正式采纳后的模型通过 sysml_elements 和 sysml_relationships 保存。",
            "这种数据拆分使系统能够明确区分“知识资料”“候选草稿”“人工反馈”和“正式模型”。如果没有这种边界，系统很容易出现 AI 生成结果、用户修改结果和正式模型混在一起的问题。当前设计虽然仍然是原型级实现，但已经具备后续扩展版本管理、审批流、模型差异对比和微调数据导出的基础。",
        ],
    )
    add_table(
        doc,
        ["数据对象", "保存位置", "技术含义"],
        [
            ["知识库文档", "documents / knowledge_chunks", "保存上传文档和切片，支撑 RAG 检索。"],
            ["候选草稿", "model_drafts.original_json", "保存 AI 初始生成结果，用于追溯 AI 原始输出。"],
            ["当前草稿", "model_drafts.current_json", "保存人工修改和一键修复后的当前版本，采纳时使用它入库。"],
            ["反馈日志", "model_feedback_logs", "保存采纳、拒绝、修改、修复的 before/after 数据。"],
            ["正式元素", "sysml_elements", "保存已采纳模型元素，构成正式模型库。"],
            ["正式关系", "sysml_relationships", "保存已采纳模型关系，支持模型图谱和同步。"],
            ["预评审结果", "validate/fix 接口即时返回", "面向草稿阶段的质量检查和修复结果。"],
        ],
        [1.45, 2.05, 3.0],
        LIGHT_BLUE,
    )

    add_heading(doc, "6. 系统搭建中的技术判断", 1)
    add_paragraphs(
        doc,
        [
            "第一，我选择让生成结果先进入草稿而不是直接入库。这是因为 MBSE 模型具有工程约束和责任边界，大模型生成结果必须经过设计师确认。通过草稿机制，系统既保留 AI 生成效率，又避免不可靠结果污染正式模型库。",
            "第二，我选择把临时附件和知识库上传分开。临时附件适合当前对话使用，知识库文档适合长期检索。如果不做区分，用户随手上传的材料会进入长期知识库，影响后续问答质量。",
            "第三，我选择先做确定性预评审规则，再考虑大模型辅助评审。确定性规则可以保证稳定性和可复现性，大模型可以在此基础上负责解释和生成更自然的修复建议。",
            "第四，我把人工修改设计为结构化模型修改，而不是前端图形拖拽。只有结构化数据发生变化，SysML textual view、模型画布、预评审报告和最终入库结果才能保持一致。",
            "第五，我保留了反馈日志的 before/after 数据。这不仅用于审计，也为后续大模型微调提供了高质量样本。相比只知道最终答案，模型更需要知道工程师如何修改 AI 结果，以及为什么修改。",
        ],
    )

    add_heading(doc, "7. 当前系统状态与不足", 1)
    add_paragraphs(
        doc,
        [
            "从功能闭环看，当前系统已经覆盖了从知识库构建、大模型问答、候选模型生成、人工修改、预评审校验、一键修复、采纳入库到 MagicDraw 同步的主要路径。设计师可以围绕一个项目持续开展需求理解、模型构建和质量检查，系统也能记录关键反馈。",
            "从工程成熟度看，当前系统仍属于原型阶段。权限管理主要在前端体现，后端还需要真实用户、角色和授权表；RAG 检索目前是轻量实现，后续应升级为向量数据库和 rerank；预评审规则已经覆盖基础规范，但还需要配置化和项目级规则集；模型库目前还缺少独立管理页面；MagicDraw 同步和外部仿真也需要进一步加强双向数据流。",
            "这些不足并不影响当前系统作为研究原型和演示平台的价值，反而为后续工程化演进提供了清晰路线。下一阶段的重点应放在模型库可视化管理、权限后端化、RAG 召回率评测、预评审规则扩展和反馈数据导出上。",
        ],
    )

    add_heading(doc, "8. 后续演进方向", 1)
    add_paragraphs(
        doc,
        [
            "后续我建议首先建设模型库管理页面。当前模型已经写入 sysml_elements 和 sysml_relationships，但用户还缺少一个可视化入口查看已采纳模型、版本、关系图和采纳记录。模型库页面可以成为连接草稿、正式模型、MagicDraw 同步和仿真结果的中心。",
            "其次，应升级 RAG 能力。当前知识库已经能完成文档上传、切片和检索，但如果要支撑更大规模文献和工程资料，需要引入向量数据库、rerank 模型、文档级权限和召回率评测。特别是在卫星通信和系统工程领域，检索质量会直接影响大模型回答和模型生成质量。",
            "第三，应把预评审规则配置化。不同项目、不同专业和不同建模规范对模型质量的要求并不完全相同。规则配置化之后，管理员可以为项目启用不同规则集，设计师也可以根据评审阶段选择严格模式或宽松模式。",
            "第四，应利用反馈日志进行模型优化。当前系统已经记录了采纳、拒绝、人工修改和一键修复的 before/after 数据。后续可以把这些数据整理成训练样本，用于优化模型生成提示词、微调领域模型，或者训练一个专门的模型修复助手。",
        ],
    )

    add_heading(doc, "结论", 1)
    add_paragraphs(
        doc,
        [
            "本系统的建设重点不是单纯展示大模型能力，而是把大模型嵌入 MBSE 工程流程，形成一个可控、可追溯、可评审、可入库的智能化建模闭环。通过人员项目管理、RAG 知识增强、大模型交互、SysML 候选生成、人为回路、预评审校验、一键修复和模型入库，系统初步实现了从自然语言需求到结构化工程模型的转化。",
            "从技术路线看，该系统采用了“AI 生成候选、人工确认边界、规则保障质量、反馈沉淀数据”的模式。这种模式适合复杂工程场景，因为它不会把大模型视为完全自动的决策者，而是把它作为系统工程师的智能助手。设计师仍然掌握最终确认权，系统则负责提高效率、提供知识支持、发现规范问题并沉淀反馈经验。",
            "因此，当前 AI-MBSE-Demo 原型已经具备进一步工程化和研究深化的基础。后续只要继续完善权限、模型库、RAG 检索、规则配置和外部工具双向同步，就可以逐步从演示原型发展为面向真实 MBSE 工作流的智能建模平台。",
        ],
    )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    doc.save(OUT)
    return OUT


if __name__ == "__main__":
    print(build_report())
