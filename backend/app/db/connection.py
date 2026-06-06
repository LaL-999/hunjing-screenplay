"""SQLite 连接管理 — 单文件 DB,启动时跑 schema.sql。

设计原则:
  - 每次 get_connection() 返一个新连接(SQLite 多线程时建议)
  - row_factory 设 sqlite3.Row,业务代码用 row["col"] 访问
  - foreign_keys=ON,删 novel 时级联清章节段落
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from app.config import settings


# 按顺序加载的 schema 文件(后加的表可引用先建的表)
_SCHEMA_FILES = [
    "schema.sql",                # PR#3:novels / chapters / paragraphs
    "story_bible_schema.sql",    # PR#4:故事圣经 5 张表
    "screenplay_schema.sql",     # PR#10:剧本组装持久化表
]


def get_connection() -> sqlite3.Connection:
    """返一个新连接,业务代码用完 close()。

    用法:
        conn = get_connection()
        try:
            ...
            conn.commit()
        finally:
            conn.close()
    """
    conn = sqlite3.connect(settings.database_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    """启动时调一次 — 按顺序执行所有 schema 文件(IF NOT EXISTS 幂等)。"""
    schemas_dir = Path(__file__).parent
    conn = get_connection()
    try:
        for filename in _SCHEMA_FILES:
            path = schemas_dir / filename
            if not path.exists():
                raise FileNotFoundError(f"{filename} not found at {path}")
            conn.executescript(path.read_text(encoding="utf-8"))
        conn.commit()
    finally:
        conn.close()
