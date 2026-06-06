"""对白归属精修 Agent — PR#8。

在 PR#7 element_extractor 粗抽之后,对 dialogue / voiceover 元素做归属增强:
  - 代词消解:'他说' / '她答' / 零标注对白 → 正确角色
  - 上下文推断:对话轮转 + 上文动作主语 → 推断说话人
  - 幻觉过滤:LLM 编造的角色直接忽略

设计原则:
  - **保守优先**:不确定不修改(避免"修正"破坏 PR#7 的正确归属)
  - **覆写而非合并**:LLM 输出的 attributions[].character_name 直接覆盖原值
  - **空字段也能修补**:character_name 为空 / null 时,refiner 是主要来源

主入口:
  refine_attribution(scene_text, characters_in_scene, draft_elements)
  → 返新的 elements 列表(浅拷贝,不修改入参)
"""
from __future__ import annotations

import copy
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
class Attribution:
    """单条归属修正记录(供审计 / 前端显示用)。"""

    element_index: int          # draft_elements 数组里的下标
    character_name: str         # 修正后的规范名
    confidence: str             # high | medium | low
    reason: str                 # 一句话说明


@dataclass
class RefineResult:
    """归属精修结果。"""

    elements: list[ScreenplayElement] = field(default_factory=list)   # 修正后的元素列表
    attributions: list[Attribution] = field(default_factory=list)     # 修正记录(审计)
    llm_usage: dict = field(default_factory=lambda: {"input_tokens": 0, "output_tokens": 0})

    def changed_count(self) -> int:
        return len(self.attributions)


_CONFIDENCE_ENUM = {"high", "medium", "low"}


# ============================================================
# Prompt 加载
# ============================================================


_PROMPT_PATH = Path(__file__).parent.parent.parent / "prompts" / "dialogue_attributor.md"
_SYSTEM_PROMPT: str | None = None


def _get_system_prompt() -> str:
    global _SYSTEM_PROMPT
    if _SYSTEM_PROMPT is None:
        if not _PROMPT_PATH.exists():
            raise FileNotFoundError(f"dialogue_attributor prompt not found: {_PROMPT_PATH}")
        _SYSTEM_PROMPT = _PROMPT_PATH.read_text(encoding="utf-8")
    return _SYSTEM_PROMPT


# ============================================================
# 主入口
# ============================================================


class DialogueAttributionError(Exception):
    """对白归属精修失败(LLM 不可达 / 输出格式严重错乱)。"""


def refine_attribution(
    scene_text: str,
    characters_in_scene: list[CharacterRef],
    draft_elements: list[ScreenplayElement],
) -> RefineResult:
    """对已抽的 elements 做归属精修。

    保守策略:
      - 只动 dialogue / voiceover 元素的 character_name
      - action / parenthetical 完全不动
      - LLM 留空或返非法 → 保留原值
      - LLM 返编造的 character_name(不在 characters_in_scene)→ 忽略
      - draft_elements 为空 → 直接返空,不调 LLM

    Args:
        scene_text: 完整场景原文
        characters_in_scene: 角色清单(含 aka)
        draft_elements: PR#7 输出的初抽元素

    Returns:
        RefineResult — 含修正后的 elements + 修正记录

    Raises:
        DialogueAttributionError: LLM 失败 / 输出非 dict / 无 attributions 字段
    """
    if not draft_elements:
        return RefineResult(elements=[], attributions=[])

    # 检查是否有任何 dialogue / voiceover 需要归属 — 若全是 action,直接返
    needs_refine = any(
        el.type in ("dialogue", "voiceover") for el in draft_elements
    )
    if not needs_refine:
        return RefineResult(elements=list(draft_elements), attributions=[])

    if not scene_text or not scene_text.strip():
        # 没原文上下文 — 无法做归属,原样返
        return RefineResult(elements=list(draft_elements), attributions=[])

    # 构造 LLM 输入
    user_input = {
        "scene_text": scene_text,
        "characters_in_scene": [
            {"id": c.id, "name": c.name, "aka": c.aka}
            for c in characters_in_scene
        ],
        "draft_elements": [
            {
                "index": i,
                "type": el.type,
                "character_name": el.character_name or "",
                "text": el.text,
            }
            for i, el in enumerate(draft_elements)
        ],
    }

    try:
        parsed, usage = call_json(_get_system_prompt(), user_input, max_tokens=3000)
    except (LlmCallFailed, LlmJsonParseFailed) as e:
        raise DialogueAttributionError(f"LLM 归属精修失败:{e}") from e

    if not isinstance(parsed, dict):
        raise DialogueAttributionError("LLM 输出根节点不是 dict")

    raw_attributions = parsed.get("attributions")
    if not isinstance(raw_attributions, list):
        raise DialogueAttributionError("LLM 输出缺少 attributions 数组")

    # 解析 + 校验
    valid_names = _build_valid_names(characters_in_scene)
    attributions = _parse_attributions(
        raw_attributions, draft_elements, valid_names,
    )

    # 应用修正(深拷贝避免污染入参)
    refined_elements = copy.deepcopy(draft_elements)
    for attr in attributions:
        idx = attr.element_index
        el = refined_elements[idx]
        # 只动 dialogue / voiceover(防御性)
        if el.type in ("dialogue", "voiceover"):
            el.character_name = attr.character_name

    return RefineResult(
        elements=refined_elements,
        attributions=attributions,
        llm_usage=usage,
    )


# ============================================================
# 校验逻辑
# ============================================================


def _build_valid_names(characters: list[CharacterRef]) -> dict[str, str]:
    """{name 或 aka → canonical name} 映射。"""
    out: dict[str, str] = {}
    for c in characters:
        out[c.name] = c.name
        for a in c.aka:
            if isinstance(a, str) and a.strip():
                out.setdefault(a.strip(), c.name)
    return out


def _parse_attributions(
    raw: list,
    draft_elements: list[ScreenplayElement],
    valid_names: dict[str, str],
) -> list[Attribution]:
    """解析 LLM attributions,过滤非法项。

    过滤规则:
      - index 越界或非整数 → 跳过
      - 指向 action / parenthetical 元素 → 跳过(防止 LLM 给错类型)
      - character_name 不在 valid_names → 跳过(防 LLM 编造)
      - confidence 不在枚举 → 默认 medium
      - reason 非字符串 → 默认空
    """
    out: list[Attribution] = []
    seen_indexes: set[int] = set()
    for item in raw:
        if not isinstance(item, dict):
            continue

        # index
        idx_raw = item.get("index")
        if not isinstance(idx_raw, int):
            try:
                idx = int(idx_raw)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                continue
        else:
            idx = idx_raw
        if idx < 0 or idx >= len(draft_elements):
            continue
        if idx in seen_indexes:
            continue   # 重复 index — 取第一个

        # 元素类型必须支持归属
        target_type = draft_elements[idx].type
        if target_type not in ("dialogue", "voiceover"):
            continue

        # character_name
        char_raw = item.get("character_name")
        if not isinstance(char_raw, str) or not char_raw.strip():
            continue
        canonical = valid_names.get(char_raw.strip())
        if canonical is None:
            continue   # LLM 编造的角色

        # confidence
        confidence = str(item.get("confidence", "")).strip().lower()
        if confidence not in _CONFIDENCE_ENUM:
            confidence = "medium"

        # reason
        reason_raw = item.get("reason", "")
        reason = str(reason_raw).strip()[:200] if isinstance(reason_raw, str) else ""

        out.append(
            Attribution(
                element_index=idx,
                character_name=canonical,
                confidence=confidence,
                reason=reason,
            )
        )
        seen_indexes.add(idx)

    return out
