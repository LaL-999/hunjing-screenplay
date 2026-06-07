"""screenplay_exporter 测试 — PR#17。

测试 3 种格式导出的核心行为。
"""
from __future__ import annotations

from app.services.screenplay_exporter import (
    export_to_fountain,
    export_to_txt,
    make_export_filename,
)


def _fixture_screenplay() -> dict:
    """构造一份简化但完整的 screenplay dict。"""
    return {
        "meta": {
            "title": "麦田里的守望者",
            "generated_by": {
                "platform": "hunjing-screenplay@0.1.0",
                "generated_at": "2026-06-07T10:00:00Z",
            },
            "source": {"novel_title": "麦田里的守望者-塞林格"},
        },
        "characters": [
            {"id": "char_001", "name": "霍尔顿", "description": "17 岁少年"},
            {"id": "char_002", "name": "斯宾塞", "description": "历史老师"},
        ],
        "locations": [
            {"id": "loc_001", "name": "潘西中学", "int_ext": "INT"},
            {"id": "loc_002", "name": "汤姆孙山", "int_ext": "EXT"},
        ],
        "scenes": [
            {
                "id": "scene_001",
                "number": 1,
                "heading": {
                    "int_ext": "EXT",
                    "location_id": "loc_002",
                    "time_of_day": "日",
                },
                "summary": "霍尔顿在山顶告别潘西",
                "elements": [
                    {
                        "type": "action",
                        "id": "el_001_001",
                        "text": "霍尔顿站在汤姆孙山顶,凝视远方。",
                    },
                    {
                        "type": "voiceover",
                        "id": "el_001_002",
                        "character_id": "char_001",
                        "text": "你要是真想听我讲...",
                        "voice_source": "VO",
                    },
                ],
                "transition_to_next": "CUT_TO",
            },
            {
                "id": "scene_002",
                "number": 2,
                "heading": {
                    "int_ext": "INT",
                    "location_id": "loc_001",
                    "time_of_day": "日",
                },
                "elements": [
                    {
                        "type": "dialogue",
                        "id": "el_002_001",
                        "character_id": "char_002",
                        "text": "进来吧,孩子。",
                        "parenthetical": "(温和地)",
                    },
                    {
                        "type": "voiceover",
                        "id": "el_002_002",
                        "character_id": "char_002",
                        "text": "你父亲会非常失望。",
                        "voice_source": "OS",
                    },
                ],
            },
        ],
    }


# ============================================================
# Fountain
# ============================================================


def test_fountain_has_title_page():
    out = export_to_fountain(_fixture_screenplay())
    assert "Title: 麦田里的守望者" in out
    assert "Credit: 改编自小说" in out


def test_fountain_scene_heading_format():
    """场号头应该是 EXT. 地点 - 时段 的 Fountain 格式。"""
    out = export_to_fountain(_fixture_screenplay())
    assert "EXT. 汤姆孙山 - 日" in out
    assert "INT. 潘西中学 - 日" in out


def test_fountain_vo_tag():
    """voice_source=VO → (V.O.) ; OS → (O.S.)"""
    out = export_to_fountain(_fixture_screenplay())
    assert "霍尔顿 (V.O.)" in out
    assert "斯宾塞 (O.S.)" in out


def test_fountain_parenthetical_unwrapped():
    """parenthetical 不重复外括号(去掉外面的再加一层)。"""
    out = export_to_fountain(_fixture_screenplay())
    # 输入 "(温和地)" 应该输出 "(温和地)" 而不是 "((温和地))"
    assert "(温和地)" in out
    assert "((温和地))" not in out


def test_fountain_transition_format():
    """transition_to_next=CUT_TO → > CUT TO:"""
    out = export_to_fountain(_fixture_screenplay())
    assert "> CUT TO:" in out


def test_fountain_character_uppercase():
    """角色名在 fountain 中必须大写。"""
    out = export_to_fountain(_fixture_screenplay())
    # 中文不变(中文没有大小写),但应该出现"霍尔顿"作为独立行
    lines = [l.strip() for l in out.split("\n")]
    assert any(l.startswith("霍尔顿") for l in lines)


# ============================================================
# TXT
# ============================================================


def test_txt_has_title_block():
    out = export_to_txt(_fixture_screenplay())
    assert "《麦田里的守望者》" in out
    assert "改编自" in out


def test_txt_scene_marker():
    out = export_to_txt(_fixture_screenplay())
    assert "【SCENE 001】" in out
    assert "【SCENE 002】" in out


def test_txt_includes_character_list():
    out = export_to_txt(_fixture_screenplay())
    assert "【角色】" in out
    assert "霍尔顿" in out
    assert "斯宾塞" in out


def test_txt_includes_summary():
    out = export_to_txt(_fixture_screenplay())
    assert "霍尔顿在山顶告别潘西" in out


def test_txt_ends_with_signature():
    out = export_to_txt(_fixture_screenplay())
    assert "— 剧本结束 —" in out
    assert "浑晶 · 剧创态" in out


# ============================================================
# 文件名
# ============================================================


def test_filename_uses_title():
    sp = _fixture_screenplay()
    assert make_export_filename(sp, "fountain") == "麦田里的守望者.fountain"
    assert make_export_filename(sp, "txt") == "麦田里的守望者.txt"
    assert make_export_filename(sp, "yaml") == "麦田里的守望者.yaml"


def test_filename_strips_illegal_chars():
    sp = {"meta": {"title": "测试:剧本/版本*1"}}
    name = make_export_filename(sp, "fountain")
    assert "/" not in name
    assert ":" not in name
    assert "*" not in name


def test_filename_fallback_when_no_title():
    sp = {}
    assert make_export_filename(sp, "txt").startswith("screenplay")


# ============================================================
# 边界
# ============================================================


def test_empty_screenplay_does_not_crash():
    """完全空的 dict 也不能崩。"""
    out = export_to_fountain({})
    assert isinstance(out, str)
    out_txt = export_to_txt({})
    assert isinstance(out_txt, str)


def test_scene_without_elements():
    """空 elements 的 scene 也要正确处理。"""
    sp = {
        "meta": {"title": "test"},
        "characters": [{"id": "char_001", "name": "甲"}],
        "locations": [{"id": "loc_001", "name": "客厅"}],
        "scenes": [
            {
                "id": "scene_001",
                "heading": {"int_ext": "INT", "location_id": "loc_001", "time_of_day": "日"},
                "elements": [],
            },
        ],
    }
    out = export_to_fountain(sp)
    assert "INT. 客厅 - 日" in out
