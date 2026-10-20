"""二期：交接四件套导出 export（D7）。"""

from __future__ import annotations

import json

import pytest

from conftest import clone, frozen_design, make_design
from light_design import cli
from light_design.export import ExportError, export_design, topo_order
from light_design.gates import advance
from light_design.project import save_design
from light_design.review import record_review_unavailable
from light_design.util import today

DID = "design_test_abc123"
FILES = ("experiment_brief.md", "design_card.json",
         "expected_registry.jsonl", "reproducibility.md")


def test_topo_order_dependency_first_regardless_of_declaration():
    runs = [
        {"run_id": "R-TREAT", "role": "treatment", "depends_on": ["R-CTRL"]},
        {"run_id": "R-ABL", "role": "ablation", "depends_on": ["R-TREAT"]},
        {"run_id": "R-CTRL", "role": "control", "depends_on": []},
    ]
    assert [r["run_id"] for r in topo_order(runs)] == ["R-CTRL", "R-TREAT", "R-ABL"]


def test_topo_order_cycle_rejected():
    runs = [{"run_id": "A", "depends_on": ["B"]},
            {"run_id": "B", "depends_on": ["A"]}]
    with pytest.raises(ExportError):
        topo_order(runs)


def test_export_draft_rejected_with_gaps(project):
    d = make_design()
    save_design(project, d)
    with pytest.raises(ExportError) as e:
        export_design(project, d)
    gaps = " ".join(e.value.errors)
    assert "未定版冻结" in gaps and "评审" in gaps  # 缺口逐条列明
    assert cli.main(["export", str(project), DID]) == 1


def test_export_reviewed_not_frozen_rejected(project):
    d = make_design()
    advance(d, "reviewed", date=today())
    save_design(project, d)
    with pytest.raises(ExportError) as e:
        export_design(project, d)
    assert any("reviewed" in x for x in e.value.errors)


def test_export_unavailable_review_gap_named(project):
    d = make_design()
    record_review_unavailable(project, d, date=today())
    with pytest.raises(ExportError) as e:
        export_design(project, d)
    assert any("REVIEW_UNAVAILABLE" in x for x in e.value.errors)


def test_export_frozen_four_files_and_contracts(project):
    d = frozen_design()
    save_design(project, d)
    out = export_design(project, d)
    for name in FILES:
        assert (out["dir"] / name).exists(), name
    # design_card.json：结构化全量投影
    card = json.loads(out["design_card"].read_text(encoding="utf-8"))
    assert card["design_id"] == DID and card["status"] == "frozen"
    assert card["claims"]["primary_claims"][0]["id"] == "C1"
    # expected_registry.jsonl：每 run 一行，含 readout 三向与主指标
    lines = [json.loads(x) for x in
             out["expected_registry"].read_text(encoding="utf-8").splitlines()]
    assert [x["run_id"] for x in lines] == ["R-CTRL", "R-TREAT"]
    for x in lines:
        assert set(x["readout"]) == {"positive", "negative", "null"}
        assert x["primary_metric"]["name"] == "MOTA"
        assert x["seeds"] == 5 and x["repetitions"] == 5
    assert lines[0]["expected"] == "复现附录 A 神谕值 ±2%"
    # brief：拓扑序小节 + 判读/熔断/预期齐全
    brief = out["brief"].read_text(encoding="utf-8")
    assert brief.index("### 1. R-CTRL") < brief.index("### 2. R-TREAT")
    assert "判读·正" in brief and "熔断线" in brief
    assert "复现附录 A 神谕值 ±2%" in brief
    # reproducibility：种子/环境/调参对等/哈希
    repro = out["reproducibility"].read_text(encoding="utf-8")
    assert "种子数：5" in repro and "torch" in repro
    assert "同等调参预算" in repro
    assert d["freeze"]["content_hash"] in repro


def test_export_topo_order_in_registry_when_declared_reversed(project):
    d = make_design()
    d["contract"]["runs"] = list(reversed(d["contract"]["runs"]))
    from conftest import add_review
    add_review(d)
    advance(d, "reviewed", date=today())
    advance(d, "frozen", date=today())
    save_design(project, d)
    out = export_design(project, d)
    lines = [json.loads(x) for x in
             out["expected_registry"].read_text(encoding="utf-8").splitlines()]
    assert [x["run_id"] for x in lines] == ["R-CTRL", "R-TREAT"]


def test_export_after_amendment_uses_current_hash(project):
    from light_design.gates import apply_amendment
    d = frozen_design()
    amd = apply_amendment(d, "plan.blocking_stratification", "按时长分层",
                          reason="补充分层", results_seen="未跑任何运行",
                          date=today())
    save_design(project, d)
    out = export_design(project, d)
    lines = [json.loads(x) for x in
             out["expected_registry"].read_text(encoding="utf-8").splitlines()]
    assert lines[0]["content_hash"] == amd["new_hash"]


def test_export_via_cli(project):
    d = frozen_design()
    save_design(project, d)
    assert cli.main(["export", str(project), DID]) == 0
    for name in FILES:
        assert (project / "exports" / DID / name).exists()
