"""图像解析：OCR 文字识别 + 视觉语言模型（VLM）语义描述。

企业 IM 中的图片以截图为主（报错信息、配置界面、图表、白板照片），
单独依赖 OCR 会丢失版面与图表语义，单独依赖 VLM 则易遗漏精确的文字（如错误码、版本号），
因此本文采用“OCR 精确文本 + VLM 语义描述”互补的融合表示。
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from eim.llm import get_llm

CAPTION_PROMPT = (
    "你是企业知识库的图片标注助手。请用中文简洁描述这张图片，便于日后检索：\n"
    "1) 图片类型（如报错截图/系统界面/数据图表/流程图/文档照片/照片）；\n"
    "2) 核心内容与关键信息（如报错原因、图表趋势与关键数值、界面中的关键配置项）；\n"
    "3) 若有明显的文字标题或关键字段请保留原文。\n不超过150字，不要编造看不清的内容。"
)


@lru_cache(maxsize=1)
def _ocr_engine():
    from rapidocr_onnxruntime import RapidOCR
    return RapidOCR()


def ocr_image(path: str | Path, min_score: float = 0.5) -> str:
    """返回按阅读顺序（自上而下、自左而右）拼接的 OCR 文本。"""
    result, _ = _ocr_engine()(str(path))
    if not result:
        return ""
    # result: [[box, text, score], ...]
    items = [(box, text) for box, text, score in result if float(score) >= min_score]
    items.sort(key=lambda it: (round(it[0][0][1] / 12), it[0][0][0]))  # 按行聚合后从左到右
    lines: list[str] = []
    last_row = None
    for box, text in items:
        row = round(box[0][1] / 12)
        if last_row is not None and row == last_row:
            lines[-1] += " " + text
        else:
            lines.append(text)
        last_row = row
    return "\n".join(lines)


def caption_image(path: str | Path) -> str:
    try:
        return get_llm().vision(CAPTION_PROMPT, path)
    except Exception as e:  # VLM 不可用时降级为仅 OCR
        return f"[caption_unavailable: {type(e).__name__}]"


def parse_image(path: str | Path, use_vlm: bool = True) -> dict:
    ocr = ocr_image(path)
    cap = caption_image(path) if use_vlm else ""
    if cap.startswith("[caption_unavailable"):
        cap = ""
    parts = []
    if cap:
        parts.append(f"【图片描述】{cap}")
    if ocr:
        parts.append(f"【图中文字】{ocr}")
    return {"text": "\n".join(parts) or "【图片】（无可识别内容）", "ocr": ocr, "caption": cap}
