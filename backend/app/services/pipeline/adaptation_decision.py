"""改编决策 Agent — PR#9(差异化创新核心)。

遇到内心独白(voiceover.is_inner_monologue=True),不替作者决定,
给 3 备选 + 利弊,作者拍板:
  - voiceover:保留 V.O. 画外音
  - action_externalize:转可见动作
  - delete:删除,假设后续场景体现

主入口:
  propose_decisions(scene_text, characters, elements)
  → DecisionResult(含每条内心独白的 3 备选)

设计原则:
  - 只处理 voiceover + is_inner_monologue=True 元素
  - 其他元素(action / dialogue / parenthetical / 普通 voiceover)不动
  - 无任何待决策元素 → 不调 LLM,直接返空
  - LLM 输出严格校验:options 必须 3 个 + type 必须三选一 + recommended 必填
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
from app.services.pipeline.element_extractor import (
    CharacterRef,
    ScreenplayElement,
)

logger = logging.getLogger(__name__)


# ============================================================
# 输入 / 输出
# ============================================================


@dataclass
class AdaptationOption:
    """单个备选 — 3 类型其中之一。

    voiceover / action_externalize: 使用 text 字段(改写后内容)
    delete:使用 rationale 字段(为什么可删),text 留空
    """

    type: str                            # voiceover | action_externalize | delete
    text: str = ""                       # voiceover / action_externalize 必填,delete 留空
    pros: str = ""                       # voiceover / action_externalize 必填
    cons: str = ""                       # voiceover / action_externalize 必填
    rationale: str = ""                  # delete 必填,其他类型留空


@dataclass
class AdaptationDecision:
    """一条改编决策(一个内心独白对应 1 条 decision)。"""

    element_index: int                   # 原 elements 数组里的下标
    original_text: str                   # 内心独白原文
    options: list[AdaptationOption] = field(default_factory=list)   # 必有 3 个,顺序 V.O./action/delete
    recommended: str = "voiceover"       # 推荐 type(三选一)


@dataclass
class DecisionResult:
    """改编决策结果。"""

    decisions: list[AdaptationDecision] = field(default_factory=list)
    llm_usage: dict = field(default_factory=lambda: {"input_tokens": 0, "output_tokens": 0})

    def decision_count(self) -> int:
        return len(self.decisions)


_OPTION_TYPES = ["voiceover", "action_externalize", "delete"]
_OPTION_TYPES_SET = set(_OPTION_TYPES)


# ============================================================
# Prompt 加载
# ============================================================


_PROMPT_PATH = Path(__file__).parent.parent.parent / "prompts" / "adaptation_decision.md"
_SYSTEM_PROMPT: str | None = None


def _get_system_prompt() -> str:
    global _SYSTEM_PROMPT
    if _SYSTEM_PROMPT is None:
        if not _PROMPT_PATH.exists():
            raise FileNotFoundError(f"adaptation_decision prompt not found: {_PROMPT_PATH}")
        _SYSTEM_PROMPT = _PROMPT_PATH.read_text(encoding="utf-8")
    return _SYSTEM_PROMPT


# ============================================================
# 主入口
# ============================================================


class AdaptationDecisionError(Exception):
    """改编决策失败。"""


def propose_decisions(
    scene_text: str,
    scene_summary: str,
    scene_heading: dict,
    characters_in_scene: list[CharacterRef],
    elements: list[ScreenplayElement],
) -> DecisionResult:
    """对场景中的内心独白生成 3 备选。

    Args:
        scene_text: 完整场景原文(给 LLM 上下文)
        scene_summary: 场景一句话概要
        scene_heading: {int_ext, location_name, time_of_day}
        characters_in_scene: 角色清单
        elements: 已抽元素列表(只抽 is_inner_monologue=True 的处理)

    Returns:
        DecisionResult — 每条内心独白的 3 备选 + 推荐

    Raises:
        AdaptationDecisionError: LLM 失败 / 输出格式错乱
    """
    # 找出所有内心独白元素(带 index)
    monologue_pairs: list[tuple[int, ScreenplayElement]] = [
        (i, el) for i, el in enumerate(elements)
        if el.type == "voiceover" and el.is_inner_monologue
    ]

    # 无待决策 → 直接返
    if not monologue_pairs:
        return DecisionResult()

    # 构造 LLM 输入(只送内心独白,省 token)
    monologue_payload = [
        {
            "index": idx,
            "type": "voiceover",
            "character_name": el.character_name or "",
            "text": el.text,
            "is_inner_monologue": True,
        }
        for idx, el in monologue_pairs
    ]

    user_input = {
        "scene_summary": scene_summary,
        "scene_heading": scene_heading,
        "scene_text": scene_text,
        "characters_in_scene": [
            {"id": c.id, "name": c.name, "aka": c.aka}
            for c in characters_in_scene
        ],
        "monologue_elements": monologue_payload,
    }

    try:
        parsed, usage = call_json(_get_system_prompt(), user_input, max_tokens=4000)
    except (LlmCallFailed, LlmJsonParseFailed) as e:
        raise AdaptationDecisionError(f"LLM 改编决策失败:{e}") from e

    if not isinstance(parsed, dict):
        raise AdaptationDecisionError("LLM 输出根节点不是 dict")

    raw_decisions = parsed.get("decisions")
    if not isinstance(raw_decisions, list):
        raise AdaptationDecisionError("LLM 输出缺少 decisions 数组")

    valid_indexes = {idx for idx, _ in monologue_pairs}
    decisions = _parse_decisions(raw_decisions, valid_indexes, monologue_pairs)

    return DecisionResult(decisions=decisions, llm_usage=usage)


# ============================================================
# 校验逻辑
# ============================================================


def _parse_decisions(
    raw: list,
    valid_indexes: set[int],
    monologue_pairs: list[tuple[int, ScreenplayElement]],
) -> list[AdaptationDecision]:
    """LLM decisions → AdaptationDecision 数组,跳过严重非法的。

    校验:
      - element_index 必须在 valid_indexes(指向 monologue_elements 中的下标)
      - options 必须有 3 个,且 type 覆盖 {voiceover, action_externalize, delete}
      - voiceover / action_externalize 的 text 必填
      - delete 的 rationale 必填
      - recommended 必须三选一,缺失 → 默认 voiceover
    """
    out: list[AdaptationDecision] = []
    seen_indexes: set[int] = set()
    # 建 index → original_text 映射,用于兜底
    index_to_text = {idx: el.text for idx, el in monologue_pairs}

    for item in raw:
        if not isinstance(item, dict):
            continue

        idx_raw = item.get("element_index")
        try:
            idx = int(idx_raw)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            continue
        if idx not in valid_indexes:
            continue
        if idx in seen_indexes:
            continue

        original_text = str(item.get("original_text", "")).strip()
        if not original_text:
            # 兜底用原 element text
            original_text = index_to_text.get(idx, "")
        original_text = original_text[:1000]

        # options
        raw_options = item.get("options")
        if not isinstance(raw_options, list):
            continue
        options = _parse_options(raw_options)
        if not _options_complete(options):
            # 不齐 3 类型 → 跳过整条决策
            continue

        # recommended
        recommended = str(item.get("recommended", "")).strip().lower()
        if recommended not in _OPTION_TYPES_SET:
            recommended = "voiceover"

        out.append(
            AdaptationDecision(
                element_index=idx,
                original_text=original_text,
                options=options,
                recommended=recommended,
            )
        )
        seen_indexes.add(idx)

    return out


def _parse_options(raw_options: list) -> list[AdaptationOption]:
    """解析单条决策的 options(可能少于 3 个,后续检查完整性)。"""
    out: list[AdaptationOption] = []
    seen_types: set[str] = set()
    for opt in raw_options:
        if not isinstance(opt, dict):
            continue
        otype = str(opt.get("type", "")).strip().lower()
        if otype not in _OPTION_TYPES_SET:
            continue
        if otype in seen_types:
            continue   # 同 type 重复 → 取第一个

        text = str(opt.get("text", "")).strip()[:1000]
        pros = str(opt.get("pros", "")).strip()[:200]
        cons = str(opt.get("cons", "")).strip()[:200]
        rationale = str(opt.get("rationale", "")).strip()[:200]

        if otype in ("voiceover", "action_externalize"):
            if not text:
                continue   # 必须有 text
            out.append(
                AdaptationOption(type=otype, text=text, pros=pros, cons=cons)
            )
        else:  # delete
            if not rationale:
                rationale = "若紧接的对白或场景能体现该线索,可删"
            out.append(
                AdaptationOption(type="delete", rationale=rationale)
            )

        seen_types.add(otype)

    return out


def _options_complete(options: list[AdaptationOption]) -> bool:
    """3 类型必须齐(顺序无关)。"""
    types = {o.type for o in options}
    return types == _OPTION_TYPES_SET
