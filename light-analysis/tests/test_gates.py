"""状态机逐段门：缺口点名、全程贯通、REVIEW_UNAVAILABLE 落 blocked。"""

import pytest

from conftest import existing_rows, frozen_ledger, valid_row, write_verdicts
from light_analysis import schema
from light_analysis.gates import GateError, advance_package
from light_analysis.project import (
    load_package, save_analysis, save_conclusions, save_spec_results,
)

LINE_IDS = ["L-OK", "L-VOID", "L-FUND", "L-PART", "L-MISS", "L-INC"]


def _fill_spec_results(root):
    rows = []
    for sid in ("S001", "S002"):
        for lid in LINE_IDS:
            rows.append({"spec_id": sid, "registry_line_id": lid,
                         "verdict": "positive",
                         "effect_size": {"type": "mean_diff", "value": 5.2},
                         "interval": {"kind": "ci", "level": 0.95,
                                      "lo": 1.0, "hi": 9.4}})
    save_spec_results(root, rows)


def _fill_conclusions(root):
    conclusions = schema.new_conclusions()
    conclusions["claims_verdict"] = [{
        "claim_id": "C1", "support": "partial",
        "line_verdicts": {"L-OK": "positive", "L-PART": "negative",
                          "L-VOID": "untested", "L-FUND": "untested",
                          "L-MISS": "untested", "L-INC": "undetermined"},
        "aggregation_note": "逐行判定如实映射，未检验行单列不压平",
    }]
    conclusions["strength"] = [{
        "claim_id": "C1", "grade": "suggestive",
        "inputs": {"line_verdicts": "1 positive / 1 negative / 3 untested / 1 undetermined",
                   "robustness_tier": "中", "evidence_cap": "未检验行封顶",
                   "validity_residual": []},
        "cap_reason": "三行未检验，强度封顶 suggestive",
    }]
    conclusions["boundaries"] = [{
        "claim_id": "C1", "conditions": "当前数据与规模内",
        "not_extrapolatable": "未检验行覆盖的臂",
        "would_change_if": "补齐 L-FUND 的数据版本后重判",
    }]
    conclusions["limitations"] = ["L-PART 覆盖 n=4<6，null 方向精度不足"]
    conclusions["number_provenance"] = [
        {"value": 5.2, "verdict_line": "L-OK#v1", "registry_line_id": lid,
         "run_refs": [], "spec_id": "S001"} for lid in LINE_IDS]
    save_conclusions(root, conclusions)


def _to_judged(root):
    frozen_ledger(root)
    assert advance_package(root) == "checked"
    rows = existing_rows(root) + [
        valid_row(root, "L-OK", "positive"),
        valid_row(root, "L-PART", "negative"),
    ]
    write_verdicts(root, rows)
    _fill_spec_results(root)
    assert advance_package(root) == "judged"


def test_checked_blocked_without_frozen_ledger(pkg):
    with pytest.raises(GateError) as ei:
        advance_package(pkg)
    assert any("账本" in g for g in ei.value.gaps)
    assert load_package(pkg)["analysis"]["status"] == "intake"


def test_checked_passes_with_frozen_ledger(pkg):
    frozen_ledger(pkg)
    assert advance_package(pkg) == "checked"


def test_judged_gap_names_missing_lines(pkg):
    frozen_ledger(pkg)
    advance_package(pkg)
    with pytest.raises(GateError) as ei:
        advance_package(pkg)
    joined = "；".join(ei.value.gaps)
    assert "L-OK" in joined and "尚无现行判定行" in joined
    assert "矩阵未账平" in joined


def test_undetermined_line_does_not_block_judged(pkg):
    # L-INC 的 undetermined 预登记是一等终态：judged 门只要求它在场且如实
    _to_judged(pkg)
    counts = load_package(pkg)["analysis"]["counts"]
    assert counts["undetermined"] == 1 and counts["untested"] == 3


def test_graded_requires_claims_mapping(pkg):
    _to_judged(pkg)
    with pytest.raises(GateError) as ei:
        advance_package(pkg)
    assert any("claims_verdict" in g for g in ei.value.gaps)
    _fill_conclusions(pkg)
    assert advance_package(pkg) == "graded"


def test_delivered_blocked_by_review_unavailable(pkg):
    _to_judged(pkg)
    _fill_conclusions(pkg)
    advance_package(pkg)
    loaded = load_package(pkg)
    loaded["analysis"]["review"] = {
        "reviewer": None, "family": None,
        "review_status": "REVIEW_UNAVAILABLE", "receipt_id": None}
    save_analysis(pkg, loaded["analysis"])
    with pytest.raises(GateError) as ei:
        advance_package(pkg)
    assert any("REVIEW_UNAVAILABLE" in g for g in ei.value.gaps)
    analysis = load_package(pkg)["analysis"]
    assert analysis["status"] == "blocked"
    assert analysis["blocked"]["from_state"] == "graded"


def test_full_path_to_delivered(pkg):
    _to_judged(pkg)
    _fill_conclusions(pkg)
    assert advance_package(pkg) == "graded"
    loaded = load_package(pkg)
    loaded["analysis"]["review"] = {
        "reviewer": "external-reviewer", "family": "other-family",
        "review_status": "approved", "receipt_id": "RV-0123456789"}
    save_analysis(pkg, loaded["analysis"])
    assert advance_package(pkg) == "delivered"
    report = (pkg / "ANALYSIS_REPORT.md").read_text(encoding="utf-8")
    assert "判定分布" in report and "positive" in report
    with pytest.raises(GateError):
        advance_package(pkg)  # delivered 是终态
