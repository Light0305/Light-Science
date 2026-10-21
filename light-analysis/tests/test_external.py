"""外部登记抽验测试（第五批 §4 P1-2，§7.0 外部抽验）。

夹具登记数字按 3 位有效数字报告（reported_digits=3），CI/p 的
未取整真值由公开 t 分布临界值手算（df=10：t.975=2.228138851986274、
t=3 双侧 p=0.013343655022569623，scipy 建批时核对）；包内测试
不依赖 scipy，数值正确性对拍在 external-crosscheck 冻结件。
"""

from __future__ import annotations

from conftest import write_design_source, write_judge_data
from light_analysis import external
from light_analysis.gates import advance_package
from light_analysis.judge import register_sesoi, run_judge
from light_analysis.project import (
    current_verdicts, load_package, save_ledger, save_verdicts,
    assign_row_refs, refresh_counts, save_analysis,
)
from light_analysis.specs import build_ledger, freeze_ledger
from light_analysis.validate import validate_package

GLM_REG = {
    "tool": {"name": "lme4", "version": "1.1-35"},
    "model_kind": "glm",
    "model_spec": "y ~ arm + (1|batch), family=gaussian(link=identity)",
    "effect": 2.40, "se": 0.800, "df": 10,
    "ci": {"level": 0.95, "lo": 0.617, "hi": 4.18},
    "p_value": 0.0133, "reported_digits": 3,
}


def _checked(root):
    ledger = build_ledger([{
        "point": "estimator", "options": ["mean_diff", "median_diff"],
        "theoretical_justification": "测试账本"}])
    freeze_ledger(ledger)
    save_ledger(root, ledger)
    assert advance_package(root) == "checked"
    return root


def _judge(root, tmp_path, lines, sesoi=2.0):
    src = write_design_source(tmp_path, sesoi=sesoi)
    register_sesoi(root, src, "evaluation.sesoi")
    data = write_judge_data(tmp_path, lines)
    return run_judge(root, data, decided_by="analyst-x")


def _row(root, line="L-OK"):
    return current_verdicts(load_package(root)["verdicts"] or [])[line]


# ---------------------------------------------------------------- 抽验单元

def test_spot_check_consistent_registration_passes():
    out = external.spot_check_external(GLM_REG)
    assert out["passed"], out["failures"]
    names = {c["name"] for c in out["checks"]}
    assert {"ci_lo", "ci_hi", "p_value"} <= names
    assert all(c["ok"] for c in out["checks"])


def test_spot_check_tampered_ci_named():
    reg = {**GLM_REG, "ci": {"level": 0.95, "lo": 0.617, "hi": 4.35}}
    out = external.spot_check_external(reg)
    assert not out["passed"]
    assert any("CI hi" in f for f in out["failures"])


def test_spot_check_tampered_p_named():
    reg = {**GLM_REG, "p_value": 0.049}
    out = external.spot_check_external(reg)
    assert not out["passed"]
    assert any("p 值复算不一致" in f for f in out["failures"])


def test_spot_check_missing_p_is_skipped_not_failed():
    reg = {k: v for k, v in GLM_REG.items() if k != "p_value"}
    out = external.spot_check_external(reg)
    assert out["passed"]
    pc = next(c for c in out["checks"] if c["name"] == "p_value")
    assert pc["registered"] is None and "未登记 p" in pc["note"]


def test_spot_check_structure_defects():
    out = external.spot_check_external({"model_kind": "glm"})
    assert not out["passed"]
    assert any("tool" in f for f in out["failures"])
    out2 = external.spot_check_external({**GLM_REG, "model_kind": "svm"})
    assert not out2["passed"]
    assert any("model_kind" in f for f in out2["failures"])


def test_spot_check_materials_sign_flip():
    reg = {**GLM_REG, "effect": -2.40,
           "ci": {"level": 0.95, "lo": -4.18, "hi": -0.617},
           "materials": {"group_summaries": [
               {"label": "treatment", "mean": 70.0, "spread": 2.0, "n": 6},
               {"label": "reference", "mean": 65.0, "spread": 2.0, "n": 6}],
               "tolerance": 0.5}}
    out = external.spot_check_external(reg)
    assert not out["passed"]
    assert any("符号相反" in f for f in out["failures"])


def test_spot_check_posterior_direction():
    reg = {**GLM_REG, "model_kind": "bayes_sampling",
           "posterior": {"mean": 2.40, "sd": 0.800,
                         "prob_direction": 0.9987}}
    out = external.spot_check_external(reg)
    assert out["passed"], out["failures"]
    reg_bad = {**reg, "posterior": {"mean": 2.40, "sd": 0.800,
                                    "prob_direction": 0.90}}
    out2 = external.spot_check_external(reg_bad)
    assert not out2["passed"]
    assert any("后验方向概率" in f for f in out2["failures"])


# ---------------------------------------------------------------- 端到端

def test_external_line_judged_end_to_end(pkg, tmp_path):
    _checked(pkg)
    _judge(pkg, tmp_path, {"L-OK": {"external_result": GLM_REG}})
    row = _row(pkg)
    assert row["verdict"] == "positive"
    assert row["effect_size"] == {"type": "external_effect", "value": 2.4}
    assert row["external_spot_check"]["passed"] is True
    assert row["robustness_scope"]["basis"].startswith("外部登记行")
    assert "抽验" in row["note"]
    # 规格集不重算：逐规格行全 not_judged 且点名协议
    pkg_data = load_package(pkg)
    srs = [r for r in pkg_data["spec_results"]
           if r["registry_line_id"] == "L-OK"]
    assert srs and all(r["status"] == "not_judged" for r in srs)
    assert validate_package(pkg) == []


def test_external_tampered_registration_not_judged(pkg, tmp_path):
    _checked(pkg)
    bad = {**GLM_REG, "ci": {"level": 0.95, "lo": 0.617, "hi": 4.35}}
    _judge(pkg, tmp_path, {"L-OK": {"external_result": bad}})
    row = _row(pkg)
    assert row["verdict"] == "undetermined"
    assert "外部登记抽验未过" in row["note"] and "CI hi" in row["note"]
    assert validate_package(pkg) == []


def test_external_with_arms_refused(pkg, tmp_path):
    _checked(pkg)
    entry = {"external_result": GLM_REG,
             "treatment": [72, 74, 73, 75, 71, 74],
             "reference": [64, 66, 65, 63, 67, 65]}
    _judge(pkg, tmp_path, {"L-OK": entry})
    row = _row(pkg)
    assert row["verdict"] == "undetermined"
    assert "同条目并存" in row["note"]


def test_external_bayes_without_diagnostics_gated(pkg, tmp_path):
    _checked(pkg)
    reg = {**GLM_REG, "model_kind": "bayes_sampling",
           "posterior": {"mean": 2.40, "sd": 0.800,
                         "prob_direction": 0.9987}}
    _judge(pkg, tmp_path, {"L-OK": {"external_result": reg}})
    row = _row(pkg)
    # 抽验过 ≠ 可判：贝叶斯行无诊断登记 → 诊断门落 undetermined
    assert row["verdict"] == "undetermined"
    assert row["diagnostics_status"] == "missing"
    assert validate_package(pkg) == []


def test_external_bayes_with_diagnostics_judged(pkg, tmp_path):
    _checked(pkg)
    reg = {**GLM_REG, "model_kind": "bayes_sampling",
           "posterior": {"mean": 2.40, "sd": 0.800,
                         "prob_direction": 0.9987}}
    entry = {"external_result": reg,
             "diagnostics": {"r_hat": 1.0, "ess_bulk": 900.0,
                             "ess_tail": 850.0, "mcse": 0.01}}
    _judge(pkg, tmp_path, {"L-OK": entry})
    row = _row(pkg)
    assert row["verdict"] == "positive"
    assert row["diagnostics_status"] == "present"
    assert validate_package(pkg) == []


def test_validate_recheck_catches_tampered_row(pkg, tmp_path):
    _checked(pkg)
    _judge(pkg, tmp_path, {"L-OK": {"external_result": GLM_REG}})
    assert validate_package(pkg) == []
    pkg_data = load_package(pkg)
    rows = pkg_data["verdicts"]
    target = next(r for r in rows if r.get("external_result"))
    target["external_result"] = {
        **target["external_result"],
        "ci": {"level": 0.95, "lo": 0.617, "hi": 9.99}}
    rows = assign_row_refs([dict(r) for r in rows])
    save_verdicts(pkg, rows)
    pkg2 = load_package(pkg)
    refresh_counts(pkg2["analysis"], rows)
    save_analysis(pkg, pkg2["analysis"])
    errs = validate_package(pkg)
    assert any("外部登记复验未过" in e for e in errs), errs
