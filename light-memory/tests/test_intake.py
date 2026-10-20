"""M0 承接：九包各至少一例、水位线幂等、上游漂移、缺项点名不假装、
失败停在水位线原处。"""

import json

import pytest

from light_memory import intake, project as project_mod
from light_memory.intake import IntakeError


def _pkg(root):
    return project_mod.load_package(root)


def _objects(root):
    return {o["object_id"]: o for o in _pkg(root)["objects"]}


def _facts(root):
    return _pkg(root)["facts"]


# ---------------------------------------------------------------- 各包

def test_ingest_idea(mem_root, idea_source):
    rep = intake.ingest(mem_root, "idea", idea_source)
    assert rep["status"] == "ingested"
    assert "idea_card:idea-alpha_123abc" in _objects(mem_root)
    facts = [f for f in _facts(mem_root) if f["fact_type"] == "direction"]
    assert len(facts) == 1
    assert facts[0]["provenance"][0]["source_package"] == "idea"
    assert facts[0]["extra"]["boundary_conditions"] == ["仅限顶视固定机位"]


def test_ingest_experiment(mem_root, experiment_source):
    rep = intake.ingest(mem_root, "experiment", experiment_source)
    assert rep["counts"]["events"] >= 5  # 里程碑+2 阶段+失败+复核
    facts = [f for f in _facts(mem_root)
             if f["fact_type"] == "failure_record"]
    assert len(facts) == 1
    assert facts[0]["extra"]["failure_class"] == "fundamental"
    assert facts[0]["extra"]["reflux_target"] == "design"
    objs = _objects(mem_root)
    assert "run:R-NEG-a1" in objs and "execution:exec-b2" in objs
    rels = _pkg(mem_root)["relations"]
    assert any(r["type"] == "derived-from" for r in rels)


def test_ingest_analysis(mem_root, analysis_source):
    intake.ingest(mem_root, "analysis", analysis_source)
    objs = _objects(mem_root)
    assert objs["execution:exec-b2"]["status"] == "referenced"
    assert "claim:C1" in objs
    facts = [f for f in _facts(mem_root)
             if f["fact_type"] == "conclusion_verdict"]
    assert len(facts) == 1
    assert facts[0]["extra"]["support"] == "untested"
    assert facts[0]["extra"]["grade"] == "insufficient"
    rels = _pkg(mem_root)["relations"]
    assert sum(1 for r in rels if r["type"] == "depends-on") == 2


def test_analysis_reference_promoted_by_experiment(
        mem_root, analysis_source, experiment_source):
    intake.ingest(mem_root, "analysis", analysis_source)
    assert _objects(mem_root)["execution:exec-b2"]["status"] == "referenced"
    intake.ingest(mem_root, "experiment", experiment_source)
    assert _objects(mem_root)["execution:exec-b2"]["status"] == "active"


def test_ingest_figure(mem_root, figure_source):
    rep = intake.ingest(mem_root, "figure", figure_source)
    objs = _objects(mem_root)
    assert "figure:fig-1" in objs and "figure:fig-2" in objs
    facts = [f for f in _facts(mem_root)
             if f["fact_type"] == "figure_provenance"]
    assert len(facts) == 2
    assert any("delivery.yaml" in g for g in rep["gaps"])  # 缺项点名


def test_ingest_journal_select(mem_root, journal_source):
    rep = intake.ingest(mem_root, "journal-select", journal_source)
    facts = _facts(mem_root)
    decisions = [f for f in facts if f["fact_type"] == "decision"]
    assert len(decisions) == 1
    assert "Smart Agricultural Technology" in decisions[0]["statement"]
    journals = [f for f in facts if f["fact_type"] == "journal_fact"]
    assert len(journals) == 1  # 只有已核验的 apc 落值，未核验不落
    assert "USD 1200" in journals[0]["statement"]
    assert rep["gaps"] == []


def test_ingest_design(mem_root, design_source):
    rep = intake.ingest(mem_root, "design", design_source)
    facts = [f for f in _facts(mem_root)
             if f["fact_type"] == "design_claim"]
    assert len(facts) == 1
    events = _pkg(mem_root)["events"]
    assert any(e["type"] == "decision" for e in events)  # 用户签的修订
    assert any(e["type"] == "milestone" for e in events)  # 冻结
    assert any("无字段标识" in g for g in rep["gaps"])


def test_ingest_literature(mem_root, literature_source):
    rep = intake.ingest(mem_root, "literature", literature_source)
    facts = [f for f in _facts(mem_root) if f["fact_type"] == "evidence"]
    assert len(facts) == 2
    assert facts[0]["provenance"][0]["source_anchor"] \
        .endswith("阅读笔记.md#10")  # 锚点原样保留为回指
    objs = _objects(mem_root)
    assert objs["paper:paper-turkey_abc"]["title"] == \
        "Abnormal turkey behaviour"
    assert any("撤稿" in g for g in rep["gaps"])  # 无结构化源，如实点名


def test_ingest_write(mem_root, write_source):
    rep = intake.ingest(mem_root, "write", write_source)
    events = [e for e in _pkg(mem_root)["events"]
              if e["type"] == "tool_use"]
    assert len(events) == 1  # 缺 model_version 的一条只登记不入账
    assert any("model_version" in g for g in rep["gaps"])
    assert "claim:C1" in _objects(mem_root)


def test_ingest_review(mem_root, review_source):
    rep = intake.ingest(mem_root, "review", review_source)
    facts = [f for f in _facts(mem_root)
             if f["fact_type"] == "review_concern"]
    assert len(facts) == 1
    assert facts[0]["extra"]["severity"] == "major"
    rels = _pkg(mem_root)["relations"]
    assert any(r["type"] == "derived-from"
               and r["from_id"] == "concern:RV-C001"
               and r["to_id"] == "claim:C1" for r in rels)
    assert any("关闭" in g for g in rep["gaps"])


# ---------------------------------------------------------------- 水位线

def test_ingest_idempotent_via_watermark(mem_root, idea_source):
    intake.ingest(mem_root, "idea", idea_source)
    n_events = len(_pkg(mem_root)["events"])
    rep = intake.ingest(mem_root, "idea", idea_source)
    assert rep["status"] == "unchanged"
    assert len(_pkg(mem_root)["events"]) == n_events
    assert len(_facts(mem_root)) == 1


def test_ingest_detects_upstream_drift(mem_root, idea_source):
    first = intake.ingest(mem_root, "idea", idea_source)
    rows = [json.loads(line) for line in
            idea_source.read_text(encoding="utf-8").splitlines()]
    rows.append(dict(rows[0], entry_id="DIR-idea-beta_456def",
                     summary="第二个方向",
                     source={"idea_id": "idea-beta_456def"}))
    idea_source.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
        encoding="utf-8")
    rep = intake.ingest(mem_root, "idea", idea_source)
    assert rep["status"] == "ingested"
    assert rep["previous_hash"] == first["snapshot_hash"]
    assert rep["snapshot_hash"] != first["snapshot_hash"]
    assert len(_facts(mem_root)) == 2  # 只增新行，旧行不重复入账


def test_ingest_missing_source_and_unknown_package(mem_root, tmp_path):
    with pytest.raises(IntakeError):
        intake.ingest(mem_root, "idea", tmp_path / "不存在.jsonl")
    with pytest.raises(IntakeError):
        intake.ingest(mem_root, "nope", tmp_path)


def test_failed_ingest_leaves_watermark_untouched(mem_root, tmp_path):
    bad = tmp_path / "exec-empty"
    bad.mkdir()  # 缺 execution_card.json
    with pytest.raises(IntakeError):
        intake.ingest(mem_root, "experiment", bad)
    memory = _pkg(mem_root)["memory"]
    assert memory["watermarks"] == {}
    assert _facts(mem_root) == []
