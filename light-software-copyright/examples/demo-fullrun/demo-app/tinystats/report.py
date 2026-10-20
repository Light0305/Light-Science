"""报表生成：把统计结果字典渲染为定宽文本表。"""

from __future__ import annotations

LABELS = (
    ("count", "样本数"),
    ("mean", "均值"),
    ("median", "中位数"),
    ("stdev", "标准差"),
    ("min", "最小值"),
    ("max", "最大值"),
)


def render_table(summary):
    """渲染统计汇总为文本表（异常值附行列出）。"""
    lines = ["指标        数值", "-" * 24]
    for key, label in LABELS:
        value = summary[key]
        shown = f"{value:.4f}" if isinstance(value, float) else str(value)
        lines.append(f"{label:<10}{shown}")
    outliers = summary.get("outliers") or []
    if outliers:
        lines.append(f"异常值下标：{outliers}")
    return "\n".join(lines)


def render_markdown(summary):
    """渲染统计汇总为 Markdown 表格。"""
    lines = ["| 指标 | 数值 |", "|---|---|"]
    for key, label in LABELS:
        value = summary[key]
        shown = f"{value:.4f}" if isinstance(value, float) else str(value)
        lines.append(f"| {label} | {shown} |")
    return "\n".join(lines)
