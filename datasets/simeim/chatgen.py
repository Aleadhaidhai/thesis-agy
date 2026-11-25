"""SimEIM 对话生成：以“事实种子”为中心，用大模型扩写为真实感的企业群聊片段，并生成噪声闲聊话题。

关键设计：
- 事实先行（fact-first）：每个话题围绕一条结构化事实生成，问答标注的标准答案直接来自事实，避免标注漂移；
- 对 hidden=true 的多模态种子，要求对话文本不得复述附件中的关键信息，只能以“见截图/见文档”等方式提及，
  从而保证答案只能从图片/文档/语音中获得，用于评测多模态解析能力；
- 模型输出中标记携带事实的消息序号，作为证据标注（gold evidence）。

用法：python chatgen.py --model qwen3:8b [--base-url http://127.0.0.1:11434/v1]
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "backend"))
from eim.llm import LLMClient  # noqa: E402

THREAD_PROMPT = """你在为一家虚构科技公司“{company}”构造企业即时通讯群聊数据。
群聊：“{conv_name}”（{conv_desc}）
话题：{topic}
参与者（id: 姓名/职位）：
{speakers}

需要在对话中体现的事实：
{fact}

{modality_rule}

要求：
1. 生成 {n_min}-{n_max} 条消息，口语化、简短，像真实工作群聊（可有“收到”“好的”“+1”等短回复、表情符号、错别字少量即可）。
2. 发言人只能从参与者中选择，第一条由 {first} 发出。
3. 可以用 reply_to 指向被回复消息的序号（从 0 开始），用 mentions 列出 @ 的人员 id。
4. 用 key 标记“携带事实关键信息”的消息（true/false）。
{attach_rule}

只输出 JSON：{{"messages": [{{"speaker": "u_xxx", "text": "...", "reply_to": null, "mentions": [], "attachment": false, "key": false}}]}}"""

RULE_TEXT = "事实应分散在多条消息中自然地表达出来（例如先提问、再给出结论、再确认），关键数字/名称必须准确出现在文本中。"
RULE_HIDDEN = ("事实中的关键信息只存在于附件（{kind_cn}）中。对话文本中【不得】直接说出附件里的具体数字、错误码、名称等细节，"
               "只能说“看下截图”“文档发群里了”“我发个语音”之类，并围绕附件做简短讨论（如“收到我看看”“这个得尽快处理”）。")
RULE_SHOWN = "附件中的信息可以在对话中被部分讨论，但关键数字仍以附件为准。"
ATTACH_RULE = "5. 其中恰好 1 条消息的 attachment 为 true，表示该消息发送了附件（{kind_cn}），由 {sender} 发送，text 可为空或一句附言，该条 key 为 true。"
KIND_CN = {"terminal": "日志截图", "form": "系统界面截图", "chart": "监控/数据图表截图", "diagram": "架构图照片",
           "pdf": "PDF 文档", "docx": "Word 文档", "pptx": "PPT 演示文稿", "xlsx": "Excel 表格", "audio": "语音消息"}

NOISE_PROMPT = """为虚构公司“{company}”的群聊“{conv_name}”（{conv_desc}）生成 {k} 段与工作知识无关或价值很低的日常闲聊/事务性对话，
例如订会议室、催周报、午饭、快递、团建投票、临时请假、网络卡顿吐槽、生日祝福等，每段 3-6 条消息。
发言人从这些 id 中选：{members}
只输出 JSON：{{"threads": [{{"topic": "简短话题", "messages": [{{"speaker": "u_xxx", "text": "...", "reply_to": null, "mentions": []}}]}}]}}"""


def gen_thread(llm: LLMClient, world: dict, seed: dict, users: dict, convs: dict, retries: int = 3) -> dict | None:
    conv = convs[seed["conv"]]
    sp = seed["speakers"]
    att = seed.get("attachment")
    if seed["modality"] == "text" or not att:
        mod_rule, attach_rule = RULE_TEXT, ""
    else:
        kind_cn = KIND_CN[att["kind"]]
        mod_rule = RULE_HIDDEN.format(kind_cn=kind_cn) if seed.get("hidden", True) else RULE_SHOWN
        attach_rule = ATTACH_RULE.format(kind_cn=kind_cn, sender=sp[0])
    prompt = THREAD_PROMPT.format(
        company=world["company"], conv_name=conv["name"], conv_desc=conv["desc"], topic=seed["topic"],
        speakers="\n".join(f"{u}: {users[u]['name']}/{users[u]['title']}" for u in sp), fact=seed["fact"],
        modality_rule=mod_rule, attach_rule=attach_rule, n_min=6, n_max=14, first=sp[0])
    for _ in range(retries):
        out = llm.chat_json([{"role": "user", "content": prompt}], max_tokens=2000, temperature=0.8)
        msgs = out.get("messages") or []
        msgs = [m for m in msgs if isinstance(m, dict) and m.get("speaker") in sp]
        if len(msgs) < 4:
            continue
        if att:
            flags = [i for i, m in enumerate(msgs) if m.get("attachment")]
            if not flags:  # 模型未标记附件时，插入到第 1 或 2 条之后
                pos = min(1, len(msgs) - 1)
                msgs.insert(pos, {"speaker": sp[0], "text": "", "attachment": True, "key": True})
            else:
                for i in flags[1:]:
                    msgs[i]["attachment"] = False
            if seed.get("hidden", True):  # 泄露检查：隐藏事实中的数字不应出现在文本中
                leak_tokens = _key_tokens(seed["fact"])
                for m in msgs:
                    if not m.get("attachment") and any(tok in (m.get("text") or "") for tok in leak_tokens):
                        m["text"] = _redact(m["text"], leak_tokens)
        return {"seed_id": seed["id"], "conv": seed["conv"], "topic": seed["topic"], "date": seed["date"],
                "attachment": att, "messages": msgs}
    return None


def _key_tokens(fact: str) -> list[str]:
    import re
    toks = re.findall(r"[A-Za-z]+[-_]?\d+[\w.-]*|\d+(?:\.\d+)?%?|\d+\.\d+\.\d+\.\d+(?::\d+)?", fact)
    return [t for t in toks if len(t) >= 2 and not re.fullmatch(r"20\d\d|[1-9]|1[0-2]", t)]


def _redact(text: str, toks: list[str]) -> str:
    for t in sorted(toks, key=len, reverse=True):
        text = text.replace(t, "（见附件）")
    return text


def gen_noise(llm: LLMClient, world: dict, conv: dict, k: int) -> list[dict]:
    out = llm.chat_json([{"role": "user", "content": NOISE_PROMPT.format(
        company=world["company"], conv_name=conv["name"], conv_desc=conv["desc"], k=k,
        members=", ".join(conv["members"][:8]))}], max_tokens=2500, temperature=0.9)
    threads = []
    for t in out.get("threads") or []:
        msgs = [m for m in t.get("messages", []) if isinstance(m, dict) and m.get("speaker") in conv["members"]]
        if len(msgs) >= 2:
            threads.append({"topic": t.get("topic", "闲聊"), "conv": conv["id"], "messages": msgs, "noise": True})
    return threads


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="qwen3:8b")
    ap.add_argument("--base-url", default=None)
    ap.add_argument("--api-key", default=None)
    ap.add_argument("--noise-per-conv", type=int, default=8)
    ap.add_argument("--out", default=str(HERE / "build" / "threads.json"))
    args = ap.parse_args()
    llm = LLMClient(base_url=args.base_url, api_key=args.api_key, model=args.model, timeout=600)
    world = json.loads((HERE / "world.json").read_text())
    users = {u["id"]: u for u in world["users"]}
    convs = {c["id"]: c for c in world["conversations"]}
    seeds = [json.loads(l) for l in (HERE / "seeds.jsonl").read_text().splitlines() if l.strip()]
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    data = json.loads(out_path.read_text()) if out_path.exists() else {"facts": {}, "noise": {}}
    for s in seeds:
        if s["id"] in data["facts"]:
            continue
        t = gen_thread(llm, world, s, users, convs)
        if t:
            data["facts"][s["id"]] = t
            out_path.write_text(json.dumps(data, ensure_ascii=False, indent=1))
            print("fact", s["id"], len(t["messages"]), flush=True)
        else:
            print("FAILED", s["id"], flush=True)
    random.seed(7)
    for cid, conv in convs.items():
        have = len(data["noise"].get(cid, []))
        while have < args.noise_per_conv:
            th = gen_noise(llm, world, conv, min(4, args.noise_per_conv - have))
            if not th:
                break
            data["noise"].setdefault(cid, []).extend(th)
            have = len(data["noise"][cid])
            out_path.write_text(json.dumps(data, ensure_ascii=False, indent=1))
            print("noise", cid, have, flush=True)


if __name__ == "__main__":
    main()
