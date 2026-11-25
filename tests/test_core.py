"""核心模块单元测试（不依赖大模型）。运行：pytest -q"""
import numpy as np
import pandas as pd

from eim.knowledge.segmentation import FixedWindowSegmenter, TopicSegmenter, is_low_info
from eim.models import Message
from eim.parsing.chunker import chunk_text
from eim.parsing.table import serialize_rows
from eim.retrieval.bm25 import BM25Index, tokenize
from eim.retrieval.fusion import rrf, time_decay
from eim.storage.vectorstore import acl_expr


def _m(i, ts, sender="a", text="x", reply=None, mentions=None):
    return Message(msg_id=f"m{i}", conv_id="c", sender_id=sender, ts=ts, text=text, reply_to=reply,
                   mentions=mentions or [])


def test_low_info():
    assert is_low_info("好的") and is_low_info("+1") and is_low_info("收到！")
    assert not is_low_info("连接池改成50了")


def test_rrf_order_and_sources():
    r = rrf({"dense": [("a", 0.9), ("b", 0.8)], "bm25": [("b", 10), ("c", 5)]})
    assert r[0][0] == "b" and set(r[0][2]) == {"dense", "bm25"}


def test_time_decay():
    assert abs(time_decay(0, now=180 * 86400, half_life_days=180) - 0.5) < 1e-6


def test_acl_expr():
    assert acl_expr(None) == ""
    assert "array_contains_any" in acl_expr({"conv:a"})
    assert "__none__" in acl_expr(set())


def test_chunker_overlap():
    text = "。".join(f"第{i}句话内容比较长一些用于测试分块" for i in range(60))
    chunks = chunk_text(text, max_chars=200, overlap=30)
    assert len(chunks) > 3 and all(len(c) <= 200 for c in chunks)


def test_table_serialize():
    df = pd.DataFrame([["创建订单", 500, 1260]], columns=["接口", "并发", "TPS"])
    out = serialize_rows(df, "压测")
    assert "接口: 创建订单" in out[0]["text"] and "TPS: 1260" in out[0]["text"]


def test_bm25_acl(tmp_path):
    idx = BM25Index(tmp_path / "b.pkl")
    idx.build([("1", "订单服务连接池 maximumPoolSize 50", ["conv:a"]), ("2", "订单服务 压测 报告", ["conv:b"])])
    assert [i for i, _ in idx.search("订单服务", 5, {"conv:a"})] == ["1"]
    assert "maximumpoolsize" in tokenize("maximumPoolSize")


def test_segmenter_disentangles_interleaved_topics():
    # 两个话题交织：A（向量 e1）与 B（向量 e2），回复关系与语义共同决定归属
    e1, e2 = np.array([1.0, 0, 0]), np.array([0, 1.0, 0])
    msgs, vecs, texts = [], {}, {}
    seq = [("A", 0), ("A", 60), ("B", 90), ("A", 120), ("B", 150), ("B", 200), ("A", 260)]
    for i, (t, ts) in enumerate(seq):
        m = _m(i, 1000 + ts, sender="u" + t, text=f"{t} 话题内容 {i}")
        msgs.append(m)
        vecs[m.msg_id] = e1 if t == "A" else e2
        texts[m.msg_id] = m.text
    topics = TopicSegmenter(threshold=0.45).segment("c", msgs, texts, vecs)
    groups = sorted(sorted(t.msg_ids) for t in topics)
    assert groups == [["m0", "m1", "m3", "m6"], ["m2", "m4", "m5"]]


def test_fixed_window():
    msgs = [_m(i, i * 60) for i in range(25)]
    assert len(FixedWindowSegmenter(window=10).segment("c", msgs)) == 3
