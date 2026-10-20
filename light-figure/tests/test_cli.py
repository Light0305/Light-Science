"""CLI 冒烟：init → intake → validate → advance → report 全链 JSON 输出。"""

import json

from light_figure.cli import main
from conftest import make_ai_policy, make_journal_contract, make_standalone


def _run(capsys, argv):
    rc = main(argv)
    out = json.loads(capsys.readouterr().out)
    return rc, out


def test_cli_full_chain(tmp_path, capsys):
    from light_figure.util import dump_yaml

    root = tmp_path / "figs"
    rc, out = _run(capsys, ["init", str(root), "--title", "CLI Demo"])
    assert rc == 0 and out["status"] == "intake"

    standalone = tmp_path / "s.yaml"
    dump_yaml(standalone, make_standalone())
    journal = tmp_path / "j.yaml"
    dump_yaml(journal, make_journal_contract())
    policy = tmp_path / "p.yaml"
    dump_yaml(policy, make_ai_policy())
    rc, out = _run(capsys, [
        "intake", str(root), "--standalone", str(standalone),
        "--journal-contract", str(journal), "--ai-policy", str(policy)])
    assert rc == 0 and out["figures"] == ["fig-data", "fig-method"]

    rc, out = _run(capsys, ["validate", str(root)])
    assert rc == 1 and out["ok"] is False  # 骨架合同未补齐，如实报错

    rc, out = _run(capsys, ["advance", str(root)])
    assert rc == 1 and out["advanced"] is False and out["gaps"]

    rc, out = _run(capsys, ["report", str(root)])
    assert rc == 0 and out["figures"] == 2

    rc, out = _run(capsys, ["status", str(root)])
    assert rc == 0 and out["status"] == "intake"
