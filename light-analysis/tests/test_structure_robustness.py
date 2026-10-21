"""ANA-D03 配对/区组结构建模 + ANA-D04 短期（robustness_scope 落字 + 封顶）。

结构口径：声明在案必须 honored（差值序列计算），声明与数据不符逐行
落 undetermined 点名，未声明走独立口径并落结构假设 + 同源警告。
稳健性覆盖：方向份额旁机械列明真算/留痕决策点，留痕过半时方向性
行强度封顶 suggestive。
"""

from __future__ import annotations

import json

import pytest

from conftest import STRONG_POS, make_upstream, write_design_source, write_judge_data
from light_analysis import calc, grading
from light_analysis.conclude import run_grade
from light_analysis.gates import advance_package
from light_analysis.intake import IntakeError, run_intake
from light_analysis.judge import (
    register_sesoi, robustness_scope_of, run_judge,
)
from light_analysis.project import (
    current_verdicts, init_package, load_package, save_ledger,
)
from light_analysis.specs import build_ledger, freeze_ledger
from light_analysis.validate import validate_package


def _current(root):
    return current_verdicts(load_package(root)["verdicts"] or [])


def _checked_with_points(root, points):
    decisions = [{"point": p, "options": opts,
                  "theoretical_justification": "测试账本决策点"}
                 for p, opts in points]
    ledger = build_ledger(decisions)
    freeze_ledger(ledger)
    save_ledger(root, ledger)
    assert advance_package(root) == "checked"
    return root


def _judge(root, tmp_path, lines, sesoi=2.0):
    src = write_design_source(tmp_path, sesoi=sesoi)
    register_sesoi(root, src, "evaluation.sesoi")
    data = write_judge_data(tmp_path, lines)
    return run_judge(root, data, decided_by="analyst-x")


SEGS = [f"seg{i}" for i in range(1, 7)]
IDENTICAL_ARMS = [75.446, 68.821, 77.293, 62.187, 79.169, 72.909]


def _identical_entry(**over):
    entry = {"treatment": list(IDENTICAL_ARMS),
             "reference": list(IDENTICAL_ARMS),
             "reference_label": "同臂冷启动重跑",
             "run_refs": ["R-a2", "R-a1"]}
    entry.update(over)
    return entry


# ---------------------------------------------------------------- calc 口径

def test_align_by_keys_reorders_and_diffs():
    diffs = calc.align_by_keys([10, 20, 30], ["s1", "s2", "s3"],
                               [1, 2, 3], ["s3", "s2", "s1"])
    assert diffs == [7.0, 18.0, 29.0]


def test_align_missing_counterpart_named():
    with pytest.raises(ValueError) as ei:
        calc.align_by_keys([1, 2], ["s1", "s2"], [1, 2], ["s1", "sX"])
    assert "缺对侧" in str(ei.value) and "s2" in str(ei.value)


def test_align_duplicate_key_named():
    with pytest.raises(ValueError) as ei:
        calc.align_by_keys([1, 2], ["s1", "s1"], [1, 2], ["s1", "s2"])
    assert "重复" in str(ei.value)


def test_block_contrasts_values_and_missing_arm():
    out = calc.block_contrasts([10, 14, 20], ["B1", "B1", "B2"],
                               [8, 10, 15], ["B1", "B1", "B2"])
    assert out == [3.0, 5.0]
    with pytest.raises(ValueError) as ei:
        calc.block_contrasts([10, 20], ["B1", "B2"], [8, 9], ["B1", "B1"])
    assert "B2" in str(ei.value) and "缺" in str(ei.value)


def test_paired_effect_known_answer():
    res = calc.paired_effect_and_ci([2, 3, 4, 5])
    assert res["mean_diff"] == 3.5
    assert abs(res["se"] - 0.645497) < 1e-5
    assert res["df"] == 3
    assert 0.011 < res["p_two_sided"] < 0.014
    assert abs(res["hedges_g"] - 1.972) < 0.01


def test_paired_degenerate_zero_diffs():
    res = calc.paired_effect_and_ci([0, 0, 0, 0])
    assert res["se"] == 0.0 and res["p_two_sided"] == 1.0
    t = calc.tost_paired([0, 0, 0, 0], sesoi=2.0)
    assert t["result"] == "pass" and t["p_tost"] == 0.0
    t2 = calc.tost_paired([3, 3, 3], sesoi=2.0)
    assert t2["result"] == "fail"


def test_tost_paired_matches_tost_when_se_positive():
    diffs = [0.5, -0.3, 0.2, 0.1, -0.2, 0.4]
    a = calc.tost_paired(diffs, sesoi=2.0)
    import statistics as _st
    m = _st.mean(diffs)
    se = _st.stdev(diffs) / (len(diffs) ** 0.5)
    b = calc.tost(m, se, len(diffs) - 1, 2.0)
    assert a["p_tost"] == b["p_tost"] and a["result"] == b["result"]


def test_p_superiority_paired_and_sign_test():
    assert calc.p_superiority_paired([1, -1, 0, 2])["value"] == 0.625
    # 5 正 1 负：精确双侧 p = 2 * (C(6,5)+C(6,6)) / 64 = 0.21875
    assert calc.sign_test_p([1, 2, 3, 4, 5, -1])["p_two_sided"] == 0.21875
    assert calc.sign_test_p([0, 0])["p_two_sided"] == 1.0


# ---------------------------------------------------------------- ANA-D03 判定

def test_paired_identical_arms_earn_null(checked_pkg, tmp_path):
    """R-FIX 形态回归：逐段同值 + 配对声明 → 差值口径下 TOST 等价挣得。"""
    entry = _identical_entry(
        pairing={"mode": "paired", "paired_by": "segment"},
        treatment_keys=SEGS, reference_keys=SEGS)
    _judge(checked_pkg, tmp_path, {"L-OK": entry})
    row = _current(checked_pkg)["L-OK"]
    assert row["verdict"] == "null"
    assert row["quadrant"] == "equivalent_only"
    assert row["effect_size"]["value"] == 0.0
    assert row["tost"]["result"] == "pass"
    st = row["structure"]
    assert st["mode"] == "paired" and st["n_units"] == 6
    assert st["source"] == "judge_data"
    assert validate_package(checked_pkg) == []


def test_paired_gain_where_independent_is_undetermined(pkg, tmp_path):
    """段间方差大、段内差一致：配对口径判得出，独立口径判不出。"""
    ref = [60, 80, 65, 85, 62, 88]
    trt = [r + d for r, d in zip(ref, [2.0, 2.1, 1.9, 2.0, 2.2, 1.8])]
    base = {"treatment": trt, "reference": ref, "reference_label": "同批段对照"}
    paired = dict(base, pairing={"mode": "paired", "paired_by": "segment"},
                  treatment_keys=SEGS, reference_keys=SEGS)

    root1 = _checked_with_points(pkg, [("estimator", ["mean_diff", "median_diff"])])
    _judge(root1, tmp_path, {"L-OK": paired}, sesoi=1.5)
    row = _current(root1)["L-OK"]
    assert row["verdict"] == "positive"
    assert row["structure"]["mode"] == "paired"

    root2 = _checked_with_points(
        _fresh_pkg(tmp_path, "ana-indep"), [("estimator", ["mean_diff", "median_diff"])])
    _judge(root2, tmp_path, {"L-OK": base}, sesoi=1.5)
    row2 = _current(root2)["L-OK"]
    assert row2["verdict"] == "undetermined"
    assert row2["structure"]["mode"] == "independent"
    assert row2["structure"]["assumption"] == "undeclared_independent_default"


def _fresh_pkg(tmp_path, name):
    sub = tmp_path / name
    sub.mkdir(parents=True, exist_ok=True)
    root = tmp_path / "analyses" / name
    init_package(root, title="独立口径对照包")
    card_path, reg_path, dc_path = make_upstream(sub)
    run_intake(root, card_path, reg_path, design_card_path=dc_path)
    return root


def test_declared_pairing_without_keys_undetermined(checked_pkg, tmp_path):
    entry = _identical_entry(pairing={"mode": "paired", "paired_by": "segment"})
    _judge(checked_pkg, tmp_path, {"L-OK": entry})
    row = _current(checked_pkg)["L-OK"]
    assert row["verdict"] == "undetermined"
    assert "对齐键" in row["note"] and "ANA-D03" in row["note"]
    assert row["structure"]["mode"] == "paired"


def test_declared_pairing_missing_counterpart_named(checked_pkg, tmp_path):
    entry = _identical_entry(
        pairing={"mode": "paired", "paired_by": "segment"},
        treatment_keys=SEGS,
        reference_keys=["seg1", "seg2", "seg3", "seg4", "seg5", "segX"])
    _judge(checked_pkg, tmp_path, {"L-OK": entry})
    row = _current(checked_pkg)["L-OK"]
    assert row["verdict"] == "undetermined"
    assert "缺对侧" in row["note"] and "seg6" in row["note"]


def test_declared_structure_summary_only_undetermined(checked_pkg, tmp_path):
    summ = {"mean": 70.0, "spread": 2.0, "n": 6, "replication_level": "segment"}
    entry = {"treatment_summary": summ, "reference_summary": dict(summ),
             "pairing": {"mode": "paired", "paired_by": "segment"},
             "reference_label": "只有摘要"}
    _judge(checked_pkg, tmp_path, {"L-OK": entry})
    row = _current(checked_pkg)["L-OK"]
    assert row["verdict"] == "undetermined"
    assert "分布摘要" in row["note"]


def test_blocked_judgement_and_missing_block(pkg, tmp_path):
    root = _checked_with_points(pkg, [("estimator", ["mean_diff", "median_diff"])])
    entry = {"treatment": [70, 80, 90, 100], "reference": [65, 74, 84, 93],
             "pairing": {"mode": "blocked", "blocked_by": "batch"},
             "treatment_keys": ["B1", "B2", "B3", "B4"],
             "reference_keys": ["B1", "B2", "B3", "B4"],
             "reference_label": "按批次区组"}
    _judge(root, tmp_path, {"L-OK": entry})
    row = _current(root)["L-OK"]
    assert row["verdict"] == "positive"
    assert row["structure"]["mode"] == "blocked"
    assert row["structure"]["n_units"] == 4

    root2 = _fresh_pkg(tmp_path, "ana-block-miss")
    _checked_with_points(root2, [("estimator", ["mean_diff", "median_diff"])])
    bad = dict(entry, reference=[65, 74, 84, 93],
               reference_keys=["B1", "B2", "B3", "B3"])
    _judge(root2, tmp_path, {"L-OK": bad})
    row2 = _current(root2)["L-OK"]
    assert row2["verdict"] == "undetermined"
    assert "B4" in row2["note"] and "缺" in row2["note"]


def test_same_origin_undeclared_warns_but_judges(checked_pkg, tmp_path):
    entry = dict(STRONG_POS, treatment_run_refs=["X1", "X2"],
                 reference_run_refs=["X2", "X3"])
    _judge(checked_pkg, tmp_path, {"L-OK": entry})
    row = _current(checked_pkg)["L-OK"]
    assert row["verdict"] == "positive"
    st = row["structure"]
    assert st["mode"] == "independent"
    assert st["warnings"] and "交叠" in st["warnings"][0]
    assert "交叠" in row["note"]


def test_identical_arms_undeclared_warns(checked_pkg, tmp_path):
    """未声明时逐段同值仍按独立口径判（挣不到等价）+ 同源警告落字。"""
    _judge(checked_pkg, tmp_path, {"L-OK": _identical_entry()})
    row = _current(checked_pkg)["L-OK"]
    assert row["verdict"] == "undetermined"
    assert any("逐元素完全相同" in w for w in row["structure"]["warnings"])
    assert "逐元素完全相同" in row["note"]


# ------------------------------------------------------- 登记行侧声明

def _pkg_with_registry_pairing(tmp_path, decl, name="ana-regpair"):
    card_path, reg_path, dc_path = make_upstream(tmp_path)
    rows = [json.loads(x) for x in
            reg_path.read_text(encoding="utf-8").splitlines() if x.strip()]
    for r in rows:
        if r["run_id"] == "L-OK":
            r["pairing"] = decl
    reg_path.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
        encoding="utf-8")
    root = tmp_path / "analyses" / name
    init_package(root, title="登记侧结构声明")
    return root, card_path, reg_path, dc_path


def test_registry_pairing_passthrough_and_use(tmp_path):
    decl = {"mode": "paired", "paired_by": "segment"}
    root, card_path, reg_path, dc_path = _pkg_with_registry_pairing(tmp_path, decl)
    run_intake(root, card_path, reg_path, design_card_path=dc_path)
    snap = load_package(root)["analysis"]["registry_snapshot"]["lines"]
    line = next(l for l in snap if l["registry_line_id"] == "L-OK")
    assert line["pairing"] == decl
    _checked_with_points(root, [("estimator", ["mean_diff", "median_diff"])])
    entry = _identical_entry(treatment_keys=SEGS, reference_keys=SEGS)
    _judge(root, tmp_path, {"L-OK": entry})
    row = _current(root)["L-OK"]
    assert row["verdict"] == "null"
    assert row["structure"]["source"] == "registry_row"


def test_registry_pairing_bad_shape_blocked_at_intake(tmp_path):
    root, card_path, reg_path, dc_path = _pkg_with_registry_pairing(
        tmp_path, {"mode": "paired"}, name="ana-regbad")
    with pytest.raises(IntakeError) as ei:
        run_intake(root, card_path, reg_path, design_card_path=dc_path)
    assert any("pairing" in g and "paired_by" in g for g in ei.value.gaps)


def test_structure_declaration_conflict_undetermined(tmp_path):
    decl = {"mode": "paired", "paired_by": "segment"}
    root, card_path, reg_path, dc_path = _pkg_with_registry_pairing(
        tmp_path, decl, name="ana-regconflict")
    run_intake(root, card_path, reg_path, design_card_path=dc_path)
    _checked_with_points(root, [("estimator", ["mean_diff", "median_diff"])])
    entry = _identical_entry(
        pairing={"mode": "blocked", "blocked_by": "batch"},
        treatment_keys=SEGS, reference_keys=SEGS)
    _judge(root, tmp_path, {"L-OK": entry})
    row = _current(root)["L-OK"]
    assert row["verdict"] == "undetermined"
    assert "不一致" in row["note"]


# ---------------------------------------------------------------- ANA-D04

DEMO_POINTS = [("estimator", ["mean_diff", "median_diff"]),
               ("outlier_handling", ["keep_all", "trim_extremes"])]
THREE_POINTS = DEMO_POINTS + [("missing_data", ["complete_case", "impute"])]
# 真留痕账本：subset / covariate_set 未登记计算语义（第五批词表外），
# 封顶纪律的覆盖靠它，不靠已升格为真执行的点充数。
CAP_POINTS = [("estimator", ["mean_diff", "median_diff"]),
              ("subset", ["full_sample", "core_only"]),
              ("covariate_set", ["unadjusted", "adjusted"])]


def test_robustness_scope_of_demo_ledger():
    # 第五批扩面后：演示账本两点（estimator / outlier_handling 的
    # keep_all+trim_extremes）选项计算语义全登记 → 全部真执行。
    ledger = build_ledger([{"point": p, "options": o,
                            "theoretical_justification": "x"}
                           for p, o in DEMO_POINTS])
    scope = robustness_scope_of(ledger)
    assert scope["computed"] == ["estimator", "outlier_handling"]
    assert scope["trace_only"] == []
    assert scope["trace_only_fraction"] == 0.0
    assert scope["target_fraction"] == 0.5


def test_robustness_scope_unregistered_option_stays_trace():
    # 选项级诚实：missing_data 的 impute 未登记语义（impute 可指
    # 均值/中位/模型填补，语义未定不许冒充已执行）→ 整点留痕并点名。
    ledger = build_ledger([{"point": p, "options": o,
                            "theoretical_justification": "x"}
                           for p, o in THREE_POINTS])
    scope = robustness_scope_of(ledger)
    assert scope["computed"] == ["estimator", "outlier_handling"]
    assert scope["trace_only"] == ["missing_data"]
    assert scope["trace_only_fraction"] == 1 / 3
    assert "impute" in scope["point_basis"]["missing_data"]


def test_row_grade_scope_cap_pure():
    scope_hi = {"computed": ["estimator"],
                "trace_only": ["outlier_handling", "missing_data"],
                "trace_only_fraction": 2 / 3}
    grade, reason = grading.row_grade(
        "positive", 1.0, type_m=1.2, robustness_scope=scope_hi)
    assert grade == "suggestive" and "ANA-D04" in reason
    scope_half = {"computed": ["estimator"], "trace_only": ["outlier_handling"],
                  "trace_only_fraction": 0.5}
    grade2, reason2 = grading.row_grade(
        "positive", 1.0, type_m=1.2, robustness_scope=scope_half)
    assert grade2 == "conclusive" and "ANA-D04" not in reason2
    # null 行不读覆盖封顶
    grade3, _ = grading.row_grade(
        "null", 1.0, tost_p=0.001, alpha=0.05, robustness_scope=scope_hi)
    assert grade3 == "conclusive"


def test_judge_rows_carry_scope_demo_fully_computed(pkg, tmp_path):
    root = _checked_with_points(pkg, DEMO_POINTS)
    _judge(root, tmp_path, {"L-OK": STRONG_POS})
    row = _current(root)["L-OK"]
    assert row["verdict"] == "positive"
    scope = row["robustness_scope"]
    assert scope["computed"] == ["estimator", "outlier_handling"]
    assert scope["trace_only"] == []
    assert scope["trace_only_fraction"] == 0.0
    assert "稳健性覆盖封顶" not in (row["strength_cap_reason"] or "")
    assert validate_package(root) == []


def test_judge_scope_cap_over_half(pkg, tmp_path):
    root = _checked_with_points(pkg, CAP_POINTS)
    _judge(root, tmp_path, {"L-OK": STRONG_POS})
    row = _current(root)["L-OK"]
    assert row["verdict"] == "positive"
    assert row["robustness_scope"]["trace_only_fraction"] == 2 / 3
    assert row["strength_grade"] == "suggestive"
    assert "ANA-D04" in row["strength_cap_reason"]
    assert validate_package(root) == []


def test_conclude_inputs_carry_scope(pkg, tmp_path):
    root = _checked_with_points(pkg, CAP_POINTS)
    _judge(root, tmp_path, {"L-OK": STRONG_POS})
    assert advance_package(root) == "judged"
    run_grade(root)
    conclusions = load_package(root)["conclusions"]
    st = conclusions["strength"][0]
    assert st["inputs"]["robustness_scope"]["trace_only_fraction"] == 2 / 3
