"""全局配置。所有参数均可通过环境变量（前缀 EIM_）覆盖，便于实验时切换配置。"""
from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="EIM_", env_file=ROOT / ".env", extra="ignore")

    # ---------- 存储 ----------
    data_dir: Path = ROOT / "data"
    sqlite_path: Path = ROOT / "data" / "eim.db"
    milvus_uri: str = str(ROOT / "data" / "milvus.db")
    blob_dir: Path = ROOT / "data" / "blobs"

    # ---------- 模型服务（OpenAI 兼容接口；本地默认 Ollama，生产可切换 vLLM） ----------
    llm_base_url: str = "http://127.0.0.1:11434/v1"
    llm_api_key: str = "ollama"
    llm_model: str = "qwen3:8b"
    vlm_model: str = "qwen2.5vl:3b"
    llm_timeout: float = 180.0

    # ---------- 向量化 ----------
    embed_backend: str = "hf"              # hf: transformers 推理 BGE-M3（稠密+稀疏）；ollama: 仅稠密
    embed_model: str = "BAAI/bge-m3"
    embed_dim: int = 1024
    rerank_model: str = "BAAI/bge-reranker-v2-m3"
    clip_model: str = "OFA-Sys/chinese-clip-vit-base-patch16"
    clip_dim: int = 512
    device: str = "mps"                    # mps / cpu / cuda

    # ---------- 话题切分 ----------
    seg_time_gap_min: float = 15.0         # 时间尺度 τ（分钟），开发集上选定
    seg_sim_threshold: float = 0.45        # 语义相似度阈值
    seg_max_msgs: int = 40                 # 单个话题最大消息数
    seg_alpha: float = 0.6                 # 语义得分权重（开发集上选定）
    seg_beta: float = 0.2                  # 回复/提及关系权重
    seg_gamma: float = 0.2                 # 时间衰减权重

    # ---------- 检索 ----------
    topk_dense: int = 30
    topk_sparse: int = 30
    topk_visual: int = 10
    visual_min_sim: float = 0.40       # 视觉通路相似度门限（Chinese-CLIP 图文余弦），低于该值的结果不参与融合
    rrf_k: int = 60
    rerank_topn: int = 8
    time_decay_half_life_days: float = 180.0
    time_decay_weight: float = 0.1

    # ---------- Agent ----------
    agent_max_iters: int = 3
    agent_min_evidence_score: float = 0.35   # 最高重排分低于该值时标记低置信
    agent_evidence_floor: float = 0.05       # 重排分低于该值的证据不进入生成


settings = Settings()
for p in (settings.data_dir, settings.blob_dir):
    p.mkdir(parents=True, exist_ok=True)
