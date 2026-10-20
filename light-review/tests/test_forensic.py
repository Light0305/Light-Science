"""法医层：四方对账四边正反例、覆盖自报、GRIM 并账、开跑纪律。

变异一律在 intake 之前施加（承接后改上游即漂移，法医拒跑另有专测）。
"""

import pytest
import yaml

from conftest import FIG_HASH, make_analysis, make_figure, make_manuscript
from light_review.forensic import ForensicError, adjudicate_finding, run_forensic
from light_review.intake import run_intake
from light_review.project import init_package, load_package
from light_review.validate import validate_package


def build_pkg(tmp_path, manuscript_kw=None, analysis_kw=None, figure_kw=None,
              with_figure=True):
    ms = make_manuscript(tmp_path / "ms", **(manuscript_kw or {}))
    an = make_analysis(tmp_path / "an", **(analysis_kw or {}))
    fig = make_figure(tmp_path / "fig", **(figure_kw or {})) \
        if with_figure else None
    root = init_package(tmp_path / "rp")
    run_intake(root, ms, analysis_path=an, figure_path=fig,
               intensity="standard")
    return root


def _checks(pkg, edge):
    return [r for r in pkg["reconciliation"]
            if r.get("type") == "check" and r.get("edge") == edge]


def _summary(pkg, edge):
    return next(r for r in pkg["reconciliation"]
                if r.get("type") == "summary" and r.get("edge") == edge)


# ---------------------------------------------------------------- 干净世界

def test_clean_world_all_edges_pass_no_findings(tmp_path):
    root = build_pkg(tmp_path)
    s = run_forensic(root)
    pkg = load_package(root)
    for edge in ("claims_evidence", "numbers_numbers",
                 "numbers_figures", "citations_claims"):
        summary = _summary(pkg, edge)
        assert summary["errors"] == 0 and summary["decision_errors"] == 0, edge
    assert pkg["findings"] == []
    assert s["findings"] == 0
    assert validate_package(root) == []  # 覆盖自报与机械重算一致


# ---------------------------------------------------------------- 主张↔证据

def test_claims_form_over_ceiling_is_decision_error(tmp_path):
    claims = [{"claim_id": "C1", "analysis_claim_ref": "C1",
               "upstream_status": "untested", "strength_grade": "insufficient",
               "line_verdicts": {"R-FIX": "undetermined",
                                 "R-ORA": "undetermined"},
               "writable_ceiling": "limitations_only", "writable_form": "full",
               "evidence_refs": [{"kind": "analysis_verdict_lines",
                                  "refs": ["R-FIX", "R-ORA"]}]}]
    root = build_pkg(tmp_path, manuscript_kw={"claims": claims})
    run_forensic(root)
    pkg = load_package(root)
    rows = _checks(pkg, "claims_evidence")
    assert rows[0]["result"] == "decision_error"
    finding = next(f for f in pkg["findings"] if f["layer"] == "conclusion_flip")
    assert finding["category"] == "confirmed_error"
    assert finding["claim_pointer"] == "claims_register:C1"


def test_claims_grade_mismatch_is_decision_error(tmp_path):
    claims = [{"claim_id": "C1", "analysis_claim_ref": "C1",
               "upstream_status": "untested", "strength_grade": "strong",
               "line_verdicts": {"R-FIX": "undetermined",
                                 "R-ORA": "undetermined"},
               "writable_ceiling": "limitations_only",
               "writable_form": "limitations_only",
               "evidence_refs": [{"kind": "analysis_verdict_lines",
                                  "refs": ["R-FIX", "R-ORA"]}]}]
    root = build_pkg(tmp_path, manuscript_kw={"claims": claims})
    run_forensic(root)
    pkg = load_package(root)
    assert _checks(pkg, "claims_evidence")[0]["result"] == "decision_error"


def test_claims_missing_conclusion_row_is_error(tmp_path):
    claims = [{"claim_id": "C1", "analysis_claim_ref": "C9",
               "upstream_status": "untested", "strength_grade": "insufficient",
               "line_verdicts": {}, "writable_ceiling": "limitations_only",
               "writable_form": "limitations_only", "evidence_refs": []}]
    root = build_pkg(tmp_path, manuscript_kw={"claims": claims})
    run_forensic(root)
    pkg = load_package(root)
    assert _checks(pkg, "claims_evidence")[0]["result"] == "error"
    assert pkg["findings"][0]["category"] == "unresolved_input"


# ---------------------------------------------------------------- 数字↔数字

def test_numbers_printed_mismatch_is_error(tmp_path):
    sections = {"03-results.md":
                "# Results\n\nDiffered by [num:N001] 5.30 points [@dong2025].\n"}
    root = build_pkg(tmp_path, manuscript_kw={"sections": sections})
    run_forensic(root)
    pkg = load_package(root)
    rows = _checks(pkg, "numbers_numbers")
    assert rows[0]["result"] == "error"
    finding = next(f for f in pkg["findings"]
                   if f["check_id"] == rows[0]["check_id"])
    assert finding["layer"] == "inconsistency"


def test_numbers_recompute_outside_interval_is_error(tmp_path):
    spec = [{"spec_id": "S001", "registry_line_id": "R-ORA",
             "status": "computed",
             "effect_size": {"type": "mean_diff", "value": 5.31}}]
    root = build_pkg(tmp_path, analysis_kw={"spec_results": spec})
    run_forensic(root)
    pkg = load_package(root)
    assert _checks(pkg, "numbers_numbers")[0]["result"] == "error"


def test_numbers_sign_flip_is_decision_error(tmp_path):
    spec = [{"spec_id": "S001", "registry_line_id": "R-ORA",
             "status": "computed",
             "effect_size": {"type": "mean_diff", "value": -5.2493333}}]
    root = build_pkg(tmp_path, analysis_kw={"spec_results": spec})
    run_forensic(root)
    pkg = load_package(root)
    assert _checks(pkg, "numbers_numbers")[0]["result"] == "decision_error"
    assert any(f["layer"] == "conclusion_flip" for f in pkg["findings"])


def test_numbers_no_recompute_source_not_assessable(tmp_path):
    numbers = [{"num_id": "N001", "value_as_printed": "5.25",
                "locations": [{"section": "03-results.md"}]}]
    conclusions = {"claims_verdict": [
        {"claim_id": "C1", "support": "untested",
         "line_verdicts": {"R-FIX": "undetermined", "R-ORA": "undetermined"}}],
        "strength": [{"claim_id": "C1", "grade": "insufficient"}],
        "number_provenance": []}
    root = build_pkg(tmp_path,
                     manuscript_kw={"numbers": numbers},
                     analysis_kw={"conclusions": conclusions,
                                  "spec_results": []})
    run_forensic(root)
    pkg = load_package(root)
    rows = _checks(pkg, "numbers_numbers")
    assert rows[0]["result"] == "not_assessable"
    assert not any(f["check_id"] == rows[0]["check_id"]
                   for f in pkg["findings"])


def test_numbers_dangling_verdict_ref_is_provenance_gap(tmp_path):
    numbers = [{"num_id": "N001", "value_as_printed": "5.25",
                "verdict_ref": "R-ORA",
                "locations": [{"section": "03-results.md"}]}]
    conclusions = {"claims_verdict": [
        {"claim_id": "C1", "support": "untested",
         "line_verdicts": {"R-FIX": "undetermined", "R-ORA": "undetermined"}}],
        "strength": [{"claim_id": "C1", "grade": "insufficient"}],
        "number_provenance": []}
    root = build_pkg(tmp_path,
                     manuscript_kw={"numbers": numbers},
                     analysis_kw={"conclusions": conclusions,
                                  "spec_results": []})
    run_forensic(root)
    pkg = load_package(root)
    assert _checks(pkg, "numbers_numbers")[0]["result"] == "not_assessable"
    assert any(f["category"] == "provenance_gap" for f in pkg["findings"])


# ---------------------------------------------------------------- 数字↔图

def test_figures_missing_counterpart_is_error(tmp_path):
    figs = [{"fig_id": "fig-9", "files": []}]
    root = build_pkg(tmp_path, figure_kw={"figures": figs})
    run_forensic(root)
    pkg = load_package(root)
    assert _checks(pkg, "numbers_figures")[0]["result"] == "error"
    assert pkg["findings"][0]["category"] == "unresolved_input"


def test_figures_hash_mismatch_is_error(tmp_path):
    figs = [{"fig_id": "fig-1", "caption_hash": "b" * 64,
             "files": [{"path": "exports/fig1.svg", "sha256": "c" * 64,
                        "role": "main_pdf"}]}]
    root = build_pkg(tmp_path, figure_kw={"figures": figs})
    run_forensic(root)
    pkg = load_package(root)
    assert _checks(pkg, "numbers_figures")[0]["result"] == "error"


def test_figures_caption_unregistered_number_is_error(tmp_path):
    figures = [{"figure_id": "F001", "kind": "figure", "status": "backfilled",
                "source_ref": "assets/fig1.svg",
                "source_hash": FIG_HASH,
                "caption": "Scores improved by 9.99 points.",
                "display_number": 1}]
    root = build_pkg(tmp_path, manuscript_kw={"figures": figures})
    run_forensic(root)
    pkg = load_package(root)
    rows = _checks(pkg, "numbers_figures")
    assert rows[0]["result"] == "error"
    assert any(f["category"] == "provenance_gap" for f in pkg["findings"])


def test_figures_no_figure_package_all_not_assessable(tmp_path):
    root = build_pkg(tmp_path, with_figure=False)
    run_forensic(root)
    pkg = load_package(root)
    summary = _summary(pkg, "numbers_figures")
    assert summary["checked"] == 1 and summary["not_assessable"] == 1
    assert summary["errors"] == 0


# ---------------------------------------------------------------- 引用↔主张

def test_citations_ghost_key_is_error(tmp_path):
    sections = {"03-results.md":
                "# Results\n\nDiffered by [num:N001] 5.25 points [@ghost2099].\n"}
    root = build_pkg(tmp_path, manuscript_kw={"sections": sections})
    run_forensic(root)
    pkg = load_package(root)
    rows = [r for r in _checks(pkg, "citations_claims")
            if r["result"] == "error"]
    assert rows, "被引键不在 lock 中应判 error"
    assert any(f["category"] == "unresolved_input" for f in pkg["findings"])


def test_citations_lock_entry_without_hash_not_assessable(tmp_path):
    lock = [{"key": "dong2025", "entry_id": "ST001",
             "retraction_state": "clean"}]
    root = build_pkg(tmp_path, manuscript_kw={"lock_entries": lock})
    run_forensic(root)
    pkg = load_package(root)
    rows = [r for r in _checks(pkg, "citations_claims")
            if r["result"] == "not_assessable"]
    assert rows, "lock 条目缺 entry_hash 应判 not_assessable"
    assert any(f["category"] == "provenance_gap" for f in pkg["findings"])


def test_citations_claim_ref_to_missing_line_is_error(tmp_path):
    claims = [{"claim_id": "C1", "analysis_claim_ref": "C1",
               "upstream_status": "untested", "strength_grade": "insufficient",
               "line_verdicts": {"R-FIX": "undetermined",
                                 "R-ORA": "undetermined"},
               "writable_ceiling": "limitations_only",
               "writable_form": "limitations_only",
               "evidence_refs": [{"kind": "analysis_verdict_lines",
                                  "refs": ["R-NOPE"]}]}]
    root = build_pkg(tmp_path, manuscript_kw={"claims": claims})
    run_forensic(root)
    pkg = load_package(root)
    rows = [r for r in _checks(pkg, "citations_claims")
            if r["result"] == "error"]
    assert rows, "主张 evidence_refs 指向不存在登记行应判 error"


# ---------------------------------------------------------------- GRIM 并账

def test_grim_flag_enters_findings_flag_only(tmp_path):
    root = build_pkg(tmp_path)
    (root / "forensic" / "summaries.yaml").write_text(yaml.safe_dump(
        {"entries": [
            {"stat_id": "GS001", "kind": "mean", "value": "2.33",
             "decimals": 2, "n": 7, "items": 1, "scale_type": "likert"},
        ]}), encoding="utf-8")
    run_forensic(root)
    pkg = load_package(root)
    finding = next(f for f in pkg["findings"]
                   if f["check_id"] == "F-GRIM-GS001")
    assert finding["category"] == "confirmed_error"
    assert finding["flag_only"] is True
    compat = next(r for r in pkg["compatibility"]
                  if r["stat_id"] == "GS001")
    assert compat["result"] == "incompatible"
    assert validate_package(root) == []


# ---------------------------------------------------------------- 开跑纪律

def test_forensic_refuses_on_snapshot_drift(tmp_path):
    root = build_pkg(tmp_path)
    section = tmp_path / "ms" / "sections" / "03-results.md"
    section.write_text(section.read_text(encoding="utf-8") + "改动\n",
                       encoding="utf-8")
    with pytest.raises(ForensicError):
        run_forensic(root)


def test_forensic_refuses_rerun_after_adjudication(tmp_path):
    sections = {"03-results.md":
                "# Results\n\nDiffered by [num:N001] 5.30 points [@dong2025].\n"}
    root = build_pkg(tmp_path, manuscript_kw={"sections": sections})
    run_forensic(root)
    adjudicate_finding(root, "F001", "overruled", "张三", "台账登记笔误已更正")
    with pytest.raises(ForensicError):
        run_forensic(root)
