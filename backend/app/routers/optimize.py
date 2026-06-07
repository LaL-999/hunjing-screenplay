"""人机协作优化 API — PR#16。

A 入口(单场精修)+ B 入口(整本重排)共用同一个 endpoint:
  POST /screenplays/{id}/optimize
    body: { scope: 'single_scene'|'full_screenplay', target_scene_id?, focus? }
  -> 跑 LLM 引擎 → 存为新版本(parent_screenplay_id = 原 id)→ 返新 id + change_log

  GET /novels/{novel_id}/versions
  -> 列出该 novel 所有剧本版本(版本树)
"""
from __future__ import annotations

from typing import Literal

import yaml as yamllib
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.services import ingest_service, screenplay_store
from app.services.pipeline.adaptation_decision import (
    AdaptationDecision,
    AdaptationOption,
)
from app.services.pipeline.element_extractor import ScreenplayElement
from app.services.pipeline.fidelity_scorer import (
    FidelityInput,
    score_scene_fidelity,
)
from app.services.pipeline.screenplay_optimizer import (
    OptimizeRequest,
    ScreenplayOptimizeError,
    optimize_screenplay,
)
from app.services.pipeline.structure_analyzer import (
    StructureSceneInput,
    analyze_structure,
)

router = APIRouter(tags=["optimize"])


# ============================================================
# Pydantic 模型
# ============================================================


class OptimizeRequestBody(BaseModel):
    scope: Literal["single_scene", "full_screenplay"]
    target_scene_id: str | None = None
    focus: Literal["fidelity", "structure", "both"] = "both"
    # PR#16 C:作者已做的决策(decision_id → 选项 type)
    user_decisions: dict[str, str] | None = None


class ChangeLogItem(BaseModel):
    scene_id: str
    original_scene_id: str | None = None
    action: str
    summary: str
    addresses_diagnostic: str = ""
    details: str = ""


class OptimizeResponse(BaseModel):
    new_screenplay_id: str
    parent_screenplay_id: str
    origin: str
    change_log: list[ChangeLogItem]
    reasoning: str
    fallback_reason: str | None = None
    llm_usage: dict = Field(default_factory=dict)


class VersionInfo(BaseModel):
    id: str
    parent_screenplay_id: str | None = None
    origin: str
    created_at: str
    scene_count: int
    change_count: int
    reasoning_snippet: str


# ============================================================
# 主 endpoint
# ============================================================


@router.post(
    "/screenplays/{screenplay_id}/optimize",
    response_model=OptimizeResponse,
)
def api_optimize_screenplay(screenplay_id: str, body: OptimizeRequestBody) -> dict:
    """A/B 入口共用 — 跑 LLM 优化 → 存新版 → 返摘要。"""
    record = screenplay_store.get_screenplay_by_id(screenplay_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "SCREENPLAY_NOT_FOUND", "message": "剧本不存在"},
        )

    # 1. 解析当前 yaml
    try:
        current_screenplay = yamllib.safe_load(record["yaml_text"])
    except yamllib.YAMLError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "YAML_PARSE_FAILED", "message": str(e)},
        )

    if not isinstance(current_screenplay, dict):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"code": "INVALID_SCREENPLAY", "message": "yaml 解析非 dict"},
        )

    # 2. 算诊断(给 LLM 当输入参考)
    diagnostics = _build_diagnostics(current_screenplay)

    # C:把作者已做的决策塞进 diagnostics — LLM prompt 会读"author_decisions"
    if body.user_decisions:
        diagnostics["author_decisions"] = _summarize_author_decisions(
            current_screenplay,
            body.user_decisions,
        )

    # 3. 跑 LLM 优化
    try:
        result = optimize_screenplay(OptimizeRequest(
            screenplay=current_screenplay,
            scope=body.scope,
            target_scene_id=body.target_scene_id,
            focus=body.focus,
            diagnostics=diagnostics,
        ))
    except ScreenplayOptimizeError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "OPTIMIZE_INPUT_INVALID", "message": str(e)},
        )

    # 3.5 优化后闭环对齐:
    #   A 修复 - 重算 fidelity
    #   B 修复 - 清幽灵 decisions
    #   D 修复 - 对新增/拆分场补 propose_decisions
    _refresh_fidelity_in_screenplay(
        result.optimized_screenplay,
        record["novel_id"],
    )
    _purge_orphan_decisions(result.optimized_screenplay)
    _attach_decisions_for_new_scenes(
        result.optimized_screenplay,
        result.change_log,
    )

    # 4. 把新版 dict 序列化回 yaml 文本
    new_yaml_text = yamllib.safe_dump(
        result.optimized_screenplay,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
        width=120,
    )

    # 5. 算新版 stats
    scenes = result.optimized_screenplay.get("scenes") or []
    stats = {
        "total_scenes": len(scenes) if isinstance(scenes, list) else 0,
        "total_pages_estimate": _estimate_pages(scenes),
    }

    # 6. 决定 origin
    if body.scope == "single_scene":
        origin = f"single_scene_{body.target_scene_id}"
    else:
        origin = "full_screenplay"

    # 7. 存为新版本(parent 指向当前)
    optimization_log_dict = {
        "change_log": [
            {
                "scene_id": c.scene_id,
                "original_scene_id": c.original_scene_id,
                "action": c.action,
                "summary": c.summary,
                "addresses_diagnostic": c.addresses_diagnostic,
                "details": c.details,
            }
            for c in result.change_log
        ],
        "reasoning": result.reasoning,
        "fallback_reason": result.fallback_reason,
        "focus": body.focus,
    }
    new_id = screenplay_store.save_screenplay(
        novel_id=record["novel_id"],
        yaml_text=new_yaml_text,
        stats=stats,
        warnings=[],
        failed_chapters=[],
        schema_version=record["schema_version"],
        model_name=record["model_name"],
        parent_screenplay_id=screenplay_id,
        optimization_origin=origin,
        optimization_log=optimization_log_dict,
    )

    return {
        "new_screenplay_id": new_id,
        "parent_screenplay_id": screenplay_id,
        "origin": origin,
        "change_log": [
            {
                "scene_id": c.scene_id,
                "original_scene_id": c.original_scene_id,
                "action": c.action,
                "summary": c.summary,
                "addresses_diagnostic": c.addresses_diagnostic,
                "details": c.details,
            }
            for c in result.change_log
        ],
        "reasoning": result.reasoning,
        "fallback_reason": result.fallback_reason,
        "llm_usage": result.llm_usage,
    }


@router.get("/novels/{novel_id}/versions")
def api_list_versions(novel_id: str) -> dict:
    """返该 novel 所有剧本版本(版本树切换用)。"""
    versions = screenplay_store.list_versions_for_novel(novel_id)
    return {"items": versions}


# ============================================================
# 辅助:构造诊断输入(从 yaml dict 扒数据)
# ============================================================


def _build_diagnostics(screenplay: dict) -> dict:
    """构造诊断输入塞给 LLM。

    fidelity 直接从 yaml.scenes[].fidelity 读(compose 时已经算过存进 yaml);
    structure 用 analyze_structure 实时算(无 LLM,快)。
    """
    scenes = screenplay.get("scenes") or []

    # fidelity:从 yaml 已存字段直接拿
    # PR#16 Hot1:过滤"未生成改编决策"伪 issue — 它不是 fidelity 问题,LLM 会误删 V.O.
    fidelity_diag: dict[str, dict] = {}
    for s in scenes:
        if not isinstance(s, dict):
            continue
        scene_id = s.get("id", "")
        fid = s.get("fidelity") or {}
        if isinstance(fid, dict):
            issues_raw = fid.get("issues", []) or []
            issues_clean = [
                iss for iss in issues_raw
                if not isinstance(iss, str)
                or ("改编决策" not in iss and "未生成" not in iss)
            ]
            fidelity_diag[scene_id] = {
                "level": fid.get("level", "medium"),
                "score": fid.get("score", None),
                "reason": fid.get("reason", ""),
                "issues": issues_clean,
            }

    # structure:实时算
    struct_inputs: list[StructureSceneInput] = []
    for s in scenes:
        if not isinstance(s, dict):
            continue
        elements = s.get("elements") or []
        dialogue_chars = 0
        ec = 0
        vo_count = 0
        text_corpus_parts: list[str] = []
        for el in elements:
            if not isinstance(el, dict):
                continue
            t = el.get("type", "")
            if t in ("action", "dialogue", "voiceover", "parenthetical"):
                ec += 1
            text = el.get("text") or ""
            if isinstance(text, str):
                text_corpus_parts.append(text)
                if t in ("dialogue", "voiceover"):
                    dialogue_chars += len(text)
            if t == "voiceover":
                vo_count += 1
        src = s.get("source") or {}
        pr = src.get("paragraph_range") if isinstance(src, dict) else None
        p_count = max(1, pr[1] - pr[0] + 1) if isinstance(pr, list) and len(pr) == 2 else 1
        chars_present = s.get("characters_present") or []
        chars_count = len(chars_present) if isinstance(chars_present, list) else 0
        # fidelity 影响张力评分 — 从 yaml 拿 score 转 0-1
        fid = s.get("fidelity") or {}
        raw_score = fid.get("score") if isinstance(fid, dict) else None
        fid_norm = (raw_score / 100.0) if isinstance(raw_score, (int, float)) else None
        struct_inputs.append(StructureSceneInput(
            scene_id=s.get("id", ""),
            number=int(s.get("number", 0)),
            element_count=ec,
            dialogue_chars=dialogue_chars,
            inner_monologue_count=vo_count,
            characters_present_count=chars_count,
            text_corpus="\n".join(text_corpus_parts),
            fidelity_score=fid_norm,
            paragraph_count=p_count,
        ))
    struct_report = analyze_structure(struct_inputs)
    structure_diag = {
        "overall_health": struct_report.overall_health,
        "overall_score": round(struct_report.overall_score * 100),
        "notes": struct_report.notes,
        "acts": [a.to_dict() for a in struct_report.acts],
    }

    return {
        "fidelity": fidelity_diag,
        "structure": structure_diag,
    }


# ============================================================
# D. 对新增 / 拆分 / 修改的场景补 propose_decisions
# ============================================================


def _attach_decisions_for_new_scenes(
    screenplay: dict, change_log: list,
) -> None:
    """优化后,对所有 action ∈ {added, split, modified} 的 scene,
    扫 voiceover 元素逐个补改编决策(in-place)。

    - added / split:新增的 scene 完全没有 decision
    - modified:旧 scene 改写后 voiceover 可能换了文本,旧 decision 已被 B 清掉
    """
    from app.services.pipeline.adaptation_decision import (
        AdaptationDecisionError,
        propose_decisions,
    )
    from app.services.pipeline.element_extractor import (
        CharacterRef,
        ScreenplayElement,
    )

    # 收集需要补决策的 scene_id
    target_scene_ids: set[str] = set()
    for c in change_log:
        if c.action in ("added", "split", "modified"):
            target_scene_ids.add(c.scene_id)

    if not target_scene_ids:
        return

    scenes = screenplay.get("scenes") or []
    characters_section = screenplay.get("characters") or []
    char_id_to_ref: dict[str, CharacterRef] = {}
    char_id_to_name: dict[str, str] = {}
    for c in characters_section:
        if not isinstance(c, dict):
            continue
        cid = c.get("id")
        nm = (c.get("name") or "").strip()
        if cid and nm:
            aka_list = [
                str(a).strip() for a in (c.get("aka") or [])
                if isinstance(a, str) and a.strip()
            ]
            char_id_to_ref[cid] = CharacterRef(id=cid, name=nm, aka=aka_list)
            char_id_to_name[cid] = nm

    locations_section = screenplay.get("locations") or []
    loc_id_to_name: dict[str, str] = {}
    for l in locations_section:
        if isinstance(l, dict) and l.get("id") and l.get("name"):
            loc_id_to_name[l["id"]] = l["name"]

    # 现有 decisions(确保我们追加,不重复同 element)
    existing_decisions = screenplay.get("adaptation_decisions") or []
    existing_pairs = {
        (d.get("scene_id"), d.get("element_id"))
        for d in existing_decisions
        if isinstance(d, dict)
    }
    # 找下一个可用 dec 编号
    next_dec_n = 1
    for d in existing_decisions:
        if isinstance(d, dict) and isinstance(d.get("id"), str):
            try:
                n = int(d["id"].replace("dec_", ""))
                if n >= next_dec_n:
                    next_dec_n = n + 1
            except (ValueError, AttributeError):
                pass

    new_decisions: list[dict] = []

    for s in scenes:
        if not isinstance(s, dict):
            continue
        sid = s.get("id")
        if sid not in target_scene_ids:
            continue

        # 找出 scene 内有 voiceover 元素
        elements = s.get("elements") or []
        scene_screen_elements: list[ScreenplayElement] = []
        vo_elements: list[tuple[int, dict]] = []  # (idx, el_dict)
        for i, el in enumerate(elements):
            if not isinstance(el, dict):
                continue
            etype = el.get("type", "")
            text = str(el.get("text", "") or "")
            char_id = el.get("character_id")
            char_name = char_id_to_name.get(char_id) if char_id else None
            scene_screen_elements.append(ScreenplayElement(
                type=etype,
                text=text,
                character_name=char_name,
                parenthetical=el.get("parenthetical"),
                is_inner_monologue=(etype == "voiceover"),
            ))
            if etype == "voiceover":
                # 跳过已有 decision 的
                eid = el.get("id")
                if (sid, eid) in existing_pairs:
                    continue
                vo_elements.append((i, el))

        if not vo_elements:
            continue

        # 调 LLM
        heading = s.get("heading") or {}
        loc_id = heading.get("location_id")
        scene_heading = {
            "int_ext": heading.get("int_ext", "INT"),
            "location_name": loc_id_to_name.get(loc_id, "未命名"),
            "time_of_day": heading.get("time_of_day", "日"),
        }
        scene_summary = str(s.get("summary", "") or "")
        chars_in_scene = [
            char_id_to_ref[cid]
            for cid in (s.get("characters_present") or [])
            if cid in char_id_to_ref
        ]
        # scene_text 用 elements 文本拼接(优化后场景没有原文)
        scene_text = "\n".join(
            str(el.get("text", "") or "")
            for el in elements
            if isinstance(el, dict)
        )

        try:
            result = propose_decisions(
                scene_text=scene_text,
                scene_summary=scene_summary,
                scene_heading=scene_heading,
                characters_in_scene=chars_in_scene,
                elements=scene_screen_elements,
            )
        except AdaptationDecisionError:
            continue  # 失败兜底:不补就不补,不阻断

        # 把 result.decisions 转 dict,绑 element_id
        for dec in result.decisions:
            idx = dec.element_index
            if idx >= len(elements):
                continue
            target_el = elements[idx]
            if not isinstance(target_el, dict):
                continue
            new_decisions.append({
                "id": f"dec_{next_dec_n:03d}",
                "scene_id": sid,
                "element_id": target_el.get("id", ""),
                "original_text": dec.original_text or "",
                "options": [
                    {
                        "type": opt.type,
                        **({"text": opt.text} if opt.text else {}),
                        **({"pros": opt.pros} if opt.pros else {}),
                        **({"cons": opt.cons} if opt.cons else {}),
                        **({"rationale": opt.rationale} if opt.rationale else {}),
                    }
                    for opt in dec.options
                ],
            })
            next_dec_n += 1

    if new_decisions:
        existing_decisions.extend(new_decisions)
        screenplay["adaptation_decisions"] = existing_decisions


# ============================================================
# C. 把作者已做的决策摘要给 LLM
# ============================================================


def _summarize_author_decisions(
    screenplay: dict, user_decisions: dict[str, str],
) -> list[dict]:
    """把 {decision_id → chosen_type} 转成 LLM 可读的列表。

    每条:{scene_id, original_text, chosen_type, chosen_label} — 让 LLM 知道
    "scene_001 的这段内心独白,作者拍板要走画外音,你别动了"。
    """
    label_map = {
        "voiceover": "保留为画外音 V.O.",
        "action_externalize": "改为可见动作",
        "delete": "删除该元素",
        "subtext": "改为潜台词",
        "symbolism": "用意象/道具替代",
        "montage": "用蒙太奇拼接",
    }
    decisions_by_id: dict[str, dict] = {}
    for d in screenplay.get("adaptation_decisions") or []:
        if isinstance(d, dict) and "id" in d:
            decisions_by_id[d["id"]] = d

    out: list[dict] = []
    for dec_id, chosen in user_decisions.items():
        d = decisions_by_id.get(dec_id)
        if not d:
            continue
        out.append({
            "scene_id": d.get("scene_id", ""),
            "element_id": d.get("element_id", ""),
            "original_text": (d.get("original_text") or "")[:140],
            "chosen_type": chosen,
            "chosen_label": label_map.get(chosen, chosen),
        })
    return out


# ============================================================
# A. 重算 fidelity — 优化后闭环对齐
# ============================================================


def _refresh_fidelity_in_screenplay(screenplay: dict, novel_id: str) -> None:
    """对优化后的 yaml 逐场重算 fidelity,写回 scene.fidelity 字段(in-place)。

    数据流:
      1. 拉 novel 的 chapters / paragraphs(用于拼 scene_text 原文)
      2. 拼 character_name → char_id / aka 映射
      3. 对每 scene:scene_text + elements + decisions → score_scene_fidelity
      4. 写回 scene["fidelity"] = result.to_dict()

    LLM 失败兜底:某场算失败 → 保留原 fidelity 或空字段,不阻断后续。
    """
    scenes = screenplay.get("scenes") or []
    if not isinstance(scenes, list) or not scenes:
        return

    # 拉小说原文 — 给 fidelity 算对白覆盖度提供 baseline
    novel = ingest_service.get_novel(novel_id)
    if novel is None:
        return
    # chapter_number → paragraphs
    paragraphs_by_chapter: dict[int, list[str]] = {}
    for ch in novel.get("chapters", []):
        rows = ingest_service.get_chapter_paragraphs(ch["id"]) or []
        # 按 index_in_chapter 排序后取 text
        rows_sorted = sorted(
            rows, key=lambda r: r.get("index_in_chapter", 0),
        )
        paragraphs_by_chapter[ch["number"]] = [
            r.get("text", "") for r in rows_sorted
        ]

    # 角色 name → aka 映射(给 character_alignment 用)
    characters_section = screenplay.get("characters") or []
    char_id_to_name: dict[str, str] = {}
    aka_lookup: dict[str, list[str]] = {}
    for c in characters_section:
        if not isinstance(c, dict):
            continue
        cid = c.get("id")
        nm = (c.get("name") or "").strip()
        if cid and nm:
            char_id_to_name[cid] = nm
            akas = [
                str(a).strip() for a in (c.get("aka") or [])
                if isinstance(a, str) and a.strip()
            ]
            aka_lookup[nm] = akas

    # decisions by scene_id(给 decision_completeness 用)
    decisions_by_scene: dict[str, list[AdaptationDecision]] = {}
    for d in screenplay.get("adaptation_decisions") or []:
        if not isinstance(d, dict):
            continue
        sid = d.get("scene_id")
        if not sid:
            continue
        # 把 dict 还原为 AdaptationDecision dataclass
        options_dicts = d.get("options") or []
        options: list[AdaptationOption] = []
        for opt in options_dicts:
            if isinstance(opt, dict):
                options.append(AdaptationOption(
                    type=opt.get("type", "voiceover"),
                    text=opt.get("text", "") or "",
                    pros=opt.get("pros", "") or "",
                    cons=opt.get("cons", "") or "",
                    rationale=opt.get("rationale", "") or "",
                ))
        decisions_by_scene.setdefault(sid, []).append(AdaptationDecision(
            element_index=0,   # 这里只用 options/recommended 给 fidelity 看,index 无所谓
            original_text=d.get("original_text", "") or "",
            options=options,
            recommended=d.get("chosen") or "voiceover",
        ))

    # 逐场算
    for scene in scenes:
        if not isinstance(scene, dict):
            continue
        # 拼 scene_text 原文
        src = scene.get("source") or {}
        chapter_no = src.get("chapter") if isinstance(src, dict) else None
        rng = src.get("paragraph_range") if isinstance(src, dict) else None
        scene_text = ""
        if isinstance(chapter_no, int) and isinstance(rng, list) and len(rng) == 2:
            paras = paragraphs_by_chapter.get(chapter_no, [])
            try:
                start, end = int(rng[0]), int(rng[1])
                selected = paras[start - 1:end]
                scene_text = "\n\n".join(selected)
            except (TypeError, ValueError):
                pass
        # 兜底:若无原文(可能是 LLM 新增的场),用 elements 文本做 baseline
        if not scene_text:
            scene_text = "\n".join(
                str(el.get("text", "") or "")
                for el in (scene.get("elements") or [])
                if isinstance(el, dict)
            )

        # characters_present 转 name
        present_names: list[str] = []
        for cid in scene.get("characters_present") or []:
            nm = char_id_to_name.get(cid)
            if nm:
                present_names.append(nm)

        # elements dict → ScreenplayElement
        screen_elements: list[ScreenplayElement] = []
        for el in scene.get("elements") or []:
            if not isinstance(el, dict):
                continue
            etype = el.get("type", "")
            text = str(el.get("text", "") or "")
            char_id = el.get("character_id")
            char_name = char_id_to_name.get(char_id) if char_id else None
            screen_elements.append(ScreenplayElement(
                type=etype,
                text=text,
                character_name=char_name,
                parenthetical=el.get("parenthetical"),
                is_inner_monologue=(etype == "voiceover"),
            ))

        # decisions
        scene_decisions = decisions_by_scene.get(scene.get("id", ""), [])

        # 调 fidelity_scorer
        try:
            result = score_scene_fidelity(FidelityInput(
                scene_text=scene_text,
                characters_present_names=present_names,
                elements=screen_elements,
                decisions=scene_decisions,
                character_aka_lookup=aka_lookup,
            ))
            # to_dict 返回的 score 是 0-1,与 compose_service 初次输出一致
            # 前端 FidelityBadge 期望 0-1 自己乘 100 显示,后端不要再乘
            scene["fidelity"] = result.to_dict()
        except Exception:   # noqa: BLE001
            # 失败兜底 — 保留原字段或写入空诊断
            if "fidelity" not in scene:
                scene["fidelity"] = {"level": "medium", "score": 50, "issues": []}


# ============================================================
# B. 清理幽灵 decisions — element_id 不存在的 decision 丢弃
# ============================================================


def _purge_orphan_decisions(screenplay: dict) -> None:
    """优化后 element_id 已重发,原 decisions 引用的 element 可能不存在 → 清理(in-place)。

    保留规则:scene_id + element_id 同时都在新 yaml 里能找到 → 保留;否则丢弃。
    """
    decisions = screenplay.get("adaptation_decisions")
    if not isinstance(decisions, list):
        return

    # 收集所有有效的 (scene_id, element_id) 对
    valid_pairs: set[tuple[str, str]] = set()
    for s in screenplay.get("scenes") or []:
        if not isinstance(s, dict):
            continue
        sid = s.get("id")
        if not sid:
            continue
        for el in s.get("elements") or []:
            if not isinstance(el, dict):
                continue
            eid = el.get("id")
            if eid:
                valid_pairs.add((sid, eid))

    cleaned: list[dict] = []
    for d in decisions:
        if not isinstance(d, dict):
            continue
        sid = d.get("scene_id")
        eid = d.get("element_id")
        if sid and eid and (sid, eid) in valid_pairs:
            cleaned.append(d)
        # 否则丢弃 — 该 element 已被优化器删除或重写,decision 失效

    screenplay["adaptation_decisions"] = cleaned


def _estimate_pages(scenes_section: list) -> int:
    """页数估算(同 yaml_composer)。"""
    if not isinstance(scenes_section, list):
        return 1
    total_lines = sum(
        len(s.get("elements", []))
        for s in scenes_section
        if isinstance(s, dict)
    )
    return max(1, round(total_lines / 25))
