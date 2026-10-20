"""v1.1 必做项回归：MM2-09 / MM2-03a/b/e / MM2-01 / MM2-02。

口径：既有测试一字不改，本文件只增。真实嵌入的实模型冒烟在
fastembed 或模型不可用时 skip（管线基线不依赖外网与模型下载）。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from light_memory import bench, candidates as cand
from light_memory import cli, epilogue, index as index_mod
from light_memory import obsidian as obs
from light_memory import project as project_mod, registry, schema


# ---------------------------------------------------------------- MM2-09

def test_candidate_list_default_shows_all_kinds(mem_root, capsys):
    cand.propose(mem_root, "fact",
                 {"nomination": {"verdict": "store",
                                 "fact": {"statement": "一条事实草稿",
                                          "fact_type": "generic",
                                          "object_id": "method:m1"}}},
                 nominator="t")
    cand.propose(mem_root, "annotation", {"text": "一条标注"},
                 nominator="t")
    assert cli.main(["candidate", str(mem_root), "list"]) == 0
    out = capsys.readouterr().out
    assert "[fact]" in out and "[annotation]" in out
    assert cli.main(["candidate", str(mem_root), "list",
                     "--kind", "annotation"]) == 0
    out = capsys.readouterr().out
    assert "[annotation]" in out and "[fact]" not in out


# ---------------------------------------------------------------- MM2-03

@pytest.fixture()
def world(tmp_path):
    base = tmp_path / "world"
    bench.build_mini_world(base)
    return base


def _note_text(world, slug_part: str) -> str:
    vault = world / "proj-a" / "obsidian"
    hits = [p for p in vault.glob("*.md") if slug_part in p.name]
    assert hits, f"未找到笔记 {slug_part}"
    return hits[0].read_text(encoding="utf-8")


def test_frontmatter_query_surface(world):
    obs.project_obsidian(world / "proj-a")
    text = _note_text(world, "claim-c1")
    fm = text.split("---")[1]
    assert re.search(r"^memory_id: claim:C1$", fm, re.M)
    assert re.search(r"^obj_type: claim$", fm, re.M)
    assert re.search(r"^stage: Analysis$", fm, re.M)
    assert re.search(r"^status: ", fm, re.M)
    assert re.search(r"^source_pkg: analysis$", fm, re.M)
    # v1 失效、v2 现行：valid_from 取最早，invalid_at 省略（仍有效）
    assert re.search(r"^valid_from: 2026-01-01$", fm, re.M)
    assert "invalid_at:" not in fm


def test_relation_type_keys_are_field_safe():
    for key in schema.RELATION_TYPES:
        assert key == key.lower() and " " not in key \
            and "_" not in key, key


def test_typed_edge_double_write(world):
    obs.project_obsidian(world / "proj-a")
    idea_note = _note_text(world, "idea-card")
    # 出边双写：人读行 + 内联字段行各一份
    assert re.search(r"^- supports \[\[claim-c1\]\]", idea_note, re.M)
    assert re.search(r"^- supports:: \[\[claim-c1\]\]", idea_note, re.M)
    claim_note = _note_text(world, "claim-c1")
    # 入边只留人读形，不写同名字段（防语义反转）
    assert "被 supports" in claim_note
    assert not re.search(r"^- supports:: ", claim_note, re.M)


def test_view_lint_clean_after_projection(world):
    obs.project_obsidian(world / "proj-a")
    assert obs.view_lint(world / "proj-a") == []


def test_view_lint_broken_link(world):
    obs.project_obsidian(world / "proj-a")
    vault = world / "proj-a" / "obsidian"
    target = next(vault.glob("*idea-card*.md"))
    target.unlink()
    cats = {f["category"] for f in obs.view_lint(world / "proj-a")}
    assert "broken_link" in cats


def test_view_lint_projection_stale(world):
    root = world / "proj-a"
    obs.project_obsidian(root)
    pkg = project_mod.load_package(root)
    pkg["facts"][0]["statement"] += "（已修订）"
    project_mod.save_facts(root, pkg["facts"])
    cats = {f["category"] for f in obs.view_lint(root)}
    assert "projection_stale" in cats


def test_view_lint_orphan_archived(world):
    root = world / "proj-a"
    obs.project_obsidian(root)
    pkg = project_mod.load_package(root)
    for o in pkg["objects"]:
        if o["object_id"] == "claim:C1":
            o["status"] = "archived"
    project_mod.save_objects(root, pkg["objects"])
    hits = [f for f in obs.view_lint(root)
            if f["category"] == "view_orphan"]
    assert hits and "archived" in hits[0]["detail"]


def test_view_lint_unresolved_relation(world):
    root = world / "proj-a"
    obs.project_obsidian(root)
    pkg = project_mod.load_package(root)
    prov = schema.make_provenance("idea", "memory_export.jsonl",
                                  "DIR-x", "v1")
    pkg["relations"].append(schema.new_relation(
        "depends-on", "claim:C1", None, prov, status="unresolved",
        target_name="尚未出现的执行包"))
    project_mod.save_relations(root, pkg["relations"])
    hits = [f for f in obs.view_lint(root)
            if f["category"] == "unresolved_relation"]
    assert hits and "尚未出现的执行包" in hits[0]["detail"]


# ---------------------------------------------------------------- MM2-01

TRANSCRIPT = """# 火鸡项目会话记录

user: 我们决定跟踪器阈值改用视频级统计量预测，不再手工逐段调参。
assistant: 收到。另外直接套用 MOT17 默认阈值的那条路，刚才验证过走不通。
user: 对，MOT17 默认阈值在顶视固定机位上完全失效，这条路放弃，别再试了。
assistant: 实验结论更新：复核后 MOTA 提升应修正为 3.10 个百分点，采纳修正版。
"""


def _epilogue_setup(tmp_path, mem_root):
    transcript = tmp_path / "transcript.md"
    transcript.write_text(TRANSCRIPT, encoding="utf-8")
    scan = epilogue.scan_transcript(transcript)
    scan_path = tmp_path / "scan.json"
    scan_path.write_text(json.dumps(scan, ensure_ascii=False),
                         encoding="utf-8")
    pkg = project_mod.load_package(mem_root)
    prov = schema.make_provenance("idea", "memory_export.jsonl",
                                  "DIR-x", "v1")
    registry.register_object(pkg, "method", "tracker-threshold", prov,
                             project="proj-demo", title="阈值预测方法")
    project_mod.save_objects(mem_root, pkg["objects"])
    return transcript, scan, scan_path


def _seg_of(scan, needle: str) -> str:
    for s in scan["segments"]:
        if needle in s["text"]:
            return s["seg_id"]
    raise AssertionError(f"段未找到：{needle}")


def test_epilogue_scan_segments_and_speakers(tmp_path, mem_root):
    _, scan, _ = _epilogue_setup(tmp_path, mem_root)
    speakers = [s["speaker"] for s in scan["segments"]]
    assert speakers.count("user") == 2 and speakers.count("ai") == 2


def test_epilogue_apply_produces_candidates_only(tmp_path, mem_root):
    _, scan, scan_path = _epilogue_setup(tmp_path, mem_root)
    items = [
        {"category": "decision", "source_tag": "user",
         "segment_refs": [_seg_of(scan, "我们决定")],
         "statement": "决定：跟踪器阈值改用视频级统计量预测",
         "object_id": "method:tracker-threshold",
         "valid_at": "2026-10-21"},
        {"category": "dead_end", "source_tag": "user",
         "segment_refs": [_seg_of(scan, "这条路放弃")],
         "statement": "死胡同：MOT17 默认阈值在顶视机位失效，已放弃",
         "object_id": "method:tracker-threshold",
         "valid_at": "2026-10-21"},
        {"category": "decision", "source_tag": "ai",
         "segment_refs": [_seg_of(scan, "采纳修正版")],
         "statement": "决定：采纳 MOTA 提升 3.10 个百分点修正版",
         "object_id": "method:tracker-threshold",
         "valid_at": "2026-10-21"},
    ]
    noms = tmp_path / "noms.json"
    noms.write_text(json.dumps({"items": items}, ensure_ascii=False),
                    encoding="utf-8")
    res = epilogue.apply_epilogue(mem_root, scan_path, noms)
    assert res["gaps"] == [] and len(res["created"]) == 3
    rows = cand.list_candidates(mem_root)
    assert len(rows) == 3
    cats = sorted(r["content"]["epilogue"]["category"] for r in rows)
    assert cats == ["dead_end", "decision", "decision"]
    tags = sorted(r["content"]["epilogue"]["source_tag"] for r in rows)
    assert tags == ["ai", "user", "user"]
    assert all(r["origin"] == "epilogue" for r in rows)
    # 未 accept 不入账：事实账仍为空
    pkg = project_mod.load_package(mem_root)
    assert pkg["facts"] == []
    # 人工 accept 后经判定落账
    target = next(r for r in rows
                  if r["content"]["epilogue"]["category"] == "dead_end")
    cand.accept(mem_root, target["candidate_id"], by="测试者")
    pkg = project_mod.load_package(mem_root)
    assert len(pkg["facts"]) == 1
    assert pkg["facts"][0]["fact_type"] == "failure_record"


def test_epilogue_apply_gaps_and_drift(tmp_path, mem_root):
    transcript, scan, scan_path = _epilogue_setup(tmp_path, mem_root)
    noms = tmp_path / "noms.json"
    noms.write_text(json.dumps({"items": [
        {"category": "decision", "source_tag": "user",
         "segment_refs": ["seg-999"], "statement": "无锚点的提名",
         "object_id": "method:tracker-threshold"}]}),
        encoding="utf-8")
    res = epilogue.apply_epilogue(mem_root, scan_path, noms)
    assert res["created"] == [] and res["gaps"]
    transcript.write_text(TRANSCRIPT + "\nuser: 又改了主意。\n",
                          encoding="utf-8")
    with pytest.raises(epilogue.EpilogueError):
        epilogue.apply_epilogue(mem_root, scan_path, noms)


# ---------------------------------------------------------------- MM2-02

class _StubLocal:
    name = "local-onnx"
    model = "stub-model-x"
    dim = 4

    def embed(self, text):
        return [0.25, 0.25, 0.25, 0.25]

    embed_query = embed


def test_local_embedder_fallback_is_honest(monkeypatch):
    def boom(model):
        raise RuntimeError("模型不可用")
    monkeypatch.setattr(index_mod, "_local_embedder", boom)
    resolved = index_mod.resolve_embedder(
        {"embedder": {"provider": "local", "model": "any"}})
    assert resolved["effective"] == "deterministic-test"
    assert "回落" in resolved["note"]


def test_local_embedder_effective_matches_actual(mem_root, monkeypatch):
    monkeypatch.setattr(index_mod, "_local_embedder",
                        lambda model: _StubLocal())
    pkg = project_mod.load_package(mem_root)
    pkg["memory"]["embedder"] = {"provider": "local",
                                 "model": "stub-model-x"}
    project_mod.save_memory(mem_root, pkg["memory"])
    state = index_mod.build_index(mem_root)
    assert state["embedder"]["effective"] == "local-onnx"
    assert state["embedder"]["model"] == "stub-model-x"
    status = index_mod.index_status(mem_root)
    assert status["embedder"]["effective"] == "local-onnx"


def test_api_embedder_requires_env_key(monkeypatch):
    reg = {"embedder": {"provider": "api", "model": "embed-x",
                        "endpoint": "https://example.invalid/v1",
                        "api_key_env": "LM_TEST_EMBED_KEY", "dim": 8}}
    monkeypatch.delenv("LM_TEST_EMBED_KEY", raising=False)
    resolved = index_mod.resolve_embedder(reg)
    assert resolved["effective"] == "deterministic-test"
    assert "回落" in resolved["note"]
    monkeypatch.setenv("LM_TEST_EMBED_KEY", "sk-test-not-real")
    resolved = index_mod.resolve_embedder(reg)
    assert resolved["effective"] == "api"
    assert resolved["dim"] == 8


def test_real_local_embedder_smoke(mem_root):
    resolved = index_mod.resolve_embedder(
        {"embedder": {"provider": "local",
                      "model": "BAAI/bge-small-zh-v1.5"}})
    if resolved["effective"] != "local-onnx":
        pytest.skip(f"真实本地嵌入不可用：{resolved['note']}")
    assert resolved["dim"] == 512
    emb = resolved["embedder"]
    near = emb.embed("视频级统计量预测跟踪阈值")
    far = emb.embed("量子纠缠与凝聚态物理")
    q = emb.embed_query("如何预测跟踪器的阈值")
    cos = lambda a, b: sum(x * y for x, y in zip(a, b))
    assert cos(q, near) > cos(q, far)
