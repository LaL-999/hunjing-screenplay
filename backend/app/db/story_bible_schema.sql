-- ============================================================
-- 故事圣经表 — PR#4
-- ============================================================
-- 一本小说对应一份故事圣经(1:1)。圣经里有 N 个角色/地点/关系/事件。
-- 复用浑晶平台的"中间态抽取"语义,但代码完全独立。
-- ============================================================

-- 故事圣经主表(每本小说 1 行,即使没填也存)
CREATE TABLE IF NOT EXISTS story_bibles (
    id          TEXT PRIMARY KEY,         -- UUID hex
    novel_id    TEXT NOT NULL UNIQUE,
    source      TEXT NOT NULL,             -- 'manual' (JSON import) | 'llm_extracted' | 'mixed'
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    FOREIGN KEY (novel_id) REFERENCES novels(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_bibles_novel ON story_bibles(novel_id);


-- 角色表
CREATE TABLE IF NOT EXISTS bible_characters (
    id              TEXT PRIMARY KEY,    -- char_NNN 格式(对齐 SCHEMA_DESIGN)
    bible_id        TEXT NOT NULL,
    name            TEXT NOT NULL,
    aka_json        TEXT,                 -- ["林先生", "老板"]
    description     TEXT,
    is_protagonist  INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (bible_id) REFERENCES story_bibles(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_bible_chars ON bible_characters(bible_id);


-- 地点表
CREATE TABLE IF NOT EXISTS bible_locations (
    id              TEXT PRIMARY KEY,    -- loc_NNN
    bible_id        TEXT NOT NULL,
    name            TEXT NOT NULL,
    int_ext         TEXT NOT NULL,        -- 'INT' | 'EXT' | 'INT/EXT'
    description     TEXT,
    FOREIGN KEY (bible_id) REFERENCES story_bibles(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_bible_locs ON bible_locations(bible_id);


-- 关系表(可选,场景切分时辅助)
CREATE TABLE IF NOT EXISTS bible_relationships (
    id              TEXT PRIMARY KEY,    -- rel_NNN
    bible_id        TEXT NOT NULL,
    source_char_id  TEXT NOT NULL,
    target_char_id  TEXT NOT NULL,
    type            TEXT NOT NULL,        -- '父子' | '夫妻' | '同事' | ...
    description     TEXT,
    FOREIGN KEY (bible_id) REFERENCES story_bibles(id) ON DELETE CASCADE,
    FOREIGN KEY (source_char_id) REFERENCES bible_characters(id) ON DELETE CASCADE,
    FOREIGN KEY (target_char_id) REFERENCES bible_characters(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_bible_rels ON bible_relationships(bible_id);


-- 事件表(关键剧情节点,后续场景切分时作锚点)
CREATE TABLE IF NOT EXISTS bible_events (
    id                  TEXT PRIMARY KEY,    -- evt_NNN
    bible_id            TEXT NOT NULL,
    description         TEXT NOT NULL,
    chapter_number      INTEGER,             -- 大致发生在哪一章(LLM 给的估计)
    participant_ids_json TEXT,                -- ["char_001", "char_002"]
    FOREIGN KEY (bible_id) REFERENCES story_bibles(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_bible_events ON bible_events(bible_id);
