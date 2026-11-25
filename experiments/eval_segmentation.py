"""话题切分实验：与金标准话题标注对比。

指标：
- NMI / ARI：聚类一致性；
- 1-1 Overlap（Elsner & Charniak 2008）：话题间最优一对一匹配后被正确归属的消息比例；
- Exact-F1（Kummerfeld et al. 2019）：预测话题与金标准话题完全一致的 F1。
方法：本文在线切分（完整 / 去语义 / 去结构 / 去时间）、固定窗口、时间间隔切分。
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict

import numpy as np
from common import DATASET, RUNS, retriever_for
from scipy.optimize import linear_sum_assignment
from sklearn.metrics import adjusted_rand_score, normalized_mutual_info_score

from eim.knowledge.embedder import get_text_embedder
from eim.knowledge.indexer import _seg_text
from eim.knowledge.segmentation import FixedWindowSegmenter, TopicSegmenter, is_low_info


def one_to_one(gold: list[str], pred: list[str]) -> float:
    g_ids, p_ids = sorted(set(gold)), sorted(set(pred))
    gi, pi = {g: i for i, g in enumerate(g_ids)}, {p: i for i, p in enumerate(p_ids)}
    M = np.zeros((len(g_ids), len(p_ids)))
    for g, p in zip(gold, pred):
        M[gi[g], pi[p]] += 1
    r, c = linear_sum_assignment(-M)
    return M[r, c].sum() / len(gold)


def exact_f1(gold: list[str], pred: list[str]) -> float:
    gs, ps = defaultdict(set), defaultdict(set)
    for i, (g, p) in enumerate(zip(gold, pred)):
        gs[g].add(i)
        ps[p].add(i)
    G = {frozenset(v) for v in gs.values()}
    P = {frozenset(v) for v in ps.values()}
    tp = len(G & P)
    prec, rec = tp / len(P), tp / len(G)
    return 2 * prec * rec / (prec + rec) if prec + rec else 0.0


METHODS = {
    "Ours(full)": lambda: TopicSegmenter(),
    "Ours-w/o-semantic": lambda: TopicSegmenter(use_semantic=False, threshold=0.3),
    "Ours-w/o-structure": lambda: TopicSegmenter(use_structure=False),
    "Ours-w/o-time": lambda: TopicSegmenter(gamma=0.0, threshold=0.45 * 0.8 / 1.0),
    "FixedWindow(10)": lambda: FixedWindowSegmenter(window=10, gap_min=10_000),
    "TimeGap(30min)": lambda: FixedWindowSegmenter(window=10_000, gap_min=30),
}


DEV_CONVS = {"c_backend", "c_frontend", "c_qa", "c_sales"}   # 参数选择用的开发集会话，其余 6 个会话为测试集


def score_on(cache, gold_of, make, convs):
    golds, preds = [], []
    for cid, (msgs, texts, vecs) in cache.items():
        if cid not in convs:
            continue
        topics = make().segment(cid, msgs, texts, vecs)
        p_of = {mid: t.topic_id for t in topics for mid in t.msg_ids}
        golds += [f"{cid}:{gold_of[m.msg_id]}" for m in msgs]
        preds += [f"{cid}:{p_of[m.msg_id]}" for m in msgs]
    return {"NMI": normalized_mutual_info_score(golds, preds), "ARI": adjusted_rand_score(golds, preds),
            "1-1": one_to_one(golds, preds), "ExactF1": exact_f1(golds, preds)}


def tune(cache, gold_of):
    """参数选择：目标为 (1-1 + Exact-F1)/2；各消融变体同样在开发集上独立选择阈值，保证公平。"""
    import itertools
    dev = DEV_CONVS
    test = set(cache) - dev
    obj = lambda r: (r["1-1"] + r["ExactF1"]) / 2  # noqa: E731
    ths = [0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60]
    grid = []
    for (a, b, g), th, tau in itertools.product([(0.5, 0.3, 0.2), (0.6, 0.3, 0.1), (0.4, 0.4, 0.2), (0.5, 0.4, 0.1),
                                                (0.6, 0.2, 0.2), (0.7, 0.2, 0.1)], ths, [15, 30, 60]):
        mk = lambda a=a, b=b, g=g, th=th, tau=tau: TopicSegmenter(alpha=a, beta=b, gamma=g, threshold=th, tau_min=tau)
        grid.append(((a, b, g, th, tau), score_on(cache, gold_of, mk, dev)))
    grid.sort(key=lambda x: -obj(x[1]))
    for p, r in grid[:5]:
        print("DEV", p, {k: round(float(v), 4) for k, v in r.items()})
    a, b, g, th, tau = grid[0][0]
    out = {"objective": "(1-1 + ExactF1)/2", "best_params": {"alpha": a, "beta": b, "gamma": g, "threshold": th,
                                                              "tau_min": tau},
           "dev_top": [{"params": p, **{k: round(float(v), 4) for k, v in r.items()}} for p, r in grid[:10]], "test": {}}

    def best_th(factory):
        cands = [(t, score_on(cache, gold_of, lambda t=t: factory(t), dev)) for t in ths]
        return max(cands, key=lambda x: obj(x[1]))[0]

    fams = {
        "Ours": lambda t: TopicSegmenter(alpha=a, beta=b, gamma=g, threshold=t, tau_min=tau),
        "Ours-w/o-semantic": lambda t: TopicSegmenter(alpha=a, beta=b, gamma=g, threshold=t, tau_min=tau, use_semantic=False),
        "Ours-w/o-structure": lambda t: TopicSegmenter(alpha=a, beta=b, gamma=g, threshold=t, tau_min=tau, use_structure=False),
        "Ours-w/o-time": lambda t: TopicSegmenter(alpha=a, beta=b, gamma=0.0, threshold=t, tau_min=tau),
    }
    methods = {}
    for name, f in fams.items():
        t = best_th(f)
        out.setdefault("thresholds", {})[name] = t
        methods[name] = (lambda f=f, t=t: f(t))
    methods["FixedWindow(10)"] = lambda: FixedWindowSegmenter(window=10, gap_min=10_000)
    methods["TimeGap(30min)"] = lambda: FixedWindowSegmenter(window=10_000, gap_min=30)
    for name, mk in methods.items():
        r = score_on(cache, gold_of, mk, test)
        out["test"][name] = {k: round(float(v), 4) for k, v in r.items()}
        out["test"][name]["n_pred"] = sum(len(mk().segment(c, *cache[c])) for c in test)
        print("TEST", f"{name:20s}", out["test"][name], out.get("thresholds", {}).get(name), flush=True)
    out["n_gold_test"] = len({gold_of[m.msg_id] for c in test for m in cache[c][0]})
    (RUNS / "segmentation_tuned.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", default="full", help="复用该变体中已解析的消息文本")
    ap.add_argument("--tune", action="store_true", help="在开发集会话上网格搜索参数，在测试集会话上报告")
    args = ap.parse_args()
    ds = json.loads(DATASET.read_text())
    gold_of = {m["msg_id"]: m["gold_topic"] for m in ds["messages"]}
    _, _, db = retriever_for(args.variant)
    convs = db.list_conversations()
    cache = {}
    for conv in convs:
        msgs = db.get_messages(conv.conv_id)
        parsed = db.get_parsed([m.msg_id for m in msgs])
        texts = {m.msg_id: _seg_text(m, parsed.get(m.msg_id, [])) for m in msgs}
        ids = [i for i, t in texts.items() if t and not is_low_info(t)]
        dense = get_text_embedder().encode([texts[i] for i in ids], sparse=False)["dense"] if ids else []
        cache[conv.conv_id] = (msgs, texts, dict(zip(ids, dense)))
    if args.tune:
        tune(cache, gold_of)
        return
    results = {}
    for name, make in METHODS.items():
        golds, preds, per_conv = [], [], {}
        for cid, (msgs, texts, vecs) in cache.items():
            topics = make().segment(cid, msgs, texts, vecs)
            p_of = {mid: t.topic_id for t in topics for mid in t.msg_ids}
            g = [gold_of[m.msg_id] for m in msgs]
            p = [p_of[m.msg_id] for m in msgs]
            golds += [f"{cid}:{x}" for x in g]
            preds += [f"{cid}:{x}" for x in p]
            per_conv[cid] = round(one_to_one(g, p), 4)
        results[name] = {"NMI": round(normalized_mutual_info_score(golds, preds), 4),
                         "ARI": round(adjusted_rand_score(golds, preds), 4),
                         "1-1": round(one_to_one(golds, preds), 4), "ExactF1": round(exact_f1(golds, preds), 4),
                         "n_pred_topics": len(set(preds)), "n_gold_topics": len(set(golds)), "per_conv_1-1": per_conv}
        r = results[name]
        print(f"{name:20s} NMI={r['NMI']:.3f} ARI={r['ARI']:.3f} 1-1={r['1-1']:.3f} F1={r['ExactF1']:.3f} "
              f"#pred={r['n_pred_topics']} #gold={r['n_gold_topics']}", flush=True)
    (RUNS / "segmentation.json").write_text(json.dumps(results, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
