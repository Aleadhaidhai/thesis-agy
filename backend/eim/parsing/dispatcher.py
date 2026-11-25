"""多模态解析调度器：根据消息类型与附件 MIME 将消息路由至对应解析器，输出统一的 ParsedContent。"""
from __future__ import annotations

import logging
from pathlib import Path

from eim.config import settings
from eim.models import Message, Modality, MsgType, ParsedContent

log = logging.getLogger(__name__)

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp"}
AUDIO_EXT = {".wav", ".mp3", ".m4a", ".amr", ".ogg", ".silk", ".flac"}
SHEET_EXT = {".xlsx", ".xls", ".csv"}


class ParserDispatcher:
    def __init__(self, use_vlm: bool = True, use_asr: bool = True):
        self.use_vlm = use_vlm
        self.use_asr = use_asr
        self.page_dir = settings.blob_dir / "pages"

    def parse(self, msg: Message) -> list[ParsedContent]:
        if msg.type == MsgType.SYSTEM:
            return []
        if msg.type == MsgType.TEXT or msg.attachment is None or not msg.attachment.path:
            return [ParsedContent(msg_id=msg.msg_id, modality=Modality.TEXT, text=msg.text)] if msg.text else []
        path = Path(msg.attachment.path)
        ext = path.suffix.lower()
        try:
            if msg.type == MsgType.IMAGE or ext in IMAGE_EXT:
                return self._image(msg, path)
            if msg.type == MsgType.AUDIO or ext in AUDIO_EXT:
                return self._audio(msg, path)
            if ext in SHEET_EXT:
                return self._sheet(msg, path)
            return self._document(msg, path, ext)
        except Exception as e:  # 单条解析失败不影响整体入库
            log.exception("parse failed for %s: %s", msg.msg_id, e)
            return [ParsedContent(msg_id=msg.msg_id, modality=Modality.TEXT,
                                  text=f"【附件】{msg.attachment.name}（解析失败）", meta={"error": str(e)})]

    def _image(self, msg: Message, path: Path) -> list[ParsedContent]:
        from eim.parsing.image import parse_image
        r = parse_image(path, use_vlm=self.use_vlm)
        text = r["text"] + (f"\n【附言】{msg.text}" if msg.text else "")
        return [ParsedContent(msg_id=msg.msg_id, modality=Modality.IMAGE, text=text,
                              meta={"ocr": r["ocr"], "caption": r["caption"]}, image_path=str(path))]

    def _audio(self, msg: Message, path: Path) -> list[ParsedContent]:
        if not self.use_asr:
            return [ParsedContent(msg_id=msg.msg_id, modality=Modality.AUDIO, text="【语音】")]
        from eim.parsing.audio import transcribe
        r = transcribe(path)
        return [ParsedContent(msg_id=msg.msg_id, modality=Modality.AUDIO, text=r["text"],
                              meta={"transcript": r["transcript"]})]

    def _sheet(self, msg: Message, path: Path) -> list[ParsedContent]:
        from eim.parsing.table import parse_spreadsheet
        return [ParsedContent(msg_id=msg.msg_id, modality=Modality.TABLE, text=c["text"], chunk_index=i,
                              meta={"sheet": c["sheet"], "rows": c["rows"], "file": path.name})
                for i, c in enumerate(parse_spreadsheet(path))]

    def _document(self, msg: Message, path: Path, ext: str) -> list[ParsedContent]:
        from eim.parsing import document as D
        if ext == ".pdf":
            items = D.parse_pdf(path, self.page_dir)
        elif ext == ".docx":
            items = D.parse_docx(path)
        elif ext == ".pptx":
            items = D.parse_pptx(path)
        elif ext in {".txt", ".md", ".log", ".json", ".yaml", ".yml"}:
            items = D.parse_txt(path)
        else:
            return [ParsedContent(msg_id=msg.msg_id, modality=Modality.DOCUMENT,
                                  text=f"【附件】{msg.attachment.name}（暂不支持的格式）")]
        out = []
        for i, it in enumerate(items):
            meta = {k: v for k, v in it.items() if k not in {"text", "image_path"}}
            meta["file"] = path.name
            modality = Modality.TABLE if it.get("table") else Modality.DOCUMENT
            out.append(ParsedContent(msg_id=msg.msg_id, modality=modality, text=it["text"], chunk_index=i,
                                     meta=meta, image_path=it.get("image_path")))
        return out
