"""面向 IM 会话的在线话题切分（会话解缠）。

群聊消息流中多个话题常交织出现，且单条消息短、口语化。本文将话题切分建模为
“消息 → 活跃话题”的在线归属问题：对新消息 m 与每个活跃话题 T 计算亲和度

    S(m, T) = α · Sim(m, T) + β · Rel(m, T) + γ · exp(-Δt / τ)

- Sim：m 的语义向量与 T 的近期加权质心的余弦相似度；
- Rel：显式结构关系——m 回复了 T 中的消息（1.0）、@了 T 中的近期发言人（0.6）、
       同一发言人在短时间内连续发言（0.5）；
- 时间项：Δt 为 m 与 T 最后一条消息的时间间隔，τ 为时间尺度。

若 max_T S(m, T) ≥ θ 则归入该话题，否则新建话题。对“好的/收到/+1”等低信息量短消息，
语义项不可靠，直接依据结构关系与时间就近原则归属。
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

import numpy as np

from eim.config import settings
from eim.models import MKU, Message, Topic

_LOW_INFO_RE = re.compile(
    r"^(好的?|好滴|嗯+|哦+|ok|OK|收到|明白|了解|可以|行|谢谢|多谢|感谢|辛苦了?|\+1|1|赞|👍|哈+|是的?|对的?|没问题)[！!。.~～]*$")


def is_low_info(text: str) -> bool:
    t = text.strip()
    return len(t) <= 2 or bool(_LOW_INFO_RE.match(t))


@dataclass
class _ActiveTopic:
    topic_id: str
    msg_ids: list[str] = field(default_factory=list)
    senders: list[str] = field(default_factory=list)
    centroid: np.ndarray | None = None
    ts_start: float = 0.0
    ts_end: float = 0.0

    def add(self, msg: Message, vec: np.ndarray | None, decay: float = 0.7):
        self.msg_ids.append(msg.msg_id)
        self.senders.append(msg.sender_id)
        if not self.ts_start:
            self.ts_start = msg.ts
        self.ts_end = msg.ts
        if vec is not None:
            # 指数滑动平均质心：近期消息权重更高，适应话题漂移
            self.centroid = vec.copy() if self.centroid is None else decay * self.centroid + (1 - decay) * vec
            self.centroid /= np.linalg.norm(self.centroid) + 1e-12


class TopicSegmenter:
    def __init__(self, alpha: float | None = None, beta: float | None = None, gamma: float | None = None,
                 threshold: float | None = None, tau_min: float | None = None, max_msgs: int | None = None,
                 active_window_h: float = 6.0, use_semantic: bool = True, use_structure: bool = True):
        self.alpha = settings.seg_alpha if alpha is None else alpha
        self.beta = settings.seg_beta if beta is None else beta
        self.gamma = settings.seg_gamma if gamma is None else gamma
        self.threshold = settings.seg_sim_threshold if threshold is None else threshold
        self.tau = 60.0 * (settings.seg_time_gap_min if tau_min is None else tau_min)
        self.max_msgs = max_msgs or settings.seg_max_msgs
        self.window = active_window_h * 3600
        self.use_semantic = use_semantic
        self.use_structure = use_structure

    # ------------------------------------------------------------------
    def relation(self, msg: Message, t: _ActiveTopic, msg2topic: dict[str, str], sender_of: dict[str, str]) -> float:
        if not self.use_structure:
            return 0.0
        if msg.reply_to and msg2topic.get(msg.reply_to) == t.topic_id:
            return 1.0
        recent = set(t.senders[-6:])
        if any(u in recent for u in msg.mentions):
            return 0.6
        if t.senders and t.senders[-1] == msg.sender_id and msg.ts - t.ts_end < 120:
            return 0.5
        return 0.0

    def score(self, msg: Message, vec: np.ndarray | None, t: _ActiveTopic, msg2topic, sender_of) -> float:
        sim = float(np.dot(vec, t.centroid)) if (self.use_semantic and vec is not None and t.centroid is not None) \
            else 0.0
        rel = self.relation(msg, t, msg2topic, sender_of)
        tim = math.exp(-max(0.0, msg.ts - t.ts_end) / self.tau)
        return self.alpha * sim + self.beta * rel + self.gamma * tim

    # ------------------------------------------------------------------
    def segment(self, conv_id: str, msgs: list[Message], texts: dict[str, str],
                vecs: dict[str, np.ndarray] | None = None) -> list[Topic]:
        """msgs 需按时间升序；texts 为每条消息的统一转写文本（附件取摘要）；vecs 为其语义向量。"""
        vecs = vecs or {}
        active: list[_ActiveTopic] = []
        closed: list[_ActiveTopic] = []
        msg2topic: dict[str, str] = {}
        sender_of = {m.msg_id: m.sender_id for m in msgs}
        n = 0
        for m in msgs:
            # 关闭超出活跃窗口或已满的话题
            still = []
            for t in active:
                (closed if (m.ts - t.ts_end > self.window or len(t.msg_ids) >= self.max_msgs) else still).append(t)
            active = still

            text = texts.get(m.msg_id, m.text)
            vec = vecs.get(m.msg_id)
            target: _ActiveTopic | None = None
            if active:
                if is_low_info(text) and not m.reply_to:
                    # 低信息量消息：结构关系优先，否则归入最近活跃话题
                    rels = [(self.relation(m, t, msg2topic, sender_of), t) for t in active]
                    best_rel, best_t = max(rels, key=lambda x: (x[0], x[1].ts_end))
                    target = best_t if best_rel > 0 else max(active, key=lambda t: t.ts_end)
                else:
                    scored = [(self.score(m, vec, t, msg2topic, sender_of), t) for t in active]
                    best, best_t = max(scored, key=lambda x: x[0])
                    if best >= self.threshold:
                        target = best_t
            if target is None:
                n += 1
                target = _ActiveTopic(topic_id=MKU.make_id(conv_id, "topic", m.msg_id))
                active.append(target)
            target.add(m, None if is_low_info(text) else vec)
            msg2topic[m.msg_id] = target.topic_id

        return [Topic(topic_id=t.topic_id, conv_id=conv_id, msg_ids=t.msg_ids, ts_start=t.ts_start, ts_end=t.ts_end)
                for t in sorted(closed + active, key=lambda t: t.ts_start)]


class FixedWindowSegmenter:
    """基线：固定窗口切分（按 N 条消息或时间间隔），用于对比实验。"""

    def __init__(self, window: int = 10, gap_min: float = 30.0):
        self.window = window
        self.gap = gap_min * 60

    def segment(self, conv_id: str, msgs: list[Message], *_, **__) -> list[Topic]:
        topics, cur = [], []
        for m in msgs:
            if cur and (len(cur) >= self.window or m.ts - cur[-1].ts > self.gap):
                topics.append(cur)
                cur = []
            cur.append(m)
        if cur:
            topics.append(cur)
        return [Topic(topic_id=MKU.make_id(conv_id, "win", t[0].msg_id), conv_id=conv_id,
                      msg_ids=[m.msg_id for m in t], ts_start=t[0].ts, ts_end=t[-1].ts) for t in topics]
