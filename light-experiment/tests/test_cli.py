"""CLI 端到端冒烟：init → intake → run 全周期 → advance → render。"""

from __future__ import annotations

from pathlib import Path

import yaml

from light_experiment.cli import main

from conftest import SPEC, write_export


def _spec_file(tmp_path: Path) -> Path:
    p = tmp_path / "spec.yaml"
    p.write_text(yaml.safe_dump(SPEC, allow_unicode=True), encoding="utf-8")
    return p


def test_cli_end_to_end(tmp_path: Path, capsys):
    root = tmp_path / "proj"
    export = write_export(tmp_path)
    spec = _spec_file(tmp_path)

    assert main(["init", str(root), "--direction", "火鸡行为检测"]) == 0
    assert main(["intake", str(root), "--from-export", str(export)]) == 0
    execs = [d.name for d in (root / "executions").iterdir()]
    assert len(execs) == 1
    exec_id = execs[0]

    assert main(["run-start", str(root), exec_id, "R00-a1",
                 "--spec", str(spec)]) == 0
    assert main(["run-finish", str(root), exec_id, "R00-a1",
                 "--exit-status", "completed", "--gpu-hours", "2"]) == 0
    assert main(["run-start", str(root), exec_id, "R01-a1",
                 "--spec", str(spec)]) == 0
    assert main(["run-finish", str(root), exec_id, "R01-a1",
                 "--exit-status", "failed_error", "--no-salvage"]) == 0
    assert main(["validate", str(root), exec_id]) == 0
    assert main(["event", str(root), exec_id, "--type", "human_checkpoint",
                 "--source", "user", "--payload", '{"decision": "continue"}']) == 0
    assert main(["list", str(root), exec_id]) == 0
    out = capsys.readouterr().out
    assert "R01-a1" in out and "failed" in out

    assert main(["advance", str(root), exec_id, "--to", "sanity"]) == 0
    assert main(["advance", str(root), exec_id, "--to", "executing"]) == 0
    assert main(["advance", str(root), exec_id, "--to", "reconciling"]) == 0
    # 还没 reconciled → delivered 被拦（rc=1）
    assert main(["advance", str(root), exec_id, "--to", "delivered"]) == 1
    assert main(["advance", str(root), exec_id, "--run", "R00-a1",
                 "--to", "reconciled"]) == 0
    assert main(["advance", str(root), exec_id, "--run", "R01-a1",
                 "--to", "reconciled"]) == 0
    assert main(["advance", str(root), exec_id, "--to", "delivered"]) == 0

    assert main(["render", str(root), exec_id]) == 0
    report = (root / "executions" / exec_id / "EXECUTION_REPORT.md").read_text(
        encoding="utf-8")
    assert "failed_error" in report  # 失败与成功同版面
    assert "预算总账" in report
    assert main(["list", str(root)]) == 0


def test_cli_intake_gap_returns_1(tmp_path: Path):
    root = tmp_path / "proj"
    export = write_export(tmp_path, skip=("design_card.json",))
    assert main(["init", str(root), "--direction", "x"]) == 0
    # design_card 缺失到无法识别设计 → rc=1 且不建包
    assert main(["intake", str(root), "--from-export", str(export)]) == 1
    assert list((root / "executions").iterdir()) == []


def test_cli_finish_free_text_exit_status_returns_1(tmp_path: Path):
    root = tmp_path / "proj"
    export = write_export(tmp_path)
    spec = _spec_file(tmp_path)
    assert main(["init", str(root), "--direction", "x"]) == 0
    assert main(["intake", str(root), "--from-export", str(export)]) == 0
    exec_id = next((root / "executions").iterdir()).name
    assert main(["run-start", str(root), exec_id, "R00-a1",
                 "--spec", str(spec)]) == 0
    assert main(["run-finish", str(root), exec_id, "R00-a1",
                 "--exit-status", "执行失败"]) == 1


def test_cli_run_new_and_retry(tmp_path: Path, capsys):
    root = tmp_path / "proj"
    export = write_export(tmp_path)
    spec = _spec_file(tmp_path)
    assert main(["init", str(root), "--direction", "x"]) == 0
    assert main(["intake", str(root), "--from-export", str(export)]) == 0
    exec_id = next((root / "executions").iterdir()).name
    assert main(["run-start", str(root), exec_id, "R01-a1",
                 "--spec", str(spec)]) == 0
    assert main(["run-finish", str(root), exec_id, "R01-a1",
                 "--exit-status", "killed_no_progress", "--no-salvage"]) == 0
    assert main(["run-new", str(root), exec_id, "R01",
                 "--retry-of", "R01-a1"]) == 0
    out = capsys.readouterr().out
    assert "R01-a2" in out
