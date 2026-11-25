"""文本分块：按标题/段落/句子的层级边界切分，块间保留重叠以保持上下文连贯。"""
from __future__ import annotations

import re

_SENT_RE = re.compile(r"(?<=[。！？!?；;\n])")


def split_sentences(text: str) -> list[str]:
    return [s for s in _SENT_RE.split(text) if s.strip()]


def chunk_text(text: str, max_chars: int = 500, overlap: int = 80, prefix: str = "") -> list[str]:
    """将文本按段落→句子聚合为不超过 max_chars 的块；prefix（如文档名+章节标题）加到每块开头。"""
    text = re.sub(r"\n{3,}", "\n\n", text.strip())
    if not text:
        return []
    paras = [p.strip() for p in text.split("\n\n") if p.strip()]
    units: list[str] = []
    for p in paras:
        if len(p) <= max_chars:
            units.append(p)
        else:
            units.extend(split_sentences(p))
    chunks: list[str] = []
    cur = ""
    for u in units:
        if len(cur) + len(u) + 1 <= max_chars:
            cur = f"{cur}\n{u}" if cur else u
            continue
        if cur:
            chunks.append(cur)
            tail = cur[-overlap:] if overlap else ""
            cur = f"{tail}{u}" if len(tail) + len(u) <= max_chars else u
        else:  # 单句超长，硬切
            for i in range(0, len(u), max_chars - overlap):
                chunks.append(u[i:i + max_chars])
            cur = ""
    if cur:
        chunks.append(cur)
    return [f"{prefix}{c}" if prefix else c for c in chunks]
