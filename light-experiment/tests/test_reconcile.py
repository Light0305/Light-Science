"""对账实质化（E6）：分布纪律、随机源警告、三层判定、清零与交付门。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from light_experiment.gates import GateError, advance_package, advance_run
from light_experiment.project import (
    finish_run,
    load_package,
    load_reconciliation,
    load_run,
    save_execution,
    save_run,
    start_run,
)
from light_experiment.reconcile import check_reconciliation, export_card, fill_row

from conftest import SPEC

DATE = "2026-10-20"
READOUT = {"mean": 0.912, "spread": 0.021, "n": 6,
           "replication_level": "video（留一视频）"}
SOURCES = {"rerandomized": ["data_order"], "frozen": []}
LAYERS = {"implementation": True, "execution": True,
          "result_fact": {"verdict": "within", "reason": ""}}


def _advance(root, exec_id, to, **kw):
    pkg = load_package(root, exec_id)
    advance_package(pkg, to, date=DATE, **kw)
    save_execution(root, pkg["execution"])
    return pkg


def _drive(root, exec_id):
    for rid in ("R00-a1", "R01-a1"):
        start_run(root, exec_id, rid, spec=SPEC)
        finish_run(root, exec_id, rid, exit_status="completed")


def test_single_point_readout_rejected(exec_pkg):
    root, exec_id = exec_pkg
    _drive(root, exec_id)
    with pytest.raises(GateError, match="单点"):
        fill_row(root, exec_id, "R00",
                 readout={"value": 0.91}, random_sources=SOURCES,
                 layers=LAYERS)
    with pytest.raises(GateError, match="单点|分布"):
        fill_row(root, exec_id, "R00",
                 readout={"mean": 0.91, "spread": 0.02, "n": 1,
                          "replication_level": "video"},
                 random_sources=SOURCES, layers=LAYERS)


def test_incomparable_requires_reason(exec_pkg):
    root, exec_id = exec_pkg
    layers = {"implementation": True, "execution": True,
              "result_fact": {"verdict": "incomparable", "reason": ""}}
    with pytest.raises(GateError, match="不可比原因"):
        fill_row(root, exec_id, "R00", readout=READOUT,
                 random_sources=SOURCES, layers=layers)


def test_fill_and_check_clearance(exec_pkg):
    root, exec_id = exec_pkg
    _drive(root, exec_id)
    problems = check_reconciliation(root, exec_id)
    assert len(problems) == 2  # 两行都 pending 未清零，逐个点名
    assert all("尚未回填" in p for p in problems)
    fill_row(root, exec_id, "R00", readout=READOUT, random_sources=SOURCES,
             layers=LAYERS, evidence=("runs/R00-a1/run.yaml",))
    row = next(r for r in load_reconciliation(root, exec_id)["rows"]
               if r["registry_run_id"] == "R00")
    assert row["status"] == "filled"
    assert (row["random_sources"] or {}).get("bias_warnings") == []
    fill_row(root, exec_id, "R01", readout=READOUT, random_sources=SOURCES,
             layers=LAYERS)
    assert check_reconciliation(root, exec_id) == []
    from light_experiment.schema import validate_package
    assert validate_package(load_package(root, exec_id)) == []


def test_seed_only_refrozen_bias_warning(exec_pkg):
    root, exec_id = exec_pkg
    _drive(root, exec_id)
    row = fill_row(root, exec_id, "R00", readout=READOUT,
                   random_sources={"rerandomized": ["seed"],
                                   "frozen": ["hyperparameters", "data_split"]},
                   layers=LAYERS)
    warns = row["random_sources"]["bias_warnings"]
    assert warns and "有偏估计" in warns[0]


def test_delivered_gate_after_substantive_fill(exec_pkg):
    root, exec_id = exec_pkg
    _advance(root, exec_id, "sanity")
    _advance(root, exec_id, "executing")
    _drive(root, exec_id)
    _advance(root, exec_id, "reconciling")
    fill_row(root, exec_id, "R00", readout=READOUT, random_sources=SOURCES,
             layers=LAYERS)  # 只填一行 → 包进入实质对账口径
    for rid in ("R00-a1", "R01-a1"):
        run = load_run(root, exec_id, rid)
        advance_run(run, "reconciled", date=DATE)
        save_run(root, exec_id, run)
    pkg = load_package(root, exec_id)
    with pytest.raises(GateError) as ei:
        advance_package(pkg, "delivered", date=DATE)
    assert any("尚未回填" in e and "R01" in e for e in ei.value.errors)
    fill_row(root, exec_id, "R01", readout=READOUT, random_sources=SOURCES,
             layers=LAYERS)
    pkg = _advance(root, exec_id, "delivered")
    assert pkg["execution"]["status"] == "delivered"


def test_export_card_projection(exec_pkg, tmp_path: Path):
    root, exec_id = exec_pkg
    _drive(root, exec_id)
    fill_row(root, exec_id, "R00", readout=READOUT, random_sources=SOURCES,
             layers=LAYERS)
    out = tmp_path / "card.json"
    card = export_card(root, exec_id, out=out)
    assert out.exists()
    assert card["exec_id"] == exec_id
    assert len(card["runs"]) == 2
    assert card["reconciliation"]["rows"][0]["readout_actual"]["n"] == 6
    json.loads(out.read_text(encoding="utf-8"))  # 合法 JSON
