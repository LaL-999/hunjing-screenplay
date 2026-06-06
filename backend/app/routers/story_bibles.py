"""故事圣经 API。

Endpoints:
  POST   /novels/{novel_id}/story-bible           手动导入(JSON body)
  POST   /novels/{novel_id}/story-bible/auto      LLM 自动抽取
  GET    /novels/{novel_id}/story-bible           查看圣经
"""
from __future__ import annotations

from fastapi import APIRouter, Body, HTTPException, status

from app.services import story_bible_service

router = APIRouter(tags=["story-bible"])


@router.post("/novels/{novel_id}/story-bible")
def api_import_bible(novel_id: str, payload: dict = Body(...)) -> dict:
    """手动导入 JSON 故事圣经(覆盖既有)。"""
    try:
        return story_bible_service.import_bible_from_json(novel_id, payload)
    except ValueError as e:
        msg = str(e)
        if "不存在" in msg:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "NOVEL_NOT_FOUND", "message": msg},
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "BIBLE_INVALID", "message": msg},
        )


@router.post("/novels/{novel_id}/story-bible/auto")
def api_extract_bible(novel_id: str, max_chapters: int = 3) -> dict:
    """LLM 自动从前 N 章抽取(覆盖既有)。

    Query 参数:
        max_chapters: 喂给 LLM 的章数(默认 3,题目要求 ≥ 3)
    """
    if max_chapters < 1 or max_chapters > 10:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INVALID_MAX_CHAPTERS", "message": "max_chapters 必须在 1-10"},
        )
    try:
        return story_bible_service.extract_bible_with_llm(novel_id, max_chapters)
    except ValueError as e:
        msg = str(e)
        if "不存在" in msg:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "NOVEL_NOT_FOUND", "message": msg},
            )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": "LLM_EXTRACT_FAILED", "message": msg},
        )


@router.get("/novels/{novel_id}/story-bible")
def api_get_bible(novel_id: str) -> dict:
    bible = story_bible_service.get_bible(novel_id)
    if bible is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "BIBLE_NOT_FOUND", "message": "该作品还没创建故事圣经"},
        )
    return bible
