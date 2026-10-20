"""测试夹具：迷你自造软件 + 全链驱动辅助。"""

from __future__ import annotations

import io
from contextlib import redirect_stdout
from pathlib import Path

import pytest
import yaml

from light_copyright.cli import main as cli_main


def run_cli(*argv):
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = cli_main(list(argv))
    return code, buf.getvalue()


FACTS = {
    "software": {"full_name": "迷你测试软件", "short_name": "迷你",
                 "version": "V2.0", "kind": "headless", "category": "工具软件"},
    "owner": {"name": "测试著作权人", "type": "自然人"},
    "development": {"mode": "independent", "completion_date": "2026-08-01",
                    "original": True},
    "publication": {"status": "unpublished"},
    "rights": {"acquisition": "原始取得", "scope": "全部权利"},
    "functions": {"main_function": "迷你测试软件用于测试。" * 40},
    "environment": {"dev_os": "Ubuntu 24.04", "dev_tools": "Python 3.12"},
}


def write_source(base: Path) -> Path:
    """迷你软件：两个正式模块 + 一个第三方头文件 + 一个测试文件。"""
    src = base / "src"
    (src / "app").mkdir(parents=True)
    (src / "tests").mkdir()
    (src / "app" / "core.py").write_text(
        '"""核心计算：数值清洗与求和。"""\n\n\n'
        "def clean(values):\n"
        '    """剔除空值并转浮点。"""\n'
        "    return [float(v) for v in values if v is not None]\n\n\n"
        "def total(values):\n"
        '    """对清洗后的序列求和。"""\n'
        "    return sum(clean(values))\n",
        encoding="utf-8")
    (src / "app" / "main.py").write_text(
        '"""入口：读参数、计算、打印。"""\n\n'
        "from .core import total\n\n\n"
        "def main(argv):\n"
        '    """打印参数序列之和。"""\n'
        "    print(total(argv))\n    return 0\n",
        encoding="utf-8")
    (src / "app" / "borrowed.py").write_text(
        "# Copyright (c) 2020 某第三方作者\n"
        "# Licensed under the MIT License\n\n"
        "def helper():\n    return 42\n",
        encoding="utf-8")
    (src / "tests" / "test_core.py").write_text(
        "def test_total():\n    assert True\n", encoding="utf-8")
    return src


@pytest.fixture()
def case_dir(tmp_path):
    return tmp_path / "case"


@pytest.fixture()
def facts_file(tmp_path):
    p = tmp_path / "facts.yaml"
    p.write_text(yaml.safe_dump(FACTS, allow_unicode=True), encoding="utf-8")
    return p


def drive_to_frozen(case_dir, facts_file, source):
    assert run_cli("init", str(case_dir))[0] == 0
    assert run_cli("set-facts", str(case_dir), "--from", str(facts_file))[0] == 0
    assert run_cli("confirm-facts", str(case_dir))[0] == 0
    assert run_cli("freeze", str(case_dir), "--source", str(source))[0] == 0


def drive_to_materials(case_dir, facts_file, source):
    drive_to_frozen(case_dir, facts_file, source)
    assert run_cli("select", str(case_dir))[0] == 0
    assert run_cli("confirm-selection", str(case_dir))[0] == 0
    assert run_cli("render-code", str(case_dir))[0] == 0
    assert run_cli("draft-doc", str(case_dir))[0] == 0


def drive_to_confirmed(case_dir, facts_file, source):
    drive_to_materials(case_dir, facts_file, source)
    from light_copyright import render
    man = render.load_segments(case_dir)
    for seg in man["segments"]:
        code, _ = run_cli("confirm-segment", str(case_dir),
                          "--seg", seg["seg_id"])
        assert code == 0
    assert run_cli("render-doc", str(case_dir))[0] == 0


def drive_to_packaged(case_dir, facts_file, source, tmp_path):
    drive_to_confirmed(case_dir, facts_file, source)
    decl = tmp_path / "decl.txt"
    decl.write_text("用户自备的当期声明原文（测试占位，内容由用户取得）。",
                    encoding="utf-8")
    assert run_cli("declaration", str(case_dir), "record", "--file",
                   str(decl), "--origin", "测试：用户自备文件")[0] == 0
    assert run_cli("declaration", str(case_dir), "verify")[0] == 0
    assert run_cli("check", str(case_dir))[0] == 0
    assert run_cli("package", str(case_dir))[0] == 0
