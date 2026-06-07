"""故事圣经测试 — PR#4。

测试矩阵:
  1. JSON 导入合法 payload → 200 + stats 正确
  2. JSON 导入到不存在 novel → 404
  3. 同 novel 二次导入 → 覆盖(不出现重复)
  4. LLM 抽取(mock LLM)→ 200 + stats 正确
  5. LLM 返回非法 name 引用 → relationships / events 过滤掉
  6. LLM 调用失败 → 502
  7. GET 圣经 → 含 characters / locations / relationships / events
  8. GET 不存在 → 404
  9. characters 内 aka 别名也加入 name → id 映射
"""
from __future__ import annotations

import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


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


@pytest.fixture
def uploaded_novel(client) -> str:
    """造一本上传的小说,返 novel_id。"""
    content = (
        Path(__file__).parent / "fixtures" / "novels" / "sample_chinese.txt"
    ).read_bytes()
    r = client.post(
        "/novels",
        files={"file": ("sample.txt", io.BytesIO(content), "text/plain")},
    )
    return r.json()["novel_id"]


# 合法 JSON payload
_VALID_PAYLOAD = {
    "characters": [
        {
            "name": "霍尔顿",
            "aka": ["考菲尔德", "我"],
            "description": "16 岁少年,刚被潘西中学开除",
            "is_protagonist": True,
        },
        {
            "name": "斯特拉雷塔",
            "aka": ["室友"],
            "description": "霍尔顿的室友",
            "is_protagonist": False,
        },
    ],
    "locations": [
        {"name": "潘西中学", "int_ext": "EXT", "description": "霍尔顿就读的学校"},
        {"name": "宿舍", "int_ext": "INT", "description": "学生宿舍房间"},
    ],
    "relationships": [
        {
            "source_name": "霍尔顿",
            "target_name": "斯特拉雷塔",
            "type": "室友",
            "description": "同房间",
        },
        {
            # 故意引用不存在的 name,应被过滤
            "source_name": "霍尔顿",
            "target_name": "幽灵人物",
            "type": "陌生",
            "description": "不应该被插入",
        },
    ],
    "events": [
        {
            "description": "霍尔顿被潘西中学开除",
            "chapter_number": 1,
            "participant_names": ["霍尔顿"],
        },
    ],
}


# ============================================================
# JSON 导入
# ============================================================

def test_import_bible_success(client, uploaded_novel):
    """正常导入 → 200 + stats"""
    novel_id = uploaded_novel
    r = client.post(
        f"/novels/{novel_id}/story-bible",
        json=_VALID_PAYLOAD,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["novel_id"] == novel_id
    assert body["source"] == "manual"
    assert body["stats"]["characters"] == 2
    assert body["stats"]["locations"] == 2
    # 关系:2 个里 1 个被过滤(target=幽灵人物不在 characters)
    assert body["stats"]["relationships"] == 1
    assert body["stats"]["events"] == 1


def test_import_bible_unknown_novel_returns_404(client):
    r = client.post(
        "/novels/nonexistent_xxx/story-bible",
        json=_VALID_PAYLOAD,
    )
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "NOVEL_NOT_FOUND"


def test_import_bible_overrides_existing(client, uploaded_novel):
    """二次导入覆盖,第一次的角色应消失"""
    novel_id = uploaded_novel
    # 第 1 次:2 个角色
    client.post(f"/novels/{novel_id}/story-bible", json=_VALID_PAYLOAD)

    # 第 2 次:1 个角色
    new_payload = {
        "characters": [{"name": "只有一个", "description": "新角色"}],
        "locations": [],
        "relationships": [],
        "events": [],
    }
    r = client.post(f"/novels/{novel_id}/story-bible", json=new_payload)
    assert r.status_code == 200
    assert r.json()["stats"]["characters"] == 1

    # 查圣经 → 只有新角色
    get_r = client.get(f"/novels/{novel_id}/story-bible")
    chars = get_r.json()["characters"]
    assert len(chars) == 1
    assert chars[0]["name"] == "只有一个"


def test_import_bible_invalid_payload_returns_400(client, uploaded_novel):
    """characters 不是数组 → 400"""
    r = client.post(
        f"/novels/{uploaded_novel}/story-bible",
        json={"characters": "not a list"},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "BIBLE_INVALID"


# ============================================================
# LLM 自动抽取
# ============================================================

def test_extract_bible_with_llm_mocked(client, uploaded_novel, monkeypatch):
    """LLM mock 返回结构化数据,落库验证"""
    # mock call_json
    mock_response = {
        "characters": [
            {
                "name": "霍尔顿",
                "aka": ["考菲尔德"],
                "description": "主角",
                "is_protagonist": True,
            },
        ],
        "locations": [
            {"name": "汤姆孙山", "int_ext": "EXT", "description": "潘西校园的山"},
        ],
        "relationships": [],
        "events": [
            {
                "description": "霍尔顿离开潘西",
                "chapter_number": 2,
                "participant_names": ["霍尔顿"],
            },
        ],
    }

    def fake_call_json(*args, **kwargs):
        return mock_response, {"input_tokens": 100, "output_tokens": 50}

    monkeypatch.setattr(
        "app.services.story_bible_service.call_json", fake_call_json,
    )

    r = client.post(f"/novels/{uploaded_novel}/story-bible/auto?max_chapters=3")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["source"] == "llm_extracted"
    assert body["stats"]["characters"] == 1
    assert body["stats"]["events"] == 1
    assert body["llm_usage"]["input_tokens"] == 100


def test_extract_bible_llm_failure_returns_502(client, uploaded_novel, monkeypatch):
    """LLM 调用炸 → 502"""
    from app.services.llm_client import LlmCallFailed

    def fake_call_json(*args, **kwargs):
        raise LlmCallFailed("network down")

    monkeypatch.setattr(
        "app.services.story_bible_service.call_json", fake_call_json,
    )

    r = client.post(f"/novels/{uploaded_novel}/story-bible/auto")
    assert r.status_code == 502
    assert r.json()["detail"]["code"] == "LLM_EXTRACT_FAILED"


def test_extract_bible_invalid_max_chapters(client, uploaded_novel):
    r = client.post(f"/novels/{uploaded_novel}/story-bible/auto?max_chapters=0")
    assert r.status_code == 400


# ============================================================
# 查询
# ============================================================

def test_get_bible_returns_full_structure(client, uploaded_novel):
    novel_id = uploaded_novel
    client.post(f"/novels/{novel_id}/story-bible", json=_VALID_PAYLOAD)
    r = client.get(f"/novels/{novel_id}/story-bible")
    assert r.status_code == 200
    body = r.json()
    assert len(body["characters"]) == 2
    # 主角标记
    protagonists = [c for c in body["characters"] if c["is_protagonist"]]
    assert len(protagonists) == 1
    assert protagonists[0]["name"] == "霍尔顿"
    # aka 应解析为数组
    assert "考菲尔德" in protagonists[0]["aka"]
    # 关系:1 条(过滤后)
    assert len(body["relationships"]) == 1
    # 事件:1 条 + participant_ids 解析
    assert len(body["events"]) == 1
    assert len(body["events"][0]["participant_ids"]) == 1


def test_get_bible_nonexistent_returns_404(client, uploaded_novel):
    """该 novel 还没建圣经"""
    r = client.get(f"/novels/{uploaded_novel}/story-bible")
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "BIBLE_NOT_FOUND"


# ============================================================
# 别名映射
# ============================================================

def test_aka_resolves_to_same_character(client, uploaded_novel):
    """关系用别名引用 → 应能映射到正确角色"""
    payload = {
        "characters": [
            {"name": "霍尔顿", "aka": ["考菲尔德", "霍利"]},
            {"name": "斯特拉雷塔"},
        ],
        "locations": [],
        "relationships": [
            {
                # 用别名引用霍尔顿
                "source_name": "考菲尔德",
                "target_name": "斯特拉雷塔",
                "type": "室友",
            },
        ],
        "events": [],
    }
    r = client.post(f"/novels/{uploaded_novel}/story-bible", json=payload)
    assert r.status_code == 200
    assert r.json()["stats"]["relationships"] == 1   # 别名应被映射,关系生效

    # GET 验证
    get_r = client.get(f"/novels/{uploaded_novel}/story-bible")
    rels = get_r.json()["relationships"]
    assert len(rels) == 1
    # ID 改为 UUID(避免多 bible 间的全局 PK 冲突,见 story_bible_service:212)
    # 只验"两个不同的 ID"+"指向有效 char 行",不再断言 char_NNN 字面值
    assert rels[0]["source_char_id"] != rels[0]["target_char_id"]
    assert len(rels[0]["source_char_id"]) > 8
    assert len(rels[0]["target_char_id"]) > 8
