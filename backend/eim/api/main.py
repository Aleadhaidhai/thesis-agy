"""FastAPI 服务入口：IM 模拟器接口、问答接口、管理后台接口。"""
from __future__ import annotations

import asyncio
import json
import logging
import shutil
import tempfile
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from eim.adapters.simulator import BOT_ID, SimulatorAdapter
from eim.agent.bot import BotService, answer_card
from eim.agent.graph import KnowledgeAgent
from eim.config import ROOT, settings
from eim.knowledge.indexer import Ingestor
from eim.models import Conversation, ConvType, MsgType
from eim.storage.db import DB

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

db = DB()
sim = SimulatorAdapter()
ingestor = Ingestor(db=db)
agent = KnowledgeAgent(db=db)
bot = BotService(sim, agent, ingestor, db)
ws_clients: set[WebSocket] = set()


async def _broadcast_loop():
    async for m in sim.events():
        data = json.dumps({"event": "message", "conv_id": m.conv_id, "msg_id": m.msg_id}, ensure_ascii=False)
        for ws in list(ws_clients):
            try:
                await ws.send_text(data)
            except Exception:  # noqa: BLE001
                ws_clients.discard(ws)


@asynccontextmanager
async def lifespan(_: FastAPI):
    tasks = [asyncio.create_task(bot.run()), asyncio.create_task(_broadcast_loop())]
    yield
    for t in tasks:
        t.cancel()


app = FastAPI(title="EIM-Agent", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ============================== IM 模拟器 ==============================
@app.get("/im/users")
def im_users():
    return sim.users()


@app.get("/im/convs")
def im_convs(user_id: str):
    convs = sim.conversations_of(user_id)
    return [c.model_dump() for c in convs]


@app.post("/im/convs/p2p_bot")
def im_open_bot_chat(user_id: str):
    cid = f"p2p_{user_id}_{BOT_ID}"
    sim.add_conversation(Conversation(conv_id=cid, name="小知（知识助手）", type=ConvType.P2P, members=[user_id, BOT_ID]))
    return {"conv_id": cid}


@app.get("/im/convs/{conv_id}/messages")
def im_messages(conv_id: str, user_id: str, limit: int = 200, before_ts: float | None = None):
    conv = next((c for c in sim.list_conversations() if c.conv_id == conv_id), None)
    if not conv or user_id not in conv.members:
        raise HTTPException(403, "not a member")
    return sim.messages(conv_id, limit, before_ts)


@app.post("/im/convs/{conv_id}/messages")
async def im_post(conv_id: str, user_id: str = Form(...), text: str = Form(""), reply_to: str | None = Form(None),
                  file: UploadFile | None = File(None)):
    conv = next((c for c in sim.list_conversations() if c.conv_id == conv_id), None)
    if not conv or user_id not in conv.members:
        raise HTTPException(403, "not a member")
    att, mtype = None, MsgType.TEXT
    if file is not None and file.filename:
        with tempfile.NamedTemporaryFile(delete=False, suffix=Path(file.filename).suffix) as tmp:
            shutil.copyfileobj(file.file, tmp)
        att = sim.store_file(tmp.name, file.filename)
        ext = Path(file.filename).suffix.lower()
        mtype = MsgType.IMAGE if ext in {".png", ".jpg", ".jpeg", ".gif", ".webp"} else \
            MsgType.AUDIO if ext in {".wav", ".mp3", ".m4a", ".amr"} else MsgType.FILE
    mentions = [BOT_ID] if "@小知" in text else []
    m = sim.post(conv_id, user_id, text, type=mtype, attachment=att, reply_to=reply_to, mentions=mentions)
    return m.model_dump()


@app.get("/im/files/{file_id}")
def im_file(file_id: str):
    hits = [p for p in (sim.file_dir / file_id).glob("*") if p.is_file()] if (sim.file_dir / file_id).is_dir() else []
    if not hits:
        raise HTTPException(404)
    return FileResponse(hits[0], filename=hits[0].name)


@app.websocket("/im/ws")
async def im_ws(ws: WebSocket):
    await ws.accept()
    ws_clients.add(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        ws_clients.discard(ws)


# ============================== 问答 API ==============================
class AskReq(BaseModel):
    user_id: str
    question: str
    conv_id: str = ""


@app.post("/api/ask")
async def api_ask(req: AskReq):
    principals = sim.get_user_principals(req.user_id)
    ans = await asyncio.to_thread(agent.ask, req.question, req.user_id, principals, req.conv_id, [])
    qa_id = db.log_qa(req.user_id, req.conv_id, req.question, ans.answer, [c.model_dump() for c in ans.citations],
                      ans.trace, ans.latency_ms)
    return {"qa_id": qa_id, **ans.model_dump(), "card": answer_card(ans, db)}


class FeedbackReq(BaseModel):
    qa_id: int
    score: int        # 1 有用 / -1 无用


@app.post("/api/feedback")
def api_feedback(req: FeedbackReq):
    db.set_feedback(req.qa_id, req.score)
    return {"ok": True}


# ============================== 管理后台 ==============================
@app.post("/admin/ingest")
async def admin_ingest(full: bool = False):
    t = time.perf_counter()
    if full:
        with db.conn as c:
            c.execute("DELETE FROM sync_state")
    st = await asyncio.to_thread(ingestor.sync_from_adapter, sim)
    return {**st.__dict__, "elapsed_s": round(time.perf_counter() - t, 1)}


@app.get("/admin/stats")
def admin_stats():
    q = lambda s: db.conn.execute(s).fetchone()[0]  # noqa: E731
    mod = {}
    for r in db.conn.execute("SELECT modality, COUNT(*) FROM parsed_contents GROUP BY modality"):
        mod[r[0]] = r[1]
    fb = db.conn.execute("SELECT SUM(feedback=1), SUM(feedback=-1), AVG(latency_ms) FROM qa_logs").fetchone()
    return {"conversations": q("SELECT COUNT(*) FROM conversations"), "messages": q("SELECT COUNT(*) FROM messages"),
            "topics": q("SELECT COUNT(*) FROM topics"), "mkus": q("SELECT COUNT(*) FROM mkus"),
            "parsed_by_modality": mod, "vectors": ingestor.vs.count(), "qa_total": q("SELECT COUNT(*) FROM qa_logs"),
            "qa_like": fb[0] or 0, "qa_dislike": fb[1] or 0, "avg_latency_ms": round(fb[2] or 0)}


@app.get("/admin/mkus")
def admin_mkus(conv_id: str | None = None, kind: str | None = None, q: str | None = None, limit: int = 50,
               offset: int = 0):
    sql, args = "SELECT * FROM mkus WHERE 1=1", []
    if conv_id:
        sql += " AND conv_id=?"
        args.append(conv_id)
    if kind:
        sql += " AND kind=?"
        args.append(kind)
    if q:
        sql += " AND content LIKE ?"
        args.append(f"%{q}%")
    rows = db.conn.execute(sql + " ORDER BY ts_end DESC LIMIT ? OFFSET ?", args + [limit, offset]).fetchall()
    return [DB._row_to_mku(r).model_dump() for r in rows]


@app.get("/admin/qa_logs")
def admin_qa_logs(limit: int = 50):
    rows = db.conn.execute("SELECT * FROM qa_logs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return [{**dict(r), "citations": json.loads(r["citations"] or "[]"), "trace": json.loads(r["trace"] or "[]")}
            for r in rows]


@app.get("/admin/convs")
def admin_convs():
    return [c.model_dump() for c in db.list_conversations()]


_dist = ROOT / "frontend" / "dist"
if _dist.exists():
    app.mount("/", StaticFiles(directory=_dist, html=True), name="web")
