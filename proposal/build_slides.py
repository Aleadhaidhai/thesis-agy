"""开题报告答辩 PPT 自动生成脚本 → proposal/build/proposal_slides.pptx & proposal_slides_preview.pdf。

规格：16:9 宽屏（13.333 × 7.5 英寸），14 页结构化学术答辩幻灯片。
配色：中科大蓝学术风（主色 #003B73、强调蓝 #1B6CA8、青绿 #0F766E、灰卡 #F4F7FA）。
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from PIL import Image
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
BUILD = HERE / "build"
FIGS = HERE / "figs"
THESIS = ROOT / "thesis"

NAVY = RGBColor(0x00, 0x3B, 0x73)
BLUE = RGBColor(0x1B, 0x6C, 0xA8)
TEAL = RGBColor(0x0F, 0x76, 0x6E)
AMBER = RGBColor(0xB4, 0x53, 0x09)
CARD_BG = RGBColor(0xF4, 0xF7, 0xFA)
CARD_ALT = RGBColor(0xEC, 0xF3, 0xFA)
BORDER = RGBColor(0xD5, 0xDF, 0xEB)
TEXT_DARK = RGBColor(0x1E, 0x29, 0x3B)
TEXT_MUTED = RGBColor(0x52, 0x60, 0x6D)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
FONT_CN = "Hiragino Sans GB"
FONT_EN = "Arial"


def _set_run(r, size: float, bold: bool = False, color: RGBColor = TEXT_DARK, font: str = FONT_CN):
    r.font.name = font
    r.font.size = Pt(size)
    r.font.bold = bold
    r.font.color.rgb = color


def add_rect(slide, x, y, w, h, fill=CARD_BG, border=BORDER, radius=True, line_pt=1.0):
    shape_type = MSO_SHAPE.ROUNDED_RECTANGLE if radius else MSO_SHAPE.RECTANGLE
    sh = slide.shapes.add_shape(shape_type, Inches(x), Inches(y), Inches(w), Inches(h))
    if radius and len(sh.adjustments) > 0:
        sh.adjustments[0] = 0.04
    sh.fill.solid()
    sh.fill.fore_color.rgb = fill
    if border is not None:
        sh.line.color.rgb = border
        sh.line.width = Pt(line_pt)
    else:
        sh.line.fill.background()
    return sh


def add_textbox(slide, x, y, w, h, lines, size=13, color=TEXT_DARK, bold=False, align=PP_ALIGN.LEFT,
                line_spacing=1.22, space_after=4, anchor=MSO_ANCHOR.TOP):
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = Inches(0.06)
    tf.margin_top = tf.margin_bottom = Inches(0.04)
    if isinstance(lines, str):
        lines = [lines]
    for i, item in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.line_spacing = line_spacing
        p.space_after = Pt(space_after)
        if isinstance(item, tuple):
            head, body = item
            r1 = p.add_run()
            r1.text = head
            _set_run(r1, size, True, color)
            r2 = p.add_run()
            r2.text = body
            _set_run(r2, size, False, color)
        else:
            r = p.add_run()
            r.text = item
            _set_run(r, size, bold, color)
    return tb


def add_image_fit(slide, img_path: Path, x, y, w, h):
    iw, ih = Image.open(img_path).size
    ratio = min(w / iw, h / ih)
    nw, nh = iw * ratio, ih * ratio
    nx = x + (w - nw) / 2.0
    ny = y + (h - nh) / 2.0
    slide.shapes.add_picture(str(img_path), Inches(nx), Inches(ny), width=Inches(nw), height=Inches(nh))


def add_chrome(slide, section: str, title: str, page_no: int, total_pages: int = 14):
    # Top navy accent bar
    add_rect(slide, 0, 0, 13.333, 0.10, fill=NAVY, border=None, radius=False)
    # Section pill
    pill = add_rect(slide, 0.55, 0.28, 2.2, 0.34, fill=CARD_ALT, border=BLUE, radius=True, line_pt=0.8)
    pill_tf = pill.text_frame
    pill_tf.margin_left = pill_tf.margin_right = Inches(0.04)
    p = pill_tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    r = p.add_run(); r.text = section; _set_run(r, 11, True, NAVY)

    # Slide title
    add_textbox(slide, 2.9, 0.23, 9.8, 0.48, title, size=22, bold=True, color=NAVY, space_after=0)
    # Divider
    add_rect(slide, 0.55, 0.82, 12.233, 0.02, fill=BORDER, border=None, radius=False)

    # Footer
    add_rect(slide, 0.55, 7.08, 12.233, 0.015, fill=BORDER, border=None, radius=False)
    add_textbox(slide, 0.55, 7.12, 9.5, 0.28,
                "中国科学技术大学 · 专业硕士学位论文开题报告 | 面向企业即时通讯的多模态知识检索 Agent 系统",
                size=10, color=TEXT_MUTED, space_after=0)
    add_textbox(slide, 11.4, 7.12, 1.38, 0.28, f"{page_no} / {total_pages}",
                size=10, bold=True, color=NAVY, align=PP_ALIGN.RIGHT, space_after=0)


def add_card_header(slide, x, y, w, h, title: str, color: RGBColor = NAVY):
    hdr = add_rect(slide, x, y, w, h, fill=color, border=None, radius=True)
    tf = hdr.text_frame
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.LEFT
    r = p.add_run(); r.text = "  " + title; _set_run(r, 14, True, WHITE)


def style_table(table, col_widths, font_size=11.5):
    for j, cw in enumerate(col_widths):
        table.columns[j].width = Inches(cw)
    for i, row in enumerate(table.rows):
        for j, cell in enumerate(row.cells):
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            cell.margin_left = cell.margin_right = Inches(0.08)
            cell.margin_top = cell.margin_bottom = Inches(0.05)
            cell.fill.solid()
            cell.fill.fore_color.rgb = NAVY if i == 0 else (WHITE if i % 2 == 1 else CARD_BG)
            for p in cell.text_frame.paragraphs:
                p.alignment = PP_ALIGN.LEFT if j == 0 and i > 0 else PP_ALIGN.CENTER
                if i == 0:
                    p.alignment = PP_ALIGN.CENTER
                for r in p.runs:
                    _set_run(r, font_size, bold=(i == 0), color=(WHITE if i == 0 else TEXT_DARK))


def build():
    BUILD.mkdir(parents=True, exist_ok=True)
    meta = json.loads((THESIS / "meta.json").read_text())
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    blank = prs.slide_layouts[6]

    # ---------------- Slide 1: Cover ----------------
    s1 = prs.slides.add_slide(blank)
    add_rect(s1, 0, 0, 13.333, 7.5, fill=NAVY, border=None, radius=False)
    add_rect(s1, 0, 5.75, 13.333, 1.75, fill=RGBColor(0x00, 0x2B, 0x54), border=None, radius=False)
    add_rect(s1, 0.85, 1.05, 0.12, 3.85, fill=RGBColor(0x38, 0xBD, 0xF8), border=None, radius=False)

    add_textbox(s1, 1.25, 0.95, 10.5, 0.45,
                "中国科学技术大学  ·  专业硕士学位论文开题报告（电子信息）",
                size=16, bold=True, color=RGBColor(0xBA, 0xE6, 0xFD))
    add_textbox(s1, 1.25, 1.65, 11.2, 1.5,
                "面向企业即时通讯的\n多模态知识检索 Agent 系统设计与实现",
                size=34, bold=True, color=WHITE, line_spacing=1.28)
    add_textbox(s1, 1.25, 3.65, 11.0, 0.9,
                meta["title_en"], size=14, color=RGBColor(0xCB, 0xD5, 0xE1), line_spacing=1.25)

    add_textbox(s1, 1.25, 6.0, 10.8, 1.1,
                [
                    f"汇报人：{meta['author_cn']}    |    专业领域：{meta['major_cn']}    |    指导教师：{meta['supervisor_cn']}",
                    "汇报时间：2026 年 11 月    |    目标节点：2027 年 3 月预答辩 / 2027 年 5 月正式答辩",
                ],
                size=13, color=RGBColor(0xE2, 0xE8, 0xF0), line_spacing=1.4)

    # ---------------- Slide 2: Outline ----------------
    s2 = prs.slides.add_slide(blank)
    add_chrome(s2, "汇报目录", "汇报提纲与核心内容概览", 2)
    items = [
        ("01", "选题背景与研究意义", "企业 IM 碎片化、多模态分散与权限保密挑战"),
        ("02", "国内外研究现状与不足", "企业搜索、会话解缠、RAG、多模态检索与安全"),
        ("03", "研究目标与核心关键技术", "MKU 建模切分、ACL 混合检索、可控状态图 Agent"),
        ("04", "系统总体架构与部署设计", "七层解耦架构、IM 模拟器与单机私有化部署方案"),
        ("05", "数据保密与实验评测方案", "SimEIM 合成基准 + C-MTEB 公开基准四维验证"),
        ("06", "预期创新点与进度安排", "三大核心创新、可行性保障与 2026–2027 研究排期"),
    ]
    for idx, (num, tit, desc) in enumerate(items):
        col, row = idx % 3, idx // 3
        cx, cy = 0.65 + col * 4.15, 1.35 + row * 2.65
        add_rect(s2, cx, cy, 3.85, 2.30, fill=CARD_BG, border=BORDER)
        badge = add_rect(s2, cx + 0.25, cy + 0.25, 0.72, 0.55, fill=NAVY, border=None)
        p = badge.text_frame.paragraphs[0]; p.alignment = PP_ALIGN.CENTER
        r = p.add_run(); r.text = num; _set_run(r, 18, True, WHITE, FONT_EN)
        add_textbox(s2, cx + 0.22, cy + 0.95, 3.4, 0.45, tit, size=16, bold=True, color=NAVY)
        add_textbox(s2, cx + 0.22, cy + 1.42, 3.4, 0.75, desc, size=12.5, color=TEXT_MUTED, line_spacing=1.3)

    # ---------------- Slide 3: Background & Pain Points ----------------
    s3 = prs.slides.add_slide(blank)
    add_chrome(s3, "01 选题背景", "企业即时通讯中的知识痛点与“聊天即遗忘”难题", 3)

    add_rect(s3, 0.55, 1.08, 5.2, 5.75, fill=CARD_ALT, border=BLUE)
    add_card_header(s3, 0.55, 1.08, 5.2, 0.48, "典型企业 IM 知识流场景", NAVY)
    add_textbox(s3, 0.75, 1.72, 4.8, 4.9, [
        ("• 研发群故障排查：", "日志报错截图 + 讨论定位 + 参数变更结论"),
        ("• 产品与项目协作：", "PDF 规范、Word 需求文档与 Excel 排期表"),
        ("• 运维值班与通知：", "语音故障交接 + 制度条款动态更新修订"),
        ("• 高频隐性提问：", "口语化提问（“那发布窗口改成啥了？”）且常涉跨群多跳关联"),
        ("• 核心矛盾：", "知识高频产生于 IM，却因缺乏检索治理迅速沉没，员工反复人工爬楼询问。"),
    ], size=13.5, line_spacing=1.35, space_after=10)

    challenges = [
        ("痛点 1｜话题交织与语义碎片", "多讨论线程并发穿插闲聊；固定分块或时间切分极易割裂问答链路。", NAVY),
        ("痛点 2｜多模态脱离语境丢失语义", "截图错误码、Excel 指标与语音结论脱离发送前后讨论难以单独召回。", BLUE),
        ("痛点 3｜严格权限隔离与保密诉求", "管理群/项目群成员边界严格，事后裁剪易漏；商业机密严禁调外部云 API。", TEAL),
        ("痛点 4｜复杂问句与可溯源刚性要求", "存在“新结论覆盖旧结论”冲突，且回答必须逐句标注来源并核实原消息。", AMBER),
    ]
    for idx, (ct, cd, clr) in enumerate(challenges):
        cy = 1.08 + idx * 1.46
        add_rect(s3, 6.05, cy, 6.73, 1.32, fill=CARD_BG, border=BORDER)
        add_rect(s3, 6.05, cy, 0.12, 1.32, fill=clr, border=None, radius=False)
        add_textbox(s3, 6.32, cy + 0.12, 6.3, 0.36, ct, size=14.5, bold=True, color=clr, space_after=2)
        add_textbox(s3, 6.32, cy + 0.50, 6.3, 0.75, cd, size=12.5, color=TEXT_DARK, line_spacing=1.25)

    # ---------------- Slide 4: Literature Review & Gaps ----------------
    s4 = prs.slides.add_slide(blank)
    add_chrome(s4, "02 研究现状", "国内外研究现状与面向企业 IM 的现有不足", 4)
    quads = [
        ("企业搜索与会话解缠",
         "• Hawking 指出企业搜索存在异构、安全裁剪难题\n• Slack/Ubuntu IRC 解缠标注确立图划分与 1-1 指标\n• 局限：多作为孤立 NLP 任务，未衔接检索单元构建",
         0.55, 1.05, NAVY),
        ("检索增强生成（RAG）与混合检索",
         "• BGE-M3 支持单模型输出稠密+稀疏词汇权重\n• RRF + Cross-Encoder 重排提升多路融合精度\n• 局限：RAPTOR/GraphRAG 对高频增量聊天重建开销大",
         6.80, 1.05, BLUE),
        ("多模态信息检索",
         "• 解析转写路线：RapidOCR/MinerU + Qwen2.5-VL + FunASR\n• 端到端视觉路线：ColPali / VisRAG 页面多向量检索\n• 局限：端到端多向量显存要求高，难以单机私有化落地",
         0.55, 3.25, TEAL),
        ("检索智能体与隐私安全",
         "• Self-RAG / CRAG / Adaptive-RAG 引入反思与自适应路由\n• ALCE 建立引用率评测，强调检索环节必须执行 ACL 隔离\n• 局限：自由 ReAct 在本地小模型易漂移且缺句级伪引用校验",
         6.80, 3.25, AMBER),
    ]
    for qt, qd, qx, qy, clr in quads:
        add_rect(s4, qx, qy, 5.98, 2.02, fill=CARD_BG, border=BORDER)
        add_card_header(s4, qx, qy, 5.98, 0.42, qt, clr)
        add_textbox(s4, qx + 0.15, qy + 0.50, 5.68, 1.42, qd.split("\n"), size=12, line_spacing=1.32, space_after=4)

    add_rect(s4, 0.55, 5.45, 12.23, 1.40, fill=CARD_ALT, border=NAVY)
    add_textbox(s4, 0.78, 5.56, 11.8, 1.2, [
        ("核心研究缺口总结：", ""),
        "① 缺话题解缠与语境绑定知识单元  |  ② 缺低算力下的多模态+精确词项融合  |  ③ 缺向量层前置 ACL 隔离  |  ④ 缺受控规划与句级溯源",
    ], size=13, color=NAVY, line_spacing=1.4, space_after=6)

    # ---------------- Slide 5: Research Objectives & Content ----------------
    s5 = prs.slides.add_slide(blank)
    add_chrome(s5, "03 研究内容", "研究目标与四大核心研究内容", 5)

    add_rect(s5, 0.55, 1.02, 12.23, 0.90, fill=NAVY, border=None)
    add_textbox(s5, 0.80, 1.07, 11.75, 0.80,
                ("总体目标：", "围绕“数据不出域、16 GB 无独显单机可运行、答案严格权限可控且逐句可溯源”目标，设计并实现平台解耦的企业 IM 多模态知识检索 Agent 系统。"),
                size=12.5, color=WHITE, line_spacing=1.22, anchor=MSO_ANCHOR.MIDDLE)

    pillars = [
        ("内容一｜知识单元构建", [
            "• 5 类模态统一转写",
            "• 融合语义/结构/时间在线话题切分",
            "• 摘要增强会话单元与上下文注入附件单元",
            "• 基于活跃窗口回溯的增量更新",
        ], NAVY),
        ("内容二｜权限混合检索", [
            "• 稠密 + 稀疏词汇 + BM25 + 视觉四路召回",
            "• 加权 RRF + Cross-Encoder 重排",
            "• 指数时间衰减应对新旧结论更替",
            "• Milvus 数组 ACL 过滤下推 + 二次校验",
        ], BLUE),
        ("内容三｜状态图问答 Agent", [
            "• 查询理解（指代消解/子查询/约束）",
            "• 检索充分性自反思与迭代补检",
            "• 相关性拒答门限防“张冠李戴”",
            "• 批量句—证交叉重排校验与来源卡片",
        ], TEAL),
        ("内容四｜系统与评测验证", [
            "• IMAdapter 平台解耦接口 + IM 模拟器",
            "• FastAPI 后端与 Vue 3 管理后台",
            "• 构造保密脱敏模拟基准 SimEIM",
            "• 联合 C-MTEB 开展消融与并发压测",
        ], AMBER),
    ]
    for idx, (pt, pitems, clr) in enumerate(pillars):
        px = 0.55 + idx * 3.12
        add_rect(s5, px, 2.10, 2.88, 4.72, fill=CARD_BG, border=BORDER)
        add_card_header(s5, px, 2.10, 2.88, 0.48, pt, clr)
        add_textbox(s5, px + 0.14, 2.72, 2.60, 3.95, pitems, size=12.5, line_spacing=1.38, space_after=8)

    # ---------------- Slide 6: Key Tech 1 (MKU & Segmentation) ----------------
    s6 = prs.slides.add_slide(blank)
    add_chrome(s6, "04 关键技术一", "面向 IM 会话的多模态知识单元 MKU 构建与话题切分", 6)

    # Top left diagram
    add_rect(s6, 0.55, 1.05, 6.35, 2.25, fill=WHITE, border=BORDER)
    add_image_fit(s6, FIGS / "fig_mku.png", 0.65, 1.12, 6.15, 2.10)

    # Bottom left compact modality table
    tbl_shape = s6.shapes.add_table(6, 2, Inches(0.55), Inches(3.45), Inches(6.35), Inches(3.40))
    tbl = tbl_shape.table
    mod_rows = [
        ("模态", "统一解析转写与结构化策略"),
        ("图片", "RapidOCR 精确字符 + Qwen2.5-VL 语义描述互补拼接"),
        ("文档", "PDF 文本层抽取（少字页面回退 OCR）；Word/PPT 按层级分块"),
        ("表格", "每 15 行分块重复表头，行级序列化为“列名: 值”键值对"),
        ("语音", "独立子进程运行 FunASR（VAD + Paraformer + 标点恢复）"),
        ("文本", "保留原发言并识别“收到/+1”等低信息量短句防止噪声污染"),
    ]
    for r_i, (k, v) in enumerate(mod_rows):
        tbl.cell(r_i, 0).text = k
        tbl.cell(r_i, 1).text = v
    style_table(tbl, [1.05, 5.30], font_size=11)

    # Right panel: Formula + Dual MKU
    add_rect(s6, 7.15, 1.05, 5.63, 2.75, fill=CARD_ALT, border=BLUE)
    add_card_header(s6, 7.15, 1.05, 5.63, 0.44, "融合多线索在线话题切分", NAVY)
    add_textbox(s6, 7.35, 1.60, 5.23, 2.10, [
        ("亲和度打分：", "S(m,T) = α·Sim(m,T) + β·Rel(m,T) + γ·exp(-Δt/τ)"),
        ("• 语义项 Sim：", "BGE-M3 向量与 EMA 滑动话题质心余弦相似度"),
        ("• 结构项 Rel：", "显式回复 (1.0)、@ 提及 (0.6)、2 分钟同人连发 (0.5)"),
        ("• 增量窗口：", "仅回溯最近 6 小时活跃窗口，复杂度 O(n·|A|)"),
    ], size=12, line_spacing=1.32, space_after=5)

    add_rect(s6, 7.15, 3.98, 5.63, 2.87, fill=CARD_BG, border=BORDER)
    add_card_header(s6, 7.15, 3.98, 5.63, 0.44, "双重 MKU 建模与语义锚定", TEAL)
    add_textbox(s6, 7.35, 4.52, 5.23, 2.20, [
        ("• 会话单元（摘要增强）：", "按“[时间] 发言人: 内容”组织，≥3 条话题调用本地 LLM 生成标题/摘要/关键词前缀，显式化讨论结论"),
        ("• 附件单元（上下文注入）：", "单块注入来源群聊、发送人、时间、话题头及前后 2 条消息证据，解决附件脱离语境难题"),
        ("• 统一 ACL 继承：", "携带 conv:群组ID 主体标识，成员变更无需重建索引"),
    ], size=12, line_spacing=1.30, space_after=5)

    # ---------------- Slide 7: Key Tech 2 (Retrieval & ACL) ----------------
    s7 = prs.slides.add_slide(blank)
    add_chrome(s7, "04 关键技术二", "ACL 过滤下推的权限感知多路混合检索", 7)

    add_rect(s7, 0.55, 1.05, 5.75, 5.80, fill=WHITE, border=BORDER)
    add_image_fit(s7, FIGS / "fig_retrieval.png", 0.65, 1.15, 5.55, 5.60)

    boxes7 = [
        ("四路互补召回设计", [
            "• 稠密语义（BGE-M3）：捕获口语同义改写与语义相关性（Top-30）",
            "• 稀疏词项（BGE-M3 词汇权重 + jieba BM25）：稳健匹配错误码、IP 与接口名",
            "• 视觉补充（Chinese-CLIP）：设相似度门限 ≥0.40 过滤截图噪声，找图意图提权至 1.0",
        ], NAVY, 1.05, 1.98),
        ("加权 RRF 融合、交叉重排与时效衰减", [
            "• 加权 RRF 融合保留 Top-30 候选，消除各路打分尺度量纲差异",
            "• BGE-Reranker-v2-M3 对（查询, MKU）进行深层交互打分并归一化",
            "• 时效衰减 s = (1-μ)·s_rr + μ·0.5^(Δ/h)（μ=0.1, h=180 天），优先最新结论",
        ], BLUE, 3.18, 1.82),
        ("三道纵深权限防御体系", [
            "• 实时主体计算 P(u) → 向量库 array_contains_any(acl, P(u)) 过滤下推",
            "• 消除先 Top-K 再裁剪导致的低选择率召回空洞",
            "• RRF 融合后 SQLite 二次比对 ACL + 前端来源卡片跳转鉴权",
        ], TEAL, 5.15, 1.70),
    ]
    for bt, bitems, clr, by, bh in boxes7:
        add_rect(s7, 6.55, by, 6.23, bh, fill=CARD_BG, border=BORDER)
        add_card_header(s7, 6.55, by, 6.23, 0.40, bt, clr)
        add_textbox(s7, 6.72, by + 0.46, 5.90, bh - 0.52, bitems, size=11.8, line_spacing=1.26, space_after=4)

    # ---------------- Slide 8: Key Tech 3 (Agent & Verify) ----------------
    s8 = prs.slides.add_slide(blank)
    add_chrome(s8, "04 关键技术三", "受控状态图驱动的检索规划与句级引用校验", 8)

    add_rect(s8, 0.55, 1.05, 4.95, 5.80, fill=WHITE, border=BORDER)
    add_image_fit(s8, FIGS / "fig_agent.png", 0.65, 1.15, 4.75, 5.60)

    boxes8 = [
        ("1. 查询理解与思考模式控制", [
            "• 结合最近 8 条上下文消解指代，识别闲聊 / 澄清 / 找图 / 时间与群范围约束",
            "• 复杂/多跳问题拆分 1–3 个子查询；约束召回为空时自动回退无约束重检",
            "• 结构化规划节点关闭 Qwen3 思考模式（reasoning_effort=none）压缩延迟",
        ], NAVY, 1.05, 1.85),
        ("2. 充分性自反思与上下文重排", [
            "• 检查 Top-6 证据是否充足，不足时触发改写重检或同话题邻居扩展（至多 3 轮）",
            "• 将判定有用证据调至提示词首部，缓解“Lost in the Middle”长文本遗忘",
            "• 最高重排分 < 0.35 标记低置信度，提示模型谨慎表述",
        ], BLUE, 3.05, 1.85),
        ("3. 相关性拒答门限与批量句级引用校验", [
            "• 低于 0.05 分证据不进入生成；零有效命中直接安全拒答，阻断无权/缺失幻觉",
            "• 按句切分回答并批量调用重排器（score_pairs）检验句—证支撑度，剔除伪引用",
            "• 组装可点击来源卡片，支持一键切换群聊并高亮定位原始消息",
        ], TEAL, 5.05, 1.80),
    ]
    for bt, bitems, clr, by, bh in boxes8:
        add_rect(s8, 5.75, by, 7.03, bh, fill=CARD_BG, border=BORDER)
        add_card_header(s8, 5.75, by, 7.03, 0.40, bt, clr)
        add_textbox(s8, 5.92, by + 0.46, 6.70, bh - 0.52, bitems, size=11.8, line_spacing=1.26, space_after=4)

    # ---------------- Slide 9: Architecture & Deployment ----------------
    s9 = prs.slides.add_slide(blank)
    add_chrome(s9, "05 系统设计", "七层解耦总体架构与单机 / 生产部署形态", 9)

    add_rect(s9, 0.55, 1.05, 5.85, 5.80, fill=WHITE, border=BORDER)
    add_image_fit(s9, FIGS / "fig_arch.png", 0.65, 1.15, 5.65, 5.60)

    add_rect(s9, 6.60, 1.05, 6.18, 2.05, fill=CARD_ALT, border=BLUE)
    add_card_header(s9, 6.60, 1.05, 6.18, 0.42, "核心设计原则与解耦机制", NAVY)
    add_textbox(s9, 6.78, 1.54, 5.82, 1.48, [
        "• IMAdapter 抽象：屏蔽企业微信/飞书/自研模拟器差异",
        "• 异构索引同步：SQLite 事实源 + topic 级幂等替换 Milvus/BM25",
        "• 优雅降级：VLM 超时回退纯 OCR、CLIP 故障降级文本三路检索",
    ], size=12, line_spacing=1.32, space_after=4)

    t9_shape = s9.shapes.add_table(6, 3, Inches(6.60), Inches(3.28), Inches(6.18), Inches(3.57))
    t9 = t9_shape.table
    dep_rows = [
        ("组件层次", "单机轻量原型（16 GB 无独显）", "企业内网生产集群"),
        ("LLM / VLM", "Ollama：Qwen3-8B(Q4) / Qwen2.5-VL-3B", "vLLM 连续批处理：14B/32B"),
        ("嵌入与重排", "BGE-M3 + Reranker + CLIP（MPS FP16）", "独立 GPU 推理微服务"),
        ("OCR / ASR", "RapidOCR + FunASR（独立 CPU 子进程）", "容器化水平扩展服务"),
        ("数据存储", "Milvus Lite + SQLite + 内存 BM25", "Milvus 集群 + PG + ES"),
        ("前端与后台", "Vue 3 + Element Plus（零外部 CDN）", "内网反向代理 + 审计日志"),
    ]
    for r_i, row in enumerate(dep_rows):
        for c_i, val in enumerate(row):
            t9.cell(r_i, c_i).text = val
    style_table(t9, [1.28, 2.55, 2.35], font_size=10.5)

    # ---------------- Slide 10: SimEIM & Eval Plan ----------------
    s10 = prs.slides.add_slide(blank)
    add_chrome(s10, "05 评测方案", "数据脱敏策略、SimEIM 基准与四维实验设计", 10)

    add_rect(s10, 0.55, 1.05, 12.23, 1.85, fill=WHITE, border=BORDER)
    add_image_fit(s10, FIGS / "fig_simeim.png", 0.70, 1.12, 11.93, 1.70)

    add_rect(s10, 0.55, 3.05, 4.35, 3.80, fill=CARD_BG, border=BORDER)
    add_card_header(s10, 0.55, 3.05, 4.35, 0.42, "合规策略与混合基准设计", TEAL)
    add_textbox(s10, 0.72, 3.58, 4.00, 3.15, [
        ("• 企业保密约束：", "真实内部平台及对话严禁出域与论文公开披露"),
        ("• SimEIM 合成设计：", "虚构“云岚智能科技”（20 员工、10 群聊含 5 人高密管理群）；50 条事实种子 + 交织闲聊 + 24 个真附件"),
        ("• 信息隐藏原则：", "多模态事实仅存在于附件内部，强制评测解析通路"),
        ("• 公开基准互补：", "引入 C-MTEB T2Retrieval 验证万级规模多路召回"),
    ], size=11.8, line_spacing=1.30, space_after=5)

    t10_shape = s10.shapes.add_table(5, 3, Inches(5.10), Inches(3.05), Inches(7.68), Inches(3.80))
    t10 = t10_shape.table
    ev_rows = [
        ("评测层面", "对比基线与消融设置", "核心量化指标"),
        ("话题切分", "FixedWindow(10)、TimeGap(30m)；语义/结构/时间消融", "NMI、ARI、1-1、Exact-F1"),
        ("检索与构建", "BM25/Dense/RRF/Rerank；fixedwin/ocronly/nosummary/noctx", "Hit@K、Recall@10、MRR、nDCG"),
        ("端到端问答", "NaiveRAG、HybridRAG、Ours 及 understand/reflect/verify 消融", "Acc、KPR、CitP、拒答率、泄露率"),
        ("系统验收", "10 项全栈黑盒用例、分阶段计时、1–16 线程并发压测", "通过率、各阶段 ms、QPS、P95"),
    ]
    for r_i, row in enumerate(ev_rows):
        for c_i, val in enumerate(row):
            t10.cell(r_i, c_i).text = val
    style_table(t10, [1.45, 3.85, 2.38], font_size=10.8)

    # ---------------- Slide 11: Innovations ----------------
    s11 = prs.slides.add_slide(blank)
    add_chrome(s11, "06 特色创新", "拟突破的三项核心技术特色与创新点", 11)
    innovs = [
        ("创新点一", "面向 IM 交织流的双重 MKU 与话题解缠方法",
         "• 提出语义滑窗质心 + 回复/@ 结构 + 时间衰减在线话题切分\n"
         "• 提出“摘要增强会话单元 + 上下文注入附件单元”表示\n"
         "• 结合 OCR/VLM 互补与行级表格序列化消除多模态割裂",
         "解决群聊碎片化、短句无意义、附件脱离语境失真问题", NAVY),
        ("创新点二", "ACL 过滤下推的多路混合检索与纵深防御",
         "• 单机统筹 BGE-M3（稠密+稀疏）、BM25 与 Chinese-CLIP\n"
         "• 实时解析用户主体并将 ACL 条件直接下推至向量近似检索\n"
         "• 融合后 SQLite 二次校验与前端来源跳转鉴权闭环防护",
         "解决传统后置过滤召回空洞与企业敏感群越权泄露隐患", BLUE),
        ("创新点三", "受控状态图智能体与句级交叉编码校验机制",
         "• 用五节点可控状态图约束小参数模型行为，杜绝死循环\n"
         "• 引入思考模式预算控制、低分拒答门限与头部证据重排\n"
         "• 批量句—证交叉编码检验过滤伪引用，构建可点击来源卡片",
         "在无需微调前提下兼顾私有化小模型可信度与工程可控性", TEAL),
    ]
    for idx, (tag, title, bullets, effect, clr) in enumerate(innovs):
        ix = 0.55 + idx * 4.18
        add_rect(s11, ix, 1.12, 3.88, 5.72, fill=CARD_BG, border=BORDER)
        add_card_header(s11, ix, 1.12, 3.88, 0.50, tag, clr)
        add_textbox(s11, ix + 0.18, 1.75, 3.52, 0.72, title, size=15, bold=True, color=clr, line_spacing=1.25)
        add_textbox(s11, ix + 0.18, 2.58, 3.52, 2.75, bullets.split("\n"), size=12, line_spacing=1.35, space_after=6)
        add_rect(s11, ix + 0.18, 5.50, 3.52, 1.12, fill=WHITE, border=clr)
        add_textbox(s11, ix + 0.28, 5.60, 3.32, 0.92, ("预期成效：", effect), size=11.5, color=TEXT_DARK, line_spacing=1.28)

    # ---------------- Slide 12: Feasibility & Foundation ----------------
    s12 = prs.slides.add_slide(blank)
    add_chrome(s12, "07 基础与可行性", "研究基础与技术、算力及数据可行性分析", 12)

    feas = [
        ("技术生态可行", "LangGraph、Milvus Lite、Transformers 自定义 BGE-M3/Reranker、RapidOCR、FunASR 均为成熟开源组件，接口稳定可控。", NAVY),
        ("受限算力可行", "Apple M 系列 16 GB 统一内存环境：Qwen3-8B Q4 占约 5.2 GB，嵌入与重排采用 MPS FP16（重排提速约 3 倍），单机流畅运行。", BLUE),
        ("数据合规可行", "通过自研 IMAdapter 解耦企业平台，全程使用合成基准 SimEIM 与公开 T2Retrieval，严格做到零真实企业涉密数据接触。", TEAL),
    ]
    for idx, (ft, fd, clr) in enumerate(feas):
        fy = 1.12 + idx * 1.88
        add_rect(s12, 0.55, fy, 5.75, 1.68, fill=CARD_BG, border=BORDER)
        add_card_header(s12, 0.55, fy, 5.75, 0.40, ft, clr)
        add_textbox(s12, 0.72, fy + 0.48, 5.40, 1.10, fd, size=12, line_spacing=1.32)

    add_rect(s12, 6.55, 1.12, 6.23, 5.45, fill=WHITE, border=BORDER)
    add_card_header(s12, 6.55, 1.12, 6.23, 0.42, "前期原型预研基础（IM 模拟器与问答界面）", NAVY)
    thumb = THESIS / "figs" / "fig6_1_im_chat.png"
    if thumb.exists():
        add_image_fit(s12, thumb, 6.70, 1.65, 5.93, 4.15)
    add_textbox(s12, 6.72, 5.88, 5.90, 0.62,
                "已完成开源栈技术选型验证、IM 模拟器与后端存储骨架搭建，并确认无独显环境下模型加载与多模态解析流水线可端到端连通。",
                size=11.5, color=TEXT_MUTED, line_spacing=1.25)

    # ---------------- Slide 13: Schedule ----------------
    s13 = prs.slides.add_slide(blank)
    add_chrome(s13, "08 进度安排", "学位论文研究计划与关键时间节点（2026.07 – 2027.05）", 13)

    t13_shape = s13.shapes.add_table(7, 4, Inches(0.55), Inches(1.15), Inches(12.23), Inches(5.10))
    t13 = t13_shape.table
    sch_rows = [
        ("阶段", "时间周期", "核心研究与开发工作内容", "阶段里程碑"),
        ("阶段一", "2026.07 – 2026.08", "文献调研（企业搜索、RAG、多模态、解缠），明确功能/安全需求与技术路线", "文献综述与方案定型"),
        ("阶段二", "2026.09 – 2026.10", "实现多模态解析、在线话题切分与 MKU 构建；构建 SimEIM 数据集与问答标注", "入库链路与 SimEIM 基准"),
        ("阶段三", "2026.11 – 2026.12", "完成 ACL 混合检索、LangGraph 智能体与全栈 UI；开展对比、消融与压测实验", "系统原型与全量实验"),
        ("阶段四", "2027.01 – 2027.02", "整理实验图表，完成学位论文第 1–8 章及中英文摘要撰写与中科大格式排版", "论文初稿与成品 .docx"),
        ("阶段五", "2027.03（关键节点）", "参加专业硕士学位论文预答辩，梳理并落实评审专家修改意见", "通过论文预答辩"),
        ("阶段六", "2027.04 – 2027.05", "论文送审盲审、按评阅意见修订定稿，完成正式毕业答辩与档案提交", "完成正式答辩与归档"),
    ]
    for r_i, row in enumerate(sch_rows):
        for c_i, val in enumerate(row):
            t13.cell(r_i, c_i).text = val
    style_table(t13, [1.25, 2.25, 6.23, 2.50], font_size=11.5)
    # Highlight stage 5 row
    for c_i in range(4):
        cell = t13.cell(5, c_i)
        cell.fill.solid()
        cell.fill.fore_color.rgb = RGBColor(0xFE, 0xF3, 0xC7)
        for p in cell.text_frame.paragraphs:
            for r in p.runs:
                _set_run(r, 11.5, bold=True, color=AMBER)

    add_textbox(s13, 0.55, 6.40, 12.23, 0.50,
                "预期核心交付物：开源可本地部署 EIM-Agent 系统原型 + SimEIM 多模态评测基准 + 中科大规范硕士学位论文。",
                size=12.5, bold=True, color=NAVY)

    # ---------------- Slide 14: Closing ----------------
    s14 = prs.slides.add_slide(blank)
    add_rect(s14, 0, 0, 13.333, 7.5, fill=NAVY, border=None, radius=False)
    add_rect(s14, 2.5, 3.88, 8.333, 0.04, fill=RGBColor(0x38, 0xBD, 0xF8), border=None, radius=False)
    add_textbox(s14, 1.0, 2.15, 11.333, 1.2, "敬请各位评审专家批评指正！",
                size=34, bold=True, color=WHITE, align=PP_ALIGN.CENTER)
    add_textbox(s14, 1.0, 4.15, 11.333, 1.2,
                [
                    "面向对象：中国科学技术大学电子信息专业硕士学位论文开题答辩",
                    f"汇报人：{meta['author_cn']}    |    指导教师：{meta['supervisor_cn']}",
                ],
                size=14, color=RGBColor(0xCB, 0xD5, 0xE1), align=PP_ALIGN.CENTER, line_spacing=1.5)

    out_pptx = BUILD / "proposal_slides.pptx"
    prs.save(str(out_pptx))

    soffice = "/Applications/LibreOffice.app/Contents/MacOS/soffice"
    if Path(soffice).exists():
        prof = THESIS / "build" / "lo_profile"
        subprocess.run(
            [soffice, f"-env:UserInstallation=file://{prof}", "--headless", "--convert-to", "pdf",
             "--outdir", str(BUILD), str(out_pptx)],
            check=True,
            capture_output=True,
        )
        pdf_raw = BUILD / "proposal_slides.pdf"
        pdf_prev = BUILD / "proposal_slides_preview.pdf"
        if pdf_raw.exists():
            pdf_raw.replace(pdf_prev)
    print(f"saved {out_pptx} ({len(prs.slides)} slides)")


if __name__ == "__main__":
    build()
