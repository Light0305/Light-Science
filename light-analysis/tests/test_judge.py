"""判定子流程（Phase 2）：四象限落字、双门拦截、SESOI 登记纪律、账平贯通。"""

import json

import pytest

from conftest import (
    NEAR_ZERO_PART, STRONG_POS, do_judge, write_design_source,
    write_judge_data,
)
from light_analysis.gates import advance_package
from light_analysis.judge import (
    JudgeError, _decide, register_sesoi, run_judge,
)
from light_analysis.project import current_verdicts, load_package
from light_analysis.validate import validate_package


def _current(root):
    return current_verdicts(load_package(root)["verdicts"] or [])


# ---------------------------------------------------------------- 落字规则（纯函数）

_JOINT_OK = {"median_effect": 3.0, "direction_share": 1.0, "stouffer_p": 0.001}


def test_decide_four_quadrants():
    base = dict(p_adj=0.01, p_ab=0.9, alpha=0.05, gamma=0.75,
                joint=_JOINT_OK, type_m=1.2, type_m_max=2.0,
                null_precision_warning=False)
    v, q, _ = _decide(effect=5.0, tost_pass=False, **base)
    assert (v, q) == ("positive", "significant_not_equivalent")
    v, q, _ = _decide(effect=5.0, tost_pass=True, **base)
    assert (v, q) == ("positive", "significant_but_equivalent")
    v, q, _ = _decide(effect=-5.0, tost_pass=False,
                      **{**base, "joint": {**_JOINT_OK, "median_effect": -3.0}})
    assert (v, q) == ("negative", "significant_not_equivalent")
    # 干净 null：未达方向门但 TOST 过
    v, q, _ = _decide(effect=0.1, tost_pass=True,
                      **{**base, "p_adj": 0.6, "p_ab": 0.55})
    assert (v, q) == ("null", "equivalent_only")
    # 什么都没过 → undetermined，且 note 点名 TOST
    v, q, notes = _decide(effect=0.1, tost_pass=False,
                          **{**base, "p_adj": 0.6, "p_ab": 0.55})
    assert v == "undetermined"
    assert any("TOST" in n for n in notes)


def test_decide_type_m_gate_blocks_positive():
    v, q, notes = _decide(
        effect=5.0, p_adj=0.01, p_ab=0.9, alpha=0.05, gamma=0.75,
        joint=_JOINT_OK, type_m=3.4, type_m_max=2.0,
        tost_pass=False, null_precision_warning=False)
    assert v == "undetermined" and q == "undetermined"
    assert any("Type M" in n for n in notes)


def test_decide_joint_gate_blocks_positive():
    weak_joint = {"median_effect": 3.0, "direction_share": 0.4,
                  "stouffer_p": 0.001}
    v, _, notes = _decide(
        effect=5.0, p_adj=0.01, p_ab=0.9, alpha=0.05, gamma=0.75,
        joint=weak_joint, type_m=1.1, type_m_max=2.0,
        tost_pass=False, null_precision_warning=False)
    assert v == "undetermined"
    assert any("联合推断" in n for n in notes)


def test_decide_precision_warning_blocks_null():
    v, _, notes = _decide(
        effect=0.1, p_adj=0.6, p_ab=0.55, alpha=0.05, gamma=0.75,
        joint=_JOINT_OK, type_m=1.1, type_m_max=2.0,
        tost_pass=True, null_precision_warning=True)
    assert v == "undetermined"
    assert any("精度预警" in n for n in notes)


# ---------------------------------------------------------------- SESOI 登记

def test_register_sesoi_snapshot_and_hash(checked_pkg, tmp_path):
    src = write_design_source(tmp_path, sesoi=2.5)
    entry = register_sesoi(checked_pkg, src, "evaluation.sesoi")
    assert entry["sesoi_value"] == 2.5
    assert entry["sesoi_pointer"] == "evaluation.sesoi"
    assert len(entry["source_hash"]) == 64
    spec = load_package(checked_pkg)["analysis"]["spec"]
    # 缺省登记到全部可判行（L-OK / L-PART），终态行不在内
    assert set(spec["sesoi"]) == {"L-OK", "L-PART"}
    assert spec["judge_params"]["type_m_max"] == 2.0
    with pytest.raises(JudgeError):
        register_sesoi(checked_pkg, src, "evaluation.missing")


def test_judge_requires_checked_state(pkg, tmp_path):
    with pytest.raises(JudgeError) as ei:
        run_judge(pkg, write_judge_data(tmp_path, {}))
    assert any("checked" in g for g in ei.value.gaps)


def test_judge_without_sesoi_falls_undetermined(checked_pkg, tmp_path):
    data = write_judge_data(tmp_path, {"L-OK": STRONG_POS})
    summary = run_judge(checked_pkg, data, decided_by="analyst-x")
    row = _current(checked_pkg)["L-OK"]
    assert row["verdict"] == "undetermined"
    assert "SESOI 未在分析规格登记" in row["note"]
    assert summary["judged"] == []


def test_judge_unknown_line_rejected(checked_pkg, tmp_path):
    src = write_design_source(tmp_path)
    register_sesoi(checked_pkg, src, "evaluation.sesoi")
    data = write_judge_data(tmp_path, {"L-GHOST": STRONG_POS})
    with pytest.raises(JudgeError) as ei:
        run_judge(checked_pkg, data)
    assert any("未登记行" in g for g in ei.value.gaps)


def test_judge_unknown_field_rejected(checked_pkg, tmp_path):
    src = write_design_source(tmp_path)
    register_sesoi(checked_pkg, src, "evaluation.sesoi")
    data = write_judge_data(tmp_path, {
        "L-OK": {**STRONG_POS, "RefCountry": [1, 2, 3]}})  # BLADE 式幻觉列名
    with pytest.raises(JudgeError) as ei:
        run_judge(checked_pkg, data)
    assert any("未知字段" in g for g in ei.value.gaps)


# ---------------------------------------------------------------- 端到端落字

def test_judge_positive_end_to_end(checked_pkg, tmp_path):
    summary = do_judge(checked_pkg, tmp_path)
    cur = _current(checked_pkg)
    row = cur["L-OK"]
    assert row["verdict"] == "positive"
    assert row["quadrant"] == "significant_not_equivalent"
    assert row["basis_spec_id"] == "S001"
    assert row["p_ab"] >= 0.75
    assert row["type_sm"]["assumed_D"]["basis"] == "sesoi_frozen"
    assert row["type_sm"]["assumed_D"]["value"] == 2.0
    assert row["correction"]["method"] == "fdr_bh"
    assert row["correction"]["p_adj"] >= row["correction"]["p_raw"]
    assert row["strength_grade"] == "conclusive"
    assert row["joint"]["direction_share"] == 1.0
    assert row["calc_provenance"]["method"] == "welch_effect_and_ci"
    assert summary["primary_spec_id"] == "S001"
    # L-PART：TOST 本可过，但精度预警在案 → undetermined 并引预警
    part = cur["L-PART"]
    assert part["verdict"] == "undetermined"
    assert "精度预警" in part["note"]
    assert part["strength_grade"] is None
    # 整包校验 0 错误 + judged 门贯通（矩阵账平）
    assert validate_package(checked_pkg) == []
    assert advance_package(checked_pkg) == "judged"


def test_judge_bayes_missing_diagnostics_terminal_state(checked_pkg, tmp_path):
    # D-ANA-1 回归：贝叶斯行诊断整组缺失 → judge 落 undetermined 终态
    # 并登记 diagnostics_status=missing，整包 validate 零错误、门可推进
    bayes_line = dict(STRONG_POS, bayes=True)
    do_judge(checked_pkg, tmp_path,
             lines={"L-OK": bayes_line, "L-PART": NEAR_ZERO_PART})
    row = _current(checked_pkg)["L-OK"]
    assert row["verdict"] == "undetermined"
    assert row["diagnostics"] is None
    assert row["diagnostics_status"] == "missing"
    assert "贝叶斯诊断未过门" in row["note"]
    assert validate_package(checked_pkg) == []
    assert advance_package(checked_pkg) == "judged"


def test_judge_significant_but_equivalent(checked_pkg, tmp_path):
    small_real = {"treatment": [66.4, 66.6, 66.5, 66.4, 66.6, 66.5],
                  "reference": [65.0, 65.1, 64.9, 65.0, 65.1, 64.9]}
    do_judge(checked_pkg, tmp_path,
             lines={"L-OK": small_real, "L-PART": NEAR_ZERO_PART}, sesoi=5.0)
    row = _current(checked_pkg)["L-OK"]
    assert row["verdict"] == "positive"
    assert row["quadrant"] == "significant_but_equivalent"  # 存在但 <SESOI
    assert row["tost"]["result"] == "pass"
    assert validate_package(checked_pkg) == []


def test_judge_clean_null(checked_pkg, tmp_path):
    zero = {"treatment": [65, 66, 64, 65, 66, 64],
            "reference": [65, 64, 66, 65, 64, 66]}
    do_judge(checked_pkg, tmp_path,
             lines={"L-OK": zero, "L-PART": NEAR_ZERO_PART}, sesoi=2.0)
    row = _current(checked_pkg)["L-OK"]
    assert row["verdict"] == "null"
    assert row["quadrant"] == "equivalent_only"
    assert row["tost"]["bounds"]["source"] == "design_sesoi"
    assert validate_package(checked_pkg) == []


def test_judge_negative(checked_pkg, tmp_path):
    worse = {"treatment": [56, 54, 57, 55, 53, 55],
             "reference": [64, 66, 65, 63, 67, 65]}
    do_judge(checked_pkg, tmp_path,
             lines={"L-OK": worse, "L-PART": NEAR_ZERO_PART}, sesoi=2.0)
    row = _current(checked_pkg)["L-OK"]
    assert row["verdict"] == "negative"
    assert row["p_ab"] >= 0.75  # 判定方向（更劣）概率
    assert validate_package(checked_pkg) == []


def test_judge_type_m_blocks_positive_end_to_end(checked_pkg, tmp_path):
    # SESOI 远小于噪声：观测差虽大，但以 D=SESOI 计 Type M 远超阈值 2.0
    pattern = [-2.67, -1.39, -0.46, 0.46, 1.39, 2.67]
    noisy = {"treatment": [x + 3.0 for x in pattern], "reference": pattern}
    do_judge(checked_pkg, tmp_path,
             lines={"L-OK": noisy, "L-PART": NEAR_ZERO_PART}, sesoi=0.4)
    row = _current(checked_pkg)["L-OK"]
    assert row["verdict"] == "undetermined"
    assert "Type M" in row["note"]
    assert row["type_sm"]["type_m"] > 2.0


def test_judge_n_mismatch_falls_undetermined(checked_pkg, tmp_path):
    short = {"treatment": [72, 74, 73], "reference": [64, 66, 65, 63, 67, 65]}
    do_judge(checked_pkg, tmp_path,
             lines={"L-OK": short, "L-PART": NEAR_ZERO_PART})
    row = _current(checked_pkg)["L-OK"]
    assert row["verdict"] == "undetermined"
    assert "不一致" in row["note"]


def test_judge_summary_form_materials(checked_pkg, tmp_path):
    summary_form = {
        "treatment_summary": {"mean": 73.0, "spread": 2.0, "n": 6,
                              "replication_level": "segment"},
        "reference_summary": {"mean": 65.0, "spread": 2.0, "n": 6,
                              "replication_level": "segment"},
    }
    do_judge(checked_pkg, tmp_path,
             lines={"L-OK": summary_form, "L-PART": NEAR_ZERO_PART})
    row = _current(checked_pkg)["L-OK"]
    assert row["verdict"] == "positive"
    sr = load_package(checked_pkg)["spec_results"]
    med = [r for r in sr if r["spec_id"] == "S002"
           and r["registry_line_id"] == "L-OK"][0]
    assert "退化" in (med["note"] or "")  # 摘要材料下秩类规格退化口径落字


def test_judge_rerun_refused(checked_pkg, tmp_path):
    do_judge(checked_pkg, tmp_path)
    src = write_design_source(tmp_path)
    data = write_judge_data(tmp_path, {"L-OK": STRONG_POS}, name="d2.json")
    with pytest.raises(JudgeError) as ei:
        run_judge(checked_pkg, data)
    assert any("supersedes" in g for g in ei.value.gaps)
    assert src  # 来源文件在位（登记已在 do_judge 内完成）
