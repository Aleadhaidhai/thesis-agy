"""IM 适配器抽象接口。

系统通过该接口与具体 IM 平台解耦：企业自研 IM、开源 IM 或本项目的 IM 模拟器
只需实现以下方法即可接入，上层解析、检索与 Agent 模块无需修改。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Iterable

from eim.models import Attachment, Conversation, Message


class IMAdapter(ABC):
    name: str = "base"

    # ---------- 拉取（历史数据全量/增量入库） ----------
    @abstractmethod
    def list_conversations(self) -> list[Conversation]:
        """返回机器人可见的会话列表（含成员，用于权限计算）。"""

    @abstractmethod
    def fetch_history(self, conv_id: str, since_ts: float = 0.0) -> Iterable[Message]:
        """按时间升序返回会话中 since_ts 之后的消息。"""

    @abstractmethod
    def download_attachment(self, att: Attachment, dest_dir: str) -> str:
        """下载附件到本地对象存储，返回本地路径。"""

    # ---------- 推送（实时事件与问答交互） ----------
    @abstractmethod
    def events(self) -> AsyncIterator[Message]:
        """实时消息事件流（WebSocket / Webhook 回调归一化后产出）。"""

    @abstractmethod
    async def send_message(self, conv_id: str, text: str, reply_to: str | None = None,
                           card: dict | None = None) -> str:
        """向会话发送消息（可附带结构化卡片，用于展示引用来源），返回消息 ID。"""

    # ---------- 权限 ----------
    @abstractmethod
    def get_user_principals(self, user_id: str) -> set[str]:
        """返回用户的权限主体集合：{user:<id>, conv:<id>..., dept:<id>...}。"""

    def is_bot_mentioned(self, msg: Message, bot_id: str) -> bool:
        return bot_id in msg.mentions
