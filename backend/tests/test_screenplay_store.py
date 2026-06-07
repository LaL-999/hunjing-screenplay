"""screenplay_store 测试 — PR#10 commit 2(持久化层)。

测试矩阵(11 case):

DB 层(2):
  1. init_db 后 screenplays 表 + 索引存在
  2. 索引 idx_screenplays_novel_time 存在

save(3):
  3. save 返合法 UUID hex id
  4. save 后 DB 行存在,字段完整
  5. JSON 字段(stats / warnings / failed_chapters)往返一致(含中文)

read(4):
  6. get_latest_screenplay 多次保存 → 返最新一条
  7. get_latest_screenplay 未存过 → 返 None
  8. get_screenplay_by_id 存在 → 返完整(JSON 已 loads)
  9. get_screenplay_by_id 不存在 → 返 None

list + 级联(2):
 10. list_screenplays 同 novel 多次 save → 按 created_at 倒序
 11. 删 novel → 关联 screenplays 自动级联清除
"""
from __future__ import annotations

import time
from pathlib import Path

import pytest

from app.services import screenplay_store


# ============================================================
# fixtures
# ============================================================


@pytest.fixture
def temp_db(monkeypatch, tmp_path: Path):
    """每个测试一个独立 DB(避免相互污染)。"""
    db_file = tmp_path / "test_screenplay_store.db"
    from app.config import settings
    monkeypatch.setattr(settings, "database_path", db_file)
    from app.db.connection import init_db
    init_db()
    yield db_file


def _insert_novel(novel_id: str = "n_test", title: str = "测试小说") -> None:
    """造一个 novel 行(外键依赖,screenplays 不能孤立存在)。"""
    from app.db.connection import get_connection
    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO novels
               (id, title, source_format, source_filename, total_chars, total_chapters, uploaded_at)
               VALUES (?, ?, 'txt', 'test.txt', 100, 1, '2026-06-06T00:00:00Z')""",
            (novel_id, title),
        )
        conn.commit()
    finally:
        conn.close()


# ============================================================
# 1. DB 层
# ============================================================


def test_screenplays_table_exists_after_init(temp_db):
    """init_db 后 screenplays 表存在。"""
    from app.db.connection import get_connection
    conn = get_connection()
    try:
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='screenplays'"
        )
        assert cur.fetchone() is not None
    finally:
        conn.close()


def test_screenplays_index_exists(temp_db):
    """idx_screenplays_novel_time 索引存在(支撑 get_latest 性能)。"""
    from app.db.connection import get_connection
    conn = get_connection()
    try:
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_screenplays_novel_time'"
        )
        assert cur.fetchone() is not None
    finally:
        conn.close()


# ============================================================
# 2. save
# ============================================================


def test_save_returns_uuid_hex(temp_db):
    """save 返合法的 UUID hex(32 位小写十六进制)。"""
    _insert_novel("n1")
    sid = screenplay_store.save_screenplay(
        novel_id="n1",
        yaml_text="meta:\n  title: x",
        stats={},
        warnings=[],
        failed_chapters=[],
    )
    assert isinstance(sid, str)
    assert len(sid) == 32
    assert all(c in "0123456789abcdef" for c in sid)


def test_save_row_in_db(temp_db):
    """save 后 DB 行可查到,核心字段一致。"""
    _insert_novel("n1")
    sid = screenplay_store.save_screenplay(
        novel_id="n1",
        yaml_text="meta:\n  title: 测试",
        stats={"total_scenes": 3},
        warnings=[{"layer": "element", "path": "x", "message": "msg"}],
        failed_chapters=[5],
        schema_version="1.0",
        model_name="deepseek-chat",
    )
    from app.db.connection import get_connection
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM screenplays WHERE id = ?", (sid,),
        ).fetchone()
        assert row is not None
        assert row["novel_id"] == "n1"
        assert row["yaml_text"] == "meta:\n  title: 测试"
        assert row["schema_version"] == "1.0"
        assert row["model_name"] == "deepseek-chat"
        assert row["created_at"]   # 非空
    finally:
        conn.close()


def test_json_fields_roundtrip_with_chinese(temp_db):
    """stats / warnings / failed_chapters JSON 字段往返一致,中文不转义。"""
    _insert_novel("n1")
    stats = {"total_scenes": 5, "中文键": "中文值", "nested": {"a": [1, 2]}}
    warnings = [
        {"layer": "scene", "path": "scenes[0]", "message": "中文 message:跳过本场"},
        {"layer": "element", "path": "scenes[1].elements[2]", "message": "角色 '张三' 未找到"},
    ]
    failed = [3, 7, 12]
    sid = screenplay_store.save_screenplay(
        novel_id="n1",
        yaml_text="dummy",
        stats=stats,
        warnings=warnings,
        failed_chapters=failed,
    )
    got = screenplay_store.get_screenplay_by_id(sid)
    assert got is not None
    assert got["stats"] == stats
    assert got["warnings"] == warnings
    assert got["failed_chapters"] == failed


# ============================================================
# 3. read
# ============================================================


def test_get_latest_returns_most_recent(temp_db):
    """同 novel 多次 save → get_latest 返最新一条。"""
    _insert_novel("n1")
    sid1 = screenplay_store.save_screenplay(
        novel_id="n1", yaml_text="v1",
        stats={"v": 1}, warnings=[], failed_chapters=[],
    )
    time.sleep(0.01)   # 确保 created_at 不同(ISO 微秒精度)
    sid2 = screenplay_store.save_screenplay(
        novel_id="n1", yaml_text="v2",
        stats={"v": 2}, warnings=[], failed_chapters=[],
    )
    latest = screenplay_store.get_latest_screenplay("n1")
    assert latest is not None
    assert latest["id"] == sid2
    assert latest["yaml_text"] == "v2"
    assert latest["stats"]["v"] == 2


def test_get_latest_returns_none_when_never_saved(temp_db):
    """未存过任何剧本 → get_latest 返 None。"""
    _insert_novel("n1")
    assert screenplay_store.get_latest_screenplay("n1") is None


def test_get_by_id_returns_full_dict(temp_db):
    """按 id 查存在 → 返完整 dict,所有字段就位。"""
    _insert_novel("n1")
    sid = screenplay_store.save_screenplay(
        novel_id="n1",
        yaml_text="full yaml",
        stats={"total_scenes": 2, "total_pages_estimate": 3},
        warnings=[{"layer": "scene", "path": "x", "message": "m"}],
        failed_chapters=[1, 4],
        schema_version="1.0",
        model_name="deepseek-chat",
    )
    got = screenplay_store.get_screenplay_by_id(sid)
    assert got is not None
    # 所有 8 个返回字段全在
    expected_keys = {
        "id", "novel_id", "yaml_text", "stats", "warnings",
        "failed_chapters", "schema_version", "model_name", "created_at",
        # PR#16 版本树字段
        "parent_screenplay_id", "optimization_origin", "optimization_log",
    }
    assert set(got.keys()) == expected_keys
    assert got["id"] == sid
    assert got["novel_id"] == "n1"
    assert got["yaml_text"] == "full yaml"
    assert got["stats"]["total_scenes"] == 2
    assert got["warnings"][0]["layer"] == "scene"
    assert got["failed_chapters"] == [1, 4]
    assert got["model_name"] == "deepseek-chat"


def test_get_by_id_returns_none_when_not_found(temp_db):
    """按 id 查不存在 → 返 None,不抛异常。"""
    _insert_novel("n1")
    assert screenplay_store.get_screenplay_by_id("not-an-id") is None


# ============================================================
# 4. list + 级联
# ============================================================


def test_list_screenplays_sorted_by_created_at_desc(temp_db):
    """同 novel 多次 save → list 返按 created_at 倒序(最新在前)。"""
    _insert_novel("n1")
    sid1 = screenplay_store.save_screenplay(
        novel_id="n1", yaml_text="v1", stats={}, warnings=[], failed_chapters=[],
    )
    time.sleep(0.01)
    sid2 = screenplay_store.save_screenplay(
        novel_id="n1", yaml_text="v2", stats={}, warnings=[], failed_chapters=[],
    )
    time.sleep(0.01)
    sid3 = screenplay_store.save_screenplay(
        novel_id="n1", yaml_text="v3", stats={}, warnings=[], failed_chapters=[],
    )
    all_records = screenplay_store.list_screenplays("n1")
    assert len(all_records) == 3
    # 倒序:最新在前
    assert [r["id"] for r in all_records] == [sid3, sid2, sid1]


def test_cascade_delete_when_novel_removed(temp_db):
    """删 novel → 关联 screenplays 全部级联清除(外键 ON DELETE CASCADE)。"""
    _insert_novel("n1")
    sid1 = screenplay_store.save_screenplay(
        novel_id="n1", yaml_text="v1", stats={}, warnings=[], failed_chapters=[],
    )
    sid2 = screenplay_store.save_screenplay(
        novel_id="n1", yaml_text="v2", stats={}, warnings=[], failed_chapters=[],
    )
    # 删 novel
    from app.db.connection import get_connection
    conn = get_connection()
    try:
        conn.execute("DELETE FROM novels WHERE id = ?", ("n1",))
        conn.commit()
    finally:
        conn.close()
    # 关联 screenplays 应都被清掉
    assert screenplay_store.get_screenplay_by_id(sid1) is None
    assert screenplay_store.get_screenplay_by_id(sid2) is None
    assert screenplay_store.list_screenplays("n1") == []
