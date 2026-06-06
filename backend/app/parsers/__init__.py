"""小说文件解析器 — 统一入口 parse_novel()。

支持格式:.txt / .epub / .docx
统一输出:list[ParsedChapter],每章含 title + paragraphs
"""
from .base import ParsedChapter, ParsedNovel, ParserError
from .dispatcher import parse_novel

__all__ = ["ParsedChapter", "ParsedNovel", "ParserError", "parse_novel"]
