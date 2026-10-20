"""双层状态机：包级全流与 delivered 门、blocked 往返、run 收尾门。"""

from __future__ import annotations

import pytest

from light_experiment.gates import GateError, advance_package, advance_run
from light_experiment.project import (
    finish_run,
    load_package,
    load_run,
    save_run,
    start_run,
)

from conftest import SPEC

DATE = "2026-10-20"


def _drive_run(root, exec_id, run_id):
    start_run(root, exec_id, run_id, spec=SPEC)
    finish_run(root, exec_id, run_id, exit_status="completed")


def _advance(root, exec_id, to, **kw):
    pkg = load_package(root, exec_id)
    advance_package(pkg, to, date=DATE, **kw)
    from light_experiment.project import save_execution
    save_execution(root, pkg["execution"])
    return pkg


def test_package_full_flow_to_delivered(exec_pkg):
    root, exec_id = exec_pkg
    _advance(root, exec_id, "sanity")
    _advance(root, exec_id, "executing")
    _drive_run(root, exec_id, "R00-a1")
    _drive_run(root, exec_id, "R01-a1")
    _advance(root, exec_id, "reconciling")
    # runs 未 reconciled → delivered 被拦并逐个点名
    pkg = load_package(root, exec_id)
    with pytest.raises(GateError) as ei:
        advance_package(pkg, "delivered", date=DATE)
    assert any("尚未对账清零" in e for e in ei.value.errors)
    for run_id in ("R00-a1", "R01-a1"):
        run = load_run(root, exec_id, run_id)
        advance_run(run, "reconciled", date=DATE)
        save_run(root, exec_id, run)
    pkg = _advance(root, exec_id, "delivered")
    assert pkg["execution"]["status"] == "delivered"
    # delivered 终态：不许再推进
    with pytest.raises(GateError):
        advance_package(pkg, "blocked", date=DATE,
                        block_reason="x", unblock_condition="y")


def test_reconciling_blocked_while_run_running(exec_pkg):
    root, exec_id = exec_pkg
    _advance(root, exec_id, "sanity")
    _advance(root, exec_id, "executing")
    start_run(root, exec_id, "R00-a1", spec=SPEC)
    pkg = load_package(root, exec_id)
    with pytest.raises(GateError, match="未终止不许进对账"):
        advance_package(pkg, "reconciling", date=DATE)


def test_illegal_package_transition_named(exec_pkg):
    root, exec_id = exec_pkg
    pkg = load_package(root, exec_id)
    with pytest.raises(GateError, match="非法跃迁"):
        advance_package(pkg, "delivered", date=DATE)


def test_blocked_roundtrip(exec_pkg):
    root, exec_id = exec_pkg
    _advance(root, exec_id, "sanity")
    pkg = load_package(root, exec_id)
    # 无原因/解阻条件 → 拦
    with pytest.raises(GateError, match="阻塞原因与解阻条件"):
        advance_package(pkg, "blocked", date=DATE)
    _advance(root, exec_id, "blocked", block_reason="等 GPU 队列",
             unblock_condition="实验室机器空出")
    pkg = load_package(root, exec_id)
    assert pkg["execution"]["status"] == "blocked"
    assert pkg["execution"]["block_record"]["from_state"] == "sanity"
    # blocked 只许回到受阻前状态
    with pytest.raises(GateError, match="只许解阻回到"):
        advance_package(pkg, "executing", date=DATE)
    pkg = _advance(root, exec_id, "sanity")
    assert pkg["execution"]["block_record"] is None


def test_run_reconcile_gate_failed_without_salvage(exec_pkg):
    root, exec_id = exec_pkg
    start_run(root, exec_id, "R01-a1", spec=SPEC)
    run = load_run(root, exec_id, "R01-a1")
    # 手工伪造一个「失败但没抢救登记」的 run（绕过 finish 门）
    run["conclusion"]["exit_status"] = "failed_error"
    run["status_history"].append(
        {"from": "running", "to": "failed", "date": DATE, "by": "手改", "note": ""})
    run["status"] = "failed"
    with pytest.raises(GateError, match="抢救"):
        advance_run(run, "reconciled", date=DATE)


def test_run_illegal_transition(exec_pkg):
    root, exec_id = exec_pkg
    run = load_run(root, exec_id, "R00-a1")
    with pytest.raises(GateError, match="非法跃迁"):
        advance_run(run, "reconciled", date=DATE)


def test_deviated_run_needs_disposition_to_reconcile(exec_pkg):
    root, exec_id = exec_pkg
    start_run(root, exec_id, "R01-a1", spec=SPEC)
    finish_run(root, exec_id, "R01-a1", exit_status="completed", mark_deviated=True)
    run = load_run(root, exec_id, "R01-a1")
    with pytest.raises(GateError, match="处置依据"):
        advance_run(run, "reconciled", date=DATE)
    # 附处置注记后放行
    advance_run(run, "reconciled", date=DATE, note="偏离已登记，处置：接受并声明")
    assert run["status"] == "reconciled"
