-- ============================================================
-- 浑晶 · 剧创态 — 剧本组装持久化表(PR#10)
-- ============================================================
-- 设计原则:
--   1. 一次 compose 调 LLM 几十次,贵且慢 — 必须持久化,GET 直接返
--   2. 同一 novel 允许多次 compose(用户改 bible / 改章节后重跑)→ 新建一行
--   3. yaml_text 直接存 TEXT — demo YAML 撑死 50KB,SQLite 单字段几 MB 无忧
--   4. stats / warnings 用 TEXT 存 JSON,业务代码 json.loads 后用
--   5. 与 novels / chapters 表风格一致:TEXT PRIMARY KEY(UUID hex)
-- ============================================================

-- 剧本表 — 一次 compose 产出一行
CREATE TABLE IF NOT EXISTS screenplays (
    id              TEXT PRIMARY KEY,                  -- UUID hex
    novel_id        TEXT NOT NULL,                      -- 关联 novels.id
    yaml_text       TEXT NOT NULL,                      -- 完整剧本 YAML
    stats_json      TEXT NOT NULL DEFAULT '{}',         -- {total_scenes, total_pages_estimate, llm_calls, ...}
    warnings_json   TEXT NOT NULL DEFAULT '[]',         -- [{layer, path, message}, ...]
    failed_chapters_json TEXT NOT NULL DEFAULT '[]',    -- 整章降级的章节号列表
    schema_version  TEXT NOT NULL DEFAULT '1.0',        -- 对齐 meta.schema_version
    model_name      TEXT,                                -- 调用的 LLM 模型名(审计追溯)
    created_at      TEXT NOT NULL,                       -- ISO 8601(业务代码填,不依赖 SQLite CURRENT_TIMESTAMP)
    FOREIGN KEY (novel_id) REFERENCES novels(id) ON DELETE CASCADE
);

-- 查询模式:GET /novels/{id}/screenplay 取最新一条 → 按 (novel_id, created_at DESC)
CREATE INDEX IF NOT EXISTS idx_screenplays_novel_time
    ON screenplays(novel_id, created_at DESC);

-- ============================================================
-- 优化版本树(PR#16)
-- ============================================================
-- 用户对剧本做的每一次 AI 优化(整本 / 单场)都新建一行,parent_screenplay_id
-- 指向上一版,形成版本树:V1 → V2 → V3 ... 或 V1 → V2 → V3, V1 → V4(分叉)。
-- optimization_origin 标注本版本的来源(initial / single_scene_<id> / full_screenplay)。
-- optimization_log_json 存本次优化的 change_log + reasoning。
-- ============================================================

-- SQLite 不支持简单的 IF NOT EXISTS 加列,用 PRAGMA 检测 + ALTER
-- 在 connection.py 的 init_db 流程里,本文件被 executescript 调用 — 失败会被吞
-- 但 ADD COLUMN 没有 IF NOT EXISTS,所以下面用幂等的手法:CREATE TABLE 兜底建好,
-- 已存在则下面 ALTER 失败也无影响(由 connection.py 包裹 try-except 处理)。
-- 这里采用 SQL 注释表明字段意图,实际加列通过 migration runner 处理。

-- 占位:实际 ALTER 由 ensure_migrations() 走幂等检测加列(见 connection.py)
