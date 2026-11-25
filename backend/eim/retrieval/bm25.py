"""BM25 词法检索（jieba 分词）。作为稀疏通路的经典基线，对错误码、工号、版本号等精确词项召回效果好。"""
from __future__ import annotations

import pickle
import re
from pathlib import Path

import jieba
from rank_bm25 import BM25Okapi

from eim.config import settings

jieba.setLogLevel(60)
_STOP = set("的 了 和 是 在 我 你 他 她 它 们 这 那 就 都 也 吗 呢 吧 啊 哦 嗯 与 及 或 对 把 被 给 让 从 到 为 以 于 上 下 中 "
            "一个 什么 怎么 如何 哪些 哪个 是否 有没有 请问 一下 我们 你们 他们".split())
_TOKEN_RE = re.compile(r"[A-Za-z0-9_.\-]+|[\u4e00-\u9fff]")


def tokenize(text: str) -> list[str]:
    toks = []
    for w in jieba.lcut_for_search(text.lower()):
        w = w.strip()
        if not w or w in _STOP or not _TOKEN_RE.search(w):
            continue
        toks.append(w)
    return toks


class BM25Index:
    def __init__(self, path: Path | None = None):
        self.path = path or (settings.data_dir / "bm25.pkl")
        self.ids: list[str] = []
        self.docs: list[list[str]] = []
        self.acl: list[set[str]] = []
        self.bm25: BM25Okapi | None = None
        self.inv: dict[str, set[int]] = {}
        if self.path.exists():
            self.load()

    def build(self, items: list[tuple[str, str, list[str]]]):
        """items: (mku_id, content, acl)"""
        self.ids = [i for i, _, _ in items]
        self.docs = [tokenize(t) for _, t, _ in items]
        self.acl = [set(a) for _, _, a in items]
        self.bm25 = BM25Okapi(self.docs) if self.docs else None
        self._build_inv()
        self.save()

    def _build_inv(self):
        self.inv: dict[str, set[int]] = {}
        for i, d in enumerate(self.docs):
            for t in set(d):
                self.inv.setdefault(t, set()).add(i)

    def search(self, query: str, k: int, principals: set[str] | None = None) -> list[tuple[str, float]]:
        if self.bm25 is None:
            return []
        q = tokenize(query)
        if not q:
            return []
        scores = self.bm25.get_scores(q)
        qs = set(q)
        cand = {i for t in qs for i in self.inv.get(t, ())}       # 仅保留至少命中一个查询词的文档
        order = sorted(cand, key=lambda i: -scores[i])
        out = []
        for idx in order:
            if principals is not None and not (self.acl[idx] & principals):
                continue
            out.append((self.ids[idx], float(scores[idx])))
            if len(out) >= k:
                break
        return out

    def save(self):
        with open(self.path, "wb") as f:
            pickle.dump((self.ids, self.docs, self.acl), f)

    def load(self):
        with open(self.path, "rb") as f:
            self.ids, self.docs, self.acl = pickle.load(f)
        self.bm25 = BM25Okapi(self.docs) if self.docs else None
        self._build_inv()
