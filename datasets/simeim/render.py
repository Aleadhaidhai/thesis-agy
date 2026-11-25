"""SimEIM 附件渲染：将种子中的附件规格渲染为真实文件（截图 PNG / PDF / DOCX / PPTX / XLSX / WAV）。

所有内容均为虚构。图片模拟企业 IM 中常见的终端日志截图、系统界面截图、监控图表与白板架构图；
语音使用 macOS 本地 TTS 合成，保证数据构建过程同样不依赖外部服务。
"""
from __future__ import annotations

import math
import random
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FONT = "/System/Library/Fonts/Hiragino Sans GB.ttc"
MONO = "/System/Library/Fonts/Menlo.ttc"


def _font(size: int, mono: bool = False):
    try:
        return ImageFont.truetype(MONO if mono else FONT, size)
    except OSError:
        return ImageFont.truetype(FONT, size)


def _cjk_font(size: int):
    return ImageFont.truetype(FONT, size)


def _text_w(draw: ImageDraw.ImageDraw, s: str, f) -> int:
    return int(draw.textlength(s, font=f))


def render_terminal(spec: dict, out: Path) -> Path:
    lines = spec["lines"]
    f = _cjk_font(17)
    tmp = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    w = max(900, max(_text_w(tmp, ln, f) for ln in lines) + 60)
    h = 70 + 30 * len(lines) + 30
    img = Image.new("RGB", (w, h), (30, 30, 30))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, w, 36], fill=(58, 58, 58))
    for i, c in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
        d.ellipse([14 + i * 22, 12, 26 + i * 22, 24], fill=c)
    d.text((w // 2 - 80, 8), spec.get("title", "terminal"), fill=(200, 200, 200), font=_cjk_font(15))
    y = 56
    for ln in lines:
        color = (230, 230, 230)
        if "ERROR" in ln or "✗" in ln or "error" in ln.lower()[:12]:
            color = (255, 110, 110)
        elif "WARN" in ln:
            color = (255, 210, 90)
        elif ln.startswith("$"):
            color = (120, 220, 120)
        d.text((24, y), ln, fill=color, font=f)
        y += 30
    img.save(out)
    return out


def render_form(spec: dict, out: Path) -> Path:
    fields = spec["fields"]
    fk, fv = _cjk_font(18), _cjk_font(18)
    tmp = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    kw = max(_text_w(tmp, k, fk) for k, _ in fields) + 40
    vw = min(900, max(_text_w(tmp, v, fv) for _, v in fields) + 40)
    w = max(700, kw + vw + 80)
    rows = []
    for k, v in fields:  # 简单折行
        chunks, cur = [], ""
        for ch in v:
            if _text_w(tmp, cur + ch, fv) > w - kw - 80:
                chunks.append(cur)
                cur = ""
            cur += ch
        chunks.append(cur)
        rows.append((k, chunks))
    h = 110 + sum(22 + 28 * len(c) for _, c in rows) + 30
    img = Image.new("RGB", (w, h), (245, 247, 250))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, w, 56], fill=(64, 128, 255))
    d.text((24, 14), spec.get("title", ""), fill="white", font=_cjk_font(22))
    y = 80
    for k, chunks in rows:
        rh = 22 + 28 * len(chunks)
        d.rectangle([24, y, w - 24, y + rh - 6], fill="white", outline=(225, 228, 235))
        d.text((40, y + 10), k, fill=(120, 125, 135), font=fk)
        for j, c in enumerate(chunks):
            d.text((40 + kw, y + 10 + 28 * j), c, fill=(30, 33, 40), font=fv)
        y += rh
    img.save(out)
    return out


def render_chart(spec: dict, out: Path) -> Path:
    x, series = spec["x"], spec["series"]
    w, h, ml, mr, mt, mb = 900, 520, 90, 40, 80, 70
    img = Image.new("RGB", (w, h), "white")
    d = ImageDraw.Draw(img)
    d.text((ml, 24), spec.get("title", ""), fill=(30, 30, 30), font=_cjk_font(22))
    allv = [v for s in series.values() for v in s]
    vmax = max(allv) * 1.15 or 1
    pw, ph = w - ml - mr, h - mt - mb
    d.line([ml, mt, ml, mt + ph], fill=(80, 80, 80), width=2)
    d.line([ml, mt + ph, ml + pw, mt + ph], fill=(80, 80, 80), width=2)
    for i in range(6):
        val = vmax * i / 5
        yy = mt + ph - ph * i / 5
        d.line([ml, yy, ml + pw, yy], fill=(232, 232, 232))
        d.text((10, yy - 10), f"{val:.1f}" if vmax < 50 else f"{int(val)}", fill=(90, 90, 90), font=_cjk_font(14))
    step = pw / max(1, len(x) - 1)
    for i, lab in enumerate(x):
        d.text((ml + i * step - 18, mt + ph + 12), lab, fill=(90, 90, 90), font=_cjk_font(15))
    colors = [(64, 128, 255), (255, 99, 71), (46, 160, 67), (255, 170, 0)]
    for si, (name, vals) in enumerate(series.items()):
        c = colors[si % len(colors)]
        pts = [(ml + i * step, mt + ph - ph * v / vmax) for i, v in enumerate(vals)]
        d.line(pts, fill=c, width=3)
        for (px, py), v in zip(pts, vals):
            d.ellipse([px - 5, py - 5, px + 5, py + 5], fill=c)
            d.text((px - 14, py - 28), f"{v:g}", fill=c, font=_cjk_font(14))
        d.rectangle([w - 220, 30 + si * 26, w - 200, 46 + si * 26], fill=c)
        d.text((w - 192, 26 + si * 26), name, fill=(40, 40, 40), font=_cjk_font(16))
    img.save(out)
    return out


def render_diagram(spec: dict, out: Path) -> Path:
    nodes, edges = spec["nodes"], spec["edges"]
    w, h = 1000, 620
    img = Image.new("RGB", (w, h), (252, 252, 248))
    d = ImageDraw.Draw(img)
    d.text((30, 20), spec.get("title", ""), fill=(40, 40, 40), font=_cjk_font(24))
    # 分层布局：按 BFS 深度
    depth = {0: 0}
    frontier = [0]
    while frontier:
        nxt = []
        for u in frontier:
            for a, b in edges:
                if a == u and b not in depth:
                    depth[b] = depth[u] + 1
                    nxt.append(b)
        frontier = nxt
    for i in range(len(nodes)):
        depth.setdefault(i, max(depth.values()) + 1)
    levels: dict[int, list[int]] = {}
    for i, dp in depth.items():
        levels.setdefault(dp, []).append(i)
    pos = {}
    nl = len(levels)
    for dp, ids in levels.items():
        for j, i in enumerate(ids):
            pos[i] = (int(w * (j + 1) / (len(ids) + 1)), int(90 + (h - 160) * dp / max(1, nl - 1)))
    f = _cjk_font(16)
    for a, b in edges:
        (x1, y1), (x2, y2) = pos[a], pos[b]
        d.line([x1, y1 + 24, x2, y2 - 24], fill=(90, 90, 90), width=2)
        ang = math.atan2((y2 - 24) - (y1 + 24), x2 - x1)
        for s in (-0.4, 0.4):
            d.line([x2, y2 - 24, x2 - 12 * math.cos(ang + s), y2 - 24 - 12 * math.sin(ang + s)],
                   fill=(90, 90, 90), width=2)
    for i, name in enumerate(nodes):
        x0, y0 = pos[i]
        tw = _text_w(d, name, f) + 30
        d.rounded_rectangle([x0 - tw // 2, y0 - 24, x0 + tw // 2, y0 + 24], radius=10, fill=(225, 238, 255),
                            outline=(64, 128, 255), width=2)
        d.text((x0 - tw // 2 + 15, y0 - 11), name, fill=(20, 40, 80), font=f)
    # 手绘感：轻微噪点
    rnd = random.Random(len(nodes))
    for _ in range(800):
        px, py = rnd.randrange(w), rnd.randrange(h)
        d.point((px, py), fill=(235, 235, 228))
    img.save(out)
    return out


def render_pdf(spec: dict, out: Path) -> Path:
    import pymupdf
    doc = pymupdf.open()
    page = doc.new_page()
    y = 60
    page.insert_text((60, y), spec["title"], fontname="china-s", fontsize=18)
    y += 40
    for head, body in spec["sections"]:
        text = f"{head}\n{body}"
        rect = pymupdf.Rect(60, y, 540, y + 400)
        rc = page.insert_textbox(rect, text, fontname="china-s", fontsize=11, lineheight=1.5)
        used = 400 - rc if rc >= 0 else 400
        y += used + 18
        if y > 740:
            page = doc.new_page()
            y = 60
    doc.save(out)
    return out


def render_docx(spec: dict, out: Path) -> Path:
    import docx
    d = docx.Document()
    d.add_heading(spec["title"], level=0)
    for head, body in spec["sections"]:
        d.add_heading(head, level=1)
        d.add_paragraph(body)
    d.save(out)
    return out


def render_pptx(spec: dict, out: Path) -> Path:
    from pptx import Presentation
    from pptx.util import Pt
    prs = Presentation()
    s = prs.slides.add_slide(prs.slide_layouts[0])
    s.shapes.title.text = spec["title"]
    for title, body in spec["slides"]:
        sl = prs.slides.add_slide(prs.slide_layouts[1])
        sl.shapes.title.text = title
        tf = sl.placeholders[1].text_frame
        tf.text = body
        for p in tf.paragraphs:
            for r in p.runs:
                r.font.size = Pt(20)
    prs.save(out)
    return out


def render_xlsx(spec: dict, out: Path) -> Path:
    import pandas as pd
    with pd.ExcelWriter(out) as w:
        for name, rows in spec["sheets"].items():
            pd.DataFrame(rows[1:], columns=rows[0]).to_excel(w, sheet_name=name, index=False)
    return out


def render_audio(spec: dict, out: Path, voice: str = "Tingting") -> Path:
    aiff = out.with_suffix(".aiff")
    subprocess.run(["say", "-v", voice, "-r", "200", "-o", str(aiff), spec["text"]], check=True)
    subprocess.run(["afconvert", "-f", "WAVE", "-d", "LEI16@16000", str(aiff), str(out)], check=True)
    aiff.unlink(missing_ok=True)
    return out


EXT = {"terminal": ".png", "form": ".png", "chart": ".png", "diagram": ".png", "pdf": ".pdf", "docx": ".docx",
       "pptx": ".pptx", "xlsx": ".xlsx", "audio": ".wav"}
RENDER = {"terminal": render_terminal, "form": render_form, "chart": render_chart, "diagram": render_diagram,
          "pdf": render_pdf, "docx": render_docx, "pptx": render_pptx, "xlsx": render_xlsx, "audio": render_audio}


def render(spec: dict, out_dir: Path, stem: str) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    kind = spec["kind"]
    name = spec.get("title", stem).replace("/", "_").replace(" ", "_")
    out = out_dir / f"{stem}_{name}{EXT[kind]}" if kind in ("pdf", "docx", "pptx", "xlsx") else \
        out_dir / f"{stem}{EXT[kind]}"
    return RENDER[kind](spec, out)
