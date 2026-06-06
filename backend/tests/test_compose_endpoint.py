"""compose API 测试 — PR#10 commit 4。

策略:沿用 commit 3 的 compose_service 测试风格,真 DB + mock LLM。
   通过 FastAPI TestClient 测 HTTP 层,确保 mapping(error code → status)
   和字段 rename(id → screenplay_id / yaml_text → yaml)正确。

测试矩阵(8 case):

POST(5):
  1. 默认 body `{}` → 200 + screenplay_id + yaml + 持久化
  2. 全选项明确传 → 200 + 选项被尊重(refine_dialogue=False 时 stats.refine_calls=0)
  3. novel 不存在 → 404 NOVEL_NOT_FOUND
  4. novel 无章节 → 422 NO_CHAPTERS
  5. 所有 split 失败 → 502 NO_SCENES_PRODUCED

GET(3):
  6. GET /novels/{id}/screenplay 已 compose → 200 + 字段重命名正确
  7. GET /novels/{id}/screenplay 未 compose → 404 SCREENPLAY_NOT_FOUND
  8. GET /screenplays/{id} → 200 / 404
"""
from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.services import compose_service
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


# ============================================================
# fixtures
# ============================================================


@pytest.fixture
def temp_db(monkeypatch, tmp_path: Path):
    db_file = tmp_path / "test_compose_api.db"
    from app.config import settings
    monkeypatch.setattr(settings, "database_path", db_file)
    from app.db.connection import init_db
    init_db()
    yield db_file


@pytest.fixture
def client(temp_db) -> TestClient:
    from app.main import app
    return TestClient(app)


def _insert_novel_with_chapters(
    novel_id: str = "n1",
    chapter_count: int = 1,
    paragraphs_per_chapter: int = 3,
) -> None:
    from app.db.connection import get_connection
    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO novels
               (id, title, source_format, source_filename,
                total_chars, total_chapters, uploaded_at)
               VALUES (?, '测试小说', 'txt', 't.txt', 500, ?, '2026-06-06T00:00:00Z')""",
            (novel_id, chapter_count),
        )
        for ch_num in range(1, chapter_count + 1):
            ch_id = uuid.uuid4().hex
            conn.execute(
                """INSERT INTO chapters
                   (id, novel_id, number, title, paragraph_count, char_count)
                   VALUES (?, ?, ?, ?, ?, 100)""",
                (ch_id, novel_id, ch_num, f"第{ch_num}章", paragraphs_per_chapter),
            )
            for p_idx in range(1, paragraphs_per_chapter + 1):
                conn.execute(
                    """INSERT INTO paragraphs
                       (id, chapter_id, index_in_chapter, text)
                       VALUES (?, ?, ?, ?)""",
                    (uuid.uuid4().hex, ch_id, p_idx, f"第{ch_num}章第{p_idx}段。"),
                )
        conn.commit()
    finally:
        conn.close()


def _patch_bible(monkeypatch) -> None:
    """让 story_bible_service.get_bible 返预设 bible。"""
    bible = {
        "characters": [
            {"id": "char_db_1", "name": "林墨", "aka": ["阿墨"], "description": "记者"},
            {"id": "char_db_2", "name": "苏清", "aka": [], "description": "钢琴家"},
        ],
        "locations": [{"id": "loc_db_1", "name": "县城旧医院", "int_ext": "INT"}],
    }
    from app.services import story_bible_service
    monkeypatch.setattr(story_bible_service, "get_bible", lambda nid: bible)


def _patch_pipeline_happy(monkeypatch) -> None:
    """4 agent 全成功 mock。"""

    def fake_split(ci):
        return SplitResult(
            chapter_number=ci.chapter_number,
            scenes=[SplitScene(
                scene_index_in_chapter=1,
                heading=SceneHeading(
                    int_ext="INT", location_name="县城旧医院", time_of_day="夜",
                ),
                summary=f"第 {ci.chapter_number} 章第 1 场",
                characters_present=["林墨", "苏清"],
                paragraph_range=(1, 2),
                transition_to_next="CUT_TO",
            )],
            llm_usage={},
        )

    def fake_extract(si):
        return ExtractResult(elements=[
            ScreenplayElement(type="action", text="林墨进来。"),
            ScreenplayElement(
                type="voiceover", text="她还在。",
                character_name="林墨", is_inner_monologue=True,
            ),
        ], llm_usage={})

    def fake_refine(st, ch, els):
        return RefineResult(elements=list(els), attributions=[], llm_usage={})

    def fake_decisions(**kw):
        return DecisionResult(decisions=[AdaptationDecision(
            element_index=1,
            original_text="她还在。",
            options=[
                AdaptationOption(type="voiceover", text="V.O.", pros="p", cons="c"),
                AdaptationOption(type="action_externalize", text="动作", pros="p", cons="c"),
                AdaptationOption(type="delete", rationale="可删"),
            ],
            recommended="voiceover",
        )], llm_usage={})

    monkeypatch.setattr(compose_service, "split_chapter", fake_split)
    monkeypatch.setattr(compose_service, "extract_elements", fake_extract)
    monkeypatch.setattr(compose_service, "refine_attribution", fake_refine)
    monkeypatch.setattr(compose_service, "propose_decisions", fake_decisions)


# ============================================================
# 1. POST(5 case)
# ============================================================


def test_post_with_default_body(client, monkeypatch):
    """POST 传空 body `{}` → 200 + 全套字段就位 + 持久化可查回。"""
    _insert_novel_with_chapters("n1", chapter_count=2)
    _patch_bible(monkeypatch)
    _patch_pipeline_happy(monkeypatch)

    r = client.post("/novels/n1/compose-screenplay", json={})
    assert r.status_code == 200
    body = r.json()
    assert body["novel_id"] == "n1"
    assert isinstance(body["screenplay_id"], str)
    assert len(body["screenplay_id"]) == 32   # UUID hex
    assert "scene_001" in body["yaml"]         # YAML 真生成了
    assert body["validation_errors"] == []
    assert body["failed_chapters"] == []
    assert body["stats"]["total_scenes"] == 2   # 2 章 × 1 场 / 章

    # 持久化:GET by id 能查回
    r2 = client.get(f"/screenplays/{body['screenplay_id']}")
    assert r2.status_code == 200
    assert r2.json()["yaml"] == body["yaml"]


def test_post_options_respected(client, monkeypatch):
    """全选项明确传 → 选项被尊重。"""
    _insert_novel_with_chapters("n1", chapter_count=1)
    _patch_bible(monkeypatch)
    _patch_pipeline_happy(monkeypatch)

    r = client.post("/novels/n1/compose-screenplay", json={
        "refine_dialogue": False,
        "propose_decisions": False,
        "max_chapters": 1,
        "retry_per_call": 1,
    })
    assert r.status_code == 200
    body = r.json()
    # refine + decisions 都关 → 对应 call 计数为 0
    assert body["stats"]["refine_calls"] == 0
    assert body["stats"]["decision_calls"] == 0
    # yaml 不含 adaptation_decisions 段
    assert "adaptation_decisions" not in body["yaml"]


def test_post_novel_not_found_returns_404(client):
    """POST 不存在的 novel → 404 NOVEL_NOT_FOUND。"""
    r = client.post("/novels/not-exist/compose-screenplay", json={})
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "NOVEL_NOT_FOUND"


def test_post_no_chapters_returns_422(client):
    """POST novel 存在但无章节 → 422 NO_CHAPTERS。"""
    from app.db.connection import get_connection
    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO novels
               (id, title, source_format, source_filename,
                total_chars, total_chapters, uploaded_at)
               VALUES ('empty', '空小说', 'txt', 'x.txt', 0, 0, '2026-06-06T00:00:00Z')""",
        )
        conn.commit()
    finally:
        conn.close()

    r = client.post("/novels/empty/compose-screenplay", json={})
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "NO_CHAPTERS"


def test_post_all_splits_fail_returns_502(client, monkeypatch):
    """POST 所有 split 失败 → 502 NO_SCENES_PRODUCED(LLM 链路问题)。"""
    _insert_novel_with_chapters("n1", chapter_count=1)
    _patch_bible(monkeypatch)
    monkeypatch.setattr(
        compose_service, "split_chapter",
        lambda ci: (_ for _ in ()).throw(SceneSplitError("总失败")),
    )

    r = client.post("/novels/n1/compose-screenplay", json={})
    assert r.status_code == 502
    assert r.json()["detail"]["code"] == "NO_SCENES_PRODUCED"


# ============================================================
# 2. GET(3 case)
# ============================================================


def test_get_latest_after_compose(client, monkeypatch):
    """先 POST compose,再 GET 最新 → 200 + 字段 rename 正确。"""
    _insert_novel_with_chapters("n1", chapter_count=1)
    _patch_bible(monkeypatch)
    _patch_pipeline_happy(monkeypatch)

    post_r = client.post("/novels/n1/compose-screenplay", json={})
    assert post_r.status_code == 200
    sid = post_r.json()["screenplay_id"]

    get_r = client.get("/novels/n1/screenplay")
    assert get_r.status_code == 200
    body = get_r.json()
    # 字段 rename:id → screenplay_id;yaml_text → yaml
    assert body["screenplay_id"] == sid
    assert body["novel_id"] == "n1"
    assert body["yaml"] == post_r.json()["yaml"]
    assert body["schema_version"] == "1.0"
    assert body["model_name"]   # 至少非 None
    assert body["created_at"]


def test_get_latest_before_compose_returns_404(client):
    """从未 compose → 404 SCREENPLAY_NOT_FOUND。"""
    _insert_novel_with_chapters("n1", chapter_count=1)

    r = client.get("/novels/n1/screenplay")
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "SCREENPLAY_NOT_FOUND"


def test_get_by_id_returns_404_when_missing(client):
    """GET /screenplays/{id} 不存在 → 404。"""
    r = client.get("/screenplays/does-not-exist")
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "SCREENPLAY_NOT_FOUND"
