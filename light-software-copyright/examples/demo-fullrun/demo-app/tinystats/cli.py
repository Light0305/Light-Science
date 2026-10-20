"""命令行入口：从标准输入或参数读数值序列，输出统计报表。"""

from __future__ import annotations

import sys

from .report import render_markdown, render_table
from .stats import summarize


def parse_values(argv):
    """把参数解析为浮点序列（逗号或空白分隔）。"""
    raw = " ".join(argv).replace(",", " ")
    return [float(x) for x in raw.split() if x]


def main(argv=None):
    """工具主入口：读数、汇总、按格式输出。"""
    args = list(sys.argv[1:] if argv is None else argv)
    fmt = "table"
    if args and args[0] == "--markdown":
        fmt = "markdown"
        args = args[1:]
    if not args:
        print("用法：tinystats [--markdown] 数值...", file=sys.stderr)
        return 2
    summary = summarize(parse_values(args))
    print(render_markdown(summary) if fmt == "markdown"
          else render_table(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
