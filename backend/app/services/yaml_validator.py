"""剧本 YAML 校验器 — 结构 + 引用完整性 双层校验。

校验链:
  Layer A — Schema 层:用 jsonschema 库按 docs/SCHEMA_DESIGN.md 定义的
            screenplay.json 严格校验(字段类型 / 枚举 / 正则 / 必填)
  Layer B — 引用层:character_id / location_id 必须在对应数组里能找到,
            scene_id / element_id 唯一。这层 JSON Schema 不易表达,自己写。

每层校验都返回**人类可读**的错误列表(场号 + 元素 ID + 问题描述),
方便 LLM 自动修复重试(见 PR#10 失败重试流程)。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError


# ============================================================
# Schema 加载(模块级缓存)
# ============================================================

_SCHEMA_PATH = Path(__file__).parent.parent / "schemas" / "screenplay.json"
_SCHEMA: dict | None = None
_VALIDATOR: Draft202012Validator | None = None


def _get_validator() -> Draft202012Validator:
    """惰性加载 + 缓存。"""
    global _SCHEMA, _VALIDATOR
    if _VALIDATOR is None:
        if not _SCHEMA_PATH.exists():
            raise FileNotFoundError(
                f"JSON Schema not found at {_SCHEMA_PATH}"
            )
        with _SCHEMA_PATH.open("r", encoding="utf-8") as f:
            _SCHEMA = json.load(f)
        _VALIDATOR = Draft202012Validator(_SCHEMA)
    return _VALIDATOR


# ============================================================
# 校验结果
# ============================================================

@dataclass
class ValidationIssue:
    """单条校验问题 — 人类可读。"""
    layer: str                     # "schema" | "reference" | "yaml_parse"
    path: str                      # JSON Pointer 风格,如 "scenes[0].heading.location_id"
    message: str                   # 一句话说明
    severity: str = "error"        # error | warning


@dataclass
class ValidationResult:
    """校验结果汇总。"""
    valid: bool
    issues: list[ValidationIssue] = field(default_factory=list)
    parsed: dict | None = None     # 校验通过时附 parsed dict,失败时 None

    def add(self, layer: str, path: str, message: str, severity: str = "error") -> None:
        self.issues.append(ValidationIssue(layer, path, message, severity))
        if severity == "error":
            self.valid = False

    def errors(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == "error"]

    def warnings(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == "warning"]

    def to_dict(self) -> dict:
        return {
            "valid": self.valid,
            "issue_count": len(self.issues),
            "error_count": len(self.errors()),
            "warning_count": len(self.warnings()),
            "issues": [
                {
                    "layer": i.layer,
                    "path": i.path,
                    "message": i.message,
                    "severity": i.severity,
                }
                for i in self.issues
            ],
        }


# ============================================================
# 主入口
# ============================================================

def validate_screenplay_yaml(yaml_text: str) -> ValidationResult:
    """校验一份剧本 YAML(文本形式)。

    流程:
      1. YAML 解析 → dict
      2. Layer A:JSON Schema 校验
      3. Layer B:引用完整性校验
      4. 汇总返回
    """
    result = ValidationResult(valid=True)

    # 1. YAML 解析
    try:
        parsed = yaml.safe_load(yaml_text)
    except yaml.YAMLError as e:
        result.add(
            "yaml_parse",
            "/",
            f"YAML 解析失败:{e}",
        )
        return result

    if not isinstance(parsed, dict):
        result.add(
            "yaml_parse",
            "/",
            f"YAML 根节点必须是对象(dict),实际是 {type(parsed).__name__}",
        )
        return result

    # 2. Layer A:JSON Schema 校验
    validator = _get_validator()
    schema_errors = sorted(validator.iter_errors(parsed), key=lambda e: e.path)
    for err in schema_errors:
        result.add(
            "schema",
            _path_to_str(err.path) or "/",
            _humanize_schema_error(err),
        )

    # Schema 错时不再做 Layer B(数据结构本身就错了)
    if not result.valid:
        return result

    # 3. Layer B:引用完整性校验
    _validate_references(parsed, result)

    # 4. 通过 → 附 parsed dict
    if result.valid:
        result.parsed = parsed

    return result


def validate_screenplay_dict(parsed: dict) -> ValidationResult:
    """直接给 dict 校验(跳过 YAML 解析步骤,LLM 直接输出 dict 时用)。"""
    result = ValidationResult(valid=True)

    if not isinstance(parsed, dict):
        result.add(
            "yaml_parse",
            "/",
            f"输入必须是 dict,实际是 {type(parsed).__name__}",
        )
        return result

    validator = _get_validator()
    schema_errors = sorted(validator.iter_errors(parsed), key=lambda e: e.path)
    for err in schema_errors:
        result.add(
            "schema",
            _path_to_str(err.path) or "/",
            _humanize_schema_error(err),
        )

    if not result.valid:
        return result

    _validate_references(parsed, result)

    if result.valid:
        result.parsed = parsed

    return result


# ============================================================
# Layer B — 引用完整性
# ============================================================

def _validate_references(parsed: dict, result: ValidationResult) -> None:
    """检查 character_id / location_id 等跨节点引用是否有效。"""
    characters = parsed.get("characters", [])
    locations = parsed.get("locations", [])
    scenes = parsed.get("scenes", [])

    char_ids = {c["id"] for c in characters if isinstance(c, dict) and "id" in c}
    loc_ids = {l["id"] for l in locations if isinstance(l, dict) and "id" in l}

    # 检查 scene 唯一性
    seen_scene_ids: set[str] = set()
    seen_scene_numbers: set[int] = set()
    seen_element_ids: set[str] = set()

    for s_idx, scene in enumerate(scenes):
        if not isinstance(scene, dict):
            continue

        sid = scene.get("id")
        if sid in seen_scene_ids:
            result.add(
                "reference",
                f"scenes[{s_idx}].id",
                f"重复的 scene_id:{sid}",
            )
        else:
            if sid:
                seen_scene_ids.add(sid)

        # scene 序号唯一
        snum = scene.get("number")
        if isinstance(snum, int):
            if snum in seen_scene_numbers:
                result.add(
                    "reference",
                    f"scenes[{s_idx}].number",
                    f"重复的 scene number:{snum}",
                )
            else:
                seen_scene_numbers.add(snum)

        # heading.location_id 必须存在
        heading = scene.get("heading", {})
        loc_id = heading.get("location_id") if isinstance(heading, dict) else None
        if loc_id and loc_id not in loc_ids:
            result.add(
                "reference",
                f"scenes[{s_idx}].heading.location_id",
                f"引用了不存在的 location_id:{loc_id}",
            )

        # characters_present 必须都在
        for c_idx, cid in enumerate(scene.get("characters_present") or []):
            if cid not in char_ids:
                result.add(
                    "reference",
                    f"scenes[{s_idx}].characters_present[{c_idx}]",
                    f"引用了不存在的 character_id:{cid}",
                )

        # 遍历 elements
        for e_idx, elem in enumerate(scene.get("elements") or []):
            if not isinstance(elem, dict):
                continue

            eid = elem.get("id")
            if eid in seen_element_ids:
                result.add(
                    "reference",
                    f"scenes[{s_idx}].elements[{e_idx}].id",
                    f"重复的 element_id:{eid}",
                )
            elif eid:
                seen_element_ids.add(eid)

            # dialogue / voiceover 的 character_id 必须存在
            etype = elem.get("type")
            if etype in ("dialogue", "voiceover"):
                cid = elem.get("character_id")
                if cid and cid not in char_ids:
                    result.add(
                        "reference",
                        f"scenes[{s_idx}].elements[{e_idx}].character_id",
                        f"对白 / 旁白引用了不存在的 character_id:{cid}",
                    )

    # adaptation_decisions 内的引用
    decisions = parsed.get("adaptation_decisions") or []
    for d_idx, dec in enumerate(decisions):
        if not isinstance(dec, dict):
            continue
        sid = dec.get("scene_id")
        if sid and sid not in seen_scene_ids:
            result.add(
                "reference",
                f"adaptation_decisions[{d_idx}].scene_id",
                f"改编决策引用了不存在的 scene_id:{sid}",
            )
        eid = dec.get("element_id")
        if eid and eid not in seen_element_ids:
            result.add(
                "reference",
                f"adaptation_decisions[{d_idx}].element_id",
                f"改编决策引用了不存在的 element_id:{eid}",
            )


# ============================================================
# 辅助 — 美化 schema 错误消息
# ============================================================

def _path_to_str(path) -> str:
    """deque[str|int] → 'scenes[0].heading.location_id' 风格"""
    parts: list[str] = []
    for p in path:
        if isinstance(p, int):
            if parts:
                parts[-1] = f"{parts[-1]}[{p}]"
            else:
                parts.append(f"[{p}]")
        else:
            parts.append(str(p))
    return ".".join(parts)


def _humanize_schema_error(err: ValidationError) -> str:
    """jsonschema 的英文错误转中文友好提示。"""
    msg = err.message

    # 常见错误模式转译
    if err.validator == "required":
        missing = err.message.split("'")[1] if "'" in err.message else "?"
        return f"缺少必填字段:{missing}"
    if err.validator == "enum":
        return f"取值 {err.instance!r} 不在允许的枚举里:{err.schema.get('enum')}"
    if err.validator == "pattern":
        return f"取值 {err.instance!r} 不符合正则模式 {err.schema.get('pattern')}"
    if err.validator == "type":
        return f"类型错误:期望 {err.schema.get('type')},实际 {type(err.instance).__name__}"
    if err.validator == "minLength":
        return f"字符串太短:期望至少 {err.schema.get('minLength')} 个字符"
    if err.validator == "maxLength":
        return f"字符串太长:期望最多 {err.schema.get('maxLength')} 个字符"
    if err.validator == "minItems":
        return f"数组太短:期望至少 {err.schema.get('minItems')} 项"
    if err.validator == "additionalProperties":
        return f"出现了未定义的字段(schema 禁止额外属性)"

    return msg
