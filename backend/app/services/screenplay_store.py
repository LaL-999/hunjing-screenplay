"""剧本持久化服务 — PR#10 commit 2。

一次 compose 调 LLM 几十次,贵且慢。持久化后 GET 直接返,demo 视频
点查询是秒响应,不卡帧。

同一 novel 允许多次 compose(用户改 bible / 章节后重跑)→ 每次新建一行,
GET 默认返最新那条;list 接口给"历史版本对比"留口子(本 PR 不前端化)。

stats / warnings / failed_chapters 在 DB 存 JSON text,读取时 json.loads。
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from app.db.connection import get_connection


def _now_iso() -> str:
    """返 UTC ISO 8601 字符串,与 ingest_service 风格对齐。"""
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    """UUID hex 主键,与 novels / chapters 表风格对齐。"""
    return uuid.uuid4().hex


# ============================================================
# 写入
# ============================================================


def save_screenplay(
    novel_id: str,
    yaml_text: str,
    stats: dict,
    warnings: list[dict],
    failed_chapters: list[int],
    schema_version: str = "1.0",
    model_name: str | None = None,
    parent_screenplay_id: str | None = None,
    optimization_origin: str | None = None,
    optimization_log: dict | None = None,
) -> str:
    """持久化一次 compose 结果,返 screenplay_id。

    PR#16 新增 3 个字段:
        parent_screenplay_id: 上一版的 id(版本树父节点),initial compose 为 None
        optimization_origin: 'initial' | 'single_scene_<id>' | 'full_screenplay'
        optimization_log: {change_log, reasoning} — AI 优化日志(initial 为 None)

    Args:
        novel_id: 关联的 novels.id
        ... 见原参数
        parent_screenplay_id: 版本树父节点
        optimization_origin: 本版本的来源
        optimization_log: 优化过程的 change_log + reasoning

    Returns:
        新建的 screenplay_id(UUID hex)
    """
    screenplay_id = _new_id()
    now = _now_iso()

    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO screenplays
               (id, novel_id, yaml_text, stats_json, warnings_json,
                failed_chapters_json, schema_version, model_name, created_at,
                parent_screenplay_id, optimization_origin, optimization_log_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                screenplay_id,
                novel_id,
                yaml_text,
                json.dumps(stats, ensure_ascii=False),
                json.dumps(warnings, ensure_ascii=False),
                json.dumps(failed_chapters, ensure_ascii=False),
                schema_version,
                model_name,
                now,
                parent_screenplay_id,
                optimization_origin or "initial",
                json.dumps(optimization_log, ensure_ascii=False) if optimization_log else None,
            ),
        )
        conn.commit()
    finally:
        conn.close()

    return screenplay_id


# ============================================================
# 读取
# ============================================================


def _row_to_dict(row) -> dict[str, Any]:
    """sqlite Row → 业务 dict,JSON 字段反序列化。"""
    keys = row.keys() if hasattr(row, "keys") else []
    opt_log_raw = row["optimization_log_json"] if "optimization_log_json" in keys else None
    return {
        "id": row["id"],
        "novel_id": row["novel_id"],
        "yaml_text": row["yaml_text"],
        "stats": json.loads(row["stats_json"] or "{}"),
        "warnings": json.loads(row["warnings_json"] or "[]"),
        "failed_chapters": json.loads(row["failed_chapters_json"] or "[]"),
        "schema_version": row["schema_version"],
        "model_name": row["model_name"],
        "created_at": row["created_at"],
        "parent_screenplay_id": row["parent_screenplay_id"] if "parent_screenplay_id" in keys else None,
        "optimization_origin": row["optimization_origin"] if "optimization_origin" in keys else "initial",
        "optimization_log": json.loads(opt_log_raw) if opt_log_raw else None,
    }


def get_latest_screenplay(novel_id: str) -> dict | None:
    """返指定 novel 最新一次 compose 的剧本(按 created_at 倒序)。无则返 None。"""
    conn = get_connection()
    try:
        cur = conn.execute(
            """SELECT *
               FROM screenplays
               WHERE novel_id = ?
               ORDER BY created_at DESC
               LIMIT 1""",
            (novel_id,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return _row_to_dict(row)
    finally:
        conn.close()


def get_screenplay_by_id(screenplay_id: str) -> dict | None:
    """按 id 取一条剧本。无则返 None。"""
    conn = get_connection()
    try:
        cur = conn.execute(
            """SELECT *
               FROM screenplays
               WHERE id = ?""",
            (screenplay_id,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return _row_to_dict(row)
    finally:
        conn.close()


def list_versions_for_novel(novel_id: str) -> list[dict]:
    """返指定 novel 的所有版本(紧凑信息,不含 yaml_text 全文)— 给版本切换 UI 用。

    每条含:id, parent_screenplay_id, optimization_origin, created_at,
    + 摘要(scene_count + total_pages_estimate 从 stats 算)+ change_log 摘要。
    """
    conn = get_connection()
    try:
        cur = conn.execute(
            """SELECT id, parent_screenplay_id, optimization_origin,
                      optimization_log_json, stats_json, created_at
               FROM screenplays
               WHERE novel_id = ?
               ORDER BY created_at ASC""",
            (novel_id,),
        )
        out: list[dict] = []
        for row in cur.fetchall():
            stats = json.loads(row["stats_json"] or "{}")
            opt_log = json.loads(row["optimization_log_json"] or "null") if row["optimization_log_json"] else None
            out.append({
                "id": row["id"],
                "parent_screenplay_id": row["parent_screenplay_id"],
                "origin": row["optimization_origin"] or "initial",
                "created_at": row["created_at"],
                "scene_count": stats.get("total_scenes", 0),
                "change_count": len(opt_log.get("change_log", [])) if opt_log else 0,
                "reasoning_snippet": (opt_log.get("reasoning", "") if opt_log else "")[:80],
                # PR#16 Hot1:前端版本树展开"上次优化记录"需完整 log
                "optimization_log": opt_log,
            })
        return out
    finally:
        conn.close()


def list_screenplays(novel_id: str) -> list[dict]:
    """返指定 novel 的所有 compose 记录,按 created_at 倒序(最新在前)。

    给"历史版本对比"功能留口子(本 PR 不前端化)。
    """
    conn = get_connection()
    try:
        cur = conn.execute(
            """SELECT *
               FROM screenplays
               WHERE novel_id = ?
               ORDER BY created_at DESC""",
            (novel_id,),
        )
        return [_row_to_dict(row) for row in cur.fetchall()]
    finally:
        conn.close()
