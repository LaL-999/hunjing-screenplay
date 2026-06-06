"""端到端 smoke — PR#10 commit 5(收尾)。

跟 commit 3-4 测试的差异:
  - commit 3 / 4 用 SQL INSERT 直接造 novel/chapter/paragraph 行
  - smoke 走真实的 parsers + ingest_service.persist_novel 链路
    -> 验证 parser 输出 → DB → compose 取数 → composer 组装 整条契约
  - 任何字段名错位 / 数据形状不匹配,smoke 会替我们最早抓到

测试矩阵(3 case):

完整链路(1):
  1. parse → persist → compose(全 LLM mock 成功)→ YAML 通过 schema 校验
     这一条覆盖了 parser/ingest/compose 三层契约对齐

降级链路(1):
  2. 真实摄入 + 部分章节 split 失败 → failed_chapters 正确 + 其他章节产出 YAML 仍校验通过

进度事件(1):
  3. progress_callback 接到的事件序列正确
     pipeline_start → chapter_done × N → assembling → pipeline_done
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.parsers import parse_novel
from app.services import compose_service, ingest_service
from app.services.pipeline.adaptation_decision import (
    AdaptationDecision,
    AdaptationOption,
    DecisionResult,
)
from app.services.pipeline.dialogue_attributor import RefineResult
from app.services.pipeline.element_extractor import (
    ExtractResult,
    ScreenplayElement,
)
from app.services.pipeline.scene_splitter import (
    SceneHeading,
    SceneSplitError,
    SplitResult,
    SplitScene,
)
from app.services.yaml_validator import validate_screenplay_yaml


FIXTURE = Path(__file__).parent / "fixtures" / "novels" / "sample_chinese.txt"


# ============================================================
# fixtures
# ============================================================


@pytest.fixture
def temp_db(monkeypatch, tmp_path: Path):
    db_file = tmp_path / "smoke.db"
    from app.config import settings
    monkeypatch.setattr(settings, "database_path", db_file)
    from app.db.connection import init_db
    init_db()
    yield db_file


def _ingest_sample_novel() -> str:
    """走真实 parser + ingest_service 落库,返 novel_id。"""
    content = FIXTURE.read_bytes()
    parsed = parse_novel(content, "sample_chinese.txt")
    summary = ingest_service.persist_novel(parsed, "sample_chinese.txt")
    return summary["novel_id"]


def _patch_bible_for_sample(monkeypatch) -> None:
    """sample_chinese.txt 主角是"我"和"琴",造 minimal bible。"""
    bible = {
        "characters": [
            {"id": "char_db_1", "name": "我", "aka": ["主角"], "description": "中学生叙述者"},
            {"id": "char_db_2", "name": "琴", "aka": [], "description": "主角思念的女孩"},
        ],
        "locations": [
            {"id": "loc_db_1", "name": "潘西中学", "int_ext": "EXT"},
        ],
    }
    from app.services import story_bible_service
    monkeypatch.setattr(story_bible_service, "get_bible", lambda nid: bible)


def _patch_pipeline_for_smoke(monkeypatch, *, ch_to_fail_split: int | None = None):
    """全 4 agent 默认 happy mock,可选让某章 split 失败。

    Returns:
        records dict — 记录每个 agent 被调次数,方便断言。
    """
    records = {"split_calls": [], "extract_calls": 0, "refine_calls": 0, "dec_calls": 0}

    def fake_split(ci):
        records["split_calls"].append(ci.chapter_number)
        if ch_to_fail_split is not None and ci.chapter_number == ch_to_fail_split:
            raise SceneSplitError(f"测试故意:章 {ci.chapter_number} 切分失败")
        return SplitResult(
            chapter_number=ci.chapter_number,
            scenes=[SplitScene(
                scene_index_in_chapter=1,
                heading=SceneHeading(
                    int_ext="EXT", location_name="潘西中学", time_of_day="日",
                ),
                summary=f"第 {ci.chapter_number} 章独白",
                characters_present=["我"],
                paragraph_range=(1, 1),
                transition_to_next="CUT_TO" if ci.chapter_number < 3 else "",
            )],
            llm_usage={},
        )

    def fake_extract(si):
        records["extract_calls"] += 1
        return ExtractResult(elements=[
            ScreenplayElement(type="action", text="主角站在原地。"),
            ScreenplayElement(
                type="voiceover", text="他/她在想什么。",
                character_name="我", is_inner_monologue=True,
            ),
        ], llm_usage={})

    def fake_refine(st, ch, els):
        records["refine_calls"] += 1
        return RefineResult(elements=list(els), attributions=[], llm_usage={})

    def fake_decisions(**kw):
        records["dec_calls"] += 1
        return DecisionResult(decisions=[AdaptationDecision(
            element_index=1,
            original_text="他/她在想什么。",
            options=[
                AdaptationOption(type="voiceover", text="V.O. 保留", pros="p", cons="c"),
                AdaptationOption(type="action_externalize", text="转动作", pros="p", cons="c"),
                AdaptationOption(type="delete", rationale="可删"),
            ],
            recommended="voiceover",
        )], llm_usage={})

    monkeypatch.setattr(compose_service, "split_chapter", fake_split)
    monkeypatch.setattr(compose_service, "extract_elements", fake_extract)
    monkeypatch.setattr(compose_service, "refine_attribution", fake_refine)
    monkeypatch.setattr(compose_service, "propose_decisions", fake_decisions)
    return records


# ============================================================
# 1. 完整链路
# ============================================================


def test_smoke_parse_ingest_compose_full_chain(temp_db, monkeypatch):
    """parse → persist → compose 全链路。

    验证 parser → ingest → compose_service → composer 之间的契约对齐。
    这一条覆盖最广,任何字段名错位 / 数据形状不匹配都会在这里抓到。
    """
    novel_id = _ingest_sample_novel()
    _patch_bible_for_sample(monkeypatch)
    records = _patch_pipeline_for_smoke(monkeypatch)

    result = compose_service.orchestrate_full_pipeline(novel_id)

    # 端到端基本契约
    assert result.screenplay_id
    assert result.yaml_text
    assert result.failed_chapters == []
    assert result.validation_errors == []

    # 每章都被切分调用过
    assert sorted(records["split_calls"]) == [1, 2, 3]
    # 每章 1 场 → 3 个 extract / refine / decision call
    assert records["extract_calls"] == 3
    assert records["refine_calls"] == 3
    assert records["dec_calls"] == 3

    # 最终 yaml 通过双层校验
    vr = validate_screenplay_yaml(result.yaml_text)
    assert vr.valid, f"smoke YAML 应通过校验,实际错误:{[i.message for i in vr.errors()]}"

    # 关键字段就位
    assert vr.parsed["meta"]["title"]
    assert len(vr.parsed["scenes"]) == 3
    assert len(vr.parsed["characters"]) == 2   # 我 + 琴
    assert vr.parsed["scenes"][0]["heading"]["location_id"] == "loc_001"
    # adaptation_decisions 段存在(每场都有一条)
    assert len(vr.parsed["adaptation_decisions"]) == 3


# ============================================================
# 2. 降级链路
# ============================================================


def test_smoke_partial_chapter_failure_does_not_break_pipeline(temp_db, monkeypatch):
    """让第 2 章 split 失败 → failed_chapters=[2] + 其他章产出 + YAML 仍校验通过。"""
    novel_id = _ingest_sample_novel()
    _patch_bible_for_sample(monkeypatch)
    records = _patch_pipeline_for_smoke(monkeypatch, ch_to_fail_split=2)

    result = compose_service.orchestrate_full_pipeline(novel_id)

    # 第 2 章降级
    assert result.failed_chapters == [2]
    assert result.stats["chapters_processed"] == 2   # 1 + 3
    assert result.stats["chapters_total"] == 3

    # 其他章节正常产出
    assert "scene_001" in result.yaml_text
    assert "scene_002" in result.yaml_text
    assert "scene_003" not in result.yaml_text   # 只 2 场入选

    # YAML 仍通过校验
    vr = validate_screenplay_yaml(result.yaml_text)
    assert vr.valid

    # warnings 中有 chapter 2 的失败记录
    chapter_warnings = [w for w in result.warnings if w["layer"] == "chapter"]
    assert any("chapter[2]" in w["path"] for w in chapter_warnings)


# ============================================================
# 3. 进度事件
# ============================================================


def test_smoke_fidelity_scoring_written_to_yaml(temp_db, monkeypatch):
    """PR#12:每个 scene 应被评分,fidelity 字段写入 YAML."""
    from app.services.yaml_validator import validate_screenplay_yaml

    novel_id = _ingest_sample_novel()
    _patch_bible_for_sample(monkeypatch)
    _patch_pipeline_for_smoke(monkeypatch)

    result = compose_service.orchestrate_full_pipeline(novel_id)

    # YAML 通过校验(含 fidelity 字段)
    vr = validate_screenplay_yaml(result.yaml_text)
    assert vr.valid, [(i.layer, i.path, i.message) for i in vr.errors()]

    # 每个 scene 都有 fidelity 字段
    parsed = vr.parsed
    assert parsed is not None
    for scene in parsed["scenes"]:
        assert "fidelity" in scene, f"scene {scene['id']} 缺 fidelity"
        fid = scene["fidelity"]
        assert fid["level"] in ("high", "medium", "low")
        assert 0.0 <= fid.get("score", 0.0) <= 1.0
        # 至少有 dimensions(4 维)
        assert "dimensions" in fid
        assert len(fid["dimensions"]) == 4
        dim_names = {d["name"] for d in fid["dimensions"]}
        assert dim_names == {
            "dialogue_coverage", "character_alignment",
            "element_density", "decision_completeness",
        }


def test_smoke_progress_callback_event_sequence(temp_db, monkeypatch):
    """progress_callback 接到的事件序列正确。

    期望:pipeline_start → chapter_done × 3 → assembling → pipeline_done
    """
    novel_id = _ingest_sample_novel()
    _patch_bible_for_sample(monkeypatch)
    _patch_pipeline_for_smoke(monkeypatch)

    events: list[dict] = []
    def collect(event: dict) -> None:
        events.append(event)

    result = compose_service.orchestrate_full_pipeline(
        novel_id, progress_callback=collect,
    )

    assert result.failed_chapters == []
    stages = [e["stage"] for e in events]

    # 起点
    assert stages[0] == "pipeline_start"
    assert events[0]["total_chapters"] == 3

    # 中间:3 次 chapter_done
    chapter_done_events = [e for e in events if e["stage"] == "chapter_done"]
    assert len(chapter_done_events) == 3
    assert sorted(e["chapter_number"] for e in chapter_done_events) == [1, 2, 3]

    # 倒数第二:assembling
    assert stages[-2] == "assembling"
    assert events[-2]["scene_count"] == 3

    # 终点:pipeline_done
    assert stages[-1] == "pipeline_done"
    assert events[-1]["screenplay_id"] == result.screenplay_id
    assert events[-1]["scene_count"] == 3
    assert events[-1]["warnings_count"] == 0
    assert events[-1]["failed_chapters_count"] == 0
