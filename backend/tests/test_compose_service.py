"""compose_service 编排层测试 — PR#10 commit 3。

策略:真 DB(SQLite tmp_path)+ mock 4 个 LLM agent + mock bible 获取。
   - 真 DB → 验证 novel/chapter/paragraph 数据流真的走通
   - mock LLM → 不依赖网络 / API key,run 快

测试矩阵(10 case):

happy path + 开关(3):
  1. 端到端:2 章 × 2 场 / 章 → 4 scenes 全产出 + screenplay 持久化
  2. refine_dialogue=False → 不调 PR#8 + 元素来自 PR#7 原始
  3. propose_decisions=False → 不调 PR#9 + decisions 为空

重试 + 单元降级(4):
  4. scene_splitter 重试 1 次后成功 → 不进 failed_chapters
  5. scene_splitter 整章 N+1 次全失败 → 进 failed_chapters,其他章继续
  6. element_extractor 整场 N+1 次失败 → 跳过本场 + warning,其他场继续
  7. dialogue_attributor 失败 → 降级用 draft + warning,pipeline 不中断
  8. propose_decisions 失败 → 空 decisions + warning,pipeline 不中断

异常 + 选项(3):
  9. max_chapters=1 → 只跑前 1 章
 10. NOVEL_NOT_FOUND / NO_CHAPTERS / NO_SCENES_PRODUCED 三种错误码
"""
from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from app.services import compose_service
from app.services.pipeline.adaptation_decision import (
    AdaptationDecision,
    AdaptationDecisionError,
    AdaptationOption,
    DecisionResult,
)
from app.services.pipeline.dialogue_attributor import (
    Attribution,
    DialogueAttributionError,
    RefineResult,
)
from app.services.pipeline.element_extractor import (
    ElementExtractError,
    ExtractResult,
    ScreenplayElement,
)
from app.services.pipeline.scene_splitter import (
    SceneHeading,
    SceneSplitError,
    SplitResult,
    SplitScene,
)


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def temp_db(monkeypatch, tmp_path: Path):
    db_file = tmp_path / "test_compose.db"
    from app.config import settings
    monkeypatch.setattr(settings, "database_path", db_file)
    from app.db.connection import init_db
    init_db()
    yield db_file


def _insert_novel_with_chapters(
    novel_id: str = "n1",
    chapter_count: int = 2,
    paragraphs_per_chapter: int = 4,
) -> list[str]:
    """造 novel + N 章 + 每章 M 段。返 chapter_ids。"""
    from app.db.connection import get_connection
    conn = get_connection()
    chapter_ids: list[str] = []
    try:
        conn.execute(
            """INSERT INTO novels
               (id, title, source_format, source_filename,
                total_chars, total_chapters, uploaded_at)
               VALUES (?, '测试小说', 'txt', 't.txt', 1000, ?, '2026-06-06T00:00:00Z')""",
            (novel_id, chapter_count),
        )
        for ch_num in range(1, chapter_count + 1):
            ch_id = uuid.uuid4().hex
            chapter_ids.append(ch_id)
            conn.execute(
                """INSERT INTO chapters
                   (id, novel_id, number, title, paragraph_count, char_count)
                   VALUES (?, ?, ?, ?, ?, 200)""",
                (ch_id, novel_id, ch_num, f"第{ch_num}章", paragraphs_per_chapter),
            )
            for p_idx in range(1, paragraphs_per_chapter + 1):
                conn.execute(
                    """INSERT INTO paragraphs
                       (id, chapter_id, index_in_chapter, text)
                       VALUES (?, ?, ?, ?)""",
                    (uuid.uuid4().hex, ch_id, p_idx, f"第{ch_num}章第{p_idx}段内容。" * 5),
                )
        conn.commit()
    finally:
        conn.close()
    return chapter_ids


def _mock_bible() -> dict:
    """造一个最小可用 bible。"""
    return {
        "characters": [
            {"id": "char_db_1", "name": "林墨", "aka": ["阿墨"], "description": "记者"},
            {"id": "char_db_2", "name": "苏清", "aka": [], "description": "钢琴家"},
        ],
        "locations": [
            {"id": "loc_db_1", "name": "县城旧医院", "int_ext": "INT"},
        ],
    }


def _patch_bible_present(monkeypatch, bible: dict | None = None) -> None:
    """让 story_bible_service.get_bible 返预设 bible(避免真实 LLM 调用)。"""
    real_bible = bible if bible is not None else _mock_bible()
    from app.services import story_bible_service
    monkeypatch.setattr(story_bible_service, "get_bible", lambda nid: real_bible)


def _make_split_result(ch_num: int, scene_count: int = 2) -> SplitResult:
    scenes = []
    for i in range(1, scene_count + 1):
        scenes.append(SplitScene(
            scene_index_in_chapter=i,
            heading=SceneHeading(
                int_ext="INT", location_name="县城旧医院", time_of_day="夜",
            ),
            summary=f"第 {ch_num} 章第 {i} 场",
            characters_present=["林墨", "苏清"],
            paragraph_range=(i, i + 1),
            transition_to_next="CUT_TO",
        ))
    return SplitResult(chapter_number=ch_num, scenes=scenes, llm_usage={})


def _make_extract_result() -> ExtractResult:
    return ExtractResult(elements=[
        ScreenplayElement(type="action", text="林墨走进房间。"),
        ScreenplayElement(
            type="dialogue", text="苏清?",
            character_name="林墨", parenthetical="低声",
        ),
        ScreenplayElement(
            type="voiceover", text="她真的来过这里。",
            character_name="林墨", is_inner_monologue=True,
        ),
    ], llm_usage={})


def _make_refine_result(elements: list[ScreenplayElement]) -> RefineResult:
    """精修后的 elements 与原 elements 完全一致 + 1 条 attribution。"""
    return RefineResult(
        elements=list(elements),
        attributions=[Attribution(
            element_index=1, character_name="林墨", confidence="high", reason="测试",
        )],
        llm_usage={},
    )


def _make_decision_result() -> DecisionResult:
    return DecisionResult(decisions=[AdaptationDecision(
        element_index=2,
        original_text="她真的来过这里。",
        options=[
            AdaptationOption(type="voiceover", text="V.O.:她来过", pros="主观", cons="VO"),
            AdaptationOption(type="action_externalize", text="林墨抚摸墙壁", pros="可见", cons="弱"),
            AdaptationOption(type="delete", rationale="后续可隐含"),
        ],
        recommended="voiceover",
    )], llm_usage={})


def _patch_pipeline_happy(monkeypatch) -> None:
    """所有 4 agent 都返成功结果(用于 happy path)。"""
    split_call_ch: list[int] = []

    def fake_split(chapter_input):
        split_call_ch.append(chapter_input.chapter_number)
        return _make_split_result(chapter_input.chapter_number, scene_count=2)

    monkeypatch.setattr(compose_service, "split_chapter", fake_split)
    monkeypatch.setattr(
        compose_service, "extract_elements",
        lambda scene_input: _make_extract_result(),
    )
    monkeypatch.setattr(
        compose_service, "refine_attribution",
        lambda st, ch, els: _make_refine_result(els),
    )
    monkeypatch.setattr(
        compose_service, "propose_decisions",
        lambda **kwargs: _make_decision_result(),
    )
    return split_call_ch


# ============================================================
# 1. happy path + 开关(3 case)
# ============================================================


def test_happy_path_end_to_end(temp_db, monkeypatch):
    """2 章 × 2 场 = 4 scenes 全产出 + 持久化 + warnings 空。"""
    _insert_novel_with_chapters("n1", chapter_count=2, paragraphs_per_chapter=4)
    _patch_bible_present(monkeypatch)
    _patch_pipeline_happy(monkeypatch)

    result = compose_service.orchestrate_full_pipeline("n1")

    assert isinstance(result.screenplay_id, str)
    assert len(result.screenplay_id) == 32
    assert result.failed_chapters == []
    assert result.validation_errors == []
    # YAML 中有 4 个 scene(2 章 × 2 场)
    assert "scene_001" in result.yaml_text
    assert "scene_004" in result.yaml_text
    assert "scene_005" not in result.yaml_text
    assert result.stats["total_scenes"] == 4
    assert result.stats["chapters_processed"] == 2

    # 持久化:可通过 store 查回来
    from app.services import screenplay_store
    saved = screenplay_store.get_screenplay_by_id(result.screenplay_id)
    assert saved is not None
    assert saved["yaml_text"] == result.yaml_text


def test_refine_dialogue_off_skips_pr8(temp_db, monkeypatch):
    """refine_dialogue=False → 不调 PR#8。"""
    _insert_novel_with_chapters("n1", chapter_count=1, paragraphs_per_chapter=3)
    _patch_bible_present(monkeypatch)
    _patch_pipeline_happy(monkeypatch)

    refine_called: list[bool] = []
    def boom(*args, **kwargs):
        refine_called.append(True)
        raise AssertionError("不应该被调用")
    monkeypatch.setattr(compose_service, "refine_attribution", boom)

    opts = compose_service.ComposeOptions(refine_dialogue=False)
    result = compose_service.orchestrate_full_pipeline("n1", options=opts)

    assert refine_called == []
    assert result.stats["refine_calls"] == 0


def test_propose_decisions_off_skips_pr9(temp_db, monkeypatch):
    """propose_decisions=False → 不调 PR#9 + 产出 yaml 不含 adaptation_decisions。"""
    _insert_novel_with_chapters("n1", chapter_count=1, paragraphs_per_chapter=3)
    _patch_bible_present(monkeypatch)
    _patch_pipeline_happy(monkeypatch)

    dec_called: list[bool] = []
    def boom(**kwargs):
        dec_called.append(True)
        raise AssertionError("不应该被调用")
    monkeypatch.setattr(compose_service, "propose_decisions", boom)

    opts = compose_service.ComposeOptions(propose_decisions=False)
    result = compose_service.orchestrate_full_pipeline("n1", options=opts)

    assert dec_called == []
    assert result.stats["decision_calls"] == 0
    assert "adaptation_decisions" not in result.yaml_text


# ============================================================
# 2. 重试 + 单元降级(5 case)
# ============================================================


def test_scene_splitter_retry_succeeds(temp_db, monkeypatch):
    """split_chapter 第 2 次成功 → 不进 failed_chapters。"""
    _insert_novel_with_chapters("n1", chapter_count=1, paragraphs_per_chapter=3)
    _patch_bible_present(monkeypatch)

    attempts: list[int] = []
    def flaky_split(chapter_input):
        attempts.append(1)
        if len(attempts) == 1:
            raise SceneSplitError("第 1 次假失败")
        return _make_split_result(chapter_input.chapter_number, scene_count=1)

    monkeypatch.setattr(compose_service, "split_chapter", flaky_split)
    monkeypatch.setattr(
        compose_service, "extract_elements", lambda si: _make_extract_result(),
    )
    monkeypatch.setattr(
        compose_service, "refine_attribution", lambda st, ch, els: _make_refine_result(els),
    )
    monkeypatch.setattr(
        compose_service, "propose_decisions", lambda **kw: _make_decision_result(),
    )

    result = compose_service.orchestrate_full_pipeline("n1")

    assert len(attempts) == 2   # 1 fail + 1 success
    assert result.failed_chapters == []
    assert result.stats["total_scenes"] == 1


def test_scene_splitter_all_attempts_fail_chapter_skipped(temp_db, monkeypatch):
    """单章 N+1 次全失败 → 进 failed_chapters,其他章正常。"""
    _insert_novel_with_chapters("n1", chapter_count=2, paragraphs_per_chapter=3)
    _patch_bible_present(monkeypatch)

    def split_fail_ch1(chapter_input):
        if chapter_input.chapter_number == 1:
            raise SceneSplitError("ch1 总是失败")
        return _make_split_result(chapter_input.chapter_number, scene_count=2)

    monkeypatch.setattr(compose_service, "split_chapter", split_fail_ch1)
    monkeypatch.setattr(
        compose_service, "extract_elements", lambda si: _make_extract_result(),
    )
    monkeypatch.setattr(
        compose_service, "refine_attribution", lambda st, ch, els: _make_refine_result(els),
    )
    monkeypatch.setattr(
        compose_service, "propose_decisions", lambda **kw: _make_decision_result(),
    )

    opts = compose_service.ComposeOptions(retry_per_call=2)   # 共尝试 3 次
    result = compose_service.orchestrate_full_pipeline("n1", options=opts)

    assert result.failed_chapters == [1]
    assert result.stats["chapters_processed"] == 1
    # ch2 的 2 场仍然产出
    assert result.stats["total_scenes"] == 2
    # warning 记录
    chapter_warnings = [w for w in result.warnings if w["layer"] == "chapter"]
    assert any("scene_splitter 重试" in w["message"] for w in chapter_warnings)


def test_element_extractor_failure_scene_skipped(temp_db, monkeypatch):
    """element_extractor 整场失败 → 跳过本场 + warning,其他场继续。"""
    _insert_novel_with_chapters("n1", chapter_count=1, paragraphs_per_chapter=4)
    _patch_bible_present(monkeypatch)

    monkeypatch.setattr(
        compose_service, "split_chapter",
        lambda ci: _make_split_result(ci.chapter_number, scene_count=3),
    )

    extract_count: list[int] = []
    def extract_fail_scene2(scene_input):
        extract_count.append(1)
        # 只对第 2 场全部 attempt 都失败(scene_summary 含 "2")
        if "第 1 章第 2 场" in scene_input.scene_summary:
            raise ElementExtractError("第 2 场失败")
        return _make_extract_result()

    monkeypatch.setattr(compose_service, "extract_elements", extract_fail_scene2)
    monkeypatch.setattr(
        compose_service, "refine_attribution", lambda st, ch, els: _make_refine_result(els),
    )
    monkeypatch.setattr(
        compose_service, "propose_decisions", lambda **kw: _make_decision_result(),
    )

    result = compose_service.orchestrate_full_pipeline("n1")

    # 3 场,第 2 场被跳过 → 仅 2 场入 yaml
    assert result.stats["total_scenes"] == 2
    assert result.stats["scenes_skipped"] == 1
    scene_warnings = [w for w in result.warnings if w["layer"] == "scene"]
    assert any("element_extractor 重试" in w["message"] for w in scene_warnings)


def test_dialogue_attributor_failure_downgrades(temp_db, monkeypatch):
    """精修失败 → 降级用 PR#7 原始 + warning,pipeline 不中断。"""
    _insert_novel_with_chapters("n1", chapter_count=1, paragraphs_per_chapter=3)
    _patch_bible_present(monkeypatch)
    _patch_pipeline_happy(monkeypatch)

    def refine_boom(st, ch, els):
        raise DialogueAttributionError("精修失败")
    monkeypatch.setattr(compose_service, "refine_attribution", refine_boom)

    result = compose_service.orchestrate_full_pipeline("n1")

    # pipeline 完成
    assert result.failed_chapters == []
    assert result.stats["total_scenes"] >= 1
    # warning 记录
    scene_warnings = [w for w in result.warnings if w["layer"] == "scene"]
    assert any("dialogue_attributor" in w["message"] for w in scene_warnings)


def test_propose_decisions_failure_downgrades(temp_db, monkeypatch):
    """决策失败 → 空 decisions + warning,pipeline 不中断。"""
    _insert_novel_with_chapters("n1", chapter_count=1, paragraphs_per_chapter=3)
    _patch_bible_present(monkeypatch)
    _patch_pipeline_happy(monkeypatch)

    def decisions_boom(**kw):
        raise AdaptationDecisionError("决策失败")
    monkeypatch.setattr(compose_service, "propose_decisions", decisions_boom)

    result = compose_service.orchestrate_full_pipeline("n1")

    assert result.failed_chapters == []
    # yaml 不含 adaptation_decisions(全空 = composer 不写入这段)
    assert "adaptation_decisions" not in result.yaml_text
    scene_warnings = [w for w in result.warnings if w["layer"] == "scene"]
    assert any("adaptation_decision" in w["message"] for w in scene_warnings)


# ============================================================
# 3. 选项 + 异常路径(2 case)
# ============================================================


def test_max_chapters_limits_processed(temp_db, monkeypatch):
    """max_chapters=1 → 只跑前 1 章,第 2 章未触及。"""
    _insert_novel_with_chapters("n1", chapter_count=3, paragraphs_per_chapter=2)
    _patch_bible_present(monkeypatch)
    split_calls = _patch_pipeline_happy(monkeypatch)

    opts = compose_service.ComposeOptions(max_chapters=1)
    result = compose_service.orchestrate_full_pipeline("n1", options=opts)

    assert split_calls == [1]   # 只调了第 1 章
    assert result.stats["chapters_total"] == 1
    assert result.stats["chapters_processed"] == 1


def test_error_codes_for_known_failures(temp_db, monkeypatch):
    """三种 ComposePipelineError code 都能被正确抛出。"""
    # a. NOVEL_NOT_FOUND
    with pytest.raises(compose_service.ComposePipelineError) as ei:
        compose_service.orchestrate_full_pipeline("不存在的 novel")
    assert ei.value.code == "NOVEL_NOT_FOUND"

    # b. NO_CHAPTERS — novel 存在但无章节
    from app.db.connection import get_connection
    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO novels
               (id, title, source_format, source_filename,
                total_chars, total_chapters, uploaded_at)
               VALUES ('empty_n', '空小说', 'txt', 'x.txt', 0, 0, '2026-06-06T00:00:00Z')""",
        )
        conn.commit()
    finally:
        conn.close()
    with pytest.raises(compose_service.ComposePipelineError) as ei:
        compose_service.orchestrate_full_pipeline("empty_n")
    assert ei.value.code == "NO_CHAPTERS"

    # c. NO_SCENES_PRODUCED — 所有 split 都失败
    _insert_novel_with_chapters("n_all_fail", chapter_count=1, paragraphs_per_chapter=2)
    _patch_bible_present(monkeypatch)
    monkeypatch.setattr(
        compose_service, "split_chapter",
        lambda ci: (_ for _ in ()).throw(SceneSplitError("总是失败")),
    )
    with pytest.raises(compose_service.ComposePipelineError) as ei:
        compose_service.orchestrate_full_pipeline("n_all_fail")
    assert ei.value.code == "NO_SCENES_PRODUCED"
