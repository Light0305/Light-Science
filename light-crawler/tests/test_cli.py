"""CLI 全链冒烟：init → register → precheck → fetch → validate → refusals。"""

import json

import yaml
from conftest import make_reg

from light_crawler import cli


def _write_reg(tmp_path, reg):
    path = tmp_path / "reg.yaml"
    path.write_text(yaml.safe_dump(reg, allow_unicode=True), encoding="utf-8")
    return str(path)


def test_cli_full_chain(tmp_path, site, capsys):
    _, base = site
    root = str(tmp_path / "data-sources")
    assert cli.main(["--root", root, "init", "--project", "p"]) == 0
    regfile = _write_reg(tmp_path, make_reg(base, channel="web_page"))
    assert cli.main(["--root", root, "register", "--file", regfile]) == 0
    assert cli.main(["--root", root, "precheck", "--target", "t1"]) == 0
    # 高危通道未确认前 fetch 被 guard 拒绝（退出码 2）
    assert cli.main(["--root", root, "fetch", "--target", "t1"]) == 2
    assert cli.main(["--root", root, "confirm", "--target", "t1",
                     "--by", "张三", "--note", "条款核对完毕"]) == 0
    capsys.readouterr()  # 排空此前输出，gate-check 的 JSON 单独取
    assert cli.main(["--root", root, "gate-check", "--target", "t1",
                     "--json"]) == 0
    out = capsys.readouterr().out
    verdict = json.loads(out)
    assert verdict["ready"] is True
    assert cli.main(["--root", root, "fetch", "--target", "t1",
                     "--url", base + "/data.json"]) == 0
    assert cli.main(["--root", root, "validate"]) == 0
    assert cli.main(["--root", root, "status"]) == 0
    assert cli.main(["--root", root, "targets"]) == 0
    assert cli.main(["--root", root, "render"]) == 0
    assert cli.main(["--root", root, "refusals"]) == 0
    out = capsys.readouterr().out
    assert "fetch_refused" in out  # 未确认时那次拒绝留了痕


def test_cli_register_rejects_login_state(tmp_path, site):
    _, base = site
    root = str(tmp_path / "data-sources")
    assert cli.main(["--root", root, "init", "--project", "p"]) == 0
    regfile = _write_reg(tmp_path, make_reg(base, login_state="cookie"))
    assert cli.main(["--root", root, "register", "--file", regfile]) == 2


def test_cli_gate_check_blocked_exit_code(tmp_path, site):
    srv, base = site
    srv.robots_status = 500  # 失败关闭：预检 blocked
    root = str(tmp_path / "data-sources")
    assert cli.main(["--root", root, "init", "--project", "p"]) == 0
    regfile = _write_reg(tmp_path, make_reg(base))
    assert cli.main(["--root", root, "register", "--file", regfile]) == 0
    assert cli.main(["--root", root, "precheck", "--target", "t1"]) == 2
    assert cli.main(["--root", root, "gate-check", "--target", "t1"]) == 2
