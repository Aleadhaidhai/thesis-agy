"""检索实验：对比基线与本文混合检索，并做检索层消融。

指标：Hit@K（Recall@K）、MRR@10、nDCG@10；按问题类型/模态分组统计；平均检索延迟。
相关性判定：检索到的 MKU 的证据消息集合与标注的证据消息集合有交集即视为相关。

用法：python eval_retrieval.py --variant full --configs all
"""
from __future__ import annotations

import argparse
import json
import math
import time
from collections import defaultdict

from common import RUNS, load_qa, retriever_for

from eim.retrieval.retriever import RetrievalConfig

CONFIGS = {
    "BM25": dict(use_dense=False, use_sparse=False, use_bm25=True, use_visual=False, use_rerank=False,
                 use_time_decay=False),
    "Dense": dict(use_dense=True, use_sparse=False, use_bm25=False, use_visual=False, use_rerank=False,
                  use_time_decay=False),
    "Dense+Sparse": dict(use_dense=True, use_sparse=True, use_bm25=False, use_visual=False, use_rerank=False,
                         use_time_decay=False),
    "Hybrid(RRF)": dict(use_dense=True, use_sparse=True, use_bm25=True, use_visual=True, use_rerank=False,
                        use_time_decay=False),
    "Hybrid+Rerank": dict(use_dense=True, use_sparse=True, use_bm25=True, use_visual=True, use_rerank=True,
                          use_time_decay=False),
    "Ours(full)": dict(),
    "Ours-w/o-visual": dict(use_visual=False),
    "Ours-w/o-bm25": dict(use_bm25=False),
    "Ours-w/o-sparse": dict(use_sparse=False),
}


def metrics(ranked_rel: list[bool], ks=(1, 3, 5, 10)) -> dict:
    out = {f"Hit@{k}": float(any(ranked_rel[:k])) for k in ks}
    rr = next((1 / (i + 1) for i, r in enumerate(ranked_rel[:10]) if r), 0.0)
    out["MRR@10"] = rr
    dcg = sum(1 / math.log2(i + 2) for i, r in enumerate(ranked_rel[:10]) if r)
    n_rel = sum(ranked_rel)
    idcg = sum(1 / math.log2(i + 2) for i in range(min(10, max(1, n_rel))))
    out["nDCG@10"] = dcg / idcg if idcg else 0.0
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", default="full")
    ap.add_argument("--configs", default="all")
    ap.add_argument("--topn", type=int, default=10)
    ap.add_argument("--tag", default="")
    args = ap.parse_args()
    retriever, sim, db = retriever_for(args.variant)
    qas = [q for q in load_qa() if q["answerable"] and q["gold_msgs"]]
    names = list(CONFIGS) if args.configs == "all" else args.configs.split(",")
    results, per_q = {}, defaultdict(dict)
    for name in names:
        cfg = RetrievalConfig(**{**CONFIGS[name], "topn": args.topn})
        agg, groups, lat = defaultdict(float), defaultdict(lambda: defaultdict(list)), []
        for q in qas:
            principals = sim.get_user_principals(q["asker"])
            t = time.perf_counter()
            hits, _ = retriever.retrieve(q["question"], principals, cfg)
            lat.append((time.perf_counter() - t) * 1000)
            gold = set(q["gold_msgs"])
            rel = [bool(gold & set(h.mku.evidence)) for h in hits]
            m = metrics(rel)
            per_q[q["qid"]][name] = {"rank": next((i + 1 for i, r in enumerate(rel) if r), None)}
            for k, v in m.items():
                agg[k] += v
                groups[q["type"] if q["type"] != "single" else q["modality"]][k].append(v)
        n = len(qas)
        results[name] = {"overall": {k: round(v / n, 4) for k, v in agg.items()},
                         "by_group": {g: {k: round(sum(v) / len(v), 4) for k, v in d.items()} | {"n": len(d["Hit@1"])}
                                      for g, d in groups.items()},
                         "latency_ms": {"mean": round(sum(lat) / n, 1), "p95": round(sorted(lat)[int(0.95 * n) - 1], 1)}}
        o = results[name]["overall"]
        print(f"{name:18s} Hit@1={o['Hit@1']:.3f} Hit@5={o['Hit@5']:.3f} Hit@10={o['Hit@10']:.3f} "
              f"MRR={o['MRR@10']:.3f} nDCG={o['nDCG@10']:.3f} lat={results[name]['latency_ms']['mean']}ms", flush=True)
    out = RUNS / f"retrieval_{args.variant}{args.tag}.json"
    out.write_text(json.dumps({"n_questions": len(qas), "results": results, "per_question": per_q},
                              ensure_ascii=False, indent=1))
    print("saved", out)


if __name__ == "__main__":
    main()
