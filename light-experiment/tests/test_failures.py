"""失败分类与回流（E5）：双层分类规则、自动回流、签名预算、抽验。"""

from __future__ import annotations

from pathlib import Path

import pytest

from light_experiment.failures import (
    classify_failure,
    review_failure,
    update_reflux_entry,
)
from light_experiment.gates import GateError
from light_experiment.project import (
    finish_run,
    load_package,
    load_run,
    new_run,
    start_run,
)
from light_experiment.schema import validate_package

from conftest import SPEC


def _fail(root, exec_id, design_run_id="R01", attempt_run=None, exit_status="failed_error"):
    if attempt_run is None:
        attempt_run = f"{design_run_id}-a1"
        start_run(root, exec_id, attempt_run, spec=SPEC)
    else:
        new_run(root, exec_id, design_run_id, retry_of=_prev(attempt_run))
        start_run(root, exec_id, attempt_run, spec=SPEC)
    finish_run(root, exec_id, attempt_run, exit_status=exit_status,
               no_salvage=True)
    return attempt_run


def _prev(run_id: str) -> str:
    head, _, tail = run_id.rpartition("-a")
    return f"{head}-a{int(tail) - 1}"


def test_implementation_requires_retry_guidance(exec_pkg):
    root, exec_id = exec_pkg
    rid = _fail(root, exec_id)
    with pytest.raises(ValueError, match="retry_guidance"):
        classify_failure(root, exec_id, run_id=rid, mast_code="FM-1.3",
                         failure_class="implementation")


def test_fundamental_requires_root_cause_and_boundary(exec_pkg):
    root, exec_id = exec_pkg
    rid = _fail(root, exec_id)
    with pytest.raises(ValueError, match="root_cause"):
        classify_failure(root, exec_id, run_id=rid, mast_code="FM-2.3",
                         failure_class="fundamental",
                         boundary_conditions="仅自建集")
    with pytest.raises(ValueError, match="boundary_conditions"):
        classify_failure(root, exec_id, run_id=rid, mast_code="FM-2.3",
                         failure_class="fundamental", root_cause="映射不存在")


def test_classify_implementation_emits_retry_queue(exec_pkg):
    root, exec_id = exec_pkg
    rid = _fail(root, exec_id)
    rec = classify_failure(root, exec_id, run_id=rid, mast_code="FM-1.3",
                           failure_class="implementation",
                           root_cause="阈值回归器拟合发散",
                           retry_guidance="改 Huber 损失后重试",
                           attempt_kind="patch")
    assert rec["failure_id"] == "F-0001"
    assert rec["reflux_target"] == "experiment"
    run = load_run(root, exec_id, rid)
    assert run["conclusion"]["failure_ref"] == "F-0001"
    pkg = load_package(root, exec_id)
    queue = pkg["reflux"]["retry_queue"]
    assert len(queue) == 1 and queue[0]["kind"] == "retry"
    assert queue[0]["status"] == "pending"
    assert validate_package(pkg) == []
    # 重复分类被拦
    with pytest.raises(GateError, match="已有失败分类"):
        classify_failure(root, exec_id, run_id=rid, mast_code="FM-1.3",
                         failure_class="implementation",
                         retry_guidance="再试")


def test_classify_fundamental_emits_design_inbox_and_dossier(exec_pkg):
    root, exec_id = exec_pkg
    rid = _fail(root, exec_id, design_run_id="R00", exit_status="failed_data")
    rec = classify_failure(root, exec_id, run_id=rid, mast_code="FM-2.3",
                           failure_class="fundamental",
                           root_cause="统计量→阈值映射在留出段不存在",
                           boundary_conditions="6 段自建集与 MOT17 先行验证内",
                           idea_bound=True)
    assert rec["reflux_target"] == "idea"
    pkg = load_package(root, exec_id)
    inbox = pkg["reflux"]["design_inbox"]
    assert len(inbox) == 1 and inbox[0]["kind"] == "design_failure"
    assert pkg["reflux"]["idea_dossiers"] == ["F-0001.md"]
    dossier = (root / "executions" / exec_id / "reflux" / "idea_dossiers"
               / "F-0001.md").read_text(encoding="utf-8")
    assert "映射在留出段不存在" in dossier


def test_signature_budget_alarms_on_third_patch(exec_pkg):
    root, exec_id = exec_pkg
    rids = [_fail(root, exec_id, attempt_run=None)]
    rids.append(_fail(root, exec_id, attempt_run="R01-a2"))
    rids.append(_fail(root, exec_id, attempt_run="R01-a3"))
    rec = None
    for rid in rids:
        rec = classify_failure(root, exec_id, run_id=rid, mast_code="FM-1.3",
                               failure_class="implementation",
                               root_cause="同一处拟合发散",
                               retry_guidance="换损失",
                               attempt_kind="patch")
    assert rec["budget_exceeded"] is True  # 2 补丁预算已用满，第三次报警
    errs = validate_package(load_package(root, exec_id))
    assert any("失败签名预算超限" in e for e in errs)
    events = load_package(root, exec_id)["events"]
    assert any(e["type"] == "budget_event" for e in events)


def test_review_and_reflux_status_tracking(exec_pkg):
    root, exec_id = exec_pkg
    rid = _fail(root, exec_id)
    rec = classify_failure(root, exec_id, run_id=rid, mast_code="FM-3.2",
                           failure_class="implementation",
                           retry_guidance="补干预核查后重跑")
    review_failure(root, exec_id, rec["failure_id"], reviewer="用户",
                   agrees=True, note="抽验同意")
    pkg = load_package(root, exec_id)
    folded = pkg["failures"][0]
    assert folded["classification_review"]["reviewer"] == "用户"
    entry_id = pkg["reflux"]["retry_queue"][0]["entry_id"]
    update_reflux_entry(root, exec_id, entry_id, status="sent")
    pkg = load_package(root, exec_id)
    assert pkg["failures"][0]["reflux_status"] == "sent"
    from light_experiment.failures import reflux_status_of
    assert reflux_status_of(pkg["reflux"]["retry_queue"], entry_id) == "sent"


def test_classify_unknown_mast_rejected(exec_pkg):
    root, exec_id = exec_pkg
    rid = _fail(root, exec_id)
    with pytest.raises(ValueError, match="MAST"):
        classify_failure(root, exec_id, run_id=rid, mast_code="执行失败",
                         failure_class="implementation",
                         retry_guidance="x")
