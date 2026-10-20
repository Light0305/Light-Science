"""Obsidian 投影：单向生成、标注区不动、回读只产候选、摘要门控。"""

import pytest

from light_memory import bench, candidates as cand
from light_memory import obsidian as obs
from light_memory import project as project_mod


@pytest.fixture()
def world(tmp_path):
    base = tmp_path / "world"
    bench.build_mini_world(base)
    return base


def _vault(world):
    return world / "proj-a" / "obsidian"


def test_projection_creates_selected_notes_and_index(world):
    a = world / "proj-a"
    report = obs.project_obsidian(a)
    vault = _vault(world)
    assert report["selected"] >= 4
    claim = (vault / "claim-c1.md").read_text(encoding="utf-8")
    # 当前与被取代的结论两代都入选（取代关系正是图谱的看点）
    assert "3.10" in claim and "5.25" in claim
    assert "superseded" in claim
    assert (vault / "index.md").exists()
    assert (vault / "relations-guide.md").exists()
    # 跨对象关系以 wikilink 落边，双向可达
    idea = (vault / "idea-card-idea-alpha-123abc.md").read_text(
        encoding="utf-8")
    assert "[[claim-c1]]" in idea
    assert "[[idea-card-idea-alpha-123abc]]" in claim


def test_reprojection_touches_machine_zone_only(world):
    a = world / "proj-a"
    obs.project_obsidian(a)
    note = _vault(world) / "claim-c1.md"
    text = note.read_text(encoding="utf-8")
    text = text.replace(obs.ANNO_PLACEHOLDER, "投稿时要带限定语")
    text = text.replace("3.10", "9.99")  # 篡改机器区
    note.write_text(text, encoding="utf-8")
    obs.project_obsidian(a, full=True)
    healed = note.read_text(encoding="utf-8")
    assert "9.99" not in healed and "3.10" in healed  # 机器区已修复
    assert "投稿时要带限定语" in healed  # 标注区原文保留


def test_source_unchanged_skips_rewrite(world):
    a = world / "proj-a"
    obs.project_obsidian(a)
    report = obs.project_obsidian(a)
    assert report["written"] == []
    assert report["unchanged"]  # 摘要门控：源未变不重写


def test_readback_produces_candidates_only(world):
    a = world / "proj-a"
    obs.project_obsidian(a)
    note = _vault(world) / "claim-c1.md"
    note.write_text(
        note.read_text(encoding="utf-8").replace(
            obs.ANNO_PLACEHOLDER, "这条结论需要补限定语"),
        encoding="utf-8")
    facts_before = len(project_mod.load_package(a)["facts"])
    events_before = len(project_mod.load_package(a)["events"])
    report = obs.readback(a)
    assert report["count"] == 1
    row = cand.get_candidate(a, report["created"][0])
    assert row["kind"] == "annotation"
    assert row["origin"] == "annotation_readback"
    assert row["status"] == "pending"
    # 只产候选：事实与事件账未被回读直接改动
    pkg = project_mod.load_package(a)
    assert len(pkg["facts"]) == facts_before
    assert not any(e["type"] == "annotation" for e in pkg["events"])
    assert len(pkg["events"]) >= events_before  # 仅候选提名事件
    # 水位已记：重复回读不重复提名
    assert obs.readback(a)["count"] == 0
    # 标注原文仍留在视图内（复制不是剪切）
    assert "这条结论需要补限定语" in note.read_text(encoding="utf-8")


def test_vault_is_projection_not_only_copy(world):
    import shutil
    a = world / "proj-a"
    obs.project_obsidian(a)
    shutil.rmtree(_vault(world))  # 整册删掉可从记录重建（MM-27）
    report = obs.project_obsidian(a)
    assert report["written"]
    assert (_vault(world) / "claim-c1.md").exists()
