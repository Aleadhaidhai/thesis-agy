"""知识入库流水线：同步 → 解析 → 话题切分 → MKU 构建 → 向量化 → 索引。

支持增量更新：每个会话记录同步水位 last_ts；新消息到达后，仅回溯“活跃窗口”内的尾部消息重新切分，
删除受影响话题的旧 MKU 后重建，避免全量重算。
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

import numpy as np

from eim.adapters.base import IMAdapter
from eim.config import settings
from eim.knowledge.embedder import get_clip_embedder, get_text_embedder
from eim.knowledge.mku_builder import MKUBuilder
from eim.knowledge.segmentation import TopicSegmenter, is_low_info
from eim.models import MKU, Conversation, Message, Modality, ParsedContent
from eim.parsing.dispatcher import ParserDispatcher
from eim.retrieval.bm25 import BM25Index
from eim.storage.db import DB
from eim.storage.vectorstore import VectorStore

log = logging.getLogger(__name__)


@dataclass
class IngestStats:
    messages: int = 0
    parsed: int = 0
    topics: int = 0
    mkus: int = 0
    visual: int = 0
    seconds: dict[str, float] = field(default_factory=dict)


class Ingestor:
    def __init__(self, db: DB | None = None, vs: VectorStore | None = None, bm25: BM25Index | None = None,
                 segmenter=None, builder: MKUBuilder | None = None, parser: ParserDispatcher | None = None,
                 use_visual: bool = True):
        self.db = db or DB()
        self.vs = vs or VectorStore()
        self.bm25 = bm25 or BM25Index()
        self.segmenter = segmenter or TopicSegmenter()
        self.builder = builder or MKUBuilder()
        self.parser = parser or ParserDispatcher()
        self.use_visual = use_visual

    # ------------------------------------------------------------------
    def sync_from_adapter(self, adapter: IMAdapter) -> IngestStats:
        st = IngestStats()
        for conv in adapter.list_conversations():
            self.db.upsert_conversation(conv)
            since = self.db.get_last_ts(conv.conv_id)
            msgs = list(adapter.fetch_history(conv.conv_id, since))
            for m in msgs:
                if m.attachment and not m.attachment.path:
                    m.attachment.path = adapter.download_attachment(m.attachment, str(settings.blob_dir))
            st.messages += self.db.insert_messages(msgs)
            if msgs:
                s = self.ingest_conversation(conv, since)
                st.parsed += s.parsed
                st.topics += s.topics
                st.mkus += s.mkus
                st.visual += s.visual
                self.db.set_last_ts(conv.conv_id, msgs[-1].ts)
        self.rebuild_bm25()
        return st

    # ------------------------------------------------------------------
    def parse_pending(self, conv_id: str) -> int:
        pending = self.db.unparsed_messages(conv_id)
        items: list[ParsedContent] = []
        for m in pending:
            items.extend(self.parser.parse(m))
        self.db.insert_parsed(items)
        self.db.mark_parsed([m.msg_id for m in pending])
        return len(pending)

    def ingest_conversation(self, conv: Conversation, since_ts: float = 0.0) -> IngestStats:
        st = IngestStats()
        t = time.perf_counter()
        st.parsed = self.parse_pending(conv.conv_id)
        st.seconds["parse"] = time.perf_counter() - t

        # 回溯活跃窗口，重新切分尾部
        start = 0.0 if since_ts <= 0 else since_ts - getattr(self.segmenter, "window", 6 * 3600)
        msgs = self.db.get_messages(conv.conv_id, since_ts=max(0.0, start) - 1e-6)
        if not msgs:
            return st
        parsed = self.db.get_parsed([m.msg_id for m in msgs])
        texts = {m.msg_id: _seg_text(m, parsed.get(m.msg_id, [])) for m in msgs}

        t = time.perf_counter()
        emb_ids = [i for i, x in texts.items() if x and not is_low_info(x)]
        vecs: dict[str, np.ndarray] = {}
        if emb_ids:
            dense = get_text_embedder().encode([texts[i] for i in emb_ids], sparse=False)["dense"]
            vecs = dict(zip(emb_ids, dense))
        topics = self.segmenter.segment(conv.conv_id, msgs, texts, vecs)
        st.seconds["segment"] = time.perf_counter() - t

        # 删除受影响话题的旧 MKU（以消息 ID 定位旧话题）
        old_topic_ids = self._topics_containing({m.msg_id for m in msgs})
        self.vs.delete(self.db.delete_mkus_of_topics(old_topic_ids))
        self.db.upsert_topics(topics)
        st.topics = len(topics)

        t = time.perf_counter()
        mdict = {m.msg_id: m for m in msgs}
        mkus: list[MKU] = []
        for tp in topics:
            mkus.extend(self.builder.build(conv, tp, mdict, parsed))
        st.seconds["build"] = time.perf_counter() - t
        st.mkus, st.visual = self.index_mkus(mkus)
        return st

    def index_mkus(self, mkus: list[MKU]) -> tuple[int, int]:
        if not mkus:
            return 0, 0
        self.db.upsert_mkus(mkus)
        enc = get_text_embedder().encode([m.content for m in mkus])
        self.vs.upsert_text(mkus, enc["dense"], enc["sparse"])
        vis = [m for m in mkus if m.image_path]
        if self.use_visual and vis:
            try:
                self.vs.upsert_visual(vis, get_clip_embedder().encode_images([m.image_path for m in vis]))
            except Exception as e:
                log.warning("visual index skipped: %s", e)
                vis = []
        return len(mkus), len(vis)

    def _topics_containing(self, msg_ids: set[str]) -> list[str]:
        rows = self.db.conn.execute("SELECT topic_id, msg_ids FROM topics").fetchall()
        import json
        return [r["topic_id"] for r in rows if msg_ids & set(json.loads(r["msg_ids"]))]

    def rebuild_bm25(self):
        self.bm25.build([(m.mku_id, m.content, m.acl) for m in self.db.all_mkus()])


def _seg_text(m: Message, parsed: list[ParsedContent]) -> str:
    """用于话题切分的消息文本：文本消息取原文，附件取解析结果的前 200 字。"""
    if not parsed:
        return m.text
    p = parsed[0]
    if p.modality == Modality.TEXT:
        return p.text
    return (m.text + " " + p.text[:200]).strip()
