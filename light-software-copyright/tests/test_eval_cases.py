"""评测小集机械承接：封闭用例与包内常量/门行为对表。"""

from __future__ import annotations

from pathlib import Path

import yaml

from light_copyright import schema

CASES = yaml.safe_load(
    (Path(__file__).parent.parent / "eval" / "cases.yaml")
    .read_text(encoding="utf-8"))["cases"]


def test_eval_cases_wellformed():
    assert len(CASES) >= 8
    ids = [c["id"] for c in CASES]
    assert len(ids) == len(set(ids))
    for c in CASES:
        assert c["scene"] and c["expected"] and c["gate"]


def test_eval_page_constants_match_rules():
    assert schema.CODE_LINES_PER_PAGE == 50
    assert schema.DOC_LINES_PER_PAGE == 30
    assert schema.FRONT_BACK_PAGES == 30
    assert schema.FULL_SUBMIT_MAX_PAGES == 60
    assert schema.CORRECTION_DAYS == 30
    assert schema.EXAM_DAYS == 60


def test_eval_doc_routing_constants():
    gates = {c["id"]: c["gate"] for c in CASES}
    assert "Q3" in gates["EV-09"]
    assert schema.DOC_TYPE_BY_KIND == {"gui": "操作手册",
                                       "headless": "设计说明书"}


def test_eval_declaration_gap_is_registered_not_fabricated():
    """EV-05 的根：规则快照中声明原文状态必须是 unobtained。"""
    rule = next(r for r in schema.RULES_SNAPSHOT["rules"]
                if r["id"] == "R-AI-DECLARATION")
    assert rule["grade"] == "unobtained"
