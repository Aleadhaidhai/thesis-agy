"""论文 Word 文档生成脚本：Markdown 源稿 → 符合《中国科学技术大学研究生学位论文撰写手册》格式的 .docx。

流程：
1. 预处理：合并各章；[@KEY] 引用按首次出现顺序编号（GB/T 7714 顺序编码制，上标，连续编号合并为 [1-3]）；
   mermaid 代码块渲染为 PNG；公式编号 \\tag{} 转为占位标记。
2. pandoc 转换为 docx（公式转为 Word 原生公式）。
3. python-docx 后处理：页面设置、各级标题/正文/图表题/参考文献样式、三线表、公式编号、
   封面、原创性声明、摘要、目录域、分节与页眉页脚（罗马/阿拉伯页码）。

用法：python build_docx.py  → thesis/build/thesis.docx
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
import subprocess
from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK, WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt

HERE = Path(__file__).resolve().parent
BUILD = HERE / "build"
FIGS = BUILD / "figs"
CHAPTERS = ["ch1", "ch2", "ch3", "ch4", "ch5", "ch6", "ch7", "ch8"]

SONG, HEI, FANGSONG, TNR, ARIAL = "宋体", "黑体", "仿宋", "Times New Roman", "Arial"
MNS = "{http://schemas.openxmlformats.org/officeDocument/2006/math}"


# ============================================================ 参考文献
def load_refs() -> dict[str, str]:
    refs = {}
    src = (HERE / "references.md")
    if not src.exists():
        src = HERE / "references_candidates.md"
    for line in src.read_text().splitlines():
        m = re.match(r"^\[([A-Z]\d+)\]\s*(.+?)(?:｜|$)", line.strip())
        if m:
            refs[m.group(1)] = m.group(2).strip()
    return refs


def process_citations(text: str, refs: dict[str, str]) -> tuple[str, list[str]]:
    order: list[str] = []

    def num(k):
        if k not in order:
            order.append(k)
        return order.index(k) + 1

    def fmt(nums):
        nums = sorted(set(nums))
        parts, i = [], 0
        while i < len(nums):
            j = i
            while j + 1 < len(nums) and nums[j + 1] == nums[j] + 1:
                j += 1
            parts.append(str(nums[i]) if j == i else (f"{nums[i]},{nums[j]}" if j == i + 1 else f"{nums[i]}-{nums[j]}"))
            i = j + 1
        return "^\\[" + ",".join(parts) + "\\]^"   # 转义方括号，避免被 pandoc 解析为脚注

    def repl(m):
        keys = re.findall(r"\[@([A-Z]\d+)\]", m.group(0))
        missing = [k for k in keys if k not in refs]
        if missing:
            print("WARNING missing refs:", missing)
        return fmt([num(k) for k in keys])

    text = re.sub(r"(?:\[@[A-Z]\d+\])+", repl, text)
    return text, order


# ============================================================ 预处理
def render_mermaid(code: str) -> Path:
    FIGS.mkdir(parents=True, exist_ok=True)
    h = hashlib.md5(code.encode()).hexdigest()[:10]
    out = FIGS / f"mmd_{h}.png"
    if not out.exists():
        src = FIGS / f"mmd_{h}.mmd"
        src.write_text(code)
        cfg = FIGS / "mmd_config.json"
        cfg.write_text(json.dumps({"theme": "neutral", "themeVariables": {"fontFamily": "PingFang SC, Hiragino Sans GB, sans-serif", "fontSize": "15px"}}))
        subprocess.run([str(HERE / "node_modules/.bin/mmdc"), "-i", str(src), "-o", str(out), "-p",
                        str(HERE / "puppeteer.json"), "-c", str(cfg), "-s", "3", "-b", "white"],
                       check=True, capture_output=True)
    return out


def preprocess(md: str) -> str:
    md = re.sub(r"```mermaid\n(.*?)```", lambda m: f"![]({render_mermaid(m.group(1))})", md, flags=re.S)
    # 公式编号：$$ ... \tag{2.1} $$ → $$ ... $$ + 占位，后处理时转为右对齐编号
    md = re.sub(r"\$\$(.+?)\\tag\{([\d.]+)\}\s*\$\$", lambda m: f"$${m.group(1).strip()}$$EQNO{m.group(2)}EQNO",
                md, flags=re.S)
    return md


# ============================================================ 样式工具
def set_font(run_or_style, east=SONG, west=TNR, size=None, bold=None):
    f = run_or_style.font
    f.name = west
    if size is not None:
        f.size = Pt(size)
    if bold is not None:
        f.bold = bold
    el = run_or_style.element if hasattr(run_or_style, "element") else run_or_style._element
    rpr = el.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.append(rfonts)
    for a in ("w:ascii", "w:hAnsi", "w:cs"):
        rfonts.set(qn(a), west)
    rfonts.set(qn("w:eastAsia"), east)
    for a in ("w:asciiTheme", "w:hAnsiTheme", "w:eastAsiaTheme", "w:cstheme"):
        if rfonts.get(qn(a)) is not None:
            del rfonts.attrib[qn(a)]


def para_fmt(p, align=None, before=0, after=0, line=None, exact=True, first_indent=None, left_indent=None,
             keep_next=False):
    pf = p.paragraph_format
    if align is not None:
        pf.alignment = align
    pf.space_before = Pt(before)
    pf.space_after = Pt(after)
    if line is None:
        pf.line_spacing_rule = WD_LINE_SPACING.SINGLE
    elif exact:
        pf.line_spacing_rule = WD_LINE_SPACING.EXACTLY
        pf.line_spacing = Pt(line)
    else:
        pf.line_spacing = Pt(line)
    if first_indent is not None:
        pf.first_line_indent = first_indent
    if left_indent is not None:
        pf.left_indent = left_indent
    pf.keep_with_next = keep_next


def style_runs(p, east=SONG, west=TNR, size=12, bold=None):
    from docx.shared import RGBColor
    for r in p.runs:
        set_font(r, east, west, size, bold)
        r.font.color.rgb = RGBColor(0, 0, 0)
        r.font.italic = False if r.font.italic and not r.font.superscript else r.font.italic


def add_field(p, instr: str, placeholder: str = ""):
    r = p.add_run()
    b = OxmlElement("w:fldChar"); b.set(qn("w:fldCharType"), "begin"); r._r.append(b)
    r2 = p.add_run()
    it = OxmlElement("w:instrText"); it.set(qn("xml:space"), "preserve"); it.text = instr; r2._r.append(it)
    r3 = p.add_run()
    s = OxmlElement("w:fldChar"); s.set(qn("w:fldCharType"), "separate"); r3._r.append(s)
    r4 = p.add_run(placeholder)
    r5 = p.add_run()
    e = OxmlElement("w:fldChar"); e.set(qn("w:fldCharType"), "end"); r5._r.append(e)
    return [r, r2, r3, r4, r5]


def set_cell_border(cell, **kw):
    tcPr = cell._tc.get_or_add_tcPr()
    borders = tcPr.find(qn("w:tcBorders"))
    if borders is None:
        borders = OxmlElement("w:tcBorders")
        tcPr.append(borders)
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        v = kw.get(edge)
        el = borders.find(qn(f"w:{edge}"))
        if el is None:
            el = OxmlElement(f"w:{edge}")
            borders.append(el)
        if v:
            el.set(qn("w:val"), "single"); el.set(qn("w:sz"), str(v)); el.set(qn("w:color"), "000000")
        else:
            el.set(qn("w:val"), "nil")


# ============================================================ 后处理
CH_RE = re.compile(r"^第\d+章")
FIG_RE = re.compile(r"^图\s?\d+\.\d+")
TAB_RE = re.compile(r"^表\s?\d+\.\d+")
UNNUMBERED = {"摘要", "摘　要", "Abstract", "ABSTRACT", "目录", "目　录", "参考文献", "致谢", "致　谢", "附录",
              "在读期间发表的学术论文与取得的其他研究成果"}


def three_line(table):
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    tbl = table._tbl
    tblPr = tbl.tblPr
    for el in tblPr.findall(qn("w:tblStyle")):
        tblPr.remove(el)
    for el in tblPr.findall(qn("w:tblW")):
        tblPr.remove(el)
    tw = OxmlElement("w:tblW"); tw.set(qn("w:w"), "5000"); tw.set(qn("w:type"), "pct"); tblPr.append(tw)
    nrows = len(table.rows)
    for i, row in enumerate(table.rows):
        trPr = row._tr.get_or_add_trPr()
        trPr.append(OxmlElement("w:cantSplit"))
        if i == 0:
            trPr.append(OxmlElement("w:tblHeader"))
        for cell in row.cells:
            set_cell_border(cell, top=12 if i == 0 else (6 if i == 1 else None),
                            bottom=12 if i == nrows - 1 else (6 if i == 0 else None))
            for p in cell.paragraphs:
                para_fmt(p, align=WD_ALIGN_PARAGRAPH.CENTER, line=None)
                p.paragraph_format.first_line_indent = Pt(0)
                style_runs(p, SONG, TNR, 10.5, bold=True if i == 0 else None)


def postprocess(doc: Document, meta: dict):
    # ---------- 页面设置 ----------
    for s in doc.sections:
        s.page_height, s.page_width = Cm(29.7), Cm(21.0)
        s.top_margin = s.bottom_margin = Cm(2.54)
        s.left_margin = s.right_margin = Cm(3.17)
        s.header_distance, s.footer_distance = Cm(1.5), Cm(1.75)
        s.gutter = Cm(0)

    # ---------- 正文默认样式 ----------
    st = doc.styles["Normal"]
    set_font(st, SONG, TNR, 12)
    for name in ("Body Text", "First Paragraph", "Compact"):
        if name in [s.name for s in doc.styles]:
            set_font(doc.styles[name], SONG, TNR, 12)

    # pandoc 会把行间公式与其后的编号占位拆成两个段落：把编号并回公式段落
    for p in list(doc.paragraphs):
        m = re.fullmatch(r"EQNO([\d.]+)EQNO", p.text.strip())
        if m:
            prev = p._p.getprevious()
            if prev is not None and any(True for _ in prev.iter(MNS + "oMathPara")):
                r = OxmlElement("w:r"); t = OxmlElement("w:t"); t.text = f"EQNO{m.group(1)}EQNO"; r.append(t)
                prev.append(r)
                p._p.getparent().remove(p._p)

    body = list(doc.paragraphs)
    for p in body:
        text = p.text.strip()
        sname = p.style.name if p.style is not None else ""
        if sname == "Heading 1":
            if CH_RE.match(text):
                text = re.sub(r"^(第\d+章)\s*", r"\1 ", text)
            p.text = text if text not in ("致谢", "摘要", "目录") else {"致谢": "致　谢", "摘要": "摘　要", "目录": "目　录"}[text]
            para_fmt(p, align=WD_ALIGN_PARAGRAPH.CENTER, before=24, after=18, line=None, first_indent=Pt(0),
                     keep_next=True)
            style_runs(p, HEI, ARIAL if text.lower() == "abstract" else TNR, 16, True)
        elif sname == "Heading 2":
            para_fmt(p, align=WD_ALIGN_PARAGRAPH.LEFT, before=24, after=6, line=None, first_indent=Pt(0), keep_next=True)
            style_runs(p, HEI, TNR, 14, False)
        elif sname == "Heading 3":
            para_fmt(p, align=WD_ALIGN_PARAGRAPH.LEFT, before=12, after=6, line=None, first_indent=Pt(0),
                     left_indent=Pt(0), keep_next=True)
            p.paragraph_format.first_line_indent = Pt(26)
            style_runs(p, HEI, TNR, 13, False)
        elif FIG_RE.match(text):
            p.text = re.sub(r"^(图\s?\d+\.\d+)\s*", lambda m: m.group(1).replace(" ", "") + "　", text)
            para_fmt(p, align=WD_ALIGN_PARAGRAPH.CENTER, before=6, after=12, line=None, first_indent=Pt(0))
            style_runs(p, SONG, TNR, 10.5, True)
        elif TAB_RE.match(text) and _next_is_table(p):
            p.text = re.sub(r"^(表\s?\d+\.\d+)\s*", lambda m: m.group(1).replace(" ", "") + "　", text)
            para_fmt(p, align=WD_ALIGN_PARAGRAPH.CENTER, before=6, after=6, line=None, first_indent=Pt(0),
                     keep_next=True)
            style_runs(p, HEI, TNR, 10.5, True)
        elif p._p.xpath(".//w:drawing"):
            para_fmt(p, align=WD_ALIGN_PARAGRAPH.CENTER, before=6, after=0, line=None, first_indent=Pt(0),
                     keep_next=True)
        elif "EQNO" in text or any(True for _ in p._p.iter(MNS + "oMathPara")):
            _format_equation(p, doc)
        elif sname in ("Block Text",):
            para_fmt(p, align=WD_ALIGN_PARAGRAPH.LEFT, line=20, first_indent=Pt(0), left_indent=Pt(24))
            style_runs(p, SONG, TNR, 10.5)
        elif text:
            para_fmt(p, align=WD_ALIGN_PARAGRAPH.JUSTIFY, line=20, first_indent=Pt(24))
            style_runs(p, SONG, TNR, 12)
            for r in p.runs:  # 上标引用保持上标
                if r.font.superscript:
                    r.font.size = Pt(12)

    for t in doc.tables:
        three_line(t)

    # 图片限制宽度
    for shp in doc.inline_shapes:
        max_w = Cm(14.5)
        if shp.width > max_w:
            ratio = max_w / shp.width
            shp.width = int(shp.width * ratio)
            shp.height = int(shp.height * ratio)


def _next_is_table(p) -> bool:
    nxt = p._p.getnext()
    return nxt is not None and nxt.tag == qn("w:tbl")


def _format_equation(p, doc):
    """公式居中、编号右对齐：使用居中制表位与右制表位。"""
    m = re.search(r"EQNO([\d.]+)EQNO", p.text)
    no = m.group(1) if m else None
    for r in p.runs:
        if "EQNO" in r.text:
            r.text = re.sub(r"EQNO[\d.]+EQNO", "", r.text)
    # oMathPara → oMath（使其可与制表位、编号同处一行）
    for omp in list(p._p.iter(MNS + "oMathPara")):
        parent = omp.getparent()
        idx = parent.index(omp)
        for om in omp.findall(MNS + "oMath"):
            parent.insert(idx, om)
            idx += 1
        parent.remove(omp)
    pPr = p._p.get_or_add_pPr()
    tabs = OxmlElement("w:tabs")
    for val, pos in (("center", 4153), ("right", 8306)):
        t = OxmlElement("w:tab"); t.set(qn("w:val"), val); t.set(qn("w:pos"), str(pos)); tabs.append(t)
    pPr.append(tabs)
    first = p._p.find(qn("w:r"))
    tab_r = OxmlElement("w:r"); tab_r.append(OxmlElement("w:tab"))
    oms = p._p.findall(MNS + "oMath")
    if oms:
        oms[0].addprevious(tab_r)
    if no:
        r = p.add_run()
        r._r.append(OxmlElement("w:tab"))
        r2 = p.add_run(f"({no})")
        set_font(r2, SONG, TNR, 12)
    para_fmt(p, align=WD_ALIGN_PARAGRAPH.LEFT, before=6, after=6, line=None, first_indent=Pt(0))


# ============================================================ 前置部分与分节
def insert_section_break_before(p, start_new_numbering: str | None = None):
    """在段落 p 之前插入“下一页”分节符。start_new_numbering: 'upperRoman' / 'decimal' / None"""
    prev = p._p.getprevious()
    while prev is not None and prev.tag != qn("w:p"):
        prev = prev.getprevious()
    if prev is None:
        return
    pPr = prev.find(qn("w:pPr"))
    if pPr is None:
        pPr = OxmlElement("w:pPr"); prev.insert(0, pPr)
    sectPr = OxmlElement("w:sectPr")
    t = OxmlElement("w:type"); t.set(qn("w:val"), "nextPage"); sectPr.append(t)
    pPr.append(sectPr)
    return sectPr


def finalize_sections(doc: Document, chapter_titles: list[tuple[object, str, str | None]]):
    """chapter_titles: [(段落, 页眉文本, 页码格式或None)]，按文档顺序。"""
    body_sectPr = doc.element.body.find(qn("w:sectPr"))
    for p, _, _ in chapter_titles[1:]:
        insert_section_break_before(p)
    # 所有 sectPr 统一页面设置（复制最终 sectPr 的页面属性）
    sects = doc.element.body.xpath(".//w:sectPr")
    for sp in sects:
        if sp is body_sectPr:
            continue
        for tag in ("w:pgSz", "w:pgMar"):
            src = body_sectPr.find(qn(tag))
            if src is not None and sp.find(qn(tag)) is None:
                sp.append(copy.deepcopy(src))
    doc_sections = doc.sections
    for i, (sec, (_, header, fmt)) in enumerate(zip(doc_sections, chapter_titles)):
        sec.header.is_linked_to_previous = False
        sec.footer.is_linked_to_previous = False
        hp = sec.header.paragraphs[0]
        hp.text = header or ""
        hp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        style_runs(hp, SONG, ARIAL if header and header.isascii() else TNR, 10.5)
        if header:
            pPr = hp._p.get_or_add_pPr()
            bdr = OxmlElement("w:pBdr"); b = OxmlElement("w:bottom")
            b.set(qn("w:val"), "single"); b.set(qn("w:sz"), "6"); b.set(qn("w:space"), "1"); b.set(qn("w:color"), "000000")
            bdr.append(b); pPr.append(bdr)
        fp = sec.footer.paragraphs[0]
        fp.text = ""
        if fmt != "none":
            fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
            for r in add_field(fp, "PAGE", "1"):
                set_font(r, SONG, TNR, 10.5)
        sp = sec._sectPr
        pg = sp.find(qn("w:pgNumType"))
        if fmt in ("upperRoman", "decimal"):
            if pg is None:
                pg = OxmlElement("w:pgNumType"); sp.append(pg)
            pg.set(qn("w:fmt"), fmt); pg.set(qn("w:start"), "1")
        elif fmt == "cont_decimal":
            if pg is None:
                pg = OxmlElement("w:pgNumType"); sp.append(pg)
            pg.set(qn("w:fmt"), "decimal")
        elif fmt == "cont_roman":
            if pg is None:
                pg = OxmlElement("w:pgNumType"); sp.append(pg)
            pg.set(qn("w:fmt"), "upperRoman")
        if i < 2:  # 封面页边距
            sec.top_margin = sec.bottom_margin = Cm(3.8)
            sec.left_margin = sec.right_margin = Cm(3.2)
            sec.header_distance = sec.footer_distance = Cm(3.0)


def build_front(doc: Document, meta: dict) -> list:
    """在文档开头插入封面（中/英）、原创性声明，返回插入的分节锚点段落。"""
    first = doc.paragraphs[0]
    anchors = []

    def P(text="", east=SONG, west=TNR, size=12, bold=False, align=WD_ALIGN_PARAGRAPH.CENTER, before=0, after=0,
          line=None, indent_cm=None):
        p = first.insert_paragraph_before(text)
        para_fmt(p, align=align, before=before, after=after, line=line, exact=line is not None, first_indent=Pt(0))
        if indent_cm is not None:
            p.paragraph_format.left_indent = Cm(indent_cm)
        style_runs(p, east, west, size, bold)
        return p

    # ---------- 中文封面 ----------
    a = P(meta.get("secret", ""), FANGSONG, TNR, 14, align=WD_ALIGN_PARAGRAPH.RIGHT); anchors.append((a, "", "none"))
    P("中国科学技术大学", HEI, TNR, 36, True, before=24)
    P(meta["degree_cn"], HEI, TNR, 36, False, before=30)
    P(meta.get("degree_type_cn", ""), HEI, TNR, 22, False, before=6)
    P("", before=60)
    P(meta["title_cn"], HEI, TNR, 26, True, before=40, after=60)
    for k, v in (("作者姓名", meta["author_cn"]), ("专业领域", meta["major_cn"]), ("导师姓名", meta["supervisor_cn"]),
                 ("完成时间", meta["date_cn"])):
        p = P("", align=WD_ALIGN_PARAGRAPH.LEFT, before=6, indent_cm=3.5)
        r = p.add_run(f"{k}："); set_font(r, HEI, TNR, 16)
        r = p.add_run(v); set_font(r, SONG, TNR, 16)
    # ---------- 英文封面 ----------
    a = P(meta.get("secret", ""), TNR, TNR, 14, align=WD_ALIGN_PARAGRAPH.RIGHT); anchors.append((a, "", "none"))
    P("University of Science and Technology of China", ARIAL, ARIAL, 20, before=24, line=30)
    P(meta["degree_en"], ARIAL, ARIAL, 26, before=12, line=30)
    P(meta.get("degree_type_en", ""), ARIAL, ARIAL, 20, line=30)
    P("", before=60)
    P(meta["title_en"], ARIAL, ARIAL, 26, True, before=40, after=60, line=30)
    for k, v in (("Author", meta["author_en"]), ("Speciality", meta["major_en"]), ("Supervisor", meta["supervisor_en"]),
                 ("Finished time", meta["date_en"])):
        P(f"{k}: {v}", TNR, TNR, 16, align=WD_ALIGN_PARAGRAPH.LEFT, line=30, indent_cm=3.0)
    # ---------- 原创性与授权使用声明 ----------
    a = P("中国科学技术大学学位论文原创性声明", HEI, TNR, 16, True, before=24, after=18)
    anchors.append((a, "", "none"))
    for t in ["本人声明所呈交的学位论文，是本人在导师指导下进行研究工作所取得的成果。除已特别加以标注和致谢的地方外，"
              "论文中不包含任何他人已经发表或撰写过的研究成果。与我一同工作的同志对本研究所做的贡献均已在论文中作了明确的说明。"]:
        p = P(t, align=WD_ALIGN_PARAGRAPH.JUSTIFY, line=20); p.paragraph_format.first_line_indent = Pt(24)
    P("作者签名：＿＿＿＿＿＿＿＿　　　签字日期：＿＿＿＿＿＿＿＿", align=WD_ALIGN_PARAGRAPH.RIGHT, before=24, after=36)
    P("中国科学技术大学学位论文授权使用声明", HEI, TNR, 16, True, before=24, after=18)
    for t in ["作为申请学位的条件之一，学位论文著作权拥有者授权中国科学技术大学拥有学位论文的部分使用权，即：学校有权按有关规定"
              "向国家有关部门或机构送交论文的复印件和电子版，允许论文被查阅和借阅，可以将学位论文编入《中国学位论文全文数据库》"
              "等有关数据库进行检索，可以采用影印、缩印或扫描等复制手段保存、汇编学位论文。本人提交的电子文档的内容和纸质论文的"
              "内容相一致。", "保密的学位论文在解密后也遵守此规定。"]:
        p = P(t, align=WD_ALIGN_PARAGRAPH.JUSTIFY, line=20); p.paragraph_format.first_line_indent = Pt(24)
    P("□公开　　□保密（＿＿年）", align=WD_ALIGN_PARAGRAPH.LEFT, before=12)
    P("作者签名：＿＿＿＿＿＿＿＿　　　导师签名：＿＿＿＿＿＿＿＿", align=WD_ALIGN_PARAGRAPH.RIGHT, before=24)
    P("签字日期：＿＿＿＿＿＿＿＿　　　签字日期：＿＿＿＿＿＿＿＿", align=WD_ALIGN_PARAGRAPH.RIGHT, before=12)
    return anchors


def build_toc(doc: Document, before_p):
    p = before_p.insert_paragraph_before("目　录")
    para_fmt(p, align=WD_ALIGN_PARAGRAPH.CENTER, before=24, after=18, line=None, first_indent=Pt(0))
    style_runs(p, HEI, TNR, 16, True)
    p2 = before_p.insert_paragraph_before("")
    para_fmt(p2, line=None, first_indent=Pt(0))
    for r in add_field(p2, 'TOC \\o "1-3" \\h \\z \\u', "（请在 Word 中右键此处 →“更新域”生成目录）"):
        set_font(r, SONG, TNR, 12)
    return p


def style_toc_levels(doc: Document):
    spec = {"TOC 1": (14, 0, SONG), "toc 1": (14, 0, SONG), "TOC 2": (12, 1, SONG), "toc 2": (12, 1, SONG),
            "TOC 3": (10.5, 2, SONG), "toc 3": (10.5, 2, SONG)}
    names = {s.name for s in doc.styles}
    from docx.enum.style import WD_STYLE_TYPE
    for name, (size, ind, font) in spec.items():
        if name not in names:
            if not name.startswith("TOC"):
                continue
            s = doc.styles.add_style(name, WD_STYLE_TYPE.PARAGRAPH)
        else:
            s = doc.styles[name]
        set_font(s, font, TNR, size)
        s.paragraph_format.left_indent = Pt(12 * ind)
        s.paragraph_format.space_before = Pt(6)
        s.paragraph_format.space_after = Pt(0)


def enable_update_fields(doc: Document):
    settings = doc.settings.element
    uf = OxmlElement("w:updateFields"); uf.set(qn("w:val"), "true")
    settings.append(uf)


def references_md(order: list[str], refs: dict[str, str]) -> str:
    lines = ["# 参考文献", ""]
    for i, k in enumerate(order, 1):
        lines.append(f"REFITEM[{i}] {refs.get(k, '【缺失文献 ' + k + '】')}")
        lines.append("")
    return "\n".join(lines)


def make_preview(docx_path: Path):
    """生成 PDF 预览（macOS 无宋体/黑体，预览时替换为系统自带的宋体-简/黑体-简，不影响正式 docx）。"""
    import shutil
    import zipfile
    soffice = "/Applications/LibreOffice.app/Contents/MacOS/soffice"
    if not Path(soffice).exists():
        return
    prev = BUILD / "preview.docx"
    with zipfile.ZipFile(docx_path) as zin, zipfile.ZipFile(prev, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename.endswith(".xml"):
                x = data.decode("utf-8")
                x = x.replace('"宋体"', '"Hiragino Sans GB"').replace('"黑体"', '"Heiti SC"').replace('"仿宋"', '"Hiragino Sans GB"')
                data = x.encode("utf-8")
            zout.writestr(item, data)
    prof = BUILD / "lo_profile" / "user" / "fonts"          # 预览专用 LibreOffice 配置目录（加载中文字体）
    prof.mkdir(parents=True, exist_ok=True)
    for f in ("/System/Library/Fonts/Hiragino Sans GB.ttc", "/System/Library/Fonts/STHeiti Light.ttc"):
        if Path(f).exists() and not (prof / Path(f).name).exists():
            shutil.copy(f, prof)
    subprocess.run([soffice, f"-env:UserInstallation=file://{BUILD / 'lo_profile'}", "--headless", "--convert-to",
                    "pdf", "--outdir", str(BUILD), str(prev)], capture_output=True)
    if (BUILD / "preview.pdf").exists():
        shutil.move(BUILD / "preview.pdf", BUILD / "thesis_preview.pdf")


def main():
    BUILD.mkdir(exist_ok=True)
    meta = json.loads((HERE / "meta.json").read_text())
    refs = load_refs()
    parts = []
    for name in ["abstract_cn", "abstract_en"]:
        f = HERE / "chapters" / f"{name}.md"
        if f.exists():
            parts.append(f.read_text())
    parts.append("TOCPLACEHOLDER")
    for ch in CHAPTERS:
        f = HERE / "chapters" / f"{ch}.md"
        if f.exists():
            parts.append(f.read_text())
    md_body = "\n\n".join(parts)
    md_body, order = process_citations(md_body, refs)
    md = md_body + "\n\n" + references_md(order, refs)
    for name in ["appendix", "ack", "achievements"]:
        f = HERE / "chapters" / f"{name}.md"
        if f.exists():
            md += "\n\n" + f.read_text()
    md = preprocess(md)
    (BUILD / "thesis_full.md").write_text(md)
    raw = BUILD / "pandoc_raw.docx"
    subprocess.run(["pandoc", str(BUILD / "thesis_full.md"), "-f", "markdown+tex_math_dollars+pipe_tables+superscript",
                    "-o", str(raw), "--resource-path", str(HERE)], check=True)
    doc = Document(str(raw))
    postprocess(doc, meta)

    # 参考文献条目格式
    for p in doc.paragraphs:
        if p.text.startswith("REFITEM"):
            p.text = p.text.replace("REFITEM", "")
            para_fmt(p, align=WD_ALIGN_PARAGRAPH.JUSTIFY, line=20, first_indent=Pt(-21), left_indent=Pt(21))
            style_runs(p, SONG, TNR, 10.5)

    # 目录占位
    toc_anchor = None
    for p in doc.paragraphs:
        if p.text.strip() == "TOCPLACEHOLDER":
            toc_title = build_toc(doc, p)
            p._p.getparent().remove(p._p)
            toc_anchor = toc_title
            break
    style_toc_levels(doc)

    # 分节：封面(中/英)、声明 → 摘要/Abstract/目录（罗马页码）→ 各章/参考文献/致谢（阿拉伯页码）
    anchors = build_front(doc, meta)
    secs = list(anchors)
    first_body = True
    first_front = True
    for p in doc.paragraphs:
        if p.style is not None and p.style.name == "Heading 1":
            t = p.text.strip()
            if t in ("摘　要", "Abstract", "ABSTRACT"):
                secs.append((p, t.replace("　", ""), "upperRoman" if first_front else "cont_roman"))
                first_front = False
            else:
                secs.append((p, t, "decimal" if first_body else "cont_decimal"))
                first_body = False
        elif toc_anchor is not None and p._p is toc_anchor._p:
            secs.append((p, "目录", "upperRoman" if first_front else "cont_roman"))
            first_front = False
    finalize_sections(doc, secs)
    enable_update_fields(doc)
    out = BUILD / "thesis.docx"
    doc.save(str(out))
    make_preview(out)
    n_chars = len(re.sub(r"\s", "", re.sub(r"[#>|`*\-$\\{}^\[\]()!]", "", md_body)))
    print(f"saved {out}; references cited: {len(order)}; approx chars: {n_chars}")


if __name__ == "__main__":
    main()
