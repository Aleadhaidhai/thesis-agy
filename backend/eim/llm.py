"""OpenAI 兼容的大模型客户端（本地 Ollama / 生产 vLLM 通用）。"""
from __future__ import annotations

import base64
import json
import re
from pathlib import Path
from typing import Any

import httpx

from eim.config import settings


def _img_b64(path: str | Path) -> str:
    data = Path(path).read_bytes()
    ext = Path(path).suffix.lower().lstrip(".") or "png"
    ext = "jpeg" if ext == "jpg" else ext
    return f"data:image/{ext};base64,{base64.b64encode(data).decode()}"


_THINK_RE = re.compile(r"<think>.*?</think>", re.S)


class LLMClient:
    def __init__(self, base_url: str | None = None, api_key: str | None = None, model: str | None = None,
                 timeout: float | None = None):
        self.base_url = (base_url or settings.llm_base_url).rstrip("/")
        self.api_key = api_key or settings.llm_api_key
        self.model = model or settings.llm_model
        self.client = httpx.Client(timeout=timeout or settings.llm_timeout)

    def chat(self, messages: list[dict[str, Any]], model: str | None = None, temperature: float = 0.2,
             max_tokens: int = 1024, json_mode: bool = False, think: bool = False) -> str:
        msgs = list(messages)
        body: dict[str, Any] = {"model": model or self.model, "messages": msgs,
                                "temperature": temperature, "max_tokens": max_tokens}
        # Qwen3 等混合推理模型默认开启思考；检索/抽取类任务关闭思考以降低延迟（OpenAI 兼容参数，Ollama/vLLM 均支持）
        if not think:
            body["reasoning_effort"] = "none"
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        r = self.client.post(f"{self.base_url}/chat/completions", json=body,
                             headers={"Authorization": f"Bearer {self.api_key}"})
        r.raise_for_status()
        text = r.json()["choices"][0]["message"]["content"] or ""
        return _THINK_RE.sub("", text).strip()

    def chat_json(self, messages: list[dict[str, Any]], **kw) -> dict:
        text = self.chat(messages, json_mode=True, **kw)
        return parse_json(text)

    def vision(self, prompt: str, image_path: str | Path, model: str | None = None, max_tokens: int = 512) -> str:
        msgs = [{"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": _img_b64(image_path)}},
        ]}]
        return self.chat(msgs, model=model or settings.vlm_model, max_tokens=max_tokens, think=True)


def _append_no_think(content: Any) -> Any:
    if isinstance(content, str):
        return content + " /no_think"
    return content


def parse_json(text: str) -> dict:
    text = text.strip()
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return {}
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return {}


_default: LLMClient | None = None


def get_llm() -> LLMClient:
    global _default
    if _default is None:
        _default = LLMClient()
    return _default
