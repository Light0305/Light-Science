"""干预核查点机械核验（EXP-D03）：三类核验器正反例、不符自动转
deviated、生态反面教训回归形态（声称扫参实际恒定）、事件锚对账。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from light_experiment.project import (
    finish_run,
    load_package,
    load_run,
    new_run,
    save_run,
    start_run,
)
from light_experiment.schema import validate_package

from conftest import SPEC


def _write_jsonl(path: Path, rows: list[dict]) -> Path:
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n"
                            for r in rows), encoding="utf-8")
    return path


def _spec_with(checks: list[dict]) -> dict:
    return {**SPEC, "intervention_checks": checks}


def _run_to_finish(root: Path, exec_id: str, run_id: str, spec: dict,
                   *, exit_status: str = "completed",
                   metrics_file: Path | None = None,
                   salvage: tuple[Path, ...] = ()) -> dict:
    start_run(root, exec_id, run_id, spec=spec)
    return finish_run(root, exec_id, run_id, exit_status=exit_status,
                      metrics_file=metrics_file, salvage_files=salvage)


def _verification(root: Path, exec_id: str, run_id: str) -> dict:
    run = load_run(root, exec_id, run_id)
    return (run.get("conclusion") or {}).get("intervention_verification") or {}


def test_equals_pass_via_metrics_jsonl(exec_pkg, tmp_path: Path):
    root, exec_id = exec_pkg
    checks = [{"point": "theta_source 实际生效", "claimed": "predicted",
               "verify": {"kind": "equals",
                          "source": {"file": "@metrics",
                                     "key": "theta_source"}}}]
    metrics = _write_jsonl(tmp_path / "metrics.jsonl", [
        {"segment": "seg-01", "theta_source": "predicted", "mota": 79.1},
        {"segment": "seg-02", "theta_source": "predicted", "mota": 76.6}])
    run = _run_to_finish(root, exec_id, "R01-a1", _spec_with(checks),
                         metrics_file=metrics)
    assert run["status"] == "completed"
    ver = _verification(root, exec_id, "R01-a1")
    assert ver["verdict"] == "passed"
    assert ver["results"][0]["status"] == "pass"
    assert ver["results"][0]["actual"] == "predicted"
    pkg = load_package(root, exec_id)
    evs = [e for e in pkg["events"] if e["type"] == "intervention_check"]
    assert len(evs) == 1 and evs[0]["run_id"] == "R01-a1"
    assert validate_package(pkg) == []


def test_equals_fraud_sweep_claimed_constant_actual(exec_pkg, tmp_path: Path):
    """生态反面教训的回归形态：声称扫参（五点网格），实际恒定一个值
    ——按设计原理不存在的改进，必须被机械检出并转 deviated。"""
    root, exec_id = exec_pkg
    checks = [{"point": "theta 扫描实际生效",
               "claimed": [0.1, 0.3, 0.5, 0.7, 0.9],
               "verify": {"kind": "equals",
                          "source": {"file": "@metrics", "key": "theta"}}}]
    metrics = _write_jsonl(tmp_path / "metrics.jsonl", [
        {"theta": 0.5, "mota": 70.0}, {"theta": 0.5, "mota": 71.0},
        {"theta": 0.5, "mota": 69.5}])
    run = _run_to_finish(root, exec_id, "R01-a1", _spec_with(checks),
                         metrics_file=metrics)
    assert run["status"] == "deviated"
    assert run["conclusion"]["exit_status"] == "completed"
    ver = _verification(root, exec_id, "R01-a1")
    assert ver["verdict"] == "failed"
    assert ver["results"][0]["status"] == "fail"
    assert ver["results"][0]["actual"] == [0.5]
    assert validate_package(load_package(root, exec_id)) == []


def test_range_pass_and_fail(exec_pkg, tmp_path: Path):
    root, exec_id = exec_pkg
    summary = tmp_path / "summary.json"
    checks = [{"point": "基线均值落带", "claimed": {"min": 70.0, "max": 80.0},
               "verify": {"kind": "range",
                          "source": {"file": str(summary), "key": "mean"}}}]
    summary.write_text(json.dumps({"mean": 77.835}), encoding="utf-8")
    run = _run_to_finish(root, exec_id, "R00-a1", _spec_with(checks))
    assert run["status"] == "completed"
    assert _verification(root, exec_id, "R00-a1")["verdict"] == "passed"

    summary.write_text(json.dumps({"mean": 65.0}), encoding="utf-8")
    run = _run_to_finish(root, exec_id, "R01-a1", _spec_with(checks))
    assert run["status"] == "deviated"
    res = _verification(root, exec_id, "R01-a1")["results"][0]
    assert res["status"] == "fail" and res["actual"] == 65.0


def test_file_hash_pass_and_fail(exec_pkg, tmp_path: Path):
    root, exec_id = exec_pkg
    artifact = tmp_path / "artifact.bin"
    artifact.write_bytes(b"frozen-config-bytes")
    digest = hashlib.sha256(b"frozen-config-bytes").hexdigest()
    good = [{"point": "配置文件即冻结件", "claimed": digest,
             "verify": {"kind": "file_hash", "source": {"file": str(artifact)}}}]
    run = _run_to_finish(root, exec_id, "R00-a1", _spec_with(good))
    assert run["status"] == "completed"
    bad = [{"point": "配置文件即冻结件", "claimed": "0" * 64,
            "verify": {"kind": "file_hash", "source": {"file": str(artifact)}}}]
    run = _run_to_finish(root, exec_id, "R01-a1", _spec_with(bad))
    assert run["status"] == "deviated"
    assert _verification(root, exec_id, "R01-a1")["results"][0]["status"] == "fail"


def test_unverifiable_missing_source_blocks_silent_pass(exec_pkg, tmp_path: Path):
    root, exec_id = exec_pkg
    checks = [{"point": "theta_source 实际生效", "claimed": "predicted",
               "verify": {"kind": "equals",
                          "source": {"file": str(tmp_path / "nope.jsonl"),
                                     "key": "theta_source"}}}]
    run = _run_to_finish(root, exec_id, "R01-a1", _spec_with(checks))
    assert run["status"] == "deviated"
    ver = _verification(root, exec_id, "R01-a1")
    assert ver["verdict"] == "unverifiable"
    assert "不存在" in ver["results"][0]["detail"]


def test_legacy_check_without_verify_is_not_verified_not_blocked(exec_pkg):
    root, exec_id = exec_pkg
    checks = [{"point": "theta_source 实际生效", "claimed": "predicted",
               "evidence": "metrics.jsonl 的 theta_source 列（v1.0 存档形态）"}]
    run = _run_to_finish(root, exec_id, "R01-a1", _spec_with(checks))
    assert run["status"] == "completed"
    ver = _verification(root, exec_id, "R01-a1")
    assert ver["verdict"] == "not_verified"
    assert ver["results"][0]["status"] == "not_verified"
    assert validate_package(load_package(root, exec_id)) == []


def test_no_checks_verdict_reported_honestly(exec_pkg):
    root, exec_id = exec_pkg
    run = _run_to_finish(root, exec_id, "R01-a1", dict(SPEC))
    assert run["status"] == "completed"
    assert _verification(root, exec_id, "R01-a1")["verdict"] == "no_checks"


def test_failed_exit_keeps_failed_but_records_mismatch(exec_pkg, tmp_path: Path):
    root, exec_id = exec_pkg
    checks = [{"point": "theta_source 实际生效", "claimed": "predicted",
               "verify": {"kind": "equals",
                          "source": {"file": "@metrics",
                                     "key": "theta_source"}}}]
    metrics = _write_jsonl(tmp_path / "metrics.jsonl",
                           [{"theta_source": "fixed"}])
    salvage = tmp_path / "partial.json"
    salvage.write_text("{}", encoding="utf-8")
    run = _run_to_finish(root, exec_id, "R01-a1", _spec_with(checks),
                         exit_status="failed_data", metrics_file=metrics,
                         salvage=(salvage,))
    assert run["status"] == "failed"
    ver = _verification(root, exec_id, "R01-a1")
    assert ver["verdict"] == "failed"
    assert validate_package(load_package(root, exec_id)) == []


def test_validator_catches_silent_pass_tamper(exec_pkg, tmp_path: Path):
    """核验不符被转 deviated 后，有人把 run.yaml 状态改回 completed
    冒充通过——校验器以核验记录点名（结论区回改即暴露）。"""
    root, exec_id = exec_pkg
    checks = [{"point": "theta_source 实际生效", "claimed": "predicted",
               "verify": {"kind": "equals",
                          "source": {"file": "@metrics",
                                     "key": "theta_source"}}}]
    metrics = _write_jsonl(tmp_path / "metrics.jsonl",
                           [{"theta_source": "fixed"}])
    run = _run_to_finish(root, exec_id, "R01-a1", _spec_with(checks),
                         metrics_file=metrics)
    assert run["status"] == "deviated"
    run["status"] = "completed"
    save_run(root, exec_id, run)
    errs = validate_package(load_package(root, exec_id))
    assert any("干预核验不符" in e and "deviated" in e for e in errs)


def test_validator_catches_result_rewrite_via_event_anchor(exec_pkg, tmp_path: Path):
    """把结论区的核验结论从 fail 改成 pass——intervention_check
    事件锚里仍是 fail，对账不一致即暴露。"""
    root, exec_id = exec_pkg
    checks = [{"point": "theta_source 实际生效", "claimed": "predicted",
               "verify": {"kind": "equals",
                          "source": {"file": "@metrics",
                                     "key": "theta_source"}}}]
    metrics = _write_jsonl(tmp_path / "metrics.jsonl",
                           [{"theta_source": "fixed"}])
    _run_to_finish(root, exec_id, "R01-a1", _spec_with(checks),
                   metrics_file=metrics)
    run = load_run(root, exec_id, "R01-a1")
    run["conclusion"]["intervention_verification"]["results"][0]["status"] = "pass"
    save_run(root, exec_id, run)
    errs = validate_package(load_package(root, exec_id))
    assert any("事件锚不一致" in e for e in errs)


def test_retry_inherits_intervention_checks(exec_pkg, tmp_path: Path):
    root, exec_id = exec_pkg
    checks = [{"point": "theta_source 实际生效", "claimed": "predicted",
               "verify": {"kind": "equals",
                          "source": {"file": "@metrics",
                                     "key": "theta_source"}}}]
    metrics = _write_jsonl(tmp_path / "metrics.jsonl",
                           [{"theta_source": "predicted"}])
    _run_to_finish(root, exec_id, "R01-a1", _spec_with(checks),
                   metrics_file=metrics)
    run2 = new_run(root, exec_id, "R01", retry_of="R01-a1")
    assert run2["identity"]["intervention_checks"] == checks
