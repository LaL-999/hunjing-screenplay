"""场景保真度评分 — PR#12。

把每场景按 4 维度评 0-1 分,加权汇总后 → high / medium / low,
并产出"为什么扣分"的人话 reason,让作者一眼看出哪些场需要手动改。

4 个维度(程序级启发式,不调 LLM — 快 + 可复现 + 可单测):

  1. **dialogue_coverage**:dialogue+voiceover 元素总字数 / 原文段落字数
     → 理想区间 0.2-0.6;过低 = LLM 没把对白挖出来;过高 = LLM 编对白

  2. **character_alignment**:characters_present 名字是否真的在原文段落里出现
     → 100% 命中 = 1.0;漏了的角色 = 按比例扣分(LLM 编角色就在这里抓)

  3. **element_density**:(action+dialogue+VO 数) / 原文段落数
     → 理想 2-5 个 element / 段;过低 = 漏处理;过高 = 灌水

  4. **decision_completeness**:含内心独白时是否都被 adaptation_decision 兜底
     → 每条内心独白都有对应 decision = 1.0;遗漏比例扣分

加权:dialogue_coverage 0.30 / character_alignment 0.30 /
     element_density 0.20 / decision_completeness 0.20

总分映射:
  >= 0.80 → high
  >= 0.55 → medium
  否则     → low
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Iterable

from app.services.pipeline.adaptation_decision import AdaptationDecision
from app.services.pipeline.element_extractor import ScreenplayElement

logger = logging.getLogger(__name__)


# ============================================================
# 输入 / 输出
# ============================================================


@dataclass
class FidelityInput:
    """单场评分输入。"""

    scene_text: str                       # 原文段落拼接(给字数 + 角色名匹配)
    characters_present_names: list[str]   # split 输出的名字(可能含 aka)
    elements: list[ScreenplayElement]
    decisions: list[AdaptationDecision] = field(default_factory=list)
    # 角色解析时,name 和 aka 都算"出现过"
    character_aka_lookup: dict[str, list[str]] = field(default_factory=dict)


@dataclass
class DimensionScore:
    """单维度得分。"""

    name: str
    score: float                          # 0.0 ~ 1.0
    reason: str = ""                      # 一句话说明

    def to_dict(self) -> dict:
        return {"name": self.name, "score": round(self.score, 2), "reason": self.reason}


@dataclass
class FidelityResult:
    """评分结果。"""

    level: str                            # high / medium / low
    score: float                          # 加权 0-1
    dimensions: list[DimensionScore] = field(default_factory=list)
    reason: str = ""                      # 一句话总结(给作者看)
    issues: list[str] = field(default_factory=list)  # 低分维度的人话清单

    def to_dict(self) -> dict:
        out: dict[str, object] = {
            "level": self.level,
            "score": round(self.score, 2),
            "dimensions": [d.to_dict() for d in self.dimensions],
        }
        if self.reason:
            out["reason"] = self.reason
        if self.issues:
            out["issues"] = self.issues
        return out


# 权重
_WEIGHTS = {
    "dialogue_coverage": 0.30,
    "character_alignment": 0.30,
    "element_density": 0.20,
    "decision_completeness": 0.20,
}

# 等级阈值
_HIGH_THRESHOLD = 0.80
_MEDIUM_THRESHOLD = 0.55


# ============================================================
# 主入口
# ============================================================


def score_scene_fidelity(input: FidelityInput) -> FidelityResult:
    """单场评分。

    Returns:
        FidelityResult(level / score / dimensions / reason / issues)
    """
    dims = [
        _score_dialogue_coverage(input),
        _score_character_alignment(input),
        _score_element_density(input),
        _score_decision_completeness(input),
    ]

    weighted_sum = sum(d.score * _WEIGHTS[d.name] for d in dims)

    if weighted_sum >= _HIGH_THRESHOLD:
        level = "high"
    elif weighted_sum >= _MEDIUM_THRESHOLD:
        level = "medium"
    else:
        level = "low"

    # 找出低分维度,生成人话 issue 清单
    issues: list[str] = []
    for d in dims:
        if d.score < 0.55 and d.reason:
            issues.append(d.reason)

    # 总结一句话
    if level == "high":
        reason = "各维度均合规;对白与角色与原文对齐。"
    elif level == "medium":
        reason = "部分维度偏弱(见 issues),建议作者人工复核。"
    else:
        reason = "保真度较低 — LLM 可能漏处理或编造,强烈建议手动修订。"

    return FidelityResult(
        level=level,
        score=weighted_sum,
        dimensions=dims,
        reason=reason,
        issues=issues,
    )


# ============================================================
# 4 个维度的具体计算
# ============================================================


def _score_dialogue_coverage(inp: FidelityInput) -> DimensionScore:
    """对白覆盖度 = dialogue+voiceover 总字数 / 原文字数。

    理想区间 0.20 - 0.60:
      < 0.10:LLM 漏对白(原文有对话但没抽出来)→ score 低
      0.10 - 0.20:偏低,可能漏了一些 → 中
      0.20 - 0.60:正常 → 高
      > 0.60:可能 LLM 编对白 → 中
      > 0.80:严重灌水 → 低
    """
    name = "dialogue_coverage"
    src_len = max(1, len(inp.scene_text.replace(" ", "").replace("\n", "")))
    dlg_len = 0
    for el in inp.elements:
        if el.type in ("dialogue", "voiceover"):
            dlg_len += len((el.text or "").replace(" ", "").replace("\n", ""))

    ratio = dlg_len / src_len

    if 0.20 <= ratio <= 0.60:
        return DimensionScore(name, 1.0)
    if 0.10 <= ratio < 0.20:
        return DimensionScore(
            name, 0.7,
            f"对白覆盖偏低({ratio:.0%}),可能漏对话",
        )
    if 0.60 < ratio <= 0.80:
        return DimensionScore(
            name, 0.7,
            f"对白覆盖偏高({ratio:.0%}),可能 LLM 编对白",
        )
    if ratio < 0.10:
        return DimensionScore(
            name, 0.35,
            f"对白覆盖过低({ratio:.0%}),原文若有对话需复核",
        )
    # > 0.80
    return DimensionScore(
        name, 0.3,
        f"对白覆盖过高({ratio:.0%}),严重怀疑灌水",
    )


def _score_character_alignment(inp: FidelityInput) -> DimensionScore:
    """场景角色与原文段落对齐 = characters_present 在原文中真的出现的比例。

    考虑 aka 兜底:'阿墨' 找不到时,试 lookup 找主名 '林墨'。
    """
    name = "character_alignment"
    if not inp.characters_present_names:
        # 没角色 → 不扣分(纯描写场景合规)
        return DimensionScore(name, 1.0)

    src = inp.scene_text
    hits = 0
    miss_names: list[str] = []
    for char_name in inp.characters_present_names:
        if not isinstance(char_name, str):
            continue
        clean = char_name.strip()
        if not clean:
            continue
        # 直接命中
        if clean in src:
            hits += 1
            continue
        # 试 aka
        aliases = inp.character_aka_lookup.get(clean, [])
        if any(a in src for a in aliases):
            hits += 1
            continue
        miss_names.append(clean)

    total = max(1, len(inp.characters_present_names))
    score = hits / total

    if score >= 0.85:
        return DimensionScore(name, score)
    if miss_names:
        missed = ", ".join(miss_names[:3])
        return DimensionScore(
            name, max(0.2, score),
            f"声称在场角色 {len(miss_names)}/{total} 未在原文出现({missed}),可能 LLM 编角色",
        )
    return DimensionScore(name, score)


def _score_element_density(inp: FidelityInput) -> DimensionScore:
    """元素密度 = (action+dialogue+VO 数) / 原文段落数。

    估算原文段落数 = max(1, 字数 // 80)。
    理想 1.5 - 5 个 element / 段。
    """
    name = "element_density"
    el_count = sum(
        1 for el in inp.elements
        if el.type in ("action", "dialogue", "voiceover", "parenthetical")
    )
    src_chars = len(inp.scene_text.replace(" ", "").replace("\n", ""))
    estimated_paragraphs = max(1, src_chars // 80)
    ratio = el_count / estimated_paragraphs

    if 1.5 <= ratio <= 5.0:
        return DimensionScore(name, 1.0)
    if 1.0 <= ratio < 1.5:
        return DimensionScore(
            name, 0.75,
            f"元素密度偏低({ratio:.1f} 元素/段),可能漏处理",
        )
    if 5.0 < ratio <= 8.0:
        return DimensionScore(
            name, 0.75,
            f"元素密度偏高({ratio:.1f} 元素/段),可能 LLM 灌水",
        )
    if ratio < 1.0:
        return DimensionScore(
            name, 0.4,
            f"元素密度过低({ratio:.1f} 元素/段),原文细节几乎没还原",
        )
    return DimensionScore(
        name, 0.4,
        f"元素密度过高({ratio:.1f} 元素/段),疑似严重灌水",
    )


def _score_decision_completeness(inp: FidelityInput) -> DimensionScore:
    """内心独白决策完整度 = 含 is_inner_monologue 的 VO 是否都有 decision。

    若无内心独白 → 1.0(此维度不适用)。
    """
    name = "decision_completeness"
    inner_count = sum(
        1 for el in inp.elements
        if el.type == "voiceover" and el.is_inner_monologue
    )
    if inner_count == 0:
        return DimensionScore(name, 1.0)

    # 每个 inner monologue 应该对应一条 decision
    covered = len(inp.decisions)
    ratio = min(1.0, covered / inner_count)

    if ratio >= 1.0:
        return DimensionScore(name, 1.0)
    missing = inner_count - covered
    return DimensionScore(
        name,
        max(0.3, ratio),
        f"{missing}/{inner_count} 条内心独白未生成改编决策",
    )


# ============================================================
# 便利:批量评所有 scenes(给 compose_service 用)
# ============================================================


def score_all_scenes(
    inputs: Iterable[FidelityInput],
) -> list[FidelityResult]:
    """批量评分。"""
    return [score_scene_fidelity(inp) for inp in inputs]
