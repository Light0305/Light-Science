"""结论包填充与交接（Phase 2）：主张映射规则、强度机械合成、溯源完整、
export 投影、回流 ≤1 轮。另建一个全 positive 的两行小包测 supported 路径。"""

import json
from pathlib import Path

import pytest

from conftest import STRONG_POS, do_judge, reg_row, _rec, _run
from light_analysis.conclude import ConcludeError, export_conclusion, run_grade
from light_analysis.gates import advance_package
from light_analysis.intake import run_intake
from light_analysis.judge import JudgeError, request_reflux
from light_analysis.project import init_package, load_package

CONTENT_HASH = "a" * 64


def _graded(root, tmp_path):
    do_judge(root, tmp_path)
    assert advance_package(root) == "judged"
    notes = tmp_path / "notes.json"
    notes.write_text(json.dumps({
        "boundaries": [{"claim_id": "C1", "conditions": "当前材料内",
                        "not_extrapolatable": "未检验臂",
                        "would_change_if": "新执行包重判"}],
        "limitations": ["演示材料局限"],
    }, ensure_ascii=False), encoding="utf-8")
    summary = run_grade(root, notes_path=notes)
    assert advance_package(root) == "graded"
    return summary


def test_grade_main_fixture_untested_claim(checked_pkg, tmp_path):
    # 六行包：C1 含 3 条 untested 预登记行 → 主张落 untested、强度 insufficient
    summary = _graded(checked_pkg, tmp_path)
    assert summary["claims"] == {"C1": "untested"}
    assert summary["grades"] == {"C1": "insufficient"}
    conclusions = load_package(checked_pkg)["conclusions"]
    cv = conclusions["claims_verdict"][0]
    assert cv["line_verdicts"]["L-OK"] == "positive"
    assert cv["line_verdicts"]["L-VOID"] == "untested"
    st = conclusions["strength"][0]
    assert st["inputs"]["line_verdicts"]["L-PART"] == "undetermined"
    assert "未检验" in st["cap_reason"]


def test_provenance_covers_every_direction_number(checked_pkg, tmp_path):
    _graded(checked_pkg, tmp_path)
    pkg = load_package(checked_pkg)
    conclusions = pkg["conclusions"]
    from light_analysis.project import current_verdicts
    current = current_verdicts(pkg["verdicts"])
    prov = {(p["registry_line_id"], p["quantity"])
            for p in conclusions["number_provenance"]}
    for lid, row in current.items():
        if row.get("effect_size"):
            assert (lid, "effect_size") in prov
            entry = next(p for p in conclusions["number_provenance"]
                         if p["registry_line_id"] == lid
                         and p["quantity"] == "effect_size")
            assert entry["value"] == row["effect_size"]["value"]
            assert entry["verdict_line"] == row["row_ref"]
            assert entry["spec_id"] == row["basis_spec_id"]


def test_export_conclusion_card(checked_pkg, tmp_path):
    _graded(checked_pkg, tmp_path)
    out = export_conclusion(checked_pkg)
    card = json.loads(Path(out["conclusion_card"]).read_text(encoding="utf-8"))
    assert card["kind"] == "light-analysis/conclusion-card"
    assert card["claims"][0]["claim_id"] == "C1"
    assert card["claims"][0]["support"] == "untested"
    assert card["claims"][0]["grade"] == "insufficient"
    assert len(card["number_provenance"]) == \
        len(load_package(checked_pkg)["conclusions"]["number_provenance"])
    assert Path(out["report"]).exists()


def test_grade_before_judged_rejected(checked_pkg):
    with pytest.raises(ConcludeError):
        run_grade(checked_pkg)


# ---------------------------------------------------------------- 全 positive 小包

def _two_line_pkg(tmp_path):
    lines = ["T-1", "T-2"]
    registry = [reg_row(l) for l in lines]
    card = {
        "exec_id": "exec-two", "status": "delivered",
        "design_ref": {"design_id": "d1", "content_hash": CONTENT_HASH},
        "runs": [_run("T-1-a1", "T-1"), _run("T-2-a1", "T-2")],
        "reconciliation": {"content_hash": CONTENT_HASH, "rows": [
            _rec("T-1", ["T-1-a1"]), _rec("T-2", ["T-2-a1"])]},
        "deviations": [], "failures": [],
    }
    up = tmp_path / "up2"
    up.mkdir(exist_ok=True)
    (up / "execution_card.json").write_text(
        json.dumps(card, ensure_ascii=False), encoding="utf-8")
    (up / "expected_registry.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in registry),
        encoding="utf-8")
    root = tmp_path / "ana-two"
    init_package(root, title="两行包")
    run_intake(root, up / "execution_card.json", up / "expected_registry.jsonl")
    from conftest import make_checked
    return make_checked(root)


def test_supported_claim_and_grade_synthesis(tmp_path):
    root = _two_line_pkg(tmp_path)
    do_judge(root, tmp_path,
             lines={"T-1": STRONG_POS, "T-2": STRONG_POS})
    assert advance_package(root) == "judged"
    summary = run_grade(root)
    assert summary["claims"] == {"C1": "supported"}
    # 两行全票同向 + Type M 余量足 → conclusive（机械合成，非手填）
    assert summary["grades"] == {"C1": "conclusive"}


def test_partial_claim_capped_suggestive(tmp_path):
    root = _two_line_pkg(tmp_path)
    worse = {"treatment": [56, 54, 57, 55, 53, 55],
             "reference": [64, 66, 65, 63, 67, 65]}
    do_judge(root, tmp_path, lines={"T-1": STRONG_POS, "T-2": worse})
    assert advance_package(root) == "judged"
    summary = run_grade(root)
    assert summary["claims"] == {"C1": "partial"}
    assert summary["grades"]["C1"] == "suggestive"  # partial 封顶


# ---------------------------------------------------------------- 回流

def test_reflux_supplementary_only_one_round(checked_pkg):
    entry = request_reflux(checked_pkg, "supplementary_ablation",
                           ["L-PART"], "关键消融行材料不足，补跑后可复判")
    assert entry["reflux_id"] == "RX-A001"
    assert entry["target"] == "experiment"
    assert Path(entry["file"]).exists()
    with pytest.raises(JudgeError) as ei:
        request_reflux(checked_pkg, "supplementary_ablation",
                       ["L-OK"], "再补一轮")
    assert any("1 轮" in g for g in ei.value.gaps)
    # 标准缺失回 Design 不占消融轮次
    gap = request_reflux(checked_pkg, "standard_gap", ["L-INC"],
                         "登记行判据缺 readout 阈值字段")
    assert gap["target"] == "design"
    conclusions = load_package(checked_pkg)["conclusions"]
    assert len(conclusions["reflux"]) == 2
