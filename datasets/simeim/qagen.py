"""SimEIM 问答标注生成。

问题类型：
- single：单事实问答（按种子模态细分 text / image / document / table / audio）
- temporal：事实存在更新（新结论覆盖旧结论），应回答最新值
- multihop：需要组合两条事实
- permission：提问者无权访问证据所在会话，系统应拒答且不泄露
- unanswerable：知识库中不存在答案，系统应明确说明无法确定

标准答案来自结构化事实，由大模型改写为问句与要点（key_points），随后人工抽检校对。
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

QA_PROMPT = """根据下面关于虚构公司的一条事实，生成 2 个员工可能在企业 IM 里向知识助手提出的问题。
事实：{fact}
话题背景：{topic}（来自群聊“{conv}”）

要求：
- 问题1（precise）：表述完整清晰，指向事实中的一个或多个具体信息点；
- 问题2（colloquial）：口语化、更简短，像同事随口一问，可以省略部分背景，但仍需能唯一指向该事实；
- 两个问题尽量考察不同的信息点；问题中不要直接包含答案；
- 为每个问题给出简洁标准答案 answer，以及判分要点 key_points（1-4 个原子事实，回答必须包含的数字/名称/结论）。
只输出 JSON：{{"qas": [{{"style": "precise", "question": "...", "answer": "...", "key_points": ["..."]}}, {{"style": "colloquial", "question": "...", "answer": "...", "key_points": ["..."]}}]}}"""

MULTIHOP = [
    {"seeds": ["F025", "F024"], "question": "灵犀 V1.0 最终选定的意图识别模型，在评测中的 F1 和推理延迟分别是多少？",
     "answer": "最终选用 RoBERTa-wwm，F1 为 0.915，推理延迟 22 毫秒。", "key_points": ["RoBERTa-wwm", "0.915", "22"]},
    {"seeds": ["F018", "F019"], "question": "支付网关证书事故的改进措施里提到证书变更要灰度，那常规发布一般能在什么时间窗口做？（按当时的规定）",
     "answer": "当时规定常规发布窗口为每周二和周四 14:00-17:00，周五和节假日前一天禁止。", "key_points": ["周二", "周四", "14:00-17:00"]},
    {"seeds": ["F027", "F049"], "question": "A 银行 UAT 提出的两个问题后来是怎么解决的？",
     "answer": "UAT 反馈账单类回答过长、转人工按钮不明显；10 月 14 日交付 v1.0.3，账单类回答控制在 150 字以内，转人工按钮改为右下角悬浮红色按钮。",
     "key_points": ["150 字", "悬浮红色按钮", "v1.0.3"]},
    {"seeds": ["F012", "F028"], "question": "灵犀的首字响应时间要求，PRD 里和客户确认的验收标准里分别是多少？",
     "answer": "PRD 要求首字响应不超过 1.5 秒；验收标准为 P95 首字响应不超过 2 秒。", "key_points": ["1.5 秒", "2 秒"]},
    {"seeds": ["F038", "F041"], "question": "A 银行明年要扩到 80 个坐席，如果按专业版 SaaS 报价，包含的坐席数够吗？超出部分单价多少？",
     "answer": "专业版 SaaS 每年 36 万元含 50 个坐席，80 个坐席超出 30 个，超出部分每坐席每月 220 元。",
     "key_points": ["50 个坐席", "220 元"]},
    {"seeds": ["F042", "F044"], "question": "肖晨的导师是谁？新人环境指南里测试库只读账号去哪拿？",
     "answer": "肖晨的导师是李娜；测试库只读账号在 Vault 路径 secret/test/db-readonly 获取。",
     "key_points": ["李娜", "secret/test/db-readonly"]},
    {"seeds": ["F026", "F030"], "question": "灵犀内测发现的严重缺陷按公司缺陷等级定义需要多久修复？",
     "answer": "内测发现 4 个严重缺陷；按定义 S2 严重缺陷需在 1 个工作日内修复。", "key_points": ["1 个工作日"]},
    {"seeds": ["F020", "F021"], "question": "9 月 12 日值班交接里提到的 GPU 节点问题需要找谁确认？监控平台迁移又是谁负责？",
     "answer": "GPU 节点 gpu-node-03 显存问题需要找周杰确认；监控平台迁移由吴越负责。",
     "key_points": ["周杰", "吴越"]},
    {"seeds": ["F003", "F048"], "question": "灵犀问答接口限流超限返回的错误码，按接口规范其前两位代表哪个系统？",
     "answer": "超限返回 400429；按规范前两位为系统编号，40 代表灵犀。", "key_points": ["400429", "40", "灵犀"]},
    {"seeds": ["F016", "F015"], "question": "灵犀正式上线时间最后定在哪天？V1.1 里 P0 需求总共预估多少人日？",
     "answer": "正式上线时间调整为 11 月 3 日；V1.1 P0 需求（R-101、R-102、R-105）共 12 人日。",
     "key_points": ["11 月 3 日", "12 人日"]},
]

TEMPORAL = [
    {"seeds": ["F001", "F007"], "question": "订单服务现在的数据库连接池 maximumPoolSize 是多少？",
     "answer": "当前为 40（10 月 13 日由 50 下调为 40）。", "key_points": ["40"], "stale": ["50"]},
    {"seeds": ["F012", "F015"], "question": "灵犀什么时候正式上线？",
     "answer": "正式上线时间已从 10 月 20 日调整为 11 月 3 日。", "key_points": ["11 月 3 日"], "stale": []},
    {"seeds": ["F019", "F022"], "question": "现在生产环境常规发布窗口是什么时候？",
     "answer": "自 10 月 20 日起为每周二、三、四 10:00-12:00 和 14:00-17:00，周五禁止常规发布。",
     "key_points": ["周三", "10:00-12:00"], "stale": []},
    {"seeds": ["F033", "F036"], "question": "11 月以后去北京出差，住宿每晚报销上限是多少？",
     "answer": "自 11 月 1 日起一线城市住宿上限为每晚 700 元（原为 600 元）。", "key_points": ["700"], "stale": ["600 元"]},
]

UNANSWERABLE = [
    ("u_lina", "c_backend", "支付服务的 Redis 集群一共有多少个节点？"),
    ("u_sunhao", "c_frontend", "前端组件库下一次升级到 Element Plus 3.0 定在什么时候？"),
    ("u_chenjing", "c_product", "灵犀 V2.0 的 PRD 里定的问答准确率指标是多少？"),
    ("u_wuyue", "c_sre", "上个月机房电费是多少？"),
    ("u_mafei", "c_qa", "支付服务的压测 TPS 是多少？"),
    ("u_yangxue", "c_sales", "客户 C 证券公司的商机金额是多少？"),
    ("u_xiaochen", "c_onboard", "公司提供的笔记本电脑是什么型号？"),
    ("u_heping", "c_all", "今年春节放几天假？"),
    ("u_zhoujie", "c_lingxi", "灵犀支持哪些小语种？"),
    ("u_liuyang", "c_product", "会员积分可以兑换实物礼品吗？兑换比例是多少？"),
    ("u_zhangwei", "c_backend", "订单服务用的 MySQL 是哪个版本？"),
    ("u_guoxin", "c_all", "公司年会定在哪个酒店？"),
]

PERMISSION = [
    ("u_xiaochen", "F045", "公司 B 轮融资是谁领投的？估值多少？", ["星海资本", "8 亿"]),
    ("u_sunhao", "F046", "明年研发部门的调薪比例是多少？", ["8%", "216"]),
    ("u_lina", "F047", "明年是不是要成立 AI 平台部？谁当负责人？", ["AI 平台部", "张伟"]),
    ("u_mafei", "F046", "2027 年调薪预算总共多少钱？", ["216", "29", "45"]),
    ("u_wuyue", "F045", "B 轮计划融多少钱，什么时候交割？", ["1.5 亿", "11 月底"]),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="qwen3:8b")
    ap.add_argument("--base-url", default=None)
    ap.add_argument("--api-key", default=None)
    ap.add_argument("--dataset", default=str(HERE / "build" / "simeim.json"))
    ap.add_argument("--out", default=str(HERE / "build" / "qa.json"))
    args = ap.parse_args()
    rnd = random.Random(11)
    llm = LLMClient(base_url=args.base_url, api_key=args.api_key, model=args.model, timeout=600)
    ds = json.loads(Path(args.dataset).read_text())
    seeds = {json.loads(l)["id"]: json.loads(l) for l in (HERE / "seeds.jsonl").read_text().splitlines() if l.strip()}
    convs = {c["id"]: c for c in ds["conversations"]}
    names = {c["id"]: c["name"] for c in ds["conversations"]}
    key_msgs: dict[str, list[str]] = {}
    all_msgs: dict[str, list[str]] = {}
    for m in ds["messages"]:
        if m["seed_id"]:
            all_msgs.setdefault(m["seed_id"], []).append(m["msg_id"])
            if m["key"]:
                key_msgs.setdefault(m["seed_id"], []).append(m["msg_id"])
    ev = lambda sid: key_msgs.get(sid) or all_msgs.get(sid, [])  # noqa: E731

    out_path = Path(args.out)
    qas = json.loads(out_path.read_text()) if out_path.exists() else []
    done = {q["seed_ids"][0] for q in qas if q["type"] == "single"}
    for sid, s in seeds.items():
        if sid in done or sid not in all_msgs or s["conv"] == "c_mgmt" and sid in {"F045", "F046", "F047"} and False:
            continue
        r = llm.chat_json([{"role": "user", "content": QA_PROMPT.format(
            fact=s["fact"], topic=s["topic"], conv=names[s["conv"]])}], max_tokens=900, temperature=0.5)
        members = [u for u in convs[s["conv"]]["members"] if u not in s["speakers"]] or convs[s["conv"]]["members"]
        for k, qa in enumerate(r.get("qas", [])[:2]):
            if not qa.get("question"):
                continue
            qas.append({"qid": f"Q_{sid}_{k}", "type": "single", "modality": s["modality"],
                        "hidden": bool(s.get("hidden")), "style": qa.get("style", ""), "seed_ids": [sid],
                        "asker": rnd.choice(members), "conv_id": s["conv"], "question": qa["question"],
                        "answer": qa.get("answer", ""), "key_points": qa.get("key_points", []),
                        "gold_msgs": ev(sid), "answerable": True})
        out_path.write_text(json.dumps(qas, ensure_ascii=False, indent=1))
        print("qa", sid, flush=True)

    qas = [q for q in qas if q["type"] == "single"]
    for i, t in enumerate(TEMPORAL):
        c = seeds[t["seeds"][1]]["conv"]
        qas.append({"qid": f"Q_T{i}", "type": "temporal", "modality": "text", "seed_ids": t["seeds"],
                    "asker": rnd.choice(convs[c]["members"]), "conv_id": c, "question": t["question"],
                    "answer": t["answer"], "key_points": t["key_points"], "stale_points": t.get("stale", []),
                    "gold_msgs": ev(t["seeds"][1]), "answerable": True})
    for i, t in enumerate(MULTIHOP):
        cs = [seeds[x]["conv"] for x in t["seeds"]]
        cand = set(convs[cs[0]]["members"]).intersection(*[set(convs[c]["members"]) for c in cs[1:]])
        asker = sorted(cand)[0] if cand else convs[cs[0]]["members"][0]
        qas.append({"qid": f"Q_M{i}", "type": "multihop", "modality": "mixed", "seed_ids": t["seeds"],
                    "asker": asker, "conv_id": cs[0], "question": t["question"], "answer": t["answer"],
                    "key_points": t["key_points"], "gold_msgs": sum((ev(x) for x in t["seeds"]), []),
                    "answerable": True})
    for i, (u, sid, q, forbidden) in enumerate(PERMISSION):
        qas.append({"qid": f"Q_P{i}", "type": "permission", "modality": seeds[sid]["modality"], "seed_ids": [sid],
                    "asker": u, "conv_id": "", "question": q, "answer": "（无权限，应拒答且不泄露）",
                    "key_points": [], "forbidden_points": forbidden, "gold_msgs": [], "answerable": False})
    for i, (u, c, q) in enumerate(UNANSWERABLE):
        qas.append({"qid": f"Q_U{i}", "type": "unanswerable", "modality": "none", "seed_ids": [], "asker": u,
                    "conv_id": c, "question": q, "answer": "（知识库中无答案）", "key_points": [], "gold_msgs": [],
                    "answerable": False})
    out_path.write_text(json.dumps(qas, ensure_ascii=False, indent=1))
    from collections import Counter
    print(Counter(q["type"] for q in qas), Counter(q["modality"] for q in qas if q["type"] == "single"))


if __name__ == "__main__":
    main()
