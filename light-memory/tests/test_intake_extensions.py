"""MM2-13 新三包承接适配器（v1.1 集成步）：patent / software-copyright
/ crawler 各一条 ingest 冒烟（产物入四账、溯源五字段完整、validate
零错误）+ 水位线幂等。夹具字段形态照三包真实演示产物裁剪。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from light_memory import intake, project as project_mod, schema
from light_memory.validate import validate_package


def _write_yaml(path: Path, obj) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(obj, allow_unicode=True,
                                   sort_keys=False), encoding="utf-8")
    return path


def _write_jsonl(path: Path, rows) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n"
                            for r in rows), encoding="utf-8")
    return path


def _pkg(root):
    return project_mod.load_package(root)


def _assert_provenance_complete(root):
    pkg = _pkg(root)
    # 对象行沿既有模型扁平存 source_package / source_version 两字段；
    # 事件/事实/关系行带完整溯源五字段 dict（或事实的溯源列表）。
    for row in pkg["objects"] or []:
        assert row.get("source_package"), row
        assert row.get("source_version"), row
    for coll in ("events", "facts", "relations"):
        for row in pkg[coll] or []:
            provs = row.get("provenance")
            provs = provs if isinstance(provs, list) else [provs]
            for prov in provs:
                assert schema.provenance_gaps(prov) == [], (coll, row)


# ---------------------------------------------------------------- Patent

@pytest.fixture()
def patent_source(tmp_path) -> Path:
    d = tmp_path / "patent-case"
    _write_yaml(d / "case.yaml", {
        "kind": "light-patent/case", "version": "1.0",
        "case_id": "PT-case_test1", "title": "一种演示检测方法",
        "patent_type": "invention", "jurisdiction": "CN",
        "status": "responded",
        "status_history": [
            {"state": "intake", "at": "2026-10-20", "by": "init"},
            {"state": "filed", "at": "2026-10-20", "by": "ledger file"},
            {"state": "responded", "at": "2026-10-20", "by": "oa amend"},
        ],
        "blocked": None,
    })
    _write_yaml(d / "ledger.yaml", {
        "kind": "light-patent/ledger", "case_id": "PT-case_test1",
        "deadlines": [
            {"kind": "office_action_response", "label": "审查意见答复期",
             "due": "2027-07-01", "basis": "以通知书为准"},
        ],
        "memory_export": {
            "objects": [{"object": "patent_case",
                         "case_id": "PT-case_test1",
                         "title": "一种演示检测方法",
                         "status": "office_action"}],
            "events": [{"event": "deadline:office_action_response",
                        "due": "2027-07-01"}],
            "facts": [
                {"fact": "查新门=pass_with_doubts，D1=DOI:10.0000/demo",
                 "evidence_ref": "novelty/d1.yaml",
                 "disclaimers": ["只作初筛底稿、不作法律意见"]},
                {"fact": "worth-it=file_narrowed",
                 "evidence_ref": "ledger.yaml#worth_it",
                 "disclaimers": ["只作初筛底稿、不作法律意见"]},
            ],
        },
    })
    return d


def test_ingest_patent(mem_root, patent_source):
    rep = intake.ingest(mem_root, "patent", patent_source)
    assert rep["status"] == "ingested"
    assert rep["gaps"] == []
    objs = {o["object_id"]: o for o in _pkg(mem_root)["objects"]}
    assert "patent_case:PT-case_test1" in objs
    events = _pkg(mem_root)["events"]
    states = [e["payload"].get("state") for e in events
              if e["type"] == "milestone"]
    # 状态以案件头 status_history 为权威（含 export 段滞后的 responded）
    assert states == ["intake", "filed", "responded"]
    deadlines = [e for e in events if e["type"] == "deadline"]
    assert len(deadlines) == 1
    assert deadlines[0]["payload"]["due"] == "2027-07-01"
    facts = [f for f in _pkg(mem_root)["facts"]
             if f["fact_type"] == "patent_assessment"]
    assert len(facts) == 2
    assert facts[0]["extra"]["evidence_ref"] == "novelty/d1.yaml"
    assert facts[0]["extra"]["disclaimers"] == ["只作初筛底稿、不作法律意见"]
    _assert_provenance_complete(mem_root)
    assert validate_package(mem_root) == []


def test_ingest_patent_missing_ledger_gap(mem_root, tmp_path):
    d = tmp_path / "patent-bare"
    _write_yaml(d / "case.yaml", {
        "kind": "light-patent/case", "case_id": "PT-case_bare",
        "title": "无台账案件", "status": "intake", "status_history": []})
    rep = intake.ingest(mem_root, "patent", d)
    assert any("ledger.yaml" in g for g in rep["gaps"])
    assert "patent_case:PT-case_bare" in \
        {o["object_id"] for o in _pkg(mem_root)["objects"]}


# ---------------------------------------------------------------- Copyright

@pytest.fixture()
def copyright_source(tmp_path) -> Path:
    d = tmp_path / "copyright-case"
    _write_yaml(d / "copyright.yaml", {
        "kind": "light-software-copyright/case", "version": 1,
        "title": "演示工具软著案", "status": "packaged",
        "correction": None})
    _write_yaml(d / "facts.yaml", {
        "software": {"full_name": "演示工具", "short_name": "演示",
                     "version": "V1.0", "kind": "headless"},
        "owner": {"name": "演示著作权人", "type": "自然人"},
        "development": {"mode": "independent",
                        "completion_date": "2026-09-15"},
        "publication": {"status": "unpublished"},
        "rights": {"acquisition": "原始取得"}})
    _write_jsonl(d / "tool_use.jsonl", [
        {"ts": "2026-10-20", "actor": "tool", "action": "init",
         "target": "case", "detail": "建案"},
        {"ts": "2026-10-20", "actor": "tool", "action": "package",
         "target": "资料包", "detail": "产出材料文件 + 递交清单"},
    ])
    _write_jsonl(d / "confirmations.jsonl", [
        {"ts": "2026-10-20", "actor": "user", "kind": "facts",
         "target": "facts", "content_hash": "a" * 64, "note": "确认"},
    ])
    (d / "snapshot.json").write_text(json.dumps({
        "kind": "light-software-copyright/snapshot",
        "frozen_at": "2026-10-20", "file_count": 2, "total_lines": 40,
        "nonempty_lines": 35, "languages": ["Python"],
        "files": [{"path": "a.py", "sha256": "b" * 64}]},
        ensure_ascii=False), encoding="utf-8")
    return d


def test_ingest_copyright(mem_root, copyright_source):
    rep = intake.ingest(mem_root, "software-copyright", copyright_source)
    assert rep["status"] == "ingested"
    assert rep["gaps"] == []
    objs = {o["object_id"]: o for o in _pkg(mem_root)["objects"]}
    assert "copyright_case:演示工具@V1.0" in objs
    events = _pkg(mem_root)["events"]
    assert sum(1 for e in events if e["type"] == "tool_use") == 2
    confs = [e for e in events if e["type"] == "confirmation"]
    assert len(confs) == 1
    assert confs[0]["payload"]["content_hash"] == "a" * 12
    facts = _pkg(mem_root)["facts"]
    kinds = {f["fact_type"] for f in facts}
    assert "copyright_facts" in kinds and "source_snapshot" in kinds
    snap = next(f for f in facts if f["fact_type"] == "source_snapshot")
    assert snap["extra"]["file_count"] == 2
    # 无 registration_no 时不落登记号事实、也不点名缺口
    assert "copyright_registration" not in kinds
    _assert_provenance_complete(mem_root)
    assert validate_package(mem_root) == []


def test_ingest_copyright_with_registration_no(mem_root, copyright_source):
    head = copyright_source / "copyright.yaml"
    data = yaml.safe_load(head.read_text(encoding="utf-8"))
    data["registration_no"] = "2026SR0000000"
    _write_yaml(head, data)
    intake.ingest(mem_root, "software-copyright", copyright_source)
    regs = [f for f in _pkg(mem_root)["facts"]
            if f["fact_type"] == "copyright_registration"]
    assert len(regs) == 1
    assert "2026SR0000000" in regs[0]["statement"]


# ---------------------------------------------------------------- Crawler

@pytest.fixture()
def crawler_source(tmp_path) -> Path:
    d = tmp_path / "data-sources"
    _write_yaml(d / "crawler.yaml", {
        "kind": "light-crawler/workspace", "version": 1,
        "workspace_id": "ws-test1", "project": "demo-proj",
        "status": "active", "circuit_broken_targets": []})
    tdir = d / "targets" / "demo-api"
    _write_yaml(tdir / "target.yaml", {
        "target_id": "demo-api", "name": "演示目标",
        "base_url": "http://127.0.0.1:9", "channel": "official_api",
        "purpose_kind": "dataset_batch", "consumer": "light-experiment"})
    _write_yaml(tdir / "state.yaml", {
        "target_id": "demo-api", "consecutive_refusals": 0,
        "circuit_broken": False, "circuit_reason": None})
    _write_jsonl(d / "events.jsonl", [
        {"event_id": "ev-1", "at": "2026-10-20T00:00:00+00:00",
         "type": "target_registered", "target_id": "demo-api",
         "detail": "通道 official_api", "data": {}},
        {"event_id": "ev-2", "at": "2026-10-20T00:00:01+00:00",
         "type": "fetch_run_finished", "target_id": "demo-api",
         "detail": "run 结束：落盘 1", "data": {"status": "finished"}},
    ])
    _write_jsonl(d / "provenance.jsonl", [
        {"prov_id": "pv-1", "at": "2026-10-20T00:00:01+00:00",
         "kind": "fetch", "target_id": "demo-api", "run_id": "run-1",
         "url": "http://127.0.0.1:9/data.json", "channel": "official_api",
         "http_status": 200, "bytes": 63, "sha256": "c" * 64,
         "raw_path": "store/c/x", "precheck_ref": "pc-1",
         "retention_tier": "lightweight_raw_plus_hash",
         "fingerprint": "d" * 64, "supersedes": None},
    ])
    return d


def test_ingest_crawler(mem_root, crawler_source):
    rep = intake.ingest(mem_root, "crawler", crawler_source)
    assert rep["status"] == "ingested"
    assert rep["gaps"] == []
    objs = {o["object_id"]: o for o in _pkg(mem_root)["objects"]}
    assert "crawl_workspace:ws-test1" in objs
    assert "crawl_target:demo-api" in objs
    rels = _pkg(mem_root)["relations"]
    assert any(r["type"] == "derived-from"
               and r["from_id"] == "crawl_target:demo-api"
               and r["to_id"] == "crawl_workspace:ws-test1"
               for r in rels)
    events = [e for e in _pkg(mem_root)["events"] if e["type"] == "stage"]
    assert len(events) == 2
    assert events[0]["payload"]["upstream_event_id"] == "ev-1"
    facts = _pkg(mem_root)["facts"]
    prov = [f for f in facts if f["fact_type"] == "crawl_provenance"]
    assert len(prov) == 1
    assert prov[0]["extra"]["sha256"] == "c" * 64
    assert prov[0]["provenance"][0]["source_anchor"] == "pv-1"
    profiles = [f for f in facts
                if f["fact_type"] == "crawl_target_profile"]
    assert len(profiles) == 1
    _assert_provenance_complete(mem_root)
    assert validate_package(mem_root) == []


# ---------------------------------------------------------------- 幂等

def test_ingest_extensions_idempotent(mem_root, patent_source,
                                      copyright_source, crawler_source):
    for package, source in (("patent", patent_source),
                            ("software-copyright", copyright_source),
                            ("crawler", crawler_source)):
        first = intake.ingest(mem_root, package, source)
        assert first["status"] == "ingested"
        counts_before = {k: len(_pkg(mem_root)[k] or [])
                         for k in ("objects", "events", "facts",
                                   "relations")}
        second = intake.ingest(mem_root, package, source)
        assert second["status"] == "unchanged"
        counts_after = {k: len(_pkg(mem_root)[k] or [])
                        for k in ("objects", "events", "facts",
                                  "relations")}
        assert counts_before == counts_after
    assert validate_package(mem_root) == []
