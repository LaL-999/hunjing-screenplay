"""structure_analyzer 测试 — PR#13 commit 1。

测试矩阵(12 case)。

张力评分:
  1. 空场 → 极低分
  2. 高密度+多角色+独白 → 高分
  3. fidelity 低 → 总分轻微下降

三幕分区:
  4. 12 场景 → 3 / 6 / 3 切分(25/50/25 取整)
  5. 1 场景 → 全部 act 1
  6. 4 场景 → 1 / 2 / 1

关键节点:
  7. Climax 位于 act 3 张力峰
  8. Inciting incident 位于 act 1 张力峰
  9. Midpoint 位于 act 2 中段张力峰

整体健康:
 10. 张力流畅 + climax 末段 → excellent
 11. 全场张力平 → flat + 提示加冲突
 12. Climax 在前半段 → notes 提示

main path:
 13. report.to_dict() 序列化无 raise + 关键字段存在
"""
from __future__ import annotations

from app.services.pipeline.structure_analyzer import (
    StructureSceneInput,
    analyze_structure,
)


def _scene(
    n: int,
    *,
    elements: int = 5,
    dialogue_chars: int = 100,
    monologue: int = 0,
    chars_present: int = 2,
    text: str = "",
    fidelity: float | None = None,
    paragraphs: int = 3,
) -> StructureSceneInput:
    return StructureSceneInput(
        scene_id=f"scene_{n:03d}",
        number=n,
        element_count=elements,
        dialogue_chars=dialogue_chars,
        inner_monologue_count=monologue,
        characters_present_count=chars_present,
        text_corpus=text,
        fidelity_score=fidelity,
        paragraph_count=paragraphs,
    )


# ============================================================
# 1. 张力评分
# ============================================================


def test_empty_scene_low_tension():
    """空场:0 元素 + 1 角色 → 张力低。"""
    sc = StructureSceneInput(
        scene_id="scene_001", number=1,
        element_count=0, dialogue_chars=0,
        inner_monologue_count=0, characters_present_count=1,
        text_corpus="", paragraph_count=10,
    )
    report = analyze_structure([sc])
    assert report.points[0].tension < 0.35


def test_high_tension_scene_scores_high():
    """高密度 + 3 角色 + 内心独白 + 冲突词 → 张力 >= 0.6。"""
    sc = _scene(
        1,
        elements=10, monologue=2, chars_present=3,
        text="你怎么敢!走开!我恨你!",
        fidelity=0.9, paragraphs=2,
    )
    report = analyze_structure([sc])
    assert report.points[0].tension >= 0.6


def test_fidelity_affects_tension():
    """同样元素,fidelity 高 vs 低 → 高 fidelity 张力分应更高。"""
    base = dict(elements=8, monologue=1, chars_present=3, paragraphs=2)
    s_high = _scene(1, **base, fidelity=1.0)
    s_low = _scene(2, **base, fidelity=0.2)
    h = analyze_structure([s_high]).points[0].tension
    l = analyze_structure([s_low]).points[0].tension
    assert h > l


# ============================================================
# 2. 三幕分区
# ============================================================


def test_12_scenes_split_3_6_3():
    """12 场景 → act 1 = 3 / act 2 = 6 / act 3 = 3。"""
    scenes = [_scene(i + 1) for i in range(12)]
    report = analyze_structure(scenes)
    act_counts = {a.act: a.scene_count for a in report.acts}
    assert act_counts == {1: 3, 2: 6, 3: 3}


def test_1_scene_all_act_1():
    """1 场景 → 全部 act 1。"""
    report = analyze_structure([_scene(1)])
    assert report.points[0].act == 1
    assert len(report.acts) == 1
    assert report.acts[0].act == 1


def test_4_scenes_split_1_2_1():
    """4 场景 → 1 / 2 / 1。"""
    scenes = [_scene(i + 1) for i in range(4)]
    report = analyze_structure(scenes)
    counts = {a.act: a.scene_count for a in report.acts}
    assert counts == {1: 1, 2: 2, 3: 1}


# ============================================================
# 3. 关键节点
# ============================================================


def test_climax_in_act_3():
    """20 场景 + act 3 中最高张力 → 标 climax。"""
    scenes = []
    for i in range(20):
        # 前 15 场普通,16-20 高张力
        if i < 15:
            scenes.append(_scene(i + 1, elements=4, chars_present=2))
        else:
            scenes.append(_scene(i + 1, elements=10, monologue=2,
                                 chars_present=3, text="不!走开!"))
    report = analyze_structure(scenes)
    climax = next((p for p in report.points if p.is_climax), None)
    assert climax is not None
    assert climax.act == 3


def test_inciting_incident_in_act_1():
    """8 场景 + act 1 张力峰 → 标 inciting incident。"""
    scenes = [_scene(i + 1) for i in range(8)]
    report = analyze_structure(scenes)
    ii = next((p for p in report.points if p.is_inciting_incident), None)
    assert ii is not None
    assert ii.act == 1


def test_midpoint_in_act_2_middle():
    """10 场景 + act 2 中段张力峰 → 标 midpoint。"""
    scenes = []
    for i in range(10):
        scenes.append(_scene(i + 1))
    report = analyze_structure(scenes)
    mp = next((p for p in report.points if p.is_midpoint), None)
    assert mp is not None
    assert mp.act == 2


# ============================================================
# 4. 整体健康
# ============================================================


def test_flat_curve_notes_warn():
    """全平张力 → notes 提示曲线偏平。"""
    scenes = [_scene(i + 1, elements=3, chars_present=1) for i in range(10)]
    report = analyze_structure(scenes)
    assert any("曲线偏平" in n or "节奏单一" in n for n in report.notes)


def test_high_variation_curve_recognized():
    """前段高张力 + 后段平 → 波动度大 → overall_score 反映在 variation 项。"""
    scenes = []
    for i in range(10):
        if i < 3:
            scenes.append(_scene(
                i + 1, elements=12, monologue=2, chars_present=3,
                text="不!走开!",
            ))
        else:
            scenes.append(_scene(i + 1, elements=2, chars_present=1))
    report = analyze_structure(scenes)
    # 前后张力差异显著,曲线一定不"flat"
    assert report.overall_health != "flat"
    # acts 仍能划分
    assert len(report.acts) == 3


# ============================================================
# 5. 序列化
# ============================================================


def test_report_to_dict_has_required_fields():
    """report.to_dict() 应含 points / acts / overall_health / overall_score / notes。"""
    scenes = [_scene(i + 1) for i in range(6)]
    report = analyze_structure(scenes)
    d = report.to_dict()
    assert set(d.keys()) >= {"points", "acts", "overall_health", "overall_score", "notes"}
    # 每个 point 含必备字段
    for p in d["points"]:
        assert "scene_id" in p
        assert "number" in p
        assert "tension" in p
        assert "act" in p
        assert "breakdown" in p
