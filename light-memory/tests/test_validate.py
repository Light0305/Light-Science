"""校验器：干净世界通过；逐项破坏各被点名（溯源/指针/双时间/环/
争议一致/索引对账/真相目录数据库文件）。"""

import json

from light_memory import index as index_mod
from light_memory import intake, project as project_mod, registry, schema
from light_memory.supersede import apply_nominations
from light_memory.util import dump_jsonl
from light_memory.validate import validate_package


def _clean_world(mem_root, idea_source, experiment_source,
                 analysis_source):
    intake.ingest(mem_root, "idea", idea_source)
    intake.ingest(mem_root, "experiment", experiment_source)
    intake.ingest(mem_root, "analysis", analysis_source)
    index_mod.build_index(mem_root)
    return mem_root


def _store(root, statement, obj="claim:C1", valid="2026-01-01"):
    pkg = project_mod.load_package(root)
    otype, _, uid = obj.partition(":")
    registry.register_object(
        pkg, otype, uid,
        schema.make_provenance("test", "fixture", "a", "h"))
    project_mod.save_objects(root, pkg["objects"])
    return apply_nominations(root, [{
        "verdict": "store", "nominator": "t",
        "fact": {"statement": statement, "fact_type": "conclusion",
                 "object_id": obj, "valid_at": valid}}])[0]["fact_id"]


def test_clean_world_passes(mem_root, idea_source, experiment_source,
                            analysis_source):
    _clean_world(mem_root, idea_source, experiment_source,
                 analysis_source)
    assert validate_package(mem_root) == []


def test_empty_project_passes(mem_root):
    assert validate_package(mem_root) == []


def test_provenance_missing_field_flagged(mem_root):
    fid = _store(mem_root, "结论")
    facts = project_mod.load_package(mem_root)["facts"]
    facts[0]["provenance"][0]["source_anchor"] = None
    dump_jsonl(mem_root / "facts.jsonl", facts)
    errs = validate_package(mem_root)
    assert any("溯源缺" in e and fid in e for e in errs)


def test_dangling_object_pointer_flagged(mem_root):
    pkg = project_mod.load_package(mem_root)
    prov = schema.make_provenance("test", "fixture", "a", "h")
    fact = schema.new_fact("孤儿事实", "generic", "claim:GHOST", prov,
                           valid_at="2026-01-01")
    dump_jsonl(mem_root / "facts.jsonl", [fact])
    errs = validate_package(mem_root)
    assert any("不存在的对象" in e for e in errs)


def test_illegal_interval_flagged(mem_root):
    _store(mem_root, "占位")
    prov = schema.make_provenance("test", "fixture", "a", "h")
    fact = schema.new_fact("坏区间", "generic", "claim:C1", prov,
                           valid_at="2026-02-01", invalid_at="2026-01-01")
    facts = project_mod.load_package(mem_root)["facts"] + [fact]
    dump_jsonl(mem_root / "facts.jsonl", facts)
    errs = validate_package(mem_root)
    assert any("invalid_at 早于 valid_at" in e for e in errs)


def test_supersede_cycle_flagged(mem_root):
    prov = schema.make_provenance("test", "fixture", "a", "h")
    pkg = project_mod.load_package(mem_root)
    registry.register_object(pkg, "claim", "C1", prov)
    project_mod.save_objects(mem_root, pkg["objects"])
    fa = schema.new_fact("甲", "conclusion", "claim:C1", prov,
                         valid_at="2026-01-01")
    fb = schema.new_fact("乙", "conclusion", "claim:C1", prov,
                         valid_at="2026-02-01")
    fa.update(status="superseded", superseded_by=fb["fact_id"],
              supersedes=fb["fact_id"], invalid_at="2026-02-01")
    fb.update(status="superseded", superseded_by=fa["fact_id"],
              supersedes=fa["fact_id"], invalid_at="2026-01-01")
    dump_jsonl(mem_root / "facts.jsonl", [fa, fb])
    errs = validate_package(mem_root)
    assert any("成环" in e for e in errs)


def test_disputed_without_open_dispute_flagged(mem_root):
    fid = _store(mem_root, "结论")
    facts = project_mod.load_package(mem_root)["facts"]
    facts[0]["status"] = "disputed"
    dump_jsonl(mem_root / "facts.jsonl", facts)
    errs = validate_package(mem_root)
    assert any("无 open 争议账对应" in e for e in errs)


def test_database_file_in_truth_dir_flagged(mem_root):
    (mem_root / "evil.sqlite").write_bytes(b"SQLite format 3\x00")
    errs = validate_package(mem_root)
    assert any("数据库文件" in e for e in errs)


def test_unresolved_relation_needs_target_name(mem_root):
    prov = schema.make_provenance("test", "fixture", "a", "h")
    rel = schema.new_relation("derived-from", "fact_x", None, prov,
                              status="unresolved", target_name=None)
    rel["to_id"] = None
    dump_jsonl(mem_root / "relations.jsonl", [rel])
    errs = validate_package(mem_root)
    assert any("未保留目标原文标识" in e for e in errs)


def test_missing_file_group_flagged(tmp_path):
    root = tmp_path / "memory"
    project_mod.init_package(root)
    (root / "facts.jsonl").unlink()
    errs = validate_package(root)
    assert any("facts.jsonl" in e for e in errs)
