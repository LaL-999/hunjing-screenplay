"""元素抽取 Agent 测试 — PR#7。

测试矩阵:
  1. 正常抽取:LLM 返 4 类元素 → 全部 ScreenplayElement 解析正确
  2. action / parenthetical 不要 character_name(LLM 给了也忽略)
  3. dialogue 缺 character_name → 跳过
  4. dialogue 用 aka(别名)→ 自动映射成 name
  5. dialogue character_name 完全不存在 → 跳过
  6. voiceover is_inner_monologue 字段被保留
  7. type 不在枚举(transition / flashback)→ 跳过
  8. text 超长 → 截断到 max_len
  9. 空 scene_text → ElementExtractError
 10. 全部元素非法 → ElementExtractError
 11. LLM 调用失败 → ElementExtractError 包装
 12. 输出无 elements 字段 → ElementExtractError
 13. count_by_type 统计正确
 14. build_scene_text helper 按 paragraph_range 拼接
 15. endpoint happy path
 16. endpoint 空 characters → 400
 17. endpoint 空 scene_text → 400
 18. endpoint LLM 失败 → 502
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.services.pipeline.element_extractor import (
    CharacterRef,
    ElementExtractError,
    SceneTextInput,
    build_scene_text,
    extract_elements,
)


# ============================================================
# fixtures
# ============================================================


@pytest.fixture
def client() -> TestClient:
    from app.main import app
    return TestClient(app)


def _make_scene_input(scene_text: str = "霍尔顿走向门口。") -> SceneTextInput:
    return SceneTextInput(
        scene_summary="霍尔顿告别潘西",
        scene_heading={
            "int_ext": "INT",
            "location_name": "宿舍",
            "time_of_day": "夜",
        },
        scene_text=scene_text,
        characters_in_scene=[
            CharacterRef(id="char_001", name="霍尔顿", aka=["考菲尔德", "我"]),
            CharacterRef(id="char_002", name="斯特拉雷塔"),
        ],
    )


def _mock_llm_returns(monkeypatch, response: dict, usage: dict | None = None):
    usage = usage or {"input_tokens": 200, "output_tokens": 100}

    def fake(*args, **kwargs):
        return response, usage

    monkeypatch.setattr(
        "app.services.pipeline.element_extractor.call_json", fake,
    )


# ============================================================
# extract_elements — 正常路径
# ============================================================


def test_extract_four_element_types(monkeypatch):
    """正常抽取 4 类元素都能解析"""
    _mock_llm_returns(
        monkeypatch,
        {
            "elements": [
                {"type": "action", "text": "霍尔顿走向门口。"},
                {
                    "type": "dialogue",
                    "character_name": "霍尔顿",
                    "parenthetical": "(疲惫)",
                    "text": "我走了。",
                },
                {"type": "parenthetical", "text": "(雨声更大)"},
                {
                    "type": "voiceover",
                    "character_name": "霍尔顿",
                    "text": "我从来没想过会就这样走。",
                    "is_inner_monologue": True,
                },
            ]
        },
    )
    result = extract_elements(_make_scene_input())
    assert len(result.elements) == 4
    types = [el.type for el in result.elements]
    assert types == ["action", "dialogue", "parenthetical", "voiceover"]
    # dialogue 的 parenthetical 保留
    assert result.elements[1].parenthetical == "(疲惫)"
    # voiceover 的 is_inner_monologue 保留
    assert result.elements[3].is_inner_monologue is True


def test_action_parenthetical_ignore_character_name(monkeypatch):
    """LLM 给 action/parenthetical 加 character_name 应忽略"""
    _mock_llm_returns(
        monkeypatch,
        {
            "elements": [
                {"type": "action", "text": "走过去。", "character_name": "霍尔顿"},
                {"type": "parenthetical", "text": "(灯灭了)", "character_name": "霍尔顿"},
            ]
        },
    )
    result = extract_elements(_make_scene_input())
    assert len(result.elements) == 2
    # action / parenthetical 的 character_name 应为 None
    assert result.elements[0].character_name is None
    assert result.elements[1].character_name is None


# ============================================================
# 角色名归属 + aka 映射
# ============================================================


def test_dialogue_missing_character_name_skipped(monkeypatch):
    """dialogue 没 character_name → 跳过"""
    _mock_llm_returns(
        monkeypatch,
        {
            "elements": [
                {"type": "dialogue", "text": "你好。"},   # 缺 character_name
                {"type": "dialogue", "character_name": "霍尔顿", "text": "嗨。"},
            ]
        },
    )
    result = extract_elements(_make_scene_input())
    assert len(result.elements) == 1
    assert result.elements[0].text == "嗨。"


def test_dialogue_with_aka_mapped_to_canonical_name(monkeypatch):
    """LLM 用 aka 引用角色 → 自动映射成 name"""
    _mock_llm_returns(
        monkeypatch,
        {
            "elements": [
                # 用别名"考菲尔德"
                {"type": "dialogue", "character_name": "考菲尔德", "text": "嗨。"},
                # 用别名"我"
                {"type": "voiceover", "character_name": "我", "text": "我累了。"},
            ]
        },
    )
    result = extract_elements(_make_scene_input())
    assert len(result.elements) == 2
    # 都应映射到 canonical name "霍尔顿"
    assert result.elements[0].character_name == "霍尔顿"
    assert result.elements[1].character_name == "霍尔顿"


def test_dialogue_unknown_character_skipped(monkeypatch):
    """LLM 编造角色名(不在 characters_in_scene)→ 跳过"""
    _mock_llm_returns(
        monkeypatch,
        {
            "elements": [
                {"type": "dialogue", "character_name": "幽灵人物", "text": "..."},
                {"type": "dialogue", "character_name": "霍尔顿", "text": "嗨。"},
            ]
        },
    )
    result = extract_elements(_make_scene_input())
    assert len(result.elements) == 1
    assert result.elements[0].character_name == "霍尔顿"


def test_voiceover_inner_monologue_default_false(monkeypatch):
    """voiceover 没标 is_inner_monologue → 默认 False(全知旁白)"""
    _mock_llm_returns(
        monkeypatch,
        {
            "elements": [
                {"type": "voiceover", "character_name": "霍尔顿", "text": "时间过去。"},
            ]
        },
    )
    result = extract_elements(_make_scene_input())
    assert result.elements[0].is_inner_monologue is False


# ============================================================
# type 校验 + 长度截断
# ============================================================


def test_unknown_type_skipped(monkeypatch):
    """LLM 输出 transition / flashback 等不支持的 type → 跳过"""
    _mock_llm_returns(
        monkeypatch,
        {
            "elements": [
                {"type": "transition", "text": "FADE OUT."},
                {"type": "flashback_start", "text": "三年前"},
                {"type": "action", "text": "走出门。"},
            ]
        },
    )
    result = extract_elements(_make_scene_input())
    assert len(result.elements) == 1
    assert result.elements[0].type == "action"


def test_text_truncated_when_too_long(monkeypatch):
    """text 超长 → 截断 + 末尾加省略号"""
    long_text = "动" * 2000  # 远超 _MAX_ACTION_LEN=1000
    _mock_llm_returns(
        monkeypatch,
        {"elements": [{"type": "action", "text": long_text}]},
    )
    result = extract_elements(_make_scene_input())
    assert len(result.elements) == 1
    truncated = result.elements[0].text
    assert len(truncated) == 1000   # max_len
    assert truncated.endswith("…")


def test_empty_text_skipped(monkeypatch):
    """text 为空字符串 → 跳过"""
    _mock_llm_returns(
        monkeypatch,
        {
            "elements": [
                {"type": "action", "text": "   "},   # 全空白
                {"type": "action", "text": "正常的动作。"},
            ]
        },
    )
    result = extract_elements(_make_scene_input())
    assert len(result.elements) == 1


# ============================================================
# 错误路径
# ============================================================


def test_empty_scene_text_raises():
    """scene_text 为空 → 不调 LLM 直接报错"""
    scene_input = _make_scene_input(scene_text="   ")
    with pytest.raises(ElementExtractError, match="原文为空"):
        extract_elements(scene_input)


def test_all_elements_invalid_raises(monkeypatch):
    """LLM 返了 elements 数组但全部非法 → ElementExtractError"""
    _mock_llm_returns(
        monkeypatch,
        {
            "elements": [
                {"type": "transition", "text": "x"},     # 不支持 type
                {"type": "dialogue", "text": "y"},       # 无 character_name
                {"type": "action"},                       # 无 text
            ]
        },
    )
    with pytest.raises(ElementExtractError, match="全部非法"):
        extract_elements(_make_scene_input())


def test_llm_failure_wrapped_as_extract_error(monkeypatch):
    """LLM 调用失败 → ElementExtractError 包装"""
    from app.services.llm_client import LlmCallFailed

    def fake(*args, **kwargs):
        raise LlmCallFailed("network down")

    monkeypatch.setattr(
        "app.services.pipeline.element_extractor.call_json", fake,
    )
    with pytest.raises(ElementExtractError, match="LLM 抽取失败"):
        extract_elements(_make_scene_input())


def test_missing_elements_field_raises(monkeypatch):
    """LLM 返了 dict 但没 elements → ElementExtractError"""
    _mock_llm_returns(monkeypatch, {"other_field": "..."})
    with pytest.raises(ElementExtractError, match="缺少 elements"):
        extract_elements(_make_scene_input())


# ============================================================
# count_by_type + build_scene_text helper
# ============================================================


def test_count_by_type_aggregates(monkeypatch):
    _mock_llm_returns(
        monkeypatch,
        {
            "elements": [
                {"type": "action", "text": "a"},
                {"type": "action", "text": "b"},
                {"type": "dialogue", "character_name": "霍尔顿", "text": "嗨"},
                {"type": "voiceover", "character_name": "霍尔顿", "text": "想"},
            ]
        },
    )
    result = extract_elements(_make_scene_input())
    counts = result.count_by_type()
    assert counts == {"action": 2, "dialogue": 1, "voiceover": 1}


def test_build_scene_text_concatenates_paragraphs():
    """按 paragraph_range 拼接段落,段间空行"""
    paragraphs = [
        {"index_in_chapter": 1, "text": "第一段。"},
        {"index_in_chapter": 2, "text": "第二段。"},
        {"index_in_chapter": 3, "text": "第三段。"},
        {"index_in_chapter": 4, "text": "第四段。"},
    ]
    text = build_scene_text(paragraphs, 2, 3)
    assert text == "第二段。\n\n第三段。"


def test_build_scene_text_skips_out_of_range():
    paragraphs = [
        {"index_in_chapter": 1, "text": "一"},
        {"index_in_chapter": 5, "text": "五"},
    ]
    # range [2, 4] 没有段落 → 返空字符串
    assert build_scene_text(paragraphs, 2, 4) == ""


# ============================================================
# endpoint
# ============================================================


def test_endpoint_happy_path(client, monkeypatch):
    """POST /scenes/extract-elements 完整流程"""
    _mock_llm_returns(
        monkeypatch,
        {
            "elements": [
                {"type": "action", "text": "走开门。"},
                {"type": "dialogue", "character_name": "霍尔顿", "text": "你好。"},
            ]
        },
    )
    payload = {
        "scene_summary": "告别场景",
        "scene_heading": {
            "int_ext": "INT",
            "location_name": "宿舍",
            "time_of_day": "夜",
        },
        "scene_text": "霍尔顿走过去开门。'你好,'他说。",
        "characters_in_scene": [
            {"id": "char_001", "name": "霍尔顿", "aka": ["考菲尔德"]}
        ],
    }
    r = client.post("/scenes/extract-elements", json=payload)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["element_count"] == 2
    assert body["count_by_type"]["action"] == 1
    assert body["count_by_type"]["dialogue"] == 1


def test_endpoint_empty_characters_returns_400(client):
    """characters_in_scene 为空 → 400 NO_CHARACTERS"""
    payload = {
        "scene_summary": "x",
        "scene_heading": {"int_ext": "INT", "location_name": "x", "time_of_day": "日"},
        "scene_text": "正文",
        "characters_in_scene": [],
    }
    r = client.post("/scenes/extract-elements", json=payload)
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "NO_CHARACTERS"


def test_endpoint_empty_scene_text_returns_400(client):
    """scene_text 为空 → 400 EMPTY_SCENE"""
    payload = {
        "scene_summary": "x",
        "scene_heading": {"int_ext": "INT", "location_name": "x", "time_of_day": "日"},
        "scene_text": "   ",
        "characters_in_scene": [{"id": "char_001", "name": "A"}],
    }
    r = client.post("/scenes/extract-elements", json=payload)
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "EMPTY_SCENE"


def test_endpoint_llm_failure_returns_502(client, monkeypatch):
    from app.services.llm_client import LlmCallFailed

    def fake(*args, **kwargs):
        raise LlmCallFailed("503")

    monkeypatch.setattr(
        "app.services.pipeline.element_extractor.call_json", fake,
    )
    payload = {
        "scene_summary": "x",
        "scene_heading": {"int_ext": "INT", "location_name": "x", "time_of_day": "日"},
        "scene_text": "正文",
        "characters_in_scene": [{"id": "char_001", "name": "A"}],
    }
    r = client.post("/scenes/extract-elements", json=payload)
    assert r.status_code == 502
    assert r.json()["detail"]["code"] == "LLM_EXTRACT_FAILED"
