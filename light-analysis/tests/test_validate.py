"""校验器逐条纪律：每条一个反例（须拦）+ 基线正例（须放行）。"""

from pathlib import Path

from conftest import existing_rows, frozen_ledger, valid_row, write_verdicts
from light_analysis.project import (
    load_package, save_analysis, save_ledger,
)
from light_analysis.util import dump_yaml
from light_analysis.validate import validate_package


def errors_of(root):
    return validate_package(root)


def has(errors, *keys):
    return any(all(k in e for k in keys) for e in errors)


def test_baseline_package_validates_clean(pkg):
    assert errors_of(pkg) == []


def test_valid_positive_row_passes(pkg):
    frozen_ledger(pkg)
    rows = existing_rows(pkg) + [valid_row(pkg, "L-OK", "positive")]
    write_verdicts(pkg, rows)
    assert errors_of(pkg) == []


def test_unknown_registry_line_rejected(pkg):
    frozen_ledger(pkg)
    rows = existing_rows(pkg) + [valid_row(pkg, "L-XXX", "positive")]
    write_verdicts(pkg, rows)
    assert has(errors_of(pkg), "L-XXX", "只认登记行")


def test_void_supported_line_cannot_be_positive(pkg):
    frozen_ledger(pkg)
    rows = existing_rows(pkg) + [valid_row(pkg, "L-VOID", "positive")]
    write_verdicts(pkg, rows)
    assert has(errors_of(pkg), "作废", "untested")


def test_fundamental_line_cannot_be_null(pkg):
    frozen_ledger(pkg)
    rows = existing_rows(pkg) + [valid_row(pkg, "L-FUND", "null")]
    write_verdicts(pkg, rows)
    assert has(errors_of(pkg), "fundamental", "untested")


def test_null_requires_tost(pkg):
    frozen_ledger(pkg)
    rows = existing_rows(pkg) + [valid_row(pkg, "L-OK", "null", tost=None)]
    write_verdicts(pkg, rows)
    assert has(errors_of(pkg), "TOST")


def test_null_tost_bounds_must_be_frozen_sesoi(pkg):
    bad_tost = {"bounds": {"lo": -2.0, "hi": 2.0, "source": "analyst_chosen"},
                "p_tost": 0.03, "ci90": {"lo": -0.5, "hi": 0.8},
                "ci90_in_bounds": True, "result": "pass"}
    rows = existing_rows(pkg) + [valid_row(pkg, "L-OK", "null", tost=bad_tost)]
    write_verdicts(pkg, rows)
    assert has(errors_of(pkg), "bounds", "design_sesoi")


def test_positive_requires_type_sm(pkg):
    frozen_ledger(pkg)
    rows = existing_rows(pkg) + [valid_row(pkg, "L-OK", "positive", type_sm=None)]
    write_verdicts(pkg, rows)
    assert has(errors_of(pkg), "Type S/M")


def test_type_sm_basis_observed_rejected(pkg):
    frozen_ledger(pkg)
    tsm = {"assumed_D": {"value": 5.2, "basis": "observed",
                         "source_ref": "本批数据估计"},
           "power": 0.8, "type_s": 0.01, "type_m": 1.2}
    rows = existing_rows(pkg) + [valid_row(pkg, "L-OK", "positive", type_sm=tsm)]
    write_verdicts(pkg, rows)
    assert has(errors_of(pkg), "basis")


def test_type_sm_posthoc_wording_rejected(pkg):
    # basis 字段写对了，但来源描述里藏 observed 字样同样拒（字段规则扫整组）
    frozen_ledger(pkg)
    tsm = {"assumed_D": {"value": 2.0, "basis": "sesoi_frozen",
                         "source_ref": "observed pilot estimate"},
           "power": 0.8, "type_s": 0.01, "type_m": 1.2}
    rows = existing_rows(pkg) + [valid_row(pkg, "L-OK", "positive", type_sm=tsm)]
    write_verdicts(pkg, rows)
    assert has(errors_of(pkg), "事后功效")


def test_bayes_row_missing_diagnostics_rejected(pkg):
    frozen_ledger(pkg)
    row = valid_row(pkg, "L-OK", "positive", bayes=True,
                    interval={"kind": "hdi", "level": 0.95, "lo": 1.0, "hi": 9.4},
                    diagnostics=None)
    write_verdicts(pkg, existing_rows(pkg) + [row])
    assert has(errors_of(pkg), "诊断硬字段")


def test_bayes_diagnostics_gate_blocks_verdict(pkg):
    frozen_ledger(pkg)
    diag = {"r_hat": 1.05, "ess_bulk": 500, "ess_tail": 500, "mcse": 0.1}
    row = valid_row(pkg, "L-OK", "positive", bayes=True,
                    interval={"kind": "hdi", "level": 0.95, "lo": 1.0, "hi": 9.4},
                    diagnostics=diag)
    write_verdicts(pkg, existing_rows(pkg) + [row])
    assert has(errors_of(pkg), "诊断未过门", "undetermined")


def test_bayes_diagnostics_gate_allows_undetermined_with_note(pkg):
    frozen_ledger(pkg)
    diag = {"r_hat": 1.05, "ess_bulk": 500, "ess_tail": 500, "mcse": 0.1}
    row = valid_row(pkg, "L-OK", "undetermined", bayes=True,
                    interval={"kind": "hdi", "level": 0.95, "lo": 1.0, "hi": 9.4},
                    diagnostics=diag, note="诊断未过门，停判")
    write_verdicts(pkg, existing_rows(pkg) + [row])
    errors = errors_of(pkg)
    assert not any("诊断" in e for e in errors), errors


def test_bayes_missing_diagnostics_undetermined_with_status_passes(pkg):
    # D-ANA-1 回归：诊断整组缺失 + undetermined + 现状登记齐全 → 放行
    row = valid_row(pkg, "L-OK", "undetermined", bayes=True,
                    interval={"kind": "hdi", "level": 0.95, "lo": 1.0, "hi": 9.4},
                    diagnostics=None, diagnostics_status="missing",
                    note="贝叶斯诊断未过门：诊断缺失，只许落 undetermined")
    write_verdicts(pkg, existing_rows(pkg) + [row])
    errors = errors_of(pkg)
    assert not any("诊断" in e for e in errors), errors


def test_bayes_missing_diagnostics_undetermined_without_status_rejected(pkg):
    # 现状未登记者仍拒（终态放行以登记为条件，不是无条件放行）
    row = valid_row(pkg, "L-OK", "undetermined", bayes=True,
                    interval={"kind": "hdi", "level": 0.95, "lo": 1.0, "hi": 9.4},
                    diagnostics=None,
                    note="贝叶斯诊断未过门：诊断缺失，只许落 undetermined")
    write_verdicts(pkg, existing_rows(pkg) + [row])
    assert has(errors_of(pkg), "登记诊断字段现状")


def test_bayes_partial_diagnostics_undetermined_with_note_passes(pkg):
    # 字段残缺（如 mcse 缺）+ undetermined + note 点名 → 放行
    diag = {"r_hat": 1.002, "ess_bulk": 500, "ess_tail": 500, "mcse": None}
    row = valid_row(pkg, "L-OK", "undetermined", bayes=True,
                    interval={"kind": "hdi", "level": 0.95, "lo": 1.0, "hi": 9.4},
                    diagnostics=diag, diagnostics_status="partial",
                    note="贝叶斯诊断未过门：诊断字段残缺，停判")
    write_verdicts(pkg, existing_rows(pkg) + [row])
    errors = errors_of(pkg)
    assert not any("诊断" in e for e in errors), errors


def test_bayes_partial_diagnostics_blocks_directional(pkg):
    # 字段残缺落方向性判定 → 仍逐键拒
    diag = {"r_hat": 1.002, "ess_bulk": 500, "ess_tail": 500, "mcse": None}
    row = valid_row(pkg, "L-OK", "positive", bayes=True,
                    interval={"kind": "hdi", "level": 0.95, "lo": 1.0, "hi": 9.4},
                    diagnostics=diag, diagnostics_status="partial")
    write_verdicts(pkg, existing_rows(pkg) + [row])
    assert has(errors_of(pkg), "diagnostics 缺 mcse")


def test_forbidden_word_in_note_rejected(pkg):
    row = valid_row(pkg, "L-OK", "undetermined",
                    note="两组差异显著，待补材料")
    write_verdicts(pkg, existing_rows(pkg) + [row])
    assert has(errors_of(pkg), "禁用词", "显著")


def test_untested_row_cannot_carry_grade(pkg):
    rows = existing_rows(pkg)
    for r in rows:
        if r["registry_line_id"] == "L-VOID":
            r["strength_grade"] = "strong"
    write_verdicts(pkg, rows)
    assert has(errors_of(pkg), "不许入强度档")


def test_correction_family_must_be_declared(pkg):
    frozen_ledger(pkg)
    corr = {"family_id": "claim:NOPE", "method": "fdr_bh",
            "p_raw": 0.01, "p_adj": 0.04}
    rows = existing_rows(pkg) + [
        valid_row(pkg, "L-OK", "positive", correction=corr)]
    write_verdicts(pkg, rows)
    assert has(errors_of(pkg), "未在登记头校正族声明")


def test_correction_method_must_match_family(pkg):
    frozen_ledger(pkg)
    corr = {"family_id": "claim:C1", "method": "holm",
            "p_raw": 0.01, "p_adj": 0.04}
    rows = existing_rows(pkg) + [
        valid_row(pkg, "L-OK", "positive", correction=corr)]
    write_verdicts(pkg, rows)
    assert has(errors_of(pkg), "不一致")


def test_p_adj_below_p_raw_rejected(pkg):
    frozen_ledger(pkg)
    corr = {"family_id": "claim:C1", "method": "fdr_bh",
            "p_raw": 0.04, "p_adj": 0.01}
    rows = existing_rows(pkg) + [
        valid_row(pkg, "L-OK", "positive", correction=corr)]
    write_verdicts(pkg, rows)
    assert has(errors_of(pkg), "p_adj")


def test_counts_tamper_rejected(pkg):
    loaded = load_package(pkg)
    loaded["analysis"]["counts"]["positive"] = 9
    save_analysis(pkg, loaded["analysis"])
    assert has(errors_of(pkg), "机械汇总")


def test_frozen_ledger_tamper_rejected(pkg):
    ledger = frozen_ledger(pkg)
    assert errors_of(pkg) == []
    ledger["specs"][0]["choices"]["estimator"] = "median_diff"
    save_ledger(pkg, ledger)
    assert has(errors_of(pkg), "冻结后被改动")


def test_exploratory_verdict_vocabulary_rejected(pkg):
    entry = {"id": "E1", "question": "q", "motivation": "m", "inputs": [],
             "method_note": "n", "finding": "a positive correlation",
             "exploratory": True, "promotion_path": "回 Design amendment"}
    dump_yaml(Path(pkg) / "exploratory" / "exploratory.yaml",
              {"entries": [entry]})
    assert has(errors_of(pkg), "探索条目 E1", "词表")


def test_exploratory_clean_entry_passes(pkg):
    entry = {"id": "E1", "question": "q", "motivation": "m", "inputs": [],
             "method_note": "n", "finding": "高分段聚集现象，待登记后检验",
             "exploratory": True, "promotion_path": "回 Design amendment"}
    dump_yaml(Path(pkg) / "exploratory" / "exploratory.yaml",
              {"entries": [entry]})
    assert errors_of(pkg) == []


def test_dual_n_required(pkg):
    frozen_ledger(pkg)
    rows = existing_rows(pkg) + [
        valid_row(pkg, "L-OK", "positive", n_effective=None)]
    write_verdicts(pkg, rows)
    assert has(errors_of(pkg), "n_effective")


def test_conclusions_malformed_entries_error_not_crash(pkg):
    """结论包条目形态不对（grade --notes 误用字符串 boundaries 等）时，
    校验器须落结构化错误，不许抛 AttributeError（演示实测回归）。"""
    from light_analysis.project import save_conclusions
    conclusions = {
        "claims_verdict": ["不是对象"],
        "strength": ["不是对象"],
        "boundaries": ["自由字符串边界"],
        "limitations": [],
        "number_provenance": ["不是对象"],
        "reflux": [],
    }
    save_conclusions(pkg, conclusions)
    errors = errors_of(pkg)
    assert has(errors, "claims_verdict 条目须为结构化对象")
    assert has(errors, "strength 条目须为结构化对象")
    assert has(errors, "boundaries 条目须为结构化对象")
    assert has(errors, "数字溯源行须为结构化对象")
