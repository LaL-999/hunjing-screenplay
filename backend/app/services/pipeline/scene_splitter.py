"""场景切分 Agent — PR#6。

输入:一章的段落列表 + 故事圣经
输出:scene boundaries(每个 scene 含 heading + paragraph_range + summary)

LLM 角色:剧本场景切分专家(prompt 在 prompts/scene_splitter.md)。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.services.llm_client import (
    LlmCallFailed,
    LlmJsonParseFailed,
    call_json,
)

logger = logging.getLogger(__name__)


# ============================================================
# 输入 / 输出数据结构
# ============================================================


@dataclass
class ChapterInput:
    """切分器输入 — 一章。"""

    chapter_number: int
    chapter_title: str | None
    paragraphs: list[dict]  # [{"index": 1, "text": "..."}, ...]
    story_bible: dict       # {"characters": [...], "locations": [...]}


@dataclass
class SceneHeading:
    """场景头三件套。"""

    int_ext: str            # INT | EXT | INT/EXT
    location_name: str
    time_of_day: str        # 日 | 夜 | 黄昏 | 黎明 | 深夜 | 凌晨 | 连续 | 稍后


@dataclass
class SplitScene:
    """切分输出的单场结果(尚未含 elements)。"""

    scene_index_in_chapter: int       # 1-based
    heading: SceneHeading
    summary: str
    characters_present: list[str]     # 角色名(故事圣经里的 name 或 aka)
    paragraph_range: tuple[int, int]  # [start, end] 1-based 段号(含端点)
    transition_to_next: str = ""      # 最后一场可空


@dataclass
class SplitResult:
    """切分结果。"""

    chapter_number: int
    scenes: list[SplitScene] = field(default_factory=list)
    llm_usage: dict = field(default_factory=lambda: {"input_tokens": 0, "output_tokens": 0})


# 允许的枚举(用于校验 LLM 输出)
_INT_EXT_ENUM = {"INT", "EXT", "INT/EXT"}
_TIME_OF_DAY_ENUM = {"日", "夜", "黄昏", "黎明", "深夜", "凌晨", "连续", "稍后"}
_TRANSITION_ENUM = {"CUT_TO", "FADE_OUT", "FADE_IN", "DISSOLVE_TO", "MATCH_CUT", "SMASH_CUT", "CONTINUOUS"}


# ============================================================
# Prompt 加载(模块级缓存)
# ============================================================


_PROMPT_PATH = Path(__file__).parent.parent.parent / "prompts" / "scene_splitter.md"
_SYSTEM_PROMPT: str | None = None


def _get_system_prompt() -> str:
    global _SYSTEM_PROMPT
    if _SYSTEM_PROMPT is None:
        if not _PROMPT_PATH.exists():
            raise FileNotFoundError(f"scene_splitter prompt not found: {_PROMPT_PATH}")
        _SYSTEM_PROMPT = _PROMPT_PATH.read_text(encoding="utf-8")
    return _SYSTEM_PROMPT


# ============================================================
# 主入口
# ============================================================


class SceneSplitError(Exception):
    """场景切分失败(LLM 不可达 / 输出不合规 / 修复 N 次后仍非法)。"""


def split_chapter(chapter: ChapterInput) -> SplitResult:
    """切分一章为场景列表。

    Args:
        chapter: 章节输入(段落 + 故事圣经)

    Returns:
        SplitResult — 含 scenes 列表 + LLM token usage

    Raises:
        SceneSplitError: LLM 失败或输出 N 次仍非法
    """
    if not chapter.paragraphs:
        # 空章 → 返 0 场景,不报错
        return SplitResult(chapter_number=chapter.chapter_number)

    user_input = {
        "chapter_number": chapter.chapter_number,
        "chapter_title": chapter.chapter_title or "",
        "paragraphs": chapter.paragraphs,
        "story_bible": chapter.story_bible,
    }

    try:
        parsed, usage = call_json(_get_system_prompt(), user_input, max_tokens=4000)
    except (LlmCallFailed, LlmJsonParseFailed) as e:
        raise SceneSplitError(f"LLM 切分失败:{e}") from e

    scenes_raw = parsed.get("scenes") if isinstance(parsed, dict) else None
    if not isinstance(scenes_raw, list):
        raise SceneSplitError("LLM 输出缺少 scenes 数组")

    paragraph_count = len(chapter.paragraphs)
    scenes = _parse_and_validate_scenes(scenes_raw, paragraph_count)

    if not scenes:
        raise SceneSplitError("LLM 输出的 scenes 全部不合法")

    return SplitResult(
        chapter_number=chapter.chapter_number,
        scenes=scenes,
        llm_usage=usage,
    )


# ============================================================
# 校验逻辑
# ============================================================


def _parse_and_validate_scenes(
    scenes_raw: list, paragraph_count: int,
) -> list[SplitScene]:
    """LLM 输出 → SplitScene 数组,跳过格式严重错误的,修补轻微问题。"""
    out: list[SplitScene] = []
    expected_idx = 1
    for raw in scenes_raw:
        if not isinstance(raw, dict):
            continue

        # heading 三件套
        heading_raw = raw.get("heading") or {}
        int_ext = str(heading_raw.get("int_ext", "")).upper().strip()
        if int_ext not in _INT_EXT_ENUM:
            int_ext = "INT"  # 默认
        location_name = str(heading_raw.get("location_name", "") or "未命名地点").strip()
        time_of_day = str(heading_raw.get("time_of_day", "") or "日").strip()
        if time_of_day not in _TIME_OF_DAY_ENUM:
            time_of_day = "日"

        # paragraph_range
        rng = raw.get("paragraph_range")
        if not (isinstance(rng, list) and len(rng) == 2):
            continue
        try:
            start = int(rng[0])
            end = int(rng[1])
        except (TypeError, ValueError):
            continue
        if start < 1 or end < start or end > paragraph_count:
            # 范围越界 — 截断到合法区间
            start = max(1, start)
            end = min(paragraph_count, max(start, end))

        # summary
        summary = str(raw.get("summary", "")).strip()[:200]
        if not summary:
            summary = f"第 {expected_idx} 场"

        # characters_present
        chars = raw.get("characters_present") or []
        if not isinstance(chars, list):
            chars = []
        chars = [str(c).strip() for c in chars if isinstance(c, str) and c.strip()]

        # transition_to_next
        transition = str(raw.get("transition_to_next", "")).upper().strip()
        if transition and transition not in _TRANSITION_ENUM:
            transition = "CUT_TO"

        out.append(
            SplitScene(
                scene_index_in_chapter=expected_idx,
                heading=SceneHeading(
                    int_ext=int_ext,
                    location_name=location_name,
                    time_of_day=time_of_day,
                ),
                summary=summary,
                characters_present=chars,
                paragraph_range=(start, end),
                transition_to_next=transition,
            )
        )
        expected_idx += 1

    return out


# ============================================================
# 便捷工具:从 DB 直接拉章节 + 圣经 + 切分
# ============================================================


def split_chapter_from_db(novel_id: str, chapter_id: str) -> SplitResult:
    """便捷入口 — 拉 DB 数据 + 调切分器。

    Raises:
        ValueError: novel 不存在 / chapter 不属于该 novel / 圣经不存在
        SceneSplitError: 切分失败
    """
    from app.services import ingest_service, story_bible_service

    novel = ingest_service.get_novel(novel_id)
    if novel is None:
        raise ValueError(f"novel_id {novel_id} 不存在")

    target_chapter = None
    for ch in novel["chapters"]:
        if ch["id"] == chapter_id:
            target_chapter = ch
            break
    if target_chapter is None:
        raise ValueError(f"chapter_id {chapter_id} 不属于 novel {novel_id}")

    paragraphs = ingest_service.get_chapter_paragraphs(chapter_id) or []
    paragraphs_input = [
        {"index": p["index_in_chapter"], "text": p["text"]} for p in paragraphs
    ]

    bible = story_bible_service.get_bible(novel_id)
    if bible is None:
        raise ValueError("故事圣经尚未创建 — 请先 POST /novels/{id}/story-bible 或 /story-bible/auto")

    # 喂给 LLM 的圣经精简版(节省 token)
    bible_input: dict[str, Any] = {
        "characters": [
            {"id": c["id"], "name": c["name"], "aka": c["aka"]}
            for c in bible.get("characters", [])
        ],
        "locations": [
            {"id": l["id"], "name": l["name"], "int_ext": l["int_ext"]}
            for l in bible.get("locations", [])
        ],
    }

    return split_chapter(
        ChapterInput(
            chapter_number=target_chapter["number"],
            chapter_title=target_chapter.get("title"),
            paragraphs=paragraphs_input,
            story_bible=bible_input,
        )
    )
