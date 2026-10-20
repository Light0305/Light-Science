"""偏离登记与闭包作废（E4）：闭包计算、公示前置、覆写留痕、回流草稿。"""

from __future__ import annotations

from pathlib import Path

import pytest

from light_experiment.deviations import (
    apply_deviation,
    get_deviation,
    override_deviation,
    publish_deviation,
    raise_deviation,
)
from light_experiment.gates import GateError, advance_run
from light_experiment.project import (
    finish_run,
    load_package,
    load_reconciliation,
    load_run,
    save_run,
    start_run,
)

from conftest import SPEC

PARAMS_VARIANT = {**SPEC, "params": {"theta_high": 0.9, "theta_low": 0.1,
                                     "theta_mod_iou": 0.35}}


def _drive_both(root, exec_id):
    start_run(root, exec_id, "R00-a1", spec=SPEC)
    finish_run(root, exec_id, "R00-a1", exit_status="completed")
    start_run(root, exec_id, "R01-a1", spec=SPEC)
    finish_run(root, exec_id, "R01-a1", exit_status="completed")


def _raise(root, exec_id, **kw):
    kw.setdefault("type", "config")
    kw.setdefault("dimension", "config")
    kw.setdefault("description", "实际配置与声称不符")
    kw.setdefault("disposition", "void_and_rerun")
    return raise_deviation(root, exec_id, **kw)


def test_closure_includes_anchor_twins_and_downstream(exec_pkg):
    root, exec_id = exec_pkg
    _drive_both(root, exec_id)
    entry = _raise(root, exec_id, run_id="R00-a1", declared=("R00-a1",))
    # 人工估计只点了 R00-a1；工具闭包：同 config 锚的 R01-a1（同 SPEC）
    # + R00 的下游条目 R01 → 两条全进
    assert entry["affected_runs_declared"] == ["R00-a1"]
    assert entry["affected_runs_closure"] == ["R00-a1", "R01-a1"]
    pkg = load_package(root, exec_id)
    dev = get_deviation(pkg, entry["deviation_id"])
    assert dev["affected_runs_declared"] != dev["affected_runs_closure"]


def test_apply_requires_publish_first(exec_pkg):
    root, exec_id = exec_pkg
    _drive_both(root, exec_id)
    entry = _raise(root, exec_id, run_id="R00-a1")
    with pytest.raises(GateError, match="尚未公示"):
        apply_deviation(root, exec_id, entry["deviation_id"])


def test_publish_then_apply_voids_with_marks(exec_pkg):
    root, exec_id = exec_pkg
    _drive_both(root, exec_id)
    entry = _raise(root, exec_id, run_id="R00-a1")
    pub = publish_deviation(root, exec_id, entry["deviation_id"])
    notice = Path(pub["notice"])
    assert notice.exists() and "R01-a1" in notice.read_text(encoding="utf-8")
    applied = apply_deviation(root, exec_id, entry["deviation_id"])
    assert applied["invalidated"] == ["R00-a1", "R01-a1"]
    for rid in ("R00-a1", "R01-a1"):
        run = load_run(root, exec_id, rid)
        assert run["status"] == "deviated"
        assert run["conclusion"]["reconciliation"]["voided_by"] == \
            entry["deviation_id"]
        # 以作废身份对账
        advance_run(run, "reconciled", date="2026-10-20")
        save_run(root, exec_id, run)
    recon = load_reconciliation(root, exec_id)
    assert all(r["status"] == "voided" for r in recon["rows"])
    assert all(entry["deviation_id"] in r["deviations"] for r in recon["rows"])
    from light_experiment.schema import validate_package
    assert validate_package(load_package(root, exec_id)) == []


def test_override_exempts_and_requires_reason(exec_pkg):
    root, exec_id = exec_pkg
    _drive_both(root, exec_id)
    entry = _raise(root, exec_id, run_id="R00-a1")
    did = entry["deviation_id"]
    publish_deviation(root, exec_id, did)
    with pytest.raises(ValueError, match="理由"):
        override_deviation(root, exec_id, did, exempted_runs=("R01-a1",),
                           by="用户", reason="")
    override_deviation(root, exec_id, did, exempted_runs=("R01-a1",),
                       by="用户", reason="R01 用的是修正前独立复核过的产物")
    applied = apply_deviation(root, exec_id, did)
    assert applied["invalidated"] == ["R00-a1"]
    assert applied["exempted"] == ["R01-a1"]
    run = load_run(root, exec_id, "R01-a1")
    assert run["status"] == "completed"
    assert run["conclusion"]["reconciliation"]["voided_by"] is None


def test_override_after_apply_rejected(exec_pkg):
    root, exec_id = exec_pkg
    _drive_both(root, exec_id)
    entry = _raise(root, exec_id, run_id="R00-a1")
    did = entry["deviation_id"]
    publish_deviation(root, exec_id, did)
    apply_deviation(root, exec_id, did)
    with pytest.raises(GateError, match="不许覆写回滚|已生效"):
        override_deviation(root, exec_id, did, exempted_runs=("R01-a1",),
                           by="用户", reason="事后反悔")


def test_apply_blocked_by_reconciled_run_in_closure(exec_pkg):
    root, exec_id = exec_pkg
    _drive_both(root, exec_id)
    run = load_run(root, exec_id, "R00-a1")
    advance_run(run, "reconciled", date="2026-10-20")
    save_run(root, exec_id, run)
    entry = _raise(root, exec_id, run_id="R00-a1")
    publish_deviation(root, exec_id, entry["deviation_id"])
    with pytest.raises(GateError, match="reconciled"):
        apply_deviation(root, exec_id, entry["deviation_id"])


def test_params_dimension_anchor_isolates_attempts(exec_pkg):
    root, exec_id = exec_pkg
    start_run(root, exec_id, "R00-a1", spec=SPEC)
    finish_run(root, exec_id, "R00-a1", exit_status="completed")
    start_run(root, exec_id, "R01-a1", spec=PARAMS_VARIANT)
    finish_run(root, exec_id, "R01-a1", exit_status="completed")
    # params 维偏离只落在 R01-a1 的锚上：闭包 = R01 条目（R00 不受牵连，
    # R01 也没有下游）——锚不同罪不同
    entry = raise_deviation(root, exec_id, run_id="R01-a1", type="config",
                            dimension="params",
                            description="theta_high 实际 0.9 非声称 0.6",
                            claimed="0.6", actual="0.9",
                            disposition="void_and_rerun")
    assert entry["affected_runs_closure"] == ["R01-a1"]


def test_design_revision_deviation_emits_amendment_draft(exec_pkg):
    root, exec_id = exec_pkg
    _drive_both(root, exec_id)
    entry = raise_deviation(root, exec_id, run_id="R01-a1", type="readout",
                            description="判读口径本身有误，构成设计修订",
                            disposition="stop_and_return_design")
    pkg = load_package(root, exec_id)
    inbox = pkg["reflux"]["design_inbox"]
    drafts = [e for e in inbox if e.get("kind") == "design_amendment_draft"]
    assert len(drafts) == 1
    assert drafts[0]["source_id"] == entry["deviation_id"]
    assert drafts[0]["status"] == "pending"


def test_accept_with_declaration_writes_rows(exec_pkg):
    root, exec_id = exec_pkg
    _drive_both(root, exec_id)
    entry = raise_deviation(root, exec_id, run_id="R01-a1", type="environment",
                            dimension="env", description="机器档位与声明不同",
                            disposition="accept_with_declaration",
                            declaration="本批结果在 lab-2gpu 上产生，声明在此")
    publish_deviation(root, exec_id, entry["deviation_id"])
    applied = apply_deviation(root, exec_id, entry["deviation_id"])
    assert applied["invalidated"] == []
    # env 维两条 run 同锚（同 SPEC 环境声明）→ 闭包含两条目，声明落两行
    assert applied["declared_rows"] == ["R00", "R01"]
    recon = load_reconciliation(root, exec_id)
    row = next(r for r in recon["rows"] if r["registry_run_id"] == "R01")
    assert row["declarations"][0]["text"].startswith("本批结果在")
    run = load_run(root, exec_id, "R01-a1")
    assert run["status"] == "completed"  # 接受声明不作废
