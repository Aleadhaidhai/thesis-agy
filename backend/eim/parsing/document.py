"""文档解析：PDF / Word / PPT。

- PDF：逐页抽取文本层；若某页文本过少（扫描件/图片页），渲染为图像后走 OCR；
  同时保存页面图像，供视觉检索通路（Chinese-CLIP / ColQwen）使用。
- Word：按标题层级维护章节路径，正文与内嵌表格分别处理。
- PPT：逐页抽取标题与文本框，页面即天然的语义单元。
"""
from __future__ import annotations

from pathlib import Path

from eim.parsing.chunker import chunk_text
from eim.parsing.image import ocr_image
from eim.parsing.table import serialize_rows


def parse_pdf(path: str | Path, page_img_dir: str | Path, min_text_chars: int = 50) -> list[dict]:
    import pymupdf
    path = Path(path)
    page_img_dir = Path(page_img_dir)
    page_img_dir.mkdir(parents=True, exist_ok=True)
    out = []
    with pymupdf.open(path) as doc:
        for i, page in enumerate(doc):
            img_path = page_img_dir / f"{path.stem}_p{i + 1}.png"
            page.get_pixmap(dpi=110).save(img_path)
            text = page.get_text().strip()
            source = "text_layer"
            if len(text) < min_text_chars:
                text = ocr_image(img_path)
                source = "ocr"
            for j, c in enumerate(chunk_text(text, prefix=f"【文档】{path.name} 第{i + 1}页\n")):
                out.append({"text": c, "page": i + 1, "source": source,
                            "image_path": str(img_path) if j == 0 else None})
    return out


def parse_docx(path: str | Path) -> list[dict]:
    import docx
    from docx.document import Document as _Doc
    from docx.table import Table
    from docx.text.paragraph import Paragraph
    import pandas as pd

    path = Path(path)
    d: _Doc = docx.Document(str(path))
    out: list[dict] = []
    heading_path: list[str] = []
    buf: list[str] = []

    def flush():
        if buf:
            sec = " > ".join(heading_path)
            prefix = f"【文档】{path.name}" + (f"｜{sec}" if sec else "") + "\n"
            for c in chunk_text("\n".join(buf), prefix=prefix):
                out.append({"text": c, "section": sec})
            buf.clear()

    for block in d.element.body.iterchildren():
        tag = block.tag.split("}")[-1]
        if tag == "p":
            p = Paragraph(block, d)
            t = p.text.strip()
            if not t:
                continue
            style = (p.style.name or "").lower() if p.style is not None else ""
            if style.startswith("heading") or style.startswith("标题") or style == "title":
                flush()
                try:
                    level = int("".join(ch for ch in style if ch.isdigit()) or 1)
                except ValueError:
                    level = 1
                heading_path[:] = heading_path[:level - 1] + [t]
            else:
                buf.append(t)
        elif tag == "tbl":
            flush()
            tbl = Table(block, d)
            rows = [[c.text.strip() for c in r.cells] for r in tbl.rows]
            if len(rows) >= 2:
                df = pd.DataFrame(rows[1:], columns=rows[0])
                for c in serialize_rows(df, f"{path.name}｜{' > '.join(heading_path)}"):
                    out.append({"text": c["text"], "section": " > ".join(heading_path), "table": True})
    flush()
    return out


def parse_pptx(path: str | Path) -> list[dict]:
    from pptx import Presentation
    path = Path(path)
    prs = Presentation(str(path))
    out = []
    for i, slide in enumerate(prs.slides):
        title = slide.shapes.title.text.strip() if slide.shapes.title is not None else ""
        texts = []
        for shp in slide.shapes:
            if shp.has_text_frame and shp != slide.shapes.title:
                t = shp.text_frame.text.strip()
                if t:
                    texts.append(t)
            if getattr(shp, "has_table", False) and shp.has_table:
                rows = [" | ".join(c.text for c in r.cells) for r in shp.table.rows]
                texts.append("\n".join(rows))
        notes = slide.notes_slide.notes_text_frame.text.strip() if slide.has_notes_slide else ""
        body = "\n".join(texts) + (f"\n备注：{notes}" if notes else "")
        out.append({"text": f"【演示文稿】{path.name} 第{i + 1}页：{title}\n{body}".strip(), "page": i + 1})
    return out


def parse_txt(path: str | Path) -> list[dict]:
    path = Path(path)
    text = path.read_text(encoding="utf-8", errors="ignore")
    return [{"text": c} for c in chunk_text(text, prefix=f"【文档】{path.name}\n")]
