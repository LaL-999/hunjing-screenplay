"""统一入口 — 按文件扩展名 dispatch 到具体解析器。"""
from __future__ import annotations

from pathlib import Path

from .base import ParsedNovel, ParserError


def parse_novel(content: bytes, filename: str) -> ParsedNovel:
    """根据文件名后缀解析。

    Args:
        content: 文件字节流
        filename: 原始文件名(用于推断格式 + 当 fallback 标题)

    Raises:
        ParserError: 格式不支持 / 解析失败
    """
    suffix = Path(filename).suffix.lower().lstrip(".")
    default_title = Path(filename).stem

    if suffix == "txt":
        from .txt import parse_txt
        text = _decode_text(content)
        return parse_txt(text, default_title=default_title)

    if suffix == "epub":
        from .epub import parse_epub
        return parse_epub(content, default_title=default_title)

    if suffix == "docx":
        from .docx import parse_docx
        return parse_docx(content, default_title=default_title)

    raise ParserError(
        f"不支持的文件格式:.{suffix}(支持 .txt / .epub / .docx)"
    )


def _decode_text(content: bytes) -> str:
    """字节流 → 文本 — 顺序尝试 UTF-8 / GBK / GB18030,失败 fallback errors=replace。"""
    for enc in ("utf-8", "utf-8-sig", "gbk", "gb18030"):
        try:
            return content.decode(enc)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="replace")
