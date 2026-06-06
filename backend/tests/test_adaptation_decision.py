"""改编决策 Agent 测试 — PR#9(差异化创新核心)。

测试矩阵:
  1. happy path:1 个内心独白 → LLM 返 3 options → 全部解析正确
  2. 多个内心独白 → 每个都有独立 3 options
  3. 无内心独白(只有 action / dialogue / non-inner voiceover)→ 不调 LLM
  4. is_inner_monologue=False 的 voiceover → 不处理
  5. options 缺一种(如缺 delete)→ 整条决策跳过
  6. options 多余类型(unknown type)→ 跳过该 option
  7. options type 重复(2 个 voiceover)→ 取第一个
  8. voiceover/action 缺 text → 跳过该 option(进而可能让整条决策不齐)
  9. delete 缺 rationale → 兜底默认 rationale
 10. element_index 越界 → 跳过决策
 11. element_index 重复 → 取第一个
 12. recommended 不在枚举 → 默认 voiceover
 13. recommended 缺失 → 默认 voiceover
 14. original_text 缺失 → 兜底用 element 原 text
 15. LLM 失败 → AdaptationDecisionError
 16. LLM 无 decisions 字段 → AdaptationDecisionError
 17. 所有 decisions 都非法 → 返空 result(不报错)
 18. endpoint happy path
 19. endpoint 空 elements → 直接返空,不调 LLM
 20. endpoint LLM 失败 → 502
 21. decision_count() 统计正确
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.services.pipeline.adaptation_decision import (
    AdaptationDecisionError,
    propose_decisions,
)
from app.services.pipeline.element_extractor import (
    CharacterRef,
    ScreenplayElement,
)


# ============================================================
# fixtures
# ============================================================


@pytest.fixture
def client() -> TestClient:
    from app.main import app
    return TestClient(app)


SCENE_TEXT = (
    "林深低头打磨齿轮。门铃响。他没抬头。"
    "陌生女子推门而入,手里捧着一只怀表。"
    "林深心里咯噔一下,他认出那是父亲三十年前丢失的怀表。"
)

SCENE_SUMMARY = "陌生女子带怀表来找钟表匠林深"
SCENE_HEADING = {"int_ext": "INT", "location_name": "老城钟表铺", "time_of_day": "日"}


def _make_characters() -> list[CharacterRef]:
    return [
        CharacterRef(id="char_001", name="林深", aka=["林先生", "我"]),
        CharacterRef(id="char_002", name="陌生女子", aka=["她"]),
    ]


def _make_elements_with_monologue() -> list[ScreenplayElement]:
    """场景元素 — 含 1 个内心独白(index=3)"""
    return [
        ScreenplayElement(type="action", text="林深低头打磨齿轮。"),
        ScreenplayElement(type="action", text="陌生女子推门而入。"),
        ScreenplayElement(
            type="dialogue", text="你能修好它吗?", character_name="陌生女子",
            parenthetical="(声音发抖)",
        ),
        # index=3 内心独白(要决策的)
        ScreenplayElement(
            type="voiceover",
            text="我一眼认出那是父亲的怀表。我的手指开始发抖。",
            character_name="林深",
            is_inner_monologue=True,
        ),
        # index=4 普通旁白(非内心独白,不决策)
        ScreenplayElement(
            type="voiceover",
            text="远处的钟声敲了三下。",
            character_name="林深",
            is_inner_monologue=False,
        ),
    ]


def _make_complete_options(idx: int = 3, recommended: str = "voiceover") -> dict:
    """生成一个完整的 LLM decision(3 options 齐)。"""
    return {
        "element_index": idx,
        "original_text": "我一眼认出那是父亲的怀表。我的手指开始发抖。",
        "options": [
            {
                "type": "voiceover",
                "text": "我一眼认出那是父亲的怀表。",
                "pros": "保留主观视角,情感直接",
                "cons": "依赖 V.O.,部分导演不喜欢",
            },
            {
                "type": "action_externalize",
                "text": "林深的手指猛地一颤,齿轮跌在桌上,发出脆响。",
                "pros": "纯视觉,更剧本化",
                "cons": "丢失'认出'的明确性",
            },
            {
                "type": "delete",
                "rationale": "若紧接的对白能体现父子线,可删",
            },
        ],
        "recommended": recommended,
    }


def _mock_llm_returns(monkeypatch, response: dict, usage: dict | None = None):
    usage = usage or {"input_tokens": 300, "output_tokens": 200}

    def fake(*args, **kwargs):
        return response, usage

    monkeypatch.setattr(
        "app.services.pipeline.adaptation_decision.call_json", fake,
    )


# ============================================================
# 正常路径
# ============================================================


def test_happy_path_one_monologue_three_options(monkeypatch):
    """1 个内心独白 → 解析出 3 options"""
    _mock_llm_returns(monkeypatch, {"decisions": [_make_complete_options()]})

    result = propose_decisions(
        SCENE_TEXT, SCENE_SUMMARY, SCENE_HEADING,
        _make_characters(), _make_elements_with_monologue(),
    )

    assert result.decision_count() == 1
    dec = result.decisions[0]
    assert dec.element_index == 3
    assert len(dec.options) == 3
    # 3 类型都在
    types = {o.type for o in dec.options}
    assert types == {"voiceover", "action_externalize", "delete"}
    # recommended
    assert dec.recommended == "voiceover"


def test_voiceover_option_has_text_pros_cons(monkeypatch):
    _mock_llm_returns(monkeypatch, {"decisions": [_make_complete_options()]})
    result = propose_decisions(
        SCENE_TEXT, SCENE_SUMMARY, SCENE_HEADING,
        _make_characters(), _make_elements_with_monologue(),
    )
    vo_opt = next(o for o in result.decisions[0].options if o.type == "voiceover")
    assert "父亲的怀表" in vo_opt.text
    assert "主观视角" in vo_opt.pros
    assert "V.O." in vo_opt.cons or "导演" in vo_opt.cons


def test_action_externalize_pure_action(monkeypatch):
    _mock_llm_returns(monkeypatch, {"decisions": [_make_complete_options()]})
    result = propose_decisions(
        SCENE_TEXT, SCENE_SUMMARY, SCENE_HEADING,
        _make_characters(), _make_elements_with_monologue(),
    )
    act_opt = next(
        o for o in result.decisions[0].options if o.type == "action_externalize"
    )
    assert "手指" in act_opt.text or "齿轮" in act_opt.text
    assert act_opt.pros
    assert act_opt.cons


def test_delete_uses_rationale_not_text(monkeypatch):
    """delete 选项用 rationale,不用 text"""
    _mock_llm_returns(monkeypatch, {"decisions": [_make_complete_options()]})
    result = propose_decisions(
        SCENE_TEXT, SCENE_SUMMARY, SCENE_HEADING,
        _make_characters(), _make_elements_with_monologue(),
    )
    del_opt = next(o for o in result.decisions[0].options if o.type == "delete")
    assert del_opt.rationale != ""
    assert del_opt.text == ""   # delete 不输出 text


# ============================================================
# 短路:无内心独白则不调 LLM
# ============================================================


def test_no_monologue_skips_llm(monkeypatch):
    """没有 is_inner_monologue=True 的元素 → 不调 LLM"""
    called = {"v": False}

    def fake(*args, **kwargs):
        called["v"] = True
        return {"decisions": []}, {}

    monkeypatch.setattr(
        "app.services.pipeline.adaptation_decision.call_json", fake,
    )

    only_action = [
        ScreenplayElement(type="action", text="走开。"),
        ScreenplayElement(type="dialogue", text="嗨。", character_name="林深"),
    ]
    result = propose_decisions(
        SCENE_TEXT, SCENE_SUMMARY, SCENE_HEADING,
        _make_characters(), only_action,
    )
    assert result.decision_count() == 0
    assert called["v"] is False


def test_non_inner_voiceover_skipped(monkeypatch):
    """voiceover 但 is_inner_monologue=False(全知旁白)→ 不参与决策"""
    called = {"v": False}

    def fake(*args, **kwargs):
        called["v"] = True
        return {"decisions": []}, {}

    monkeypatch.setattr(
        "app.services.pipeline.adaptation_decision.call_json", fake,
    )

    omniscient_only = [
        ScreenplayElement(
            type="voiceover", text="远处钟响。", character_name="林深",
            is_inner_monologue=False,
        ),
    ]
    result = propose_decisions(
        SCENE_TEXT, SCENE_SUMMARY, SCENE_HEADING,
        _make_characters(), omniscient_only,
    )
    assert result.decision_count() == 0
    assert called["v"] is False


# ============================================================
# 校验 + 兜底
# ============================================================


def test_decision_missing_one_option_type_dropped(monkeypatch):
    """options 缺一种 type → 整条决策跳过(3 选项必齐)"""
    incomplete = {
        "element_index": 3,
        "options": [
            {"type": "voiceover", "text": "x", "pros": "y", "cons": "z"},
            {"type": "action_externalize", "text": "a", "pros": "b", "cons": "c"},
            # 缺 delete
        ],
        "recommended": "voiceover",
    }
    _mock_llm_returns(monkeypatch, {"decisions": [incomplete]})
    result = propose_decisions(
        SCENE_TEXT, SCENE_SUMMARY, SCENE_HEADING,
        _make_characters(), _make_elements_with_monologue(),
    )
    assert result.decision_count() == 0   # 不齐 → 跳过


def test_unknown_option_type_filtered(monkeypatch):
    """options 含 unknown type → 那个 option 跳过,但若剩 3 类型不齐 → 整条决策跳过"""
    bad_type = {
        "element_index": 3,
        "options": [
            {"type": "voiceover", "text": "x", "pros": "y", "cons": "z"},
            {"type": "action_externalize", "text": "a", "pros": "b", "cons": "c"},
            {"type": "delete", "rationale": "ok"},
            {"type": "transformation", "text": "未来类型"},   # unknown
        ],
        "recommended": "voiceover",
    }
    _mock_llm_returns(monkeypatch, {"decisions": [bad_type]})
    result = propose_decisions(
        SCENE_TEXT, SCENE_SUMMARY, SCENE_HEADING,
        _make_characters(), _make_elements_with_monologue(),
    )
    assert result.decision_count() == 1   # 合法 3 个保留,bad 被过滤,整条仍有效
    types = {o.type for o in result.decisions[0].options}
    assert types == {"voiceover", "action_externalize", "delete"}


def test_duplicate_option_type_first_wins(monkeypatch):
    """同 type option 出现 2 次 → 取第一个,后续跳过"""
    dup = {
        "element_index": 3,
        "options": [
            {"type": "voiceover", "text": "first", "pros": "a", "cons": "b"},
            {"type": "voiceover", "text": "second", "pros": "x", "cons": "y"},   # 重复
            {"type": "action_externalize", "text": "act", "pros": "x", "cons": "y"},
            {"type": "delete", "rationale": "ok"},
        ],
        "recommended": "voiceover",
    }
    _mock_llm_returns(monkeypatch, {"decisions": [dup]})
    result = propose_decisions(
        SCENE_TEXT, SCENE_SUMMARY, SCENE_HEADING,
        _make_characters(), _make_elements_with_monologue(),
    )
    assert result.decision_count() == 1
    vo_opt = next(o for o in result.decisions[0].options if o.type == "voiceover")
    assert vo_opt.text == "first"   # 第一个胜


def test_voiceover_missing_text_skipped(monkeypatch):
    """voiceover option 缺 text → 跳过 → 整条不齐 → 决策跳过"""
    missing = {
        "element_index": 3,
        "options": [
            {"type": "voiceover", "pros": "x", "cons": "y"},   # 无 text
            {"type": "action_externalize", "text": "act", "pros": "x", "cons": "y"},
            {"type": "delete", "rationale": "ok"},
        ],
        "recommended": "voiceover",
    }
    _mock_llm_returns(monkeypatch, {"decisions": [missing]})
    result = propose_decisions(
        SCENE_TEXT, SCENE_SUMMARY, SCENE_HEADING,
        _make_characters(), _make_elements_with_monologue(),
    )
    assert result.decision_count() == 0   # 不齐


def test_delete_missing_rationale_uses_default(monkeypatch):
    """delete 缺 rationale → 用默认值兜底,决策仍有效"""
    no_rationale = {
        "element_index": 3,
        "options": [
            {"type": "voiceover", "text": "x", "pros": "a", "cons": "b"},
            {"type": "action_externalize", "text": "y", "pros": "c", "cons": "d"},
            {"type": "delete"},   # 缺 rationale
        ],
        "recommended": "voiceover",
    }
    _mock_llm_returns(monkeypatch, {"decisions": [no_rationale]})
    result = propose_decisions(
        SCENE_TEXT, SCENE_SUMMARY, SCENE_HEADING,
        _make_characters(), _make_elements_with_monologue(),
    )
    assert result.decision_count() == 1
    del_opt = next(o for o in result.decisions[0].options if o.type == "delete")
    assert del_opt.rationale != ""   # 有兜底值


def test_out_of_range_index_dropped(monkeypatch):
    """element_index 越界 → 决策跳过"""
    bad = _make_complete_options(idx=99)
    _mock_llm_returns(monkeypatch, {"decisions": [bad]})
    result = propose_decisions(
        SCENE_TEXT, SCENE_SUMMARY, SCENE_HEADING,
        _make_characters(), _make_elements_with_monologue(),
    )
    assert result.decision_count() == 0


def test_invalid_recommended_defaults_to_voiceover(monkeypatch):
    """recommended 不在三选一 → 默认 voiceover"""
    dec = _make_complete_options(recommended="random_choice")
    _mock_llm_returns(monkeypatch, {"decisions": [dec]})
    result = propose_decisions(
        SCENE_TEXT, SCENE_SUMMARY, SCENE_HEADING,
        _make_characters(), _make_elements_with_monologue(),
    )
    assert result.decisions[0].recommended == "voiceover"


def test_missing_recommended_defaults_to_voiceover(monkeypatch):
    dec = _make_complete_options()
    del dec["recommended"]
    _mock_llm_returns(monkeypatch, {"decisions": [dec]})
    result = propose_decisions(
        SCENE_TEXT, SCENE_SUMMARY, SCENE_HEADING,
        _make_characters(), _make_elements_with_monologue(),
    )
    assert result.decisions[0].recommended == "voiceover"


def test_missing_original_text_falls_back_to_element_text(monkeypatch):
    """LLM 没回 original_text → 兜底用原 element.text"""
    dec = _make_complete_options()
    del dec["original_text"]
    _mock_llm_returns(monkeypatch, {"decisions": [dec]})
    result = propose_decisions(
        SCENE_TEXT, SCENE_SUMMARY, SCENE_HEADING,
        _make_characters(), _make_elements_with_monologue(),
    )
    assert "父亲的怀表" in result.decisions[0].original_text


# ============================================================
# 错误路径
# ============================================================


def test_llm_failure_raises(monkeypatch):
    from app.services.llm_client import LlmCallFailed

    def fake(*args, **kwargs):
        raise LlmCallFailed("503")

    monkeypatch.setattr(
        "app.services.pipeline.adaptation_decision.call_json", fake,
    )
    with pytest.raises(AdaptationDecisionError):
        propose_decisions(
            SCENE_TEXT, SCENE_SUMMARY, SCENE_HEADING,
            _make_characters(), _make_elements_with_monologue(),
        )


def test_missing_decisions_field_raises(monkeypatch):
    _mock_llm_returns(monkeypatch, {"unknown": []})
    with pytest.raises(AdaptationDecisionError):
        propose_decisions(
            SCENE_TEXT, SCENE_SUMMARY, SCENE_HEADING,
            _make_characters(), _make_elements_with_monologue(),
        )


def test_all_decisions_invalid_returns_empty(monkeypatch):
    """LLM 返了 decisions 但全部不齐 / 越界 → 返空 result(不报错)"""
    _mock_llm_returns(
        monkeypatch,
        {
            "decisions": [
                _make_complete_options(idx=99),   # 越界
                {"element_index": 3, "options": []},   # 空 options
            ]
        },
    )
    result = propose_decisions(
        SCENE_TEXT, SCENE_SUMMARY, SCENE_HEADING,
        _make_characters(), _make_elements_with_monologue(),
    )
    assert result.decision_count() == 0


# ============================================================
# endpoint
# ============================================================


def test_endpoint_happy_path(client, monkeypatch):
    """POST /scenes/propose-adaptation-decisions"""
    _mock_llm_returns(monkeypatch, {"decisions": [_make_complete_options()]})
    payload = {
        "scene_summary": SCENE_SUMMARY,
        "scene_heading": SCENE_HEADING,
        "scene_text": SCENE_TEXT,
        "characters_in_scene": [
            {"id": "char_001", "name": "林深", "aka": ["林先生"]},
            {"id": "char_002", "name": "陌生女子"},
        ],
        "elements": [
            {"type": "action", "text": "x"},
            {"type": "voiceover", "text": "...", "character_name": "林深",
             "is_inner_monologue": True},
        ],
    }
    # 注:elements[1] 是 index=1,但 mock LLM 返 element_index=3 → 校验跳过
    # 改 payload 让 monologue 在 index=3
    payload["elements"] = [
        {"type": "action", "text": "1"},
        {"type": "action", "text": "2"},
        {"type": "dialogue", "text": "3", "character_name": "林深"},
        {"type": "voiceover", "text": "我认出怀表。", "character_name": "林深",
         "is_inner_monologue": True},
    ]
    r = client.post("/scenes/propose-adaptation-decisions", json=payload)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["decision_count"] == 1
    assert len(body["decisions"][0]["options"]) == 3
    assert body["decisions"][0]["recommended"] == "voiceover"


def test_endpoint_empty_elements_returns_empty(client):
    """无元素 → 直接返空,不调 LLM"""
    payload = {
        "scene_summary": "x",
        "scene_heading": {"int_ext": "INT", "location_name": "x", "time_of_day": "日"},
        "scene_text": "x",
        "characters_in_scene": [{"id": "char_001", "name": "A"}],
        "elements": [],
    }
    r = client.post("/scenes/propose-adaptation-decisions", json=payload)
    assert r.status_code == 200
    assert r.json()["decision_count"] == 0


def test_endpoint_llm_failure_returns_502(client, monkeypatch):
    from app.services.llm_client import LlmCallFailed

    def fake(*args, **kwargs):
        raise LlmCallFailed("503")

    monkeypatch.setattr(
        "app.services.pipeline.adaptation_decision.call_json", fake,
    )
    payload = {
        "scene_summary": "x",
        "scene_heading": {"int_ext": "INT", "location_name": "x", "time_of_day": "日"},
        "scene_text": "x",
        "characters_in_scene": [{"id": "char_001", "name": "林深"}],
        "elements": [
            {"type": "voiceover", "text": "想", "character_name": "林深",
             "is_inner_monologue": True}
        ],
    }
    r = client.post("/scenes/propose-adaptation-decisions", json=payload)
    assert r.status_code == 502
    assert r.json()["detail"]["code"] == "LLM_DECISION_FAILED"
