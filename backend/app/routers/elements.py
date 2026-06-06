"""元素抽取 API — PR#7。

Endpoint(无状态):
  POST /scenes/extract-elements

body 直接接收 scene_text + characters,LLM 抽取后返 elements 数组。
不持久化 — PR#10 整合主流程时会持久化。

为什么无状态:
  - PR#6 的 split 也没持久化(只返 SplitResult)
  - 让前端 / CLI 可以独立调"我有一段文本,帮我转剧本元素"
  - PR#10 主流程串联时,内部直接调 service 不走 HTTP
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.services.pipeline.element_extractor import (
    CharacterRef,
    ElementExtractError,
    SceneTextInput,
    extract_elements,
)

router = APIRouter(tags=["elements"])


# ============================================================
# Pydantic 请求 / 响应模型
# ============================================================


class CharacterRefIn(BaseModel):
    id: str = Field(..., description="char_NNN 格式")
    name: str
    aka: list[str] = Field(default_factory=list)


class SceneHeadingIn(BaseModel):
    int_ext: str = Field(..., description="INT | EXT | INT/EXT")
    location_name: str
    time_of_day: str = Field(..., description="日 | 夜 | 黄昏 | ...")


class ExtractElementsRequest(BaseModel):
    scene_summary: str
    scene_heading: SceneHeadingIn
    scene_text: str
    characters_in_scene: list[CharacterRefIn]


class ElementOut(BaseModel):
    type: str
    text: str
    character_name: str | None = None
    parenthetical: str | None = None
    is_inner_monologue: bool = False


class ExtractElementsResponse(BaseModel):
    element_count: int
    count_by_type: dict
    elements: list[ElementOut]
    llm_usage: dict


# ============================================================
# Endpoint
# ============================================================


@router.post(
    "/scenes/extract-elements",
    response_model=ExtractElementsResponse,
)
def api_extract_elements(req: ExtractElementsRequest) -> dict:
    """无状态:接收 scene 原文 + 角色,返抽取出的元素列表。"""
    if not req.characters_in_scene:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "NO_CHARACTERS", "message": "characters_in_scene 不能为空"},
        )

    scene_input = SceneTextInput(
        scene_summary=req.scene_summary,
        scene_heading=req.scene_heading.model_dump(),
        scene_text=req.scene_text,
        characters_in_scene=[
            CharacterRef(id=c.id, name=c.name, aka=c.aka)
            for c in req.characters_in_scene
        ],
    )

    try:
        result = extract_elements(scene_input)
    except ElementExtractError as e:
        msg = str(e)
        # 空文本是用户错误,LLM 失败是上游问题
        if "原文为空" in msg:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"code": "EMPTY_SCENE", "message": msg},
            )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": "LLM_EXTRACT_FAILED", "message": msg},
        )

    return {
        "element_count": len(result.elements),
        "count_by_type": result.count_by_type(),
        "elements": [
            {
                "type": el.type,
                "text": el.text,
                "character_name": el.character_name,
                "parenthetical": el.parenthetical,
                "is_inner_monologue": el.is_inner_monologue,
            }
            for el in result.elements
        ],
        "llm_usage": result.llm_usage,
    }
