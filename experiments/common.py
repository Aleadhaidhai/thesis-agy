"""实验公共工具：按“变体”构建独立索引（用于知识构建层的消融实验），以及加载问答标注。

变体（variant）：
  full        ：本文方法（在线话题切分 + LLM 摘要增强 + VLM+OCR 图像表示 + 附件上下文头）
  fixedwin    ：话题切分替换为固定窗口（10 条 / 30 分钟）
  nosummary   ：不做 LLM 话题摘要增强
  ocronly     ：图片仅用 OCR，不用 VLM 描述
  noctx       ：附件单元不注入会话上下文头
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from eim.adapters.loader import load_simeim  # noqa: E402
from eim.adapters.simulator import SimulatorAdapter  # noqa: E402
from eim.knowledge import mku_builder as MB  # noqa: E402
from eim.knowledge.indexer import Ingestor  # noqa: E402
from eim.knowledge.segmentation import FixedWindowSegmenter, TopicSegmenter  # noqa: E402
from eim.parsing.dispatcher import ParserDispatcher  # noqa: E402
from eim.retrieval.bm25 import BM25Index  # noqa: E402
from eim.retrieval.retriever import HybridRetriever  # noqa: E402
from eim.storage.db import DB  # noqa: E402
from eim.storage.vectorstore import VectorStore  # noqa: E402

import os  # noqa: E402

DATASET = Path(os.environ.get("EIM_DATASET", ROOT / "datasets" / "simeim" / "build" / "simeim.json"))
QA = Path(os.environ.get("EIM_QA", ROOT / "datasets" / "simeim" / "build" / "qa.json"))
RUNS = Path(os.environ.get("EIM_RUNS", ROOT / "experiments" / "runs"))


class NoCtxBuilder(MB.MKUBuilder):
    """消融：附件单元去掉上下文头，仅保留附件自身解析文本。"""

    def build(self, conv, topic, msgs, parsed):
        out = super().build(conv, topic, msgs, parsed)
        for m in out:
            if m.kind == "attachment" and m.content.startswith("【来源】"):
                m.content = m.content.split("\n", 1)[-1]
        return out


def variant_paths(name: str) -> dict:
    d = RUNS / "index" / name
    d.mkdir(parents=True, exist_ok=True)
    return {"dir": d, "db": d / "eim.db", "milvus": str(d / "milvus.db"), "bm25": d / "bm25.pkl",
            "sim": d / "im_sim.db", "files": d / "im_files"}


def open_variant(name: str) -> tuple[DB, VectorStore, BM25Index, SimulatorAdapter]:
    p = variant_paths(name)
    return DB(p["db"]), VectorStore(p["milvus"]), BM25Index(p["bm25"]), SimulatorAdapter(p["sim"], p["files"])


def build_variant(name: str, reuse_parse_from: str | None = None) -> dict:
    db, vs, bm25, sim = open_variant(name)
    if not sim.list_conversations():
        load_simeim(DATASET, sim)
    seg = FixedWindowSegmenter(10, 30) if name == "fixedwin" else TopicSegmenter()
    builder = NoCtxBuilder() if name == "noctx" else MB.MKUBuilder(use_llm_summary=(name != "nosummary"))
    parser = ParserDispatcher(use_vlm=(name != "ocronly"))
    if reuse_parse_from:  # 复用已解析结果（解析与切分/构建无关时节省时间）
        src = DB(variant_paths(reuse_parse_from)["db"])
        if not db.conn.execute("SELECT COUNT(*) FROM parsed_contents").fetchone()[0]:
            sim_paths = {}
            for r in sim.conn.execute("SELECT msg_id, attachment FROM msgs WHERE attachment IS NOT NULL"):
                att = json.loads(r["attachment"])
                if att.get("path"):
                    sim_paths[r["msg_id"]] = att["path"]
            rows = src.conn.execute("SELECT * FROM messages").fetchall()
            reparse_ids = set()
            with db.conn as c:
                for r in rows:
                    row = list(r)
                    mid, mtype, att_raw = r["msg_id"], r["type"], r["attachment"]
                    if att_raw and mid in sim_paths:
                        att = json.loads(att_raw)
                        att["path"] = sim_paths[mid]
                        row[7] = json.dumps(att, ensure_ascii=False)
                    if name == "ocronly" and mtype == "image":
                        row[10] = 0  # 仅对图片重新执行纯 OCR（不调用 VLM）
                        reparse_ids.add(mid)
                    c.execute("INSERT OR IGNORE INTO messages VALUES (?,?,?,?,?,?,?,?,?,?,?)", tuple(row))
                for r in src.conn.execute("SELECT msg_id,modality,text,chunk_index,meta,image_path FROM parsed_contents"):
                    mid, mod, txt, cidx, meta, img_p = tuple(r)
                    if mid in reparse_ids:
                        continue
                    if img_p and not Path(img_p).exists():
                        if mid in sim_paths and Path(sim_paths[mid]).exists():
                            img_p = sim_paths[mid]
                        else:
                            cand = img_p.replace("/index/full/", f"/index/{reuse_parse_from}/")
                            if Path(cand).exists():
                                img_p = cand
                    c.execute("INSERT INTO parsed_contents(msg_id,modality,text,chunk_index,meta,image_path) "
                              "VALUES (?,?,?,?,?,?)", (mid, mod, txt, cidx, meta, img_p))
                for r in src.conn.execute("SELECT * FROM conversations"):
                    c.execute("INSERT OR REPLACE INTO conversations VALUES (?,?,?,?,?)", tuple(r))
    t = time.perf_counter()
    ing = Ingestor(db=db, vs=vs, bm25=bm25, segmenter=seg, builder=builder, parser=parser)
    if reuse_parse_from and db.conn.execute("SELECT COUNT(*) FROM parsed_contents").fetchone()[0]:
        stats = {"messages": db.conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0],
                 "parsed": 0, "topics": 0, "mkus": 0, "visual": 0}
        for conv in db.list_conversations():
            s = ing.ingest_conversation(conv, 0.0)
            for k in ("parsed", "topics", "mkus", "visual"):
                stats[k] += getattr(s, k)
        ing.rebuild_bm25()
    else:
        stats = ing.sync_from_adapter(sim).__dict__
    stats["elapsed_s"] = round(time.perf_counter() - t, 1)
    (variant_paths(name)["dir"] / "build_stats.json").write_text(json.dumps(stats, ensure_ascii=False, indent=1))
    return stats


def retriever_for(name: str) -> tuple[HybridRetriever, SimulatorAdapter, DB]:
    db, vs, bm25, sim = open_variant(name)
    return HybridRetriever(db=db, vs=vs, bm25=bm25), sim, db


def load_qa() -> list[dict]:
    return json.loads(QA.read_text())


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("variant", nargs="+")
    ap.add_argument("--reuse-parse-from", default=None)
    a = ap.parse_args()
    for v in a.variant:
        print(v, build_variant(v, a.reuse_parse_from), flush=True)
