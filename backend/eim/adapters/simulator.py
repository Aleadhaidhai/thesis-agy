"""IM 模拟器适配器。

本项目自研的轻量 IM 模拟器（群聊/单聊、文件/图片/语音消息、@机器人），用于在不接触企业真实数据的前提下
完成系统演示与评测。其数据独立存放于 im_sim.db，与知识库元数据库隔离，模拟“外部 IM 平台”。
企业 IM 的适配器实现与本类遵循同一接口。
"""
from __future__ import annotations

import asyncio
import json
import shutil
import sqlite3
import threading
import time
import uuid
from collections.abc import AsyncIterator, Iterable
from pathlib import Path

from eim.adapters.base import IMAdapter
from eim.config import settings
from eim.models import Attachment, Conversation, ConvType, Message, MsgType

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (user_id TEXT PRIMARY KEY, name TEXT, dept TEXT, title TEXT, is_bot INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS convs (conv_id TEXT PRIMARY KEY, name TEXT, type TEXT, dept TEXT, members TEXT);
CREATE TABLE IF NOT EXISTS msgs (
  msg_id TEXT PRIMARY KEY, conv_id TEXT, sender_id TEXT, ts REAL, type TEXT, text TEXT,
  attachment TEXT, reply_to TEXT, mentions TEXT, card TEXT
);
CREATE INDEX IF NOT EXISTS idx_sim_msgs ON msgs(conv_id, ts);
"""

BOT_ID = "bot_xiaozhi"
BOT_NAME = "小知"


class SimulatorAdapter(IMAdapter):
    name = "simulator"

    def __init__(self, path: str | Path | None = None, file_dir: str | Path | None = None):
        self.path = str(path or settings.data_dir / "im_sim.db")
        self.file_dir = Path(file_dir or settings.data_dir / "im_files")
        self.file_dir.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._subscribers: list[asyncio.Queue] = []
        with self.conn as c:
            c.executescript(SCHEMA)
            c.execute("INSERT OR IGNORE INTO users VALUES (?,?,?,?,1)", (BOT_ID, BOT_NAME, "", "知识助手"))

    @property
    def conn(self) -> sqlite3.Connection:
        c = getattr(self._local, "c", None)
        if c is None:
            c = sqlite3.connect(self.path, check_same_thread=False)
            c.row_factory = sqlite3.Row
            self._local.c = c
        return c

    # ------------------------------------------------------------ 管理
    def add_user(self, user_id: str, name: str, dept: str = "", title: str = ""):
        with self.conn as c:
            c.execute("INSERT OR REPLACE INTO users VALUES (?,?,?,?,0)", (user_id, name, dept, title))

    def add_conversation(self, conv: Conversation):
        with self.conn as c:
            c.execute("INSERT OR REPLACE INTO convs VALUES (?,?,?,?,?)",
                      (conv.conv_id, conv.name, conv.type.value, conv.dept, json.dumps(conv.members)))

    def users(self) -> list[dict]:
        return [dict(r) for r in self.conn.execute("SELECT * FROM users")]

    def user_name(self, uid: str) -> str:
        r = self.conn.execute("SELECT name FROM users WHERE user_id=?", (uid,)).fetchone()
        return r[0] if r else uid

    def store_file(self, src: str | Path, name: str | None = None) -> Attachment:
        src = Path(src)
        fid = uuid.uuid4().hex[:12]
        dst = self.file_dir / fid / (name or src.name)      # 每个文件独立目录，保留原始文件名
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(src, dst)
        return Attachment(file_id=fid, name=name or src.name, mime=_mime(dst), size=dst.stat().st_size, path=str(dst))

    def post(self, conv_id: str, sender_id: str, text: str = "", type: MsgType = MsgType.TEXT,
             attachment: Attachment | None = None, reply_to: str | None = None, mentions: list[str] | None = None,
             ts: float | None = None, msg_id: str | None = None, card: dict | None = None,
             notify: bool = True) -> Message:
        m = Message(msg_id=msg_id or uuid.uuid4().hex[:16], conv_id=conv_id, sender_id=sender_id,
                    sender_name=self.user_name(sender_id), ts=ts or time.time(), type=type, text=text,
                    attachment=attachment, reply_to=reply_to, mentions=mentions or [])
        with self.conn as c:
            c.execute("INSERT OR REPLACE INTO msgs VALUES (?,?,?,?,?,?,?,?,?,?)",
                      (m.msg_id, conv_id, sender_id, m.ts, m.type.value, text,
                       attachment.model_dump_json() if attachment else None, reply_to, json.dumps(m.mentions),
                       json.dumps(card, ensure_ascii=False) if card else None))
        if notify:
            for q in list(self._subscribers):
                q.put_nowait(m)
        return m

    def messages(self, conv_id: str, limit: int = 200, before_ts: float | None = None) -> list[dict]:
        q, args = "SELECT * FROM msgs WHERE conv_id=?", [conv_id]
        if before_ts:
            q += " AND ts<?"
            args.append(before_ts)
        rows = self.conn.execute(q + " ORDER BY ts DESC LIMIT ?", args + [limit]).fetchall()
        out = []
        for r in reversed(rows):
            d = dict(r)
            d["attachment"] = json.loads(d["attachment"]) if d["attachment"] else None
            d["mentions"] = json.loads(d["mentions"] or "[]")
            d["card"] = json.loads(d["card"]) if d["card"] else None
            d["sender_name"] = self.user_name(d["sender_id"])
            out.append(d)
        return out

    def recent_context(self, conv_id: str, n: int = 8, before_ts: float | None = None) -> list[str]:
        return [f"{m['sender_name']}：{m['text'] or (m['attachment'] or {}).get('name', '')}"
                for m in self.messages(conv_id, n, before_ts)]

    # ------------------------------------------------------------ IMAdapter
    def list_conversations(self) -> list[Conversation]:
        return [Conversation(conv_id=r["conv_id"], name=r["name"], type=ConvType(r["type"]), dept=r["dept"] or "",
                             members=json.loads(r["members"])) for r in self.conn.execute("SELECT * FROM convs")]

    def conversations_of(self, user_id: str) -> list[Conversation]:
        return [c for c in self.list_conversations() if user_id in c.members]

    def fetch_history(self, conv_id: str, since_ts: float = 0.0) -> Iterable[Message]:
        rows = self.conn.execute("SELECT * FROM msgs WHERE conv_id=? AND ts>? AND sender_id!=? ORDER BY ts",
                                 (conv_id, since_ts, BOT_ID)).fetchall()
        for r in rows:
            yield Message(msg_id=r["msg_id"], conv_id=r["conv_id"], sender_id=r["sender_id"],
                          sender_name=self.user_name(r["sender_id"]), ts=r["ts"], type=MsgType(r["type"]),
                          text=r["text"] or "",
                          attachment=Attachment(**json.loads(r["attachment"])) if r["attachment"] else None,
                          reply_to=r["reply_to"], mentions=json.loads(r["mentions"] or "[]"))

    def download_attachment(self, att: Attachment, dest_dir: str) -> str:
        return att.path or str(self.file_dir / att.file_id)

    async def events(self) -> AsyncIterator[Message]:
        q: asyncio.Queue = asyncio.Queue()
        self._subscribers.append(q)
        try:
            while True:
                yield await q.get()
        finally:
            self._subscribers.remove(q)

    async def send_message(self, conv_id: str, text: str, reply_to: str | None = None,
                           card: dict | None = None) -> str:
        return self.post(conv_id, BOT_ID, text, reply_to=reply_to, card=card).msg_id

    def get_user_principals(self, user_id: str) -> set[str]:
        p = {f"user:{user_id}"}
        p |= {f"conv:{c.conv_id}" for c in self.conversations_of(user_id)}
        r = self.conn.execute("SELECT dept FROM users WHERE user_id=?", (user_id,)).fetchone()
        if r and r[0]:
            p.add(f"dept:{r[0]}")
        return p


def _mime(p: Path) -> str:
    import mimetypes
    return mimetypes.guess_type(p.name)[0] or "application/octet-stream"
