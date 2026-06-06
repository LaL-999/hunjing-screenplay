"""剧本组装 API — PR#10 commit 4。

Endpoints:
  POST   /novels/{novel_id}/compose-screenplay   一键端到端编排(贵)
  GET    /novels/{novel_id}/screenplay            返该 novel 最新一次 compose 的剧本
  GET    /screenplays/{screenplay_id}             按 id 取(给历史版本对比留口子)

为什么 POST 同步而不是异步任务队列:
  - YAGNI。比赛 demo 跑短篇,LLM 链 30-60s 能跑完
  - 引入 Celery / RQ / background worker 是过度工程
  - 真的太慢时 frontend 给 loading 转圈即可
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Body, HTTPException, status
from pydantic import BaseModel, Field

from app.services import compose_service, screenplay_store
from app.services.pipeline.structure_analyzer import (
    StructureSceneInput,
    analyze_structure,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["compose"])


# ============================================================
# Pydantic 模型
# ============================================================


class ComposeRequest(BaseModel):
    """编排选项。全字段有默认值 — 客户端可传 `{}` 走全默认。"""

    refine_dialogue: bool = True
    propose_decisions: bool = True
    max_chapters: int | None = Field(default=None, ge=1, le=100)
    retry_per_call: int = Field(default=2, ge=0, le=5)


class ComposeResponse(BaseModel):
    """POST 返;不含 created_at(用 GET 二次查询拿)。"""

    screenplay_id: str
    novel_id: str
    yaml: str
    stats: dict
    warnings: list[dict]
    failed_chapters: list[int]
    validation_errors: list[dict] = []


class ScreenplayResponse(BaseModel):
    """GET 返(已持久化的剧本完整记录)。"""

    screenplay_id: str
    novel_id: str
    yaml: str
    stats: dict
    warnings: list[dict]
    failed_chapters: list[int]
    schema_version: str
    model_name: str | None = None
    created_at: str


# ============================================================
# Endpoints
# ============================================================


@router.post(
    "/novels/{novel_id}/compose-screenplay",
    response_model=ComposeResponse,
)
def api_compose_screenplay(
    novel_id: str,
    req: ComposeRequest = Body(default_factory=ComposeRequest),
) -> dict:
    """端到端编排:小说 → 多 agent → 完整剧本 YAML(持久化)。

    Errors:
      404 NOVEL_NOT_FOUND     — novel_id 不存在
      422 NO_CHAPTERS         — novel 无章节
      422 BIBLE_EMPTY         — 故事圣经为空(且自动抽取后仍为空)
      502 BIBLE_FAILED        — 故事圣经自动抽取失败(LLM 调用错)
      502 NO_SCENES_PRODUCED  — 所有章节切分失败,无可组装的场景
      500 PIPELINE_FAILED     — 未预期编排错误(查 log)
    """
    opts = compose_service.ComposeOptions(
        refine_dialogue=req.refine_dialogue,
        propose_decisions=req.propose_decisions,
        max_chapters=req.max_chapters,
        retry_per_call=req.retry_per_call,
    )

    try:
        result = compose_service.orchestrate_full_pipeline(novel_id, options=opts)
    except compose_service.ComposePipelineError as e:
        status_code = _err_code_to_status(e.code)
        raise HTTPException(
            status_code=status_code,
            detail={"code": e.code, "message": str(e)},
        )
    except Exception as e:    # noqa: BLE001
        logger.exception("compose_screenplay novel=%s 未预期错误", novel_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "PIPELINE_FAILED", "message": str(e)},
        )

    return {
        "screenplay_id": result.screenplay_id,
        "novel_id": novel_id,
        "yaml": result.yaml_text,
        "stats": result.stats,
        "warnings": result.warnings,
        "failed_chapters": result.failed_chapters,
        "validation_errors": result.validation_errors,
    }


@router.get(
    "/novels/{novel_id}/screenplay",
    response_model=ScreenplayResponse,
)
def api_get_latest_screenplay(novel_id: str) -> dict:
    """返该 novel 最新一次 compose 的剧本。从未 compose 则 404。"""
    record = screenplay_store.get_latest_screenplay(novel_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "SCREENPLAY_NOT_FOUND",
                "message": "该作品尚未生成剧本 — 先 POST /novels/{id}/compose-screenplay",
            },
        )
    return _record_to_response(record)


@router.get("/screenplays/{screenplay_id}/structure")
def api_get_screenplay_structure(screenplay_id: str) -> dict:
    """剧本结构报告(张力曲线 + 三幕分区 + 关键节点)— PR#13。

    服务端解析 YAML,程序级计算结构指标(不调 LLM)。
    """
    import yaml as yamllib

    record = screenplay_store.get_screenplay_by_id(screenplay_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "SCREENPLAY_NOT_FOUND",
                "message": f"screenplay {screenplay_id} 不存在",
            },
        )
    try:
        parsed = yamllib.safe_load(record["yaml_text"])
    except yamllib.YAMLError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "YAML_PARSE_FAILED", "message": str(e)},
        )

    scenes = parsed.get("scenes") if isinstance(parsed, dict) else None
    if not isinstance(scenes, list):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "INVALID_SCREENPLAY", "message": "YAML 无 scenes 数组"},
        )

    inputs: list[StructureSceneInput] = []
    for s in scenes:
        if not isinstance(s, dict):
            continue
        elements = s.get("elements") or []
        if not isinstance(elements, list):
            elements = []
        dialogue_chars = 0
        inner_mono = 0
        ec = 0
        text_corpus_parts: list[str] = []
        for el in elements:
            if not isinstance(el, dict):
                continue
            etype = el.get("type", "")
            if etype in ("action", "dialogue", "voiceover", "parenthetical"):
                ec += 1
            text = el.get("text") or ""
            if isinstance(text, str):
                text_corpus_parts.append(text)
                if etype in ("dialogue", "voiceover"):
                    dialogue_chars += len(text)
        # paragraph_range → paragraph_count
        src = s.get("source") or {}
        pr = src.get("paragraph_range") if isinstance(src, dict) else None
        if isinstance(pr, list) and len(pr) == 2:
            p_count = max(1, pr[1] - pr[0] + 1)
        else:
            p_count = 1

        fid = s.get("fidelity") or {}
        fid_score = fid.get("score") if isinstance(fid, dict) else None

        chars_present = s.get("characters_present") or []
        chars_present_count = (
            len(chars_present) if isinstance(chars_present, list) else 0
        )

        inputs.append(StructureSceneInput(
            scene_id=s.get("id", ""),
            number=int(s.get("number", 0)),
            element_count=ec,
            dialogue_chars=dialogue_chars,
            inner_monologue_count=inner_mono,
            characters_present_count=chars_present_count,
            text_corpus="\n".join(text_corpus_parts),
            fidelity_score=float(fid_score) if isinstance(fid_score, (int, float)) else None,
            paragraph_count=p_count,
        ))

    # 内心独白计数:扫一遍 voiceover.is_inner_monologue(YAML 里没存这个字段,
    # 我们没法判定;PR#9 schema 把内心独白做成"含 decision 关联"的标志,
    # 这里用是否有 adaptation_decision 关联做兜底)
    decision_refs: set[str] = set()
    for d in (parsed.get("adaptation_decisions") or []):
        if isinstance(d, dict) and d.get("element_id"):
            decision_refs.add(d["element_id"])

    # 给每场补上 inner_monologue_count(用 VO 数 ≈ 内心独白数估算)
    for inp, s in zip(inputs, scenes):
        if not isinstance(s, dict):
            continue
        vo_count = sum(
            1 for el in (s.get("elements") or [])
            if isinstance(el, dict) and el.get("type") == "voiceover"
        )
        inp.inner_monologue_count = vo_count

    report = analyze_structure(inputs)
    return {
        "screenplay_id": screenplay_id,
        "scene_count": len(inputs),
        **report.to_dict(),
    }


@router.get(
    "/screenplays/{screenplay_id}",
    response_model=ScreenplayResponse,
)
def api_get_screenplay_by_id(screenplay_id: str) -> dict:
    """按 screenplay_id 取一条(给历史版本对比留口子)。"""
    record = screenplay_store.get_screenplay_by_id(screenplay_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "SCREENPLAY_NOT_FOUND",
                "message": f"screenplay {screenplay_id} 不存在",
            },
        )
    return _record_to_response(record)


# ============================================================
# 辅助
# ============================================================


def _err_code_to_status(code: str) -> int:
    """ComposePipelineError code → HTTP status code。"""
    mapping = {
        "NOVEL_NOT_FOUND": status.HTTP_404_NOT_FOUND,
        "NO_CHAPTERS": status.HTTP_422_UNPROCESSABLE_ENTITY,
        "BIBLE_EMPTY": status.HTTP_422_UNPROCESSABLE_ENTITY,
        "BIBLE_FAILED": status.HTTP_502_BAD_GATEWAY,
        "NO_SCENES_PRODUCED": status.HTTP_502_BAD_GATEWAY,
        "COMPOSE_FAILED": status.HTTP_500_INTERNAL_SERVER_ERROR,
    }
    return mapping.get(code, status.HTTP_500_INTERNAL_SERVER_ERROR)


def _record_to_response(record: dict) -> dict:
    """screenplay_store 返的 dict → ScreenplayResponse 形状。

    主要做字段重命名:id → screenplay_id,yaml_text → yaml。
    """
    return {
        "screenplay_id": record["id"],
        "novel_id": record["novel_id"],
        "yaml": record["yaml_text"],
        "stats": record["stats"],
        "warnings": record["warnings"],
        "failed_chapters": record["failed_chapters"],
        "schema_version": record["schema_version"],
        "model_name": record["model_name"],
        "created_at": record["created_at"],
    }
