"""裁决义务账（v1.1 REV-D05）：登记/履行/豁免纪律 + delivered 阻断。"""

import pytest

from conftest import drive_panel
from light_review.forensic import adjudicate_finding, run_forensic
from light_review.gates import GateError, advance_package, deliver_package
from light_review.obligations import (
    ObligationError, apply_obligation_event, fold_obligations,
    open_obligations, register_obligation,
)
from light_review.panel import build_consensus, freeze_reports
from light_review.project import load_package
from light_review.util import dump_jsonl, read_jsonl
from light_review.validate import validate_package

CONCERNS = [{"concern_id": "RV-C001", "statement": "方法节缺关键参数",
             "raised_by": ["S1", "S2"],
             "severity_proposals": {"S1": "minor", "S2": "minor"}}]


def _to_adjudicated(root):
    run_forensic(root)
    advance_package(root)
    drive_panel(root)
    advance_package(root)
    freeze_reports(root)
    build_consensus(root, CONCERNS)
    advance_package(root)          # reported
    advance_package(root)          # adjudicated


def test_register_and_close_lifecycle(review_pkg):
    row = register_obligation(review_pkg, "投稿前补伦理批件号",
                              by="李四")
    assert row["obligation_id"] == "OB001"
    folded = fold_obligations(load_package(review_pkg)["obligations"])
    assert folded[0]["status"] == "open"
    assert len(open_obligations(folded)) == 1
    # fulfill 须证据指针：缺指针被拒
    with pytest.raises(ObligationError):
        apply_obligation_event(review_pkg, "OB001", "fulfill", by="李四")
    apply_obligation_event(review_pkg, "OB001", "fulfill", by="李四",
                           evidence_pointer="manuscript:ethics/approval.pdf")
    folded = fold_obligations(load_package(review_pkg)["obligations"])
    assert folded[0]["status"] == "fulfilled"
    assert folded[0]["closure"]["evidence_pointer"] \
        == "manuscript:ethics/approval.pdf"
    # 已关闭不许重复关闭
    with pytest.raises(ObligationError):
        apply_obligation_event(review_pkg, "OB001", "waive", by="李四",
                               reason="再豁免")


def test_waive_requires_named_reason(review_pkg):
    register_obligation(review_pkg, "补数据可用性声明", by="李四")
    with pytest.raises(ObligationError) as ei:
        apply_obligation_event(review_pkg, "OB001", "waive", by="李四")
    assert any("理由" in g for g in ei.value.gaps)
    apply_obligation_event(review_pkg, "OB001", "waive", by="李四",
                           reason="目标刊不要求该声明，编辑确认")
    folded = fold_obligations(load_package(review_pkg)["obligations"])
    assert folded[0]["status"] == "waived"
    assert folded[0]["closure"]["reason"]


def test_register_discipline(review_pkg):
    with pytest.raises(ObligationError):
        register_obligation(review_pkg, "", by="李四")
    with pytest.raises(ObligationError):
        register_obligation(review_pkg, "补 X", by="")
    with pytest.raises(ObligationError):
        register_obligation(review_pkg, "补 X", finding_id="F999", by="李四")


def test_open_obligation_blocks_delivered(review_pkg):
    _to_adjudicated(review_pkg)
    register_obligation(review_pkg, "投稿前把图 F001 源链闭合",
                        by="王五")
    with pytest.raises(GateError) as ei:
        deliver_package(review_pkg)
    assert any("OB001" in g and "义务" in g for g in ei.value.gaps)
    apply_obligation_event(review_pkg, "OB001", "fulfill", by="王五",
                           evidence_pointer="delivery:fig-1")
    deliver_package(review_pkg)
    text = (review_pkg / "REVIEW_DELIVERY.md").read_text(encoding="utf-8")
    assert "义务账" in text and "OB001" in text
    assert validate_package(review_pkg) == []


def test_adjudicate_attaches_obligation(tmp_path):
    from conftest import make_analysis, make_figure, make_manuscript
    from light_review.intake import run_intake
    from light_review.project import init_package
    sections = {"03-results.md":
                "# Results\n\nDiffered by [num:N001] 5.30 points "
                "[@dong2025].\n"}
    ms = make_manuscript(tmp_path / "ms", sections=sections)
    root = init_package(tmp_path / "rp")
    run_intake(root, ms, analysis_path=make_analysis(tmp_path / "an"),
               figure_path=make_figure(tmp_path / "fig"),
               intensity="standard")
    run_forensic(root)
    adjudicate_finding(
        root, "F001", "overruled", "张三", "正文笔误，已回 Write 更正",
        obligations=[{"text": "投稿前核对更正后的 PDF 终稿数字"}])
    folded = fold_obligations(load_package(root)["obligations"])
    assert len(folded) == 1
    assert folded[0]["finding_id"] == "F001"
    assert folded[0]["registered_by"] == "张三"
    assert folded[0]["status"] == "open"


def test_validate_catches_reasonless_waive(review_pkg):
    register_obligation(review_pkg, "补 X", by="李四")
    path = review_pkg / "forensic" / "obligations.jsonl"
    rows = read_jsonl(path)
    rows.append({"type": "obligation_event", "obligation_id": "OB001",
                 "action": "waive", "by": "李四", "reason": None,
                 "evidence_pointer": None, "at": "2026-10-21"})
    dump_jsonl(path, rows)
    errors = validate_package(review_pkg)
    assert any("waive" in e and "理由" in e for e in errors)
