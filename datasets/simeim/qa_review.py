"""问答标注人工校验工具。

导出：python qa_review.py export  → build/qa_review.xlsx（含问题、标准答案、要点、证据原文，供人工逐条核对）
导入：python qa_review.py import  → 按表中“校验结论/修改后问题/修改后答案/修改后要点”更新 build/qa.json，
      结论为“删除”的条目将被移除，并记录 reviewed=True。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
QA = HERE / "build" / "qa.json"
DS = HERE / "build" / "simeim.json"
XLSX = HERE / "build" / "qa_review.xlsx"


def export():
    qas = json.loads(QA.read_text())
    ds = json.loads(DS.read_text())
    msgs = {m["msg_id"]: m for m in ds["messages"]}
    seeds = {json.loads(l)["id"]: json.loads(l) for l in (HERE / "seeds.jsonl").read_text().splitlines() if l.strip()}
    rows = []
    for q in qas:
        ev = "\n".join(f"[{m}] {msgs[m]['text'] or '(附件) ' + str(msgs[m]['attachment_path']).split('/')[-1]}"
                       for m in q["gold_msgs"] if m in msgs)
        facts = "\n".join(seeds[s]["fact"] for s in q.get("seed_ids", []) if s in seeds)
        rows.append({"qid": q["qid"], "类型": q["type"], "模态": q["modality"], "提问者": q["asker"],
                     "问题": q["question"], "标准答案": q["answer"], "判分要点": "；".join(q.get("key_points", [])),
                     "事实来源": facts, "证据消息": ev, "校验结论(通过/修改/删除)": "", "修改后问题": "",
                     "修改后答案": "", "修改后要点(；分隔)": ""})
    pd.DataFrame(rows).to_excel(XLSX, index=False)
    print("exported", XLSX, len(rows))


def do_import():
    qas = {q["qid"]: q for q in json.loads(QA.read_text())}
    df = pd.read_excel(XLSX).fillna("")
    keep = []
    for _, r in df.iterrows():
        q = qas.get(r["qid"])
        if q is None:
            continue
        verdict = str(r["校验结论(通过/修改/删除)"]).strip()
        if verdict == "删除":
            continue
        if r["修改后问题"]:
            q["question"] = str(r["修改后问题"])
        if r["修改后答案"]:
            q["answer"] = str(r["修改后答案"])
        if r["修改后要点(；分隔)"]:
            q["key_points"] = [x.strip() for x in str(r["修改后要点(；分隔)"]).split("；") if x.strip()]
        q["reviewed"] = verdict in ("通过", "修改")
        keep.append(q)
    QA.write_text(json.dumps(keep, ensure_ascii=False, indent=1))
    print("imported", len(keep), "reviewed:", sum(q.get("reviewed", False) for q in keep))


if __name__ == "__main__":
    {"export": export, "import": do_import}[sys.argv[1]]()
