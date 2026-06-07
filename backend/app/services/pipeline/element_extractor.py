"""剧本元素抽取 Agent — PR#7。

输入:一个场景的原文 + 该场角色清单
输出:elements 数组(action / dialogue / parenthetical / voiceover)

LLM 角色:剧本格式专家(prompt 在 prompts/element_extractor.md)。

注:本 PR 不处理 transition 元素(由 split_chapter 的 transition_to_next 已经提供),
也不处理 flashback_*(罕见,后续 PR 加)。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

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
class CharacterRef:
    """场景中出现的角色引用(给 LLM 做对白归属)。"""

    id: str
    name: str
    aka: list[str] = field(default_factory=list)


@dataclass
class SceneTextInput:
    """元素抽取器输入 — 一个场景。"""

    scene_summary: str
    scene_heading: dict          # {int_ext, location_name, time_of_day}
    scene_text: str              # 本场原文(可跨多段,内部用 \n\n 分段)
    characters_in_scene: list[CharacterRef]


@dataclass
class ScreenplayElement:
    """剧本单个元素 — 按 type 区分含字段不同。"""

    type: str                            # action | dialogue | parenthetical | voiceover
    text: str
    character_name: str | None = None    # dialogue / voiceover 必填
    parenthetical: str | None = None     # dialogue 可选(表演提示)
    is_inner_monologue: bool = False     # voiceover 专用
    voice_source: str = "VO"             # voiceover 专用:VO=画外音 / OS=画外音效(PR#16 升级 3)


@dataclass
class ExtractResult:
    """元素抽取结果。"""

    elements: list[ScreenplayElement] = field(default_factory=list)
    llm_usage: dict = field(default_factory=lambda: {"input_tokens": 0, "output_tokens": 0})

    def count_by_type(self) -> dict[str, int]:
        """每种类型的元素数(给前端 / 监控看)。"""
        out: dict[str, int] = {}
        for el in self.elements:
            out[el.type] = out.get(el.type, 0) + 1
        return out


# 允许的元素类型
_ALLOWED_TYPES = {"action", "dialogue", "parenthetical", "voiceover"}

# 字段长度上限(对齐 SCHEMA_DESIGN.md)
_MAX_ACTION_LEN = 1000
_MAX_DIALOGUE_LEN = 2000
_MAX_PARENTHETICAL_LEN = 200
_MAX_VOICEOVER_LEN = 1000


# ============================================================
# Prompt 加载
# ============================================================


_PROMPT_PATH = Path(__file__).parent.parent.parent / "prompts" / "element_extractor.md"
_SYSTEM_PROMPT: str | None = None


def _get_system_prompt() -> str:
    global _SYSTEM_PROMPT
    if _SYSTEM_PROMPT is None:
        if not _PROMPT_PATH.exists():
            raise FileNotFoundError(f"element_extractor prompt not found: {_PROMPT_PATH}")
        _SYSTEM_PROMPT = _PROMPT_PATH.read_text(encoding="utf-8")
    return _SYSTEM_PROMPT


# ============================================================
# 主入口
# ============================================================


class ElementExtractError(Exception):
    """元素抽取失败(LLM 不可达 / 全部输出非法 / 空场景)。"""


def extract_elements(scene_input: SceneTextInput) -> ExtractResult:
    """抽取一个场景的剧本元素。

    Args:
        scene_input: 场景原文 + 角色清单 + 场景头

    Returns:
        ExtractResult — 含 elements 列表 + LLM token usage

    Raises:
        ElementExtractError: scene_text 为空 / LLM 失败 / 全部元素非法
    """
    if not scene_input.scene_text or not scene_input.scene_text.strip():
        raise ElementExtractError("场景原文为空,无法抽取元素")

    # 构造 LLM 输入
    user_input = {
        "scene_summary": scene_input.scene_summary,
        "scene_heading": scene_input.scene_heading,
        "scene_text": scene_input.scene_text,
        "characters_in_scene": [
            {"id": c.id, "name": c.name, "aka": c.aka}
            for c in scene_input.characters_in_scene
        ],
    }

    try:
        parsed, usage = call_json(_get_system_prompt(), user_input, max_tokens=4000)
    except (LlmCallFailed, LlmJsonParseFailed) as e:
        raise ElementExtractError(f"LLM 抽取失败:{e}") from e

    if not isinstance(parsed, dict):
        raise ElementExtractError("LLM 输出格式非法(根节点不是 dict)")

    elements_raw = parsed.get("elements")
    if not isinstance(elements_raw, list):
        raise ElementExtractError("LLM 输出缺少 elements 数组")

    valid_names = _build_valid_names(scene_input.characters_in_scene)
    elements = _parse_and_validate_elements(elements_raw, valid_names)

    if not elements:
        raise ElementExtractError("LLM 输出的 elements 全部非法")

    return ExtractResult(elements=elements, llm_usage=usage)


# ============================================================
# 校验 + 兜底
# ============================================================


def _build_valid_names(characters: list[CharacterRef]) -> dict[str, str]:
    """构建 {别名 → 规范名} 映射,用于 dialogue / voiceover 归属修正。

    规则:
      - name 自己也是合法 key
      - 每个 aka 都映射到 name
    """
    out: dict[str, str] = {}
    for c in characters:
        out[c.name] = c.name
        for a in c.aka:
            if isinstance(a, str) and a.strip():
                out.setdefault(a.strip(), c.name)
    return out


def _parse_and_validate_elements(
    elements_raw: list, valid_names: dict[str, str],
) -> list[ScreenplayElement]:
    """LLM 输出 → ScreenplayElement 数组,跳过严重非法的。

    兜底策略:
      - type 非允许枚举 → 跳过
      - text 为空 → 跳过
      - dialogue / voiceover 缺 character_name → 跳过
      - character_name 不在 valid_names → 尝试用 aka 映射,失败则跳过
      - text 超长 → 截断
    """
    out: list[ScreenplayElement] = []
    for raw in elements_raw:
        if not isinstance(raw, dict):
            continue

        etype = str(raw.get("type", "")).strip().lower()
        if etype not in _ALLOWED_TYPES:
            continue

        text = str(raw.get("text", "")).strip()
        if not text:
            continue

        # 长度截断(对齐 SCHEMA_DESIGN.md)
        max_len = {
            "action": _MAX_ACTION_LEN,
            "dialogue": _MAX_DIALOGUE_LEN,
            "parenthetical": _MAX_PARENTHETICAL_LEN,
            "voiceover": _MAX_VOICEOVER_LEN,
        }[etype]
        if len(text) > max_len:
            text = text[: max_len - 1] + "…"

        # action / parenthetical:无需 character_name
        if etype in ("action", "parenthetical"):
            out.append(ScreenplayElement(type=etype, text=text))
            continue

        # dialogue / voiceover:必须 character_name
        char_raw = raw.get("character_name")
        if not isinstance(char_raw, str) or not char_raw.strip():
            continue
        # 用 valid_names 映射(把 aka 转规范名)
        canonical = valid_names.get(char_raw.strip())
        if canonical is None:
            # 没匹配到 — 跳过(LLM 编造的角色名不放进产物)
            continue

        if etype == "dialogue":
            parenthetical = raw.get("parenthetical")
            if isinstance(parenthetical, str) and parenthetical.strip():
                paren = parenthetical.strip()[:_MAX_PARENTHETICAL_LEN]
            else:
                paren = None
            out.append(
                ScreenplayElement(
                    type="dialogue",
                    text=text,
                    character_name=canonical,
                    parenthetical=paren,
                )
            )
        else:  # voiceover
            inner = bool(raw.get("is_inner_monologue", False))
            voice_source_raw = str(raw.get("voice_source", "VO")).strip().upper()
            voice_source = voice_source_raw if voice_source_raw in ("VO", "OS") else "VO"
            # O.S. 类型的不应该是内心独白
            if voice_source == "OS":
                inner = False
            out.append(
                ScreenplayElement(
                    type="voiceover",
                    text=text,
                    character_name=canonical,
                    is_inner_monologue=inner,
                    voice_source=voice_source,
                )
            )

    return out


# ============================================================
# 便捷工具:scene_text 从 DB paragraph_range 直接组装
# ============================================================


def build_scene_text(paragraphs: list[dict], start: int, end: int) -> str:
    """按 paragraph_range 拼接段落原文(段间空行)。

    Args:
        paragraphs: [{"index_in_chapter": 1, "text": "..."}, ...]
        start, end: 1-based 段号范围(含端点)

    Returns:
        拼接后的场景原文
    """
    selected = [
        p["text"] for p in paragraphs
        if start <= p["index_in_chapter"] <= end and p.get("text")
    ]
    return "\n\n".join(selected)
