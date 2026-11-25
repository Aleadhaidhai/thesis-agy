"""公开数据集检索实验：C-MTEB T2Retrieval（中文段落检索）。

用于在非饱和、可复现的公开基准上比较检索通路与融合/重排策略（与 SimEIM 结论互为补充）。
受单机算力限制，采用常见的“子采样语料”设置：随机抽取 N 条开发集查询，语料由这些查询的全部相关段落
加上随机抽取的干扰段落组成。所有方法使用同一子集，结论在方法间可比。

用法：python eval_public.py --n-queries 500 --n-distractors 20000
"""
from __future__ import annotations

import argparse
import json
import math
import random
import time
from collections import defaultdict

import numpy as np
import pandas as pd
from common import RUNS
from huggingface_hub import hf_hub_download

from eim.knowledge.embedder import get_text_embedder
from eim.retrieval.bm25 import tokenize
from eim.retrieval.fusion import get_reranker, rrf


def load(n_q: int, n_d: int, seed: int = 42):
    corpus = pd.read_parquet(hf_hub_download("C-MTEB/T2Retrieval", "data/corpus-00000-of-00001-8afe7b7a7eca49e3.parquet",
                                             repo_type="dataset"))
    queries = pd.read_parquet(hf_hub_download("C-MTEB/T2Retrieval", "data/queries-00000-of-00001-930bf3b805a80dd9.parquet",
                                              repo_type="dataset"))
    qrels = pd.read_parquet(hf_hub_download("C-MTEB/T2Retrieval-qrels", "data/dev-00000-of-00001-92ed0416056ff7e1.parquet",
                                            repo_type="dataset"))
    rel = defaultdict(dict)
    for r in qrels.itertuples():
        if r.score > 0:
            rel[str(r.qid)][str(r.pid)] = int(r.score)
    rnd = random.Random(seed)
    qids = sorted(q for q in rel if q in set(queries["id"].astype(str)))
    qids = rnd.sample(qids, min(n_q, len(qids)))
    qtext = dict(zip(queries["id"].astype(str), queries["text"]))
    need = {p for q in qids for p in rel[q]}
    ctext = dict(zip(corpus["id"].astype(str), corpus["text"]))
    others = [p for p in ctext if p not in need]
    pids = sorted(need) + rnd.sample(others, min(n_d, len(others)))
    return [(q, qtext[q]) for q in qids], {p: ctext[p] for p in pids}, {q: rel[q] for q in qids}


def ndcg10(ranked, rels):
    dcg = sum((2 ** rels.get(p, 0) - 1) / math.log2(i + 2) for i, p in enumerate(ranked[:10]))
    ideal = sorted(rels.values(), reverse=True)[:10]
    idcg = sum((2 ** g - 1) / math.log2(i + 2) for i, g in enumerate(ideal))
    return dcg / idcg if idcg else 0.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-queries", type=int, default=500)
    ap.add_argument("--n-distractors", type=int, default=20000)
    ap.add_argument("--max-len", type=int, default=512)
    a = ap.parse_args()
    t0 = time.time()
    queries, corpus, qrels = load(a.n_queries, a.n_distractors)
    pids = list(corpus)
    texts = [corpus[p] for p in pids]
    print(f"queries={len(queries)} corpus={len(pids)} load={time.time() - t0:.0f}s", flush=True)

    cache = RUNS / f"t2_cache_{len(queries)}_{len(pids)}.npz"
    emb = get_text_embedder()
    if cache.exists():
        z = np.load(cache, allow_pickle=True)
        D, S = z["D"], list(z["S"])
    else:
        t = time.time()
        enc = emb.encode(texts, batch_size=16, max_length=a.max_len)
        D, S = enc["dense"], enc["sparse"]
        np.savez(cache, D=D, S=np.array(S, dtype=object))
        print(f"encode corpus {time.time() - t:.0f}s", flush=True)
    from rank_bm25 import BM25Okapi
    bm = BM25Okapi([tokenize(x) for x in texts])
    inv = defaultdict(list)
    for i, sp in enumerate(S):
        for tok, w in sp.items():
            inv[tok].append((i, w))

    def search_sparse(qs, k):
        sc = defaultdict(float)
        for tok, w in qs.items():
            for i, dw in inv.get(tok, ()):
                sc[i] += w * dw
        return sorted(sc.items(), key=lambda x: -x[1])[:k]

    rr = get_reranker()
    systems = ["BM25", "Dense", "Sparse(M3)", "Dense+Sparse", "Dense+Sparse+BM25", "Dense+Sparse+BM25+Rerank"]
    res = {s: defaultdict(float) for s in systems}
    lat = {s: 0.0 for s in systems}
    K = 30
    for qi, (qid, q) in enumerate(queries):
        qe = emb.encode_query(q)
        t = time.perf_counter(); ds = D @ qe["dense"]; top = np.argsort(-ds)[:K]
        L = {"Dense": [(pids[i], float(ds[i])) for i in top]}; lat["Dense"] += time.perf_counter() - t
        t = time.perf_counter(); L["Sparse(M3)"] = [(pids[i], s) for i, s in search_sparse(qe["sparse"], K)]
        lat["Sparse(M3)"] += time.perf_counter() - t
        t = time.perf_counter(); bs = bm.get_scores(tokenize(q)); tb = np.argsort(-bs)[:K]
        L["BM25"] = [(pids[i], float(bs[i])) for i in tb]; lat["BM25"] += time.perf_counter() - t
        L["Dense+Sparse"] = [(d, s) for d, s, _ in rrf({"d": L["Dense"], "s": L["Sparse(M3)"]},
                                                       weights={"d": 1.0, "s": 0.7})]
        L["Dense+Sparse+BM25"] = [(d, s) for d, s, _ in rrf({"d": L["Dense"], "s": L["Sparse(M3)"], "b": L["BM25"]},
                                                            weights={"d": 1.0, "s": 0.7, "b": 0.7})]
        t = time.perf_counter()
        cand = [d for d, _ in L["Dense+Sparse+BM25"][:K]]
        sc = rr.score(q, [corpus[d] for d in cand], max_len=512)
        L["Dense+Sparse+BM25+Rerank"] = sorted(zip(cand, sc), key=lambda x: -x[1])
        lat["Dense+Sparse+BM25+Rerank"] += time.perf_counter() - t
        for s in systems:
            ranked = [d for d, _ in L[s]]
            rels = qrels[qid]
            res[s]["nDCG@10"] += ndcg10(ranked, rels)
            res[s]["Recall@10"] += len(set(ranked[:10]) & set(rels)) / len(rels)
            res[s]["MRR@10"] += next((1 / (i + 1) for i, d in enumerate(ranked[:10]) if d in rels), 0.0)
        if (qi + 1) % 100 == 0:
            print(qi + 1, {s: round(res[s]["nDCG@10"] / (qi + 1), 4) for s in systems}, flush=True)
    n = len(queries)
    out = {s: {k: round(v / n, 4) for k, v in res[s].items()} for s in systems}
    for s in systems:
        print(f"{s:28s}", out[s])
    (RUNS / "public_t2retrieval.json").write_text(json.dumps(
        {"n_queries": n, "corpus": len(pids), "results": out}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
