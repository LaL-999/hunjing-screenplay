"""纯文本 .txt 解析 — 按章节标题正则自动分章。

支持的章节标题模式:
  - 「第 N 章」「第 N 回」「第 N 节」(中文)
  - 「Chapter N」「CHAPTER N」(英文)
  - 「# 标题」(Markdown 风格)
  - 「N. 标题」(数字 + 句点)

策略:
  1. 按行扫描,匹配章节标题正则的行 → 切分边界
  2. 边界之间的非空行 → 段落
  3. 没匹配到任何标题 → 整篇当 1 章(兜底)
"""
from __future__ import annotations

import re

from .base import ParsedChapter, ParsedNovel, ParserError


# 章节标题正则(优先级从高到低)
_CHAPTER_PATTERNS: list[tuple[str, re.Pattern]] = [
    # 中文章节:「第 1 章」「第 一 回」(支持中文数字)
    (
        "chinese_chapter",
        re.compile(
            r"^\s*第\s*[0-9零一二三四五六七八九十百千万]+\s*[章回节卷篇](?:\s+(.+))?\s*$"
        ),
    ),
    # 英文 Chapter
    (
        "english_chapter",
        re.compile(r"^\s*Chapter\s+\d+(?:\s*[:\-—]\s*(.+))?\s*$", re.IGNORECASE),
    ),
    # Markdown # 标题(1-2 层)
    (
        "markdown_heading",
        re.compile(r"^\s*#{1,2}\s+(.+)\s*$"),
    ),
    # 数字 + 句点 + 标题:「1. 起因」
    (
        "numbered_heading",
        re.compile(r"^\s*\d+\.\s+(.+)\s*$"),
    ),
]

_MIN_CHARS_PER_CHAPTER = 50   # 短于此的"章"算误判,合并到上一章


def parse_txt(text: str, default_title: str = "未命名作品") -> ParsedNovel:
    """解析 .txt 文本内容。

    Args:
        text: 完整文件内容(已 decode)
        default_title: 文件名推断不出标题时的兜底

    Raises:
        ParserError: 文本为空 / 全是空白
    """
    if not text or not text.strip():
        raise ParserError("文件内容为空")

    # 第 1 行若像标题(短行且无章节模式),取为作品名
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    novel_title = _extract_novel_title(lines, default_title)

    # 扫描章节边界
    boundaries = _find_chapter_boundaries(lines)
    if not boundaries:
        # 没识别到章节标题 — 整篇当 1 章
        paragraphs = _extract_paragraphs(lines)
        if not paragraphs:
            raise ParserError("文件没有非空段落")
        return ParsedNovel(
            title=novel_title,
            source_format="txt",
            chapters=[
                ParsedChapter(number=1, title=None, paragraphs=paragraphs),
            ],
        )

    # 按边界切分
    chapters: list[ParsedChapter] = []
    for idx, (line_idx, title) in enumerate(boundaries):
        next_boundary = (
            boundaries[idx + 1][0] if idx + 1 < len(boundaries) else len(lines)
        )
        chapter_lines = lines[line_idx + 1 : next_boundary]
        paragraphs = _extract_paragraphs(chapter_lines)
        if not paragraphs:
            continue   # 标题后没内容 — 跳过
        chapters.append(
            ParsedChapter(
                number=len(chapters) + 1,
                title=title,
                paragraphs=paragraphs,
            )
        )

    if not chapters:
        raise ParserError("识别到章节标题但提取不到任何内容")

    # 兜底:若有"章"段落太少(< _MIN_CHARS_PER_CHAPTER),合并到上一章
    chapters = _merge_tiny_chapters(chapters)

    return ParsedNovel(
        title=novel_title,
        source_format="txt",
        chapters=chapters,
    )


# ============================================================
# 辅助
# ============================================================

def _extract_novel_title(lines: list[str], fallback: str) -> str:
    """猜测作品标题 — 取第一行非空且非章节模式的内容。"""
    for ln in lines[:5]:  # 只看前 5 行
        s = ln.strip()
        if not s:
            continue
        # 不能是章节标题本身
        if any(p[1].match(s) for p in _CHAPTER_PATTERNS):
            return fallback
        # 太长的不像标题
        if len(s) > 50:
            return fallback
        return s
    return fallback


def _find_chapter_boundaries(lines: list[str]) -> list[tuple[int, str | None]]:
    """扫描所有行,返回 [(line_idx, title), ...] — 每条对应一个章节起点。"""
    boundaries: list[tuple[int, str | None]] = []
    for i, line in enumerate(lines):
        for name, pat in _CHAPTER_PATTERNS:
            m = pat.match(line)
            if m:
                # 提取标题(若 group 1 存在)
                title = m.group(1).strip() if m.lastindex else None
                # markdown_heading 的整行去掉 # 后就是标题
                if name == "markdown_heading":
                    title = m.group(1).strip()
                boundaries.append((i, title))
                break
    return boundaries


def _extract_paragraphs(lines: list[str]) -> list[str]:
    """连续非空行合并为一段(不严格,够用)。

    更严:行末有标点(。?!」"')才算段落结束 — MVP 不做。
    """
    paragraphs: list[str] = []
    buf: list[str] = []
    for line in lines:
        s = line.strip()
        if s:
            buf.append(s)
        else:
            if buf:
                paragraphs.append("".join(buf))
                buf = []
    if buf:
        paragraphs.append("".join(buf))
    return paragraphs


def _merge_tiny_chapters(chapters: list[ParsedChapter]) -> list[ParsedChapter]:
    """太小的章节并入上一章(防过度切分)。第 1 章不能并。"""
    if len(chapters) <= 1:
        return chapters
    merged: list[ParsedChapter] = [chapters[0]]
    for ch in chapters[1:]:
        if ch.char_count < _MIN_CHARS_PER_CHAPTER and merged:
            # 段落并入上一章
            merged[-1].paragraphs.extend(ch.paragraphs)
        else:
            merged.append(ch)
    # 重新编号
    for i, ch in enumerate(merged, start=1):
        ch.number = i
    return merged
