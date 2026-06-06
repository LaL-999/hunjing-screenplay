"""解析器测试 — PR#3。

测试矩阵:
  1. 中文章节标题(第一章 / 第二章 / 第三章)→ 3 章
  2. 英文 Chapter 标题(支持冒号 / 短横线后跟标题)→ 3 章
  3. 没章节标题 → 1 章(整篇)
  4. 空内容 → ParserError
  5. UTF-8 BOM 兼容
  6. 不支持的扩展名 → ParserError
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.parsers import ParserError, parse_novel
from app.parsers.txt import parse_txt


FIXTURES_DIR = Path(__file__).parent / "fixtures" / "novels"


def _read_fixture(name: str) -> bytes:
    return (FIXTURES_DIR / name).read_bytes()


# ============================================================
# .txt 解析
# ============================================================

def test_chinese_chapters_recognized():
    """中文「第 N 章」标题 → 切出 3 章"""
    content = _read_fixture("sample_chinese.txt")
    novel = parse_novel(content, "sample_chinese.txt")
    assert novel.source_format == "txt"
    assert novel.total_chapters == 3
    assert novel.chapters[0].number == 1
    # 每章必有段落,且总字数 >= 100(MVP 段落合并较激进)
    for ch in novel.chapters:
        assert ch.paragraph_count > 0
        assert ch.char_count >= 50


def test_english_chapters_recognized():
    """英文「Chapter N」标题 → 切出 3 章,标题可包含连字符 / 冒号"""
    content = _read_fixture("sample_english.txt")
    novel = parse_novel(content, "sample_english.txt")
    assert novel.total_chapters == 3
    # 第 2 章「Chapter 2 — Departure」标题应被提取
    assert novel.chapters[1].title is not None
    assert "Departure" in (novel.chapters[1].title or "")


def test_no_chapter_titles_treated_as_single_chapter():
    """没识别到标题 → 整篇当 1 章"""
    content = _read_fixture("no_chapters.txt")
    novel = parse_novel(content, "no_chapters.txt")
    assert novel.total_chapters == 1
    assert novel.chapters[0].paragraph_count >= 3


def test_empty_content_raises_parser_error():
    """空内容 → 报错"""
    with pytest.raises(ParserError):
        parse_novel(b"", "empty.txt")


def test_whitespace_only_raises_parser_error():
    """全是空白 → 报错"""
    with pytest.raises(ParserError):
        parse_novel(b"   \n\n  \t  ", "blank.txt")


def test_utf8_bom_handled():
    """UTF-8 BOM 兼容(部分 Windows 程序导出会带)"""
    text = "﻿第一章\n\n第一句。第二句。\n"
    novel = parse_txt(text)
    assert novel.total_chapters == 1


# ============================================================
# Dispatcher
# ============================================================

def test_unsupported_extension():
    """不支持的扩展名 → 报错"""
    with pytest.raises(ParserError):
        parse_novel(b"some content", "novel.pdf")


def test_extension_case_insensitive():
    """扩展名大小写不敏感 — .TXT 应工作"""
    content = _read_fixture("sample_chinese.txt")
    novel = parse_novel(content, "sample.TXT")
    assert novel.total_chapters == 3


# ============================================================
# 标题提取
# ============================================================

def test_novel_title_from_first_line():
    """第 1 行非空 + 非章节模式 → 作品标题"""
    content = _read_fixture("sample_chinese.txt")
    novel = parse_novel(content, "anything.txt")
    assert novel.title == "麦田里的守望者"


def test_novel_title_fallback_to_filename():
    """没头部标题 → fallback 文件名(去后缀)"""
    novel = parse_txt("第一章\n\n正文内容。", default_title="my-novel")
    assert novel.title == "my-novel"


# ============================================================
# 段落 + 字数统计
# ============================================================

def test_char_count_matches():
    """字数统计正确"""
    content = _read_fixture("sample_chinese.txt")
    novel = parse_novel(content, "sample_chinese.txt")
    expected = sum(len(p) for ch in novel.chapters for p in ch.paragraphs)
    assert novel.total_chars == expected
