"""场景切分 API — PR#6。

Endpoint:
  POST /chapters/{chapter_id}/split  调 LLM 切分该章为场景列表
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.services import ingest_service
from app.services.pipeline.scene_splitter import (
    SceneSplitError,
    split_chapter_from_db,
)

router = APIRouter(tags=["scenes"])


class SceneOut(BaseModel):
    """Pydantic 响应 schema(给 OpenAPI 文档清晰展示)。"""

    scene_index_in_chapter: int
    heading: dict = Field(..., description="{int_ext, location_name, time_of_day}")
    summary: str
    characters_present: list[str]
    paragraph_range: tuple[int, int]
    transition_to_next: str


class SplitResponseOut(BaseModel):
    chapter_number: int
    scene_count: int
    scenes: list[SceneOut]
    llm_usage: dict


@router.post("/chapters/{chapter_id}/split", response_model=SplitResponseOut)
def api_split_chapter(chapter_id: str) -> dict:
    """调 LLM 把该章切分为场景列表。

    前置条件:
      - 该 novel 已上传 + 已有故事圣经(POST /novels/{id}/story-bible)
    """
    # 找该 chapter 属于哪个 novel
    conn = ingest_service.get_chapter_paragraphs(chapter_id)
    if conn is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "CHAPTER_NOT_FOUND", "message": "章节不存在"},
        )

    # 通过 DB 拿 novel_id(简便起见,SQL 直查)
    from app.db.connection import get_connection
    db = get_connection()
    try:
        row = db.execute(
            "SELECT novel_id FROM chapters WHERE id = ?", (chapter_id,),
        ).fetchone()
    finally:
        db.close()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "CHAPTER_NOT_FOUND", "message": "章节不存在"},
        )
    novel_id = row["novel_id"]

    try:
        result = split_chapter_from_db(novel_id, chapter_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "SPLIT_PRECONDITION", "message": str(e)},
        )
    except SceneSplitError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": "LLM_SPLIT_FAILED", "message": str(e)},
        )

    return {
        "chapter_number": result.chapter_number,
        "scene_count": len(result.scenes),
        "scenes": [
            {
                "scene_index_in_chapter": s.scene_index_in_chapter,
                "heading": {
                    "int_ext": s.heading.int_ext,
                    "location_name": s.heading.location_name,
                    "time_of_day": s.heading.time_of_day,
                },
                "summary": s.summary,
                "characters_present": s.characters_present,
                "paragraph_range": list(s.paragraph_range),
                "transition_to_next": s.transition_to_next,
            }
            for s in result.scenes
        ],
        "llm_usage": result.llm_usage,
    }
