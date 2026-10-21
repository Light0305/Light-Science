"""WRT-D06 分册化结构 lint：主文件行数预算、分册引用存在性、frontmatter 完整性。

注记：第 3 步施工期本文件以 version "1.0" 钉住 frontmatter 不动；
第 6 步封版按封版口径将版本行升至 "1.1"，本钉随之更新为 "1.1"
（phase6-seal.md 留痕），断言的守护目的（防 frontmatter 被无意改动）
不变。第三批快修封版升至 "1.2"，本钉随之更新为 "1.2"
（patch-seal-2026-10-21-e.md 留痕）。
"""

from pathlib import Path

PKG = Path(__file__).resolve().parent.parent
SKILL = PKG / "SKILL.md"
REFS = {
    "section-protocols.md": "§10",
    "audit-gates.md": "§11",
    "disclosure-review-revision.md": "§12",
    "failure-modes.md": "§17",
    "supplement-d.md": "§18",
}
MAIN_LINE_BUDGET = 200  # 加载量普查后定（v1.0 单体 313 行 → 主文件 156 行）


def test_skill_line_budget():
    lines = SKILL.read_text(encoding="utf-8").splitlines()
    assert len(lines) <= MAIN_LINE_BUDGET, len(lines)


def test_frontmatter_unchanged():
    text = SKILL.read_text(encoding="utf-8")
    head = text.split("---", 2)[1]
    assert "name: light-write" in head
    assert "description: Use when 需要把分析结论包写成可投稿的稿件" in head
    assert 'version: "1.2"' in head
    assert "author: light-write contributors" in head
    assert "license: MIT" in head


def test_references_exist_and_routed():
    main = SKILL.read_text(encoding="utf-8")
    for fname, section_mark in REFS.items():
        path = PKG / "references" / fname
        assert path.exists(), fname
        body = path.read_text(encoding="utf-8")
        assert len(body.splitlines()) >= 10, fname
        assert section_mark in body, (fname, section_mark)
        assert f"references/{fname}" in main, fname


def test_main_keeps_rule_table_and_checklist():
    main = SKILL.read_text(encoding="utf-8")
    assert "writable_form 规则表" in main
    assert "成稿自检清单" in main
    assert "五段门规程卡" in main
    assert "合理化反制表" in main
