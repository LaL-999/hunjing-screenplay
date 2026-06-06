"""场景切分 Agent 测试 — PR#6。

测试矩阵:
  1. 正常切分:LLM 返 2 场,paragraphs 正确 → SplitResult 含 2 个 SplitScene
  2. 空章节 → 返 0 场景,不报错
  3. LLM 返非法 int_ext → 兜底为 INT
  4. LLM 返非法 time_of_day → 兜底为 日
  5. LLM 返非法 transition → 兜底为 CUT_TO
  6. LLM 返 paragraph_range 越界 → 截断到合法区间
  7. LLM 返 paragraph_range 缺失或非数组 → 跳过该场
  8. LLM 全部 scenes 都非法 → SceneSplitError
  9. LLM 调用本身失败 → SceneSplitError(包装原异常)
 10. LLM 返回 dict 但无 scenes 字段 → SceneSplitError
 11. split_chapter_from_db:novel 不存在 → ValueError
 12. split_chapter_from_db:chapter 不属于该 novel → ValueError
 13. split_chapter_from_db:圣经未创建 → ValueError
 14. split_chapter_from_db happy path → 调通
"""
from __future__ import annotations

import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.services.pipeline.scene_splitter import (
    ChapterInput,
    SceneSplitError,
    SplitScene,
    split_chapter,
    split_chapter_from_db,
)


# ============================================================
# fixtures
# ============================================================


@pytest.fixture
def temp_db(monkeypatch, tmp_path: Path):
    db_file = tmp_path / "test_screenplay.db"
    from app.config import settings
    monkeypatch.setattr(settings, "database_path", db_file)
    from app.db.connection import init_db
    init_db()
    yield db_file


@pytest.fixture
def client(temp_db) -> TestClient:
    from app.main import app
    return TestClient(app)


def _make_chapter_input(num_paragraphs: int = 10) -> ChapterInput:
    return ChapterInput(
        chapter_number=1,
        chapter_title="第一章",
        paragraphs=[
            {"index": i + 1, "text": f"段落 {i+1} 的内容,描述某些情节。"}
            for i in range(num_paragraphs)
        ],
        story_bible={
            "characters": [
                {"id": "char_001", "name": "霍尔顿", "aka": ["考菲尔德"]},
            ],
            "locations": [
                {"id": "loc_001", "name": "潘西中学", "int_ext": "EXT"},
            ],
        },
    )


def _mock_llm_returns(monkeypatch, response: dict, usage: dict | None = None):
    """让 call_json 返指定 dict。"""
    usage = usage or {"input_tokens": 100, "output_tokens": 50}

    def fake(*args, **kwargs):
        return response, usage

    monkeypatch.setattr(
        "app.services.pipeline.scene_splitter.call_json", fake,
    )


# ============================================================
# 直接调 split_chapter
# ============================================================


def test_normal_split(monkeypatch):
    """正常 2 场切分"""
    _mock_llm_returns(
        monkeypatch,
        {
            "scenes": [
                {
                    "scene_index_in_chapter": 1,
                    "heading": {
                        "int_ext": "EXT",
                        "location_name": "潘西中学",
                        "time_of_day": "日",
                    },
                    "summary": "霍尔顿告别潘西",
                    "characters_present": ["霍尔顿"],
                    "paragraph_range": [1, 5],
                    "transition_to_next": "CUT_TO",
                },
                {
                    "scene_index_in_chapter": 2,
                    "heading": {
                        "int_ext": "INT",
                        "location_name": "宿舍",
                        "time_of_day": "夜",
                    },
                    "summary": "深夜收拾行李",
                    "characters_present": ["霍尔顿"],
                    "paragraph_range": [6, 10],
                    "transition_to_next": "",
                },
            ]
        },
    )
    result = split_chapter(_make_chapter_input(10))
    assert len(result.scenes) == 2
    assert result.scenes[0].heading.int_ext == "EXT"
    assert result.scenes[1].heading.time_of_day == "夜"
    assert result.scenes[0].paragraph_range == (1, 5)
    assert result.llm_usage["input_tokens"] == 100


def test_empty_chapter_returns_zero_scenes(monkeypatch):
    """空章节 — 不调 LLM,直接返 0 场景"""
    chapter = ChapterInput(
        chapter_number=1, chapter_title=None, paragraphs=[], story_bible={},
    )
    result = split_chapter(chapter)
    assert result.scenes == []


def test_invalid_int_ext_defaults_to_INT(monkeypatch):
    """LLM 返非法 int_ext(如 '室内') → 兜底 INT"""
    _mock_llm_returns(
        monkeypatch,
        {
            "scenes": [
                {
                    "heading": {
                        "int_ext": "室内",
                        "location_name": "X",
                        "time_of_day": "日",
                    },
                    "summary": "x",
                    "paragraph_range": [1, 5],
                }
            ]
        },
    )
    result = split_chapter(_make_chapter_input(10))
    assert result.scenes[0].heading.int_ext == "INT"


def test_invalid_time_of_day_defaults_to_day(monkeypatch):
    _mock_llm_returns(
        monkeypatch,
        {
            "scenes": [
                {
                    "heading": {
                        "int_ext": "INT",
                        "location_name": "X",
                        "time_of_day": "正午",   # 不在枚举里
                    },
                    "summary": "x",
                    "paragraph_range": [1, 5],
                }
            ]
        },
    )
    result = split_chapter(_make_chapter_input(10))
    assert result.scenes[0].heading.time_of_day == "日"


def test_invalid_transition_defaults_to_cut(monkeypatch):
    _mock_llm_returns(
        monkeypatch,
        {
            "scenes": [
                {
                    "heading": {
                        "int_ext": "INT", "location_name": "X", "time_of_day": "日",
                    },
                    "summary": "x",
                    "paragraph_range": [1, 5],
                    "transition_to_next": "随便瞎写",
                }
            ]
        },
    )
    result = split_chapter(_make_chapter_input(10))
    assert result.scenes[0].transition_to_next == "CUT_TO"


def test_paragraph_range_clamped_to_chapter_bounds(monkeypatch):
    """LLM 返 [1, 99] 但章节只有 10 段 → 截断到 [1, 10]"""
    _mock_llm_returns(
        monkeypatch,
        {
            "scenes": [
                {
                    "heading": {
                        "int_ext": "INT", "location_name": "X", "time_of_day": "日",
                    },
                    "summary": "x",
                    "paragraph_range": [1, 99],
                }
            ]
        },
    )
    result = split_chapter(_make_chapter_input(10))
    assert result.scenes[0].paragraph_range == (1, 10)


def test_paragraph_range_missing_skips_scene(monkeypatch):
    """缺 paragraph_range → 跳过该 scene,但合法的保留"""
    _mock_llm_returns(
        monkeypatch,
        {
            "scenes": [
                {
                    "heading": {
                        "int_ext": "INT", "location_name": "X", "time_of_day": "日",
                    },
                    "summary": "缺 range",
                    # paragraph_range missing
                },
                {
                    "heading": {
                        "int_ext": "INT", "location_name": "Y", "time_of_day": "夜",
                    },
                    "summary": "正常",
                    "paragraph_range": [1, 5],
                },
            ]
        },
    )
    result = split_chapter(_make_chapter_input(10))
    # 第一场被跳过,第二场重新编号为 1
    assert len(result.scenes) == 1
    assert result.scenes[0].scene_index_in_chapter == 1
    assert result.scenes[0].summary == "正常"


def test_all_scenes_invalid_raises_error(monkeypatch):
    """所有 scenes 都没合法 paragraph_range → SceneSplitError"""
    _mock_llm_returns(
        monkeypatch,
        {
            "scenes": [
                {"heading": {}, "summary": "x"},   # 无 range
                {"summary": "y"},                   # 无 heading 无 range
            ]
        },
    )
    with pytest.raises(SceneSplitError):
        split_chapter(_make_chapter_input(10))


def test_llm_call_failure_raises_split_error(monkeypatch):
    """LLM 调用本身失败 → SceneSplitError 包装"""
    from app.services.llm_client import LlmCallFailed

    def fake(*args, **kwargs):
        raise LlmCallFailed("network down")

    monkeypatch.setattr(
        "app.services.pipeline.scene_splitter.call_json", fake,
    )
    with pytest.raises(SceneSplitError) as exc:
        split_chapter(_make_chapter_input(10))
    assert "network down" in str(exc.value)


def test_no_scenes_field_raises_split_error(monkeypatch):
    """LLM 返了 dict 但没 scenes 字段 → SceneSplitError"""
    _mock_llm_returns(monkeypatch, {"other_field": "..."})
    with pytest.raises(SceneSplitError):
        split_chapter(_make_chapter_input(10))


# ============================================================
# split_chapter_from_db
# ============================================================


def _upload_novel_with_bible(client) -> tuple[str, str]:
    """造一本小说 + 圣经,返 (novel_id, chapter_id)。"""
    content = (
        Path(__file__).parent / "fixtures" / "novels" / "sample_chinese.txt"
    ).read_bytes()
    upload_resp = client.post(
        "/novels", files={"file": ("t.txt", io.BytesIO(content), "text/plain")},
    )
    novel_id = upload_resp.json()["novel_id"]
    chapter_id = upload_resp.json()["chapters"][0]["id"]

    bible_payload = {
        "characters": [{"name": "霍尔顿", "is_protagonist": True}],
        "locations": [{"name": "潘西中学", "int_ext": "EXT"}],
        "relationships": [],
        "events": [],
    }
    client.post(f"/novels/{novel_id}/story-bible", json=bible_payload)
    return novel_id, chapter_id


def test_split_from_db_unknown_novel_raises(client):
    with pytest.raises(ValueError, match="不存在"):
        split_chapter_from_db("nonexistent_xxx", "chapter_xxx")


def test_split_from_db_chapter_not_in_novel(client):
    novel_id, _ = _upload_novel_with_bible(client)
    with pytest.raises(ValueError, match="不属于"):
        split_chapter_from_db(novel_id, "chapter_999")


def test_split_from_db_without_bible(client, monkeypatch):
    """上传小说但没建圣经 → ValueError"""
    content = (
        Path(__file__).parent / "fixtures" / "novels" / "sample_chinese.txt"
    ).read_bytes()
    r = client.post(
        "/novels", files={"file": ("t.txt", io.BytesIO(content), "text/plain")},
    )
    novel_id = r.json()["novel_id"]
    chapter_id = r.json()["chapters"][0]["id"]

    with pytest.raises(ValueError, match="圣经"):
        split_chapter_from_db(novel_id, chapter_id)


def test_split_from_db_happy_path(client, monkeypatch):
    """完整跑通 — LLM mock 返合法切分"""
    novel_id, chapter_id = _upload_novel_with_bible(client)

    _mock_llm_returns(
        monkeypatch,
        {
            "scenes": [
                {
                    "heading": {
                        "int_ext": "EXT",
                        "location_name": "潘西中学",
                        "time_of_day": "日",
                    },
                    "summary": "霍尔顿离开潘西",
                    "characters_present": ["霍尔顿"],
                    "paragraph_range": [1, 2],
                    "transition_to_next": "FADE_OUT",
                },
            ]
        },
    )

    result = split_chapter_from_db(novel_id, chapter_id)
    assert len(result.scenes) == 1
    assert result.scenes[0].heading.location_name == "潘西中学"


# ============================================================
# endpoint
# ============================================================


def test_endpoint_split_chapter_happy_path(client, monkeypatch):
    """POST /chapters/{id}/split → 200 + scene 列表"""
    novel_id, chapter_id = _upload_novel_with_bible(client)
    _mock_llm_returns(
        monkeypatch,
        {
            "scenes": [
                {
                    "heading": {
                        "int_ext": "EXT", "location_name": "潘西中学", "time_of_day": "日",
                    },
                    "summary": "离别",
                    "characters_present": ["霍尔顿"],
                    "paragraph_range": [1, 2],
                    "transition_to_next": "CUT_TO",
                }
            ]
        },
    )

    r = client.post(f"/chapters/{chapter_id}/split")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["scene_count"] == 1
    assert body["scenes"][0]["heading"]["location_name"] == "潘西中学"
    assert body["llm_usage"]["input_tokens"] == 100


def test_endpoint_chapter_not_found(client):
    r = client.post("/chapters/nonexistent_xxx/split")
    assert r.status_code == 404


def test_endpoint_without_bible_returns_400(client):
    """章节存在但圣经未建 → 400"""
    content = (
        Path(__file__).parent / "fixtures" / "novels" / "sample_chinese.txt"
    ).read_bytes()
    r = client.post(
        "/novels", files={"file": ("t.txt", io.BytesIO(content), "text/plain")},
    )
    chapter_id = r.json()["chapters"][0]["id"]

    r2 = client.post(f"/chapters/{chapter_id}/split")
    assert r2.status_code == 400
    assert r2.json()["detail"]["code"] == "SPLIT_PRECONDITION"


def test_endpoint_llm_failure_returns_502(client, monkeypatch):
    """LLM 炸 → 502 LLM_SPLIT_FAILED"""
    novel_id, chapter_id = _upload_novel_with_bible(client)

    from app.services.llm_client import LlmCallFailed

    def fake(*args, **kwargs):
        raise LlmCallFailed("503 Service Unavailable")

    monkeypatch.setattr(
        "app.services.pipeline.scene_splitter.call_json", fake,
    )

    r = client.post(f"/chapters/{chapter_id}/split")
    assert r.status_code == 502
    assert r.json()["detail"]["code"] == "LLM_SPLIT_FAILED"
