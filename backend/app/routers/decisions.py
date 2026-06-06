"""改编决策 API — PR#9(差异化创新)。

Endpoint(无状态):
  POST /scenes/propose-adaptation-decisions

接收 scene 上下文 + elements,对内心独白返 3 备选 + 推荐。

为什么独立 endpoint:
  - 改编决策**贵**(LLM 调用),只在用户主动请求时跑
  - demo 视频里这是核心画面:"AI 给你 3 选项,你来选"
  - PR#10 主流程串联时,内部调 service 不走 HTTP
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.services.pipeline.adaptation_decision import (
    AdaptationDecisionError,
    propose_decisions,
)
from app.services.pipeline.element_extractor import (
    CharacterRef,
    ScreenplayElement,
)

router = APIRouter(tags=["decisions"])


# ============================================================
# Pydantic 模型
# ============================================================


class CharacterRefIn(BaseModel):
    id: str
    name: str
    aka: list[str] = Field(default_factory=list)


class SceneHeadingIn(BaseModel):
    int_ext: str
    location_name: str
    time_of_day: str


class ElementIn(BaseModel):
    type: str
    text: str
    character_name: str | None = None
    parenthetical: str | None = None
    is_inner_monologue: bool = False


class ProposeRequest(BaseModel):
    scene_summary: str
    scene_heading: SceneHeadingIn
    scene_text: str
    characters_in_scene: list[CharacterRefIn]
    elements: list[ElementIn]


class OptionOut(BaseModel):
    type: str
    text: str = ""
    pros: str = ""
    cons: str = ""
    rationale: str = ""


class DecisionOut(BaseModel):
    element_index: int
    original_text: str
    options: list[OptionOut]
    recommended: str


class ProposeResponse(BaseModel):
    decision_count: int
    decisions: list[DecisionOut]
    llm_usage: dict


# ============================================================
# Endpoint
# ============================================================


@router.post(
    "/scenes/propose-adaptation-decisions",
    response_model=ProposeResponse,
)
def api_propose_decisions(req: ProposeRequest) -> dict:
    """对场景中的内心独白生成 3 备选。

    Returns:
      - decision_count: 检出的内心独白条数(也是 decisions 数组长度)
      - decisions[]: 每条含 3 options(V.O./action_externalize/delete)+ recommended
    """
    if not req.elements:
        # 无元素 → 直接返空,不调 LLM
        return {"decision_count": 0, "decisions": [], "llm_usage": {"input_tokens": 0, "output_tokens": 0}}

    characters = [
        CharacterRef(id=c.id, name=c.name, aka=c.aka)
        for c in req.characters_in_scene
    ]
    elements = [
        ScreenplayElement(
            type=el.type,
            text=el.text,
            character_name=el.character_name,
            parenthetical=el.parenthetical,
            is_inner_monologue=el.is_inner_monologue,
        )
        for el in req.elements
    ]

    try:
        result = propose_decisions(
            scene_text=req.scene_text,
            scene_summary=req.scene_summary,
            scene_heading=req.scene_heading.model_dump(),
            characters_in_scene=characters,
            elements=elements,
        )
    except AdaptationDecisionError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"code": "LLM_DECISION_FAILED", "message": str(e)},
        )

    return {
        "decision_count": result.decision_count(),
        "decisions": [
            {
                "element_index": d.element_index,
                "original_text": d.original_text,
                "options": [
                    {
                        "type": o.type,
                        "text": o.text,
                        "pros": o.pros,
                        "cons": o.cons,
                        "rationale": o.rationale,
                    }
                    for o in d.options
                ],
                "recommended": d.recommended,
            }
            for d in result.decisions
        ],
        "llm_usage": result.llm_usage,
    }
