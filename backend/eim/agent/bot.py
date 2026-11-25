"""知识助手机器人服务：监听 IM 事件流，被 @ 或在与机器人的单聊中收到消息时调用 Agent 作答，
并以“回答 + 引用来源卡片”的形式回复；同时把新消息增量写入知识库。"""
from __future__ import annotations

import asyncio
import logging

from eim.adapters.base import IMAdapter
from eim.adapters.simulator import BOT_ID
from eim.agent.graph import KnowledgeAgent
from eim.knowledge.indexer import Ingestor
from eim.models import Answer, Message
from eim.storage.db import DB

log = logging.getLogger(__name__)


def answer_card(ans: Answer, db: DB) -> dict:
    items = []
    for c in ans.citations:
        conv = db.get_conversation(c.conv_id)
        msgs = db.get_messages_by_ids(c.msg_ids[:1])
        m = msgs[0] if msgs else None
        items.append({"index": c.index, "conv_id": c.conv_id, "conv_name": conv.name if conv else c.conv_id,
                      "msg_id": c.msg_ids[0] if c.msg_ids else None, "sender": m.sender_name if m else "",
                      "ts": m.ts if m else None, "snippet": c.snippet,
                      "attachment": m.attachment.model_dump() if m and m.attachment else None})
    return {"type": "answer", "citations": items, "latency_ms": round(ans.latency_ms)}


class BotService:
    def __init__(self, adapter: IMAdapter, agent: KnowledgeAgent, ingestor: Ingestor, db: DB,
                 auto_ingest: bool = True, ingest_debounce_s: float = 20.0):
        self.adapter = adapter
        self.agent = agent
        self.ingestor = ingestor
        self.db = db
        self.auto_ingest = auto_ingest
        self.debounce = ingest_debounce_s
        self._dirty = asyncio.Event()

    async def run(self):
        tasks = [asyncio.create_task(self._listen())]
        if self.auto_ingest:
            tasks.append(asyncio.create_task(self._ingest_loop()))
        await asyncio.gather(*tasks)

    async def _listen(self):
        async for msg in self.adapter.events():
            if msg.sender_id == BOT_ID:
                continue
            self._dirty.set()
            conv = next((c for c in self.adapter.list_conversations() if c.conv_id == msg.conv_id), None)
            is_p2p_bot = conv is not None and conv.type.value == "p2p" and BOT_ID in conv.members
            if self.adapter.is_bot_mentioned(msg, BOT_ID) or is_p2p_bot:
                asyncio.create_task(self.handle_question(msg))

    async def handle_question(self, msg: Message):
        q = msg.text.replace("@小知", "").strip()
        if not q:
            return
        principals = self.adapter.get_user_principals(msg.sender_id)
        history = getattr(self.adapter, "recent_context", lambda *a, **k: [])(msg.conv_id, 8, msg.ts)
        try:
            ans = await asyncio.to_thread(self.agent.ask, q, msg.sender_id, principals, msg.conv_id, history)
        except Exception as e:  # noqa: BLE001
            log.exception("agent failed")
            await self.adapter.send_message(msg.conv_id, f"抱歉，处理问题时出错：{type(e).__name__}", reply_to=msg.msg_id)
            return
        qa_id = self.db.log_qa(msg.sender_id, msg.conv_id, q, ans.answer, [c.model_dump() for c in ans.citations],
                               ans.trace, ans.latency_ms)
        card = answer_card(ans, self.db)
        card["qa_id"] = qa_id
        await self.adapter.send_message(msg.conv_id, ans.answer, reply_to=msg.msg_id, card=card)

    async def _ingest_loop(self):
        while True:
            await self._dirty.wait()
            await asyncio.sleep(self.debounce)       # 防抖：批量增量入库
            self._dirty.clear()
            try:
                st = await asyncio.to_thread(self.ingestor.sync_from_adapter, self.adapter)
                log.info("incremental ingest: %s", st)
            except Exception:  # noqa: BLE001
                log.exception("incremental ingest failed")
