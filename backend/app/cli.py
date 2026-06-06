"""命令行工具 — screenplay validate path/to/script.yaml

用法:
    python -m app.cli validate path/to/screenplay.yaml
    python -m app.cli validate path/to/screenplay.yaml --json
    cat script.yaml | python -m app.cli validate -

退出码:
    0  通过(可能有 warning)
    1  有错误(invalid)
    2  使用错误(参数 / 文件路径错)

为什么独立成 CLI:
  - 团队 CI 流水线无需起 backend,可直接对仓库里所有 YAML 跑 lint
  - 编辑器集成(VS Code task / Vim quickfix)
  - 演示视频里可现场展示"YAML 出错时具体哪行哪个字段错"
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Windows 终端默认 GBK,无法输出 Unicode 符号(如 ✓✗)
# Python 3.7+ 的 reconfigure 把 stdout / stderr 切到 UTF-8
# 若不支持(测试时 capsys 等),静默跳过
try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except (AttributeError, Exception):
    pass

# 颜色码(终端友好,Windows 10+ 也支持)
_RED = "\033[31m"
_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_DIM = "\033[2m"
_BOLD = "\033[1m"
_RESET = "\033[0m"


def _supports_color() -> bool:
    """简单探测:管道 / 非终端时不上色。"""
    return sys.stdout.isatty()


def _c(code: str, text: str) -> str:
    """条件着色。"""
    return f"{code}{text}{_RESET}" if _supports_color() else text


# ============================================================
# 子命令:validate
# ============================================================

def cmd_validate(args: argparse.Namespace) -> int:
    """剧本 YAML 校验。"""
    # 读输入
    if args.path == "-":
        yaml_text = sys.stdin.read()
        source_label = "<stdin>"
    else:
        p = Path(args.path)
        if not p.exists():
            print(_c(_RED, f"错误: 文件不存在 — {p}"), file=sys.stderr)
            return 2
        if not p.is_file():
            print(_c(_RED, f"错误: 不是文件 — {p}"), file=sys.stderr)
            return 2
        try:
            yaml_text = p.read_text(encoding="utf-8")
        except Exception as e:
            print(_c(_RED, f"错误: 读取失败 — {e}"), file=sys.stderr)
            return 2
        source_label = str(p)

    # 校验
    from app.services.yaml_validator import validate_screenplay_yaml
    result = validate_screenplay_yaml(yaml_text)

    # 输出
    if args.json:
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    else:
        _print_human_report(result, source_label)

    return 0 if result.valid else 1


def _print_human_report(result, source_label: str) -> None:
    """人类友好的报告输出。"""
    err_count = len(result.errors())
    warn_count = len(result.warnings())

    print(_c(_BOLD, f"==> {source_label}"))
    print()

    if result.valid:
        print(_c(_GREEN, "✓ 通过"), end="")
        if warn_count:
            print(f"({_c(_YELLOW, f'{warn_count} warnings')})")
        else:
            print()
        if result.parsed:
            meta = result.parsed.get("meta", {})
            stats = meta.get("stats") or {}
            scenes = result.parsed.get("scenes") or []
            print(_c(_DIM, f"  标题  : {meta.get('title', '?')}"))
            print(_c(_DIM, f"  场次  : {len(scenes)}"))
            print(_c(_DIM, f"  角色  : {len(result.parsed.get('characters') or [])}"))
            print(_c(_DIM, f"  地点  : {len(result.parsed.get('locations') or [])}"))
            if stats:
                hi = stats.get("high_fidelity_scenes", "?")
                me = stats.get("medium_fidelity_scenes", "?")
                lo = stats.get("low_fidelity_scenes", "?")
                print(_c(_DIM, f"  保真度: 高 {hi} / 中 {me} / 低 {lo}"))
    else:
        print(_c(_RED, f"✗ 失败 — {err_count} 错误"), end="")
        if warn_count:
            print(_c(_YELLOW, f" + {warn_count} 警告"))
        else:
            print()
        print()
        for issue in result.errors():
            tag = _layer_tag(issue.layer)
            print(f"  {tag} {_c(_BOLD, issue.path)}")
            print(f"      {issue.message}")
        if warn_count:
            print()
            for w in result.warnings():
                print(f"  {_c(_YELLOW, '[warn]')} {w.path}")
                print(f"      {w.message}")


def _layer_tag(layer: str) -> str:
    """layer 字符串变彩色 tag。"""
    mapping = {
        "yaml_parse": (_RED, "[YAML 解析]"),
        "schema":     (_RED, "[Schema]   "),
        "reference":  (_RED, "[引用完整] "),
    }
    code, text = mapping.get(layer, (_RED, f"[{layer}]"))
    return _c(code, text)


# ============================================================
# 主入口
# ============================================================

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="screenplay",
        description="浑晶 · 剧创态 命令行工具",
    )
    subparsers = parser.add_subparsers(dest="command")

    # validate 子命令
    p_val = subparsers.add_parser(
        "validate",
        help="校验剧本 YAML 文件 — schema + 引用完整性",
    )
    p_val.add_argument(
        "path",
        help="YAML 文件路径(- 表示从 stdin 读)",
    )
    p_val.add_argument(
        "--json",
        action="store_true",
        help="输出 JSON 报告(供脚本消费)",
    )
    p_val.set_defaults(func=cmd_validate)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 2
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
