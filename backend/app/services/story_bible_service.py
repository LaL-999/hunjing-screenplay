"""故事圣经 service — JSON 直接导入 + LLM 自动抽取。

数据流:
  - import_bible_from_json(novel_id, dict) → 直接落库
  - extract_bible_with_llm(novel_id, max_chapters=3) → 喂前 N 章给 LLM,
    返结构化人物/地点/关系/事件,再落库

ID 规则:
  - char_001 / loc_001 / rel_001 / evt_001(在每本书内 1-based)
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone

from app.db.connection import get_connection
from app.services import ingest_service
from app.services.llm_client import LlmCallFailed, LlmJsonParseFailed, call_json

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return uuid.uuid4().hex


# ============================================================
# 主入口 — JSON 导入
# ============================================================

def import_bible_from_json(novel_id: str, payload: dict) -> dict:
    """从用户提供的 JSON 导入故事圣经。

    payload 结构:
        {
          "characters": [
            {"name": "林深", "aka": ["林先生"], "description": "...", "is_protagonist": true},
            ...
          ],
          "locations": [
            {"name": "老城钟表铺", "int_ext": "INT", "description": "..."},
            ...
          ],
          "relationships": [
            {"source_name": "林深", "target_name": "陌生女子", "type": "陌生→交集", "description": "..."},
            ...
          ],
          "events": [
            {"description": "...", "chapter_number": 1, "participant_names": ["林深"]},
            ...
          ]
        }

    Returns:
        bible_id + 各表插入数

    Raises:
        ValueError: novel_id 不存在 / payload 不规范
    """
    # 检 novel 存在
    novel = ingest_service.get_novel(novel_id)
    if novel is None:
        raise ValueError(f"novel_id {novel_id} 不存在")

    characters = payload.get("characters") or []
    locations = payload.get("locations") or []
    relationships = payload.get("relationships") or []
    events = payload.get("events") or []

    if not isinstance(characters, list):
        raise ValueError("characters 必须是数组")

    return _persist_bible(novel_id, characters, locations, relationships, events, source="manual")


# ============================================================
# 主入口 — LLM 自动抽取
# ============================================================

_EXTRACT_SYSTEM_PROMPT = """你是一个小说文本分析专家。从用户提供的小说片段中抽取「故事圣经」— 角色 / 地点 / 关系 / 关键事件。

输出严格 JSON 格式:
{
  "characters": [
    {
      "name": "<人物规范名>",
      "aka": ["<别名 1>", "<代称>"],
      "description": "<一句话描述,< 80 字>",
      "is_protagonist": <true|false>
    }
  ],
  "locations": [
    {
      "name": "<地点规范名>",
      "int_ext": "<INT|EXT|INT/EXT>",
      "description": "<一句话描述,< 60 字>"
    }
  ],
  "relationships": [
    {
      "source_name": "<人物 A>",
      "target_name": "<人物 B>",
      "type": "<关系类型,如 父子 / 朋友 / 同事 / 陌生人>",
      "description": "<一句话,< 50 字>"
    }
  ],
  "events": [
    {
      "description": "<事件一句话,< 80 字>",
      "chapter_number": <该事件大致发生的章号>,
      "participant_names": ["<参与角色 1>", "<参与角色 2>"]
    }
  ]
}

规则:
- 只抽显式出现的人物 / 地点(不要凭空想象)
- relationships.source_name 和 target_name 必须出现在 characters 数组里
- events.participant_names 同理
- 不要输出 markdown / 注释 / 说明,只输出纯 JSON
- 主角(is_protagonist=true)最多 2 人
"""


def extract_bible_with_llm(novel_id: str, max_chapters: int = 3) -> dict:
    """LLM 自动抽取故事圣经。

    流程:
      1. 拉小说前 max_chapters 章原文
      2. 拼 prompt,调 call_json
      3. name → id 映射(确保 relationships / events 引用合法)
      4. 落库
    """
    novel = ingest_service.get_novel(novel_id)
    if novel is None:
        raise ValueError(f"novel_id {novel_id} 不存在")

    # 拉前 N 章原文
    text_chunks: list[str] = []
    for ch in novel["chapters"][:max_chapters]:
        paragraphs = ingest_service.get_chapter_paragraphs(ch["id"]) or []
        text_chunks.append(f"# 第 {ch['number']} 章 {ch['title'] or ''}\n")
        text_chunks.extend(p["text"] for p in paragraphs)
    full_text = "\n\n".join(text_chunks)

    # 截断超长(保护 prompt 不爆)
    MAX_INPUT_CHARS = 30000
    if len(full_text) > MAX_INPUT_CHARS:
        full_text = full_text[:MAX_INPUT_CHARS] + "\n\n[...原文过长已截断]"

    user_input = (
        f"作品标题:《{novel['title']}》\n\n"
        f"小说前 {max_chapters} 章原文:\n\n{full_text}"
    )

    try:
        parsed, usage = call_json(_EXTRACT_SYSTEM_PROMPT, user_input, max_tokens=4000)
    except (LlmCallFailed, LlmJsonParseFailed) as e:
        raise ValueError(f"LLM 抽取失败:{e}") from e

    # name → id 映射(LLM 不输出 id,我们生成)
    characters = parsed.get("characters") or []
    locations = parsed.get("locations") or []
    relationships = parsed.get("relationships") or []
    events = parsed.get("events") or []

    result = _persist_bible(
        novel_id, characters, locations, relationships, events, source="llm_extracted",
    )
    result["llm_usage"] = usage
    return result


# ============================================================
# 共享落库逻辑
# ============================================================

def _persist_bible(
    novel_id: str,
    characters: list[dict],
    locations: list[dict],
    relationships: list[dict],
    events: list[dict],
    source: str,
) -> dict:
    """落库(若该 novel 已有 bible,覆盖)。"""
    now = _now_iso()
    conn = get_connection()
    try:
        # 删旧(若有)
        old = conn.execute(
            "SELECT id FROM story_bibles WHERE novel_id = ?", (novel_id,),
        ).fetchone()
        if old:
            conn.execute("DELETE FROM story_bibles WHERE id = ?", (old["id"],))
            # CASCADE 自动清子表

        bible_id = _new_id()
        conn.execute(
            """INSERT INTO story_bibles (id, novel_id, source, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?)""",
            (bible_id, novel_id, source, now, now),
        )

        # 角色 — 同时记 name → id 映射
        # 注:DB 内部 id 用 UUID,避免不同 bible 之间的 char_NNN 全局冲突;
        # yaml_composer 会按顺序重新发 char_NNN(对外的 schema id)。
        name_to_char_id: dict[str, str] = {}
        for c in characters:
            cid = uuid.uuid4().hex
            name = (c.get("name") or "").strip()
            if not name:
                continue
            aka = c.get("aka") or []
            conn.execute(
                """INSERT INTO bible_characters
                   (id, bible_id, name, aka_json, description, is_protagonist)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    cid, bible_id, name,
                    json.dumps(aka, ensure_ascii=False),
                    (c.get("description") or "")[:500],
                    1 if c.get("is_protagonist") else 0,
                ),
            )
            name_to_char_id[name] = cid
            # 别名也映射
            for a in aka:
                if isinstance(a, str) and a:
                    name_to_char_id.setdefault(a, cid)

        # 地点
        for l in locations:
            lid = uuid.uuid4().hex
            name = (l.get("name") or "").strip()
            if not name:
                continue
            int_ext = l.get("int_ext", "INT")
            if int_ext not in ("INT", "EXT", "INT/EXT"):
                int_ext = "INT"
            conn.execute(
                """INSERT INTO bible_locations
                   (id, bible_id, name, int_ext, description)
                   VALUES (?, ?, ?, ?, ?)""",
                (lid, bible_id, name, int_ext, (l.get("description") or "")[:500]),
            )

        # 关系(过滤未知 name)
        rel_inserted = 0
        for r in relationships:
            src_name = (r.get("source_name") or "").strip()
            tgt_name = (r.get("target_name") or "").strip()
            src_id = name_to_char_id.get(src_name)
            tgt_id = name_to_char_id.get(tgt_name)
            if not src_id or not tgt_id:
                continue
            rid = uuid.uuid4().hex
            conn.execute(
                """INSERT INTO bible_relationships
                   (id, bible_id, source_char_id, target_char_id, type, description)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    rid, bible_id, src_id, tgt_id,
                    (r.get("type") or "未知")[:50],
                    (r.get("description") or "")[:500],
                ),
            )
            rel_inserted += 1

        # 事件
        for e in events:
            eid = uuid.uuid4().hex
            desc = (e.get("description") or "").strip()
            if not desc:
                continue
            participants = e.get("participant_names") or []
            participant_ids = [
                name_to_char_id[n] for n in participants
                if n in name_to_char_id
            ]
            conn.execute(
                """INSERT INTO bible_events
                   (id, bible_id, description, chapter_number, participant_ids_json)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    eid, bible_id, desc[:500],
                    e.get("chapter_number"),
                    json.dumps(participant_ids, ensure_ascii=False),
                ),
            )

        conn.commit()
    finally:
        conn.close()

    return {
        "bible_id": bible_id,
        "novel_id": novel_id,
        "source": source,
        "stats": {
            "characters": len(characters),
            "locations": len(locations),
            "relationships": rel_inserted,
            "events": len(events),
        },
    }


# ============================================================
# 查询
# ============================================================

def get_bible(novel_id: str) -> dict | None:
    """完整圣经 — 给前端显示用。"""
    conn = get_connection()
    try:
        bible = conn.execute(
            "SELECT * FROM story_bibles WHERE novel_id = ?", (novel_id,),
        ).fetchone()
        if bible is None:
            return None
        bible_id = bible["id"]

        chars = conn.execute(
            """SELECT id, name, aka_json, description, is_protagonist
                 FROM bible_characters WHERE bible_id = ? ORDER BY id""",
            (bible_id,),
        ).fetchall()
        locs = conn.execute(
            """SELECT id, name, int_ext, description
                 FROM bible_locations WHERE bible_id = ? ORDER BY id""",
            (bible_id,),
        ).fetchall()
        rels = conn.execute(
            """SELECT id, source_char_id, target_char_id, type, description
                 FROM bible_relationships WHERE bible_id = ? ORDER BY id""",
            (bible_id,),
        ).fetchall()
        evts = conn.execute(
            """SELECT id, description, chapter_number, participant_ids_json
                 FROM bible_events WHERE bible_id = ? ORDER BY id""",
            (bible_id,),
        ).fetchall()

        return {
            "id": bible_id,
            "novel_id": bible["novel_id"],
            "source": bible["source"],
            "created_at": bible["created_at"],
            "updated_at": bible["updated_at"],
            "characters": [
                {
                    "id": c["id"],
                    "name": c["name"],
                    "aka": json.loads(c["aka_json"] or "[]"),
                    "description": c["description"],
                    "is_protagonist": bool(c["is_protagonist"]),
                }
                for c in chars
            ],
            "locations": [dict(l) for l in locs],
            "relationships": [dict(r) for r in rels],
            "events": [
                {
                    "id": e["id"],
                    "description": e["description"],
                    "chapter_number": e["chapter_number"],
                    "participant_ids": json.loads(e["participant_ids_json"] or "[]"),
                }
                for e in evts
            ],
        }
    finally:
        conn.close()
