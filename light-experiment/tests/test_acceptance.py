"""基线复现验收子流程（E1）：验收表冻结、冷启动证据纪律、闸门。"""

from __future__ import annotations

from pathlib import Path

import pytest

from light_experiment.acceptance import init_acceptance, record_leaf
from light_experiment.gates import GateError, advance_package
from light_experiment.project import (
    finish_run,
    intake,
    load_acceptance,
    load_package,
    new_run,
    save_acceptance,
    save_execution,
    start_run,
)

from conftest import SPEC, make_card, registry_line, write_export

DATE = "2026-10-20"
COLD_SPEC = {**SPEC, "cold_start": True}


def _baseline_export(tmp_path: Path) -> Path:
    card = make_card()
    card["contract"]["runs"].append(
        {"run_id": "R02", "role": "baseline", "control_run": None,
         "depends_on": [], "stage": "sanity"})
    lines = [registry_line("R00", "control"),
             registry_line("R01", "treatment", control_run="R00"),
             registry_line("R02", "baseline")]
    return write_export(tmp_path, card=card, lines=lines)


@pytest.fixture()
def baseline_pkg(project: Path, tmp_path: Path) -> tuple[Path, str]:
    execution, gaps = intake(project, _baseline_export(tmp_path))
    assert gaps == []
    return project, execution["exec_id"]


def _advance(root, exec_id, to, **kw):
    pkg = load_package(root, exec_id)
    advance_package(pkg, to, date=DATE, **kw)
    save_execution(root, pkg["execution"])
    return pkg


def _cold_rerun(root, exec_id) -> str:
    """执行期原样跑一条（R02-a1），再冷启动重跑一条（R02-a2）。"""
    start_run(root, exec_id, "R02-a1", spec=SPEC)
    finish_run(root, exec_id, "R02-a1", exit_status="completed")
    new_run(root, exec_id, "R02")
    start_run(root, exec_id, "R02-a2", spec=COLD_SPEC)
    finish_run(root, exec_id, "R02-a2", exit_status="completed")
    return "R02-a2"


def test_acceptance_gate_blocks_executing_without_table(baseline_pkg):
    root, exec_id = baseline_pkg
    _advance(root, exec_id, "sanity")
    pkg = load_package(root, exec_id)
    with pytest.raises(GateError, match="验收表未生成"):
        advance_package(pkg, "executing", date=DATE)


def test_acceptance_full_flow_and_gate(baseline_pkg):
    root, exec_id = baseline_pkg
    _advance(root, exec_id, "sanity")
    acc = init_acceptance(root, exec_id)
    assert [l["leaf_id"] for l in acc["leaves"]] == [
        "R02:implementation", "R02:execution", "R02:result"]
    assert acc["verdict"] == "incomplete"
    cold = _cold_rerun(root, exec_id)
    # 未判全 → executing 仍被拦
    pkg = load_package(root, exec_id)
    with pytest.raises(GateError, match="验收未通过"):
        advance_package(pkg, "executing", date=DATE)
    for leaf in ("R02:implementation", "R02:execution"):
        record_leaf(root, exec_id, leaf, verdict="pass", evidence_run=cold)
    record_leaf(root, exec_id, "R02:result", verdict="pass",
                evidence_run=cold, observed_value=99.0, expected_value=100.0)
    acc = load_acceptance(root, exec_id)
    assert acc["verdict"] == "passed"
    leaf = next(l for l in acc["leaves"] if l["leaf_id"] == "R02:result")
    assert leaf["deviation_pct"] == 1.0
    _advance(root, exec_id, "executing")  # 验收过 → 放行


def test_execution_period_product_rejected_as_evidence(baseline_pkg):
    root, exec_id = baseline_pkg
    init_acceptance(root, exec_id)
    start_run(root, exec_id, "R02-a1", spec=SPEC)  # 执行期产物，无冷启动锚
    finish_run(root, exec_id, "R02-a1", exit_status="completed")
    with pytest.raises(ValueError, match="冷启动"):
        record_leaf(root, exec_id, "R02:result", verdict="pass",
                    evidence_run="R02-a1", observed_value=99.0,
                    expected_value=100.0)


def test_evidence_run_must_match_leaf_entry(baseline_pkg):
    root, exec_id = baseline_pkg
    init_acceptance(root, exec_id)
    cold = _cold_rerun(root, exec_id)
    # 拿 R02 的冷启动 run 去给别的条目当证据——本表只有 R02 叶子，
    # 改用不存在/错位 run：R00 的尝试
    start_run(root, exec_id, "R00-a1", spec=COLD_SPEC)
    finish_run(root, exec_id, "R00-a1", exit_status="completed")
    with pytest.raises(ValueError, match="张冠李戴"):
        record_leaf(root, exec_id, "R02:result", verdict="pass",
                    evidence_run="R00-a1")
    assert cold == "R02-a2"


def test_acceptance_table_tamper_detected(baseline_pkg):
    root, exec_id = baseline_pkg
    init_acceptance(root, exec_id)
    acc = load_acceptance(root, exec_id)
    acc["leaves"][0]["weight"] = 99  # 冻结后改权重冒充
    save_acceptance(root, exec_id, acc)
    from light_experiment.schema import validate_package
    errs = validate_package(load_package(root, exec_id))
    assert any("leaves_hash" in e for e in errs)


def test_result_leaf_pass_beyond_tolerance_flagged(baseline_pkg):
    root, exec_id = baseline_pkg
    init_acceptance(root, exec_id)
    cold = _cold_rerun(root, exec_id)
    record_leaf(root, exec_id, "R02:result", verdict="pass",
                evidence_run=cold, observed_value=90.0, expected_value=100.0)
    from light_experiment.schema import validate_package
    errs = validate_package(load_package(root, exec_id))
    assert any("超过" in e and "容差" in e for e in errs)


def test_acceptance_init_requires_baseline(exec_pkg):
    root, exec_id = exec_pkg  # 一期夹具：无 baseline 条目
    with pytest.raises(ValueError, match="无基线可验收"):
        init_acceptance(root, exec_id)
