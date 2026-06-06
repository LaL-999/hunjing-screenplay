"""对白归属精修 API — PR#8。

Endpoint(无状态):
  POST /scenes/refine-attribution

接收 scene_text + characters + draft_elements(通常来自 PR#7 的输出),
返修正后的 elements + 修正记录(供审计)。

为什么独立 endpoint:
  - 让 PR#7 的 quick 抽取仍可单独用(不强制走精修,省 token)
  - 前端在 demo 时可以演示"PR#7 → PR#8"的二段式效果
  - PR#10 主流程串联时,内部直接调 service 不走 HTTP
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.services.pipeline.dialogue_attributor import (
    DialogueAttributionError,
    refine_attribution,
)
from app.services.pipeline.element_extractor import (
    CharacterRef,
    ScreenplayElement,
)

router = APIRouter(tags=["attributions"])


# ============================================================
# Pydantic 模型
# ============================================================


class CharacterRefIn(BaseModel):
    id: str = Field(..., description="char_NNN 格式")
    name: str
    aka: list[str] = Field(default_factory=list)


class DraftElementIn(BaseModel):
    type: str
    text: str
    character_name: str | None = None
    parenthetical: str | None = None
    is_inner_monologue: bool = False


class RefineRequest(BaseModel):
    scene_text: str
    characters_in_scene: list[CharacterRefIn]
    draft_elements: list[DraftElementIn]


class AttributionOut(BaseModel):
    element_index: int
    character_name: str
    confidence: str
    reason: str


class RefinedElementOut(BaseModel):
    type: str
    text: str
    character_name: str | None = None
    parenthetical: str | None = None
    is_inner_monologue: bool = False


class RefineResponse(BaseModel):
    changed_count: int
    elements: list[RefinedElementOut]
    attributions: list[AttributionOut]
    llm_usage: dict


# ============================================================
# Endpoint
# ============================================================


@router.post(
    "/scenes/refine-attribution",
    response_model=RefineResponse,
)
def api_refine_attribution(req: RefineRequest) -> dict:
    """对已抽 elements 做对白归属精修。

    返回:
      - 修正后的 elements 数组(同输入顺序,长度一致)
      - 修正记录(attributions)— 哪个 index 改成哪个 character_name + 依据
    """
    if not req.characters_in_scene:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "NO_CHARACTERS", "message": "characters_in_scene 不能为空"},
        )

    characters = [
        CharacterRef(id=c.id, name=c.name, aka=c.aka)
        for c in req.characters_in_scene
    ]
    draft_elements = [
        ScreenplayElement(
            type=el.type,
            text=el.text,
            character_name=el.character_name,
            parenthetical=el.parenthetical,
            is_inner_monologue=el.is_inner_monologue,
        )
        for el in req.draft_elements
    ]

    try:
        result = refine_attribution(req.scene_text, characters, draft_elements)
    except DialogueAttributionError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": "LLM_ATTRIBUTION_FAILED", "message": str(e)},
        )

    return {
        "changed_count": result.changed_count(),
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
        "attributions": [
            {
                "element_index": a.element_index,
                "character_name": a.character_name,
                "confidence": a.confidence,
                "reason": a.reason,
            }
            for a in result.attributions
        ],
        "llm_usage": result.llm_usage,
    }
