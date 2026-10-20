"""补课 D（nature-skills 生态簇）采纳项的校验/门/账本测试。

覆盖：D-W01 位置图、D-W02 术语账、D-W03 一致性清扫、D-W04 风险分级、
D-W05 容差矩阵校准、D-W06 核查四级、D-W07 作者完整性+支撑五级、
D-W08 数据集映射、D-W09 stage/readiness、D-W11 承重保护、
D-W12 对抗协议机械面、D-W13 标记纪律、D-W14 统计底稿条目。
"""

from pathlib import Path

import pytest

from light_write.audit import gate_citations, run_audit
from light_write.gates import _drafted_gate_gaps, advance
from light_write.ledger import allocation_check, scan_markers
from light_write.project import (
    load_package, save_allocation, save_lock, save_manuscript,
    save_terminology,
)
from light_write.util import dump_yaml
from light_write.validate import validate_package
from conftest import add_section, online_records_for


def _codes(gate):
    findings = gate["findings"] if isinstance(gate, dict) else gate.findings
    return {f["code"] for f in findings}


def _gate(report, gate_id):
    return next(g for g in report["gates"] if g["gate"] == gate_id)


def _set_lock_pages(root, pages, entry_id="ST001"):
    pkg = load_package(root)
    for e in pkg["lock"]["entries"]:
        if e["entry_id"] == entry_id:
            e["pages"] = pages
    save_lock(root, pkg["lock"])


# ---------------------------------------------------------------- D-W05

def test_pages_drift_within_four_warns_only(drafted_pkg):
    root = drafted_pkg["root"]
    _set_lock_pages(root, "101-110")
    records = online_records_for(root)
    records["ST001"]["pages"] = "104-113"  # 起页差 3 ≤ 4
    report = run_audit(root, online_records=records)
    gate = _gate(report, "citations")
    assert "cite.pages_drift" in _codes(gate)
    assert gate["status"] == "pass"
    row = gate["details"]["entries"][0]
    assert row["verification_status"] == "check_suggested"  # D-W06


def test_pages_critical_at_five(drafted_pkg):
    root = drafted_pkg["root"]
    _set_lock_pages(root, "101-110")
    records = online_records_for(root)
    records["ST001"]["pages"] = "106-115"  # 起页差 5
    gate = _gate(run_audit(root, online_records=records), "citations")
    assert "cite.pages_critical" in _codes(gate)
    assert gate["status"] == "fail"


def test_article_number_confusable_is_critical(drafted_pkg):
    root = drafted_pkg["root"]
    _set_lock_pages(root, "101880T")
    records = online_records_for(root)
    records["ST001"]["pages"] = "1018807"  # T→7 形近误判
    gate = _gate(run_audit(root, online_records=records), "citations")
    assert "cite.article_number_confusable" in _codes(gate)
    assert gate["status"] == "fail"


def test_early_access_year_drift_warns_not_wrong(drafted_pkg):
    root = drafted_pkg["root"]
    records = online_records_for(root)
    records["ST001"]["year"] += 2
    records["ST001"]["early_access"] = True
    gate = _gate(run_audit(root, online_records=records), "citations")
    assert "cite.early_access_drift" in _codes(gate)
    row = gate["details"]["entries"][0]
    assert row["field_screen"] == "negative"
    assert gate["status"] == "pass"


# ---------------------------------------------------------------- D-W06

def test_verification_status_verified_and_unverifiable(drafted_pkg):
    root = drafted_pkg["root"]
    gate = _gate(run_audit(root, online_records=online_records_for(root)),
                 "citations")
    assert gate["details"]["entries"][0]["verification_status"] == "verified"
    offline = _gate(run_audit(root), "citations")
    assert offline["details"]["entries"][0]["verification_status"] == \
        "unverifiable"  # 查不到 ≠ 编造：合法终态


def test_verification_status_needs_fix_on_field_error(drafted_pkg):
    root = drafted_pkg["root"]
    records = online_records_for(root)
    records["ST001"]["authors"] = ["Ada Lovelace"]  # 人数不符 = error
    gate = _gate(run_audit(root, online_records=records), "citations")
    assert gate["details"]["entries"][0]["verification_status"] == "needs_fix"


# ------------------------------------------------------- D-W07 / D-W12

def test_support_strong_requires_verbatim_quote(drafted_pkg):
    pkg = load_package(drafted_pkg["root"])
    gate = gate_citations(pkg, online_records=online_records_for(
        drafted_pkg["root"]), support={"ST001": {"level": "strong"}})
    assert "cite.support_no_quote" in _codes(gate)
    gate2 = gate_citations(pkg, online_records=online_records_for(
        drafted_pkg["root"]),
        support={"ST001": {"level": "strong",
                           "verbatim_quote": "shows a clear improvement"}})
    assert "cite.support_no_quote" not in _codes(gate2)


def test_support_vocab_and_rejection_taxonomy(drafted_pkg):
    pkg = load_package(drafted_pkg["root"])
    gate = gate_citations(
        pkg, online_records=online_records_for(drafted_pkg["root"]),
        support={"ST001": {"level": "ironclad"}})
    assert "cite.support_vocab" in _codes(gate)
    gate = gate_citations(
        pkg, online_records=online_records_for(drafted_pkg["root"]),
        support={"ST001": {"level": "partial", "verbatim_quote": "q",
                           "rejection_reason": "made_up_reason"}})
    assert "cite.rejection_vocab" in _codes(gate)
    gate = gate_citations(
        pkg, online_records=online_records_for(drafted_pkg["root"]),
        support={"ST001": {"level": "metadata_only"}})
    assert "cite.support_metadata_only" in _codes(gate)
    assert gate.details["support_assessments"][0]["level"] == "metadata_only"



def test_authors_incomplete_blocks_unless_override(pkg):
    root = pkg["root"]
    data = load_package(root)
    data["lock"]["entries"][0]["authors_complete"] = False
    save_lock(root, data["lock"])
    report = validate_package(root)
    assert any(e["code"] == "lock.authors_incomplete"
               for e in report["errors"])
    data = load_package(root)
    data["lock"]["entries"][0]["author_override"] = "紧急覆盖：已按 DOI 回查"
    save_lock(root, data["lock"])
    report = validate_package(root)
    assert not any(e["code"] == "lock.authors_incomplete"
                   for e in report["errors"])


# ---------------------------------------------------------------- D-W03

def test_consistency_sweep_precision_drift_warns(drafted_pkg):
    root = drafted_pkg["root"]
    dump_yaml(Path(root) / "numbers_ledger.yaml", {"numbers": [
        {"num_id": "N001", "value_as_printed": "5.2",
         "trace_ref": "R-PRED#v1", "verdict_ref": "R-PRED",
         "spec_ref": "S001", "calc_provenance": "welch_effect_and_ci",
         "locations": [{"section": "01-introduction.md"}],
         "rounding": "1 位"},
        {"num_id": "N002", "value_as_printed": "5.20",
         "trace_ref": "R-PRED#v1", "verdict_ref": "R-PRED",
         "spec_ref": "S001", "calc_provenance": "welch_effect_and_ci",
         "locations": [{"section": "01-introduction.md"}],
         "rounding": "2 位"},
    ]})
    intro = Path(root) / "sections" / "01-introduction.md"
    intro.write_text(intro.read_text(encoding="utf-8").replace(
        "in the primary metric", "in the primary metric, replicated as "
        "[num:N002] 5.20,"), encoding="utf-8")
    gate = _gate(run_audit(root, online_records=online_records_for(root)),
                 "numbers")
    assert "numbers.precision_drift" in _codes(gate)
    assert gate["status"] == "pass"  # 只警告不自动改


# ---------------------------------------------------------------- D-W02

def test_terminology_locked_variant_in_text_is_error(pkg):
    root = pkg["root"]
    add_section(root, text="We report acc. values for the cohort.\n")
    save_terminology(root, {"locked": True, "terms": [
        {"canonical": "accuracy", "first_use_full": "accuracy",
         "variants": ["acc."], "adjudication": "全稿统一 accuracy"}]})
    report = validate_package(root)
    assert any(e["code"] == "terms.variant_in_text"
               for e in report["errors"])
    # 未锁定则不报错；自创术语任何时候报错
    save_terminology(root, {"locked": False, "terms": [
        {"canonical": "accuracy", "first_use_full": "accuracy",
         "variants": ["acc."]}]})
    report = validate_package(root)
    assert not any(e["code"] == "terms.variant_in_text"
                   for e in report["errors"])
    save_terminology(root, {"locked": False, "terms": [
        {"canonical": "accu-thing", "first_use_full": "accu-thing",
         "coined": True}]})
    report = validate_package(root)
    assert any(e["code"] == "terms.coined" for e in report["errors"])


# ---------------------------------------------------------------- D-W04

def test_use_log_risk_tiers(pkg):
    root = pkg["root"]
    data = load_package(root)
    data["manuscript"]["use_log"] = [
        {"tool": "X", "model_version": "1", "purpose": "draft core argument",
         "section": "discussion", "date": "2026-10-20",
         "risk_tier": "prohibited"}]
    save_manuscript(root, data["manuscript"])
    report = validate_package(root)
    assert any(e["code"] == "use_log.prohibited" for e in report["errors"])
    data["manuscript"]["use_log"] = [
        {"tool": "X", "model_version": "1", "purpose": "interpret results",
         "section": "results", "date": "2026-10-20",
         "risk_tier": "evaluative_interpretive"}]
    save_manuscript(root, data["manuscript"])
    report = validate_package(root)
    assert any(e["code"] == "use_log.evaluative_unverified"
               for e in report["errors"])
    data["manuscript"]["use_log"][0]["human_verified"] = "作者逐条核对 2026-10-20"
    save_manuscript(root, data["manuscript"])
    report = validate_package(root)
    assert not any(e["code"].startswith("use_log.evaluative")
                   for e in report["errors"])


# ------------------------------------------------------- D-W08 / D-W09

def test_datasets_access_path_and_weak_request(pkg):
    root = pkg["root"]
    data = load_package(root)
    data["manuscript"]["datasets"] = [
        {"name": "cohort", "access_path": "sideways", "location": "repo"}]
    save_manuscript(root, data["manuscript"])
    report = validate_package(root)
    assert any(e["code"] == "datasets.access_path_vocab"
               for e in report["errors"])
    data["manuscript"]["datasets"] = [
        {"name": "cohort", "access_path": "justified_request",
         "location": "corresponding author"}]
    save_manuscript(root, data["manuscript"])
    report = validate_package(root)
    assert any(w["code"] == "datasets.weak_request"
               for w in report["warnings"])


def test_checklist_stage_vocab(pkg):
    root = pkg["root"]
    dump_yaml(Path(root) / "submission_checklist.yaml", {"items": [
        {"item_id": "CHK-X", "tier": "baseline", "requirement": "r",
         "status": "open", "stage": "whenever",
         "location": {"kind": "section", "file": "f", "anchor": "a"}}]})
    report = validate_package(root)
    assert any(e["code"] == "checklist.stage_vocab" for e in report["errors"])


def test_stats_checklist_items_via_cli(pkg):
    from light_write.cli import main
    root = str(pkg["root"])
    assert main(["checklist", "add-stats", root]) == 0
    data = load_package(root)
    ids = {i["item_id"] for i in data["checklist"]["items"]}
    assert {"stats-independent-unit", "stats-claim-analysis-map"} <= ids
    assert main(["checklist", "add-stats", root]) == 0  # 幂等
    data = load_package(root)
    assert len(data["checklist"]["items"]) == 2


# ---------------------------------------------------------------- D-W11

def test_protected_statement_must_exist(pkg):
    root = pkg["root"]
    add_section(root, text="No significant difference was observed.\n")
    data = load_package(root)
    data["manuscript"]["protected_statements"] = [
        {"kind": "negative_results", "section": "S-intro",
         "snippet": "No significant difference was observed."}]
    save_manuscript(root, data["manuscript"])
    report = validate_package(root)
    assert not any(e["code"] == "protected.missing"
                   for e in report["errors"])
    data["manuscript"]["protected_statements"][0]["snippet"] = \
        "The deleted sentence."
    save_manuscript(root, data["manuscript"])
    report = validate_package(root)
    assert any(e["code"] == "protected.missing" for e in report["errors"])


# ---------------------------------------------------------------- D-W13

def test_directive_marker_blocks_drafted_gate(drafted_pkg):
    root = drafted_pkg["root"]
    intro = Path(root) / "sections" / "01-introduction.md"
    intro.write_text(intro.read_text(encoding="utf-8")
                     + "[directive: rewrite the gap paragraph]\n",
                     encoding="utf-8")
    gaps = _drafted_gate_gaps(load_package(root))
    assert any("[directive:]" in g for g in gaps)


def test_unknown_marker_is_purity_violation(drafted_pkg):
    root = drafted_pkg["root"]
    intro = Path(root) / "sections" / "01-introduction.md"
    intro.write_text(intro.read_text(encoding="utf-8")
                     + "[fixme: later]\n", encoding="utf-8")
    report = validate_package(root)
    assert any(e["code"] == "markers.unregistered"
               for e in report["errors"])
    markers = scan_markers(load_package(root))
    assert markers["unknown"]


def test_fact_todo_count_is_evidence_readiness(drafted_pkg):
    root = drafted_pkg["root"]
    intro = Path(root) / "sections" / "01-introduction.md"
    intro.write_text(intro.read_text(encoding="utf-8")
                     + "[todo-fact: verify cohort size]\n", encoding="utf-8")
    markers = scan_markers(load_package(root))
    assert markers["evidence_readiness_open"] == 1


# ---------------------------------------------------------------- D-W01

def test_allocation_core_discovery_not_in_supplementary(pkg):
    data = load_package(pkg["root"])
    save_allocation(pkg["root"], {
        "enforced": False, "locations": [], "deletion_log": [],
        "word_count_delta": 0,
        "results": [{"result": "R1", "function": "core_discovery",
                     "destination": "supplementary"}]})
    issues = allocation_check(load_package(pkg["root"]))
    assert any(i["code"] == "allocation.core_in_si" for i in issues)


def test_allocation_enforced_blocks_ready_gate(audited_pkg):
    root = audited_pkg["root"]
    save_allocation(root, {"enforced": True, "locations": [],
                           "results": [], "deletion_log": [],
                           "word_count_delta": 0})
    result = advance(root)
    assert not result["advanced"]
    assert any("正文分配纪律" in g for g in result["gaps"])


def test_allocation_duplicate_demonstrate_rejected(drafted_pkg):
    root = drafted_pkg["root"]
    save_allocation(root, {
        "enforced": False, "results": [], "deletion_log": [],
        "word_count_delta": 0,
        "locations": [
            {"claim_id": "C1", "section": "S-introduction",
             "role": "demonstrate"},
            {"claim_id": "C1", "section": "S-introduction",
             "role": "demonstrate"}]})
    issues = allocation_check(load_package(root))
    assert any(i["code"] == "allocation.duplicate_demonstrate"
               for i in issues)
