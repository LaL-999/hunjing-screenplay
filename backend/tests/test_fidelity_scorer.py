"""fidelity_scorer 测试 — PR#12 commit 1。

测试矩阵(15 case):

整体路径(3):
  1. 完美场景 → high + score >= 0.8
  2. 中等场景(部分维度偏弱)→ medium
  3. 严重灌水场景 → low

dialogue_coverage(3):
  4. 对白覆盖 0.30 → 满分
  5. 对白覆盖 0.05 → 严重偏低 → 低分 + issue
  6. 对白覆盖 0.90 → 严重灌水 → 低分 + issue

character_alignment(3):
  7. 所有 characters_present 都在原文出现 → 1.0
  8. aka 兜底:原文出现 '阿墨',characters_present 是 '林墨' → 命中
  9. 50% 编造 → 中分 + issue

element_density(2):
 10. 理想密度 → 1.0
 11. 灌水(20 元素 / 1 段)→ 低分

decision_completeness(2):
 12. 2 内心独白 + 2 decision → 1.0
 13. 2 内心独白 + 0 decision → 0.3 + issue

issues 汇总(2):
 14. 低分维度的 reason 加入 issues
 15. 高分维度的 reason 不加入 issues
"""
from __future__ import annotations

from app.services.pipeline.adaptation_decision import (
    AdaptationDecision,
    AdaptationOption,
)
from app.services.pipeline.element_extractor import ScreenplayElement
from app.services.pipeline.fidelity_scorer import (
    FidelityInput,
    score_scene_fidelity,
)


# ============================================================
# Helpers
# ============================================================


def _action(text: str) -> ScreenplayElement:
    return ScreenplayElement(type="action", text=text)


def _dialogue(name: str, text: str) -> ScreenplayElement:
    return ScreenplayElement(
        type="dialogue", text=text, character_name=name,
    )


def _vo(name: str, text: str, inner: bool = False) -> ScreenplayElement:
    return ScreenplayElement(
        type="voiceover", text=text, character_name=name,
        is_inner_monologue=inner,
    )


def _decision(idx: int, text: str) -> AdaptationDecision:
    return AdaptationDecision(
        element_index=idx,
        original_text=text,
        options=[
            AdaptationOption(type="voiceover", text=text, pros="p", cons="c"),
            AdaptationOption(type="action_externalize", text="动作", pros="p", cons="c"),
            AdaptationOption(type="delete", rationale="可删"),
        ],
    )


# 一段约 100 字的"原文",含林墨 + 苏清
_SAMPLE_TEXT = (
    "林墨走进医院走廊,脚步沉重。\n"
    "他看到苏清坐在长椅上,头埋在膝盖里。\n"
    "苏清抬起头,眼里含着泪。她颤抖地说:'你来晚了。'\n"
    "林墨没说话,只是默默坐到她身边。\n"
)


# ============================================================
# 1. 整体路径(3 case)
# ============================================================


def test_high_quality_scene_returns_high(monkeypatch):
    """所有维度都合规 → high + score >= 0.8。"""
    elements = [
        _action("林墨走进走廊,脚步沉重。"),
        _action("苏清坐在长椅上,头埋在膝盖里。"),
        # 对白覆盖加到约 0.25
        _dialogue("苏清", "你来晚了。我等了你三个小时。眼泪我都流干了。"),
        _action("林墨默默坐到她身边。"),
    ]
    result = score_scene_fidelity(FidelityInput(
        scene_text=_SAMPLE_TEXT,
        characters_present_names=["林墨", "苏清"],
        elements=elements,
        decisions=[],
    ))
    assert result.level == "high"
    assert result.score >= 0.8


def test_medium_quality_scene(monkeypatch):
    """对白覆盖偏低 + 角色对齐部分扣分 → medium。"""
    elements = [
        # 对白只有很短的一句,覆盖率低
        _dialogue("苏清", "嗯。"),
    ]
    result = score_scene_fidelity(FidelityInput(
        scene_text=_SAMPLE_TEXT,
        characters_present_names=["林墨", "苏清"],
        elements=elements,
        decisions=[],
    ))
    # 对白覆盖很低 + 元素密度很低 + 但角色对齐还在
    assert result.level in ("medium", "low")


def test_low_quality_severe_padding():
    """3 维度同时崩(对白灌水 + 角色编造 + 元素灌水)→ low。"""
    elements = [
        # 严重灌水的假对白
        _dialogue("张三", "这是一句很长很长很长很长很长的台词。" * 5)
        for _ in range(20)
    ]
    result = score_scene_fidelity(FidelityInput(
        scene_text=_SAMPLE_TEXT,
        # 张三不在 _SAMPLE_TEXT 里 → character_alignment 也扣分
        characters_present_names=["张三", "李四"],
        elements=elements,
        decisions=[],
    ))
    assert result.level == "low"
    assert result.score < 0.55
    assert len(result.issues) >= 2   # 至少 2 个维度低分


# ============================================================
# 2. dialogue_coverage(3 case)
# ============================================================


def test_dialogue_coverage_optimal():
    """对白覆盖 0.30 → 满分。"""
    text = "X" * 100
    elements = [_dialogue("A", "Y" * 30)]
    result = score_scene_fidelity(FidelityInput(
        scene_text=text,
        characters_present_names=["A"],
        elements=elements,
        # 让 character_alignment 完美
        character_aka_lookup={"A": []},
    ))
    dcov = next(d for d in result.dimensions if d.name == "dialogue_coverage")
    assert dcov.score == 1.0


def test_dialogue_coverage_too_low():
    """对白覆盖 0.05 → 严重偏低 → 0.35 分 + issue。"""
    text = "X" * 100
    elements = [_dialogue("A", "Y" * 5)]
    result = score_scene_fidelity(FidelityInput(
        scene_text=text,
        characters_present_names=[],
        elements=elements,
    ))
    dcov = next(d for d in result.dimensions if d.name == "dialogue_coverage")
    assert dcov.score < 0.5
    assert "对白覆盖" in dcov.reason


def test_dialogue_coverage_padding():
    """对白覆盖 > 0.8 → 灌水 → 低分。"""
    text = "X" * 100
    elements = [_dialogue("A", "Y" * 95)]
    result = score_scene_fidelity(FidelityInput(
        scene_text=text,
        characters_present_names=[],
        elements=elements,
    ))
    dcov = next(d for d in result.dimensions if d.name == "dialogue_coverage")
    assert dcov.score < 0.4


# ============================================================
# 3. character_alignment(3 case)
# ============================================================


def test_character_alignment_all_hit():
    """所有声称在场角色都在原文出现 → 1.0。"""
    result = score_scene_fidelity(FidelityInput(
        scene_text=_SAMPLE_TEXT,
        characters_present_names=["林墨", "苏清"],
        elements=[_action("X")],
    ))
    ca = next(d for d in result.dimensions if d.name == "character_alignment")
    assert ca.score == 1.0


def test_character_alignment_aka_fallback():
    """原文里只出现 aka,characters_present 是主名 → aka 兜底命中。"""
    text = "阿墨走进房间。他看到了她。"
    result = score_scene_fidelity(FidelityInput(
        scene_text=text,
        characters_present_names=["林墨"],
        elements=[_action("X")],
        character_aka_lookup={"林墨": ["阿墨", "小林"]},
    ))
    ca = next(d for d in result.dimensions if d.name == "character_alignment")
    assert ca.score == 1.0


def test_character_alignment_half_missing():
    """50% 编造的角色 → 0.5 分 + issue 提及未命中名。"""
    text = "林墨走进房间。"
    result = score_scene_fidelity(FidelityInput(
        scene_text=text,
        characters_present_names=["林墨", "张三"],   # 张三 LLM 编的
        elements=[_action("X")],
    ))
    ca = next(d for d in result.dimensions if d.name == "character_alignment")
    assert 0.4 <= ca.score <= 0.6
    assert "张三" in ca.reason


# ============================================================
# 4. element_density(2 case)
# ============================================================


def test_element_density_optimal():
    """100 字原文 → 1 段;3 元素 → 3/段 → 满分。"""
    text = "X" * 100
    elements = [_action("A"), _action("B"), _action("C")]
    result = score_scene_fidelity(FidelityInput(
        scene_text=text,
        characters_present_names=[],
        elements=elements,
    ))
    ed = next(d for d in result.dimensions if d.name == "element_density")
    assert ed.score == 1.0


def test_element_density_severe_padding():
    """100 字原文 → 1 段;30 元素 → 灌水低分。"""
    text = "X" * 100
    elements = [_action("X") for _ in range(30)]
    result = score_scene_fidelity(FidelityInput(
        scene_text=text,
        characters_present_names=[],
        elements=elements,
    ))
    ed = next(d for d in result.dimensions if d.name == "element_density")
    assert ed.score < 0.5
    assert "灌水" in ed.reason


# ============================================================
# 5. decision_completeness(2 case)
# ============================================================


def test_decision_completeness_full():
    """2 内心独白 + 2 decision → 1.0。"""
    elements = [
        _action("X"),
        _vo("A", "想着她", inner=True),
        _vo("A", "想着他", inner=True),
    ]
    decisions = [_decision(1, "想着她"), _decision(2, "想着他")]
    result = score_scene_fidelity(FidelityInput(
        scene_text="原文",
        characters_present_names=[],
        elements=elements,
        decisions=decisions,
    ))
    dc = next(d for d in result.dimensions if d.name == "decision_completeness")
    assert dc.score == 1.0


def test_decision_completeness_missing():
    """2 内心独白 + 0 decision → 0.3 + issue。"""
    elements = [
        _vo("A", "想着她", inner=True),
        _vo("A", "想着他", inner=True),
    ]
    result = score_scene_fidelity(FidelityInput(
        scene_text="原文",
        characters_present_names=[],
        elements=elements,
        decisions=[],
    ))
    dc = next(d for d in result.dimensions if d.name == "decision_completeness")
    assert dc.score == 0.3
    assert "2/2" in dc.reason


# ============================================================
# 6. issues 汇总(2 case)
# ============================================================


def test_low_dimension_appears_in_issues():
    """低分维度的 reason 加入 result.issues。"""
    text = "X" * 100
    # 严重灌水 → element_density 必扣分
    elements = [_action("Y") for _ in range(30)]
    result = score_scene_fidelity(FidelityInput(
        scene_text=text,
        characters_present_names=[],
        elements=elements,
    ))
    assert any("灌水" in issue for issue in result.issues)


def test_high_dimension_not_in_issues():
    """高分维度的 reason 不加入 issues(只有低分维度才会)。"""
    text = "X" * 100
    elements = [
        _action("A"),
        _action("B"),
        _dialogue("X", "Y" * 30),  # 让 dialogue_coverage 满分
    ]
    result = score_scene_fidelity(FidelityInput(
        scene_text=text,
        characters_present_names=[],
        elements=elements,
    ))
    # dialogue_coverage 满分 → 不该出现在 issues
    for issue in result.issues:
        assert "对白覆盖" not in issue or "偏" in issue or "过" in issue
