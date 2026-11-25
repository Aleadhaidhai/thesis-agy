"""多路结果融合与重排。

1. 加权 RRF（Reciprocal Rank Fusion）：score(d) = Σ_r w_r / (k + rank_r(d))
   仅依赖排名，无需对不同通路的异构分数做归一化，对稠密/稀疏/视觉三路天然适用。
2. 交叉编码器重排：bge-reranker-v2-m3 对 (query, MKU 内容) 精排。
3. 时效衰减：final = (1-λ)·rerank + λ·0.5^(Δdays / half_life)，企业知识存在“新结论覆盖旧结论”的特点。
"""
from __future__ import annotations

import math
import time
from functools import lru_cache

from eim.config import settings


def rrf(ranked_lists: dict[str, list[tuple[str, float]]], k: int | None = None,
        weights: dict[str, float] | None = None) -> list[tuple[str, float, dict[str, int]]]:
    k = k or settings.rrf_k
    weights = weights or {}
    agg: dict[str, float] = {}
    src: dict[str, dict[str, int]] = {}
    for name, lst in ranked_lists.items():
        w = weights.get(name, 1.0)
        for rank, (doc_id, _) in enumerate(lst, start=1):
            agg[doc_id] = agg.get(doc_id, 0.0) + w / (k + rank)
            src.setdefault(doc_id, {})[name] = rank
    return sorted(((d, s, src[d]) for d, s in agg.items()), key=lambda x: -x[1])


def time_decay(ts: float, now: float | None = None, half_life_days: float | None = None) -> float:
    now = now or time.time()
    hl = half_life_days or settings.time_decay_half_life_days
    days = max(0.0, (now - ts) / 86400)
    return math.pow(0.5, days / hl)


class Reranker:
    """bge-reranker-v2-m3 交叉编码器（基于 transformers 直接推理，输出经 sigmoid 归一化到 [0,1]）。"""

    def __init__(self, model: str | None = None):
        self.model_name = model or settings.rerank_model
        self._m = None

    def _load(self):
        if self._m is None:
            import torch
            from transformers import AutoModelForSequenceClassification, AutoTokenizer
            from eim.knowledge.embedder import _device
            self._dev = _device()
            self._tok = AutoTokenizer.from_pretrained(self.model_name)
            kw = {"dtype": torch.float16} if self._dev in ("mps", "cuda") else {}
            self._m = AutoModelForSequenceClassification.from_pretrained(self.model_name, **kw).eval().to(self._dev)
        return self._m

    def score_pairs(self, pairs: list[tuple[str, str]], max_len: int = 512, batch_size: int = 16) -> list[float]:
        if not pairs:
            return []
        import torch
        m = self._load()
        out: list[float] = []
        for i in range(0, len(pairs), batch_size):
            batch = [[q, d[:1500]] for q, d in pairs[i:i + batch_size]]
            enc = self._tok(batch, padding=True, truncation=True, max_length=max_len, return_tensors="pt")
            enc = {k: v.to(self._dev) for k, v in enc.items()}
            with torch.no_grad():
                logits = m(**enc).logits.view(-1).float()
            out.extend(torch.sigmoid(logits).cpu().tolist())
        return out

    def score(self, query: str, docs: list[str], max_len: int = 512, batch_size: int = 16) -> list[float]:
        return self.score_pairs([(query, d) for d in docs], max_len=max_len, batch_size=batch_size)


@lru_cache(maxsize=1)
def get_reranker() -> Reranker:
    return Reranker()
