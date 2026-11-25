"""向量化：BGE-M3（一次前向同时得到稠密向量与词汇权重稀疏向量）+ Chinese-CLIP（图文跨模态向量）。

BGE-M3 推理直接基于 transformers 实现（与官方 FlagEmbedding 计算方式一致）：
- 稠密向量：最后一层 [CLS] 隐状态，L2 归一化；
- 稀疏向量：w_t = ReLU(W_sparse · h_t)，同一 token id 取最大权重，去除特殊符号。
"""
from __future__ import annotations

import logging
import os
from functools import lru_cache

import numpy as np

from eim.config import settings

log = logging.getLogger(__name__)
if os.environ.get("EIM_HF_ENDPOINT"):          # 网络受限时可设为 https://hf-mirror.com
    os.environ.setdefault("HF_ENDPOINT", os.environ["EIM_HF_ENDPOINT"])


def _device():
    import torch
    if settings.device == "mps" and torch.backends.mps.is_available():
        return "mps"
    if settings.device == "cuda" and torch.cuda.is_available():
        return "cuda"
    return "cpu"


class TextEmbedder:
    """返回 dense: (n, d) 归一化矩阵；sparse: list[dict[token_id, weight]]。"""

    def __init__(self, backend: str | None = None):
        self.backend = backend or settings.embed_backend
        self._tok = self._model = self._sparse = None

    def _load(self):
        if self._model is None:
            import torch
            from huggingface_hub import snapshot_download
            from transformers import AutoModel, AutoTokenizer
            path = snapshot_download(settings.embed_model)
            self._dev = _device()
            self._tok = AutoTokenizer.from_pretrained(path)
            kw = {"dtype": torch.float16} if self._dev in ("mps", "cuda") else {}
            self._model = AutoModel.from_pretrained(path, **kw).eval().to(self._dev)
            sp = torch.nn.Linear(self._model.config.hidden_size, 1)
            sp.load_state_dict(torch.load(os.path.join(path, "sparse_linear.pt"), map_location="cpu"))
            self._sparse = sp.eval().to(self._dev)
            self._special = {self._tok.cls_token_id, self._tok.eos_token_id, self._tok.pad_token_id,
                             self._tok.unk_token_id}
        return self._model

    def encode(self, texts: list[str], batch_size: int = 16, sparse: bool = True, max_length: int = 1024) -> dict:
        if not texts:
            return {"dense": np.zeros((0, settings.embed_dim), dtype=np.float32), "sparse": []}
        if self.backend == "ollama":
            return {"dense": _ollama_embed(texts), "sparse": [{} for _ in texts]}
        import torch
        model = self._load()
        dense_all, sparse_all = [], []
        order = np.argsort([-len(t) for t in texts])          # 按长度排序减少 padding
        for i in range(0, len(texts), batch_size):
            idx = order[i:i + batch_size]
            batch = [texts[j] for j in idx]
            enc = self._tok(batch, padding=True, truncation=True, max_length=max_length, return_tensors="pt")
            enc = {k: v.to(self._dev) for k, v in enc.items()}
            with torch.no_grad():
                h = model(**enc).last_hidden_state
                d = torch.nn.functional.normalize(h[:, 0], dim=-1)
                dense_all.append((idx, d.float().cpu().numpy()))
                if sparse:
                    w = torch.relu(self._sparse(h.float())).squeeze(-1).cpu().numpy()
                    ids = enc["input_ids"].cpu().numpy()
                    mask = enc["attention_mask"].cpu().numpy()
                    for r in range(len(batch)):
                        dct: dict[int, float] = {}
                        for tid, wt, m in zip(ids[r], w[r], mask[r]):
                            if not m or tid in self._special or wt <= 0:
                                continue
                            if wt > dct.get(int(tid), 0.0):
                                dct[int(tid)] = float(wt)
                        sparse_all.append((idx[r], dct))
        dense = np.zeros((len(texts), settings.embed_dim), dtype=np.float32)
        for idx, d in dense_all:
            dense[idx] = d
        sp = [{} for _ in texts]
        for j, dct in sparse_all:
            sp[j] = dct
        return {"dense": dense, "sparse": sp}

    def encode_query(self, q: str) -> dict:
        r = self.encode([q], max_length=256)
        return {"dense": r["dense"][0], "sparse": r["sparse"][0]}


def _ollama_embed(texts: list[str]) -> np.ndarray:
    import httpx
    base = settings.llm_base_url.replace("/v1", "")
    r = httpx.post(f"{base}/api/embed", json={"model": "bge-m3", "input": texts}, timeout=300)
    r.raise_for_status()
    v = np.asarray(r.json()["embeddings"], dtype=np.float32)
    return v / (np.linalg.norm(v, axis=1, keepdims=True) + 1e-12)


class ClipEmbedder:
    def __init__(self):
        self._model = None
        self._proc = None

    def _load(self):
        if self._model is None:
            from transformers import ChineseCLIPModel, ChineseCLIPProcessor
            self._dev = _device()
            self._model = ChineseCLIPModel.from_pretrained(settings.clip_model).eval().to(self._dev)
            self._proc = ChineseCLIPProcessor.from_pretrained(settings.clip_model)
        return self._model, self._proc

    @staticmethod
    def _feat(out):
        return out if hasattr(out, "norm") else getattr(out, "pooler_output", out[0])

    def encode_images(self, paths: list[str], batch_size: int = 16) -> np.ndarray:
        import torch
        from PIL import Image
        model, proc = self._load()
        vecs = []
        for i in range(0, len(paths), batch_size):
            imgs = [Image.open(p).convert("RGB") for p in paths[i:i + batch_size]]
            with torch.no_grad():
                inp = proc(images=imgs, return_tensors="pt").to(self._dev)
                v = self._feat(model.get_image_features(**inp))
            vecs.append(torch.nn.functional.normalize(v, dim=-1).float().cpu().numpy())
        return np.concatenate(vecs).astype(np.float32) if vecs else np.zeros((0, settings.clip_dim), np.float32)

    def encode_text(self, texts: list[str]) -> np.ndarray:
        import torch
        model, proc = self._load()
        with torch.no_grad():
            inp = proc(text=texts, padding=True, truncation=True, max_length=52, return_tensors="pt").to(self._dev)
            v = self._feat(model.get_text_features(**inp))
        return torch.nn.functional.normalize(v, dim=-1).float().cpu().numpy().astype(np.float32)


@lru_cache(maxsize=1)
def get_text_embedder() -> TextEmbedder:
    return TextEmbedder()


@lru_cache(maxsize=1)
def get_clip_embedder() -> ClipEmbedder:
    return ClipEmbedder()
