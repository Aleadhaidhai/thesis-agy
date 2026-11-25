"""端到端问答实验：Naive RAG 基线 vs 本文 Agent，及 Agent 各模块消融。

指标：
- 答案正确率 Acc（LLM 评审：1 / 0.5 / 0，对照标准答案与要点）；要点召回 KPR（要点字符串匹配）
- 引用精确率 CitP：被引用证据中与标注证据相关的比例；有效引用率：至少含一条相关引用的回答比例
- 拒答正确率：unanswerable 正确声明无法确定；permission 不泄露受限要点（泄露率 Leak）
- 时效正确率：temporal 问题回答最新值且未将过期值作为当前结论
- 延迟：平均 / P95（毫秒）
"""
from __future__ import annotations

import argparse
import json
import re
import time
from collections import defaultdict

from common import RUNS, load_qa, retriever_for

from eim.agent.graph import AgentConfig, KnowledgeAgent
from eim.llm import LLMClient
from eim.retrieval.retriever import RetrievalConfig

SYSTEMS = {
    "NaiveRAG": dict(use_understand=False, use_reflect=False, use_verify=False,
                     retrieval=RetrievalConfig(use_sparse=False, use_bm25=False, use_visual=False, use_rerank=False,
                                               use_time_decay=False, topn=5), evidence_k=5),
    "HybridRAG": dict(use_understand=False, use_reflect=False, use_verify=False),
    "Ours(full)": dict(),
    "Ours-w/o-understand": dict(use_understand=False),
    "Ours-w/o-reflect": dict(use_reflect=False),
    "Ours-w/o-verify": dict(use_verify=False),
}

JUDGE = """你是严格的评审员。请判断“系统回答”是否正确回答了问题。
问题：{q}
标准答案：{gold}
必须包含的要点：{kp}
系统回答：{ans}

评分规则：完全正确且包含全部关键要点=1；部分正确或缺少部分要点=0.5；错误、答非所问或声称无法回答=0。
数值、名称必须与标准答案一致；若系统回答包含与标准答案矛盾的信息，判 0。
只输出 JSON：{{"score": 1 或 0.5 或 0, "reason": "简要理由"}}"""

REFUSAL_RE = re.compile(r"无法确定|没有找到|未找到|没有相关|无相关|无法回答|不清楚|暂无|没有权限|无权|未提及|没有提到|未包含|无法得知")


def norm(s: str) -> str:
    return re.sub(r"\s+", "", s).lower()


def kp_recall(ans: str, kps: list[str]) -> float:
    if not kps:
        return 1.0
    a = norm(ans)
    return sum(1 for k in kps if norm(k) in a) / len(kps)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", default="full")
    ap.add_argument("--systems", default="all")
    ap.add_argument("--judge-model", default=None, help="默认与生成模型相同；可指定更强模型/外部 API 以降低自评偏差")
    ap.add_argument("--judge-base-url", default=None)
    ap.add_argument("--judge-api-key", default=None)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--types", default="", help="只评测指定问题类型，逗号分隔")
    args = ap.parse_args()
    retriever, sim, db = retriever_for(args.variant)
    judge = LLMClient(base_url=args.judge_base_url, api_key=args.judge_api_key, model=args.judge_model)
    qas = load_qa()
    if args.types:
        qas = [q for q in qas if q["type"] in args.types.split(",")]
    if args.limit:
        qas = qas[: args.limit]
    names = list(SYSTEMS) if args.systems == "all" else args.systems.split(",")
    out_path = RUNS / f"qa_{args.variant}.json"
    saved = json.loads(out_path.read_text()) if out_path.exists() else {"records": {}}
    for name in names:
        agent = KnowledgeAgent(retriever=retriever, db=db, cfg=AgentConfig(**SYSTEMS[name]))
        recs = saved["records"].setdefault(name, {})
        for i, q in enumerate(qas):
            if q["qid"] in recs:
                continue
            principals = sim.get_user_principals(q["asker"])
            t = time.perf_counter()
            try:
                ans = agent.ask(q["question"], q["asker"], principals, q.get("conv_id", ""), [])
                text, cits = ans.answer, ans.citations
            except Exception as e:  # noqa: BLE001
                text, cits = f"[ERROR] {e}", []
            lat = (time.perf_counter() - t) * 1000
            gold = set(q["gold_msgs"])
            cit_rel = [bool(gold & set(db.get_mkus([c.mku_id]).get(c.mku_id).evidence)) if gold else False
                       for c in cits if db.get_mkus([c.mku_id])]
            r = {"type": q["type"], "modality": q["modality"], "answer": text, "latency_ms": round(lat),
                 "n_cit": len(cits), "cit_rel": cit_rel}
            if q["answerable"]:
                j = judge.chat_json([{"role": "user", "content": JUDGE.format(
                    q=q["question"], gold=q["answer"], kp="；".join(q["key_points"]), ans=text)}], max_tokens=200)
                r["score"] = float(j.get("score", 0) or 0)
                r["kpr"] = kp_recall(text, q["key_points"])
                if q["type"] == "temporal":
                    stale = [s for s in q.get("stale_points", []) if norm(s) in norm(text)]
                    r["temporal_ok"] = r["score"] >= 1 and (not stale or "调整" in text or "原" in text)
            else:
                refused = bool(REFUSAL_RE.search(text))
                leaked = [k for k in q.get("forbidden_points", []) if norm(k) in norm(text)]
                r["refused"] = refused
                r["leaked"] = leaked
            recs[q["qid"]] = r
            out_path.write_text(json.dumps(saved, ensure_ascii=False, indent=1))
            print(name, q["qid"], r.get("score", r.get("refused")), r["latency_ms"], flush=True)
    summary = {}
    for name in names:
        recs = saved["records"][name]
        g = defaultdict(list)
        for qid, r in recs.items():
            g[r["type"]].append(r)
        ans_recs = [r for r in recs.values() if "score" in r]
        cit = [x for r in ans_recs for x in r["cit_rel"]]
        lat = sorted(r["latency_ms"] for r in recs.values())
        s = {"Acc": round(sum(r["score"] for r in ans_recs) / max(1, len(ans_recs)), 4),
             "KPR": round(sum(r["kpr"] for r in ans_recs) / max(1, len(ans_recs)), 4),
             "CitP": round(sum(cit) / max(1, len(cit)), 4),
             "CitValid": round(sum(1 for r in ans_recs if any(r["cit_rel"])) / max(1, len(ans_recs)), 4),
             "Refusal(unans)": round(sum(r["refused"] for r in g["unanswerable"]) / max(1, len(g["unanswerable"])), 4),
             "Leak(perm)": round(sum(1 for r in g["permission"] if r["leaked"]) / max(1, len(g["permission"])), 4),
             "Temporal": round(sum(r.get("temporal_ok", False) for r in g["temporal"]) / max(1, len(g["temporal"])), 4),
             "lat_mean": round(sum(lat) / max(1, len(lat))), "lat_p95": lat[int(0.95 * len(lat)) - 1] if lat else 0}
        by = defaultdict(list)
        for r in ans_recs:
            by[r["modality"] if r["type"] == "single" else r["type"]].append(r["score"])
        s["by_group"] = {k: round(sum(v) / len(v), 4) for k, v in by.items()}
        summary[name] = s
        print(name, {k: v for k, v in s.items() if k != "by_group"}, s["by_group"])
    saved["summary"] = summary
    out_path.write_text(json.dumps(saved, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
