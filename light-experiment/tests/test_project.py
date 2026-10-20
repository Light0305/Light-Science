"""项目骨架与 E0 承接（intake 打回纪律）。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from light_experiment.gates import GateError, advance_package
from light_experiment.project import (
    IntakeError,
    init_project,
    intake,
    list_runs,
    load_package,
    new_run,
)
from light_experiment.schema import validate_package

from conftest import DESIGN_HASH, make_card, registry_line, write_export


def test_init_creates_skeleton_and_refuses_overwrite(tmp_path: Path):
    root = tmp_path / "p"
    init_project(root, "方向")
    assert (root / "project.yaml").exists()
    assert (root / "experiment-stage" / "intake_log.md").exists()
    assert (root / "executions").is_dir()
    with pytest.raises(FileExistsError):
        init_project(root, "方向")


def test_intake_success_builds_package(project: Path, export_dir: Path):
    execution, gaps = intake(project, export_dir)
    assert gaps == []
    assert execution["exec_id"].endswith("-b1")
    assert execution["design_ref"]["content_hash"] == DESIGN_HASH
    runs = list_runs(project, execution["exec_id"])
    assert [r["run_id"] for r in runs] == ["R00-a1", "R01-a1"]
    assert all(r["status"] == "planned" for r in runs)
    pkg = load_package(project, execution["exec_id"])
    rows = pkg["reconciliation"]["rows"]
    assert [r["registry_run_id"] for r in rows] == ["R00", "R01"]
    assert rows[1]["run_ids"] == ["R01-a1"]
    assert validate_package(pkg) == []


def test_intake_second_batch_gets_b2(project: Path, export_dir: Path):
    e1, _ = intake(project, export_dir)
    e2, _ = intake(project, export_dir)
    assert e1["exec_id"].endswith("-b1")
    assert e2["exec_id"].endswith("-b2")


def test_intake_missing_file_is_gap_not_crash(project: Path, tmp_path: Path):
    out = write_export(tmp_path, skip=("reproducibility.md",))
    execution, gaps = intake(project, out)
    assert any("reproducibility.md" in g for g in gaps)
    assert execution["status"] == "intake"
    assert list_runs(project, execution["exec_id"]) == []
    # 缺口未清零 → advance 到 sanity 被门拦
    pkg = load_package(project, execution["exec_id"])
    with pytest.raises(GateError):
        advance_package(pkg, "sanity", date="2026-10-20")


def test_intake_non_frozen_design_rejected(project: Path, tmp_path: Path):
    out = write_export(tmp_path, card=make_card(status="reviewed"))
    _, gaps = intake(project, out)
    assert any("只消费 frozen" in g for g in gaps)


def test_intake_registry_hash_mismatch(project: Path, tmp_path: Path):
    bad = registry_line("R01", "treatment", control_run="R00")
    bad["content_hash"] = "0" * 64
    out = write_export(tmp_path, lines=[registry_line("R00", "control"), bad])
    _, gaps = intake(project, out)
    assert any("content_hash" in g and "R01" in g for g in gaps)


def test_intake_registry_missing_run(project: Path, tmp_path: Path):
    out = write_export(tmp_path, lines=[registry_line("R00", "control")])
    _, gaps = intake(project, out)
    assert any("不一一对应" in g for g in gaps)


def test_intake_brief_hash_not_pinned(project: Path, tmp_path: Path):
    out = write_export(tmp_path, brief="# 清单（忘了钉哈希）\n")
    _, gaps = intake(project, out)
    assert any("experiment_brief.md" in g and "哈希" in g for g in gaps)


def test_intake_readout_three_ways_required(project: Path, tmp_path: Path):
    bad = registry_line("R00", "control")
    bad["readout"] = {"positive": {"meaning": "x"}}
    out = write_export(tmp_path, lines=[bad, registry_line("R01", "treatment", "R00")])
    _, gaps = intake(project, out)
    assert any("判读三向不齐" in g for g in gaps)


def test_intake_unparseable_card_raises(project: Path, tmp_path: Path):
    out = write_export(tmp_path)
    (out / "design_card.json").write_text("{不是 json", encoding="utf-8")
    with pytest.raises(IntakeError):
        intake(project, out)


def test_intake_amendment_chain_hash(project: Path, tmp_path: Path):
    """有 amendment 的设计：现行哈希取链尾 new_hash，四件套须钉现行哈希。"""
    card = make_card()
    new_hash = "f" * 64
    card["freeze"]["amendments"] = [
        {"date": "2026-10-20", "fields": ["resources.budget"], "new_hash": new_hash}]
    lines = []
    for lid, role, ctl in (("R00", "control", None), ("R01", "treatment", "R00")):
        line = registry_line(lid, role, control_run=ctl)
        line["content_hash"] = new_hash
        lines.append(line)
    out = write_export(tmp_path, card=card, lines=lines,
                       brief=f"# 清单\n> 🔒 冻结哈希 `{new_hash}`\n",
                       repro=f"# 复现\n- 内容哈希：`{new_hash}`\n")
    execution, gaps = intake(project, out)
    assert gaps == []
    assert execution["design_ref"]["content_hash"] == new_hash
    assert execution["design_ref"]["frozen_content_hash"] == DESIGN_HASH
    assert execution["design_ref"]["amendments"] == 1


def test_new_run_unknown_brief_entry(exec_pkg):
    root, exec_id = exec_pkg
    with pytest.raises(ValueError, match="运行清单里没有条目"):
        new_run(root, exec_id, "R99")


def test_new_run_refused_when_intake_gapped(project: Path, tmp_path: Path):
    out = write_export(tmp_path, skip=("reproducibility.md",))
    execution, gaps = intake(project, out)
    assert gaps
    with pytest.raises(ValueError, match="承接未清零"):
        new_run(root=project, exec_id=execution["exec_id"], design_run_id="R00")


def test_intake_log_records_roundtrip(project: Path, tmp_path: Path):
    out = write_export(tmp_path, skip=("reproducibility.md",))
    intake(project, out)
    intake(project, export_dir := write_export(tmp_path / "second"))
    log = (project / "experiment-stage" / "intake_log.md").read_text(encoding="utf-8")
    assert "打回 1 项" in log
    assert "承接齐全" in log


# ---------- v1.1 承接补三件（EXP-D04） ----------

def test_intake_placeholder_scan_gap(project: Path, tmp_path: Path):
    brief = (f"# 实验运行清单\n\n> 🔒 冻结哈希 `{DESIGN_HASH}`\n\n"
             "R01 的 theta 取值 TODO 待填\n")
    out = write_export(tmp_path, brief=brief)
    _, gaps = intake(project, out)
    assert any("占位符" in g and "experiment_brief.md" in g for g in gaps)


def test_intake_placeholder_scan_clean_docs_pass(project: Path, export_dir: Path):
    """干净交接件零误报：夹具四件套含判读文本（差 <1 点之类）不许中招。"""
    _, gaps = intake(project, export_dir)
    assert not any("占位符" in g for g in gaps)


def test_intake_treatment_without_checkpoints_gap(project: Path, tmp_path: Path):
    card = make_card()
    del card["plan"]
    out = write_export(tmp_path, card=card)
    _, gaps = intake(project, out)
    assert any("干预核查点" in g and "R01" in g for g in gaps)


def test_intake_per_run_checkpoints_suffice(project: Path, tmp_path: Path):
    """设计级未声明时，条目级（登记行）声明核查点亦算齐备。"""
    card = make_card()
    del card["plan"]
    line = registry_line("R01", "treatment", control_run="R00")
    line["intervention_checks"] = [{"point": "theta_source 实际生效",
                                    "claimed": "predicted"}]
    out = write_export(tmp_path, card=card,
                       lines=[registry_line("R00", "control"), line])
    _, gaps = intake(project, out)
    assert gaps == []


def test_intake_dependency_plan_written(project: Path, export_dir: Path):
    execution, gaps = intake(project, export_dir)
    assert gaps == []
    assert execution["intake_report"]["execution_plan"] == ["R00", "R01"]
    plan = (project / "executions" / execution["exec_id"]
            / "execution_plan.md").read_text(encoding="utf-8")
    assert plan.index("R00") < plan.index("R01")
    assert "依赖计划" in plan


def test_intake_dependency_cycle_is_gap(project: Path, tmp_path: Path):
    card = make_card()
    card["contract"]["runs"][0]["depends_on"] = ["R01"]
    out = write_export(tmp_path, card=card)
    _, gaps = intake(project, out)
    assert any("成环" in g for g in gaps)


def test_intake_unknown_dependency_is_gap(project: Path, tmp_path: Path):
    card = make_card()
    card["contract"]["runs"][1]["depends_on"] = ["R00", "R99"]
    out = write_export(tmp_path, card=card)
    _, gaps = intake(project, out)
    assert any("不在 brief 运行清单内" in g and "R99" in g for g in gaps)
