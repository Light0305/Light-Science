"""确定性校验器：字段下限 / params 冻结 / 身份重算 / 终止词表 /
终态不可逆 / 血缘证据 / 对账行对齐。"""

from __future__ import annotations

from pathlib import Path

import pytest

from light_experiment.gates import GateError
from light_experiment.project import (
    finish_run,
    load_package,
    load_run,
    new_run,
    run_dir,
    save_run,
    start_run,
)
from light_experiment.schema import derive_seed, validate_package
from light_experiment.util import read_yaml, write_yaml

from conftest import SPEC


def _start(root: Path, exec_id: str, run_id: str) -> dict:
    return start_run(root, exec_id, run_id, spec=SPEC)


def _finish_ok(root: Path, exec_id: str, run_id: str) -> dict:
    return finish_run(root, exec_id, run_id, exit_status="completed",
                      wall_clock_s=60)


def _errors(root: Path, exec_id: str) -> list[str]:
    return validate_package(load_package(root, exec_id))


def test_full_lifecycle_validates_clean(exec_pkg):
    root, exec_id = exec_pkg
    _start(root, exec_id, "R01-a1")
    _finish_ok(root, exec_id, "R01-a1")
    assert _errors(root, exec_id) == []


def test_start_without_spec_lists_all_minimum_gaps(exec_pkg):
    root, exec_id = exec_pkg
    with pytest.raises(GateError) as ei:
        start_run(root, exec_id, "R00-a1")
    text = "；".join(ei.value.errors)
    assert len(ei.value.errors) >= 5
    for needle in ("配置全文", "根种子", "代码快照哈希", "数据版本", "环境声明"):
        assert needle in text


def test_start_with_partial_spec_lists_only_missing(exec_pkg):
    root, exec_id = exec_pkg
    with pytest.raises(GateError) as ei:
        start_run(root, exec_id, "R00-a1", spec={"config": {"a": 1}, "root_seed": 1})
    text = "；".join(ei.value.errors)
    assert "配置全文" not in text
    assert "根种子" not in text
    assert "代码快照哈希" in text


def test_params_tamper_detected(exec_pkg):
    root, exec_id = exec_pkg
    _start(root, exec_id, "R01-a1")
    run = load_run(root, exec_id, "R01-a1")
    run["identity"]["params"]["theta_high"] = 0.99  # 开跑后偷改参数
    save_run(root, exec_id, run)
    errs = _errors(root, exec_id)
    assert any("params 已被改动" in e for e in errs)


def test_identity_tamper_detected(exec_pkg):
    root, exec_id = exec_pkg
    _start(root, exec_id, "R01-a1")
    run = load_run(root, exec_id, "R01-a1")
    run["identity"]["config"]["model"] = "别的模型"  # 身份成分被换
    save_run(root, exec_id, run)
    errs = _errors(root, exec_id)
    assert any("身份已被改动" in e for e in errs)
    assert any("出生证明" in e for e in errs)


def test_exit_status_free_text_detected(exec_pkg):
    root, exec_id = exec_pkg
    _start(root, exec_id, "R01-a1")
    _finish_ok(root, exec_id, "R01-a1")
    path = run_dir(root, exec_id, "R01-a1") / "run.yaml"
    run = read_yaml(path)
    run["conclusion"]["exit_status"] = "执行失败"  # 自由文本冒充终止分类
    write_yaml(path, run)
    errs = _errors(root, exec_id)
    assert any("终止分类词表" in e for e in errs)


def test_conclusion_tamper_caught_by_event_anchor(exec_pkg):
    root, exec_id = exec_pkg
    _start(root, exec_id, "R01-a1")
    _finish_ok(root, exec_id, "R01-a1")
    run = load_run(root, exec_id, "R01-a1")
    run["conclusion"]["exit_status"] = "forfeited"  # 词表内但与事件锚不符
    save_run(root, exec_id, run)
    errs = _errors(root, exec_id)
    assert any("事件" in e and "不一致" in e for e in errs)


def test_failed_finish_requires_salvage(exec_pkg, tmp_path: Path):
    root, exec_id = exec_pkg
    _start(root, exec_id, "R01-a1")
    with pytest.raises(GateError, match="抢救"):
        finish_run(root, exec_id, "R01-a1", exit_status="failed_error")
    # 显式声明无可抢救 → 放行且校验干净
    finish_run(root, exec_id, "R01-a1", exit_status="failed_error", no_salvage=True)
    assert _errors(root, exec_id) == []
    run = load_run(root, exec_id, "R01-a1")
    assert "无可抢救" in run["conclusion"]["salvage_note"]


def test_failed_finish_with_salvage_file(exec_pkg, tmp_path: Path):
    root, exec_id = exec_pkg
    _start(root, exec_id, "R01-a1")
    patch = tmp_path / "partial.patch"
    patch.write_text("diff --git a/x b/x\n", encoding="utf-8")
    run = finish_run(root, exec_id, "R01-a1", exit_status="failed_error",
                     salvage_files=(patch,))
    assert run["conclusion"]["salvage"][0]["name"] == "partial.patch"
    assert len(run["conclusion"]["salvage"][0]["sha256"]) == 64
    assert _errors(root, exec_id) == []


def test_finish_rejects_free_text_exit_status(exec_pkg):
    root, exec_id = exec_pkg
    _start(root, exec_id, "R01-a1")
    with pytest.raises(ValueError, match="终止分类词表"):
        finish_run(root, exec_id, "R01-a1", exit_status="执行失败")


def test_metrics_file_registered_with_hash(exec_pkg, tmp_path: Path):
    root, exec_id = exec_pkg
    _start(root, exec_id, "R01-a1")
    m = tmp_path / "metrics.jsonl"
    m.write_text('{"step": 1, "mota": 0.5}\n', encoding="utf-8")
    run = finish_run(root, exec_id, "R01-a1", exit_status="completed",
                     metrics_file=m, gpu_hours=1.5)
    assert run["observation"]["metrics_ref"]["name"] == "metrics.jsonl"
    assert run["observation"]["attempts_budget"]["gpu_hours"] == 1.5
    assert _errors(root, exec_id) == []


def test_derived_seed_deterministic_and_run_specific(exec_pkg):
    root, exec_id = exec_pkg
    r0 = _start(root, exec_id, "R00-a1")
    r1 = _start(root, exec_id, "R01-a1")
    s0 = r0["identity"]["seeds"]["derived_seed"]
    s1 = r1["identity"]["seeds"]["derived_seed"]
    assert s0 == derive_seed(42, "R00-a1")
    assert s1 == derive_seed(42, "R01-a1")
    assert s0 != s1  # 同根种子、不同 run → 不同派生种子


def test_retry_creates_new_run_with_lineage_evidence(exec_pkg):
    root, exec_id = exec_pkg
    origin = _start(root, exec_id, "R01-a1")
    finish_run(root, exec_id, "R01-a1", exit_status="killed_budget",
               no_salvage=True)
    retry = new_run(root, exec_id, "R01", retry_of="R01-a1")
    assert retry["run_id"] == "R01-a2"
    lineage = retry["identity"]["lineage"]
    assert lineage["origin_run"] == "R01-a1"
    seg = lineage["reused_segments"][0]
    assert seg["identity_hash"] == origin["identity"]["identity_hash"]
    # 身份成分继承 → 开跑后身份哈希与原 run 相同，校验干净
    _start(root, exec_id, "R01-a2")
    run2 = load_run(root, exec_id, "R01-a2")
    assert run2["identity"]["identity_hash"] == origin["identity"]["identity_hash"]
    assert _errors(root, exec_id) == []


def test_reused_segment_without_hash_evidence_detected(exec_pkg):
    root, exec_id = exec_pkg
    _start(root, exec_id, "R01-a1")
    finish_run(root, exec_id, "R01-a1", exit_status="failed_error", no_salvage=True)
    new_run(root, exec_id, "R01", retry_of="R01-a1")
    run = load_run(root, exec_id, "R01-a2")
    run["identity"]["lineage"]["reused_segments"][0]["identity_hash"] = "0" * 64
    save_run(root, exec_id, run)
    errs = _errors(root, exec_id)
    assert any("复用段缺内容哈希证据" in e for e in errs)


def test_retry_of_unfinished_run_rejected(exec_pkg):
    root, exec_id = exec_pkg
    with pytest.raises(ValueError, match="尚未终止"):
        new_run(root, exec_id, "R01", retry_of="R01-a1")


def test_terminal_history_irreversible(exec_pkg):
    root, exec_id = exec_pkg
    _start(root, exec_id, "R01-a1")
    _finish_ok(root, exec_id, "R01-a1")
    run = load_run(root, exec_id, "R01-a1")
    run["status_history"].append(
        {"from": "completed", "to": "running", "date": "2026-10-20",
         "by": "手改", "note": "想原地续跑"})
    save_run(root, exec_id, run)
    errs = _errors(root, exec_id)
    assert any("非法跃迁" in e for e in errs)


def test_reconciliation_missing_row_detected(exec_pkg):
    root, exec_id = exec_pkg
    pkg = load_package(root, exec_id)
    recon = pkg["reconciliation"]
    recon["rows"] = recon["rows"][:1]  # 删一行冒充对齐
    from light_experiment.project import save_reconciliation
    save_reconciliation(root, exec_id, recon)
    errs = _errors(root, exec_id)
    assert any("不对齐" in e for e in errs)


def test_deviated_finish_and_budget_ledger(exec_pkg):
    root, exec_id = exec_pkg
    _start(root, exec_id, "R01-a1")
    run = finish_run(root, exec_id, "R01-a1", exit_status="completed",
                     mark_deviated=True, wall_clock_s=120, api_cost=0.5)
    assert run["status"] == "deviated"
    pkg = load_package(root, exec_id)
    spent = pkg["execution"]["budget_ledger"]["spent"]
    assert spent["wall_clock_s"] == 120
    assert spent["api_cost"] == 0.5
    assert _errors(root, exec_id) == []
