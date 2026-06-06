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


_SCHEMA_PATH = Path(__file__).parent / "schema.sql"


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
    """启动时调一次 — 跑 schema.sql 创建所有表(IF NOT EXISTS)。"""
    if not _SCHEMA_PATH.exists():
        raise FileNotFoundError(f"schema.sql not found at {_SCHEMA_PATH}")
    schema_sql = _SCHEMA_PATH.read_text(encoding="utf-8")
    conn = get_connection()
    try:
        conn.executescript(schema_sql)
        conn.commit()
    finally:
        conn.close()
