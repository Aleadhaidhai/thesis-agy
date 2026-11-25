"""多模态知识单元（MKU）构建。

两类 MKU：
1. 会话单元（dialog）：以话题为单位，将话题内所有消息（含图片描述、语音转写、附件摘要）
   按“时间 发言人：内容”格式组织为规范化文本；可选地由 LLM 生成话题标题与摘要，
   作为“摘要增强”前缀以提升口语化对话的可检索性。
2. 附件单元（attachment）：文档/表格分块、图片、语音各自成为独立单元，并注入上下文头
   （所在群、发送者、时间、附言、所属话题标题），解决附件脱离会话语境后语义缺失的问题。

每个 MKU 记录证据消息 ID（用于引用溯源）与 ACL（用于权限过滤）。
"""
from __future__ import annotations

import time
from datetime import datetime

from eim.llm import get_llm
from eim.models import MKU, Conversation, Message, Modality, ParsedContent, Topic

SUMMARY_PROMPT = """下面是企业群聊“{conv}”中的一段对话。请输出 JSON：
{{"title": "不超过20字的话题标题", "summary": "不超过100字的摘要，保留结论、决策、负责人、时间、数值等关键信息", "keywords": ["3-6个关键词"]}}
对话：
{dialog}"""

MAX_DIALOG_CHARS = 1500


def fmt_ts(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")


def acl_for(conv: Conversation) -> list[str]:
    return [f"conv:{conv.conv_id}"]


def _msg_line(m: Message, parsed: list[ParsedContent], attach_brief: int = 160) -> str:
    if parsed:
        p0 = parsed[0]
        if p0.modality == Modality.TEXT:
            body = p0.text
        elif p0.modality in (Modality.IMAGE, Modality.AUDIO):
            body = p0.text.replace("\n", " ")
        else:
            name = m.attachment.name if m.attachment else "附件"
            body = f"[附件:{name}] " + p0.text.split("\n", 1)[-1][:attach_brief].replace("\n", " ")
    else:
        body = m.text
    return f"[{fmt_ts(m.ts)}] {m.sender_name or m.sender_id}：{body}"


class MKUBuilder:
    def __init__(self, use_llm_summary: bool = True):
        self.use_llm_summary = use_llm_summary

    def summarize(self, conv: Conversation, dialog: str) -> dict:
        if not self.use_llm_summary:
            return {}
        try:
            return get_llm().chat_json([{"role": "user", "content": SUMMARY_PROMPT.format(
                conv=conv.name, dialog=dialog[:3000])}], max_tokens=300)
        except Exception:
            return {}

    def build(self, conv: Conversation, topic: Topic, msgs: dict[str, Message],
              parsed: dict[str, list[ParsedContent]]) -> list[MKU]:
        tmsgs = [msgs[i] for i in topic.msg_ids if i in msgs]
        if not tmsgs:
            return []
        acl = acl_for(conv)
        lines = [_msg_line(m, parsed.get(m.msg_id, [])) for m in tmsgs]
        modalities = sorted({p.modality for m in tmsgs for p in parsed.get(m.msg_id, [])} | {Modality.TEXT},
                            key=lambda x: x.value)
        full_dialog = "\n".join(lines)
        info = self.summarize(conv, full_dialog) if len(tmsgs) >= 3 else {}
        title = info.get("title", "") or (lines[0].split("：", 1)[-1][:20])
        header = f"【群聊】{conv.name}｜【话题】{title}"
        if info.get("summary"):
            header += f"\n【摘要】{info['summary']}"
        if info.get("keywords"):
            header += f"\n【关键词】{'、'.join(map(str, info['keywords']))}"

        out: list[MKU] = []
        # --- 会话单元：超长话题按窗口切分，窗口间保留 2 条消息重叠 ---
        windows: list[tuple[int, int]] = []
        start, size = 0, 0
        for i, ln in enumerate(lines):
            if size + len(ln) > MAX_DIALOG_CHARS and i > start:
                windows.append((start, i))
                start = max(start + 1, i - 2)
                size = sum(len(x) for x in lines[start:i])
            size += len(ln)
        windows.append((start, len(lines)))
        for wi, (a, b) in enumerate(windows):
            ev = [m.msg_id for m in tmsgs[a:b]]
            out.append(MKU(
                mku_id=MKU.make_id(topic.topic_id, "dialog", str(wi)), conv_id=conv.conv_id, topic_id=topic.topic_id,
                kind="dialog", modalities=modalities, title=title,
                content=header + "\n" + "\n".join(lines[a:b]), evidence=ev,
                ts_start=tmsgs[a].ts, ts_end=tmsgs[b - 1].ts, acl=acl,
                meta={"summary": info.get("summary", ""), "keywords": info.get("keywords", []),
                      "n_msgs": b - a, "window": wi}))

        # --- 附件单元 ---
        for idx, m in enumerate(tmsgs):
            plist = parsed.get(m.msg_id, [])
            if not plist or plist[0].modality == Modality.TEXT:
                continue
            ctx = [x.msg_id for x in tmsgs[max(0, idx - 2): idx + 3]]
            note = f"｜附言：{m.text}" if m.text and plist[0].modality != Modality.IMAGE else ""
            ctx_head = (f"【来源】群聊“{conv.name}”｜{m.sender_name or m.sender_id}｜{fmt_ts(m.ts)}"
                        f"｜话题：{title}{note}")
            for p in plist:
                out.append(MKU(
                    mku_id=MKU.make_id(m.msg_id, "att", str(p.chunk_index)), conv_id=conv.conv_id,
                    topic_id=topic.topic_id, kind="attachment", modalities=[p.modality],
                    title=(m.attachment.name if m.attachment else title),
                    content=ctx_head + "\n" + p.text, evidence=[m.msg_id] + [c for c in ctx if c != m.msg_id],
                    ts_start=m.ts, ts_end=m.ts, acl=acl, image_path=p.image_path,
                    meta={**{k: v for k, v in p.meta.items() if k not in ("ocr",)}, "chunk": p.chunk_index,
                          "built_at": time.time()}))
        return out
