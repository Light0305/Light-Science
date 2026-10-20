"""ANA-D02：SESOI 结构化联动（登记行直读 + 一致性比对 + 缺失落 undetermined）。

覆盖 phase2-sesoi.md 验收 A7–A10：intake 捕获/拦截、主路登记、
结构化指针路、两处不一致必红、快照不完整落 undetermined、兼容路保留。
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from conftest import (
    NEAR_ZERO_PART, STRONG_POS, make_checked, make_upstream,
    write_design_source, write_judge_data,
)

from light_analysis.intake import IntakeError, run_intake
from light_analysis.judge import (
    JudgeError, register_sesoi, register_sesoi_from_registry, run_judge,
)
from light_analysis.project import init_package, load_package, save_analysis

BLOCK = {
    "value": 2.0, "unit": "MOTA 百分点", "direction": "higher",
    "bounds": "等价界取 ±value 对称双侧界",
    "basis": "承卡判别实验预写判读阈值（差 ≤2 点）",
    "estimand_ref": "claims.primary_claims[C1]",
    "summary_measure": "mean_diff",
}


def _upstream_with_blocks(tmp_path: Path, blocks: dict):
    """在 conftest 上游三件套的登记表里给指定行加 sesoi 块。

    blocks: {run_id 或 "*": block}；不在表内的行不带块。"""
    card_path, reg_path, dc_path = make_upstream(tmp_path)
    rows = [json.loads(x) for x in
            reg_path.read_text(encoding="utf-8").splitlines() if x.strip()]
    for r in rows:
        b = blocks.get(r["run_id"], blocks.get("*"))
        if b is not None:
            r["sesoi"] = copy.deepcopy(b)
    reg_path.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
        encoding="utf-8")
    return card_path, reg_path, dc_path


def _intaken(tmp_path: Path, blocks: dict, name="ana-sesoi") -> Path:
    root = tmp_path / "analyses" / name
    init_package(root, title="SESOI 联动测试包")
    card_path, reg_path, dc_path = _upstream_with_blocks(tmp_path, blocks)
    run_intake(root, card_path, reg_path, design_card_path=dc_path)
    return root


def _current_rows(root):
    pkg = load_package(root)
    rows = {}
    for r in pkg["verdicts"] or []:
        rows[r["registry_line_id"]] = r  # 夹具内每行只判一次，末行即现行
    return rows


# ---------------------------------------------------------------- A7 intake

def test_intake_captures_registry_block(tmp_path):
    root = _intaken(tmp_path, {"*": BLOCK})
    pkg = load_package(root)
    lines = {l["registry_line_id"]: l
             for l in pkg["analysis"]["registry_snapshot"]["lines"]}
    assert lines["L-OK"]["sesoi"] == BLOCK
    assert lines["L-PART"]["sesoi"] == BLOCK


def test_intake_rejects_incomplete_block(tmp_path):
    bad = {k: v for k, v in BLOCK.items() if k != "basis"}
    with pytest.raises(IntakeError) as e:
        _intaken(tmp_path, {"L-OK": bad, "L-PART": BLOCK})
    assert any("L-OK" in g and "不完整" in g for g in e.value.gaps)


def test_intake_rejects_inconsistent_blocks(tmp_path):
    other = dict(BLOCK, value=3.0)
    with pytest.raises(IntakeError) as e:
        _intaken(tmp_path, {"L-OK": BLOCK, "L-PART": other})
    assert any("不一致" in g for g in e.value.gaps)


# ---------------------------------------------------------------- A8 主路

def test_register_from_registry_then_judge(tmp_path):
    root = make_checked(_intaken(tmp_path, {"*": BLOCK}))
    res = register_sesoi_from_registry(root)
    assert set(res["registered"]) == {"L-OK", "L-PART"}
    assert res["skipped"] == []
    assert res["entry"]["via"] == "registry_row"
    assert res["entry"]["sesoi_block"]["basis"] == BLOCK["basis"]
    data = write_judge_data(tmp_path, {"L-OK": STRONG_POS,
                                       "L-PART": NEAR_ZERO_PART})
    summary = run_judge(root, data, decided_by="analyst-x")
    assert "L-OK" in summary["judged"]
    rows = _current_rows(root)
    assert rows["L-OK"]["verdict"] == "positive"
    assert "expected_registry.sesoi" in rows["L-OK"]["criteria_ref"]


def test_register_from_registry_without_blocks_errors(tmp_path):
    root = tmp_path / "analyses" / "ana-plain"
    init_package(root, title="无块包")
    card_path, reg_path, dc_path = make_upstream(tmp_path)
    run_intake(root, card_path, reg_path, design_card_path=dc_path)
    make_checked(root)
    with pytest.raises(JudgeError):
        register_sesoi_from_registry(root)


# ------------------------------------------------------- 结构化指针路 + 兼容路

def _checked_plain(tmp_path, name="ana-plain2"):
    root = tmp_path / "analyses" / name
    init_package(root, title="无块包")
    card_path, reg_path, dc_path = make_upstream(tmp_path)
    run_intake(root, card_path, reg_path, design_card_path=dc_path)
    return make_checked(root)


def test_structured_pointer_path_snapshots_block(tmp_path):
    root = _checked_plain(tmp_path)
    src = tmp_path / "design-block.json"
    src.write_text(json.dumps({"evaluation": {"sesoi": BLOCK}},
                              ensure_ascii=False), encoding="utf-8")
    entry = register_sesoi(root, src, "evaluation.sesoi")
    assert entry["via"] == "structured_block"
    assert entry["sesoi_value"] == 2.0
    assert entry["sesoi_block"]["estimand_ref"] == "claims.primary_claims[C1]"
    data = write_judge_data(tmp_path, {"L-OK": STRONG_POS,
                                       "L-PART": NEAR_ZERO_PART})
    summary = run_judge(root, data, decided_by="analyst-x")
    assert "L-OK" in summary["judged"]


def test_structured_pointer_incomplete_block_rejected(tmp_path):
    root = _checked_plain(tmp_path)
    bad = {k: v for k, v in BLOCK.items() if k != "estimand_ref"}
    src = tmp_path / "design-block-bad.json"
    src.write_text(json.dumps({"evaluation": {"sesoi": bad}},
                              ensure_ascii=False), encoding="utf-8")
    with pytest.raises(JudgeError) as e:
        register_sesoi(root, src, "evaluation.sesoi")
    assert any("不完整" in g for g in e.value.gaps)


def test_compat_pointer_entry_marked(tmp_path):
    root = _checked_plain(tmp_path)
    src = write_design_source(tmp_path, sesoi=2.0)
    entry = register_sesoi(root, src, "evaluation.sesoi")
    assert entry["via"] == "pointer_compat"
    assert "sesoi_block" not in entry


# ---------------------------------------------------------------- A9 不一致

def test_pointer_value_conflicts_registry_block_rejected(tmp_path):
    root = make_checked(_intaken(tmp_path, {"*": BLOCK}))
    src = write_design_source(tmp_path, sesoi=3.0)
    with pytest.raises(JudgeError) as e:
        register_sesoi(root, src, "evaluation.sesoi")
    assert any("不一致" in g and "L-OK" in g for g in e.value.gaps)


def test_judge_precheck_rejects_tampered_snapshot(tmp_path):
    root = make_checked(_intaken(tmp_path, {"*": BLOCK}))
    register_sesoi_from_registry(root)
    pkg = load_package(root)
    entry = pkg["analysis"]["spec"]["sesoi"]["L-OK"]
    entry["sesoi_value"] = 9.9
    entry["sesoi_block"]["value"] = 9.9  # 值与块自洽，但与登记行不符
    save_analysis(root, pkg["analysis"])
    data = write_judge_data(tmp_path, {"L-OK": STRONG_POS,
                                       "L-PART": NEAR_ZERO_PART})
    with pytest.raises(JudgeError) as e:
        run_judge(root, data, decided_by="analyst-x")
    assert any("不一致" in g for g in e.value.gaps)


# ---------------------------------------------------------------- A10 不完整

def test_incomplete_snapshot_entry_falls_undetermined(tmp_path):
    root = make_checked(_intaken(tmp_path, {"*": BLOCK}))
    register_sesoi_from_registry(root)
    pkg = load_package(root)
    entry = pkg["analysis"]["spec"]["sesoi"]["L-OK"]
    entry["sesoi_block"].pop("basis")  # 块残缺：judge 不许猜
    save_analysis(root, pkg["analysis"])
    data = write_judge_data(tmp_path, {"L-OK": STRONG_POS,
                                       "L-PART": NEAR_ZERO_PART})
    run_judge(root, data, decided_by="analyst-x")
    rows = _current_rows(root)
    assert rows["L-OK"]["verdict"] == "undetermined"
    assert "快照不完整" in rows["L-OK"]["note"]
    # 对照行（快照完整）照常判定：L-PART 带 null 精度预警落 undetermined，
    # 证明缺陷处理只作用于残缺行、不扩散到整包。
    assert rows["L-PART"]["verdict"] == "undetermined"
    assert "快照不完整" not in rows["L-PART"]["note"]
