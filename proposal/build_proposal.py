"""开题报告 Word 文档生成脚本：proposal.md → proposal/build/proposal.docx & proposal_preview.pdf。

复用 thesis/build_docx.py 的中科大排版规范：
- GB/T 7714—2015 顺序编码制（上标引用 + 自动生成参考文献）
- 封面（中国科学技术大学专业硕士学位论文开题报告）
- A4 页边距、三线表（内容自适应列宽、跨页不断行、跨页重复表头）、居中图/表题、公式编号、页眉页脚
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
BUILD = HERE / "build"
THESIS = ROOT / "thesis"

sys.path.insert(0, str(THESIS))
from build_docx import (  # noqa: E402
    FANGSONG,
    HEI,
    MNS,
    SONG,
    TNR,
    _format_equation,
    _next_is_table,
    add_field,
    load_refs,
    para_fmt,
    process_citations,
    set_font,
    style_runs,
    three_line,
)

HDR_RE = re.compile(r"^[一二三四五六七八九十]+、")
FIG_RE = re.compile(r"^图\s?\d+\.\d+")
TAB_RE = re.compile(r"^表\s?\d+\.\d+")


def preprocess_proposal(md: str) -> str:
    return re.sub(
        r"\$\$(.+?)\\tag\{([\d.]+)\}\s*\$\$",
        lambda m: f"$${m.group(1).strip()}$$EQNO{m.group(2)}EQNO",
        md,
        flags=re.S,
    )


def references_md(order: list[str], refs: dict[str, str]) -> str:
    lines = ["# 参考文献", ""]
    for i, k in enumerate(order, 1):
        lines.append(f"REFITEM[{i}] {refs.get(k, '【缺失文献 ' + k + '】')}")
        lines.append("")
    return "\n".join(lines)


def build_cover(doc: Document, meta: dict):
    first = doc.paragraphs[0]

    def P(text="", east=SONG, west=TNR, size=12, bold=False, align=WD_ALIGN_PARAGRAPH.CENTER, before=0, after=0,
          line=None):
        p = first.insert_paragraph_before(text)
        para_fmt(p, align=align, before=before, after=after, line=line, exact=line is not None, first_indent=Pt(0))
        style_runs(p, east, west, size, bold)
        return p

    P("中国科学技术大学", HEI, TNR, 28, True, before=36, after=12)
    P("专业硕士学位论文开题报告", HEI, TNR, 22, True, before=6, after=36)
    P(f"题目：{meta['title_cn']}", HEI, TNR, 16, True, before=12, after=6, line=24)
    P(meta["title_en"], TNR, TNR, 12, False, before=0, after=36, line=18)

    rows = [
        ("学位类别", f"{meta.get('degree_cn', '专业硕士学位论文')} {meta.get('degree_type_cn', '（电子信息）')}"),
        ("作者姓名", meta.get("author_cn", "【作者姓名】")),
        ("专业领域", meta.get("major_cn", "【专业领域】")),
        ("指导教师", meta.get("supervisor_cn", "【导师姓名】 教授")),
        ("报告日期", "二〇二六年十一月"),
    ]
    for k, v in rows:
        P(f"{k}：{v}", FANGSONG, TNR, 14, False, align=WD_ALIGN_PARAGRAPH.CENTER, before=8, after=8)

    pb = first.insert_paragraph_before("")
    pb.add_run().add_break()
    from docx.enum.text import WD_BREAK
    pb.runs[0].add_break(WD_BREAK.PAGE)


def postprocess_proposal(doc: Document):
    for s in doc.sections:
        s.page_height, s.page_width = Cm(29.7), Cm(21.0)
        s.top_margin = s.bottom_margin = Cm(2.54)
        s.left_margin = s.right_margin = Cm(3.17)
        s.header_distance, s.footer_distance = Cm(1.5), Cm(1.75)
        s.gutter = Cm(0)
        s.different_first_page_header_footer = True

        hp = s.header.paragraphs[0]
        hp.text = "中国科学技术大学专业硕士学位论文开题报告"
        hp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        style_runs(hp, SONG, TNR, 10.5)
        pPr = hp._p.get_or_add_pPr()
        bdr = OxmlElement("w:pBdr")
        b = OxmlElement("w:bottom")
        b.set(qn("w:val"), "single"); b.set(qn("w:sz"), "6"); b.set(qn("w:space"), "1"); b.set(qn("w:color"), "000000")
        bdr.append(b); pPr.append(bdr)

        fp = s.footer.paragraphs[0]
        fp.text = ""
        fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        for r in add_field(fp, "PAGE", "1"):
            set_font(r, SONG, TNR, 10.5)

    set_font(doc.styles["Normal"], SONG, TNR, 12)
    for name in ("Body Text", "First Paragraph", "Compact"):
        if name in [st.name for st in doc.styles]:
            set_font(doc.styles[name], SONG, TNR, 12)

    # 公式编号合并
    for p in list(doc.paragraphs):
        m = re.fullmatch(r"EQNO([\d.]+)EQNO", p.text.strip())
        if m:
            prev = p._p.getprevious()
            if prev is not None and any(True for _ in prev.iter(MNS + "oMathPara")):
                r = OxmlElement("w:r"); t = OxmlElement("w:t"); t.text = f"EQNO{m.group(1)}EQNO"; r.append(t)
                prev.append(r)
                p._p.getparent().remove(p._p)

    for p in list(doc.paragraphs):
        text = p.text.strip()
        sname = p.style.name if p.style is not None else ""
        if sname == "Heading 1":
            para_fmt(p, align=WD_ALIGN_PARAGRAPH.LEFT, before=18, after=10, line=None, first_indent=Pt(0), keep_next=True)
            style_runs(p, HEI, TNR, 15, True)
        elif sname == "Heading 2":
            para_fmt(p, align=WD_ALIGN_PARAGRAPH.LEFT, before=12, after=6, line=None, first_indent=Pt(0), keep_next=True)
            style_runs(p, HEI, TNR, 13.5, True)
        elif FIG_RE.match(text):
            p.text = re.sub(r"^(图\s?\d+\.\d+)\s*", lambda m: m.group(1).replace(" ", "") + "　", text)
            para_fmt(p, align=WD_ALIGN_PARAGRAPH.CENTER, before=4, after=10, line=None, first_indent=Pt(0))
            style_runs(p, SONG, TNR, 10.5, True)
        elif TAB_RE.match(text) and _next_is_table(p):
            p.text = re.sub(r"^(表\s?\d+\.\d+)\s*", lambda m: m.group(1).replace(" ", "") + "　", text)
            para_fmt(p, align=WD_ALIGN_PARAGRAPH.CENTER, before=8, after=4, line=None, first_indent=Pt(0), keep_next=True)
            style_runs(p, HEI, TNR, 10.5, True)
        elif p._p.xpath(".//w:drawing"):
            para_fmt(p, align=WD_ALIGN_PARAGRAPH.CENTER, before=6, after=0, line=None, first_indent=Pt(0), keep_next=True)
        elif "EQNO" in text or any(True for _ in p._p.iter(MNS + "oMathPara")):
            _format_equation(p, doc)
        elif text.startswith("REFITEM"):
            p.text = text.replace("REFITEM", "")
            para_fmt(p, align=WD_ALIGN_PARAGRAPH.JUSTIFY, line=18, first_indent=Pt(-21), left_indent=Pt(21))
            style_runs(p, SONG, TNR, 10.5)
        elif text:
            para_fmt(p, align=WD_ALIGN_PARAGRAPH.JUSTIFY, line=20, first_indent=Pt(24))
            style_runs(p, SONG, TNR, 12)
            for r in p.runs:
                if r.font.superscript:
                    r.font.size = Pt(12)

    for t in doc.tables:
        three_line(t)
        if t.rows and t.rows[0].cells[0].text.strip() == "阶段" and len(t.columns) == 4:
            widths = [Cm(1.65), Cm(2.85), Cm(6.45), Cm(3.71)]
            for row in t.rows:
                for idx, cell in enumerate(row.cells):
                    cell.width = widths[idx]
            for idx, w in enumerate(widths):
                t.columns[idx].width = w

    for shp in doc.inline_shapes:
        max_w = Cm(12.2)
        if shp.width > max_w:
            ratio = max_w / shp.width
            shp.width = int(shp.width * ratio)
            shp.height = int(shp.height * ratio)


def make_preview(docx_path: Path):
    soffice = "/Applications/LibreOffice.app/Contents/MacOS/soffice"
    if not Path(soffice).exists():
        return
    prev = BUILD / "proposal_prev.docx"
    with zipfile.ZipFile(docx_path) as zin, zipfile.ZipFile(prev, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename.endswith(".xml"):
                x = data.decode("utf-8")
                x = x.replace('"宋体"', '"Hiragino Sans GB"').replace('"黑体"', '"Heiti SC"').replace('"仿宋"', '"Hiragino Sans GB"')
                data = x.encode("utf-8")
            zout.writestr(item, data)
    prof = THESIS / "build" / "lo_profile"
    subprocess.run(
        [soffice, f"-env:UserInstallation=file://{prof}", "--headless", "--convert-to", "pdf", "--outdir", str(BUILD), str(prev)],
        check=True,
        capture_output=True,
    )
    if (BUILD / "proposal_prev.pdf").exists():
        shutil.move(BUILD / "proposal_prev.pdf", BUILD / "proposal_preview.pdf")


def main():
    BUILD.mkdir(parents=True, exist_ok=True)
    meta = json.loads((THESIS / "meta.json").read_text())
    refs = load_refs()
    raw_md = (HERE / "proposal.md").read_text()
    body_md, order = process_citations(raw_md, refs)
    full_md = preprocess_proposal(body_md + "\n\n" + references_md(order, refs))
    (BUILD / "proposal_full.md").write_text(full_md)

    raw_docx = BUILD / "proposal_raw.docx"
    subprocess.run(
        ["pandoc", str(BUILD / "proposal_full.md"), "-f", "markdown+tex_math_dollars+pipe_tables+superscript",
         "-o", str(raw_docx), "--resource-path", str(HERE)],
        check=True,
    )
    doc = Document(str(raw_docx))
    postprocess_proposal(doc)
    build_cover(doc, meta)

    out = BUILD / "proposal.docx"
    doc.save(str(out))
    make_preview(out)
    cjk = len(re.findall(r"[\u4e00-\u9fff]", raw_md))
    print(f"saved {out}; cited refs: {len(order)}; proposal CJK chars: {cjk}")


if __name__ == "__main__":
    main()
