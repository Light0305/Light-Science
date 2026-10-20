"""FIGURE_REPORT.md：生成内容与手工区保留。"""

from light_figure.report import MANUAL_END, MANUAL_START, build_report


def test_report_generated_with_figure_table(filled_pkg):
    result = build_report(filled_pkg["root"])
    text = (filled_pkg["root"] / "FIGURE_REPORT.md").read_text(
        encoding="utf-8")
    assert result["figures"] == 2
    assert "fig-data" in text and "fig-method" in text
    assert "provenance 账面" in text
    assert MANUAL_START in text and MANUAL_END in text


def test_report_preserves_manual_section(filled_pkg):
    root = filled_pkg["root"]
    build_report(root)
    path = root / "FIGURE_REPORT.md"
    text = path.read_text(encoding="utf-8")
    text = text.replace(MANUAL_START,
                        MANUAL_START + "\n人工注记：本图包服务于演示稿件。\n")
    path.write_text(text, encoding="utf-8")
    build_report(root)  # 刷新不许覆盖手工区
    refreshed = path.read_text(encoding="utf-8")
    assert "人工注记：本图包服务于演示稿件。" in refreshed
