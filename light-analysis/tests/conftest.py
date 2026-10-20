"""测试夹具：构造上游输入（execution_card + expected_registry）与已承接分析包。

登记行六条，覆盖 A0 全部可判性分支：
  L-OK    正常可判
  L-VOID  支撑 run 全部作废 → untested 候选
  L-FUND  fundamental 失败 → untested 候选（且 n=2<6 带精度预警）
  L-PART  覆盖 n=4<6 → 可判 + null 精度预警
  L-MISS  无对账行 → untested 候选
  L-INC   事实层 incomparable → undetermined 候选
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from light_analysis import schema
from light_analysis.intake import run_intake
from light_analysis.project import (
    assign_row_refs, init_package, load_package, refresh_counts,
    save_analysis, save_verdicts,
)
from light_analysis.specs import build_ledger, freeze_ledger

CONTENT_HASH = "a" * 64
REPO_ROOT = Path(__file__).resolve().parents[2]


def reg_row(run_id, claim="C1", repetitions=6):
    return {
        "design_id": "d1", "run_id": run_id, "role": "treatment",
        "control_run": None, "stage": "main",
        "primary_metric": {"name": "MOTA", "direction": "higher"},
        "readout": {"positive": {"meaning": "p"}, "negative": {"meaning": "n"},
                    "null": {"meaning": "u"}},
        "expected": None, "seeds": 3, "repetitions": repetitions,
        "claim_ref": claim, "content_hash": CONTENT_HASH,
    }


def _run(run_id, design_id, **kw):
    base = {"run_id": run_id, "design_run_id": design_id, "attempt": 1,
            "status": "reconciled", "exit_status": "completed",
            "identity_hash": "b" * 64, "voided_by": [], "failure_ref": None}
    base.update(kw)
    return base


def _rec(line, run_ids, n=6, verdict="within"):
    return {
        "registry_run_id": line, "run_ids": run_ids, "status": "filled",
        "readout_actual": {"mean": 70.0, "spread": 2.0, "n": n,
                           "replication_level": "segment"},
        "layers": {"implementation": True, "execution": True,
                   "result_fact": {"verdict": verdict, "reason": "事实层"}},
        "deviations": [], "evidence": [],
        "random_sources": {"rerandomized": [], "frozen": [],
                           "bias_warnings": []},
    }


def make_upstream(tmp_path: Path):
    """写出 card/registry/design_card 三件套，返回路径三元组。"""
    lines = ["L-OK", "L-VOID", "L-FUND", "L-PART", "L-MISS", "L-INC"]
    registry = [reg_row(l) for l in lines]
    card = {
        "exec_id": "exec-test-1",
        "design_ref": {"design_id": "d1", "content_hash": CONTENT_HASH},
        "status": "delivered",
        "runs": [
            _run("L-OK-a1", "L-OK"),
            _run("L-VOID-a1", "L-VOID", voided_by=["DV-0001"]),
            _run("L-FUND-a1", "L-FUND", exit_status="failed_data",
                 failure_ref="F-0001"),
            _run("L-PART-a1", "L-PART"),
            _run("L-INC-a1", "L-INC"),
        ],
        "reconciliation": {
            "content_hash": CONTENT_HASH,
            "rows": [
                _rec("L-OK", ["L-OK-a1"]),
                _rec("L-VOID", ["L-VOID-a1"]),
                _rec("L-FUND", ["L-FUND-a1"], n=2),
                _rec("L-PART", ["L-PART-a1"], n=4),
                _rec("L-INC", ["L-INC-a1"], verdict="incomparable"),
            ],
        },
        "deviations": [{"deviation_id": "DV-0001", "type": "config",
                        "disposition": "void_and_rerun",
                        "invalidated": ["L-VOID-a1"]}],
        "failures": [{"failure_id": "F-0001", "run_id": "L-FUND-a1",
                      "mast_code": "FM-2.3", "failure_class": "fundamental",
                      "reflux_target": "design", "reflux_status": "pending"}],
    }
    up = tmp_path / "upstream"
    up.mkdir(exist_ok=True)
    card_path = up / "execution_card.json"
    card_path.write_text(json.dumps(card, ensure_ascii=False), encoding="utf-8")
    reg_path = up / "expected_registry.jsonl"
    reg_path.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in registry),
        encoding="utf-8")
    dc_path = up / "design_card.json"
    dc_path.write_text(json.dumps(
        {"design_id": "d1",
         "claims": {"primary_claims": [{"id": "C1", "statement": "主张一"}]}},
        ensure_ascii=False), encoding="utf-8")
    return card_path, reg_path, dc_path


@pytest.fixture()
def upstream(tmp_path):
    return make_upstream(tmp_path)


@pytest.fixture()
def pkg(tmp_path, upstream):
    """已 init + intake 的分析包根目录。"""
    root = tmp_path / "analyses" / "ana-test"
    init_package(root, title="测试分析包")
    card_path, reg_path, dc_path = upstream
    run_intake(root, card_path, reg_path, design_card_path=dc_path)
    return root


# ---------------------------------------------------------------- 辅助

def write_verdicts(root, rows):
    """落判定行并同步机械计数（校验器会核 counts，不许手填只能这样刷）。"""
    rows = assign_row_refs([dict(r) for r in rows])
    save_verdicts(root, rows)
    pkg = load_package(root)
    refresh_counts(pkg["analysis"], rows)
    save_analysis(root, pkg["analysis"])
    return rows


def existing_rows(root):
    return load_package(root)["verdicts"] or []


def family_id_of(root):
    pkg = load_package(root)
    return pkg["analysis"]["correction_families"][0]["family_id"]


def valid_row(root, line, verdict, **over):
    """构造一条字段完备的判定行（按 verdict 类型补齐各组）。"""
    fam = family_id_of(root)
    row = schema.verdict_row(
        line, verdict, claim_ref="C1",
        note="按冻结判据落字", decided_by="analyst-x", decided_at="2026-10-20")
    if verdict in schema.DIRECTIONAL_VERDICTS:
        row.update({
            "basis_spec_id": "S001",
            "criteria_ref": "登记行 readout 标准",
            "direction": "higher",
            "effect_size": {"type": "mean_diff", "value": 5.2},
            "interval": {"kind": "ci", "level": 0.95, "lo": 1.0, "hi": 9.4},
            "correction": {"family_id": fam, "method": "fdr_bh",
                           "p_raw": 0.01, "p_adj": 0.04},
            "n_effective": 6, "n_registered": 6,
            "strength_grade": "strong",
            "strength_cap_reason": "稳健档封顶",
        })
    if verdict == "positive":
        row.update({
            "quadrant": "significant_not_equivalent",
            "p_ab": 0.83,
            "type_sm": {
                "assumed_D": {"value": 2.0, "basis": "sesoi_frozen",
                              "source_ref": "design sesoi"},
                "power": 0.8, "type_s": 0.01, "type_m": 1.2},
        })
    if verdict == "negative":
        row["quadrant"] = "significant_not_equivalent"
    if verdict == "null":
        row.update({
            "quadrant": "equivalent_only",
            "tost": {"bounds": {"lo": -2.0, "hi": 2.0,
                                "source": "design_sesoi"},
                     "p_tost": 0.03, "ci90": {"lo": -0.5, "hi": 0.8},
                     "ci90_in_bounds": True, "result": "pass"},
        })
    if verdict == "undetermined":
        row["quadrant"] = "undetermined"
        row["strength_grade"] = None
    if verdict in ("undetermined", "untested"):
        row["strength_grade"] = None
    row.update(over)
    return row


def frozen_ledger(root):
    """给包写入一个已冻结的最小账本（1 决策点 × 2 选项，S001/S002 均 included）。"""
    from light_analysis.project import save_ledger
    ledger = build_ledger([{
        "point": "estimator",
        "options": ["mean_diff", "median_diff"],
        "theoretical_justification": "登记规格的主估计量与稳健替代各一",
    }])
    freeze_ledger(ledger)
    save_ledger(root, ledger)
    return ledger


# ---------------------------------------------------------------- Phase 2 夹具

def make_checked(pkg_root):
    """把 pkg 夹具的包推进到 checked（冻结账本 + advance）。"""
    from light_analysis.gates import advance_package
    frozen_ledger(pkg_root)
    assert advance_package(pkg_root) == "checked"
    return pkg_root


@pytest.fixture()
def checked_pkg(pkg):
    return make_checked(pkg)


def write_design_source(tmp_path: Path, sesoi=2.0):
    """写一个带 SESOI 的 Design 来源文件，指针 evaluation.sesoi。"""
    p = tmp_path / "design-source.json"
    p.write_text(json.dumps({"design_id": "d1",
                             "evaluation": {"sesoi": sesoi}}),
                 encoding="utf-8")
    return p


def write_judge_data(tmp_path: Path, lines, name="judge-data.json"):
    p = tmp_path / name
    p.write_text(json.dumps({"lines": lines}, ensure_ascii=False),
                 encoding="utf-8")
    return p


# L-OK 强正向（diff≈8.2，SESOI=2 时稳健 positive）；L-PART 近零效应
# （TOST 本可过，但承接 null 精度预警在案 → 只许 undetermined）。
STRONG_POS = {"treatment": [72, 74, 73, 75, 71, 74],
              "reference": [64, 66, 65, 63, 67, 65],
              "reference_label": "baseline-arm"}
NEAR_ZERO_PART = {"treatment": [65, 66, 64, 65],
                  "reference": [65, 64, 66, 65],
                  "reference_label": "baseline-arm"}


def do_judge(root, tmp_path, lines=None, sesoi=2.0):
    """登记 SESOI + 跑 judge 的标准动作，返回 judge 汇总。"""
    from light_analysis.judge import register_sesoi, run_judge
    src = write_design_source(tmp_path, sesoi=sesoi)
    register_sesoi(root, src, "evaluation.sesoi")
    if lines is None:
        lines = {"L-OK": STRONG_POS, "L-PART": NEAR_ZERO_PART}
    data = write_judge_data(tmp_path, lines)
    return run_judge(root, data, decided_by="analyst-x")
