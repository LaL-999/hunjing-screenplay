-- ============================================================
-- 浑晶 · 剧创态 SQLite 数据库 schema
-- ============================================================
-- 设计原则:
--   1. 每段(paragraph)有稳定 index_in_chapter,后续场景切分能溯源回原文位置
--   2. 章节(chapter)number 从 1 起,与读者阅读顺序对齐
--   3. 软删除暂不做(MVP 直接 DELETE,简单优先)
-- ============================================================

-- 小说主表 — 用户上传的原始作品
CREATE TABLE IF NOT EXISTS novels (
    id              TEXT PRIMARY KEY,         -- UUID hex
    title           TEXT NOT NULL,             -- 作品标题(从文件名或元数据推断)
    source_format   TEXT NOT NULL,             -- 'txt' | 'epub' | 'docx'
    source_filename TEXT NOT NULL,             -- 原始上传文件名
    total_chars     INTEGER NOT NULL DEFAULT 0,
    total_chapters  INTEGER NOT NULL DEFAULT 0,
    uploaded_at     TEXT NOT NULL              -- ISO 8601
);

CREATE INDEX IF NOT EXISTS idx_novels_uploaded ON novels(uploaded_at DESC);


-- 章节表 — 自动分章后的结果
CREATE TABLE IF NOT EXISTS chapters (
    id                TEXT PRIMARY KEY,        -- UUID hex
    novel_id          TEXT NOT NULL,
    number            INTEGER NOT NULL,         -- 1-based 章节号
    title             TEXT,                     -- 章节标题(若提取到)
    paragraph_count   INTEGER NOT NULL DEFAULT 0,
    char_count        INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (novel_id) REFERENCES novels(id) ON DELETE CASCADE,
    UNIQUE (novel_id, number)
);

CREATE INDEX IF NOT EXISTS idx_chapters_novel ON chapters(novel_id, number);


-- 段落表 — 每段独立行,带稳定 index 用于溯源
CREATE TABLE IF NOT EXISTS paragraphs (
    id                  TEXT PRIMARY KEY,      -- UUID hex
    chapter_id          TEXT NOT NULL,
    index_in_chapter    INTEGER NOT NULL,       -- 1-based 段落号(章节内)
    text                TEXT NOT NULL,
    FOREIGN KEY (chapter_id) REFERENCES chapters(id) ON DELETE CASCADE,
    UNIQUE (chapter_id, index_in_chapter)
);

CREATE INDEX IF NOT EXISTS idx_paragraphs_chapter ON paragraphs(chapter_id, index_in_chapter);
