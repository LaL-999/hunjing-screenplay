"""剧本导出服务 — PR#17。

把内部 YAML 剧本 → 行业标准格式(给作者真正可用的文件):

| 格式 | 适用场景 |
|---|---|
| Fountain (.fountain) | 行业标准。Final Draft / WriterDuet / Highland 等专业软件可导入。 |
| TXT (.txt)          | 纯文本简洁排版。发微信 / 打印 / 跟搭档对稿。 |
| YAML (.yaml)        | 原始结构化数据。给工具链 / 二次开发 / 版本管理用。 |

Fountain 规范参考:https://fountain.io/syntax
"""
from __future__ import annotations

import logging
from io import StringIO

logger = logging.getLogger(__name__)


# ============================================================
# 公共辅助
# ============================================================


def _build_id_to_name(characters: list, locations: list) -> tuple[dict, dict]:
    """从 yaml dict 抽 id → name 映射(角色 + 地点)。"""
    char_map: dict[str, str] = {}
    loc_map: dict[str, str] = {}
    if isinstance(characters, list):
        for c in characters:
            if isinstance(c, dict) and c.get("id") and c.get("name"):
                char_map[c["id"]] = c["name"]
    if isinstance(locations, list):
        for l in locations:
            if isinstance(l, dict) and l.get("id") and l.get("name"):
                loc_map[l["id"]] = l["name"]
    return char_map, loc_map


# ============================================================
# Fountain 导出 — 行业标准
# ============================================================


def export_to_fountain(screenplay: dict) -> str:
    """把 screenplay dict 转 Fountain 格式纯文本。

    Fountain 语法关键点:
      - Title Page:Key: Value 段(开头)+ 空行
      - Scene Heading:大写,以 INT. / EXT. 等开头(我们直接用)
      - Action:默认就是 action,纯段落
      - Character:大写一行,前后必须空行
      - Parenthetical:(xxx) 在 character 和 dialogue 之间
      - Dialogue:紧跟 character 下方,不空行
      - Voice-Over / O.S.:character 行追加 (V.O.) / (O.S.)
      - Transition:大写 + 以 TO: 结尾,右对齐(Final Draft 自动识别)
    """
    out = StringIO()
    meta = screenplay.get("meta") or {}
    characters = screenplay.get("characters") or []
    locations = screenplay.get("locations") or []
    scenes = screenplay.get("scenes") or []

    char_map, loc_map = _build_id_to_name(characters, locations)

    # === Title Page ===
    title = (meta.get("title") or "未命名剧本").strip()
    out.write(f"Title: {title}\n")
    out.write("Credit: 改编自小说\n")
    source = meta.get("source") or {}
    if isinstance(source, dict):
        novel = source.get("novel_title", "").strip()
        if novel:
            out.write(f"Source: {novel}\n")
    generated_by = meta.get("generated_by") or {}
    if isinstance(generated_by, dict):
        platform = generated_by.get("platform", "").strip()
        if platform:
            out.write(f"Draft date: {generated_by.get('generated_at', '')}\n")
            out.write(f"Notes: 由 {platform} 自动生成,作者人工打磨\n")
    out.write("\n\n")   # Title Page 与正文之间必须空 2 行

    # === Scenes ===
    for scene in scenes:
        if not isinstance(scene, dict):
            continue

        # Scene Heading
        heading = scene.get("heading") or {}
        if not isinstance(heading, dict):
            continue
        int_ext = (heading.get("int_ext") or "INT").upper()
        loc_id = heading.get("location_id", "")
        loc_name = loc_map.get(loc_id, "未命名")
        time_of_day = heading.get("time_of_day") or "日"
        # Fountain 推荐 INT./EXT. 后面 - 时段
        out.write(f"{int_ext}. {loc_name} - {time_of_day}\n\n")

        # 可选:本场概要作为隐藏注释(Boneyard)
        summary = (scene.get("summary") or "").strip()
        if summary:
            out.write(f"[[ {summary} ]]\n\n")

        # Elements
        elements = scene.get("elements") or []
        prev_type: str | None = None
        for el in elements:
            if not isinstance(el, dict):
                continue
            etype = el.get("type", "")
            text = (el.get("text") or "").strip()
            if not text:
                continue

            if etype == "action":
                out.write(f"{text}\n\n")
                prev_type = "action"

            elif etype in ("dialogue", "voiceover"):
                char_id = el.get("character_id", "")
                char_name = char_map.get(char_id, "未知")
                # voiceover 追加 (V.O.) 或 (O.S.)
                voice_tag = ""
                if etype == "voiceover":
                    vs = el.get("voice_source", "VO")
                    voice_tag = " (V.O.)" if vs != "OS" else " (O.S.)"
                # Character 必须大写 + 前后空行(前一个非空行已经在上一个 element 写了 \n\n)
                out.write(f"{char_name.upper()}{voice_tag}\n")
                # Parenthetical(可选)
                paren = (el.get("parenthetical") or "").strip()
                if paren:
                    # 去掉外面可能已有的括号,统一格式
                    paren_clean = paren.strip("()").strip()
                    out.write(f"({paren_clean})\n")
                # Dialogue
                out.write(f"{text}\n\n")
                prev_type = "dialogue"

            elif etype == "parenthetical":
                # 独立的 parenthetical → 转为 action 处理(剧本里这种少见)
                out.write(f"({text.strip('()')})\n\n")
                prev_type = "parenthetical"

        # Transition
        trans = (scene.get("transition_to_next") or "").strip()
        if trans:
            # CUT_TO → CUT TO:(Fountain 标准是空格 + 冒号)
            trans_display = trans.replace("_", " ").upper()
            if not trans_display.endswith(":"):
                trans_display += ":"
            out.write(f"> {trans_display}\n\n")

    return out.getvalue()


# ============================================================
# TXT 导出 — 简洁可读
# ============================================================


def export_to_txt(screenplay: dict) -> str:
    """把 screenplay dict 转中文友好的 TXT 排版。

    - 场号头:【SCENE 001】INT. 潘西中学 — 日
    - 角色对白:角色名居中(用前导空格模拟)+ 对白
    - 动作:正常段落
    - 过场:右对齐大写
    """
    out = StringIO()
    meta = screenplay.get("meta") or {}
    characters = screenplay.get("characters") or []
    locations = screenplay.get("locations") or []
    scenes = screenplay.get("scenes") or []

    char_map, loc_map = _build_id_to_name(characters, locations)

    # 标题页
    title = (meta.get("title") or "未命名剧本").strip()
    source = meta.get("source") or {}
    novel = ""
    if isinstance(source, dict):
        novel = source.get("novel_title", "").strip()
    out.write("=" * 60 + "\n")
    out.write(f"《{title}》\n")
    if novel:
        out.write(f"改编自 — {novel}\n")
    out.write("=" * 60 + "\n\n")

    # 角色 / 地点 列表(可选)
    if characters:
        out.write("【角色】\n")
        for c in characters:
            if isinstance(c, dict):
                nm = c.get("name", "")
                desc = c.get("description", "")
                if desc:
                    out.write(f"  · {nm} — {desc}\n")
                else:
                    out.write(f"  · {nm}\n")
        out.write("\n")

    # Scenes
    for i, scene in enumerate(scenes, 1):
        if not isinstance(scene, dict):
            continue
        heading = scene.get("heading") or {}
        if not isinstance(heading, dict):
            continue
        int_ext = (heading.get("int_ext") or "INT").upper()
        loc_id = heading.get("location_id", "")
        loc_name = loc_map.get(loc_id, "未命名")
        time_of_day = heading.get("time_of_day") or "日"

        out.write("-" * 60 + "\n")
        out.write(f"【SCENE {i:03d}】  {int_ext}. {loc_name} — {time_of_day}\n")
        out.write("-" * 60 + "\n\n")

        summary = (scene.get("summary") or "").strip()
        if summary:
            out.write(f"  [本场概要] {summary}\n\n")

        elements = scene.get("elements") or []
        for el in elements:
            if not isinstance(el, dict):
                continue
            etype = el.get("type", "")
            text = (el.get("text") or "").strip()
            if not text:
                continue

            if etype == "action":
                out.write(f"{text}\n\n")

            elif etype in ("dialogue", "voiceover"):
                char_id = el.get("character_id", "")
                char_name = char_map.get(char_id, "未知")
                voice_tag = ""
                if etype == "voiceover":
                    vs = el.get("voice_source", "VO")
                    voice_tag = " (V.O.)" if vs != "OS" else " (O.S.)"
                # 角色名居中(用前导空格模拟,基线 60 字符宽)
                char_line = f"{char_name}{voice_tag}"
                pad = max(0, (60 - len(char_line) * 2) // 2)
                out.write(f"{' ' * pad}{char_line}\n")
                paren = (el.get("parenthetical") or "").strip()
                if paren:
                    paren_clean = paren.strip("()").strip()
                    paren_str = f"({paren_clean})"
                    p_pad = max(0, (60 - len(paren_str) * 2) // 2)
                    out.write(f"{' ' * p_pad}{paren_str}\n")
                out.write(f"    {text}\n\n")

            elif etype == "parenthetical":
                out.write(f"  ({text.strip('()')})\n\n")

        trans = (scene.get("transition_to_next") or "").strip()
        if trans:
            trans_display = trans.replace("_", " ").upper()
            if not trans_display.endswith(":"):
                trans_display += ":"
            # 右对齐(60 字符宽)
            pad = max(0, 60 - len(trans_display))
            out.write(f"{' ' * pad}{trans_display}\n\n")

    out.write("=" * 60 + "\n")
    out.write("— 剧本结束 —\n")
    out.write("=" * 60 + "\n")
    out.write("\n由「浑晶 · 剧创态」自动生成,作者人工打磨。\n")

    return out.getvalue()


# ============================================================
# 文件名建议
# ============================================================


def make_export_filename(screenplay: dict, ext: str) -> str:
    """根据 meta.title 生成下载文件名。
    ext: 'fountain' / 'txt' / 'yaml'
    """
    meta = screenplay.get("meta") or {}
    title = (meta.get("title") or "screenplay").strip()
    # 去掉文件名非法字符
    safe = "".join(c for c in title if c not in r'\/:*?"<>|').strip() or "screenplay"
    return f"{safe}.{ext}"
