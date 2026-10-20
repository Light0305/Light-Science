"""CLI 端到端冒烟：init → ingest → verdict → facts → index →
registry → validate → status 全链走通，失败路径 exit 1。"""

import json

from light_memory import cli


def test_cli_end_to_end(tmp_path, idea_source, capsys):
    root = str(tmp_path / "memory")
    assert cli.main(["init", root, "--project", "proj-demo"]) == 0
    assert cli.main(["ingest", root, "--package", "idea",
                     "--source", str(idea_source)]) == 0
    noms = tmp_path / "noms.json"
    noms.write_text(json.dumps([{
        "verdict": "store", "nominator": "cli-test",
        "fact": {"statement": "CLI 落账的事实", "fact_type": "generic",
                 "object_id": "idea_card:idea-alpha_123abc",
                 "valid_at": "2026-10-20"}}]), encoding="utf-8")
    assert cli.main(["verdict", root, "--file", str(noms)]) == 0
    assert cli.main(["facts", root]) == 0
    assert cli.main(["facts", root, "--as-of", "2026-10-20"]) == 0
    assert cli.main(["index", root, "rebuild"]) == 0
    assert cli.main(["index", root, "status"]) == 0
    assert cli.main(["registry", root, "export"]) == 0
    assert cli.main(["validate", root]) == 0
    assert cli.main(["status", root]) == 0
    out = capsys.readouterr().out
    assert "收编完成" in out and "校验通过" in out


def test_cli_failures_exit_1(tmp_path, capsys):
    missing = str(tmp_path / "nope")
    assert cli.main(["validate", missing]) == 1
    assert cli.main(["ingest", missing, "--package", "idea",
                     "--source", str(tmp_path)]) == 1
    root = str(tmp_path / "memory")
    assert cli.main(["init", root]) == 0
    assert cli.main(["init", root]) == 1  # 已存在拒绝覆盖
    assert cli.main(["dispute-resolve", root, "--dispute-id", "DSP-9999",
                     "--outcome", "both_stand", "--by", "测试"]) == 1
