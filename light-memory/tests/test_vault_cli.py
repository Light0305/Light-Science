"""vault 命令组 CLI 冒烟：probe/create/fm/links/rename dry-run/canvas/base。"""

import json

from light_memory.cli import main


def _run(capsys, argv):
    rc = main(argv)
    out = capsys.readouterr().out
    return rc, out


def test_vault_cli_end_to_end(tmp_path, capsys):
    root = tmp_path / "proj"
    rc, out = _run(capsys, ["vault", str(root), "probe", "--json"])
    assert rc == 0
    probe = json.loads(out)
    assert probe["obsidian_live_verified"] is False
    assert probe["file_layer"] == "available"

    rc, _ = _run(capsys, ["vault", str(root), "create",
                          "--note", "notes/a.md",
                          "--content", "supports:: [[b]]"])
    assert rc == 0
    rc, _ = _run(capsys, ["vault", str(root), "create",
                          "--note", "b.md", "--content", "# B"])
    assert rc == 0
    rc, out = _run(capsys, ["vault", str(root), "fm", "set",
                            "--note", "b.md", "--key", "stage",
                            "--value", "Design", "--json"])
    assert rc == 0
    rc, out = _run(capsys, ["vault", str(root), "fm", "get",
                            "--note", "b.md", "--key", "stage",
                            "--json"])
    assert json.loads(out)["value"] == "Design"
    rc, out = _run(capsys, ["vault", str(root), "backlinks",
                            "--note", "b.md", "--json"])
    assert json.loads(out)["backlinks"] == ["notes/a.md"]
    # rename 默认 dry-run：文件不动
    rc, out = _run(capsys, ["vault", str(root), "rename",
                            "--from", "b.md", "--to", "b2.md",
                            "--json"])
    plan = json.loads(out)
    assert plan["applied"] is False
    assert (root / "obsidian" / "b.md").exists()
    rc, out = _run(capsys, ["vault", str(root), "rename",
                            "--from", "b.md", "--to", "b2.md",
                            "--apply", "--json"])
    plan = json.loads(out)
    assert plan["applied"] is True and plan["new_unresolved"] == []
    assert (root / "obsidian" / "b2.md").exists()
    # canvas / base 生成并登记
    rc, out = _run(capsys, ["vault", str(root), "canvas", "build",
                            "--out", "graph.canvas", "--json"])
    assert rc == 0 and json.loads(out)["nodes"] == 2
    spec = tmp_path / "spec.yaml"
    spec.write_text(
        'filters:\n  and:\n    - file.hasProperty("stage")\n'
        "views:\n  - type: table\n    name: 视图\n",
        encoding="utf-8")
    rc, out = _run(capsys, ["vault", str(root), "base", "build",
                            "--from", str(spec), "--out", "view.base",
                            "--json"])
    assert rc == 0
    rc, out = _run(capsys, ["vault", str(root), "base", "eval",
                            "--file", "view.base", "--json"])
    r = json.loads(out)
    assert r["label"] == "offline-eval"
    assert r["matched"] == ["b2.md"]
    rc, out = _run(capsys, ["vault", str(root), "daily", "--json"])
    assert rc == 0 and json.loads(out)["created"] is True


def test_vault_cli_refusals_surface_as_errors(tmp_path, capsys):
    root = tmp_path / "proj"
    rc, _ = _run(capsys, ["vault", str(root), "create",
                          "--note", "x.md", "--content", "正文"])
    assert rc == 0
    rc = main(["vault", str(root), "create", "--note", "x.md",
               "--content", "重复"])
    capsys.readouterr()
    assert rc == 1
    rc = main(["vault", str(root), "patch", "--note", "x.md",
               "--heading", "不存在", "--text", "y"])
    capsys.readouterr()
    assert rc == 1
