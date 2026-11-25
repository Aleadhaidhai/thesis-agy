"""第 7 章系统功能测试与性能测试脚本。

用法：
  1. 启动测试服务（EIM_DATA_DIR=data_demo 等指向演示库）后运行在线测试：
     python eval_system.py --online
  2. 停止服务（释放 Milvus 单写锁）后运行分阶段耗时分解（检索子步骤 + Agent 节点）：
     python eval_system.py --stages
"""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import re
import statistics
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
RUNS = ROOT / "experiments" / "runs"
OUT_PATH = RUNS / "system_eval.json"
REFUSAL_RE = re.compile(r"无法确定|没有找到|未找到|没有相关|无相关|无法回答|不清楚|暂无|没有权限|无权|未提及|没有提到|未包含|无法得知")


def pct(vals: list[float], q: float) -> float:
    if not vals:
        return 0.0
    s = sorted(vals)
    idx = min(len(s) - 1, max(0, int(round(q * (len(s) - 1)))))
    return round(s[idx], 2)


def run_online(base_url: str) -> dict:
    c = httpx.Client(base_url=base_url, timeout=180.0)
    func_tests = []

    def record(tid: str, name: str, fn):
        t0 = time.perf_counter()
        try:
            ok, detail = fn()
        except Exception as e:  # noqa: BLE001
            ok, detail = False, f"Exception: {e}"
        ms = round((time.perf_counter() - t0) * 1000, 1)
        row = {"id": tid, "name": name, "ok": bool(ok), "latency_ms": ms, "detail": detail}
        func_tests.append(row)
        print(f"[{tid}] {'PASS' if ok else 'FAIL'} ({ms}ms) - {name}: {detail}", flush=True)
        return row

    # FT-01: Users
    record("FT-01", "用户与机器人列表初始化", lambda: (
        (us := c.get("/im/users").json()) and None,
        (len(us) == 21 and any(u["user_id"] == "bot_xiaozhi" and u["is_bot"] for u in us),
         f"users={len(us)}, bot_present={any(u['user_id']=='bot_xiaozhi' for u in us)}")
    )[-1])

    # FT-02: Authorized convs & 403 isolation
    def _ft02():
        convs = c.get("/im/convs", params={"user_id": "u_xiaochen"}).json()
        cids = {x["conv_id"] for x in convs}
        r403 = c.get("/im/convs/c_mgmt/messages", params={"user_id": "u_xiaochen"})
        ok = {"c_backend", "c_all", "c_onboard"}.issubset(cids) and ("c_mgmt" not in cids) and r403.status_code == 403
        return ok, f"visible={sorted(cids)}, c_mgmt_status={r403.status_code}"
    record("FT-02", "群聊列表可见性与越权访问拦截", _ft02)

    # FT-03: Text QA + source card
    ft03_qa_id = [None]
    def _ft03():
        r = c.post("/api/ask", json={
            "user_id": "u_huangtao",
            "conv_id": "c_backend",
            "question": "订单服务数据库连接池的maximumPoolSize参数在什么时候被调整了？",
        }).json()
        ft03_qa_id[0] = r.get("qa_id")
        cits = r.get("citations", [])
        card_cits = r.get("card", {}).get("citations", [])
        ok = bool(r.get("answer")) and len(cits) >= 1 and len(card_cits) >= 1
        return ok, f"qa_id={ft03_qa_id[0]}, n_cit={len(cits)}, ans={r['answer'][:70]}"
    record("FT-03", "文本问答与引用来源卡片生成", _ft03)

    # FT-04: Multimodal image QA
    def _ft04():
        r = c.post("/api/ask", json={
            "user_id": "u_tangming",
            "conv_id": "c_backend",
            "question": "8 月 11 日用户中心刷新 token 失败的错误码是什么？该错误的根因是什么？",
        }).json()
        ans = r.get("answer", "")
        cits = r.get("citations", [])
        ok = bool(ans) and len(cits) >= 1 and any(x.get("conv_id") == "c_backend" for x in cits)
        return ok, f"n_cit={len(cits)}, ans={ans[:75]}"
    record("FT-04", "多模态截图问答检索与作答", _ft04)

    # FT-05: Permission isolation QA
    def _ft05():
        r = c.post("/api/ask", json={
            "user_id": "u_xiaochen",
            "conv_id": "",
            "question": "公司 B 轮融资是谁领投的？估值多少？",
        }).json()
        cits = r.get("citations", [])
        ans = r.get("answer", "")
        no_mgmt = all(x.get("conv_id") != "c_mgmt" for x in cits)
        refused = bool(REFUSAL_RE.search(ans))
        return no_mgmt and refused, f"c_mgmt_cits={sum(1 for x in cits if x.get('conv_id')=='c_mgmt')}, refused={refused}, ans={ans[:65]}"
    record("FT-05", "跨群问答权限隔离验证", _ft05)

    # FT-06: Unanswerable refusal
    def _ft06():
        r = c.post("/api/ask", json={
            "user_id": "u_lina",
            "conv_id": "c_backend",
            "question": "支付服务的 Redis 集群一共有多少个节点？",
        }).json()
        ans = r.get("answer", "")
        refused = bool(REFUSAL_RE.search(ans))
        return refused, f"refused={refused}, ans={ans[:65]}"
    record("FT-06", "无答案问题诚实拒答验证", _ft06)

    # FT-07: Feedback + Admin stats
    def _ft07():
        assert ft03_qa_id[0] is not None
        fb = c.post("/api/feedback", json={"qa_id": ft03_qa_id[0], "score": 1}).json()
        st = c.get("/admin/stats").json()
        ok = fb.get("ok") and st.get("qa_like", 0) >= 1 and st.get("qa_total", 0) >= 4
        return ok, f"qa_total={st.get('qa_total')}, qa_like={st.get('qa_like')}, mkus={st.get('mkus')}, vecs={st.get('vectors')}"
    record("FT-07", "用户反馈提交与后台统计刷新", _ft07)

    # FT-08: Admin MKU filtering & QA logs trace
    def _ft08():
        mkus = c.get("/admin/mkus", params={"conv_id": "c_backend", "kind": "attachment", "limit": 20}).json()
        logs = c.get("/admin/qa_logs", params={"limit": 10}).json()
        has_trace = bool(logs and isinstance(logs[0].get("trace"), list) and len(logs[0]["trace"]) >= 2)
        ok = len(mkus) >= 1 and has_trace
        return ok, f"attachment_mkus={len(mkus)}, qa_logs={len(logs)}, trace_steps={len(logs[0]['trace']) if logs else 0}"
    record("FT-08", "管理后台 MKU 筛选与推理轨迹查看", _ft08)

    # FT-09: File upload & download (CSV table attachment)
    def _ft09():
        raw = "节点,显存占用,温度\ngpu-node-04,42%,58℃\n".encode("utf-8")
        r = c.post(
            "/im/convs/c_onboard/messages",
            data={"user_id": "u_xiaochen", "text": "同步测试节点 gpu-node-04 资源检查表"},
            files={"file": ("node_check.csv", raw, "text/csv")},
        ).json()
        att = r.get("attachment") or {}
        fid = att.get("file_id")
        dl = c.get(f"/im/files/{fid}") if fid else None
        ok = r.get("type") == "file" and dl is not None and dl.status_code == 200 and len(dl.content) == len(raw)
        return ok, f"msg_type={r.get('type')}, file_id={fid}, dl_bytes={len(dl.content) if dl else 0}"
    record("FT-09", "IM 多模态文件上传与下载接口", _ft09)

    # FT-10: Incremental ingest + immediate queryability
    ingest_res = {}
    def _ft10():
        post = c.post("/im/convs/c_onboard/messages", data={
            "user_id": "u_zhangwei",
            "text": "【新人规范补充】2026年11月起新人试用期导师双周反馈表统一提交至内网教务系统，截止时间为隔周周五 18:00。",
        }).json()
        ing = c.post("/admin/ingest", params={"full": "false"}).json()
        ingest_res.update(ing)
        ask = c.post("/api/ask", json={
            "user_id": "u_xiaochen",
            "conv_id": "c_onboard",
            "question": "新人试用期导师双周反馈表提交到哪里，截止时间是什么时候？",
        }).json()
        ans = ask.get("answer", "")
        ok = ing.get("messages", 0) >= 2 and ing.get("mkus", 0) >= 1 and ("内网教务系统" in ans or "18:00" in ans)
        return ok, f"msg_id={post.get('msg_id')}, ingest={ing}, ans={ans[:70]}"
    record("FT-10", "增量同步入库与新知识立即可检验证", _ft10)

    # Performance 1: HTTP Read API concurrency (1, 4, 8, 16)
    read_bench = []
    for threads in (1, 4, 8, 16):
        n_req = 48
        def _hit_read(_):
            with httpx.Client(base_url=base_url, timeout=30.0) as cli:
                t0 = time.perf_counter()
                r = cli.get("/admin/mkus", params={"limit": 20})
                return (r.status_code == 200), (time.perf_counter() - t0) * 1000
        t0 = time.perf_counter()
        with concurrent.futures.ThreadPoolExecutor(max_workers=threads) as ex:
            res = list(ex.map(_hit_read, range(n_req)))
        wall = time.perf_counter() - t0
        lats = [x[1] for x in res if x[0]]
        errs = sum(1 for x in res if not x[0])
        row = {
            "threads": threads, "n_req": n_req, "wall_s": round(wall, 3),
            "qps": round(len(lats) / wall, 2),
            "mean_ms": round(statistics.mean(lats), 2) if lats else 0.0,
            "p50_ms": pct(lats, 0.50), "p95_ms": pct(lats, 0.95),
            "errors": errs,
        }
        read_bench.append(row)
        print(f"[READ c={threads:2d}] QPS={row['qps']} mean={row['mean_ms']}ms p95={row['p95_ms']}ms err={errs}", flush=True)

    # Performance 2: /api/ask concurrency (1, 2, 4)
    qa_bench = []
    sample_qs = [
        {"user_id": "u_huangtao", "conv_id": "c_backend", "question": "订单服务现在的数据库连接池 maximumPoolSize 是多少？"},
        {"user_id": "u_zhoujie", "conv_id": "c_backend", "question": "《云岚后端接口设计规范 v1.2》中默认超时时间是多少？"},
        {"user_id": "u_yangxue", "conv_id": "c_product", "question": "灵犀 V1.1 需求池中 R-101 的人日预估是多少？"},
        {"user_id": "u_tangming", "conv_id": "c_sre", "question": "9 月 12 日晚 gpu-node-03 的显存占用率是多少？"},
    ]
    for threads in (1, 2, 4):
        n_req = 4
        def _hit_ask(i):
            payload = sample_qs[i % len(sample_qs)]
            with httpx.Client(base_url=base_url, timeout=600.0) as cli:
                t0 = time.perf_counter()
                try:
                    r = cli.post("/api/ask", json=payload)
                    ok = r.status_code == 200 and bool(r.json().get("answer"))
                except Exception:  # noqa: BLE001
                    ok = False
                return ok, (time.perf_counter() - t0) * 1000
        t0 = time.perf_counter()
        with concurrent.futures.ThreadPoolExecutor(max_workers=threads) as ex:
            res = list(ex.map(_hit_ask, range(n_req)))
        wall = time.perf_counter() - t0
        lats = [x[1] for x in res if x[0]]
        errs = sum(1 for x in res if not x[0])
        row = {
            "threads": threads, "n_req": n_req, "wall_s": round(wall, 3),
            "qps": round(len(lats) / wall, 3),
            "mean_ms": round(statistics.mean(lats), 1) if lats else 0.0,
            "p50_ms": pct(lats, 0.50), "p95_ms": pct(lats, 0.95),
            "errors": errs,
        }
        qa_bench.append(row)
        print(f"[ASK  c={threads:2d}] QPS={row['qps']} mean={row['mean_ms']}ms p95={row['p95_ms']}ms err={errs}", flush=True)

    return {
        "functional_tests": func_tests,
        "incremental_ingest": ingest_res,
        "read_concurrency": read_bench,
        "ask_concurrency": qa_bench,
    }


def run_stages(data_dir: Path) -> dict:
    # Delay heavy backend imports until needed, pointing EIM_* at data_dir
    os.environ["EIM_DATA_DIR"] = str(data_dir)
    os.environ["EIM_SQLITE_PATH"] = str(data_dir / "eim.db")
    os.environ["EIM_MILVUS_URI"] = str(data_dir / "milvus.db")
    os.environ["EIM_BLOB_DIR"] = str(ROOT / "data" / "blobs")

    from common import load_qa
    from eim.agent.graph import KnowledgeAgent
    from eim.config import settings
    from eim.knowledge.embedder import get_clip_embedder, get_text_embedder
    from eim.retrieval.bm25 import BM25Index
    from eim.retrieval.fusion import get_reranker, rrf, time_decay
    from eim.retrieval.retriever import Hit, HybridRetriever, RetrievalConfig
    from eim.storage.db import DB
    from eim.storage.vectorstore import VectorStore

    db = DB(data_dir / "eim.db")
    vs = VectorStore(str(data_dir / "milvus.db"))
    bm25 = BM25Index(data_dir / "bm25.pkl")
    retriever = HybridRetriever(db=db, vs=vs, bm25=bm25)

    # Pick 20 diverse retrieval queries (including warmup first)
    qas = [q for q in load_qa() if q["answerable"]]
    sel = []
    for key in ("text", "image", "document", "table", "audio", "temporal", "multihop"):
        sub = [q for q in qas if (q["modality"] if q["type"] == "single" else q["type"]) == key]
        sel.extend(sub[:3])
    sel = sel[:20]

    # Warmup models on MPS
    cfg = RetrievalConfig()
    _ = get_text_embedder().encode_query(sel[0]["question"])
    _ = get_clip_embedder().encode_text([sel[0]["question"]])
    _ = get_reranker().score(sel[0]["question"], ["预热文档内容"])

    ret_rows = []
    for q in sel:
        p = None  # stage timing independent of ACL string
        row = {}
        t_start = time.perf_counter()

        t0 = time.perf_counter()
        emb = get_text_embedder().encode_query(q["question"])
        row["embed_m3_ms"] = (time.perf_counter() - t0) * 1000

        t0 = time.perf_counter()
        d_res = vs.search_dense(emb["dense"], cfg.topk_dense, p)
        row["dense_ms"] = (time.perf_counter() - t0) * 1000

        t0 = time.perf_counter()
        s_res = vs.search_sparse(emb["sparse"], cfg.topk_sparse, p)
        row["sparse_ms"] = (time.perf_counter() - t0) * 1000

        t0 = time.perf_counter()
        b_res = bm25.search(q["question"], cfg.topk_sparse * 3, p)[:cfg.topk_sparse]
        row["bm25_ms"] = (time.perf_counter() - t0) * 1000

        t0 = time.perf_counter()
        qv = get_clip_embedder().encode_text([q["question"]])[0]
        vis = vs.search_visual(qv, cfg.topk_visual, p)
        v_res = [(i, sc) for i, sc in vis if sc >= settings.visual_min_sim]
        row["visual_clip_ms"] = (time.perf_counter() - t0) * 1000

        t0 = time.perf_counter()
        fused = rrf({"dense": d_res, "sparse": s_res, "bm25": b_res, "visual": v_res}, weights=cfg.weights)[:cfg.rerank_pool]
        mkus = db.get_mkus([d for d, _, _ in fused])
        hits = [Hit(mku=mkus[d], score=s, sources=src) for d, s, src in fused if d in mkus]
        row["rrf_sqlite_ms"] = (time.perf_counter() - t0) * 1000

        t0 = time.perf_counter()
        scores = get_reranker().score(q["question"], [h.mku.content for h in hits])
        for h, s in zip(hits, scores):
            h.score = s
        if hits:
            now = max(h.mku.ts_end for h in hits)
            for h in hits:
                h.score = (1 - settings.time_decay_weight) * h.score + settings.time_decay_weight * time_decay(h.mku.ts_end, now=now)
        hits.sort(key=lambda h: -h.score)
        row["rerank_ms"] = (time.perf_counter() - t0) * 1000
        row["total_ms"] = (time.perf_counter() - t_start) * 1000
        ret_rows.append(row)

    ret_summary = {
        k: {"mean_ms": round(statistics.mean(r[k] for r in ret_rows), 2), "p95_ms": pct([r[k] for r in ret_rows], 0.95)}
        for k in ret_rows[0]
    }
    print("RETRIEVAL STAGES:", json.dumps(ret_summary, ensure_ascii=False))

    # Agent node timing via timed subclass
    class TimedAgent(KnowledgeAgent):
        def __init__(self, *a, **kw):
            self.timings: dict[str, list[float]] = {}
            super().__init__(*a, **kw)

        def _rec(self, name: str, fn, s):
            t0 = time.perf_counter()
            out = fn(s)
            self.timings.setdefault(name, []).append((time.perf_counter() - t0) * 1000)
            return out

        def understand(self, s): return self._rec("understand", super().understand, s)
        def retrieve(self, s): return self._rec("retrieve", super().retrieve, s)
        def reflect(self, s): return self._rec("reflect", super().reflect, s)
        def generate(self, s): return self._rec("generate", super().generate, s)
        def verify(self, s): return self._rec("verify", super().verify, s)

    agent = TimedAgent(retriever=retriever, db=db)
    agent_qs = [sel[0], sel[3], sel[6], sel[9], sel[12], sel[15]]
    # warmup
    agent.ask(agent_qs[0]["question"], agent_qs[0]["asker"], None, agent_qs[0].get("conv_id", ""), [])
    agent.timings.clear()
    total_ms = []
    for q in agent_qs:
        t0 = time.perf_counter()
        agent.ask(q["question"], q["asker"], None, q.get("conv_id", ""), [])
        total_ms.append((time.perf_counter() - t0) * 1000)

    node_summary = {}
    for k, vals in agent.timings.items():
        # Note retrieve/reflect may trigger >1 call in multi-hop; record per-call mean & per-query total sum/n_queries
        node_summary[k] = {
            "calls": len(vals),
            "per_call_mean_ms": round(statistics.mean(vals), 1),
            "per_query_mean_ms": round(sum(vals) / len(agent_qs), 1),
        }
    node_summary["total_e2e"] = {"calls": len(agent_qs), "per_query_mean_ms": round(statistics.mean(total_ms), 1), "p95_ms": pct(total_ms, 0.95)}
    print("AGENT NODES:", json.dumps(node_summary, ensure_ascii=False))

    ingest_stats = {}
    for v in ("full", "nosummary", "ocronly", "noctx", "fixedwin"):
        p = RUNS / "index" / v / "build_stats.json"
        if p.exists():
            ingest_stats[v] = json.loads(p.read_text())

    return {
        "retrieval_stages_20q": ret_summary,
        "agent_nodes_6q": node_summary,
        "build_stats": ingest_stats,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--online", action="store_true")
    ap.add_argument("--stages", action="store_true")
    ap.add_argument("--base-url", default="http://127.0.0.1:8000")
    ap.add_argument("--data-dir", default=str(ROOT / "data_demo"))
    args = ap.parse_args()

    saved = json.loads(OUT_PATH.read_text()) if OUT_PATH.exists() else {}
    if args.online:
        saved["online"] = run_online(args.base_url)
    if args.stages:
        saved["stages"] = run_stages(Path(args.data_dir))
    OUT_PATH.write_text(json.dumps(saved, ensure_ascii=False, indent=2))
    print("saved", OUT_PATH)


if __name__ == "__main__":
    main()
