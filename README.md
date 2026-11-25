# EIM-Agent：面向企业即时通讯的多模态知识检索 Agent 系统

硕士论文配套系统原型。全部组件均可本地私有化部署（无需 GPU，Apple Silicon 16 GB 可运行）。

## 目录结构

```
backend/eim/
  config.py            全局配置（模型、路径、检索参数）
  models.py            核心数据结构：Message / Attachment / MKU / Conversation
  adapters/            IM 适配器层（抽象接口 + IM 模拟器实现；企业 IM 实现不在本仓库）
  parsing/             多模态解析层：OCR / VLM / ASR / 文档 / 表格
  knowledge/           知识构建层：话题切分、MKU 构建、向量化、索引
  retrieval/           检索层：稠密/稀疏/视觉三路召回、RRF、重排、ACL 过滤
  agent/               Agent 编排层：工具、LangGraph 状态图、引用约束生成
  storage/             存储层：SQLite 元数据、Milvus Lite 向量库、本地对象存储
  api/                 FastAPI 服务
frontend/              IM 模拟器 + 管理后台（Vue3）
datasets/simeim/       模拟企业 IM 数据集 SimEIM 的生成与标注脚本
experiments/           评测脚本与云端 GPU notebook
thesis/                论文各章 Markdown 源稿与 Word 生成脚本
```

## 快速开始

```bash
uv venv --python 3.12 .venv && source .venv/bin/activate
uv pip install -e .
ollama serve &               # 本地 LLM / VLM / Embedding
ollama pull qwen3:8b qwen2.5vl:3b bge-m3
uvicorn eim.api.main:app --reload --app-dir backend
```
