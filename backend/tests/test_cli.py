"""CLI 工具测试 — PR#5。

测试矩阵:
  1. 校验合法 YAML 文件 → exit 0 + 文本含"通过"
  2. 校验非法 YAML 文件 → exit 1
  3. 文件不存在 → exit 2 + 错误消息
  4. --json 参数 → 输出 JSON 结构(有 valid/issues 字段)
  5. stdin 输入(path='-') → 同样工作
  6. 无子命令 → 打印帮助 + exit 2
  7. validate 缺路径 → argparse 报错(exit 2)
  8. 校验后 stats 行显示在通过报告里
"""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest


FIXTURES_DIR = Path(__file__).parent / "fixtures"
VALID_YAML = FIXTURES_DIR / "valid_screenplay.yaml"


@pytest.fixture
def invalid_yaml_file(tmp_path: Path) -> Path:
    """造一份故意非法的 YAML 文件:缺 meta 必填字段。"""
    p = tmp_path / "bad.yaml"
    p.write_text(
        "characters:\n  - id: char_001\n    name: A\n",
        encoding="utf-8",
    )
    return p


@pytest.fixture
def parse_error_yaml_file(tmp_path: Path) -> Path:
    """YAML 解析错(语法层)"""
    p = tmp_path / "syntax_error.yaml"
    p.write_text("meta:\n  title: x\n - bad indent", encoding="utf-8")
    return p


# ============================================================
# 路径输入
# ============================================================

def test_validate_valid_file_returns_0(capsys):
    """合法文件 → exit 0 + 通过消息"""
    from app.cli import main
    rc = main(["validate", str(VALID_YAML)])
    captured = capsys.readouterr()
    assert rc == 0
    assert "通过" in captured.out


def test_validate_valid_file_shows_stats(capsys):
    """通过报告应显示标题 / 场次等"""
    from app.cli import main
    main(["validate", str(VALID_YAML)])
    out = capsys.readouterr().out
    assert "标题" in out
    assert "场次" in out


def test_validate_invalid_file_returns_1(capsys, invalid_yaml_file):
    """缺 meta 必填 → exit 1"""
    from app.cli import main
    rc = main(["validate", str(invalid_yaml_file)])
    captured = capsys.readouterr()
    assert rc == 1
    # 报告应含"失败"
    assert "失败" in captured.out


def test_validate_yaml_parse_error_returns_1(capsys, parse_error_yaml_file):
    """YAML 解析错 → exit 1 + 错误层 tag"""
    from app.cli import main
    rc = main(["validate", str(parse_error_yaml_file)])
    captured = capsys.readouterr()
    assert rc == 1


def test_validate_missing_file_returns_2(capsys):
    """文件不存在 → exit 2 + stderr"""
    from app.cli import main
    rc = main(["validate", "/path/that/does/not/exist.yaml"])
    captured = capsys.readouterr()
    assert rc == 2
    assert "不存在" in captured.err


def test_validate_path_is_directory_returns_2(capsys, tmp_path):
    from app.cli import main
    rc = main(["validate", str(tmp_path)])
    captured = capsys.readouterr()
    assert rc == 2


# ============================================================
# JSON 输出
# ============================================================

def test_json_mode_outputs_structured_report(capsys):
    """--json 输出可被 json.loads 解析"""
    from app.cli import main
    main(["validate", str(VALID_YAML), "--json"])
    out = capsys.readouterr().out
    parsed = json.loads(out)
    assert "valid" in parsed
    assert "issue_count" in parsed
    assert "error_count" in parsed
    assert "issues" in parsed
    assert parsed["valid"] is True


def test_json_mode_with_invalid_file(capsys, invalid_yaml_file):
    from app.cli import main
    rc = main(["validate", str(invalid_yaml_file), "--json"])
    assert rc == 1
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["valid"] is False
    assert parsed["error_count"] >= 1


# ============================================================
# stdin
# ============================================================

def test_validate_stdin_input(capsys, monkeypatch):
    """path='-' → 从 stdin 读"""
    valid_text = VALID_YAML.read_text(encoding="utf-8")
    monkeypatch.setattr(sys, "stdin", io.StringIO(valid_text))
    from app.cli import main
    rc = main(["validate", "-"])
    assert rc == 0
    assert "通过" in capsys.readouterr().out


# ============================================================
# 入口 / 帮助
# ============================================================

def test_no_command_shows_help(capsys):
    """无参数 → 打印帮助 + exit 2"""
    from app.cli import main
    rc = main([])
    assert rc == 2


def test_validate_without_path_exits_2(capsys):
    """validate 没传路径 → argparse 报错(SystemExit 2)"""
    from app.cli import main
    with pytest.raises(SystemExit) as exc_info:
        main(["validate"])
    assert exc_info.value.code == 2
