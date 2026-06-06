"""对白归属精修 Agent 测试 — PR#8。

测试矩阵:
  1. happy path:LLM 给 2 条修正 → elements 对应字段被覆盖
  2. 空 draft_elements → 直接返空,不调 LLM
  3. 全是 action / parenthetical(无 dialogue / voiceover)→ 直接返,不调 LLM
  4. 空 scene_text → 不调 LLM(无上下文无法做归属)
  5. LLM 输出 character_name 是别名 → 自动映射 canonical name
  6. LLM 输出 character_name 不在 characters_in_scene → 跳过(防编造)
  7. LLM index 越界 → 跳过
  8. LLM index 重复 → 取第一个,后续忽略
  9. LLM 指向 action 类型元素 → 跳过(保护非对白类型)
 10. confidence 不在枚举 → 默认 medium
 11. confidence / reason 字段缺失 → 默认值兜底
 12. LLM 返了 attributions 但全部非法 → 返空 attributions,elements 不变
 13. LLM 调用失败 → DialogueAttributionError
 14. LLM 输出无 attributions 字段 → DialogueAttributionError
 15. 入参 draft_elements 不被修改(深拷贝验证)
 16. RefineResult.changed_count() 统计正确
 17. endpoint happy path
 18. endpoint 空 characters → 400
 19. endpoint LLM 失败 → 502
 20. 修正只动 dialogue / voiceover 的 character_name,不动 text / parenthetical
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.services.pipeline.dialogue_attributor import (
    DialogueAttributionError,
    refine_attribution,
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


def _make_characters() -> list[CharacterRef]:
    return [
        CharacterRef(id="char_001", name="霍尔顿", aka=["考菲尔德", "我"]),
        CharacterRef(id="char_002", name="斯特拉雷塔", aka=["室友"]),
    ]


def _make_draft_elements() -> list[ScreenplayElement]:
    """场景:霍尔顿和斯特拉雷塔的对话。"""
    return [
        ScreenplayElement(type="action", text="斯特拉雷塔抬起头。"),
        # PR#7 留空 character_name 的零标注对白
        ScreenplayElement(type="dialogue", text="你要走?", character_name=None),
        ScreenplayElement(type="dialogue", text="嗯。", character_name=None),
        ScreenplayElement(type="action", text="霍尔顿合上箱子。"),
    ]


def _mock_llm_returns(monkeypatch, response: dict, usage: dict | None = None):
    usage = usage or {"input_tokens": 200, "output_tokens": 100}

    def fake(*args, **kwargs):
        return response, usage

    monkeypatch.setattr(
        "app.services.pipeline.dialogue_attributor.call_json", fake,
    )


SCENE_TEXT = (
    "斯特拉雷塔抬起头,问:'你要走?'霍尔顿合上箱子,答:'嗯。'"
)


# ============================================================
# refine_attribution — 正常路径
# ============================================================


def test_happy_path_two_attributions_applied(monkeypatch):
    """LLM 给 2 条修正,elements 的 character_name 被覆盖"""
    _mock_llm_returns(
        monkeypatch,
        {
            "attributions": [
                {
                    "index": 1,
                    "character_name": "斯特拉雷塔",
                    "confidence": "high",
                    "reason": "上文有'斯特拉雷塔抬起头',接下来引号是他说",
                },
                {
                    "index": 2,
                    "character_name": "霍尔顿",
                    "confidence": "high",
                    "reason": "对话轮转",
                },
            ]
        },
    )
    result = refine_attribution(SCENE_TEXT, _make_characters(), _make_draft_elements())
    # elements 数量不变
    assert len(result.elements) == 4
    # dialogue 1 / 2 的 character_name 被填上
    assert result.elements[1].character_name == "斯特拉雷塔"
    assert result.elements[2].character_name == "霍尔顿"
    # action 不变
    assert result.elements[0].type == "action"
    assert result.elements[0].character_name is None
    # changed_count
    assert result.changed_count() == 2
    assert len(result.attributions) == 2
    assert result.attributions[0].confidence == "high"


def test_aka_resolved_to_canonical_name(monkeypatch):
    """LLM 用别名 '考菲尔德' → 自动映射 '霍尔顿'"""
    _mock_llm_returns(
        monkeypatch,
        {
            "attributions": [
                {
                    "index": 2,
                    "character_name": "考菲尔德",
                    "confidence": "medium",
                    "reason": "...",
                }
            ]
        },
    )
    result = refine_attribution(SCENE_TEXT, _make_characters(), _make_draft_elements())
    assert result.elements[2].character_name == "霍尔顿"   # canonical


def test_only_changes_dialogue_voiceover_not_action(monkeypatch):
    """修正只动 dialogue / voiceover 的 character_name,不动 text / parenthetical"""
    draft = _make_draft_elements()
    draft[1].parenthetical = "(声音发抖)"   # 给 dialogue 加 parenthetical
    original_text = draft[1].text

    _mock_llm_returns(
        monkeypatch,
        {
            "attributions": [
                {"index": 1, "character_name": "斯特拉雷塔", "confidence": "high", "reason": "x"}
            ]
        },
    )
    result = refine_attribution(SCENE_TEXT, _make_characters(), draft)
    # character_name 改了
    assert result.elements[1].character_name == "斯特拉雷塔"
    # text 不变
    assert result.elements[1].text == original_text
    # parenthetical 不变
    assert result.elements[1].parenthetical == "(声音发抖)"


def test_input_draft_elements_not_mutated(monkeypatch):
    """深拷贝校验:入参 draft_elements 不被改"""
    draft = _make_draft_elements()
    original_names = [el.character_name for el in draft]

    _mock_llm_returns(
        monkeypatch,
        {
            "attributions": [
                {"index": 1, "character_name": "斯特拉雷塔", "confidence": "high", "reason": "x"}
            ]
        },
    )
    refine_attribution(SCENE_TEXT, _make_characters(), draft)
    # 入参没被改
    after_names = [el.character_name for el in draft]
    assert after_names == original_names


# ============================================================
# 短路路径(不调 LLM)
# ============================================================


def test_empty_draft_elements_returns_empty_without_llm(monkeypatch):
    """draft_elements 空 → 直接返,不调 LLM"""
    called = {"v": False}

    def fake(*args, **kwargs):
        called["v"] = True
        return {"attributions": []}, {"input_tokens": 0, "output_tokens": 0}

    monkeypatch.setattr(
        "app.services.pipeline.dialogue_attributor.call_json", fake,
    )

    result = refine_attribution(SCENE_TEXT, _make_characters(), [])
    assert result.elements == []
    assert result.changed_count() == 0
    assert called["v"] is False   # LLM 没被调


def test_no_dialogue_voiceover_skips_llm(monkeypatch):
    """全是 action / parenthetical → 不调 LLM"""
    called = {"v": False}

    def fake(*args, **kwargs):
        called["v"] = True
        return {"attributions": []}, {}

    monkeypatch.setattr(
        "app.services.pipeline.dialogue_attributor.call_json", fake,
    )

    only_actions = [
        ScreenplayElement(type="action", text="走过去。"),
        ScreenplayElement(type="parenthetical", text="(灯灭)"),
    ]
    result = refine_attribution(SCENE_TEXT, _make_characters(), only_actions)
    assert len(result.elements) == 2
    assert called["v"] is False


def test_empty_scene_text_skips_llm(monkeypatch):
    """无场景原文 → 没上下文无法做归属,直接返"""
    called = {"v": False}

    def fake(*args, **kwargs):
        called["v"] = True
        return {"attributions": []}, {}

    monkeypatch.setattr(
        "app.services.pipeline.dialogue_attributor.call_json", fake,
    )

    result = refine_attribution("   ", _make_characters(), _make_draft_elements())
    assert len(result.elements) == 4
    assert called["v"] is False


# ============================================================
# 校验 + 兜底
# ============================================================


def test_hallucinated_character_name_dropped(monkeypatch):
    """LLM 编造的角色名(不在 characters_in_scene)→ 跳过该 attribution"""
    _mock_llm_returns(
        monkeypatch,
        {
            "attributions": [
                {"index": 1, "character_name": "幽灵人物", "confidence": "high", "reason": "x"},
                {"index": 2, "character_name": "霍尔顿", "confidence": "high", "reason": "y"},
            ]
        },
    )
    result = refine_attribution(SCENE_TEXT, _make_characters(), _make_draft_elements())
    # 幽灵的修正被跳过 → 只 1 条生效
    assert result.changed_count() == 1
    assert result.elements[1].character_name is None   # index 1 没被改
    assert result.elements[2].character_name == "霍尔顿"   # index 2 改了


def test_out_of_range_index_dropped(monkeypatch):
    """index 越界 → 跳过"""
    _mock_llm_returns(
        monkeypatch,
        {
            "attributions": [
                {"index": 99, "character_name": "霍尔顿", "confidence": "high", "reason": "x"},
                {"index": 1, "character_name": "斯特拉雷塔", "confidence": "high", "reason": "y"},
            ]
        },
    )
    result = refine_attribution(SCENE_TEXT, _make_characters(), _make_draft_elements())
    assert result.changed_count() == 1
    assert result.attributions[0].element_index == 1


def test_duplicate_index_uses_first(monkeypatch):
    """同 index 多次出现 → 取第一个,后续跳过"""
    _mock_llm_returns(
        monkeypatch,
        {
            "attributions": [
                {"index": 1, "character_name": "霍尔顿", "confidence": "high", "reason": "first"},
                {"index": 1, "character_name": "斯特拉雷塔", "confidence": "high", "reason": "dup"},
            ]
        },
    )
    result = refine_attribution(SCENE_TEXT, _make_characters(), _make_draft_elements())
    assert result.changed_count() == 1
    assert result.elements[1].character_name == "霍尔顿"   # 第一个胜出


def test_attribution_pointing_to_action_dropped(monkeypatch):
    """LLM 指向 action 类型(index 0)→ 跳过"""
    _mock_llm_returns(
        monkeypatch,
        {
            "attributions": [
                {"index": 0, "character_name": "霍尔顿", "confidence": "high", "reason": "x"},
                {"index": 1, "character_name": "斯特拉雷塔", "confidence": "high", "reason": "y"},
            ]
        },
    )
    result = refine_attribution(SCENE_TEXT, _make_characters(), _make_draft_elements())
    # action 元素的 character_name 仍为 None(没改)
    assert result.elements[0].character_name is None
    # 只 dialogue 修正生效
    assert result.changed_count() == 1


def test_invalid_confidence_defaults_to_medium(monkeypatch):
    """confidence 不在枚举 → 默认 medium"""
    _mock_llm_returns(
        monkeypatch,
        {
            "attributions": [
                {"index": 1, "character_name": "斯特拉雷塔", "confidence": "确定", "reason": "x"},
            ]
        },
    )
    result = refine_attribution(SCENE_TEXT, _make_characters(), _make_draft_elements())
    assert result.attributions[0].confidence == "medium"


def test_missing_confidence_reason_uses_defaults(monkeypatch):
    """confidence / reason 缺失 → 默认值兜底"""
    _mock_llm_returns(
        monkeypatch,
        {
            "attributions": [
                {"index": 1, "character_name": "斯特拉雷塔"},   # 缺 confidence + reason
            ]
        },
    )
    result = refine_attribution(SCENE_TEXT, _make_characters(), _make_draft_elements())
    assert result.changed_count() == 1
    assert result.attributions[0].confidence == "medium"
    assert result.attributions[0].reason == ""


def test_all_attributions_invalid_returns_unchanged(monkeypatch):
    """所有 attributions 都非法 → elements 原样返,attributions 空"""
    _mock_llm_returns(
        monkeypatch,
        {
            "attributions": [
                {"index": 99, "character_name": "x", "confidence": "high", "reason": "y"},
                {"index": 0, "character_name": "幽灵", "confidence": "high", "reason": "z"},
            ]
        },
    )
    result = refine_attribution(SCENE_TEXT, _make_characters(), _make_draft_elements())
    assert result.changed_count() == 0
    # elements 不变
    assert result.elements[1].character_name is None
    assert result.elements[2].character_name is None


# ============================================================
# 错误路径
# ============================================================


def test_llm_failure_raises(monkeypatch):
    """LLM 调用失败 → DialogueAttributionError"""
    from app.services.llm_client import LlmCallFailed

    def fake(*args, **kwargs):
        raise LlmCallFailed("503")

    monkeypatch.setattr(
        "app.services.pipeline.dialogue_attributor.call_json", fake,
    )
    with pytest.raises(DialogueAttributionError):
        refine_attribution(SCENE_TEXT, _make_characters(), _make_draft_elements())


def test_missing_attributions_field_raises(monkeypatch):
    """LLM 返了 dict 但没 attributions 字段 → 报错"""
    _mock_llm_returns(monkeypatch, {"other_field": []})
    with pytest.raises(DialogueAttributionError):
        refine_attribution(SCENE_TEXT, _make_characters(), _make_draft_elements())


# ============================================================
# endpoint
# ============================================================


def test_endpoint_happy_path(client, monkeypatch):
    """POST /scenes/refine-attribution"""
    _mock_llm_returns(
        monkeypatch,
        {
            "attributions": [
                {"index": 1, "character_name": "斯特拉雷塔", "confidence": "high", "reason": "x"},
                {"index": 2, "character_name": "霍尔顿", "confidence": "high", "reason": "y"},
            ]
        },
    )
    payload = {
        "scene_text": SCENE_TEXT,
        "characters_in_scene": [
            {"id": "char_001", "name": "霍尔顿", "aka": ["考菲尔德"]},
            {"id": "char_002", "name": "斯特拉雷塔", "aka": []},
        ],
        "draft_elements": [
            {"type": "action", "text": "斯特拉雷塔抬起头。"},
            {"type": "dialogue", "text": "你要走?"},
            {"type": "dialogue", "text": "嗯。"},
            {"type": "action", "text": "霍尔顿合上箱子。"},
        ],
    }
    r = client.post("/scenes/refine-attribution", json=payload)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["changed_count"] == 2
    assert body["elements"][1]["character_name"] == "斯特拉雷塔"
    assert body["elements"][2]["character_name"] == "霍尔顿"
    assert len(body["attributions"]) == 2


def test_endpoint_empty_characters_returns_400(client):
    payload = {
        "scene_text": "x",
        "characters_in_scene": [],
        "draft_elements": [{"type": "dialogue", "text": "..."}],
    }
    r = client.post("/scenes/refine-attribution", json=payload)
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "NO_CHARACTERS"


def test_endpoint_llm_failure_returns_502(client, monkeypatch):
    from app.services.llm_client import LlmCallFailed

    def fake(*args, **kwargs):
        raise LlmCallFailed("503")

    monkeypatch.setattr(
        "app.services.pipeline.dialogue_attributor.call_json", fake,
    )
    payload = {
        "scene_text": SCENE_TEXT,
        "characters_in_scene": [{"id": "char_001", "name": "A"}],
        "draft_elements": [{"type": "dialogue", "text": "你好"}],
    }
    r = client.post("/scenes/refine-attribution", json=payload)
    assert r.status_code == 502
    assert r.json()["detail"]["code"] == "LLM_ATTRIBUTION_FAILED"
