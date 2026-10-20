"""席位升格三查（v1.1 REV-D10）：虚设拒 / 逐字对不上拒 / 越档拒。"""

import pytest

from conftest import drive_panel, make_analysis, make_figure, \
    make_manuscript
from light_review.forensic import run_forensic
from light_review.intake import run_intake
from light_review.panel import PanelError, build_consensus, freeze_reports
from light_review.project import init_package, load_package
from light_review.validate import validate_package


def _concern(cid="RV-C001", raised=("S1", "S2"), proposals=None, **kw):
    row = {"concern_id": cid, "statement": "关切陈述",
           "raised_by": list(raised),
           "severity_proposals": proposals or {"S1": "major",
                                                "S2": "major"}}
    row.update(kw)
    return row


def test_fabricated_pointer_rejected(review_pkg):
    drive_panel(review_pkg)
    freeze_reports(review_pkg)
    bad = _concern(pointers={"claim_pointer": "claims_register:C1",
                             "evidence_pointer": "conclusions:C99"})
    with pytest.raises(PanelError) as ei:
        build_consensus(review_pkg, [bad])
    assert any("升格三查" in g and "虚设" in g for g in ei.value.gaps)


def test_fabricated_verdict_line_rejected(review_pkg):
    drive_panel(review_pkg)
    freeze_reports(review_pkg)
    bad = _concern(pointers={
        "claim_pointer": "claims_register:C1",
        "evidence_pointer": "verdicts.jsonl:R-NOPE 不存在"})
    with pytest.raises(PanelError) as ei:
        build_consensus(review_pkg, [bad])
    assert any("虚设" in g for g in ei.value.gaps)


def test_verbatim_snippet_mismatch_rejected(review_pkg):
    drive_panel(review_pkg)
    freeze_reports(review_pkg)
    bad = _concern(
        pointers={"claim_pointer": "claims_register:C1",
                  "evidence_pointer": "conclusions:C1"},
        support_snippet="这段文字在结论卡里根本不存在")
    with pytest.raises(PanelError) as ei:
        build_consensus(review_pkg, [bad])
    assert any("逐字" in g for g in ei.value.gaps)


def test_verbatim_snippet_matched_and_recorded(review_pkg):
    drive_panel(review_pkg)
    freeze_reports(review_pkg)
    ok = _concern(
        pointers={"claim_pointer": "claims_register:C1",
                  "evidence_pointer": "conclusions:C1"},
        support_snippet="untested")
    out = build_consensus(review_pkg, [ok])
    esc = out["concerns"][0]["escalation_checks"]
    assert esc["pointer_resolution"]["result"] == "resolved"
    assert esc["verbatim_support"]["result"] == "matched"
    assert esc["severity_cap"]["result"] == "within_cap"
    assert esc["verdict"] == "pass"
    assert validate_package(review_pkg) == []


def test_critical_without_confirmed_error_evidence_rejected(review_pkg):
    drive_panel(review_pkg)
    freeze_reports(review_pkg)
    over = _concern(
        proposals={"S1": "critical", "S2": "critical"},
        pointers={"claim_pointer": "claims_register:C1",
                  "evidence_pointer": "conclusions:C1"})
    with pytest.raises(PanelError) as ei:
        build_consensus(review_pkg, [over])
    assert any("越档" in g for g in ei.value.gaps)


def test_critical_with_confirmed_error_evidence_admitted(tmp_path):
    # 数字实印与台账不符 → 法医 confirmed error（非 flag_only）
    sections = {"03-results.md":
                "# Results\n\nDiffered by [num:N001] 5.30 points "
                "[@dong2025].\n"}
    ms = make_manuscript(tmp_path / "ms", sections=sections)
    root = init_package(tmp_path / "rp")
    run_intake(root, ms, analysis_path=make_analysis(tmp_path / "an"),
               figure_path=make_figure(tmp_path / "fig"),
               intensity="standard")
    run_forensic(root)
    folded = load_package(root)["findings"]
    errors = [r for r in folded if r.get("type") == "finding"
              and r.get("category") == "confirmed_error"
              and not r.get("flag_only")]
    assert errors, "夹具应产生 confirmed error"
    fid = errors[0]["finding_id"]
    drive_panel(root)
    freeze_reports(root)
    ok = _concern(
        proposals={"S1": "critical", "S2": "major"},
        pointers={"claim_pointer": "claims_register:C1",
                  "evidence_pointer": f"findings:{fid}"})
    out = build_consensus(root, [ok])
    esc = out["concerns"][0]["escalation_checks"]
    assert esc["severity_cap"]["result"] == "within_cap"
    assert out["concerns"][0]["severity"] == "critical"


def test_v10_form_concern_admitted_with_partial_record(review_pkg):
    """v1.0 形态（无指针无片段）仍可入账，三查结果如实落 partial。"""
    drive_panel(review_pkg)
    freeze_reports(review_pkg)
    out = build_consensus(review_pkg, [_concern()])
    esc = out["concerns"][0]["escalation_checks"]
    assert esc["pointer_resolution"]["result"] == "absent"
    assert esc["verbatim_support"]["result"] == "not_provided"
    assert esc["verdict"] == "partial"
    assert validate_package(review_pkg) == []


def test_validate_rejects_tampered_fail_verdict(review_pkg):
    from light_review.project import save_consensus
    drive_panel(review_pkg)
    freeze_reports(review_pkg)
    out = build_consensus(review_pkg, [_concern(
        pointers={"claim_pointer": "claims_register:C1",
                  "evidence_pointer": "conclusions:C1"})])
    out["concerns"][0]["escalation_checks"]["verdict"] = "fail"
    save_consensus(review_pkg, out)
    errors = validate_package(review_pkg)
    assert any("升格三查" in e for e in errors)
