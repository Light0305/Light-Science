"""outer 测试：漏斗统计（LD-06）与外环综合（LD-05）。

夹具口径：now 固定 2026-10-21；事件账含 design 顺进+回退跃迁、
write 50 天前跃迁（停滞样本）、experiment 同类 failure 两条（反复
样本）、一条无归属事件；registry-view 含两项目与一个跨项目同源
对象；promotions 一条在账、一条已撤回。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from light_leader import cli, outer, scan as scan_mod

from conftest import (make_design, make_idea, make_literature,
                      make_manuscript, write_jsonl, write_yaml)

NOW = datetime(2026, 10, 21, tzinfo=timezone.utc)

EVENTS = [
    {"event_id": "EV1", "seq": 1, "ts": "2026-10-20T10:00:00+00:00",
     "type": "milestone", "summary": "设计 draft 到 reviewed",
     "object_id": "design:d1",
     "payload": {"from": "draft", "to": "reviewed"},
     "provenance": {"source_package": "design"}},
    {"event_id": "EV2", "seq": 2, "ts": "2026-10-20T11:00:00+00:00",
     "type": "milestone", "summary": "设计 reviewed 退回 draft",
     "object_id": "design:d1",
     "payload": {"from": "reviewed", "to": "draft"},
     "provenance": {"source_package": "design"}},
    {"event_id": "EV3", "seq": 3, "ts": "2026-09-01T10:00:00+00:00",
     "type": "milestone", "summary": "稿件 outlined 到 drafted",
     "object_id": "manuscript:m1",
     "payload": {"from": "outlined", "to": "drafted"},
     "provenance": {"source_package": "write"}},
    {"event_id": "EV4", "seq": 4, "ts": "2026-10-19T10:00:00+00:00",
     "type": "failure", "summary": "失败 F-1",
     "object_id": "run:r1",
     "payload": {"failure_class": "fundamental",
                 "reflux_target": "design"},
     "provenance": {"source_package": "experiment"}},
    {"event_id": "EV5", "seq": 5, "ts": "2026-10-19T12:00:00+00:00",
     "type": "failure", "summary": "失败 F-2",
     "object_id": "run:r2",
     "payload": {"failure_class": "fundamental",
                 "reflux_target": "design"},
     "provenance": {"source_package": "experiment"}},
    {"event_id": "EV6", "seq": 6, "ts": "2026-10-20T12:00:00+00:00",
     "type": "note", "summary": "无归属注记", "object_id": None,
     "payload": {}, "provenance": {}},
]

OBJECTS = [
    {"object_id": "design:d1", "object_type": "design",
     "upstream_id": "d1", "project": "proj-a", "title": "设计一",
     "status": "active", "current_version": "abc123",
     "source_package": "design"},
    {"object_id": "paper:shared-1", "object_type": "paper",
     "upstream_id": "shared-1", "project": "proj-a", "title": "同源论文",
     "status": "active", "current_version": "def456",
     "source_package": "literature"},
    {"object_id": "paper:shared-1", "object_type": "paper",
     "upstream_id": "shared-1", "project": "proj-b", "title": "同源论文",
     "status": "active", "current_version": "def456",
     "source_package": "literature"},
]

PROMOTIONS = [
    {"promotion_id": "P-0001", "action": "promoted",
     "source_project": "proj-a", "source_fact_id": "f1",
     "object_id": "paper:shared-1"},
    {"promotion_id": "P-0002", "action": "promoted",
     "source_project": "proj-a", "source_fact_id": "f2",
     "object_id": "design:d1"},
    {"promotion_id": "P-0002", "action": "withdrawn",
     "source_project": "proj-a"},
]


def make_stock_project(root, events=EVENTS, with_view=True):
    mem = root / "memory"
    mem.mkdir(parents=True, exist_ok=True)
    write_yaml(mem / "memory.yaml",
               {"kind": "light-memory/project", "memory_id": "demo"})
    write_jsonl(mem / "objects.jsonl", OBJECTS)
    write_jsonl(mem / "events.jsonl", events)
    write_jsonl(mem / "facts.jsonl", [])
    write_jsonl(mem / "relations.jsonl", [])
    write_jsonl(mem / "promotions.jsonl", PROMOTIONS)
    if with_view:
        by_type = {}
        for o in OBJECTS:
            by_type.setdefault(o["object_type"], []).append(
                {k: o[k] for k in ("object_id", "upstream_id", "project",
                                   "title", "status", "current_version",
                                   "source_package")})
        view = {"kind": "light-memory/registry-view", "version": "1.0",
                "memory_id": "demo",
                "generated_at": "2026-10-20T00:00:00+00:00",
                "counts": {t: len(r) for t, r in by_type.items()},
                "objects_by_type": by_type}
        (mem / "registry-view.json").write_text(
            json.dumps(view, ensure_ascii=False, indent=1),
            encoding="utf-8")
    return mem


def build(root):
    make_literature(root)
    make_idea(root, status="pre_mortem_passed",
              review_status="REVIEW_UNAVAILABLE")
    make_design(root, status="reviewed")
    make_manuscript(root, status="drafted")
    make_stock_project(root)
    scan = scan_mod.scan_project(root)
    stock = outer.load_stock(root)
    return scan, stock


def test_funnel_distribution_and_gates(tmp_path):
    scan, stock = build(tmp_path)
    fun = outer.funnel(scan, stock, NOW)
    assert fun["stages"]["idea"]["gates"]["review_unavailable"] == 1
    assert fun["stages"]["design"]["canonical"]["进行中"] == 1
    assert fun["stages"]["write"]["canonical"]["进行中"] == 1
    assert fun["stages"]["patent"]["found"] is False
    assert fun["unattributed_events"] == 1


def test_funnel_rework_rate(tmp_path):
    scan, stock = build(tmp_path)
    rw = outer.funnel(scan, stock, NOW)["rework"]
    assert rw["classifiable"] == 3
    assert rw["backward"] == {"design": 1}
    assert abs(rw["rate"] - 1 / 3) < 1e-9


def test_funnel_conversions(tmp_path):
    scan, stock = build(tmp_path)
    conv = {c["from"]: c for c in outer.funnel(scan, stock, NOW)
            ["conversions"]}
    assert conv["literature"]["denominator"] == 2
    assert conv["literature"]["ratio"] == 0.5
    assert conv["experiment"]["ratio"] is None
    assert conv["experiment"]["denominator"] == 0


def test_funnel_staleness(tmp_path):
    scan, stock = build(tmp_path)
    stages = outer.funnel(scan, stock, NOW)["stages"]
    assert stages["write"]["staleness"] == "长期停滞"
    assert stages["write"]["age_days"] > outer.STALE_DAYS
    assert stages["design"]["staleness"] == "活跃"
    assert stages["idea"]["staleness"].startswith("不可判")


def test_funnel_projects(tmp_path):
    scan, stock = build(tmp_path)
    projects = outer.funnel(scan, stock, NOW)["projects"]
    assert projects["proj-a"]["objects"] == 2
    assert projects["proj-b"]["objects"] == 1
    assert projects["proj-a"]["by_stage"]["design"] == 1


def test_synthesis_findings_and_evidence(tmp_path):
    scan, stock = build(tmp_path)
    fun = outer.funnel(scan, stock, NOW)
    syn = outer.synthesis(scan, stock, fun, NOW)
    kinds = {(f["kind"], f.get("stage")) for f in syn["findings"]}
    assert ("stale", "write") in kinds
    assert ("gate", "idea") in kinds
    assert ("no_evidence", "idea") in kinds
    assert ("rework", "design") in kinds
    rep = [f for f in syn["findings"] if f["kind"] == "failure_repeat"]
    assert len(rep) == 1 and rep[0]["evidence"] == ["EV4", "EV5"]
    reuse = [f for f in syn["findings"] if f["kind"] == "reuse"]
    assert len(reuse) == 1
    assert "晋升在账 1 条" in reuse[0]["title"]
    assert "upstream:shared-1" in reuse[0]["evidence"]
    assert len(syn["timeline"]) == 6
    assert syn["sample"]["events"] == 6
    assert any("停滞阶段 write" in s for s in syn["suggestions"])
    assert any("解 idea 的门" in s for s in syn["suggestions"])


def test_synthesis_empty_events_named(tmp_path):
    make_stock_project(tmp_path, events=[])
    scan = scan_mod.scan_project(tmp_path)
    stock = outer.load_stock(tmp_path)
    fun = outer.funnel(scan, stock, NOW)
    text = outer.render_synthesis(outer.synthesis(scan, stock, fun, NOW),
                                  stock)
    assert "事件账为空" in text
    assert "样本量：事件 0 条" in text


def test_funnel_missing_view_named_not_fatal(tmp_path):
    make_stock_project(tmp_path, with_view=False)
    scan = scan_mod.scan_project(tmp_path)
    stock = outer.load_stock(tmp_path)
    assert stock["view"] is None and stock["view_error"]
    fun = outer.funnel(scan, stock, NOW)
    text = outer.render_funnel(fun, stock)
    assert "registry-view 不可用" in text
    assert fun["projects"] == {}


def test_cli_funnel_and_synthesis(tmp_path, capsys):
    build(tmp_path)
    assert cli.main(["funnel", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "漏斗统计" in out and "阶段分布与门拦截" in out
    assert cli.main(["synthesis", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "外环综合简报" in out and "决策时间线" in out


def test_cli_outer_missing_memory_fails(tmp_path, capsys):
    assert cli.main(["funnel", str(tmp_path)]) == 1
    assert "未找到 memory" in capsys.readouterr().out
    assert cli.main(["synthesis", str(tmp_path)]) == 1
