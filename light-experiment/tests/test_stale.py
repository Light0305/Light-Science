"""事前 stale 清单（EXP-D02）：三态、逐维点名、下游闭包与 deviation
闭包口径一致、设计链 amendment 检出、只读纪律。"""

from __future__ import annotations

import json
from pathlib import Path

from light_experiment.cli import main as cli_main
from light_experiment.deviations import compute_closure
from light_experiment.project import finish_run, load_package, start_run
from light_experiment.stale import compute_stale_report, write_stale_reports

from conftest import DESIGN_HASH, SPEC


def _finish_two(root: Path, exec_id: str) -> None:
    for rid in ("R00-a1", "R01-a1"):
        start_run(root, exec_id, rid, spec=SPEC)
        finish_run(root, exec_id, rid, exit_status="completed")


def _states(report: dict) -> dict[str, dict]:
    return {e["run_id"]: e for e in report["runs"]}


def test_all_current_when_nothing_changed(exec_pkg):
    root, exec_id = exec_pkg
    _finish_two(root, exec_id)
    report = compute_stale_report(root, exec_id)
    assert report["summary"] == {"current": 2, "stale": 0, "voided": 0}
    assert report["compared_dimensions"] == ["design"]
    assert "params" in report["uncompared_dimensions"]


def test_planned_runs_are_current_with_note(exec_pkg):
    root, exec_id = exec_pkg
    report = compute_stale_report(root, exec_id)
    for e in report["runs"]:
        assert e["state"] == "current"
        assert "无出生证明" in e["note"]


def test_spec_param_tamper_names_run_and_downstream(exec_pkg):
    """篡改一维（R00 的 params 现行声明）：R00 点名 stale、其下游
    R01 经依赖闭包标 stale；stale 集与 deviation 闭包结果集一致。"""
    root, exec_id = exec_pkg
    _finish_two(root, exec_id)
    spec = {"R00": {**SPEC, "params": {**SPEC["params"], "theta_high": 0.7}}}
    report = compute_stale_report(root, exec_id, current_spec=spec)
    states = _states(report)
    assert states["R00-a1"]["state"] == "stale"
    assert [d["dimension"] for d in states["R00-a1"]["stale_dimensions"]] == ["params"]
    assert "补跑" in states["R00-a1"]["advice"]
    assert states["R01-a1"]["state"] == "stale"
    assert states["R01-a1"]["stale_upstream"] == ["R00"]
    assert [d["dimension"] for d in states["R01-a1"]["stale_dimensions"]] == ["upstream"]
    pkg = load_package(root, exec_id)
    closure = set(compute_closure(pkg, run_id="R00-a1", dimension="params"))
    stale_set = {r for r, e in states.items() if e["state"] == "stale"}
    assert stale_set == closure


def test_design_amendment_makes_runs_stale(exec_pkg, export_dir: Path):
    root, exec_id = exec_pkg
    _finish_two(root, exec_id)
    card_path = export_dir / "design_card.json"
    card = json.loads(card_path.read_text(encoding="utf-8"))
    card["freeze"]["amendments"] = [
        {"date": "2026-10-21", "fields": ["plan.variables"],
         "new_hash": "f" * 64}]
    card_path.write_text(json.dumps(card, ensure_ascii=False, indent=2),
                         encoding="utf-8")
    report = compute_stale_report(root, exec_id)
    for e in report["runs"]:
        assert e["state"] == "stale"
        assert [d["dimension"] for d in e["stale_dimensions"]] == ["design"]
        assert "新批次承接" in e["advice"]


def test_voided_runs_reported_as_voided(exec_pkg):
    from light_experiment.deviations import (
        apply_deviation,
        publish_deviation,
        raise_deviation,
    )
    root, exec_id = exec_pkg
    _finish_two(root, exec_id)
    raise_deviation(root, exec_id, run_id="R01-a1", type="config",
                    dimension=None, description="登记的参数与实际不符",
                    disposition="void_and_rerun")
    publish_deviation(root, exec_id, "DV-0001")
    apply_deviation(root, exec_id, "DV-0001")
    report = compute_stale_report(root, exec_id)
    states = _states(report)
    assert states["R01-a1"]["state"] == "voided"
    assert states["R01-a1"]["voided_by"] == ["DV-0001"]
    assert states["R00-a1"]["state"] == "current"


def test_stale_is_read_only_and_writes_two_reports(exec_pkg, tmp_path: Path):
    root, exec_id = exec_pkg
    _finish_two(root, exec_id)
    d = root / "executions" / exec_id
    events_before = (d / "events.jsonl").read_text(encoding="utf-8")
    run_before = (d / "runs" / "R00-a1" / "run.yaml").read_text(encoding="utf-8")
    exec_before = (d / "execution.yaml").read_text(encoding="utf-8")
    report = compute_stale_report(root, exec_id)
    out_json, out_md = write_stale_reports(root, exec_id, report)
    assert out_json.exists() and out_md.exists()
    saved = json.loads(out_json.read_text(encoding="utf-8"))
    assert saved["exec_id"] == exec_id and saved["summary"]["current"] == 2
    assert "stale 预检清单" in out_md.read_text(encoding="utf-8")
    # 只读纪律：包状态文件一字未动
    assert (d / "events.jsonl").read_text(encoding="utf-8") == events_before
    assert (d / "runs" / "R00-a1" / "run.yaml").read_text(encoding="utf-8") == run_before
    assert (d / "execution.yaml").read_text(encoding="utf-8") == exec_before


def test_cli_stale_end_to_end(exec_pkg):
    root, exec_id = exec_pkg
    _finish_two(root, exec_id)
    rc = cli_main(["stale", str(root), exec_id])
    assert rc == 0
    d = root / "executions" / exec_id
    assert (d / "stale_report.json").exists()
    assert (d / "STALE_REPORT.md").exists()


def test_spec_single_form_applies_to_all_entries(exec_pkg):
    """--spec 给全包一份（顶层成分键形态）：同 spec 与出生证明一致
    → 全 current；这验证声明比对走的是出生证明成分而非自述。"""
    root, exec_id = exec_pkg
    _finish_two(root, exec_id)
    report = compute_stale_report(root, exec_id, current_spec=dict(SPEC))
    assert report["summary"]["stale"] == 0
    assert set(report["compared_dimensions"]) >= {"code", "params", "config",
                                                 "data", "env"}
    assert report["design_current_hash"] == DESIGN_HASH
