"""基于 LangGraph 的检索规划 Agent。

状态图：
    understand ──► (chitchat) ──► chitchat ──► END
        │  └────► (clarify) ───► clarify ───► END
        ▼
    retrieve ◄──────────────┐
        ▼                   │ search / expand_context（≤ max_iters）
    reflect ────────────────┘
        ▼ answer
    generate ──► verify ──► END

- understand：结合会话上下文做指代消解与查询改写，识别意图、模态、时间与会话范围约束，必要时拆分子查询；
- retrieve：调用权限感知混合检索工具，多查询结果合并去重；
- reflect：检索充分性自反思——结合重排分数阈值与 LLM 判断，决定回答、换查询重检或扩展上下文；
- generate：引用约束生成，证据编号化，要求逐句标注来源；
- verify：引用校验，剔除无效编号，并以交叉编码器校验“句子-证据”支撑度，过滤无支撑引用。
"""
from __future__ import annotations

import re
import time
from datetime import datetime
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from eim.agent import prompts as P
from eim.config import settings
from eim.knowledge.mku_builder import fmt_ts
from eim.llm import get_llm
from eim.models import Answer, Citation, Modality
from eim.retrieval.fusion import get_reranker
from eim.retrieval.retriever import Hit, HybridRetriever, RetrievalConfig
from eim.storage.db import DB


class AgentState(TypedDict, total=False):
    question: str
    user_id: str
    conv_id: str
    principals: set[str]
    history: list[str]
    understanding: dict
    queries: list[str]
    hits: list[Hit]
    iters: int
    reflection: dict
    answer: str
    citations: list[Citation]
    trace: list[dict]


class AgentConfig:
    def __init__(self, use_understand: bool = True, use_reflect: bool = True, use_verify: bool = True,
                 max_iters: int | None = None, retrieval: RetrievalConfig | None = None, evidence_k: int = 6):
        self.use_understand = use_understand
        self.use_reflect = use_reflect
        self.use_verify = use_verify
        self.max_iters = max_iters or settings.agent_max_iters
        self.retrieval = retrieval or RetrievalConfig()
        self.evidence_k = evidence_k


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def _to_ts(s: str, end: bool = False) -> float | None:
    if not s:
        return None
    try:
        d = datetime.strptime(s[:10], "%Y-%m-%d")
        return d.timestamp() + (86399 if end else 0)
    except ValueError:
        return None


def format_evidence(hits: list[Hit], max_chars: int = 700) -> str:
    out = []
    for i, h in enumerate(hits, 1):
        m = h.mku
        kind = "会话记录" if m.kind == "dialog" else f"附件/{m.modalities[0].value if m.modalities else ''}"
        out.append(f"[{i}]（{kind}｜{fmt_ts(m.ts_end)}）\n{m.content[:max_chars]}")
    return "\n\n".join(out)


class KnowledgeAgent:
    def __init__(self, retriever: HybridRetriever | None = None, db: DB | None = None,
                 cfg: AgentConfig | None = None):
        self.db = db or DB()
        self.retriever = retriever or HybridRetriever(db=self.db)
        self.cfg = cfg or AgentConfig()
        self.llm = get_llm()
        self.graph = self._build()

    # ------------------------------------------------------------------ nodes
    def understand(self, s: AgentState) -> AgentState:
        q = s["question"]
        if not self.cfg.use_understand:
            u = {"intent": "knowledge_qa", "standalone_query": q, "sub_queries": []}
        else:
            conv = self.db.get_conversation(s.get("conv_id", "")) if s.get("conv_id") else None
            u = self.llm.chat_json([{"role": "user", "content": P.UNDERSTAND.format(
                now=_now(), conv_name=conv.name if conv else "私聊", history="\n".join(s.get("history", [])[-8:]) or "（无）",
                question=q)}], max_tokens=400) or {}
            u.setdefault("intent", "knowledge_qa")
            u["standalone_query"] = u.get("standalone_query") or q
        queries = [u["standalone_query"]] + [x for x in (u.get("sub_queries") or []) if x and x != u["standalone_query"]]
        return {"understanding": u, "queries": queries[:4], "iters": 0, "hits": [],
                "trace": s.get("trace", []) + [{"node": "understand", "output": u}]}

    def _filters(self, u: dict, question: str = "") -> tuple[str, list[str] | None]:
        parts = []
        tr = u.get("time_range") or {}
        a, b = _to_ts(tr.get("start", "")), _to_ts(tr.get("end", ""), end=True)
        if a:
            parts.append(f"ts_end >= {a}")
        if b:
            parts.append(f"ts_end <= {b}")
        scope = None
        hint = (u.get("conv_hint") or "").strip()
        # 仅当用户在问题中显式提到会话名称时才限定会话范围，避免模型把“提问所在会话”误作检索范围
        core = hint.replace("群聊", "").replace("群", "").strip()
        if hint and core and core in question:
            convs = [c for c in self.db.list_conversations() if hint in c.name or c.name in hint]
            scope = [c.conv_id for c in convs] or None
        return " and ".join(parts), scope

    def retrieve(self, s: AgentState) -> AgentState:
        u = s.get("understanding", {})
        extra, scope = self._filters(u, s["question"])
        cfg = self.cfg.retrieval
        if u.get("intent") == "find_image" or u.get("modality") == "image":
            cfg = RetrievalConfig(**{**cfg.__dict__, "weights": {**cfg.weights, "visual": 1.0}})
        merged: dict[str, Hit] = {h.mku.mku_id: h for h in s.get("hits", [])}
        new_q = s["queries"][-1:] if s.get("iters", 0) > 0 else s["queries"]
        info_all = []
        for q in new_q:
            hits, info = self.retriever.retrieve(q, s.get("principals"), cfg, extra_filter=extra, conv_scope=scope)
            if not hits and (extra or scope):   # 约束过严时放宽重试
                hits, info = self.retriever.retrieve(q, s.get("principals"), cfg)
            info_all.append({"query": q, **info})
            for h in hits:
                if h.mku.mku_id not in merged or merged[h.mku.mku_id].score < h.score:
                    merged[h.mku.mku_id] = h
        hits = sorted(merged.values(), key=lambda h: -h.score)
        mod = u.get("modality", "any")
        if mod in {m.value for m in Modality} and mod != "text":   # 模态偏好：同分时优先目标模态
            hits.sort(key=lambda h: -(h.score + (0.05 if Modality(mod) in h.mku.modalities else 0)))
        return {"hits": hits[: max(self.cfg.evidence_k * 2, 10)], "iters": s.get("iters", 0) + 1,
                "trace": s["trace"] + [{"node": "retrieve", "queries": new_q, "info": info_all,
                                        "top": [(h.mku.mku_id, round(h.score, 3)) for h in hits[:8]]}]}

    def reflect(self, s: AgentState) -> AgentState:
        hits = s["hits"][: self.cfg.evidence_k]
        top = max((h.rerank if h.rerank is not None else h.score for h in hits), default=0.0)
        if not self.cfg.use_reflect:
            return {"reflection": {"next_action": "answer"}}
        if s["iters"] >= self.cfg.max_iters:
            r = {"next_action": "answer", "reason": "max_iters"}
        else:
            r = self.llm.chat_json([{"role": "user", "content": P.REFLECT.format(
                question=s["understanding"].get("standalone_query", s["question"]), queries=s["queries"],
                evidence=format_evidence(hits, 400) or "（无）")}], max_tokens=300) or {}
            # 规则兜底：最高重排分低于阈值时标记低置信，生成阶段需显式提示不确定性
            if top < settings.agent_min_evidence_score:
                r["low_confidence"] = True
            if r.get("sufficient") is True:
                r["next_action"] = "answer"
        out: AgentState = {"reflection": r, "trace": s["trace"] + [{"node": "reflect", "top_score": top, "output": r}]}
        if r.get("next_action") == "search" and r.get("next_query") and r["next_query"] not in s["queries"]:
            out["queries"] = s["queries"] + [r["next_query"]]
        elif r.get("next_action") == "expand_context":
            out["hits"] = self._expand(s["hits"], r.get("expand_id"))
            out["reflection"] = {**r, "next_action": "answer"}
        else:
            out["reflection"] = {**r, "next_action": "answer"}
        if r.get("useful_ids"):
            keep = {int(i) for i in r["useful_ids"] if str(i).isdigit()}
            hs = out.get("hits", s["hits"])
            if keep:
                out["hits"] = [h for i, h in enumerate(hs, 1) if i in keep] + \
                              [h for i, h in enumerate(hs, 1) if i not in keep]
        return out

    def _expand(self, hits: list[Hit], expand_id) -> list[Hit]:
        """扩展上下文：取证据所属话题的相邻会话单元，补充前因后果。"""
        try:
            idx = int(expand_id) - 1
            h = hits[idx]
        except (TypeError, ValueError, IndexError):
            return hits
        rows = self.db.conn.execute("SELECT mku_id FROM mkus WHERE topic_id=? AND kind='dialog'",
                                    (h.mku.topic_id,)).fetchall()
        extra = self.db.get_mkus([r[0] for r in rows])
        have = {x.mku.mku_id for x in hits}
        add = [Hit(mku=m, score=h.score - 1e-3, sources={"expand": 1}) for i, m in extra.items() if i not in have]
        return hits[: idx + 1] + add + hits[idx + 1:]

    def generate(self, s: AgentState) -> AgentState:
        # 相关性门限：剔除重排分数过低的证据，防止模型基于无关证据“强行作答”
        hits = [h for h in s["hits"] if h.rerank is None or h.rerank >= settings.agent_evidence_floor]
        hits = hits[: self.cfg.evidence_k]
        if not hits:
            return {"answer": "抱歉，在你有权限访问的群聊和文件中没有找到相关记录。", "citations": [],
                    "trace": s["trace"] + [{"node": "generate", "empty": True}]}
        ans = self.llm.chat([{"role": "user", "content": P.ANSWER.format(
            now=_now(), question=s["understanding"].get("standalone_query", s["question"]),
            evidence=format_evidence(hits))}], max_tokens=800, temperature=0.1)
        return {"answer": ans, "hits": hits, "trace": s["trace"] + [{"node": "generate"}]}

    def verify(self, s: AgentState) -> AgentState:
        hits, ans = s["hits"], s["answer"]
        n = len(hits)
        removed = []
        if self.cfg.use_verify and n:
            # 1) 剔除越界编号；2) 交叉编码器校验句子与被引证据的支撑度
            sents = re.split(r"(?<=[。！？\n])", ans)
            pairs, locs = [], []
            for si, sent in enumerate(sents):
                for mm in re.finditer(r"\[(\d+)\]", sent):
                    k = int(mm.group(1))
                    if 1 <= k <= n:
                        clean = re.sub(r"\[\d+\]", "", sent).strip()
                        if len(clean) >= 6:
                            pairs.append((clean, hits[k - 1].mku.content))
                            locs.append((si, k))
            if pairs:
                try:
                    scores = get_reranker().score_pairs(pairs)
                except Exception:
                    scores = [1.0] * len(pairs)
                for (si, k), sc in zip(locs, scores):
                    if sc < 0.02:     # 极低支撑度视为无效引用
                        sents[si] = sents[si].replace(f"[{k}]", "")
                        removed.append(k)
            ans = "".join(sents)
            ans = re.sub(r"\[(\d+)\]", lambda m: m.group(0) if 1 <= int(m.group(1)) <= n else "", ans)
        used = sorted({int(x) for x in re.findall(r"\[(\d+)\]", ans) if 1 <= int(x) <= n})
        cits = [Citation(index=i, mku_id=hits[i - 1].mku.mku_id, conv_id=hits[i - 1].mku.conv_id,
                         msg_ids=hits[i - 1].mku.evidence[:5], snippet=hits[i - 1].mku.content[:160]) for i in used]
        return {"answer": ans, "citations": cits,
                "trace": s["trace"] + [{"node": "verify", "used": used, "removed": removed}]}

    def chitchat(self, s: AgentState) -> AgentState:
        return {"answer": self.llm.chat([{"role": "user", "content": P.CHITCHAT.format(question=s["question"])}],
                                        max_tokens=200), "citations": []}

    def clarify(self, s: AgentState) -> AgentState:
        return {"answer": s["understanding"].get("clarify_question") or "能再具体描述一下你要找的内容吗？",
                "citations": []}

    # ------------------------------------------------------------------ graph
    @staticmethod
    def _route_understand(s: AgentState) -> str:
        u = s["understanding"]
        if u.get("intent") == "chitchat":
            return "chitchat"
        if u.get("intent") == "clarify" and u.get("clarify_question"):
            return "clarify"
        return "retrieve"

    def _build(self):
        g = StateGraph(AgentState)
        for name in ("understand", "retrieve", "reflect", "generate", "verify", "chitchat", "clarify"):
            g.add_node(name, getattr(self, name))
        g.set_entry_point("understand")
        g.add_conditional_edges("understand", self._route_understand)
        g.add_edge("retrieve", "reflect")
        g.add_conditional_edges("reflect", lambda s: "retrieve" if s["reflection"].get("next_action") == "search"
                                and s["iters"] < self.cfg.max_iters else "generate")
        g.add_edge("generate", "verify")
        g.add_edge("verify", END)
        g.add_edge("chitchat", END)
        g.add_edge("clarify", END)
        return g.compile()

    # ------------------------------------------------------------------ API
    def ask(self, question: str, user_id: str, principals: set[str] | None, conv_id: str = "",
            history: list[str] | None = None) -> Answer:
        t0 = time.perf_counter()
        st: AgentState = self.graph.invoke({"question": question, "user_id": user_id, "conv_id": conv_id,
                                            "principals": principals, "history": history or [], "trace": []},
                                           config={"recursion_limit": 25})
        return Answer(question=question, answer=st.get("answer", ""), citations=st.get("citations", []),
                      trace=_jsonable(st.get("trace", [])), latency_ms=(time.perf_counter() - t0) * 1000)


def _jsonable(x: Any) -> Any:
    if isinstance(x, dict):
        return {k: _jsonable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_jsonable(v) for v in x]
    if isinstance(x, set):
        return sorted(x)
    if isinstance(x, (str, int, float, bool)) or x is None:
        return x
    return str(x)
