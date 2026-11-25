"""表格解析：Excel/CSV 及文档内嵌表格。

表格直接展平为文本会丢失“行-列”对应关系，导致数值类问题检索失败。
本文采用“表头重复 + 行级自然语言序列化”的方式：每 N 行组成一个块，
每块均携带表名与表头，并将每一行序列化为“列名: 值”的形式。
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd


def serialize_rows(df: pd.DataFrame, title: str, rows_per_chunk: int = 15) -> list[dict]:
    df = df.dropna(how="all").dropna(axis=1, how="all")
    if df.empty:
        return []
    df.columns = [str(c).strip() if not str(c).startswith("Unnamed") else f"列{i + 1}"
                  for i, c in enumerate(df.columns)]
    header = " | ".join(df.columns)
    chunks = []
    for start in range(0, len(df), rows_per_chunk):
        part = df.iloc[start:start + rows_per_chunk]
        lines = []
        for _, row in part.iterrows():
            kv = [f"{c}: {_fmt(v)}" for c, v in row.items() if pd.notna(v) and str(v).strip()]
            lines.append("；".join(kv))
        text = f"【表格】{title}\n表头：{header}\n" + "\n".join(lines)
        chunks.append({"text": text, "rows": [int(start), int(start + len(part) - 1)],
                       "markdown": part.to_markdown(index=False) if len(part) <= 30 else ""})
    return chunks


def _fmt(v) -> str:
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).strip()


def parse_spreadsheet(path: str | Path) -> list[dict]:
    path = Path(path)
    out: list[dict] = []
    if path.suffix.lower() == ".csv":
        df = pd.read_csv(path)
        for c in serialize_rows(df, path.stem):
            out.append({**c, "sheet": path.stem})
        return out
    sheets = pd.read_excel(path, sheet_name=None)
    for name, df in sheets.items():
        for c in serialize_rows(df, f"{path.stem}/{name}"):
            out.append({**c, "sheet": name})
    return out
