"""审计四门：引用两段核对（容差层/双口径分名）、数字对账、落点复核、STALE。"""

import copy
from pathlib import Path

import pytest

from light_write.audit import audit_status, run_audit
from light_write.project import load_package
from light_write.util import dump_yaml
from conftest import online_records_for


def _codes(gate):
    return {f["code"] for f in gate["findings"]}


def _gate(report, gate_id):
    return next(g for g in report["gates"] if g["gate"] == gate_id)


# ---------------------------------------------------------------- 门一

def test_audit_all_pass_with_online_records(drafted_pkg):
    report = run_audit(drafted_pkg["root"],
                       online_records=online_records_for(drafted_pkg["root"]))
    assert report["overall"] == "pass"
    assert all(g["status"] == "pass" for g in report["gates"])
    assert (drafted_pkg["root"] / "audit" / "AUDIT_SUMMARY.md").exists()
    assert audit_status(drafted_pkg["root"])["stale"] is False


def test_gate1_offline_is_honest_unverified(drafted_pkg):
    report = run_audit(drafted_pkg["root"])
    gate = _gate(report, "citations")
    assert gate["status"] == "unverified"
    assert report["overall"] == "fail"
    entry = gate["details"]["entries"][0]
    assert entry["identity"] == "honest-unverified"


def test_gate1_year_drift_within_tolerance_warns_only(drafted_pkg):
    records = online_records_for(drafted_pkg["root"])
    records["ST001"]["year"] = 2025  # 在线年/正式年差 1：容差内
    report = run_audit(drafted_pkg["root"], online_records=records)
    gate = _gate(report, "citations")
    assert gate["status"] == "pass"
    assert "cite.year_drift" in _codes(gate)


def test_gate1_doi_mismatch_resolvable_downgrades(drafted_pkg):
    records = online_records_for(drafted_pkg["root"])
    records["ST001"]["doi"] = "10.1000/clean.9"
    records["ST001"]["doi_resolves"] = True
    report = run_audit(drafted_pkg["root"], online_records=records)
    gate = _gate(report, "citations")
    assert gate["status"] == "pass"
    assert "cite.doi_resolvable" in _codes(gate)


def test_gate1_doi_unresolvable_is_error(drafted_pkg):
    records = online_records_for(drafted_pkg["root"])
    records["ST001"]["doi"] = "10.1000/clean.9"
    records["ST001"]["doi_resolves"] = False
    report = run_audit(drafted_pkg["root"], online_records=records)
    gate = _gate(report, "citations")
    assert gate["status"] == "fail"
    assert "cite.doi_unresolvable" in _codes(gate)


def test_gate1_field_screen_two_wrong_fields_positive(drafted_pkg):
    records = online_records_for(drafted_pkg["root"])
    records["ST001"]["title"] = "A Completely Different Study on Other Things"
    records["ST001"]["year"] = 2019  # 题名 + 年份两错 → Chelli 口径筛阳性
    report = run_audit(drafted_pkg["root"], online_records=records)
    gate = _gate(report, "citations")
    assert gate["status"] == "fail"
    assert "cite.field_screen_positive" in _codes(gate)


def test_gate1_identity_unresolved_without_second_source(drafted_pkg):
    records = {"ST001": {"exists": False}}
    report = run_audit(drafted_pkg["root"], online_records=records)
    gate = _gate(report, "citations")
    assert gate["status"] == "fail"
    assert "cite.identity_unresolved" in _codes(gate)
    assert "cite.identity_fabrication" not in _codes(gate)


def test_gate1_identity_fabrication_needs_second_negative(drafted_pkg):
    records = {"ST001": {"exists": False, "second_source_checked": True,
                         "second_source_found": False}}
    report = run_audit(drafted_pkg["root"], online_records=records)
    gate = _gate(report, "citations")
    assert gate["status"] == "fail"
    assert "cite.identity_fabrication" in _codes(gate)


def test_gate1_relevance_replace_needs_human(drafted_pkg):
    relevance = {"ST001": {"verdict": "neutral", "disposition": "REPLACE",
                           "note": "拟替换", "human_approved": False}}
    report = run_audit(drafted_pkg["root"],
                       online_records=online_records_for(drafted_pkg["root"]),
                       relevance=relevance)
    gate = _gate(report, "citations")
    assert gate["status"] == "fail"
    assert "cite.disposition_needs_human" in _codes(gate)


def test_gate1_relevance_pending_marks_not_convicts(drafted_pkg):
    report = run_audit(drafted_pkg["root"],
                       online_records=online_records_for(drafted_pkg["root"]))
    gate = _gate(report, "citations")
    assert gate["status"] == "pass"
    assert gate["details"]["relevance_pending"] == ["ST001"]


# ---------------------------------------------------------------- 门二

def _edit_section(root, fname, old, new):
    path = Path(root) / "sections" / fname
    text = path.read_text(encoding="utf-8")
    assert old in text
    path.write_text(text.replace(old, new), encoding="utf-8")


def test_gate2_printed_value_edited_without_ledger_fails(drafted_pkg):
    _edit_section(drafted_pkg["root"], "01-introduction.md",
                  "[num:N001] 5.2", "[num:N001] 5.3")
    report = run_audit(drafted_pkg["root"],
                       online_records=online_records_for(drafted_pkg["root"]))
    gate = _gate(report, "numbers")
    assert gate["status"] == "fail"
    assert "numbers.printed_vs_trace" in _codes(gate)
    assert "numbers.printed_vs_ledger" in _codes(gate)


def test_gate2_unregistered_number_in_prose_named(drafted_pkg):
    _edit_section(drafted_pkg["root"], "04-discussion.md",
                  "modest number of segments",
                  "modest number of segments across 37 sites")
    report = run_audit(drafted_pkg["root"],
                       online_records=online_records_for(drafted_pkg["root"]))
    gate = _gate(report, "numbers")
    assert gate["status"] == "fail"
    msgs = [f["message"] for f in gate["findings"]
            if f["code"] == "numbers.unregistered_in_text"]
    assert any("37" in m for m in msgs)


def test_gate2_rounding_to_printed_precision_passes(drafted_pkg):
    dump_yaml(drafted_pkg["root"] / "numbers_ledger.yaml", {"numbers": [
        {"num_id": "N001", "value_as_printed": "5.20",
         "trace_ref": "R-PRED#v1", "verdict_ref": "R-PRED",
         "spec_ref": "S001", "calc_provenance": "welch_effect_and_ci",
         "locations": [], "rounding": "2 位小数"}]})
    _edit_section(drafted_pkg["root"], "01-introduction.md",
                  "[num:N001] 5.2", "[num:N001] 5.20")
    report = run_audit(drafted_pkg["root"],
                       online_records=online_records_for(drafted_pkg["root"]))
    assert _gate(report, "numbers")["status"] == "pass"


# ---------------------------------------------------------------- 门四

def test_gate4_anchor_missing_fails(drafted_pkg):
    pkg_data = load_package(drafted_pkg["root"])
    checklist = pkg_data["checklist"]
    checklist["items"][0]["location"]["anchor"] = "anchor that does not exist"
    dump_yaml(drafted_pkg["root"] / "submission_checklist.yaml", checklist)
    report = run_audit(drafted_pkg["root"],
                       online_records=online_records_for(drafted_pkg["root"]))
    gate = _gate(report, "landing")
    assert gate["status"] == "fail"
    assert "landing.anchor_missing" in _codes(gate)


def test_gate4_item_without_location_fails(drafted_pkg):
    pkg_data = load_package(drafted_pkg["root"])
    checklist = pkg_data["checklist"]
    checklist["items"][1]["location"] = None
    dump_yaml(drafted_pkg["root"] / "submission_checklist.yaml", checklist)
    report = run_audit(drafted_pkg["root"],
                       online_records=online_records_for(drafted_pkg["root"]))
    gate = _gate(report, "landing")
    assert gate["status"] == "fail"
    assert "landing.no_location" in _codes(gate)


# ---------------------------------------------------------------- STALE

def test_audit_stale_after_manuscript_edit(drafted_pkg):
    run_audit(drafted_pkg["root"],
              online_records=online_records_for(drafted_pkg["root"]))
    assert audit_status(drafted_pkg["root"])["stale"] is False
    _edit_section(drafted_pkg["root"], "04-discussion.md",
                  "single-site", "single-site (revised)")
    status = audit_status(drafted_pkg["root"])
    assert status["stale"] is True
