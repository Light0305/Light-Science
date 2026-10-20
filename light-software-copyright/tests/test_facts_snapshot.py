"""事实校验与冻结快照（SC0/SC1）。"""

from __future__ import annotations

import copy

import pytest

from light_copyright import case as case_mod
from light_copyright import snapshot
from conftest import FACTS, drive_to_frozen, run_cli, write_source


def test_validate_facts_names_each_gap():
    facts = {"software": {"full_name": "只有名字"}}
    gaps = case_mod.validate_facts(facts)
    assert len(gaps) >= 8
    assert any("版本号" in g for g in gaps)
    assert any("主要功能" in g for g in gaps)


def test_validate_facts_vocabulary():
    facts = copy.deepcopy(FACTS)
    facts["software"]["kind"] = "mobile"
    gaps = case_mod.validate_facts(facts)
    assert any("kind" in g for g in gaps)


def test_published_without_first_date_is_gap():
    facts = copy.deepcopy(FACTS)
    facts["publication"] = {"status": "published"}
    gaps = case_mod.validate_facts(facts)
    assert any("首次发表日期" in g for g in gaps)


def test_main_function_length_warns_not_blocks():
    facts = copy.deepcopy(FACTS)
    facts["functions"]["main_function"] = "很短。"
    assert case_mod.validate_facts(facts) == []
    warns = case_mod.facts_warnings(facts)
    assert warns and "B 级信号" in warns[0]


def test_freeze_counts_and_languages(tmp_path, case_dir, facts_file):
    src = write_source(tmp_path)
    drive_to_frozen(case_dir, facts_file, src)
    snap = snapshot.load_snapshot(case_dir)
    assert snap["file_count"] == 4  # 含第三方与测试文件（选材阶段才排除）
    assert snap["languages"] == ["Python"]
    assert snap["total_lines"] > 0


def test_snapshot_drift_named(tmp_path, case_dir, facts_file):
    src = write_source(tmp_path)
    drive_to_frozen(case_dir, facts_file, src)
    (src / "app" / "core.py").write_text("# 被改动\n", encoding="utf-8")
    (src / "app" / "new.py").write_text("x = 1\n", encoding="utf-8")
    gaps = snapshot.verify_snapshot(case_dir)
    assert any("漂移" in g and "core.py" in g for g in gaps)
    assert any("新增" in g and "new.py" in g for g in gaps)


def test_freeze_requires_confirmed_facts(tmp_path, case_dir, facts_file):
    src = write_source(tmp_path)
    assert run_cli("init", str(case_dir))[0] == 0
    code, out = run_cli("freeze", str(case_dir), "--source", str(src))
    assert code == 1 and "facts_confirmed" in out


def test_facts_edit_invalidates_confirmation(tmp_path, case_dir, facts_file):
    src = write_source(tmp_path)
    drive_to_frozen(case_dir, facts_file, src)
    facts = case_mod.load_facts(case_dir)
    fp = case_mod.facts_fingerprint(facts)
    assert case_mod.confirmation_valid(case_dir, "facts", "facts", fp)
    facts["software"]["version"] = "V9.9"
    assert not case_mod.confirmation_valid(
        case_dir, "facts", "facts", case_mod.facts_fingerprint(facts))
