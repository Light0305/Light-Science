from light_leader import cli

from conftest import (make_idea, make_literature, make_manuscript,
                      make_memory)


def test_cli_full_chain(tmp_path, capsys):
    proj = tmp_path / "proj"
    assert cli.main(["init", str(proj), "--name", "demo",
                     "--title", "演示项目"]) == 0
    make_literature(proj)
    make_idea(proj, status="pre_mortem_passed",
              review_status="REVIEW_UNAVAILABLE")
    make_memory(proj, with_view=True, n_objects=2)
    assert cli.main(["status", str(proj)]) == 0
    out = capsys.readouterr().out
    assert "pre_mortem_passed" in out
    assert "REVIEW_UNAVAILABLE" in out
    assert cli.main(["route", str(proj)]) == 0
    out = capsys.readouterr().out
    assert "[硬门]" in out and "idea" in out
    assert cli.main(["registry", str(proj)]) == 0
    out = capsys.readouterr().out
    assert "[paper] 2 个" in out


def test_cli_status_missing_project_fails(tmp_path):
    assert cli.main(["status", str(tmp_path / "nope")]) == 1


def test_cli_registry_missing_view_fails(tmp_path, capsys):
    assert cli.main(["registry", str(tmp_path)]) == 1
    assert "未找到 registry-view.json" in capsys.readouterr().out


def test_cli_init_refuses_existing(tmp_path):
    proj = tmp_path / "proj"
    assert cli.main(["init", str(proj)]) == 0
    assert cli.main(["init", str(proj)]) == 1
