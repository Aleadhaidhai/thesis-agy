"""SimEIM 组装：渲染附件、为话题分配时间并交错排布（制造多话题交织），输出数据集与金标准话题标注。

输出 build/simeim.json:
{
  users, conversations,
  messages: [{msg_id, conv_id, sender_id, ts, type, text, attachment_path, reply_to, mentions, gold_topic, seed_id, key}],
  topics:   {topic_id: {conv, seed_id|None, noise, topic}}
}
"""
from __future__ import annotations

import argparse
import json
import random
from datetime import datetime, timedelta
from pathlib import Path

from render import render

HERE = Path(__file__).resolve().parent


def parse_dt(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%d %H:%M")


def schedule(msgs: list[dict], start: datetime, rnd: random.Random, delay_p: float = 0.0) -> list[float]:
    """为话题内消息分配时间。delay_p：模拟“隔一段时间才回复”的延迟回复概率（间隔 40~150 分钟）。"""
    ts, t = [], start
    for i, _ in enumerate(msgs):
        if i:
            if rnd.random() < delay_p and i >= 2:
                t += timedelta(minutes=rnd.uniform(40, 150))
            else:
                t += timedelta(seconds=rnd.choice([20, 40, 60, 90, 120, 180, 300, 600]) * rnd.uniform(0.6, 1.4))
        ts.append(t.timestamp())
    return ts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--threads", default=str(HERE / "build" / "threads.json"))
    ap.add_argument("--out", default=str(HERE / "build" / "simeim.json"))
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--interleave", type=float, default=0.6, help="噪声话题与事实话题时间重叠的比例")
    ap.add_argument("--delay-p", type=float, default=0.08, help="事实话题内延迟回复的概率")
    args = ap.parse_args()
    rnd = random.Random(args.seed)
    world = json.loads((HERE / "world.json").read_text())
    seeds = {json.loads(l)["id"]: json.loads(l) for l in (HERE / "seeds.jsonl").read_text().splitlines() if l.strip()}
    data = json.loads(Path(args.threads).read_text())
    att_dir = HERE / "build" / "files"
    start, end = parse_dt(world["start_date"] + " 09:00"), parse_dt(world["end_date"] + " 18:00")

    messages, topics = [], {}
    fact_times: dict[str, list[datetime]] = {}
    for sid, th in data["facts"].items():
        tid = f"T_{sid}"
        topics[tid] = {"conv": th["conv"], "seed_id": sid, "noise": False, "topic": th["topic"]}
        t0 = parse_dt(th["date"])
        fact_times.setdefault(th["conv"], []).append(t0)
        ts = schedule(th["messages"], t0, rnd, args.delay_p)
        att_path = None
        if th.get("attachment"):
            att_path = str(render(th["attachment"], att_dir, sid))
        for i, (m, t) in enumerate(zip(th["messages"], ts)):
            mid = f"{sid}_m{i:02d}"
            is_att = bool(m.get("attachment"))
            kind = (th["attachment"] or {}).get("kind") if is_att else None
            mtype = "text"
            if is_att:
                mtype = "image" if kind in ("terminal", "form", "chart", "diagram") else \
                    "audio" if kind == "audio" else "file"
            rt = m.get("reply_to")
            messages.append({
                "msg_id": mid, "conv_id": th["conv"], "sender_id": m["speaker"], "ts": t, "type": mtype,
                "text": "" if mtype == "audio" else (m.get("text") or ""),
                "attachment_path": att_path if is_att else None,
                "reply_to": f"{sid}_m{int(rt):02d}" if isinstance(rt, int) and 0 <= rt < i else None,
                "mentions": [u for u in (m.get("mentions") or []) if isinstance(u, str) and u.startswith("u_")],
                "gold_topic": tid, "seed_id": sid, "key": bool(m.get("key")) or is_att})

    for cid, ths in data["noise"].items():
        anchors = fact_times.get(cid, [])
        for k, th in enumerate(ths):
            tid = f"N_{cid}_{k:02d}"
            topics[tid] = {"conv": cid, "seed_id": None, "noise": True, "topic": th["topic"]}
            if anchors and rnd.random() < args.interleave:
                # 与某个事实话题时间重叠，形成交织
                t0 = rnd.choice(anchors) + timedelta(minutes=rnd.uniform(1, 20))
            else:
                day = start + timedelta(days=rnd.uniform(0, (end - start).days))
                t0 = day.replace(hour=rnd.choice([9, 10, 11, 13, 14, 15, 16, 17]), minute=rnd.randrange(60))
            ts = schedule(th["messages"], t0, rnd)
            for i, (m, t) in enumerate(zip(th["messages"], ts)):
                rt = m.get("reply_to")
                messages.append({
                    "msg_id": f"{tid}_m{i:02d}", "conv_id": cid, "sender_id": m["speaker"], "ts": t, "type": "text",
                    "text": m.get("text") or "", "attachment_path": None,
                    "reply_to": f"{tid}_m{int(rt):02d}" if isinstance(rt, int) and 0 <= rt < i else None,
                    "mentions": [u for u in (m.get("mentions") or []) if isinstance(u, str) and u.startswith("u_")],
                    "gold_topic": tid, "seed_id": None, "key": False})

    messages.sort(key=lambda m: (m["conv_id"], m["ts"]))
    out = {"meta": {"company": world["company"], "note": world["note"], "generated_at": datetime.now().isoformat()},
           "users": world["users"], "conversations": world["conversations"], "messages": messages, "topics": topics}
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=1))
    n_att = sum(1 for m in messages if m["attachment_path"])
    print(f"messages={len(messages)} topics={len(topics)} attachments={n_att}")


if __name__ == "__main__":
    main()
