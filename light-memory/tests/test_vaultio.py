"""vaultio：行级 frontmatter 补丁保真、区分隔、留痕删除、日记。"""

from datetime import date

import pytest

from light_memory import bench, obsidian as obs
from light_memory import vaultio

NOTE = """---
title: 实验笔记
valid_from: 2026-10-01
# 注释行不许漂移
tags:
  - stage/Design
  - status/current
memo: "quoted: value"
count: 3 # 行内计数
---
# 标题

## 观察
旧观察一行。

## 方法
方法正文。
"""


@pytest.fixture()
def vault(tmp_path):
    v = tmp_path / "vault"
    v.mkdir()
    (v / "note.md").write_text(NOTE, encoding="utf-8")
    return v


def test_fm_set_new_key_preserves_all_other_lines(vault):
    text = (vault / "note.md").read_text(encoding="utf-8")
    new = vaultio.fm_set_in_text(text, "reviewer", "张三")
    old_lines = text.split("\n")
    new_lines = new.split("\n")
    # 原每一行在新文本中逐字存在（只多一行新键）
    for line in old_lines:
        assert line in new_lines
    assert "reviewer: 张三" in new_lines
    assert len(new_lines) == len(old_lines) + 1
    # 日期行与注释行逐字未动（P7 教训：日期不许被加引号）
    assert "valid_from: 2026-10-01" in new_lines
    assert "# 注释行不许漂移" in new_lines


def test_fm_set_scalar_replaces_only_its_line(vault):
    text = (vault / "note.md").read_text(encoding="utf-8")
    new = vaultio.fm_set_in_text(text, "title", "新标题")
    old_lines, new_lines = text.split("\n"), new.split("\n")
    assert len(old_lines) == len(new_lines)
    diff = [i for i, (a, b) in enumerate(zip(old_lines, new_lines))
            if a != b]
    assert diff == [1]
    assert new_lines[1] == "title: 新标题"


def test_fm_set_date_value_stays_unquoted(vault):
    text = (vault / "note.md").read_text(encoding="utf-8")
    new = vaultio.fm_set_in_text(text, "valid_from",
                                 date(2026, 11, 2))
    assert "valid_from: 2026-11-02" in new.split("\n")
    assert 'valid_from: "2026-11-02"' not in new


def test_fm_set_inline_comment_preserved(vault):
    text = (vault / "note.md").read_text(encoding="utf-8")
    new = vaultio.fm_set_in_text(text, "count", 4)
    assert "count: 4  # 行内计数" in new.split("\n")


def test_fm_set_block_list_replaced_as_block(vault):
    text = (vault / "note.md").read_text(encoding="utf-8")
    new = vaultio.fm_set_in_text(text, "tags", ["a/b", "c"])
    lines = new.split("\n")
    i = lines.index("tags:")
    assert lines[i + 1:i + 3] == ["  - a/b", "  - c"]
    assert "stage/Design" not in new
    # 块列表之后的键未受影响
    assert 'memo: "quoted: value"' in lines


def test_fm_set_creates_frontmatter_when_absent(vault):
    new = vaultio.fm_set_in_text("# 裸笔记\n正文\n", "stage", "Design")
    assert new.startswith("---\nstage: Design\n---\n# 裸笔记")


def test_fm_get_values(vault):
    text = (vault / "note.md").read_text(encoding="utf-8")
    found, value = vaultio.fm_get(text, "valid_from")
    assert found and str(value) == "2026-10-01"
    found, value = vaultio.fm_get(text, "tags")
    assert found and value == ["stage/Design", "status/current"]
    found, _ = vaultio.fm_get(text, "不存在")
    assert not found


def test_fm_set_nested_mapping_refused(tmp_path):
    v = tmp_path / "vault"
    v.mkdir()
    p = v / "n.md"
    p.write_text("---\nnested:\n  a: 1\n---\n正文\n",
                 encoding="utf-8")
    with pytest.raises(vaultio.VaultError):
        vaultio.fm_set_note(v, "n.md", "nested", {"a": 2})


def test_create_append_patch_delete(vault):
    r = vaultio.create_note(vault, "sub/new.md", content="第一段。")
    assert r["created"]
    with pytest.raises(vaultio.VaultError):
        vaultio.create_note(vault, "sub/new.md", content="x")
    vaultio.append_note(vault, "sub/new.md", "第二段。")
    text = vaultio.read_note(vault, "sub/new.md")
    assert text == "第一段。\n第二段。\n"
    vaultio.patch_section(vault, "note.md", "观察", "新观察正文。")
    new = vaultio.read_note(vault, "note.md")
    assert "新观察正文。" in new and "旧观察一行" not in new
    assert "方法正文。" in new  # 兄弟段逐字未动
    vaultio.patch_section(vault, "note.md", "标题/方法", "改后方法。",
                          mode="replace")
    assert "改后方法。" in vaultio.read_note(vault, "note.md")
    with pytest.raises(vaultio.VaultError):
        vaultio.patch_section(vault, "note.md", "不存在的段", "x")
    r = vaultio.delete_note(vault, "sub/new.md")
    assert not (vault / "sub/new.md").exists()
    assert (vault / ".trash" / "sub/new.md").exists()
    assert r["sha256"]
    log = (vault / ".trash" / "trash-log.jsonl").read_text(
        encoding="utf-8")
    assert "sub/new.md" in log


def test_create_with_template(vault):
    vaultio.create_note(vault, "tpl.md",
                        content="# {{title}}\n日期 {{date}}\n")
    r = vaultio.create_note(vault, "from-tpl.md", template="tpl.md")
    text = vaultio.read_note(vault, "from-tpl.md")
    assert "# from-tpl" in text and "{{title}}" not in text
    assert r["after_hash"]


# ------------------------------------------------------------ 投影笔记纪律

@pytest.fixture()
def world(tmp_path):
    base = tmp_path / "world"
    bench.build_mini_world(base)
    obs.project_obsidian(base / "proj-a")
    return base / "proj-a" / "obsidian"


def test_projected_note_machine_key_refused(world):
    with pytest.raises(vaultio.VaultError):
        vaultio.fm_set_note(world, "claim-c1.md", "memory_id", "X")
    with pytest.raises(vaultio.VaultError):
        vaultio.fm_set_note(world, "claim-c1.md", "status",
                            "archived")
    # 白名单之外的普通键可写，且机器区逐字不动
    before = vaultio.read_note(world, "claim-c1.md")
    machine_before = before.split(obs.MACHINE_START)[1] \
        .split(obs.MACHINE_END)[0]
    vaultio.fm_set_note(world, "claim-c1.md", "my_flag", "yes")
    after = vaultio.read_note(world, "claim-c1.md")
    machine_after = after.split(obs.MACHINE_START)[1] \
        .split(obs.MACHINE_END)[0]
    assert machine_before == machine_after
    # 字符串 yes 须引号保型（YAML 1.1 会把裸 yes 读成布尔）
    assert 'my_flag: "yes"' in after


def test_projected_note_machine_zone_patch_refused(world):
    with pytest.raises(vaultio.VaultError):
        vaultio.patch_section(world, "claim-c1.md", "观察", "篡改")


def test_projected_note_append_lands_in_annotation_zone(world):
    vaultio.append_note(world, "claim-c1.md", "人工补记一行")
    text = vaultio.read_note(world, "claim-c1.md")
    assert "人工补记一行" in obs.extract_annotations(text)


# ------------------------------------------------------------ 状态与日记

def test_live_verified_default_false_and_register_gate(vault):
    probe = vaultio.probe_vault(vault)
    assert probe["obsidian_live_verified"] is False
    with pytest.raises(vaultio.VaultError):
        vaultio.register_live_smoke(vault, {"surface": "official-cli"})
    state = vaultio.register_live_smoke(vault, {
        "surface": "official-cli", "app_version": "1.12.7",
        "suite": "consistency-v1", "by": "user-machine"})
    assert state["obsidian_live_verified"] is True
    assert vaultio.probe_vault(vault)["obsidian_live_verified"]


def test_daily_defaults_and_config(tmp_path):
    v = tmp_path / "vault"
    v.mkdir()
    r = vaultio.daily_note(v, on=date(2026, 10, 21))
    assert r["path"] == "2026-10-21.md" and r["created"]
    assert r["config_source"] == "default"
    r2 = vaultio.daily_note(v, on=date(2026, 10, 21))
    assert r2["created"] is False
    (v / ".obsidian").mkdir()
    (v / ".obsidian" / "daily-notes.json").write_text(
        '{"folder": "日记", "format": "YYYY/MM/YYYY-MM-DD"}',
        encoding="utf-8")
    r3 = vaultio.daily_note(v, on=date(2026, 10, 22))
    assert r3["path"] == "日记/2026/10/2026-10-22.md"
    assert r3["config_source"] == "config"


def test_search_content_and_field(vault):
    hits = vaultio.search_vault(vault, "方法正文")
    assert hits["count"] == 1 and hits["hits"][0]["path"] == "note.md"
    hits = vaultio.search_vault(vault, "Design", field="tags")
    assert hits["count"] == 1
    hits = vaultio.search_vault(vault, "Design", field="title")
    assert hits["count"] == 0
