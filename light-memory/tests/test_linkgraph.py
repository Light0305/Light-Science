"""linkgraph：四表金标、改名重写一致性（别名/标题/字段/canvas/base）。"""

import json

import pytest

from light_memory import linkgraph, vaultio


@pytest.fixture()
def vault(tmp_path):
    v = tmp_path / "vault"
    (v / "notes").mkdir(parents=True)
    (v / "sub").mkdir()
    (v / "other").mkdir()
    (v / "notes" / "obj-a.md").write_text(
        "---\nmemory_id: OBJ-A\n---\n"
        "supports:: [[obj-b]]\n"
        "见 [[obj-b|别名B]] 与 [[obj-c#小节]]、块 [[obj-c#^blk1]]、"
        "图 ![[img-note]]、缺 [[missing-note]]。\n"
        "```\n[[code-link]]\n```\n",
        encoding="utf-8")
    (v / "notes" / "obj-b.md").write_text(
        "# B\n回链 [[obj-a]]。\n", encoding="utf-8")
    (v / "notes" / "obj-c.md").write_text(
        "# C\n\n## 小节\n正文 ^blk1\n", encoding="utf-8")
    (v / "img-note.md").write_text("# 图\n", encoding="utf-8")
    (v / "sub" / "obj-d.md").write_text("# D1\n", encoding="utf-8")
    (v / "other" / "obj-d.md").write_text("# D2\n", encoding="utf-8")
    (v / "linker.md").write_text("含糊短链 [[obj-d]]。\n",
                                  encoding="utf-8")
    (v / "lonely.md").write_text("# 孤儿\n无链。\n", encoding="utf-8")
    return v


def test_graph_four_tables(vault):
    g = linkgraph.build_graph(vault)
    a = "notes/obj-a.md"
    assert g["outlinks"][a] == ["img-note.md", "notes/obj-b.md",
                                "notes/obj-c.md"]
    assert g["backlinks"]["notes/obj-b.md"] == [a]
    kinds = {(e["target"], e["kind"]) for e in g["edges"]
             if e["from"] == a}
    assert ("obj-b", "inline_field") in kinds
    assert ("obj-b", "wikilink") in kinds
    assert ("img-note", "embed") in kinds
    # 代码围栏内的链接不算边
    assert all(e["target"] != "code-link" for e in g["edges"])
    un = {(u["target_raw"], u["reason"]) for u in g["unresolved"]}
    assert ("missing-note", "missing") in un
    amb = [u for u in g["unresolved"] if u["target_raw"] == "obj-d"]
    assert amb and amb[0]["reason"] == "ambiguous"
    assert sorted(amb[0]["candidates"]) == ["other/obj-d.md",
                                            "sub/obj-d.md"]
    # 孤儿口径：无任何已解出/入边（linker 只有一条含糊未解链，
    # 未接进任何真实笔记，同列孤儿，未解另表登记）
    assert g["orphans"] == ["linker.md", "lonely.md",
                            "other/obj-d.md", "sub/obj-d.md"]


def test_rename_dry_run_reports_without_touching(vault):
    before = (vault / "notes" / "obj-a.md").read_text(encoding="utf-8")
    plan = linkgraph.rename_note(vault, "notes/obj-b.md",
                                 "notes/obj-b2.md")
    assert plan["applied"] is False
    reps = [c for c in plan["note_changes"]
            if c["file"] == "notes/obj-a.md"]
    assert reps and len(reps[0]["replacements"]) == 2
    news = {r["new"] for r in reps[0]["replacements"]}
    assert news == {"obj-b2", "obj-b2|别名B"}
    assert (vault / "notes" / "obj-a.md").read_text(
        encoding="utf-8") == before
    assert (vault / "notes" / "obj-b.md").exists()


def test_rename_apply_rewrites_all_forms(vault):
    canvas = {
        "nodes": [
            {"id": "n1", "type": "file", "file": "notes/obj-b.md",
             "x": 0, "y": 0, "width": 250, "height": 120},
            {"id": "n2", "type": "text", "text": "参考 [[obj-b]]",
             "x": 300, "y": 0, "width": 250, "height": 120},
        ],
        "edges": [{"id": "e1", "fromNode": "n1", "toNode": "n2",
                   "label": "supports"}],
    }
    (vault / "graph.canvas").write_text(
        json.dumps(canvas, ensure_ascii=False), encoding="utf-8")
    (vault / "view.base").write_text(
        'filters:\n  and:\n    - file.hasProperty("memory_id")\n'
        '    - source_note == "notes/obj-b"\n'
        "views:\n  - type: table\n    name: 全部\n",
        encoding="utf-8")
    before = linkgraph.build_graph(vault)
    plan = linkgraph.rename_note(vault, "notes/obj-b.md",
                                 "notes/obj-b2.md", apply=True)
    assert plan["applied"] is True
    assert plan["new_unresolved"] == []
    assert not (vault / "notes" / "obj-b.md").exists()
    assert (vault / "notes" / "obj-b2.md").exists()
    a = (vault / "notes" / "obj-a.md").read_text(encoding="utf-8")
    assert "supports:: [[obj-b2]]" in a
    assert "[[obj-b2|别名B]]" in a
    data = json.loads((vault / "graph.canvas").read_text(
        encoding="utf-8"))
    assert data["nodes"][0]["file"] == "notes/obj-b2.md"
    assert "[[obj-b2]]" in data["nodes"][1]["text"]
    base = (vault / "view.base").read_text(encoding="utf-8")
    assert '"notes/obj-b2"' in base
    after = linkgraph.build_graph(vault)
    assert {(u["from"], u["target_raw"]) for u in after["unresolved"]} \
        == {(u["from"], u["target_raw"])
            for u in before["unresolved"]}


def test_rename_short_link_upgrades_to_path_on_clash(tmp_path):
    v = tmp_path / "vault"
    (v / "sub").mkdir(parents=True)
    (v / "free.md").write_text("# 自由\n", encoding="utf-8")
    (v / "target.md").write_text("# 已有 target\n", encoding="utf-8")
    (v / "use.md").write_text("链 [[free]]。\n", encoding="utf-8")
    plan = linkgraph.rename_note(v, "free.md", "sub/target.md",
                                 apply=True)
    use = (v / "use.md").read_text(encoding="utf-8")
    assert "[[sub/target]]" in use
    assert plan["new_unresolved"] == []


def test_rename_projected_note_refused(tmp_path):
    from light_memory import bench, obsidian as obs
    base = tmp_path / "world"
    bench.build_mini_world(base)
    obs.project_obsidian(base / "proj-a")
    v = base / "proj-a" / "obsidian"
    with pytest.raises(linkgraph.LinkGraphError):
        linkgraph.rename_note(v, "claim-c1.md", "claim-x.md",
                              apply=True)


def test_rename_missing_and_clash_refused(vault):
    with pytest.raises(linkgraph.LinkGraphError):
        linkgraph.rename_note(vault, "nope.md", "x.md")
    with pytest.raises(linkgraph.LinkGraphError):
        linkgraph.rename_note(vault, "lonely.md", "img-note.md")
