"""向量存储：Milvus（原型使用 Milvus Lite 本地文件模式，接口与 Milvus 集群一致）。

集合设计：
- mku_text   ：mku_id | dense(1024, IP) | sparse(BGE-M3 词汇权重, IP) | acl(ARRAY) | conv_id | kind | ts_end
- mku_visual ：mku_id | clip(512, IP) | acl(ARRAY) | conv_id | ts_end
ACL 以标量过滤表达式 array_contains_any(acl, [...]) 下推到向量检索内部，实现“先过滤后排序”，
避免后过滤导致的召回不足与越权泄露风险。
"""
from __future__ import annotations

import numpy as np
from pymilvus import DataType, MilvusClient

from eim.config import settings
from eim.models import MKU

TEXT_COL = "mku_text"
VIS_COL = "mku_visual"


def acl_expr(principals: list[str] | set[str] | None) -> str:
    if principals is None:          # None 表示管理员/离线评测模式：不过滤
        return ""
    if not principals:
        return 'mku_id == "__none__"'
    plist = ", ".join(f'"{p}"' for p in sorted(principals))
    return f"array_contains_any(acl, [{plist}])"


class VectorStore:
    def __init__(self, uri: str | None = None):
        if settings.device == "mps":  # 必须在 Milvus Lite fork 前初始化 Metal/MPS，避免 macOS 混合 fp16 崩溃
            import torch
            if torch.backends.mps.is_available():
                torch.zeros(1, device="mps")
        self.client = MilvusClient(uri or settings.milvus_uri)
        self._ensure()

    def _ensure(self):
        c = self.client
        if not c.has_collection(TEXT_COL):
            s = MilvusClient.create_schema(auto_id=False)
            s.add_field("mku_id", DataType.VARCHAR, is_primary=True, max_length=64)
            s.add_field("dense", DataType.FLOAT_VECTOR, dim=settings.embed_dim)
            s.add_field("sparse", DataType.SPARSE_FLOAT_VECTOR)
            s.add_field("acl", DataType.ARRAY, element_type=DataType.VARCHAR, max_capacity=256, max_length=128)
            s.add_field("conv_id", DataType.VARCHAR, max_length=128)
            s.add_field("kind", DataType.VARCHAR, max_length=32)
            s.add_field("ts_end", DataType.DOUBLE)
            ip = c.prepare_index_params()
            ip.add_index("dense", index_type="FLAT", metric_type="IP")   # 原型规模小用 FLAT；生产用 HNSW
            ip.add_index("sparse", index_type="SPARSE_INVERTED_INDEX", metric_type="IP")
            c.create_collection(TEXT_COL, schema=s, index_params=ip)
        if not c.has_collection(VIS_COL):
            s = MilvusClient.create_schema(auto_id=False)
            s.add_field("mku_id", DataType.VARCHAR, is_primary=True, max_length=64)
            s.add_field("clip", DataType.FLOAT_VECTOR, dim=settings.clip_dim)
            s.add_field("acl", DataType.ARRAY, element_type=DataType.VARCHAR, max_capacity=256, max_length=128)
            s.add_field("conv_id", DataType.VARCHAR, max_length=128)
            s.add_field("ts_end", DataType.DOUBLE)
            ip = c.prepare_index_params()
            ip.add_index("clip", index_type="FLAT", metric_type="IP")
            c.create_collection(VIS_COL, schema=s, index_params=ip)
        for col in (TEXT_COL, VIS_COL):      # 重新打开已有库时集合处于 released 状态，需显式加载
            c.load_collection(col)

    def reset(self):
        for col in (TEXT_COL, VIS_COL):
            if self.client.has_collection(col):
                self.client.drop_collection(col)
        self._ensure()

    # ---------- 写入 ----------
    def upsert_text(self, mkus: list[MKU], dense: np.ndarray, sparse: list[dict]):
        rows = [{"mku_id": m.mku_id, "dense": dense[i].tolist(), "sparse": sparse[i] or {0: 1e-6},
                 "acl": m.acl, "conv_id": m.conv_id, "kind": m.kind, "ts_end": m.ts_end}
                for i, m in enumerate(mkus)]
        if rows:
            self.client.upsert(TEXT_COL, rows)

    def upsert_visual(self, mkus: list[MKU], vecs: np.ndarray):
        rows = [{"mku_id": m.mku_id, "clip": vecs[i].tolist(), "acl": m.acl, "conv_id": m.conv_id,
                 "ts_end": m.ts_end} for i, m in enumerate(mkus)]
        if rows:
            self.client.upsert(VIS_COL, rows)

    def delete(self, mku_ids: list[str]):
        if not mku_ids:
            return
        ids = ", ".join(f'"{i}"' for i in mku_ids)
        for col in (TEXT_COL, VIS_COL):
            self.client.delete(col, filter=f"mku_id in [{ids}]")

    # ---------- 检索 ----------
    def _search(self, col: str, field: str, vec, k: int, principals, extra: str = "") -> list[tuple[str, float]]:
        expr = " and ".join(e for e in (acl_expr(principals), extra) if e)
        res = self.client.search(col, [vec], anns_field=field, limit=k, filter=expr,
                                 search_params={"metric_type": "IP"}, output_fields=["mku_id"])
        return [(h["entity"]["mku_id"], float(h["distance"])) for h in res[0]]

    def search_dense(self, vec: np.ndarray, k: int, principals=None, extra: str = ""):
        return self._search(TEXT_COL, "dense", vec.tolist(), k, principals, extra)

    def search_sparse(self, sp: dict, k: int, principals=None, extra: str = ""):
        if not sp:
            return []
        return self._search(TEXT_COL, "sparse", sp, k, principals, extra)

    def search_visual(self, vec: np.ndarray, k: int, principals=None, extra: str = ""):
        return self._search(VIS_COL, "clip", vec.tolist(), k, principals, extra)

    def count(self) -> dict:
        return {col: self.client.get_collection_stats(col).get("row_count", 0) for col in (TEXT_COL, VIS_COL)}
