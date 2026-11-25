"""将 SimEIM 数据集导入 IM 模拟器（模拟“企业 IM 平台中已有的历史消息”）。"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from eim.adapters.simulator import SimulatorAdapter
from eim.models import Conversation, ConvType, MsgType


def load_simeim(path: str | Path, sim: SimulatorAdapter | None = None) -> SimulatorAdapter:
    ds = json.loads(Path(path).read_text())
    sim = sim or SimulatorAdapter()
    for u in ds["users"]:
        sim.add_user(u["id"], u["name"], u.get("dept", ""), u.get("title", ""))
    for c in ds["conversations"]:
        sim.add_conversation(Conversation(conv_id=c["id"], name=c["name"], type=ConvType.GROUP,
                                          dept=c.get("dept", ""), members=c["members"]))
    for m in ds["messages"]:
        att = None
        if m.get("attachment_path"):
            p = Path(m["attachment_path"])
            if not p.is_absolute():
                p = Path(path).parent / p
            if m["type"] == "file":
                name = p.name.split("_", 1)[-1]          # 去掉种子编号前缀，保留文档原名
            else:                                         # 图片/语音使用 IM 常见的自动命名
                h = hashlib.md5(m["msg_id"].encode()).hexdigest()[:8]
                name = f"{'image' if m['type'] == 'image' else 'voice'}_{h}{p.suffix}"
            att = sim.store_file(p, name)
        sim.post(m["conv_id"], m["sender_id"], m.get("text", ""), type=MsgType(m["type"]), attachment=att,
                 reply_to=m.get("reply_to"), mentions=m.get("mentions", []), ts=m["ts"], msg_id=m["msg_id"],
                 notify=False)
    return sim
