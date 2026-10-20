"""索引层：全量重建、块 ID 含模型名、删索引不丢记忆、漂移对账、
未登记嵌入标注、登记信息照录。"""

import json
import shutil
import sqlite3

from light_memory import index as index_mod
from light_memory import intake, project as project_mod
from light_memory.supersede import apply_nominations
from light_memory.validate import validate_package


def _world(mem_root, idea_source):
    intake.ingest(mem_root, "idea", idea_source)
    (mem_root / "notes").mkdir(exist_ok=True)
    (mem_root / "notes" / "stage-note.md").write_text(
        "# 阶段笔记\n\n零调参阈值预测的方向笔记正文。\n", encoding="utf-8")
    return mem_root


def test_build_index_chunks_and_model_in_id(mem_root, idea_source):
    _world(mem_root, idea_source)
    state = index_mod.build_index(mem_root)
    assert state["counts"]["fact_chunks"] == 1
    assert state["counts"]["note_chunks"] == 1
    assert state["embedder"]["effective"] == "deterministic-test"
    con = sqlite3.connect(mem_root / ".index" / "memory_index.sqlite")
    rows = con.execute("SELECT chunk_id, model FROM chunks").fetchall()
    con.close()
    assert rows and all(m == "deterministic-test-v1" for _, m in rows)
    assert all(cid.startswith("chk_") for cid, _ in rows)


def test_search_primitives_find_content(mem_root, idea_source):
    _world(mem_root, idea_source)
    index_mod.build_index(mem_root)
    hits = index_mod.search_fts(mem_root, "阈值")
    assert hits and hits[0]["source_kind"] in ("fact", "note")
    vec = index_mod.search_vector(mem_root, "零调参阈值预测")
    assert vec and "score" in vec[0]


def test_delete_index_loses_nothing_and_rebuilds(mem_root, idea_source):
    _world(mem_root, idea_source)
    index_mod.build_index(mem_root)
    facts_before = project_mod.load_package(mem_root)["facts"]
    shutil.rmtree(mem_root / ".index")
    # 索引整删后：记忆本体一字不少，校验照常通过（MM-03 的可执行验收）
    assert project_mod.load_package(mem_root)["facts"] == facts_before
    assert validate_package(mem_root) == []
    assert index_mod.index_status(mem_root)["status"] == "absent"
    index_mod.build_index(mem_root)
    assert index_mod.index_status(mem_root)["status"] == "current"
    assert index_mod.search_fts(mem_root, "阈值")


def test_truth_drift_marks_index_stale(mem_root, idea_source):
    _world(mem_root, idea_source)
    index_mod.build_index(mem_root)
    apply_nominations(mem_root, [{
        "verdict": "store", "nominator": "t",
        "fact": {"statement": "新事实", "fact_type": "generic",
                 "object_id": "idea_card:idea-alpha_123abc",
                 "valid_at": "2026-10-20"}}])
    status = index_mod.index_status(mem_root)
    assert status["status"] == "stale"
    assert "facts.jsonl" in status["changed"]
    assert any("stale" in e for e in validate_package(mem_root))


def test_registered_embedder_recorded_but_effective_is_test(
        mem_root, idea_source):
    pkg = project_mod.load_package(mem_root)
    memory = pkg["memory"]
    memory["embedder"] = {"provider": "api", "model": "embed-x",
                          "dim": 1024}
    project_mod.save_memory(mem_root, memory)
    _world(mem_root, idea_source)
    state = index_mod.build_index(mem_root)
    # 登记信息照录，有效嵌入如实回落并标注（不冒充已用登记模型）
    assert state["embedder"]["registered_model"] == "embed-x"
    assert state["embedder"]["effective"] == "deterministic-test"
    assert "回落" in state["embedder"]["note"]


def test_index_state_ledger_per_file(mem_root, idea_source):
    _world(mem_root, idea_source)
    state = index_mod.build_index(mem_root)
    assert state["truth_files"]["facts.jsonl"]["status"] == "done"
    on_disk = json.loads((mem_root / ".index" / "index-state.json")
                         .read_text(encoding="utf-8"))
    assert on_disk["truth_manifest_hash"] == state["truth_manifest_hash"]
