"""P0 审计 + P1 挖掘：决策表四行、审计前置、虚锚拦截、代码盘点。"""

import pytest

from light_patent import intake
from light_patent.project import PatentError, init_package, load_case

from conftest import TITLE, audit_clear, drive_to_mined


def test_init_rejects_utility_model(tmp_path):
    with pytest.raises(PatentError) as ei:
        init_package(tmp_path / "c", TITLE, patent_type="utility_model")
    assert "只做发明" in str(ei.value)


def test_init_rejects_foreign_jurisdiction(tmp_path):
    with pytest.raises(PatentError):
        init_package(tmp_path / "c", TITLE, jurisdiction="US")


def test_init_shape(case_root):
    case = load_case(case_root)
    assert case["status"] == "intake"
    assert case["kind"] == "light-patent/case"
    assert "草案，需专利代理师复核" in case["disclaimers"]
    assert case["blocked"] is None


def test_audit_unknown_without_confirmation(case_root):
    audit = intake.run_audit(case_root, {"confirmed_complete": False})
    assert audit["conclusion"] == "unknown"
    with pytest.raises(PatentError):
        intake.register_sources(case_root, {"sources": [
            {"kind_prefix": "P", "route": "paper", "ref": "x"}]})


def test_audit_clear_when_confirmed(case_root):
    audit = audit_clear(case_root)
    assert audit["conclusion"] == "clear"
    assert load_case(case_root)["status"] == "audited"


def test_audit_grace_possible(case_root):
    audit = intake.run_audit(case_root, {
        "confirmed_complete": True,
        "planned_filing_date": "2026-06-01",
        "disclosures": [{
            "kind": "conference_talk", "date": "2026-03-05",
            "detail": "在规定的学术会议上报告",
            "grace_situation": "prescribed_academic_meeting"}]})
    assert audit["conclusion"] == "grace_possible"
    assert audit["grace_window"]["grace_deadline"] == "2026-09-05"
    assert audit["grace_window"]["proof_within_months"] == 2


def test_audit_blocked_sets_gate(case_root):
    audit = intake.run_audit(case_root, {
        "confirmed_complete": True,
        "planned_filing_date": "2026-06-01",
        "disclosures": [{
            "kind": "paper_published", "date": "2025-01-10",
            "detail": "期刊已发表"}]})
    assert audit["conclusion"] == "blocked_prior_disclosure"
    case = load_case(case_root)
    assert case["blocked"]["gate_id"] == "public_disclosure_block"
    with pytest.raises(PatentError):
        intake.register_candidates(case_root, {"candidates": []})


def test_audit_recent_disclosure_without_grace_blocked(case_root):
    audit = intake.run_audit(case_root, {
        "confirmed_complete": True,
        "planned_filing_date": "2026-06-01",
        "disclosures": [{
            "kind": "preprint", "date": "2026-04-01",
            "detail": "预印本公开"}]})
    assert audit["conclusion"] == "blocked_prior_disclosure"


def test_mine_rejects_virtual_anchor(case_root):
    audit_clear(case_root)
    with pytest.raises(PatentError) as ei:
        intake.register_candidates(case_root, {"candidates": [{
            "candidate_id": "X", "title": "t", "technical_problem": "p",
            "technical_means": "m", "technical_effect": "e",
            "evidence": [{"anchor": "P999"}], "claim_category": "方法",
            "gaps": ["g"], "risks": ["r"]}]})
    assert "虚锚" in str(ei.value)


def test_mine_requires_eight_fields(case_root):
    audit_clear(case_root)
    intake.register_sources(case_root, {"sources": [
        {"kind_prefix": "P", "route": "paper", "ref": "r"}]})
    with pytest.raises(PatentError) as ei:
        intake.register_candidates(case_root, {"candidates": [{
            "candidate_id": "X", "title": "t"}]})
    assert "八字段" in str(ei.value)


def test_drive_to_mined_status(case_root):
    drive_to_mined(case_root)
    assert load_case(case_root)["status"] == "mined"


def test_scan_code_inventories(case_root, tmp_path):
    audit_clear(case_root)
    repo = tmp_path / "repo"
    (repo / "tracker").mkdir(parents=True)
    (repo / "tracker" / "fusion.py").write_text("x = 1\n", encoding="utf-8")
    (repo / "tracker" / "detect.py").write_text("y = 2\n", encoding="utf-8")
    (repo / "notes.txt").write_text("not code", encoding="utf-8")
    result = intake.scan_code(case_root, repo)
    assert result["files"] == 2
    assert len(result["anchors"]) == 2
