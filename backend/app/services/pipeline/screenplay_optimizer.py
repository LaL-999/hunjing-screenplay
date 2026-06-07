"""剧本优化引擎 — PR#16 人机协作核心。

A 入口(单场精修)+ B 入口(整本重排)共用同一个 LLM 调用,只是 scope 不同。

输入:
  - 完整 screenplay dict(从 yaml 解析)
  - 诊断:fidelity 各场 + structure 整体
  - 范围:single_scene(+target_id) 或 full_screenplay
  - focus:fidelity | structure | both

输出:
  - 新版 screenplay dict(可能新增/拆/合并 scene)
  - change_log:每个修改的 scene 一条({scene_id, action, summary, addresses_diagnostic})
  - reasoning:总体优化思路

数据流:
  optimize_screenplay()
    → 构造 user_input
    → call_json(prompt, user_input)
    → 解析返回 dict
    → 校验 + 重发 scene_id(NEW_after_xxx → scene_NNN)+ 重发 element_id
    → 返 OptimizeResult
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from app.services.llm_client import (
    LlmCallFailed,
    LlmJsonParseFailed,
    call_json,
)

logger = logging.getLogger(__name__)


# ============================================================
# 输入 / 输出
# ============================================================


OptimizeScope = Literal["single_scene", "full_screenplay"]
FocusType = Literal["fidelity", "structure", "both"]


@dataclass
class OptimizeRequest:
    screenplay: dict                          # 完整 yaml 解析后 dict
    scope: OptimizeScope
    diagnostics: dict                          # {"fidelity": {...}, "structure": {...}}
    focus: FocusType = "both"
    target_scene_id: str | None = None         # 只在 single_scene 时有
    # single_scene 用小预算(只输出 1 场,~2500 已经够);full_screenplay 仍 6000
    max_tokens: int = 6000

    def effective_max_tokens(self) -> int:
        """根据 scope 自动调整 max_tokens(单场 3500 / 整本 6000)。"""
        if self.scope == "single_scene":
            return min(self.max_tokens, 3500)
        return self.max_tokens


@dataclass
class ChangeLogEntry:
    """单场的修改记录。"""

    scene_id: str                              # 修改后的 scene_id(可能是新分配的)
    original_scene_id: str | None              # 修改前的 scene_id(新增场为 None)
    action: str                                # modified | added | removed | split | merged
    summary: str                               # 一句话说改了什么
    addresses_diagnostic: str                  # 呼应了哪条诊断
    details: str = ""                          # 详细说明(可空)


@dataclass
class OptimizeResult:
    """优化结果。"""

    optimized_screenplay: dict                 # 新版 yaml dict(已重发 id)
    change_log: list[ChangeLogEntry] = field(default_factory=list)
    reasoning: str = ""
    llm_usage: dict = field(default_factory=lambda: {"input_tokens": 0, "output_tokens": 0})
    fallback_reason: str | None = None         # 非 None 时表示 LLM 失败,返回了原 screenplay 不变


# ============================================================
# Prompt 加载
# ============================================================


_PROMPT_PATH = Path(__file__).parent.parent.parent / "prompts" / "screenplay_optimizer.md"
_SYSTEM_PROMPT: str | None = None


def _get_system_prompt() -> str:
    global _SYSTEM_PROMPT
    if _SYSTEM_PROMPT is None:
        if not _PROMPT_PATH.exists():
            raise FileNotFoundError(f"screenplay_optimizer prompt not found: {_PROMPT_PATH}")
        _SYSTEM_PROMPT = _PROMPT_PATH.read_text(encoding="utf-8")
    return _SYSTEM_PROMPT


# ============================================================
# 主入口
# ============================================================


class ScreenplayOptimizeError(Exception):
    """优化失败。"""


def optimize_screenplay(req: OptimizeRequest) -> OptimizeResult:
    """优化剧本 — A/B 入口共用此函数。

    Args:
        req: 包含 screenplay + scope + diagnostics 等

    Returns:
        OptimizeResult — 失败时返原 screenplay + fallback_reason
    """
    if not isinstance(req.screenplay, dict):
        raise ScreenplayOptimizeError("screenplay 必须是 dict")

    if req.scope == "single_scene" and not req.target_scene_id:
        raise ScreenplayOptimizeError("single_scene 范围必须指定 target_scene_id")

    # 校验 target_scene_id 存在
    if req.scope == "single_scene":
        scene_ids = {s.get("id") for s in (req.screenplay.get("scenes") or []) if isinstance(s, dict)}
        if req.target_scene_id not in scene_ids:
            raise ScreenplayOptimizeError(
                f"target_scene_id {req.target_scene_id} 不在剧本中"
            )

    user_input = _build_user_input(req)

    try:
        parsed, usage = call_json(
            _get_system_prompt(), user_input, max_tokens=req.effective_max_tokens(),
        )
    except (LlmCallFailed, LlmJsonParseFailed) as e:
        # 兜底:返原 screenplay + 失败信息
        return OptimizeResult(
            optimized_screenplay=req.screenplay,
            change_log=[],
            reasoning="LLM 调用失败,已回退到原版,你可以重试。",
            llm_usage={"input_tokens": 0, "output_tokens": 0},
            fallback_reason=f"LLM 失败: {e}",
        )

    if not isinstance(parsed, dict):
        return _fallback_result(req, "LLM 返回非 dict")

    raw_change_log = parsed.get("change_log") or []
    raw_reasoning = str(parsed.get("reasoning", "")).strip()

    # 输出形态根据 scope 区分:
    #   single_scene → LLM 只输出 optimized_scene(单场),后端 merge 回完整 screenplay
    #   full_screenplay → LLM 输出 optimized_screenplay(完整)
    if req.scope == "single_scene":
        optimized_scene = parsed.get("optimized_scene")
        if not isinstance(optimized_scene, dict):
            # 兼容:有些模型还是返回 optimized_screenplay
            full_sp = parsed.get("optimized_screenplay")
            if isinstance(full_sp, dict):
                optimized = full_sp
            else:
                return _fallback_result(req, "LLM 输出缺少 optimized_scene")
        else:
            # 把单场 merge 回原 screenplay
            optimized = _merge_single_scene(
                req.screenplay, optimized_scene, req.target_scene_id or "",
            )
    else:
        optimized = parsed.get("optimized_screenplay")
        if not isinstance(optimized, dict):
            return _fallback_result(req, "LLM 输出缺少 optimized_screenplay")

    # 把新增场的占位 id(NEW_after_scene_XXX) 重新发为正式 scene_NNN
    optimized, id_remap = _renumber_scenes_and_elements(optimized)

    # 解析 change_log
    change_log = _parse_change_log(raw_change_log, id_remap)

    return OptimizeResult(
        optimized_screenplay=optimized,
        change_log=change_log,
        reasoning=raw_reasoning or "(LLM 未给出 reasoning)",
        llm_usage=usage,
    )


# ============================================================
# 单场 merge 回完整 screenplay(single_scene 模式专用)
# ============================================================


def _merge_single_scene(
    original_screenplay: dict,
    optimized_scene: dict,
    target_scene_id: str,
) -> dict:
    """把 LLM 输出的单场 merge 回原 screenplay,其他场原样保留。

    LLM 返回 {id, heading, elements, ...} 形态的单场,这里替换 scenes 数组中
    对应 id 的那一场,其余 24 场原样保留 — 大幅省 token + 加速。
    """
    new_screenplay = dict(original_screenplay)
    scenes = list(original_screenplay.get("scenes") or [])
    new_scenes: list[dict] = []
    found = False
    for s in scenes:
        if isinstance(s, dict) and s.get("id") == target_scene_id:
            # 替换为新场;保留原 id / number(LLM 可能不写)
            merged = dict(optimized_scene)
            merged["id"] = target_scene_id
            if "number" not in merged and "number" in s:
                merged["number"] = s["number"]
            new_scenes.append(merged)
            found = True
        else:
            new_scenes.append(s)
    if not found and isinstance(optimized_scene, dict):
        # LLM 可能修改了 id 或者拆/合并,直接追加(后续 renumber 会处理)
        new_scenes.append(optimized_scene)
    new_screenplay["scenes"] = new_scenes
    return new_screenplay


# ============================================================
# 构造 LLM user_input
# ============================================================


def _build_user_input(req: OptimizeRequest) -> dict:
    """喂给 LLM 的 JSON payload。

    single_scene 模式:精简上下文 — 只送 target scene 完整 + 前后 2 场摘要,
    并把 characters / locations 等元数据原样保留。这样输入从 ~20K 降到 ~3K token。
    """
    payload: dict[str, Any] = {
        "scope": req.scope,
        "diagnostics": req.diagnostics or {},
        "focus": req.focus,
    }
    if req.scope == "single_scene" and req.target_scene_id:
        payload["target_scene_id"] = req.target_scene_id
        payload["current_screenplay"] = _build_compact_context(
            req.screenplay, req.target_scene_id,
        )
    else:
        payload["current_screenplay"] = req.screenplay
    return payload


def _build_compact_context(screenplay: dict, target_scene_id: str) -> dict:
    """单场优化时,只送 target scene 全文 + 前后 2 场摘要 + meta / characters / locations。

    省 token 同时给 LLM 足够上下文(知道角色、地点、邻接剧情、全本骨架)。

    精简策略:
      - target_scene:完整 elements
      - 前后各 2 场:summary + heading + characters_present(详细摘要)
      - 其余远场:仅 number + heading + summary 短行(全本骨架 outline)
    """
    scenes = screenplay.get("scenes") or []
    target_idx = -1
    for i, s in enumerate(scenes):
        if isinstance(s, dict) and s.get("id") == target_scene_id:
            target_idx = i
            break
    if target_idx == -1:
        # 找不到 target,退回完整 yaml(理论上不会到这,前面已校验)
        return screenplay

    # 邻接场摘要(前后各 2 场)
    def _scene_brief(s: dict) -> dict:
        if not isinstance(s, dict):
            return {}
        return {
            "id": s.get("id"),
            "number": s.get("number"),
            "heading": s.get("heading"),
            "summary": s.get("summary", ""),
            "characters_present": s.get("characters_present", []),
        }

    context_scenes: list[dict] = []
    for i in range(max(0, target_idx - 2), target_idx):
        context_scenes.append(_scene_brief(scenes[i]))
    # target scene 原文完整保留
    context_scenes.append(scenes[target_idx])
    for i in range(target_idx + 1, min(len(scenes), target_idx + 3)):
        context_scenes.append(_scene_brief(scenes[i]))

    # 🌟 全本骨架(outline) — 让 LLM 知道剧本整体走向,避免与远场矛盾
    full_outline: list[dict] = []
    for i, s in enumerate(scenes):
        if not isinstance(s, dict):
            continue
        heading = s.get("heading") or {}
        full_outline.append({
            "number": s.get("number", i + 1),
            "id": s.get("id"),
            "int_ext": heading.get("int_ext") if isinstance(heading, dict) else None,
            "location_id": heading.get("location_id") if isinstance(heading, dict) else None,
            "time_of_day": heading.get("time_of_day") if isinstance(heading, dict) else None,
            "summary": (s.get("summary") or "")[:120],
            "is_target": s.get("id") == target_scene_id,
        })

    return {
        "meta": screenplay.get("meta", {}),
        "characters": screenplay.get("characters", []),
        "locations": screenplay.get("locations", []),
        "scenes": context_scenes,
        "full_outline": full_outline,
        "_context_note": (
            f"为节省 token,只送 target_scene 完整内容及前后各 2 场摘要;"
            f"另附 full_outline(全本 {len(scenes)} 场骨架)给你做全局一致性检查。"
        ),
    }


# ============================================================
# 重发 scene_id + element_id
# ============================================================


def _renumber_scenes_and_elements(
    screenplay: dict,
) -> tuple[dict, dict[str, str]]:
    """LLM 返回的 scene 列表中,新增场用 NEW_after_xxx 占位 — 重新编号为 scene_NNN_NNN。

    Returns:
        (new_screenplay, id_remap)
        id_remap: {原 scene_id (含占位) → 新分配的 scene_id}
    """
    scenes = screenplay.get("scenes") or []
    if not isinstance(scenes, list):
        return screenplay, {}

    id_remap: dict[str, str] = {}
    renumbered: list[dict] = []
    counter = 0

    for s in scenes:
        if not isinstance(s, dict):
            continue
        counter += 1
        old_id = str(s.get("id", ""))
        new_id = f"scene_{counter:03d}"
        s = dict(s)
        s["id"] = new_id
        s["number"] = counter
        if old_id:
            id_remap[old_id] = new_id

        # element id 也按 new_id 重新编号
        elements = s.get("elements") or []
        if isinstance(elements, list):
            new_elements: list[dict] = []
            for i, el in enumerate(elements, start=1):
                if not isinstance(el, dict):
                    continue
                el = dict(el)
                el["id"] = f"el_{counter:03d}_{i:03d}"
                new_elements.append(el)
            s["elements"] = new_elements

        renumbered.append(s)

    screenplay = dict(screenplay)
    screenplay["scenes"] = renumbered

    # adaptation_decisions 里的 scene_id / element_id 也要更新
    decisions = screenplay.get("adaptation_decisions") or []
    if isinstance(decisions, list):
        new_decisions: list[dict] = []
        for d in decisions:
            if not isinstance(d, dict):
                continue
            d = dict(d)
            old_sid = d.get("scene_id", "")
            if old_sid in id_remap:
                d["scene_id"] = id_remap[old_sid]
            # element_id 我们已经重发了,但 decision 引用的 old element_id 在这里没法精确映射
            # 简化:scene 还在的情况下,保留 decision 但 element_id 可能失效 — 校验层会丢弃
            new_decisions.append(d)
        screenplay["adaptation_decisions"] = new_decisions

    return screenplay, id_remap


# ============================================================
# 解析 change_log
# ============================================================


def _parse_change_log(
    raw: list, id_remap: dict[str, str],
) -> list[ChangeLogEntry]:
    """把 LLM 输出的 change_log 数组转 dataclass。"""
    out: list[ChangeLogEntry] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        scene_id_raw = str(item.get("scene_id", "")).strip()
        # 占位 id → 新分配 id
        scene_id = id_remap.get(scene_id_raw, scene_id_raw)
        action = str(item.get("action", "modified")).strip().lower()
        if action not in ("modified", "added", "removed", "split", "merged"):
            action = "modified"
        summary = str(item.get("summary", "")).strip()[:200]
        addresses = str(item.get("addresses_diagnostic", "")).strip()[:200]
        details = str(item.get("details", "")).strip()[:500]

        # 修改场:original_scene_id = scene_id_raw(可能也是占位)
        # 新增场:scene_id_raw 是 NEW_after_xxx,original_scene_id = None
        original = scene_id_raw if not scene_id_raw.startswith("NEW_") else None

        if not summary:
            continue

        out.append(ChangeLogEntry(
            scene_id=scene_id,
            original_scene_id=original,
            action=action,
            summary=summary,
            addresses_diagnostic=addresses,
            details=details,
        ))

    return out


# ============================================================
# 兜底
# ============================================================


def _fallback_result(req: OptimizeRequest, reason: str) -> OptimizeResult:
    return OptimizeResult(
        optimized_screenplay=req.screenplay,
        change_log=[],
        reasoning=f"优化未能生成有效输出,已回退到原版:{reason}",
        llm_usage={"input_tokens": 0, "output_tokens": 0},
        fallback_reason=reason,
    )
