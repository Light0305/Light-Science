"""项目骨架与 CLI 基本流。"""

import pytest
from conftest import full_card
from light_idea.cli import main
from light_idea.project import (
    init_project,
    list_cards,
    load_card,
    new_card,
    save_card,
)
from light_idea.util import make_idea_id, read_yaml


def test_make_idea_id_format():
    iid = make_idea_id("Self-supervised pretraining for tomato leaf disease")
    assert iid.startswith("self-supervised-pretraining-for-tomato-l_")
    assert len(iid.rsplit("_", 1)[1]) == 6


def test_init_creates_structure(tmp_path):
    root = tmp_path / "proj"
    init_project(root, "番茄病害检测")
    for rel in ("project.yaml", "index.yaml", "index.md",
                "idea-stage/IDEA_REPORT.md", "idea-stage/candidates.md",
                "idea-stage/research_contract.md", "novelty/.gitkeep"):
        assert (root / rel).exists(), rel
    assert (root / "cards").is_dir()


def test_init_refuses_overwrite(tmp_path):
    root = tmp_path / "proj"
    init_project(root, "方向A")
    with pytest.raises(FileExistsError):
        init_project(root, "方向A")


def test_new_card_roundtrip(tmp_path):
    root = tmp_path / "proj"
    init_project(root, "方向A")
    card = new_card(root, "Idea One", "一句话", "manual",
                    provenance_note="用户自带")
    d = root / "cards" / card["idea_id"]
    assert (d / "idea.yaml").exists()
    assert (d / "card.md").exists()
    loaded = load_card(root, card["idea_id"])
    assert loaded["status"] == "draft"
    assert loaded["provenance"]["note"] == "用户自带"
    idx = read_yaml(root / "index.yaml")
    assert idx["total"] == 1


def test_new_duplicate_title_rejected(tmp_path):
    root = tmp_path / "proj"
    init_project(root, "方向A")
    new_card(root, "Idea One", "一句话", "manual")
    with pytest.raises(FileExistsError):
        new_card(root, "Idea One", "另一句", "manual")


def test_save_and_render_marks_conceptual(tmp_path):
    root = tmp_path / "proj"
    init_project(root, "方向A")
    card = full_card("finalized_conceptual")
    card["finalization_level"] = "conceptual"
    save_card(root, card)
    md = (root / "cards" / card["idea_id"] / "card.md").read_text(encoding="utf-8")
    assert "概念定版" in md and "不得直接开工" in md
    assert "未经试点验证" in md  # pilot=not_run 时定版卡必须带此标注（拍板 9.6-B）
    assert "辅助字段区" in md and "查新证据区" in md  # 两区物理分离排版


def test_cli_flow(tmp_path, capsys):
    root = str(tmp_path / "proj")
    assert main(["init", root, "--direction", "方向A"]) == 0
    assert main(["new", root, "--title", "Idea One", "--one-liner", "一句话",
                 "--operator", "manual", "--provenance", "用户自带"]) == 0
    iid = make_idea_id("Idea One")
    assert main(["list", root]) == 0
    out = capsys.readouterr().out
    assert iid in out
    # 空卡骨架未填 → validate 应报不合法（exit 1），且逐条列出
    assert main(["validate", root, iid]) == 1
    assert list_cards(tmp_path / "proj")


def test_cli_advance_blocked_prints_reasons(tmp_path, capsys):
    root = str(tmp_path / "proj")
    main(["init", root, "--direction", "方向A"])
    main(["new", root, "--title", "Idea One", "--one-liner", "一句话"])
    iid = make_idea_id("Idea One")
    rc = main(["advance", root, iid, "--to", "finalized_executable"])
    assert rc == 1
    out = capsys.readouterr().out
    assert "推进被拦" in out and "不许跳级" in out
