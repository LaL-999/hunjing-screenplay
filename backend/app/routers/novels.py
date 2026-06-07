"""小说摄入 API。

Endpoints:
  POST   /novels                     上传 + 解析 + 落库,返摘要
  GET    /novels                     列出所有已上传作品
  GET    /novels/{novel_id}          单本详情(含章节列表,不含段落)
  GET    /chapters/{chapter_id}      单章全部段落
"""
from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, UploadFile, status

from app.config import settings
from app.parsers import ParserError, parse_novel
from app.services import ingest_service

router = APIRouter(tags=["novels"])


@router.post("/novels")
async def api_upload_novel(file: UploadFile = File(...)) -> dict:
    """上传小说文件 → 解析 → 落库。

    Returns:
        201 Created + 摘要 dict
    """
    # 文件名 / 大小校验
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "MISSING_FILENAME", "message": "缺少文件名"},
        )

    content = await file.read()
    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail={
                "code": "FILE_TOO_LARGE",
                "message": f"文件超过 {settings.max_upload_size_mb}MB 限制",
            },
        )

    # 解析
    try:
        parsed = parse_novel(content, file.filename)
    except ParserError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "PARSE_ERROR", "message": str(e)},
        )

    # 落库
    summary = ingest_service.persist_novel(parsed, file.filename)
    return summary


@router.get("/novels")
def api_list_novels() -> dict:
    return {"items": ingest_service.list_novels()}


@router.get("/novels/{novel_id}")
def api_get_novel(novel_id: str) -> dict:
    novel = ingest_service.get_novel(novel_id)
    if novel is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NOVEL_NOT_FOUND", "message": "小说不存在"},
        )
    return novel


@router.delete("/novels/{novel_id}", status_code=status.HTTP_204_NO_CONTENT)
def api_delete_novel(novel_id: str):
    """删除小说(级联清章节 / 段落 / 故事圣经 / screenplays)。"""
    deleted = ingest_service.delete_novel(novel_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "NOVEL_NOT_FOUND", "message": "小说不存在"},
        )
    return None


@router.get("/chapters/{chapter_id}")
def api_get_chapter(chapter_id: str) -> dict:
    paragraphs = ingest_service.get_chapter_paragraphs(chapter_id)
    if paragraphs is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "CHAPTER_NOT_FOUND", "message": "章节不存在"},
        )
    return {
        "chapter_id": chapter_id,
        "paragraphs": paragraphs,
    }
