"""解析器统一数据结构。

三种格式(.txt / .epub / .docx)解析后都归一化到 ParsedNovel,
后续摄入服务无需区分来源。
"""
from __future__ import annotations

from dataclasses import dataclass, field


class ParserError(Exception):
    """解析失败 — 由具体解析器抛出,业务层捕获后返 400。"""


@dataclass
class ParsedChapter:
    """一章 — 标题 + 段落列表。段落 1-based index 在落库时再分配。"""
    number: int                                  # 1-based 章节号(全文连续)
    title: str | None                            # 章节标题(若提取到)
    paragraphs: list[str] = field(default_factory=list)

    @property
    def char_count(self) -> int:
        return sum(len(p) for p in self.paragraphs)

    @property
    def paragraph_count(self) -> int:
        return len(self.paragraphs)


@dataclass
class ParsedNovel:
    """整本小说 — 标题 + 来源格式 + 章节数组。"""
    title: str
    source_format: str                           # 'txt' | 'epub' | 'docx'
    chapters: list[ParsedChapter] = field(default_factory=list)

    @property
    def total_chars(self) -> int:
        return sum(c.char_count for c in self.chapters)

    @property
    def total_chapters(self) -> int:
        return len(self.chapters)
