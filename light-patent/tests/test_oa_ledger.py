"""P5 答复（第 33 条）+ P6 台账（期限/worth-it/memory 导出段）。"""

import pytest

from light_patent import check, draft, ledger, oa
from light_patent.project import PatentError, load_case, load_ledger

from conftest import drive_to_drafted


def _to_filed(root, tmp_path):
    drive_to_drafted(root, tmp_path)
    draft.strip_filing(root)
    check.register_redteam(root, {
        "claims_team": {"checked": ["创造性"], "not_checked": [],
                        "findings": []},
        "package_team": {"checked": ["一致性"], "not_checked": [],
                         "findings": []}})
    check.run_check(root)
    ledger.register_filing(root, {"application_no": "CN202610000000.X",
                                  "filing_date": "2026-05-01"})
    return root


def test_priority_window_and_pct_hint(case_root):
    ledger.register_priority(case_root, {"app_no": "CN202510999999.9",
                                         "date": "2026-01-15"})
    deadlines = ledger.refresh_deadlines(case_root)
    prio = [d for d in deadlines if d["kind"] == "priority_window"]
    assert prio and prio[0]["due"] == "2027-01-15"
    assert "PCT" in prio[0]["basis"]


def test_filing_sets_status_and_exam_deadline(case_root, tmp_path):
    _to_filed(case_root, tmp_path)
    assert load_case(case_root)["status"] == "filed"
    deadlines = load_ledger(case_root)["deadlines"]
    exam = [d for d in deadlines if d["kind"] == "request_examination"]
    assert exam and exam[0]["due"] == "2029-05-01"


def test_office_action_response_deadline(case_root, tmp_path):
    _to_filed(case_root, tmp_path)
    oa.register_office_action(case_root, {
        "action_id": "OA-1", "notified_at": "2026-09-01",
        "response_months": 4,
        "defects": [{"defect_id": "D-1", "article": "专利法第 22 条第 3 款",
                     "claim_refs": [1], "cited_docs": ["CN111111111A"],
                     "summary": "权要 1 创造性缺陷"}]})
    assert load_case(case_root)["status"] == "office_action"
    deadlines = load_ledger(case_root)["deadlines"]
    resp = [d for d in deadlines if d["kind"] == "office_action_response"]
    assert resp and resp[0]["due"] == "2027-01-01"


def test_amendment_requires_art33_basis(case_root, tmp_path):
    _to_filed(case_root, tmp_path)
    oa.register_office_action(case_root, {
        "action_id": "OA-1", "notified_at": "2026-09-01",
        "response_months": 4,
        "defects": [{"defect_id": "D-1", "article": "专利法第 22 条第 3 款",
                     "claim_refs": [1], "cited_docs": [],
                     "summary": "创造性缺陷"}]})
    with pytest.raises(PatentError) as ei:
        oa.register_amendment(case_root, {
            "amendment_id": "AM-1", "target": "权利要求 1",
            "before": "原特征", "after": "新特征", "defect_ref": "D-1"})
    assert "第 33 条" in str(ei.value) or "出处" in str(ei.value)
    row = oa.register_amendment(case_root, {
        "amendment_id": "AM-1", "target": "权利要求 1",
        "before": "原特征", "after": "并入从属权要 2 的时序聚合特征",
        "defect_ref": "D-1",
        "basis_pointer": "原权利要求 2",
        "basis_quote": "时序聚合模块采用滑动窗口注意力",
        "art33_checked": True})
    assert row["amendment_id"] == "AM-1"
    assert load_case(case_root)["status"] == "responded"


def test_meeting_questions_export(case_root, tmp_path):
    _to_filed(case_root, tmp_path)
    oa.register_office_action(case_root, {
        "action_id": "OA-1", "notified_at": "2026-09-01",
        "response_months": 4,
        "defects": [{"defect_id": "D-1", "article": "专利法第 22 条第 3 款",
                     "claim_refs": [1], "cited_docs": ["CN111111111A"],
                     "summary": "创造性缺陷"}]})
    result = oa.export_meeting_questions(case_root)
    assert result["defects_listed"] == 1
    from light_patent.util import read_text
    text = read_text(result["path"])
    assert "草案，需专利代理师复核" in text
    assert "D-1" in text and "F1" in text


def test_worth_it_requires_evidence(case_root):
    with pytest.raises(PatentError):
        ledger.set_worth_it(case_root, {
            "verdict": "file", "rationale": "值得", "evidence": []})
    result = ledger.set_worth_it(case_root, {
        "verdict": "file_narrowed", "rationale": "收窄后值得",
        "evidence": [{"ref": "novelty/d1.yaml"},
                     {"ref": "intake/candidates.yaml"}]})
    assert result["verdict"] == "file_narrowed"
    assert "只作初筛底稿、不作法律意见" in result["disclaimers"]


def test_memory_export_sync(case_root, tmp_path):
    _to_filed(case_root, tmp_path)
    ledger.refresh_deadlines(case_root)
    export = load_ledger(case_root)["memory_export"]
    assert export["objects"][0]["object"] == "patent_case"
    assert any("查新门" in f["fact"] for f in export["facts"])
    assert any(e["event"].startswith("deadline:") for e in export["events"])
