"""剧本 YAML 组装 — PR#10 核心(纯函数层,无 LLM / 无 DB / 无 IO)。

把 PR#6-9 各 agent 的产出,组装成符合 docs/SCHEMA_DESIGN.md
（schemas/screenplay.json）的剧本 YAML。

设计原则:
  - **纯函数**,可单测,无副作用
  - **ID 编号纪律**(对齐 schema 正则 ^xxx_\\d{3,5}$):
      * char_NNN  — 按 bible.characters 顺序
      * loc_NNN   — 按场景中首次出现顺序
      * scene_NNN — 全局连续,跨 chapter
      * el_NNN_MMM — scene_NNN + scene 内 element 1-based 序号
      * dec_NNN   — 全局连续
  - **name → ID 映射**在 composer 内集中做,外部传 name
  - **降级而非崩溃**:任何无法合法转 ID 的元素 / 场景跳过 + warning,
    只在完全无法产出时 raise ComposeError
  - 最终 yaml dict **必须能通过 yaml_validator**(由 service 层强制)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import yaml

from app.services.pipeline.adaptation_decision import AdaptationDecision
from app.services.pipeline.element_extractor import ScreenplayElement
from app.services.pipeline.scene_splitter import SceneHeading

logger = logging.getLogger(__name__)


# ============================================================
# 输入 / 输出
# ============================================================


@dataclass
class SceneAssembleData:
    """单场组装数据 — 编排层(PR#10 commit 3)调完 PR#6-9 各 agent 后的产物。"""

    chapter_number: int
    scene_index_in_chapter: int           # 1-based,仅 fallback summary 用
    heading: SceneHeading
    summary: str
    characters_present_names: list[str]   # 名字 / aka,composer 内转 char_id
    paragraph_range: tuple[int, int]
    elements: list[ScreenplayElement]
    decisions: list[AdaptationDecision] = field(default_factory=list)
    transition_to_next: str = ""           # 空 → 不写入 yaml(避免 schema 枚举校验失败)
    fidelity: dict | None = None           # PR#12:{level, score, reason, issues, dimensions}


@dataclass
class ComposeInput:
    """组装输入 — 一篇小说的全套数据。"""

    novel_title: str
    bible: dict                            # story_bible 完整 dict
    scenes: list[SceneAssembleData]
    source_format: str | None = None       # txt / epub / docx
    source_filename: str | None = None
    adapted_from_chapters: list[int] = field(default_factory=list)
    model_name: str | None = None          # LLM 模型名(给 meta.generated_by)
    schema_version: str = "1.0"
    platform_version: str = "hunjing-screenplay@0.1.0"


@dataclass
class ComposeWarning:
    """组装过程中跳过的元素 / 场景 — 给 service 层汇总 + 持久化。"""

    layer: str       # location | character | element | scene | decision
    path: str        # 类似 scenes[3].elements[2]
    message: str


@dataclass
class ComposeResult:
    """组装结果。"""

    yaml_text: str
    yaml_dict: dict
    location_id_map: dict[str, str] = field(default_factory=dict)   # name → loc_NNN
    character_id_map: dict[str, str] = field(default_factory=dict)  # name/aka → char_NNN
    scene_id_map: dict[int, str] = field(default_factory=dict)      # 输入 scenes 下标 0-based → scene_NNN
    warnings: list[ComposeWarning] = field(default_factory=list)
    stats: dict = field(default_factory=dict)


class ComposeError(Exception):
    """组装致命错误(bible 无 characters / scenes 全空 / 全场被过滤)。"""


# ============================================================
# ID 编号工具
# ============================================================


def _id_pad(n: int) -> str:
    """1 → "001";schema 允许 3-5 位 zero-padded。"""
    return f"{n:03d}" if n < 1000 else f"{n:05d}"


def _make_char_id(n: int) -> str:
    return f"char_{_id_pad(n)}"


def _make_loc_id(n: int) -> str:
    return f"loc_{_id_pad(n)}"


def _make_scene_id(n: int) -> str:
    return f"scene_{_id_pad(n)}"


def _make_element_id(scene_n: int, el_n: int) -> str:
    return f"el_{_id_pad(scene_n)}_{_id_pad(el_n)}"


def _make_decision_id(n: int) -> str:
    return f"dec_{_id_pad(n)}"


# ============================================================
# 主入口
# ============================================================


def assemble_screenplay(compose_input: ComposeInput) -> ComposeResult:
    """组装完整剧本 YAML。

    Args:
        compose_input: 小说标题 + 圣经 + 全套 scenes

    Returns:
        ComposeResult — yaml_text + yaml_dict + 全套 ID 映射 + warnings

    Raises:
        ComposeError: bible 缺 characters / scenes 全空 / 全部被过滤
    """
    # 1. bible.characters 必须有(schema minItems: 1)
    bible_chars = compose_input.bible.get("characters") or []
    if not isinstance(bible_chars, list) or not bible_chars:
        raise ComposeError("故事圣经缺少 characters,无法组装(schema 要求至少 1 个角色)")

    if not compose_input.scenes:
        raise ComposeError("无可组装的场景")

    warnings: list[ComposeWarning] = []

    # 2. characters 段 + name → char_id 映射
    characters_section, char_id_map = _build_characters(bible_chars)
    if not characters_section:
        raise ComposeError("bible.characters 全部无效(无名字 / 重名 / 非 dict)")

    # 3. 收集 location_name → loc_id(按首次出现顺序)
    location_id_map = _collect_location_ids(compose_input.scenes)
    locations_section = _build_locations(
        compose_input.scenes, location_id_map, compose_input.bible
    )
    if not locations_section:
        raise ComposeError("无法从场景头推断任何 location")

    # 4. 组装 scenes(同时分配 scene_id + element_id)
    scenes_section, scene_id_map, element_id_lookup = _build_scenes(
        compose_input.scenes, char_id_map, location_id_map, warnings,
    )
    if not scenes_section:
        raise ComposeError(
            "所有场景都被过滤(elements 全空 / 角色名全不在 bible / location 全无映射)"
        )

    # 5. 组装 adaptation_decisions(可空)
    decisions_section = _build_decisions(
        compose_input.scenes, scene_id_map, element_id_lookup, warnings,
    )

    # 6. 统计 + meta
    stats = {
        "total_scenes": len(scenes_section),
        "total_pages_estimate": _estimate_pages(scenes_section),
    }
    meta_section = _build_meta(compose_input, stats)

    # 7. 汇总最终 dict
    yaml_dict: dict[str, Any] = {
        "meta": meta_section,
        "characters": characters_section,
        "locations": locations_section,
        "scenes": scenes_section,
    }
    if decisions_section:
        yaml_dict["adaptation_decisions"] = decisions_section

    yaml_text = _serialize_to_yaml(yaml_dict)

    return ComposeResult(
        yaml_text=yaml_text,
        yaml_dict=yaml_dict,
        location_id_map=location_id_map,
        character_id_map=char_id_map,
        scene_id_map=scene_id_map,
        warnings=warnings,
        stats=stats,
    )


# ============================================================
# characters 段
# ============================================================


def _build_characters(bible_chars: list[dict]) -> tuple[list[dict], dict[str, str]]:
    """构建 characters 段 + (name + aka) → char_id 映射。

    name 重复 → 跳过后续(避免编号空洞);
    aka 已在 name_to_id 里 → setdefault 不覆盖(主名优先)。
    """
    section: list[dict] = []
    name_to_id: dict[str, str] = {}
    char_counter = 0

    for raw in bible_chars:
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("name", "")).strip()
        if not name or name in name_to_id:
            continue

        char_counter += 1
        cid = _make_char_id(char_counter)
        entry: dict[str, Any] = {"id": cid, "name": name}

        aka_raw = raw.get("aka") or []
        if isinstance(aka_raw, list):
            clean_aka: list[str] = []
            for a in aka_raw:
                if isinstance(a, str) and a.strip():
                    a_clean = a.strip()
                    if a_clean not in clean_aka and a_clean != name:
                        clean_aka.append(a_clean)
            if clean_aka:
                entry["aka"] = clean_aka

        desc = raw.get("description")
        if isinstance(desc, str) and desc.strip():
            entry["description"] = desc.strip()[:500]

        arc = raw.get("arc_summary")
        if isinstance(arc, str) and arc.strip():
            entry["arc_summary"] = arc.strip()[:200]

        section.append(entry)
        name_to_id[name] = cid
        for a in entry.get("aka", []):
            name_to_id.setdefault(a, cid)   # 主名已占位,aka 不能覆盖别的主名

    return section, name_to_id


# ============================================================
# locations 段
# ============================================================


def _collect_location_ids(scenes: list[SceneAssembleData]) -> dict[str, str]:
    """按场景首次出现顺序分配 loc_NNN。"""
    out: dict[str, str] = {}
    counter = 0
    for s in scenes:
        name = (s.heading.location_name or "").strip()
        if not name:
            continue
        if name not in out:
            counter += 1
            out[name] = _make_loc_id(counter)
    return out


def _build_locations(
    scenes: list[SceneAssembleData],
    loc_id_map: dict[str, str],
    bible: dict,
) -> list[dict]:
    """构建 locations 段。int_ext 取首次出现的 scene heading。"""
    bible_locs = bible.get("locations") or []
    bible_loc_by_name: dict[str, dict] = {}
    if isinstance(bible_locs, list):
        for raw in bible_locs:
            if isinstance(raw, dict):
                lname = str(raw.get("name", "")).strip()
                if lname:
                    bible_loc_by_name[lname] = raw

    first_int_ext: dict[str, str] = {}
    for s in scenes:
        name = (s.heading.location_name or "").strip()
        if name and name not in first_int_ext:
            first_int_ext[name] = s.heading.int_ext

    section: list[dict] = []
    for name, lid in loc_id_map.items():
        entry: dict[str, Any] = {
            "id": lid,
            "name": name,
            "int_ext": first_int_ext.get(name, "INT"),
        }
        bible_entry = bible_loc_by_name.get(name)
        if bible_entry:
            desc = bible_entry.get("description")
            if isinstance(desc, str) and desc.strip():
                entry["description"] = desc.strip()[:500]
        section.append(entry)

    return section


# ============================================================
# scenes 段
# ============================================================


def _build_scenes(
    scenes_in: list[SceneAssembleData],
    char_id_map: dict[str, str],
    loc_id_map: dict[str, str],
    warnings: list[ComposeWarning],
) -> tuple[list[dict], dict[int, str], dict[tuple[int, int], str]]:
    """构建 scenes 段 + scene_id_map + element_id_lookup。

    流程:
      1. 检查 location 映射(无 → 跳过本场 + warning)
      2. 试构造每个 element 的 partial dict(不含 id)
      3. 若全被过滤 → 跳过本场 + warning
      4. 入选 → 分配 scene_id + 给 elements 加 id
    """
    scenes_section: list[dict] = []
    scene_id_map: dict[int, str] = {}
    element_id_lookup: dict[tuple[int, int], str] = {}

    global_scene_n = 0

    for in_idx, s in enumerate(scenes_in):
        loc_name = (s.heading.location_name or "").strip()
        loc_id = loc_id_map.get(loc_name)
        if not loc_id:
            warnings.append(ComposeWarning(
                layer="scene", path=f"scenes[{in_idx}]",
                message=f"无 location_id 映射(原 name={loc_name!r}),跳过本场",
            ))
            continue

        # 试构造 elements(先不给 id,等本场确认入选再编号)
        kept: list[tuple[int, dict]] = []  # (原 element 0-based 下标, partial dict 不含 id)
        for el_in_idx, el in enumerate(s.elements):
            partial = _build_element_no_id(
                el, char_id_map,
                f"scenes[{in_idx}].elements[{el_in_idx}]",
                warnings,
            )
            if partial is None:
                continue
            kept.append((el_in_idx, partial))

        if not kept:
            warnings.append(ComposeWarning(
                layer="scene", path=f"scenes[{in_idx}]",
                message="本场所有元素被过滤,跳过本场(schema 要求 minItems=1)",
            ))
            continue

        # 确认入选 → 分配 scene_id + element_id
        global_scene_n += 1
        scene_id = _make_scene_id(global_scene_n)
        scene_id_map[in_idx] = scene_id

        confirmed_elements: list[dict] = []
        for el_1based_idx, (orig_idx, partial) in enumerate(kept, start=1):
            new_id = _make_element_id(global_scene_n, el_1based_idx)
            partial["id"] = new_id
            # 为保持 schema 字段顺序好读,把 id 提到最前
            confirmed_elements.append(_reorder_element_keys(partial))
            element_id_lookup[(in_idx, orig_idx)] = new_id

        scene_dict: dict[str, Any] = {
            "id": scene_id,
            "number": global_scene_n,
            "heading": {
                "int_ext": s.heading.int_ext,
                "location_id": loc_id,
                "time_of_day": s.heading.time_of_day,
            },
        }
        if s.summary and s.summary.strip():
            scene_dict["summary"] = s.summary.strip()[:300]
        present_ids = _map_characters_present(
            s.characters_present_names, char_id_map,
            f"scenes[{in_idx}].characters_present", warnings,
        )
        if present_ids:
            scene_dict["characters_present"] = present_ids
        if s.paragraph_range:
            scene_dict["source"] = {
                "chapter": s.chapter_number,
                "paragraph_range": list(s.paragraph_range),
            }
        if s.transition_to_next and s.transition_to_next.strip():
            scene_dict["transition_to_next"] = s.transition_to_next.strip()
        if s.fidelity and isinstance(s.fidelity, dict) and s.fidelity.get("level"):
            scene_dict["fidelity"] = _sanitize_fidelity(s.fidelity)
        # elements 放最后(可读性最高)
        scene_dict["elements"] = confirmed_elements

        scenes_section.append(scene_dict)

    return scenes_section, scene_id_map, element_id_lookup


def _sanitize_fidelity(fid: dict) -> dict:
    """裁剪 fidelity 字段对齐 schema(防止超长 / 多余键)。"""
    out: dict[str, Any] = {"level": fid["level"]}
    if "score" in fid:
        try:
            out["score"] = max(0.0, min(1.0, float(fid["score"])))
        except (TypeError, ValueError):
            pass
    if isinstance(fid.get("reason"), str) and fid["reason"]:
        out["reason"] = fid["reason"][:200]
    if isinstance(fid.get("issues"), list):
        out["issues"] = [
            str(i)[:200] for i in fid["issues"] if i
        ]
    if isinstance(fid.get("dimensions"), list):
        dims: list[dict] = []
        for d in fid["dimensions"]:
            if not isinstance(d, dict):
                continue
            name = d.get("name")
            score = d.get("score")
            if not isinstance(name, str) or not isinstance(score, (int, float)):
                continue
            entry: dict[str, Any] = {
                "name": name[:50],
                "score": max(0.0, min(1.0, float(score))),
            }
            if isinstance(d.get("reason"), str) and d["reason"]:
                entry["reason"] = d["reason"][:200]
            dims.append(entry)
        if dims:
            out["dimensions"] = dims
    return out


def _reorder_element_keys(partial: dict) -> dict:
    """把 id 提到最前(可读性),保持其他键的相对顺序。"""
    order = ["type", "id", "character_id", "parenthetical", "text"]
    out: dict[str, Any] = {}
    for k in order:
        if k in partial:
            out[k] = partial[k]
    for k, v in partial.items():
        if k not in out:
            out[k] = v
    return out


def _build_element_no_id(
    el: ScreenplayElement,
    char_id_map: dict[str, str],
    path: str,
    warnings: list[ComposeWarning],
) -> dict | None:
    """ScreenplayElement → yaml dict(不含 id),失败返 None + 记 warning。"""
    etype = (el.type or "").strip().lower()
    text = (el.text or "").strip()
    if not text:
        warnings.append(ComposeWarning(
            layer="element", path=path,
            message=f"{etype or '?'} text 为空,跳过",
        ))
        return None

    if etype == "action":
        return {"type": "action", "text": text}

    if etype == "parenthetical":
        return {"type": "parenthetical", "text": text}

    if etype == "dialogue":
        cid = char_id_map.get((el.character_name or "").strip())
        if not cid:
            warnings.append(ComposeWarning(
                layer="element", path=path,
                message=f"dialogue 角色 {el.character_name!r} 未在 characters 中,跳过",
            ))
            return None
        out: dict[str, Any] = {
            "type": "dialogue",
            "character_id": cid,
            "text": text,
        }
        if el.parenthetical and el.parenthetical.strip():
            out["parenthetical"] = el.parenthetical.strip()[:100]
        return out

    if etype == "voiceover":
        cid = char_id_map.get((el.character_name or "").strip())
        if not cid:
            warnings.append(ComposeWarning(
                layer="element", path=path,
                message=f"voiceover 角色 {el.character_name!r} 未在 characters 中,跳过",
            ))
            return None
        return {
            "type": "voiceover",
            "character_id": cid,
            "text": text,
        }

    warnings.append(ComposeWarning(
        layer="element", path=path,
        message=f"未知 element 类型 {etype!r},跳过",
    ))
    return None


def _map_characters_present(
    names: list[str],
    char_id_map: dict[str, str],
    path: str,
    warnings: list[ComposeWarning],
) -> list[str]:
    """把 name 列表转 char_id 列表(去重 + 跳过未匹配)。"""
    out: list[str] = []
    seen: set[str] = set()
    for n in names or []:
        if not isinstance(n, str):
            continue
        n_clean = n.strip()
        if not n_clean:
            continue
        cid = char_id_map.get(n_clean)
        if not cid:
            warnings.append(ComposeWarning(
                layer="character", path=path,
                message=f"characters_present 中 {n_clean!r} 未在 characters 段,跳过",
            ))
            continue
        if cid in seen:
            continue
        out.append(cid)
        seen.add(cid)
    return out


# ============================================================
# adaptation_decisions 段
# ============================================================


def _build_decisions(
    scenes_in: list[SceneAssembleData],
    scene_id_map: dict[int, str],
    element_id_lookup: dict[tuple[int, int], str],
    warnings: list[ComposeWarning],
) -> list[dict]:
    """构建 adaptation_decisions 段 — 绑 scene_id + element_id。

    PR#9 输出的 decision.element_index 是 scene 内 elements 数组的 0-based 下标。
    composer 把它通过 element_id_lookup 转成 el_NNN_MMM 形式的 element_id。
    """
    section: list[dict] = []
    counter = 0

    for in_idx, s in enumerate(scenes_in):
        scene_id = scene_id_map.get(in_idx)
        if not scene_id:
            if s.decisions:
                warnings.append(ComposeWarning(
                    layer="decision",
                    path=f"scenes[{in_idx}].decisions",
                    message="本场已跳过,关联的 decisions 一并跳过",
                ))
            continue

        for dec in s.decisions:
            el_id = element_id_lookup.get((in_idx, dec.element_index))
            if not el_id:
                warnings.append(ComposeWarning(
                    layer="decision",
                    path=f"scenes[{in_idx}].decisions[el_idx={dec.element_index}]",
                    message="关联的 element 已被过滤,decision 跳过",
                ))
                continue
            counter += 1
            options_out: list[dict] = []
            for opt in dec.options:
                opt_dict: dict[str, Any] = {"type": opt.type}
                if opt.type in ("voiceover", "action_externalize"):
                    if opt.text:
                        opt_dict["text"] = opt.text
                    if opt.pros:
                        opt_dict["pros"] = opt.pros[:200]
                    if opt.cons:
                        opt_dict["cons"] = opt.cons[:200]
                elif opt.type == "delete":
                    if opt.rationale:
                        opt_dict["rationale"] = opt.rationale[:200]
                options_out.append(opt_dict)
            section.append({
                "id": _make_decision_id(counter),
                "scene_id": scene_id,
                "element_id": el_id,
                "original_text": dec.original_text or "(无原文)",
                "options": options_out,
            })

    return section


# ============================================================
# meta + 序列化
# ============================================================


def _build_meta(compose_input: ComposeInput, stats: dict) -> dict:
    """构建 meta 段(对齐 schema)。"""
    title = (compose_input.novel_title or "").strip()[:100] or "未命名剧本"

    meta: dict[str, Any] = {
        "schema_version": compose_input.schema_version,
        "title": title,
        "generated_by": {
            "platform": compose_input.platform_version,
            "schema_version": compose_input.schema_version,
            "generated_at": _utc_now_iso(),
        },
        "stats": stats,
    }
    if compose_input.model_name:
        meta["generated_by"]["model"] = compose_input.model_name

    source_info: dict[str, Any] = {"novel_title": title}
    if compose_input.adapted_from_chapters:
        source_info["adapted_from_chapters"] = sorted(set(compose_input.adapted_from_chapters))
    meta["source"] = source_info

    return meta


def _utc_now_iso() -> str:
    """UTC ISO 8601 字符串。测试可 monkeypatch 这个函数。"""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _serialize_to_yaml(yaml_dict: dict) -> str:
    """yaml.safe_dump:保留中文 + 不排序键 + block 风格。"""
    return yaml.safe_dump(
        yaml_dict,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
        width=120,
    )


def _estimate_pages(scenes_section: list[dict]) -> int:
    """粗算页数 — 行业经验:1 页 ≈ 1 分钟 ≈ 约 25 行;1 元素 ≈ 1-2 行。"""
    total_lines = sum(len(s.get("elements", [])) for s in scenes_section)
    return max(1, round(total_lines / 25))
