"""多重宇宙真执行测试（第五批 §4 P0-2，ANA-D04 扩面）。

纪律：数据准备类决策点（missing_data / transform / outlier_handling）
必须真制备材料帧再计算——规格效应随选择而变是「真跑」的证据；
退化路径（摘要材料、非正值 log、规格帧不可行）一律点名落字，
不许静默恒等冒充执行。
"""

from __future__ import annotations

import math

from conftest import write_design_source, write_judge_data
from light_analysis.gates import advance_package
from light_analysis.judge import register_sesoi, run_judge
from light_analysis.project import (
    current_verdicts, load_package, save_analysis, save_ledger,
)
from light_analysis.specs import build_ledger, freeze_ledger
from light_analysis.validate import validate_package


def _checked_with_points(root, points):
    decisions = [{"point": p, "options": opts,
                  "theoretical_justification": "测试账本决策点"}
                 for p, opts in points]
    ledger = build_ledger(decisions)
    freeze_ledger(ledger)
    save_ledger(root, ledger)
    assert advance_package(root) == "checked"
    return ledger


def _judge(root, tmp_path, lines, sesoi=2.0):
    src = write_design_source(tmp_path, sesoi=sesoi)
    register_sesoi(root, src, "evaluation.sesoi")
    data = write_judge_data(tmp_path, lines)
    return run_judge(root, data, decided_by="analyst-x")


def _spec_rows(root, line="L-OK"):
    pkg = load_package(root)
    by_id = {s["spec_id"]: s for s in pkg["spec_ledger"]["specs"]}
    out = {}
    for r in pkg["spec_results"] or []:
        if r["registry_line_id"] == line and r["status"] == "computed":
            out[r["spec_id"]] = (by_id[r["spec_id"]], r)
    return out


def _row(root, line="L-OK"):
    return current_verdicts(load_package(root)["verdicts"] or [])[line]


def _spec_by_choice(rows, point, choice):
    for spec, r in rows.values():
        if (spec.get("choices") or {}).get(point) == choice:
            return spec, r
    raise AssertionError(f"无 {point}={choice} 的规格行")


# ---------------------------------------------------------------- 异常值

def test_winsorize_truly_changes_spec_effect(pkg, tmp_path):
    _checked_with_points(pkg, [
        ("estimator", ["mean_diff"]),
        ("outlier_handling", ["keep_all", "winsorize_1pct"]),
    ])
    entry = {"treatment": [10, 11, 12, 13, 14, 200],
             "reference": [9, 10, 11, 12, 13, 14],
             "reference_label": "base"}
    _judge(pkg, tmp_path, {"L-OK": entry})
    rows = _spec_rows(pkg)
    assert len(rows) == 2
    _, keep = _spec_by_choice(rows, "outlier_handling", "keep_all")
    _, wins = _spec_by_choice(rows, "outlier_handling", "winsorize_1pct")
    eff_keep = keep["effect_size"]["value"]
    eff_wins = wins["effect_size"]["value"]
    assert abs(eff_keep - (260 / 6 - 69 / 6)) < 1e-9
    # 独立复算缩尾：P99/P1 线性插值（numpy linear 口径，手算钉住）
    def q(sorted_v, qq):
        pos = qq * (len(sorted_v) - 1)
        lo = int(pos)
        return sorted_v[lo] + (sorted_v[lo + 1] - sorted_v[lo]) * (pos - lo)
    t = sorted([10, 11, 12, 13, 14, 200])
    clipped = [min(max(v, q(t, 0.01)), q(t, 0.99)) for v in
               [10, 11, 12, 13, 14, 200]]
    r = sorted([9, 10, 11, 12, 13, 14])
    clipped_r = [min(max(v, q(r, 0.01)), q(r, 0.99)) for v in
                 [9, 10, 11, 12, 13, 14]]
    expected = sum(clipped) / 6 - sum(clipped_r) / 6
    assert abs(eff_wins - expected) < 1e-9
    assert eff_wins < eff_keep  # 极值被拉回，效应变小：真制备的证据
    row = _row(pkg)
    assert row["robustness_scope"]["trace_only_fraction"] == 0.0
    assert validate_package(pkg) == []


def test_trim_extremes_on_paired_units(pkg, tmp_path):
    _checked_with_points(pkg, [
        ("estimator", ["mean_diff"]),
        ("outlier_handling", ["keep_all", "trim_extremes"]),
    ])
    keys = [f"s{i}" for i in range(1, 7)]
    entry = {"treatment": [70, 71, 72, 73, 74, 200],
             "reference": [65, 66, 67, 68, 69, 70],
             "treatment_keys": keys, "reference_keys": keys,
             "pairing": {"mode": "paired", "paired_by": "seg"},
             "reference_label": "base"}
    _judge(pkg, tmp_path, {"L-OK": entry})
    rows = _spec_rows(pkg)
    _, keep = _spec_by_choice(rows, "outlier_handling", "keep_all")
    _, trim = _spec_by_choice(rows, "outlier_handling", "trim_extremes")
    # 差值序列 [5,5,5,5,5,130]：keep 均值 155/6；trim 删最大最小各一 → 5
    assert abs(keep["effect_size"]["value"] - 155 / 6) < 1e-9
    assert trim["effect_size"]["value"] == 5.0


# ---------------------------------------------------------------- 缺失

def test_missing_semantics_differ_by_choice(pkg, tmp_path):
    _checked_with_points(pkg, [
        ("estimator", ["median_diff"]),
        ("missing_data", ["complete_case", "mean_impute"]),
    ])
    entry = {"treatment": [60, None, 61, 62, 63, 100],
             "reference": [50, 51, 52, 53, 54, 55],
             "reference_label": "base"}
    _judge(pkg, tmp_path, {"L-OK": entry})
    rows = _spec_rows(pkg)
    _, cc = _spec_by_choice(rows, "missing_data", "complete_case")
    _, mi = _spec_by_choice(rows, "missing_data", "mean_impute")
    # complete_case 中位 62；mean_impute 填观测均值 69.2 → 中位 62.5
    assert cc["effect_size"]["value"] == 62 - 52.5
    assert mi["effect_size"]["value"] == 62.5 - 52.5
    assert cc["p_value"] != mi["p_value"]


def test_missing_without_disposition_undetermined(pkg, tmp_path):
    _checked_with_points(pkg, [("estimator", ["mean_diff", "median_diff"])])
    entry = {"treatment": [70, None, 72, 73, 71, 74],
             "reference": [64, 66, 65, 63, 67, 65],
             "reference_label": "base"}
    _judge(pkg, tmp_path, {"L-OK": entry})
    row = _row(pkg)
    assert row["verdict"] == "undetermined"
    assert "缺失值" in row["note"] and "missing_data" in row["note"]
    assert validate_package(pkg) == []


# ---------------------------------------------------------------- 变换

def test_log_transform_truly_applies(pkg, tmp_path):
    _checked_with_points(pkg, [
        ("estimator", ["mean_diff"]),
        ("transform", ["none", "log"]),
    ])
    t = [20, 22, 24, 26, 28, 30]
    r = [10, 11, 12, 13, 14, 15]
    entry = {"treatment": t, "reference": r, "reference_label": "base"}
    _judge(pkg, tmp_path, {"L-OK": entry})
    rows = _spec_rows(pkg)
    _, raw = _spec_by_choice(rows, "transform", "none")
    _, lg = _spec_by_choice(rows, "transform", "log")
    assert raw["effect_size"]["value"] == 12.5
    expected = (sum(math.log(v) for v in t) / 6
                - sum(math.log(v) for v in r) / 6)
    assert abs(lg["effect_size"]["value"] - expected) < 1e-12


def test_log_nonpositive_degrades_named(pkg, tmp_path):
    _checked_with_points(pkg, [
        ("estimator", ["mean_diff"]),
        ("transform", ["none", "log"]),
    ])
    entry = {"treatment": [0, 22, 24, 26, 28, 30],
             "reference": [10, 11, 12, 13, 14, 15],
             "reference_label": "base"}
    _judge(pkg, tmp_path, {"L-OK": entry})
    rows = _spec_rows(pkg)
    _, raw = _spec_by_choice(rows, "transform", "none")
    _, lg = _spec_by_choice(rows, "transform", "log")
    assert lg["effect_size"]["value"] == raw["effect_size"]["value"]
    assert "退化为不变换" in (lg["note"] or "")


# ---------------------------------------------------------------- 退化面

def test_summary_prep_degrades_named(pkg, tmp_path):
    _checked_with_points(pkg, [
        ("estimator", ["mean_diff"]),
        ("outlier_handling", ["keep_all", "winsorize_5pct"]),
    ])
    entry = {"treatment_summary": {"mean": 75.0, "spread": 3.0, "n": 6,
                                   "replication_level": "segment"},
             "reference_summary": {"mean": 65.0, "spread": 3.0, "n": 6,
                                   "replication_level": "segment"},
             "reference_label": "base"}
    _judge(pkg, tmp_path, {"L-OK": entry})
    rows = _spec_rows(pkg)
    _, keep = _spec_by_choice(rows, "outlier_handling", "keep_all")
    _, wins = _spec_by_choice(rows, "outlier_handling", "winsorize_5pct")
    assert wins["effect_size"]["value"] == keep["effect_size"]["value"]
    assert "摘要材料无原始值" in (wins["note"] or "")


def test_infeasible_spec_frame_falls_back_named(pkg, tmp_path):
    _checked_with_points(pkg, [
        ("estimator", ["mean_diff"]),
        ("missing_data", ["mean_impute", "complete_case"]),
    ])
    # 区组 b2 的处理臂只有一个元素且缺失：complete_case 帧会让 b2
    # 缺臂（制备不可行）→ 退化为主规格（mean_impute）帧并点名；
    # mean_impute 帧完整可判。
    entry = {"treatment": [100, None],
             "reference": [90, 70, 72],
             "treatment_keys": ["b1", "b2"],
             "reference_keys": ["b1", "b2", "b2"],
             "pairing": {"mode": "blocked", "blocked_by": "batch"},
             "reference_label": "base"}
    _judge(pkg, tmp_path, {"L-OK": entry})
    rows = _spec_rows(pkg)
    _, mi = _spec_by_choice(rows, "missing_data", "mean_impute")
    _, cc = _spec_by_choice(rows, "missing_data", "complete_case")
    assert cc["effect_size"]["value"] == mi["effect_size"]["value"]
    assert "退化为主规格帧口径" in (cc["note"] or "")


# ---------------------------------------------------------------- 下降目标

def test_over_target_note_without_cap(pkg, tmp_path):
    _checked_with_points(pkg, [
        ("estimator", ["mean_diff"]),
        ("missing_data", ["complete_case", "mean_impute"]),
        ("subset", ["full_sample", "core_only"]),
    ])
    pkg_data = load_package(pkg)
    pkg_data["analysis"].setdefault("spec", {})["robustness_target"] = 0.2
    save_analysis(pkg, pkg_data["analysis"])
    entry = {"treatment": [72, 74, 73, 75, 71, 74],
             "reference": [64, 66, 65, 63, 67, 65],
             "reference_label": "base"}
    _judge(pkg, tmp_path, {"L-OK": entry})
    row = _row(pkg)
    scope = row["robustness_scope"]
    assert scope["trace_only_fraction"] == 1 / 3
    assert scope["target_fraction"] == 0.2
    # 1/3 未过 0.5 封顶线：不封顶，但超下降目标须在 note 点名
    assert "ANA-D04" not in (row["strength_cap_reason"] or "")
    assert "下降目标" in row["note"] and "subset" in row["note"]
    assert validate_package(pkg) == []
