"""剧本 YAML 校验器测试 — PR#2 核心。

测试矩阵:
  1. 合法 YAML 通过双层校验
  2. YAML 解析失败 → yaml_parse 错
  3. 缺少必填字段 → schema 错
  4. 枚举越界 → schema 错
  5. 正则不匹配(id 格式错)→ schema 错
  6. 引用不存在的 character_id → reference 错
  7. 引用不存在的 location_id → reference 错
  8. 重复的 scene_id → reference 错
  9. 改编决策引用不存在的 element → reference 错
  10. 直接给 dict(跳过 yaml 解析)路径
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.services.yaml_validator import (
    validate_screenplay_dict,
    validate_screenplay_yaml,
)


FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def valid_yaml_text() -> str:
    return (FIXTURES_DIR / "valid_screenplay.yaml").read_text(encoding="utf-8")


# ============================================================
# 通过路径
# ============================================================

def test_valid_yaml_passes(valid_yaml_text):
    """完整合法 YAML 应通过双层校验"""
    r = validate_screenplay_yaml(valid_yaml_text)
    assert r.valid is True, f"应通过,但有 errors: {[i.message for i in r.errors()]}"
    assert r.parsed is not None
    assert r.parsed["meta"]["title"] == "孤独的钟表匠"
    assert len(r.parsed["scenes"]) == 2


def test_validate_dict_direct(valid_yaml_text):
    """validate_screenplay_dict 跳过 YAML 解析直接吃 dict"""
    import yaml
    parsed = yaml.safe_load(valid_yaml_text)
    r = validate_screenplay_dict(parsed)
    assert r.valid is True


# ============================================================
# YAML 解析失败
# ============================================================

def test_invalid_yaml_syntax():
    """YAML 语法错 → yaml_parse 层"""
    bad = "meta:\n  title: hello\n - unbalanced"
    r = validate_screenplay_yaml(bad)
    assert r.valid is False
    assert any(i.layer == "yaml_parse" for i in r.errors())


def test_yaml_root_not_dict():
    """根是 list 不是 dict → yaml_parse 错"""
    bad = "- a\n- b\n- c"
    r = validate_screenplay_yaml(bad)
    assert r.valid is False
    assert any(i.layer == "yaml_parse" for i in r.errors())


# ============================================================
# Schema 层错误
# ============================================================

def test_missing_required_meta():
    """缺 meta → schema 错"""
    bad = """
characters:
  - id: char_001
    name: A
locations:
  - id: loc_001
    name: B
    int_ext: INT
scenes:
  - id: scene_001
    number: 1
    heading:
      int_ext: INT
      location_id: loc_001
      time_of_day: 日
    elements:
      - type: action
        id: el_001_001
        text: x
"""
    r = validate_screenplay_yaml(bad)
    assert r.valid is False
    assert any(i.layer == "schema" and "meta" in i.message for i in r.errors())


def test_invalid_enum_value():
    """time_of_day 不在枚举里 → schema 错"""
    bad_dict = {
        "meta": {
            "schema_version": "1.0",
            "title": "T",
            "generated_by": {"platform": "P"},
        },
        "characters": [{"id": "char_001", "name": "A"}],
        "locations": [{"id": "loc_001", "name": "B", "int_ext": "INT"}],
        "scenes": [{
            "id": "scene_001",
            "number": 1,
            "heading": {
                "int_ext": "INT",
                "location_id": "loc_001",
                "time_of_day": "黄昏微雨",     # ✗ 不在枚举
            },
            "elements": [{"type": "action", "id": "el_001_001", "text": "x"}],
        }],
    }
    r = validate_screenplay_dict(bad_dict)
    assert r.valid is False
    msgs = " ".join(i.message for i in r.errors())
    assert "枚举" in msgs or "enum" in msgs


def test_invalid_id_format():
    """character id 不符合正则 → schema 错"""
    bad_dict = {
        "meta": {
            "schema_version": "1.0",
            "title": "T",
            "generated_by": {"platform": "P"},
        },
        "characters": [{"id": "林深", "name": "A"}],   # ✗ 应该是 char_NNN
        "locations": [{"id": "loc_001", "name": "B", "int_ext": "INT"}],
        "scenes": [{
            "id": "scene_001",
            "number": 1,
            "heading": {
                "int_ext": "INT",
                "location_id": "loc_001",
                "time_of_day": "日",
            },
            "elements": [{"type": "action", "id": "el_001_001", "text": "x"}],
        }],
    }
    r = validate_screenplay_dict(bad_dict)
    assert r.valid is False
    assert any("正则" in i.message or "pattern" in i.message for i in r.errors())


# ============================================================
# 引用层错误
# ============================================================

def test_reference_unknown_character_id():
    """对白引用不存在的 char_id → reference 错"""
    bad_dict = {
        "meta": {
            "schema_version": "1.0",
            "title": "T",
            "generated_by": {"platform": "P"},
        },
        "characters": [{"id": "char_001", "name": "A"}],
        "locations": [{"id": "loc_001", "name": "B", "int_ext": "INT"}],
        "scenes": [{
            "id": "scene_001",
            "number": 1,
            "heading": {
                "int_ext": "INT",
                "location_id": "loc_001",
                "time_of_day": "日",
            },
            "elements": [
                {
                    "type": "dialogue",
                    "id": "el_001_001",
                    "character_id": "char_999",   # ✗ 不存在
                    "text": "你好",
                },
            ],
        }],
    }
    r = validate_screenplay_dict(bad_dict)
    assert r.valid is False
    assert any(i.layer == "reference" and "char_999" in i.message for i in r.errors())


def test_reference_unknown_location_id():
    """heading 引用不存在的 loc_id → reference 错"""
    bad_dict = {
        "meta": {
            "schema_version": "1.0",
            "title": "T",
            "generated_by": {"platform": "P"},
        },
        "characters": [{"id": "char_001", "name": "A"}],
        "locations": [{"id": "loc_001", "name": "B", "int_ext": "INT"}],
        "scenes": [{
            "id": "scene_001",
            "number": 1,
            "heading": {
                "int_ext": "INT",
                "location_id": "loc_888",        # ✗ 不存在
                "time_of_day": "日",
            },
            "elements": [{"type": "action", "id": "el_001_001", "text": "x"}],
        }],
    }
    r = validate_screenplay_dict(bad_dict)
    assert r.valid is False
    assert any(i.layer == "reference" and "loc_888" in i.message for i in r.errors())


def test_duplicate_scene_id():
    """重复的 scene_id → reference 错"""
    bad_dict = {
        "meta": {
            "schema_version": "1.0",
            "title": "T",
            "generated_by": {"platform": "P"},
        },
        "characters": [{"id": "char_001", "name": "A"}],
        "locations": [{"id": "loc_001", "name": "B", "int_ext": "INT"}],
        "scenes": [
            {
                "id": "scene_001",
                "number": 1,
                "heading": {"int_ext": "INT", "location_id": "loc_001", "time_of_day": "日"},
                "elements": [{"type": "action", "id": "el_001_001", "text": "x"}],
            },
            {
                "id": "scene_001",   # ✗ 重复
                "number": 2,
                "heading": {"int_ext": "INT", "location_id": "loc_001", "time_of_day": "夜"},
                "elements": [{"type": "action", "id": "el_002_001", "text": "y"}],
            },
        ],
    }
    r = validate_screenplay_dict(bad_dict)
    assert r.valid is False
    assert any(i.layer == "reference" and "重复" in i.message for i in r.errors())


def test_adaptation_decision_unknown_element():
    """改编决策引用不存在的 element_id → reference 错"""
    bad_dict = {
        "meta": {
            "schema_version": "1.0",
            "title": "T",
            "generated_by": {"platform": "P"},
        },
        "characters": [{"id": "char_001", "name": "A"}],
        "locations": [{"id": "loc_001", "name": "B", "int_ext": "INT"}],
        "scenes": [{
            "id": "scene_001",
            "number": 1,
            "heading": {"int_ext": "INT", "location_id": "loc_001", "time_of_day": "日"},
            "elements": [{"type": "action", "id": "el_001_001", "text": "x"}],
        }],
        "adaptation_decisions": [{
            "id": "dec_001",
            "scene_id": "scene_001",
            "element_id": "el_001_999",       # ✗ 不存在
            "options": [{"type": "voiceover", "text": "..."}],
        }],
    }
    r = validate_screenplay_dict(bad_dict)
    assert r.valid is False
    assert any(i.layer == "reference" and "el_001_999" in i.message for i in r.errors())


# ============================================================
# 结果对象 helper
# ============================================================

def test_result_to_dict_structure(valid_yaml_text):
    """ValidationResult.to_dict 给前端用 — 验证结构"""
    r = validate_screenplay_yaml(valid_yaml_text)
    d = r.to_dict()
    assert "valid" in d
    assert "issue_count" in d
    assert "error_count" in d
    assert "warning_count" in d
    assert "issues" in d


def test_errors_and_warnings_split():
    """ValidationResult.errors() / warnings() 分流"""
    bad = "not a valid yaml at all just [["
    r = validate_screenplay_yaml(bad)
    assert len(r.errors()) >= 1
    assert all(i.severity == "error" for i in r.errors())
