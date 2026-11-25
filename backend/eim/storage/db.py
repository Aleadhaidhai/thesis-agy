"""SQLite 元数据存储（原型）。生产环境可替换为 PostgreSQL，表结构保持一致。"""
from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Iterable
from pathlib import Path

from eim.config import settings
from eim.models import MKU, Conversation, Message, ParsedContent, Topic

SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    conv_id TEXT PRIMARY KEY, name TEXT, type TEXT, dept TEXT, members TEXT
);
CREATE TABLE IF NOT EXISTS messages (
    msg_id TEXT PRIMARY KEY, conv_id TEXT, sender_id TEXT, sender_name TEXT, ts REAL,
    type TEXT, text TEXT, attachment TEXT, reply_to TEXT, mentions TEXT,
    parsed INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_msg_conv_ts ON messages(conv_id, ts);
CREATE TABLE IF NOT EXISTS parsed_contents (
    id INTEGER PRIMARY KEY AUTOINCREMENT, msg_id TEXT, modality TEXT, text TEXT,
    chunk_index INTEGER, meta TEXT, image_path TEXT
);
CREATE INDEX IF NOT EXISTS idx_pc_msg ON parsed_contents(msg_id);
CREATE TABLE IF NOT EXISTS topics (
    topic_id TEXT PRIMARY KEY, conv_id TEXT, msg_ids TEXT, ts_start REAL, ts_end REAL
);
CREATE TABLE IF NOT EXISTS mkus (
    mku_id TEXT PRIMARY KEY, conv_id TEXT, topic_id TEXT, kind TEXT, modalities TEXT,
    title TEXT, content TEXT, evidence TEXT, ts_start REAL, ts_end REAL, acl TEXT,
    image_path TEXT, meta TEXT
);
CREATE TABLE IF NOT EXISTS sync_state (
    conv_id TEXT PRIMARY KEY, last_ts REAL
);
CREATE TABLE IF NOT EXISTS qa_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, conv_id TEXT, question TEXT,
    answer TEXT, citations TEXT, trace TEXT, latency_ms REAL, feedback INTEGER,
    created_at REAL DEFAULT (strftime('%s','now'))
);
"""


class DB:
    def __init__(self, path: Path | str | None = None):
        self.path = str(path or settings.sqlite_path)
        self._local = threading.local()
        with self.conn as c:
            c.executescript(SCHEMA)

    @property
    def conn(self) -> sqlite3.Connection:
        c = getattr(self._local, "conn", None)
        if c is None:
            c = sqlite3.connect(self.path, check_same_thread=False)
            c.row_factory = sqlite3.Row
            c.execute("PRAGMA journal_mode=WAL")
            self._local.conn = c
        return c

    # ---------- conversations ----------
    def upsert_conversation(self, conv: Conversation) -> None:
        with self.conn as c:
            c.execute("INSERT OR REPLACE INTO conversations VALUES (?,?,?,?,?)",
                      (conv.conv_id, conv.name, conv.type.value, conv.dept, json.dumps(conv.members)))

    def get_conversation(self, conv_id: str) -> Conversation | None:
        r = self.conn.execute("SELECT * FROM conversations WHERE conv_id=?", (conv_id,)).fetchone()
        if not r:
            return None
        return Conversation(conv_id=r["conv_id"], name=r["name"], type=r["type"], dept=r["dept"] or "",
                            members=json.loads(r["members"] or "[]"))

    def list_conversations(self) -> list[Conversation]:
        rows = self.conn.execute("SELECT conv_id FROM conversations").fetchall()
        return [self.get_conversation(r["conv_id"]) for r in rows]

    # ---------- messages ----------
    def insert_messages(self, msgs: Iterable[Message]) -> int:
        n = 0
        with self.conn as c:
            for m in msgs:
                cur = c.execute(
                    "INSERT OR IGNORE INTO messages(msg_id,conv_id,sender_id,sender_name,ts,type,text,"
                    "attachment,reply_to,mentions) VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (m.msg_id, m.conv_id, m.sender_id, m.sender_name, m.ts, m.type.value, m.text,
                     m.attachment.model_dump_json() if m.attachment else None, m.reply_to,
                     json.dumps(m.mentions)))
                n += cur.rowcount
        return n

    @staticmethod
    def _row_to_msg(r: sqlite3.Row) -> Message:
        return Message(msg_id=r["msg_id"], conv_id=r["conv_id"], sender_id=r["sender_id"],
                       sender_name=r["sender_name"] or "", ts=r["ts"], type=r["type"], text=r["text"] or "",
                       attachment=json.loads(r["attachment"]) if r["attachment"] else None,
                       reply_to=r["reply_to"], mentions=json.loads(r["mentions"] or "[]"))

    def get_messages(self, conv_id: str, since_ts: float = 0.0, until_ts: float | None = None) -> list[Message]:
        q, args = "SELECT * FROM messages WHERE conv_id=? AND ts>?", [conv_id, since_ts]
        if until_ts is not None:
            q += " AND ts<=?"
            args.append(until_ts)
        rows = self.conn.execute(q + " ORDER BY ts", args).fetchall()
        return [self._row_to_msg(r) for r in rows]

    def get_messages_by_ids(self, ids: list[str]) -> list[Message]:
        if not ids:
            return []
        qs = ",".join("?" * len(ids))
        rows = self.conn.execute(f"SELECT * FROM messages WHERE msg_id IN ({qs}) ORDER BY ts", ids).fetchall()
        return [self._row_to_msg(r) for r in rows]

    def unparsed_messages(self, conv_id: str | None = None) -> list[Message]:
        q = "SELECT * FROM messages WHERE parsed=0"
        args: list = []
        if conv_id:
            q += " AND conv_id=?"
            args.append(conv_id)
        return [self._row_to_msg(r) for r in self.conn.execute(q + " ORDER BY ts", args).fetchall()]

    def mark_parsed(self, msg_ids: list[str]) -> None:
        with self.conn as c:
            c.executemany("UPDATE messages SET parsed=1 WHERE msg_id=?", [(i,) for i in msg_ids])

    # ---------- parsed contents ----------
    def insert_parsed(self, items: Iterable[ParsedContent]) -> None:
        with self.conn as c:
            c.executemany(
                "INSERT INTO parsed_contents(msg_id,modality,text,chunk_index,meta,image_path) VALUES (?,?,?,?,?,?)",
                [(p.msg_id, p.modality.value, p.text, p.chunk_index, json.dumps(p.meta, ensure_ascii=False),
                  p.image_path) for p in items])

    def get_parsed(self, msg_ids: list[str]) -> dict[str, list[ParsedContent]]:
        out: dict[str, list[ParsedContent]] = {}
        if not msg_ids:
            return out
        qs = ",".join("?" * len(msg_ids))
        for r in self.conn.execute(
                f"SELECT * FROM parsed_contents WHERE msg_id IN ({qs}) ORDER BY msg_id, chunk_index", msg_ids):
            out.setdefault(r["msg_id"], []).append(ParsedContent(
                msg_id=r["msg_id"], modality=r["modality"], text=r["text"], chunk_index=r["chunk_index"],
                meta=json.loads(r["meta"] or "{}"), image_path=r["image_path"]))
        return out

    # ---------- topics & MKUs ----------
    def upsert_topics(self, topics: Iterable[Topic]) -> None:
        with self.conn as c:
            c.executemany("INSERT OR REPLACE INTO topics VALUES (?,?,?,?,?)",
                          [(t.topic_id, t.conv_id, json.dumps(t.msg_ids), t.ts_start, t.ts_end) for t in topics])

    def upsert_mkus(self, mkus: Iterable[MKU]) -> None:
        with self.conn as c:
            c.executemany(
                "INSERT OR REPLACE INTO mkus VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                [(m.mku_id, m.conv_id, m.topic_id, m.kind, json.dumps([x.value for x in m.modalities]), m.title,
                  m.content, json.dumps(m.evidence), m.ts_start, m.ts_end, json.dumps(m.acl), m.image_path,
                  json.dumps(m.meta, ensure_ascii=False)) for m in mkus])

    @staticmethod
    def _row_to_mku(r: sqlite3.Row) -> MKU:
        return MKU(mku_id=r["mku_id"], conv_id=r["conv_id"], topic_id=r["topic_id"], kind=r["kind"],
                   modalities=json.loads(r["modalities"]), title=r["title"] or "", content=r["content"],
                   evidence=json.loads(r["evidence"]), ts_start=r["ts_start"], ts_end=r["ts_end"],
                   acl=json.loads(r["acl"]), image_path=r["image_path"], meta=json.loads(r["meta"] or "{}"))

    def get_mkus(self, ids: list[str]) -> dict[str, MKU]:
        if not ids:
            return {}
        qs = ",".join("?" * len(ids))
        rows = self.conn.execute(f"SELECT * FROM mkus WHERE mku_id IN ({qs})", ids).fetchall()
        return {r["mku_id"]: self._row_to_mku(r) for r in rows}

    def all_mkus(self) -> list[MKU]:
        return [self._row_to_mku(r) for r in self.conn.execute("SELECT * FROM mkus")]

    def delete_mkus_of_topics(self, topic_ids: list[str]) -> list[str]:
        if not topic_ids:
            return []
        qs = ",".join("?" * len(topic_ids))
        ids = [r[0] for r in self.conn.execute(f"SELECT mku_id FROM mkus WHERE topic_id IN ({qs})", topic_ids)]
        with self.conn as c:
            c.execute(f"DELETE FROM mkus WHERE topic_id IN ({qs})", topic_ids)
        return ids

    # ---------- sync state ----------
    def get_last_ts(self, conv_id: str) -> float:
        r = self.conn.execute("SELECT last_ts FROM sync_state WHERE conv_id=?", (conv_id,)).fetchone()
        return r[0] if r else 0.0

    def set_last_ts(self, conv_id: str, ts: float) -> None:
        with self.conn as c:
            c.execute("INSERT OR REPLACE INTO sync_state VALUES (?,?)", (conv_id, ts))

    # ---------- QA logs ----------
    def log_qa(self, user_id: str, conv_id: str, question: str, answer: str, citations: list, trace: list,
               latency_ms: float) -> int:
        with self.conn as c:
            cur = c.execute(
                "INSERT INTO qa_logs(user_id,conv_id,question,answer,citations,trace,latency_ms) VALUES (?,?,?,?,?,?,?)",
                (user_id, conv_id, question, answer, json.dumps(citations, ensure_ascii=False),
                 json.dumps(trace, ensure_ascii=False), latency_ms))
            return cur.lastrowid

    def set_feedback(self, qa_id: int, score: int) -> None:
        with self.conn as c:
            c.execute("UPDATE qa_logs SET feedback=? WHERE id=?", (score, qa_id))
