"""生成第 7 章实验结果可视化图表（300 DPI PNG，写入 thesis/figs/）。

用法：
  python plot_charts.py --retrieval   # 生成图 7.2、图 7.3
  python plot_charts.py --qa          # 生成图 7.4
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
RUNS = ROOT / "experiments" / "runs"
FIGS = ROOT / "thesis" / "figs"

plt.rcParams["font.sans-serif"] = ["Hiragino Sans GB", "Heiti TC", "Arial Unicode MS", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

COLORS = ["#4C78A8", "#F58518", "#54A24B", "#E45756", "#72B7B2", "#B279A2"]


def _grouped_bars(ax, labels, series, title, ylabel="指标值", ylim=(0.70, 1.04), bar_w=0.25, label_fmt="{:.3f}"):
    x = np.arange(len(labels))
    n = len(series)
    offsets = (np.arange(n) - (n - 1) / 2.0) * bar_w
    for idx, (sname, vals) in enumerate(series.items()):
        bars = ax.bar(x + offsets[idx], vals, width=bar_w * 0.92, label=sname, color=COLORS[idx % len(COLORS)], edgecolor="#333333", linewidth=0.4)
        for b, v in zip(bars, vals):
            ax.text(b.get_x() + b.get_width() / 2.0, v + 0.005, label_fmt.format(v), ha="center", va="bottom", fontsize=7.5, rotation=90)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=9)
    ax.set_ylim(*ylim)
    ax.set_ylabel(ylabel, fontsize=10)
    ax.set_title(title, fontsize=11, pad=8)
    ax.grid(axis="y", linestyle="--", alpha=0.35)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)


def plot_retrieval():
    FIGS.mkdir(parents=True, exist_ok=True)
    rf = json.load(open(RUNS / "retrieval_full.json"))["results"]
    methods = [
        ("BM25", "BM25"),
        ("Dense", "Dense"),
        ("Dense+Sparse", "Dense+\nSparse"),
        ("Hybrid(RRF)", "Hybrid\n(RRF)"),
        ("Hybrid+Rerank", "Hybrid+\nRerank"),
        ("Ours(full)", "Ours\n(full)"),
    ]
    s_cmp = {
        "Hit@1": [rf[k]["overall"]["Hit@1"] for k, _ in methods],
        "MRR@10": [rf[k]["overall"]["MRR@10"] for k, _ in methods],
        "nDCG@10": [rf[k]["overall"]["nDCG@10"] for k, _ in methods],
    }

    variants = [
        ("Ours(full)", "完整构建\n(Full)", rf["Ours(full)"]["overall"]),
        ("nosummary", "无摘要\n(nosummary)", json.load(open(RUNS / "retrieval_nosummary.json"))["results"]["Ours(full)"]["overall"]),
        ("noctx", "无指代补全\n(noctx)", json.load(open(RUNS / "retrieval_noctx.json"))["results"]["Ours(full)"]["overall"]),
        ("ocronly", "仅 OCR\n(ocronly)", json.load(open(RUNS / "retrieval_ocronly.json"))["results"]["Ours(full)"]["overall"]),
        ("fixedwin", "固定窗口\n(fixedwin)", json.load(open(RUNS / "retrieval_fixedwin.json"))["results"]["Ours(full)"]["overall"]),
    ]
    s_abl = {
        "Hit@1": [o["Hit@1"] for _, _, o in variants],
        "MRR@10": [o["MRR@10"] for _, _, o in variants],
        "nDCG@10": [o["nDCG@10"] for _, _, o in variants],
    }

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12.2, 4.6), dpi=300)
    _grouped_bars(ax1, [lbl for _, lbl in methods], s_cmp, "(a) SimEIM 不同检索方法对比", ylim=(0.76, 1.07), bar_w=0.25)
    _grouped_bars(ax2, [lbl for _, lbl, _ in variants], s_abl, "(b) SimEIM 知识构建模块消融对比", ylim=(0.82, 1.06), bar_w=0.25)
    handles, legend_labels = ax1.get_legend_handles_labels()
    fig.legend(handles, legend_labels, loc="upper center", ncol=3, frameon=False, fontsize=9.5, bbox_to_anchor=(0.5, 0.99))
    plt.tight_layout(rect=[0, 0, 1, 0.91])
    out1 = FIGS / "fig7_2_retrieval_simeim.png"
    fig.savefig(out1, dpi=300)
    plt.close(fig)

    pub = json.load(open(RUNS / "public_t2retrieval.json"))["results"]
    pub_keys = [
        ("BM25", "BM25"),
        ("Sparse(M3)", "Sparse\n(BGE-M3)"),
        ("Dense", "Dense\n(BGE-M3)"),
        ("Dense+Sparse", "Dense+\nSparse"),
        ("Dense+Sparse+BM25", "Dense+Sparse\n+BM25(RRF)"),
        ("Dense+Sparse+BM25+Rerank", "Dense+Sparse+\nBM25+Rerank"),
    ]
    s_pub = {
        "Recall@10": [pub[k]["Recall@10"] for k, _ in pub_keys],
        "nDCG@10": [pub[k]["nDCG@10"] for k, _ in pub_keys],
        "MRR@10": [pub[k]["MRR@10"] for k, _ in pub_keys],
    }
    fig2, ax = plt.subplots(figsize=(9.2, 4.5), dpi=300)
    _grouped_bars(ax, [lbl for _, lbl in pub_keys], s_pub, "C-MTEB T2Retrieval 公开中文检索基准对比（300 条查询，11,595 条语料）", ylim=(0.68, 1.07), bar_w=0.25)
    ax.legend(loc="upper left", ncol=3, frameon=False, fontsize=9.5)
    plt.tight_layout()
    out2 = FIGS / "fig7_3_retrieval_public.png"
    fig2.savefig(out2, dpi=300)
    plt.close(fig2)
    print("saved:", out1, out2)


def _compute_qa_summary(qa_path: Path) -> dict:
    saved = json.load(open(qa_path))
    if "summary" in saved and saved["summary"]:
        return saved["summary"]
    summary = {}
    for name, recs in saved["records"].items():
        g = defaultdict(list)
        for r in recs.values():
            g[r["type"]].append(r)
        ans = [r for r in recs.values() if "score" in r]
        cit = [x for r in ans for x in r["cit_rel"]]
        lat = sorted(r["latency_ms"] for r in recs.values())
        by = defaultdict(list)
        for r in ans:
            by[r["modality"] if r["type"] == "single" else r["type"]].append(r["score"])
        summary[name] = {
            "Acc": round(sum(r["score"] for r in ans) / max(1, len(ans)), 4),
            "KPR": round(sum(r["kpr"] for r in ans) / max(1, len(ans)), 4),
            "CitP": round(sum(cit) / max(1, len(cit)), 4),
            "Refusal(unans)": round(sum(r["refused"] for r in g["unanswerable"]) / max(1, len(g["unanswerable"])), 4),
            "Leak(perm)": round(sum(1 for r in g["permission"] if r["leaked"]) / max(1, len(g["permission"])), 4),
            "Temporal": round(sum(r.get("temporal_ok", False) for r in g["temporal"]) / max(1, len(g["temporal"])), 4),
            "lat_mean": round(sum(lat) / max(1, len(lat))),
            "by_group": {k: round(sum(v) / len(v), 4) for k, v in by.items()},
        }
    return summary


def plot_qa():
    FIGS.mkdir(parents=True, exist_ok=True)
    summary = _compute_qa_summary(RUNS / "qa_full.json")
    sys_keys = [
        ("NaiveRAG", "Naive\nRAG"),
        ("HybridRAG", "Hybrid\nRAG"),
        ("Ours(full)", "Ours\n(full)"),
        ("Ours-w/o-understand", "w/o\nUnderstand"),
        ("Ours-w/o-reflect", "w/o\nReflect"),
        ("Ours-w/o-verify", "w/o\nVerify"),
    ]
    s_main = {
        "准确率 Acc": [summary[k]["Acc"] for k, _ in sys_keys],
        "要点召回 KPR": [summary[k]["KPR"] for k, _ in sys_keys],
        "引用精确率 CitP": [summary[k]["CitP"] for k, _ in sys_keys],
    }

    groups = [("text", "文本"), ("image", "图片"), ("document", "文档"), ("table", "表格"), ("audio", "语音"), ("multihop", "多跳")]
    cmp_sys = [("NaiveRAG", "NaiveRAG"), ("HybridRAG", "HybridRAG"), ("Ours(full)", "Ours(full)")]
    s_grp = {lbl: [summary[k]["by_group"].get(gk, 0.0) for gk, _ in groups] for k, lbl in cmp_sys}

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12.2, 4.6), dpi=300)
    _grouped_bars(ax1, [lbl for _, lbl in sys_keys], s_main, "(a) 端到端问答系统与智能体消融整体对比", ylim=(0.65, 1.07), bar_w=0.25)
    ax1.legend(loc="lower right", ncol=1, frameon=True, fontsize=8.5, facecolor="white", framealpha=0.9)
    _grouped_bars(ax2, [lbl for _, lbl in groups], s_grp, "(b) 各模态及多跳问题准确率 Acc 对比", ylim=(0.45, 1.12), bar_w=0.25)
    ax2.legend(loc="lower right", ncol=1, frameon=True, fontsize=8.5, facecolor="white", framealpha=0.9)
    plt.tight_layout()
    out = FIGS / "fig7_4_qa_comparison.png"
    fig.savefig(out, dpi=300)
    plt.close(fig)
    print("saved:", out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--retrieval", action="store_true")
    ap.add_argument("--qa", action="store_true")
    args = ap.parse_args()
    if args.retrieval:
        plot_retrieval()
    if args.qa:
        plot_qa()


if __name__ == "__main__":
    main()
