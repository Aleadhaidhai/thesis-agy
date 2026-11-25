"""语音解析：FunASR Paraformer（VAD + ASR + 标点恢复），纯 CPU 可运行。

为避免语音模型与向量库 gRPC 客户端、MPS 模型在同一进程中相互干扰，默认在独立子进程中执行识别
（生产部署中对应独立的 ASR 推理服务）。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def _asr_model():
    from funasr import AutoModel
    return AutoModel(model="paraformer-zh", vad_model="fsmn-vad", punc_model="ct-punc",
                     disable_update=True, device="cpu")


def _transcribe_local(path: str | Path) -> str:
    res = _asr_model().generate(input=str(path), batch_size_s=300)
    return "".join(r.get("text", "") for r in res) if res else ""


def transcribe(path: str | Path) -> dict:
    if os.environ.get("EIM_ASR_INPROC") == "1":
        text = _transcribe_local(path)
    else:
        out = subprocess.run([sys.executable, "-m", "eim.parsing.audio", str(Path(path).resolve())], capture_output=True, text=True,
                             cwd=str(Path(__file__).resolve().parents[2]), timeout=600)
        line = next((l for l in reversed(out.stdout.splitlines()) if l.startswith("{\"transcript\"")), None)
        text = json.loads(line)["transcript"] if line else ""
    return {"text": f"【语音转写】{text}" if text else "【语音】（无法识别）", "transcript": text}


if __name__ == "__main__":
    print(json.dumps({"transcript": _transcribe_local(sys.argv[1])}, ensure_ascii=False))
