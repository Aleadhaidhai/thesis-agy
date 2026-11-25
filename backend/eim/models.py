"""核心数据结构。

消息流（Message）经多模态解析（ParsedContent）、话题切分（Topic）后，
被组织为多模态知识单元（MKU, Multimodal Knowledge Unit），MKU 是检索与引用的基本粒度。
"""
from __future__ import annotations

import hashlib
import time
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class Modality(str, Enum):
    TEXT = "text"
    IMAGE = "image"
    DOCUMENT = "document"
    AUDIO = "audio"
    TABLE = "table"


class MsgType(str, Enum):
    TEXT = "text"
    IMAGE = "image"
    FILE = "file"
    AUDIO = "audio"
    SYSTEM = "system"


class ConvType(str, Enum):
    GROUP = "group"
    P2P = "p2p"


class Attachment(BaseModel):
    file_id: str
    name: str
    mime: str
    size: int = 0
    path: str | None = None            # 下载到本地对象存储后的路径


class Message(BaseModel):
    """统一消息模型：各 IM 平台的原始事件由适配器归一化为该结构。"""
    msg_id: str
    conv_id: str
    sender_id: str
    sender_name: str = ""
    ts: float = Field(default_factory=time.time)   # Unix 时间戳（秒）
    type: MsgType = MsgType.TEXT
    text: str = ""
    attachment: Attachment | None = None
    reply_to: str | None = None                   # 被回复消息 ID（线程/引用回复）
    mentions: list[str] = Field(default_factory=list)


class Conversation(BaseModel):
    conv_id: str
    name: str
    type: ConvType = ConvType.GROUP
    members: list[str] = Field(default_factory=list)
    dept: str = ""


class ParsedContent(BaseModel):
    """单条消息（或其附件中的一个片段）的解析结果。"""
    msg_id: str
    modality: Modality
    text: str                                   # 统一转写后的文本
    chunk_index: int = 0                        # 文档分块序号
    meta: dict[str, Any] = Field(default_factory=dict)  # page / ocr / caption / transcript / sheet 等
    image_path: str | None = None               # 若可用于视觉检索，记录图像路径


class Topic(BaseModel):
    topic_id: str
    conv_id: str
    msg_ids: list[str]
    ts_start: float
    ts_end: float


class MKU(BaseModel):
    """多模态知识单元。

    - content: 用于稠密/稀疏检索与生成的规范化文本（含上下文窗口）
    - evidence: 证据消息 ID 列表，用于回答溯源跳转
    - acl: 可见主体集合（会话 ID / 用户 ID / 部门 ID），检索时做前置过滤
    """
    mku_id: str
    conv_id: str
    topic_id: str
    kind: str = "dialog"                        # dialog: 会话话题单元; attachment: 附件片段单元
    modalities: list[Modality] = Field(default_factory=list)
    title: str = ""
    content: str
    evidence: list[str] = Field(default_factory=list)
    ts_start: float = 0.0
    ts_end: float = 0.0
    acl: list[str] = Field(default_factory=list)
    image_path: str | None = None
    meta: dict[str, Any] = Field(default_factory=dict)

    @staticmethod
    def make_id(*parts: str) -> str:
        return hashlib.md5("|".join(parts).encode("utf-8")).hexdigest()[:16]


class Citation(BaseModel):
    index: int
    mku_id: str
    conv_id: str
    msg_ids: list[str]
    snippet: str


class Answer(BaseModel):
    question: str
    answer: str
    citations: list[Citation] = Field(default_factory=list)
    trace: list[dict[str, Any]] = Field(default_factory=list)   # Agent 推理轨迹（用于可解释性与案例分析）
    latency_ms: float = 0.0
