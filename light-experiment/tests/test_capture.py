"""第四批：自动捕获 + 内容寻址产物池 + 无进展巡检。

口径钉子：
- 开跑捕获是工具实测（provenance=captured），命令文本与身份是
  spec 声明（declared）——两者不许混；捕获块哈希钉事件锚，
  改捕获记录必被校验器点名；
- 声明输入开跑时实测哈希，缺失即拦开跑；
- 产物入池 = 内容寻址：同内容一份、地址即哈希；池对象被改
  validate 主动巡检点名；
- 无进展巡检只判定留痕不代杀；按规程发心跳的正常长运行
  永不误判（反例钉住）。
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from light_experiment.capture import (
    hash_file,
    pool_object_relpath,
    probe_git,
    register_artifact,
    verify_pool,
)
from light_experiment.cli import main as cli_main
from light_experiment.events import append_event, read_events
from light_experiment.gates import GateError
from light_experiment.project import (
    exec_dir,
    finish_run,
    load_package,
    load_run,
    save_run,
    start_run,
)
from light_experiment.schema import validate_package
from light_experiment.watchdog import evaluate_no_progress, scan_no_progress

from conftest import SPEC


def _started(exec_pkg, run_id: str = "R01-a1", spec: dict | None = None) -> dict:
    root, exec_id = exec_pkg
    return start_run(root, exec_id, run_id, spec=dict(spec or SPEC))


def _capture_of(run: dict) -> dict:
    return (run["observation"].get("capture") or {})


# ---------- 开跑自动捕获 ----------

def test_start_capture_block_present_with_provenance(exec_pkg):
    run = _started(exec_pkg)
    cap = _capture_of(run)
    start = cap["start"]
    assert start is not None and cap["start_hash"]
    assert start["provenance"] == "captured"
    fp = start["environment_fingerprint"]
    assert fp["os"] and fp["python"] and fp["hostname"]
    assert start["executor"]["user"]
    assert start["executor"]["provenance"] == "captured"
    # tmp 项目不在 git 树内 → git 如实缺席 + 原因，不冒充
    assert start["git"] is None
    assert "git" in (start["git_unavailable_reason"] or "")
    assert start["command"] is None and start["inputs"] == []
    assert validate_package(load_package(*exec_pkg)) == []


def test_start_capture_hash_anchored_in_event(exec_pkg):
    root, exec_id = exec_pkg
    run = _started(exec_pkg)
    events, errors = read_events(exec_dir(root, exec_id))
    assert errors == []
    started = [e for e in events if e["type"] == "run_started"
               and e["run_id"] == "R01-a1"]
    assert started[-1]["payload"]["capture_hash"] == \
        _capture_of(run)["start_hash"]


def test_capture_tamper_detected_by_validator(exec_pkg):
    root, exec_id = exec_pkg
    run = _started(exec_pkg)
    cap = _capture_of(run)
    cap["start"]["executor"]["user"] = "冒名者"
    save_run(root, exec_id, run)
    errs = validate_package(load_package(root, exec_id))
    assert any("捕获块" in e and "start_hash" in e for e in errs)


def test_capture_anchor_removed_detected(exec_pkg):
    root, exec_id = exec_pkg
    _started(exec_pkg)
    # 抹掉事件锚里的 capture_hash（模拟事后补录/改账）
    d = exec_dir(root, exec_id)
    lines = (d / "events.jsonl").read_text(encoding="utf-8").splitlines()
    out = []
    for line in lines:
        ev = json.loads(line)
        if ev["type"] == "run_started":
            ev["payload"].pop("capture_hash", None)
        out.append(json.dumps(ev, ensure_ascii=False))
    (d / "events.jsonl").write_text("\n".join(out) + "\n", encoding="utf-8")
    errs = validate_package(load_package(root, exec_id))
    assert any("capture_hash" in e and "锚" in e for e in errs)


def test_declared_command_and_inputs_captured(exec_pkg, tmp_path: Path):
    root, exec_id = exec_pkg
    data = tmp_path / "input.csv"
    data.write_bytes(b"a,b\n1,2\n")
    spec = dict(SPEC)
    spec["command"] = "python train.py --config cfg.yaml"
    spec["input_files"] = [str(data)]
    run = start_run(root, exec_id, "R01-a1", spec=spec)
    start = _capture_of(run)["start"]
    # 命令是声明（工具不代测），来源标记必须分开
    assert start["command"] == {"text": "python train.py --config cfg.yaml",
                                "provenance": "declared"}
    # 输入哈希是工具开跑时实测
    sha, size = hash_file(data)
    assert start["inputs"] == [{"name": "input.csv", "path": str(data),
                                "sha256": sha, "size": size,
                                "provenance": "captured"}]
    # 身份哈希口径不变：捕获不进 identity（声明身份与实测证据分工）
    ident = run["identity"]
    assert ident["command"] == "python train.py --config cfg.yaml"
    assert validate_package(load_package(root, exec_id)) == []


def test_missing_declared_input_blocks_start(exec_pkg, tmp_path: Path):
    root, exec_id = exec_pkg
    spec = dict(SPEC)
    spec["input_files"] = [str(tmp_path / "不存在.csv")]
    with pytest.raises(GateError) as ei:
        start_run(root, exec_id, "R01-a1", spec=spec)
    assert any("输入文件不存在" in e for e in ei.value.errors)
    # 拦下后 run 仍是 planned（未落 running 脏状态）
    assert load_run(root, exec_id, "R01-a1")["status"] == "planned"


# ---------- git 文件级探针 ----------

def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True, capture_output=True, text=True).stdout.strip()


@pytest.mark.skipif(shutil.which("git") is None, reason="本机无 git")
def test_git_probe_reads_real_repo(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "t")
    (repo / "a.txt").write_text("v1\n", encoding="utf-8")
    _git(repo, "add", "a.txt")
    _git(repo, "commit", "-qm", "init")
    _git(repo, "remote", "add", "origin", "https://example.com/x/y.git")
    head = _git(repo, "rev-parse", "HEAD")
    branch = _git(repo, "rev-parse", "--abbrev-ref", "HEAD")

    block, reason = probe_git(repo)
    assert reason is None and block is not None
    assert block["commit"] == head
    assert block["branch"] == branch
    assert block["remote_url"] == "https://example.com/x/y.git"
    assert block["dirty"] is False  # 刚提交完，跟踪文件与 index 一致

    (repo / "a.txt").write_text("v2\n", encoding="utf-8")
    block2, _ = probe_git(repo)
    assert block2["dirty"] is True  # 改了跟踪文件 → 脏

    (repo / "untracked.txt").write_text("x", encoding="utf-8")
    (repo / "a.txt").write_text("v1\n", encoding="utf-8")
    block3, _ = probe_git(repo)
    # 未跟踪文件不计（口径落字在 dirty_probe），跟踪文件已复原 → 不脏
    assert block3["dirty"] is False
    assert "未跟踪" in block3["dirty_probe"]


def test_git_probe_outside_repo_is_honest_absent(tmp_path: Path):
    block, reason = probe_git(tmp_path)
    assert block is None and reason and "git" in reason


# ---------- 内容寻址产物池 ----------

def _finish_with_outputs(exec_pkg, tmp_path: Path) -> dict:
    root, exec_id = exec_pkg
    _started(exec_pkg)
    metrics = tmp_path / "metrics.jsonl"
    metrics.write_text('{"MOTA": 77.8}\n', encoding="utf-8")
    stdout = tmp_path / "stdout.log"
    stdout.write_text("训练完成\n", encoding="utf-8")
    stderr = tmp_path / "stderr.log"
    stderr.write_text("", encoding="utf-8")
    return finish_run(root, exec_id, "R01-a1", exit_status="completed",
                      metrics_file=metrics, stdout_file=stdout,
                      stderr_file=stderr)


def test_finish_pools_products_and_marks_capture(exec_pkg, tmp_path: Path):
    root, exec_id = exec_pkg
    run = _finish_with_outputs(exec_pkg, tmp_path)
    d = exec_dir(root, exec_id)
    obs = run["observation"]
    mr = obs["metrics_ref"]
    assert mr["pool_ref"] == pool_object_relpath(mr["sha256"])
    assert (d / mr["pool_ref"]).is_file()
    kinds = {e["kind"] for e in obs["artifacts"]}
    assert {"stdout", "stderr"} <= kinds
    for e in obs["artifacts"]:
        assert (d / e["pool_ref"]).is_file()
        assert hash_file(d / e["pool_ref"])[0] == e["sha256"]
    cap = _capture_of(run)
    assert cap["finish"]["outputs"] == "captured"
    assert validate_package(load_package(root, exec_id)) == []
    report = verify_pool(d)
    assert report["corrupt"] == [] and report["objects"] == 3


def test_finish_without_outputs_marks_not_provided(exec_pkg):
    root, exec_id = exec_pkg
    _started(exec_pkg)
    run = finish_run(root, exec_id, "R01-a1", exit_status="completed")
    assert _capture_of(run)["finish"]["outputs"] == "not_provided"
    assert validate_package(load_package(root, exec_id)) == []


def test_pool_dedup_same_content_one_object(exec_pkg, tmp_path: Path):
    root, exec_id = exec_pkg
    _started(exec_pkg)
    same = tmp_path / "same.bin"
    same.write_bytes(b"identical-bytes")
    copy = tmp_path / "same-copy.bin"
    copy.write_bytes(b"identical-bytes")
    e1 = register_artifact(root, exec_id, "R01-a1", same, kind="product")
    e2 = register_artifact(root, exec_id, "R01-a1", copy, kind="product")
    assert e1["sha256"] == e2["sha256"] == \
        hashlib.sha256(b"identical-bytes").hexdigest()
    assert e1["pool_ref"] == e2["pool_ref"]
    d = exec_dir(root, exec_id)
    assert verify_pool(d)["objects"] == 1  # 同内容只存一份
    run = load_run(root, exec_id, "R01-a1")
    assert len(run["observation"]["artifacts"]) == 2  # 登记两条、对象一份
    events, _ = read_events(d)
    assert sum(1 for e in events if e["type"] == "artifact_registered") == 2
    assert validate_package(load_package(root, exec_id)) == []


def test_pool_object_tamper_caught_by_validate(exec_pkg, tmp_path: Path):
    root, exec_id = exec_pkg
    run = _finish_with_outputs(exec_pkg, tmp_path)
    d = exec_dir(root, exec_id)
    obj = d / run["observation"]["metrics_ref"]["pool_ref"]
    obj.write_bytes("被改过的指标".encode("utf-8"))
    errs = validate_package(load_package(root, exec_id))
    assert any("池对象" in e and "重哈希" in e for e in errs)
    report = verify_pool(d)
    assert len(report["corrupt"]) == 1


def test_pool_object_missing_caught_by_validate(exec_pkg, tmp_path: Path):
    root, exec_id = exec_pkg
    run = _finish_with_outputs(exec_pkg, tmp_path)
    d = exec_dir(root, exec_id)
    (d / run["observation"]["metrics_ref"]["pool_ref"]).unlink()
    errs = validate_package(load_package(root, exec_id))
    assert any("池对象" in e and "缺失" in e for e in errs)


def test_artifact_add_rejected_for_planned_and_reconciled(
        exec_pkg, tmp_path: Path):
    root, exec_id = exec_pkg
    f = tmp_path / "x.bin"
    f.write_bytes(b"x")
    with pytest.raises(GateError):
        register_artifact(root, exec_id, "R01-a1", f)  # planned 无产物
    _started(exec_pkg)
    finish_run(root, exec_id, "R01-a1", exit_status="completed")
    from light_experiment.gates import advance_run
    run = load_run(root, exec_id, "R01-a1")
    advance_run(run, "reconciled", date="2026-10-21")
    save_run(root, exec_id, run)
    with pytest.raises(GateError):
        register_artifact(root, exec_id, "R01-a1", f)  # 终态封账


def test_legacy_run_without_capture_still_validates(exec_pkg):
    """旧包存档形态：无捕获块、无池引用 → 不拿新口径追溯判死刑。"""
    root, exec_id = exec_pkg
    run = _started(exec_pkg)
    run["observation"]["capture"] = {"start": None, "start_hash": None,
                                     "finish": None}
    save_run(root, exec_id, run)
    pkg = load_package(root, exec_id)
    # 事件锚里有 capture_hash 但块缺席：块缺席即旧形态，不对锚较真
    errs = [e for e in validate_package(pkg) if "捕获" in e or "池" in e]
    assert errs == []


# ---------- 无进展巡检 ----------

def _now() -> datetime:
    return datetime.now(timezone.utc)


def test_watchdog_flags_silent_run_and_records_once(exec_pkg):
    root, exec_id = exec_pkg
    _started(exec_pkg)
    later = _now() + timedelta(hours=2)
    r1 = scan_no_progress(root, exec_id, threshold_s=3600, now=later)
    assert [v["run_id"] for v in r1["verdicts"]] == ["R01-a1"]
    assert len(r1["newly_recorded"]) == 1
    # 判定只留痕不代杀：run 仍 running
    assert load_run(root, exec_id, "R01-a1")["status"] == "running"
    events, _ = read_events(exec_dir(root, exec_id))
    verdict_events = [e for e in events if e["type"] == "no_progress_verdict"]
    assert len(verdict_events) == 1
    assert verdict_events[0]["payload"]["idle_seconds"] >= 3600
    # 同一进展状态重复扫描不刷事件
    r2 = scan_no_progress(root, exec_id, threshold_s=3600,
                          now=later + timedelta(minutes=30))
    assert r2["newly_recorded"] == [] and len(r2["already_recorded"]) == 1
    events2, _ = read_events(exec_dir(root, exec_id))
    assert sum(1 for e in events2
               if e["type"] == "no_progress_verdict") == 1
    assert validate_package(load_package(root, exec_id)) == []


def test_watchdog_heartbeat_keeps_long_run_alive(exec_pkg):
    """反例钉子：正常长运行按规程发心跳 → 永不误判。"""
    root, exec_id = exec_pkg
    _started(exec_pkg)
    d = exec_dir(root, exec_id)
    append_event(d, "heartbeat", run_id="R01-a1",
                 payload={"note": "epoch 40/100"})
    # 心跳刚落：哪怕阈值只有 60 秒也不判（最近进展 = 心跳当下）
    r = scan_no_progress(root, exec_id, threshold_s=60,
                         now=_now() + timedelta(seconds=30))
    assert r["verdicts"] == []
    # 纯判定层同口径：进展事件新鲜 → 无判定
    events, _ = read_events(d)
    pkg = load_package(root, exec_id)
    vs = evaluate_no_progress(events, pkg["runs"], now=_now(),
                              threshold_s=3600)
    assert vs == []


def test_watchdog_ignores_terminal_and_planned(exec_pkg):
    root, exec_id = exec_pkg
    _started(exec_pkg, "R00-a1")
    finish_run(root, exec_id, "R00-a1", exit_status="completed")
    r = scan_no_progress(root, exec_id, threshold_s=1,
                         now=_now() + timedelta(days=1))
    assert r["verdicts"] == [] and r["running"] == []


def test_watchdog_threshold_configurable(exec_pkg):
    root, exec_id = exec_pkg
    _started(exec_pkg)
    soon = _now() + timedelta(minutes=10)
    assert scan_no_progress(root, exec_id, threshold_s=3600,
                            now=soon)["verdicts"] == []
    assert scan_no_progress(root, exec_id, threshold_s=300,
                            now=soon)["verdicts"] != []


def test_cli_artifact_and_watchdog_end_to_end(exec_pkg, tmp_path: Path):
    root, exec_id = exec_pkg
    assert cli_main(["run-start", str(root), exec_id, "R01-a1",
                     "--spec", str(_spec_file(tmp_path))]) == 0
    f = tmp_path / "out.bin"
    f.write_bytes(b"cli-product")
    assert cli_main(["artifact", "add", str(root), exec_id,
                     "--run", "R01-a1", "--file", str(f)]) == 0
    assert cli_main(["artifact", "verify", str(root), exec_id]) == 0
    assert cli_main(["artifact", "list", str(root), exec_id]) == 0
    assert cli_main(["watchdog", "scan", str(root), exec_id]) == 0
    assert cli_main(["run-finish", str(root), exec_id, "R01-a1",
                     "--exit-status", "completed",
                     "--stdout-file", str(f)]) == 0
    assert cli_main(["validate", str(root), exec_id]) == 0
    assert cli_main(["render", str(root), exec_id]) == 0
    report = (exec_dir(root, exec_id) / "EXECUTION_REPORT.md").read_text(
        encoding="utf-8")
    assert "自动捕获与产物池" in report


def _spec_file(tmp_path: Path) -> Path:
    p = tmp_path / "spec.json"
    p.write_text(json.dumps(SPEC), encoding="utf-8")
    return p
