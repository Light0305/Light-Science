"""预算闸（E2 补，拍板 ⑤）：触发即停报、候选登记、熔断线防放宽。"""

from __future__ import annotations

import pytest
import yaml

from light_experiment.budget import check_budget
from light_experiment.cli import main
from light_experiment.project import (
    finish_run,
    load_execution,
    load_package,
    new_run,
    save_execution,
    start_run,
)
from light_experiment.schema import validate_package

from conftest import SPEC


def _spend(root, exec_id):
    """把 gpu_hours 账烧到 35（线 30）：R00 烧 20、R01 烧 15，
    再开一条 R01-a2 留在 running 当候选。"""
    start_run(root, exec_id, "R00-a1", spec=SPEC)
    finish_run(root, exec_id, "R00-a1", exit_status="completed", gpu_hours=20)
    start_run(root, exec_id, "R01-a1", spec=SPEC)
    finish_run(root, exec_id, "R01-a1", exit_status="completed", gpu_hours=15)
    new_run(root, exec_id, "R01", retry_of="R01-a1")
    start_run(root, exec_id, "R01-a2", spec=SPEC)


def test_budget_check_trips_and_names_candidates(exec_pkg):
    root, exec_id = exec_pkg
    _spend(root, exec_id)
    result = check_budget(root, exec_id)
    assert [t["metric"] for t in result["tripped"]] == ["gpu_hours"]
    assert result["tripped"][0]["spent"] == 35
    assert result["candidates"] == ["R01-a2"]  # 仍在 running 的才进候选
    pkg = load_package(root, exec_id)
    types = [e["type"] for e in pkg["events"]]
    assert "budget_event" in types and "breaker_tripped" in types
    assert pkg["execution"]["budget_ledger"]["candidates"] == ["R01-a2"]


def test_budget_check_quiet_under_line(exec_pkg):
    root, exec_id = exec_pkg
    start_run(root, exec_id, "R00-a1", spec=SPEC)
    finish_run(root, exec_id, "R00-a1", exit_status="completed", gpu_hours=5)
    result = check_budget(root, exec_id)
    assert result["tripped"] == []
    assert result["lines"][0]["threshold"] == 30


def test_cli_budget_check_exit_code(exec_pkg):
    root, exec_id = exec_pkg
    _spend(root, exec_id)
    assert main(["budget", "check", str(root), exec_id]) == 1


def test_no_relax_command_exists(exec_pkg):
    root, exec_id = exec_pkg
    # 工具不提供任何放宽/上调熔断线的命令（只许停不许改）
    with pytest.raises(SystemExit):
        main(["budget", "set", str(root), exec_id, "--gpu-hours", "999"])


def test_raised_limit_flagged_by_validator(exec_pkg):
    root, exec_id = exec_pkg
    execution = load_execution(root, exec_id)
    execution["budget_ledger"]["limits"]["gpu_hours"] = 999  # 执行端偷偷放宽
    save_execution(root, execution)
    errs = validate_package(load_package(root, exec_id))
    assert any("熔断线被执行端放宽" in e for e in errs)
    # 落回线内则不报（lines 是快照口径，不是 limits）
    execution["budget_ledger"]["limits"]["gpu_hours"] = 30
    save_execution(root, execution)
    assert validate_package(load_package(root, exec_id)) == []
