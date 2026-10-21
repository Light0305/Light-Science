"""livecli 官方 CLI 适配器：注入式执行器替身验解析与降级（T3）。

夹具来源声明：命令形态与输出样本按官方帮助页 help.obsidian.md/cli
与 kepano/obsidian-skills 的 obsidian-cli 技能（本地克隆，2026-10-21
实读）建模，属自建录制夹具、非实机抓取；用户机器冒烟
（22-user-machine/checklist 第 4 项）后应以真品输出替换并复跑。
VM 内无 Obsidian 活应用，本文件不真跑官方 CLI。
"""

import json
import subprocess

import pytest

from light_memory import livecli, restapi, vaultio
from light_memory.util import sha256_text


class FakeRunner:
    """按 argv 前缀应答的执行器替身，记录全部调用。"""

    def __init__(self, table):
        self.table = table
        self.calls = []

    def __call__(self, argv, timeout):
        self.calls.append(list(argv))
        for prefix, result in self.table:
            if tuple(argv[:len(prefix)]) == tuple(prefix):
                if isinstance(result, Exception):
                    raise result
                return result
        raise AssertionError(f"替身未登记的命令：{argv}")


def _runner_ok():
    return FakeRunner([
        (("obsidian", "version"), (0, "1.12.7\n", "")),
        (("obsidian", "vault=演示", "files"), (0, "128\n", "")),
        (("obsidian", "vault=演示", "create"), (0, "notes/new.md\n", "")),
        (("obsidian", "vault=演示", "search"),
         (0, "a.md\nfolder/b.md\n", "")),
        (("obsidian", "vault=演示", "backlinks"), (0, "a.md\nc.md\n", "")),
        (("obsidian", "vault=演示", "read"), (0, "# 正文\n", "")),
        (("obsidian", "vault=演示", "append"), (0, "", "")),
        (("obsidian", "vault=演示", "property:set"), (0, "", "")),
    ])


# ---------------------------------------------------------------- 探测

def test_probe_unavailable_without_binary(monkeypatch):
    monkeypatch.setattr(livecli, "find_binary", lambda: None)
    probe = livecli.probe_cli()
    assert probe["status"] == "unavailable"
    assert probe["fallback"] == "file-layer"
    assert probe["verified"] is False
    assert "1.12.7" in probe["reason"]


def test_probe_available_with_vault():
    probe = livecli.probe_cli(runner=_runner_ok(), vault="演示")
    assert probe["status"] == "available"
    assert probe["version"] == "1.12.7"
    assert probe["files_total"] == 128
    assert probe["verified"] is False


def test_probe_too_old():
    runner = FakeRunner([
        (("obsidian", "version"), (0, "Obsidian 1.11.0\n", ""))])
    probe = livecli.probe_cli(runner=runner)
    assert probe["status"] == "too-old"
    assert probe["version"] == "1.11.0"
    assert "1.12.7" in probe["reason"]


def test_probe_error_when_app_not_running():
    runner = FakeRunner([
        (("obsidian", "version"),
         (1, "", "Error: Obsidian is not running"))])
    probe = livecli.probe_cli(runner=runner)
    assert probe["status"] == "error"
    assert "退出码 1" in probe["reason"]


def test_probe_error_unparseable_version():
    runner = FakeRunner([
        (("obsidian", "version"), (0, "no version here\n", ""))])
    probe = livecli.probe_cli(runner=runner)
    assert probe["status"] == "error"
    assert "无法解析" in probe["reason"]


def test_probe_timeout_named():
    runner = FakeRunner([
        (("obsidian", "version"),
         subprocess.TimeoutExpired(cmd="obsidian", timeout=15))])
    probe = livecli.probe_cli(runner=runner)
    assert probe["status"] == "error"
    assert "超时" in probe["reason"]


def test_probe_vault_unreachable_named():
    runner = FakeRunner([
        (("obsidian", "version"), (0, "1.12.7\n", "")),
        (("obsidian",), (1, "", "Vault not found"))])
    probe = livecli.probe_cli(runner=runner, vault="不存在")
    assert probe["status"] == "error"
    assert "vault 不可达" in probe["reason"]


# ---------------------------------------------------------------- 操作

def test_create_receipt_hides_content():
    runner = _runner_ok()
    secret_body = "这是一段不应进回执的正文"
    r = livecli.cli_create(runner, "new", content=secret_body,
                           template="模板", vault="演示")
    assert r["created_path"] == "notes/new.md"
    dumped = json.dumps(r, ensure_ascii=False)
    assert secret_body not in dumped
    assert r["receipt"]["params"]["content"]["sha256"] == \
        sha256_text(secret_body)
    assert r["receipt"]["surface"] == "official-cli"
    argv = runner.calls[-1]
    assert argv[1] == "vault=演示" and argv[2] == "create"
    assert "name=new" in argv and "silent" in argv


def test_search_and_backlinks_parse():
    runner = _runner_ok()
    s = livecli.cli_search(runner, "火鸡", vault="演示", limit=5)
    assert s["paths"] == ["a.md", "folder/b.md"]
    assert "limit=5" in runner.calls[-1]
    b = livecli.cli_backlinks(runner, file="b", vault="演示")
    assert b["backlinks"] == ["a.md", "c.md"]


def test_read_and_target_conflict():
    runner = _runner_ok()
    r = livecli.cli_read(runner, file="b", vault="演示")
    assert r["text"] == "# 正文\n"
    with pytest.raises(livecli.LiveCliError):
        livecli.cli_read(runner, file="b", path="x/b.md", vault="演示")


def test_files_total_unparseable():
    runner = FakeRunner([
        (("obsidian", "files"), (0, "many\n", ""))])
    with pytest.raises(livecli.LiveCliError):
        livecli.cli_files_total(runner)


def test_invoke_nonzero_names_exit_code():
    runner = FakeRunner([
        (("obsidian", "read"), (2, "", "boom"))])
    with pytest.raises(livecli.LiveCliError) as exc:
        livecli.cli_read(runner, file="x")
    assert "退出码 2" in exc.value.gaps[0]
    assert "boom" in exc.value.gaps[0]


def test_append_and_property_set_receipts():
    runner = _runner_ok()
    r = livecli.cli_append(runner, "追加行", file="b", vault="演示")
    assert r["receipt"]["command"] == "append"
    r = livecli.cli_property_set(runner, "status", "done",
                                 file="b", vault="演示")
    assert r["receipt"]["params"]["value"] == "done"


# ---------------------------------------------------------------- probe 集成

def test_probe_vault_three_surfaces(tmp_path, monkeypatch):
    monkeypatch.setattr(livecli, "find_binary", lambda: None)
    monkeypatch.delenv(restapi.KEY_ENV, raising=False)
    probe = vaultio.probe_vault(tmp_path / "proj")
    surfaces = probe["live_surfaces"]
    assert surfaces["official-cli"]["status"] == "unavailable"
    assert surfaces["local-rest-api"]["status"] == "disabled"
    assert surfaces["uri"]["status"] == "available"
    assert probe["obsidian_live_verified"] is False
    assert all(s["verified"] is False for s in surfaces.values())
