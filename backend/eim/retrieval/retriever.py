"""权限感知的多路混合检索器。

流程：ACL 主体解析 → 三路召回（稠密 / 稀疏 / 视觉，均在向量库内做 ACL 前置过滤）
     → 加权 RRF 融合 → 交叉编码器重排 → 时效衰减 → Top-N。
各环节可通过参数开关，便于第 7 章的消融实验。
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from eim.config import settings
from eim.knowledge.embedder import get_clip_embedder, get_text_embedder
from eim.models import MKU
from eim.retrieval.bm25 import BM25Index
from eim.retrieval.fusion import get_reranker, rrf, time_decay
from eim.storage.db import DB
from eim.storage.vectorstore import VectorStore

log = logging.getLogger(__name__)


@dataclass
class RetrievalConfig:
    use_dense: bool = True
    use_sparse: bool = True          # BGE-M3 稀疏词汇权重
    use_bm25: bool = True            # BM25 词法
    use_visual: bool = True
    use_rerank: bool = True
    use_time_decay: bool = True
    use_acl: bool = True
    topk_dense: int = settings.topk_dense
    topk_sparse: int = settings.topk_sparse
    topk_visual: int = settings.topk_visual
    rerank_pool: int = 30
    topn: int = settings.rerank_topn
    weights: dict[str, float] = field(default_factory=lambda: {"dense": 1.0, "sparse": 0.7, "bm25": 0.7,
                                                                "visual": 0.3})


@dataclass
class Hit:
    mku: MKU
    score: float
    sources: dict[str, int]
    rerank: float | None = None


class HybridRetriever:
    def __init__(self, db: DB | None = None, vs: VectorStore | None = None, bm25: BM25Index | None = None):
        self.db = db or DB()
        self.vs = vs or VectorStore()
        self.bm25 = bm25 or BM25Index()

    def retrieve(self, query: str, principals: set[str] | None, cfg: RetrievalConfig | None = None,
                 extra_filter: str = "", conv_scope: list[str] | None = None) -> tuple[list[Hit], dict]:
        cfg = cfg or RetrievalConfig()
        p = principals if cfg.use_acl else None
        if conv_scope:
            scope = ", ".join(f'"{c}"' for c in conv_scope)
            extra_filter = " and ".join(x for x in (extra_filter, f"conv_id in [{scope}]") if x)
        timing: dict[str, float] = {}
        lists: dict[str, list[tuple[str, float]]] = {}

        t0 = time.perf_counter()
        if cfg.use_dense or cfg.use_sparse:
            q = get_text_embedder().encode_query(query)
            timing["embed"] = time.perf_counter() - t0
            if cfg.use_dense:
                lists["dense"] = self.vs.search_dense(q["dense"], cfg.topk_dense, p, extra_filter)
            if cfg.use_sparse:
                lists["sparse"] = self.vs.search_sparse(q["sparse"], cfg.topk_sparse, p, extra_filter)
        if cfg.use_bm25:
            res = self.bm25.search(query, cfg.topk_sparse * 3, p)
            if conv_scope:
                mk = self.db.get_mkus([i for i, _ in res])
                res = [(i, s) for i, s in res if i in mk and mk[i].conv_id in conv_scope]
            lists["bm25"] = res[:cfg.topk_sparse]
        if cfg.use_visual:
            try:
                qv = get_clip_embedder().encode_text([query])[0]
                vis = self.vs.search_visual(qv, cfg.topk_visual, p, extra_filter)
                lists["visual"] = [(i, sc) for i, sc in vis if sc >= settings.visual_min_sim]
            except Exception as e:  # 视觉模型不可用时降级
                log.warning("visual retrieval disabled: %s", e)
        timing["recall"] = time.perf_counter() - t0

        fused = rrf(lists, weights=cfg.weights)[: cfg.rerank_pool if cfg.use_rerank else cfg.topn]
        mkus = self.db.get_mkus([d for d, _, _ in fused])
        hits = [Hit(mku=mkus[d], score=s, sources=src) for d, s, src in fused if d in mkus]
        # 二次 ACL 校验（纵深防御）：即使索引过滤失效也不会越权返回
        if p is not None:
            hits = [h for h in hits if set(h.mku.acl) & p]

        t1 = time.perf_counter()
        if cfg.use_rerank and hits:
            scores = get_reranker().score(query, [h.mku.content for h in hits])
            for h, s in zip(hits, scores):
                h.rerank = s
                h.score = s
        if cfg.use_time_decay and hits:
            lam = settings.time_decay_weight
            now = max(h.mku.ts_end for h in hits)  # 以语料最新时间为参照，便于离线评测复现
            for h in hits:
                h.score = (1 - lam) * h.score + lam * time_decay(h.mku.ts_end, now=now)
        hits.sort(key=lambda h: -h.score)
        timing["rerank"] = time.perf_counter() - t1
        timing["total"] = time.perf_counter() - t0
        return hits[: cfg.topn], {"lists": {k: len(v) for k, v in lists.items()}, "timing": timing}
