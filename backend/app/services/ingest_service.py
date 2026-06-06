"""小说摄入服务 — 解析 + 落库。

接 parser 的 ParsedNovel,展平成 SQLite 三表(novels / chapters / paragraphs)。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.db.connection import get_connection
from app.parsers import ParsedNovel


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return uuid.uuid4().hex


def persist_novel(parsed: ParsedNovel, source_filename: str) -> dict:
    """把解析结果存进 SQLite,返摄入摘要 dict。

    Args:
        parsed: 解析器输出
        source_filename: 原始上传文件名(只存档,不参与解析)

    Returns:
        {
          "novel_id": str,
          "title": str,
          "source_format": str,
          "total_chapters": int,
          "total_chars": int,
          "chapters": [
            {"id": str, "number": int, "title": str|None, "paragraph_count": int, "char_count": int},
            ...
          ]
        }
    """
    novel_id = _new_id()
    now = _now_iso()

    conn = get_connection()
    try:
        # 1. novel 行
        conn.execute(
            """INSERT INTO novels
               (id, title, source_format, source_filename, total_chars, total_chapters, uploaded_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                novel_id,
                parsed.title,
                parsed.source_format,
                source_filename,
                parsed.total_chars,
                parsed.total_chapters,
                now,
            ),
        )

        # 2. 每章 + 段落
        chapter_summaries: list[dict] = []
        for ch in parsed.chapters:
            chapter_id = _new_id()
            conn.execute(
                """INSERT INTO chapters
                   (id, novel_id, number, title, paragraph_count, char_count)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    chapter_id,
                    novel_id,
                    ch.number,
                    ch.title,
                    ch.paragraph_count,
                    ch.char_count,
                ),
            )

            # 段落批量插入
            para_rows = [
                (_new_id(), chapter_id, i + 1, text)
                for i, text in enumerate(ch.paragraphs)
            ]
            conn.executemany(
                """INSERT INTO paragraphs
                   (id, chapter_id, index_in_chapter, text)
                   VALUES (?, ?, ?, ?)""",
                para_rows,
            )

            chapter_summaries.append({
                "id": chapter_id,
                "number": ch.number,
                "title": ch.title,
                "paragraph_count": ch.paragraph_count,
                "char_count": ch.char_count,
            })

        conn.commit()
    finally:
        conn.close()

    return {
        "novel_id": novel_id,
        "title": parsed.title,
        "source_format": parsed.source_format,
        "total_chapters": parsed.total_chapters,
        "total_chars": parsed.total_chars,
        "chapters": chapter_summaries,
    }


def list_novels() -> list[dict]:
    """所有上传过的小说(按上传时间倒序)。"""
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT id, title, source_format, source_filename,
                      total_chars, total_chapters, uploaded_at
                 FROM novels
             ORDER BY uploaded_at DESC""",
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_novel(novel_id: str) -> dict | None:
    """单本详情 + 章节列表(不含段落正文)。"""
    conn = get_connection()
    try:
        novel_row = conn.execute(
            "SELECT * FROM novels WHERE id = ?", (novel_id,),
        ).fetchone()
        if novel_row is None:
            return None

        chapter_rows = conn.execute(
            """SELECT id, number, title, paragraph_count, char_count
                 FROM chapters
                WHERE novel_id = ?
             ORDER BY number""",
            (novel_id,),
        ).fetchall()

        out = dict(novel_row)
        out["chapters"] = [dict(r) for r in chapter_rows]
        return out
    finally:
        conn.close()


def get_chapter_paragraphs(chapter_id: str) -> list[dict] | None:
    """单章全部段落正文。"""
    conn = get_connection()
    try:
        chapter = conn.execute(
            "SELECT id FROM chapters WHERE id = ?", (chapter_id,),
        ).fetchone()
        if chapter is None:
            return None
        rows = conn.execute(
            """SELECT index_in_chapter, text
                 FROM paragraphs
                WHERE chapter_id = ?
             ORDER BY index_in_chapter""",
            (chapter_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
