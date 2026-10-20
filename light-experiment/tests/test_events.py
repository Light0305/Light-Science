"""事件日志只增性：序号连续 / 时间戳不倒退 / 词表与 schema。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from light_experiment.events import append_event, read_events, validate_events
from light_experiment.project import exec_dir, load_package
from light_experiment.schema import validate_package


def _ev(seq: int, ts: str, type: str = "note") -> dict:
    return {"seq": seq, "event_id": f"EV-{seq:06d}", "ts": ts, "type": type,
            "source": "tool", "run_id": None, "parent_event_id": None,
            "payload": {}}


def test_append_assigns_sequential_ids(exec_pkg):
    root, exec_id = exec_pkg
    d = exec_dir(root, exec_id)
    before, _ = read_events(d)
    ev = append_event(d, "human_checkpoint", source="user",
                      payload={"decision": "approve"})
    assert ev["seq"] == len(before) + 1
    assert ev["event_id"] == f"EV-{ev['seq']:06d}"
    events, errors = read_events(d)
    assert errors == []
    assert validate_events(events) == []


def test_append_rejects_type_outside_vocabulary(exec_pkg):
    root, exec_id = exec_pkg
    with pytest.raises(ValueError, match="不在词表"):
        append_event(exec_dir(root, exec_id), "随便写个类型")


def test_seq_gap_detected(exec_pkg):
    root, exec_id = exec_pkg
    d = exec_dir(root, exec_id)
    append_event(d, "note", payload={"n": 1})
    append_event(d, "note", payload={"n": 2})
    lines = (d / "events.jsonl").read_text(encoding="utf-8").splitlines()
    del lines[1]  # 删一行：只增日志被动过手脚
    (d / "events.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    errs = validate_package(load_package(root, exec_id))
    assert any("序号不连续" in e for e in errs)


def test_timestamp_regression_detected():
    events = [_ev(1, "2026-10-20T10:00:00+00:00"),
              _ev(2, "2026-10-20T09:00:00+00:00")]
    errs = validate_events(events)
    assert any("时间戳倒退" in e for e in errs)


def test_event_id_must_be_derived():
    ev = _ev(1, "2026-10-20T10:00:00+00:00")
    ev["event_id"] = "EV-999999"
    errs = validate_events([ev])
    assert any("event_id" in e for e in errs)


def test_event_missing_field_detected():
    ev = _ev(1, "2026-10-20T10:00:00+00:00")
    del ev["source"]
    errs = validate_events([ev])
    assert any("缺字段 source" in e for e in errs)


def test_corrupt_jsonl_line_reported(exec_pkg):
    root, exec_id = exec_pkg
    d = exec_dir(root, exec_id)
    with open(d / "events.jsonl", "a", encoding="utf-8") as f:
        f.write("{坏行\n")
    pkg = load_package(root, exec_id)
    assert pkg["event_errors"]
    errs = validate_package(pkg)
    assert any("事件日志" in e for e in errs)
    # 日志损坏后拒绝继续追加（不许在坏账上续写）
    with pytest.raises(ValueError, match="已损坏"):
        append_event(d, "note")


def test_intake_event_recorded(exec_pkg):
    root, exec_id = exec_pkg
    events, _ = read_events(exec_dir(root, exec_id))
    types = [e["type"] for e in events]
    assert types[0] == "intake_done"
    assert types.count("run_created") == 2
    # run_started 事件带哈希锚（防回改的钉子）
    from light_experiment.project import start_run
    from conftest import SPEC
    start_run(root, exec_id, "R00-a1", spec=SPEC)
    events, _ = read_events(exec_dir(root, exec_id))
    started = [e for e in events if e["type"] == "run_started"]
    assert started and started[0]["payload"]["identity_hash"]
