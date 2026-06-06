"""EPUB 解析 — 用 ebooklib 读 OPF spine,每个 ITEM 当一章。

EPUB 的 spine 顺序就是阅读顺序,不需要自己识别章节标题。
但段落需要从 XHTML 里挑 <p>。
"""
from __future__ import annotations

from io import BytesIO

import ebooklib
from bs4 import BeautifulSoup
from ebooklib import epub

from .base import ParsedChapter, ParsedNovel, ParserError


def parse_epub(content: bytes, default_title: str = "未命名作品") -> ParsedNovel:
    """解析 .epub 字节流。

    流程:
      1. ebooklib 读 EPUB,拿 metadata title + spine
      2. 遍历 spine 顺序的 ITEM,每个 ITEM 当 1 章
      3. 每个 ITEM 的 XHTML 用 BeautifulSoup 抽 <p> 文本
    """
    if not content:
        raise ParserError("文件内容为空")

    try:
        book = epub.read_epub(BytesIO(content))
    except Exception as e:
        raise ParserError(f"EPUB 解析失败:{e}") from e

    # 标题:metadata 优先,无则 fallback
    title = default_title
    try:
        metas = book.get_metadata("DC", "title")
        if metas:
            title = metas[0][0]
    except Exception:
        pass

    chapters: list[ParsedChapter] = []
    chapter_num = 0

    for item in book.spine:
        # spine 元素结构:(item_id, linear)
        item_id = item[0] if isinstance(item, tuple) else item
        item_obj = book.get_item_with_id(item_id)
        if item_obj is None or item_obj.get_type() != ebooklib.ITEM_DOCUMENT:
            continue

        try:
            html = item_obj.get_content().decode("utf-8", errors="ignore")
        except Exception:
            continue

        soup = BeautifulSoup(html, "html.parser")

        # 章节标题:第一个 h1/h2/h3
        ch_title = None
        for tag in soup.find_all(["h1", "h2", "h3"]):
            txt = tag.get_text(strip=True)
            if txt:
                ch_title = txt
                break

        # 段落:所有 <p> 内容
        paragraphs: list[str] = []
        for p in soup.find_all("p"):
            txt = p.get_text(strip=True)
            if txt:
                paragraphs.append(txt)

        if not paragraphs:
            continue   # 空章节(可能是封面页 / 目录页)

        chapter_num += 1
        chapters.append(
            ParsedChapter(number=chapter_num, title=ch_title, paragraphs=paragraphs),
        )

    if not chapters:
        raise ParserError("EPUB 内没有任何非空章节")

    return ParsedNovel(
        title=title,
        source_format="epub",
        chapters=chapters,
    )
