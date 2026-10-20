"""风险门：分级硬度、名单注入、放行留痕、excluded 只增（E3 / JS-02）。"""

from __future__ import annotations

import pytest

from light_journal_select.gate import (
    apply_gate, checks_from_name_list, evaluate_level, load_name_list,
    valid_override,
)
from light_journal_select.project import load_selection

CEA = "Computers and Electronics in Agriculture"
ANIMALS = "Animals"
POULTRY = "Poultry Science"

NAME_LIST_CSV = """name,issn,condition,source,version
Animals,,predatory_list_hit,stop-predatory-journals,2026-01
Poultry Science,,warning_list_hit,cas-warning-list,2025
"""


def _check(condition, hit=True, source="official-page"):
    return {"condition": condition, "hit": hit, "source": source,
            "source_ref": "checked 2026-10-20", "checked_at": "2026-10-20",
            "note": None}


def _clear_checks():
    return [_check("warning_list_hit", hit=False),
            _check("predatory_list_hit", hit=False)]


def test_evaluate_level_precedence():
    assert evaluate_level([_check("apc_opaque"),
                           _check("warning_list_hit")]) == "hard_exclude"
    assert evaluate_level([_check("apc_opaque"),
                           _check("domain_mismatch")]) == "quasi_hard"
    assert evaluate_level([_check("esci_only")]) == "soft_warn"
    assert evaluate_level([_check("esci_only", hit=False)]) == "clear"
    assert evaluate_level([]) == "clear"


def test_override_field_discipline():
    ok, _ = valid_override({"confirmed_by": "用户",
                             "confirmation_text": "知情，仍投",
                             "date": "2026-10-20"})
    assert ok
    ok, gaps = valid_override({"confirmed_by": "用户", "date": "2026-10-20"})
    assert not ok and gaps  # 缺确认文本不许放行


def test_name_list_matching(tmp_path):
    path = tmp_path / "list.csv"
    path.write_text(NAME_LIST_CSV, encoding="utf-8")
    name_list = load_name_list(path)
    candidates = [{"candidate_id": "J-a", "name": ANIMALS,
                   "issn": None, "eissn": None},
                  {"candidate_id": "J-b", "name": CEA,
                   "issn": None, "eissn": None}]
    checks = checks_from_name_list(candidates, name_list, "2026-10-20")
    animals_hits = [c for c in checks["J-a"] if c["hit"]]
    assert len(animals_hits) == 1
    assert animals_hits[0]["condition"] == "predatory_list_hit"
    assert all(not c["hit"] for c in checks["J-b"])  # 未命中也落记录


def test_quasi_hard_excluded_by_default(verified_pkg):
    checks = {ANIMALS: [_check("predatory_list_hit")],
              CEA: _clear_checks(), POULTRY: _clear_checks()}
    result = apply_gate(verified_pkg, checks, today_str="2026-10-20")
    assert result["excluded"] == [ANIMALS]
    selection = load_selection(verified_pkg)
    assert selection["status"] == "gated"
    assert [c["name"] for c in selection["candidates"]] == [CEA, POULTRY]
    row = selection["excluded"][0]
    assert row["level"] == "quasi_hard"
    assert "predatory_list_hit" in row["reasons"][0]
    assert row["candidate_snapshot"]["name"] == ANIMALS


def test_quasi_hard_release_with_written_confirmation(verified_pkg):
    override = {"confirmed_by": "用户本人",
                "confirmation_text": "已知其在社区名单上，仍决定投稿",
                "date": "2026-10-20"}
    checks = {ANIMALS: [_check("predatory_list_hit")],
              CEA: _clear_checks(), POULTRY: _clear_checks()}
    result = apply_gate(verified_pkg, checks,
                        overrides={ANIMALS: override}, today_str="2026-10-20")
    assert result["excluded"] == []
    selection = load_selection(verified_pkg)
    animals = next(c for c in selection["candidates"] if c["name"] == ANIMALS)
    assert animals["risk"]["level"] == "quasi_hard"
    assert animals["risk"]["override"]["confirmation_text"] \
        .startswith("已知其在社区名单上")  # 放行永久留痕


def test_quasi_hard_incomplete_override_rejected(verified_pkg):
    checks = {ANIMALS: [_check("predatory_list_hit")],
              CEA: _clear_checks(), POULTRY: _clear_checks()}
    with pytest.raises(Exception) as exc:
        apply_gate(verified_pkg, checks,
                   overrides={ANIMALS: {"confirmed_by": "用户"}},
                   today_str="2026-10-20")
    assert "放行记录缺字段" in str(exc.value)


def test_hard_exclude_cannot_be_overridden(verified_pkg):
    override = {"confirmed_by": "用户", "confirmation_text": "仍投",
                "date": "2026-10-20"}
    checks = {POULTRY: [_check("warning_list_hit",
                               source="中科院预警名单官方页")],
              CEA: _clear_checks(), ANIMALS: _clear_checks()}
    with pytest.raises(Exception) as exc:
        apply_gate(verified_pkg, checks, overrides={POULTRY: override},
                   today_str="2026-10-20")
    assert "不许放行" in str(exc.value)


def test_missing_checks_block_gate(verified_pkg):
    checks = {CEA: _clear_checks(), ANIMALS: _clear_checks()}  # 缺 Poultry
    with pytest.raises(Exception) as exc:
        apply_gate(verified_pkg, checks, today_str="2026-10-20")
    assert "缺风险核查记录" in str(exc.value)


def test_hit_without_source_rejected(verified_pkg):
    bad = [{"condition": "warning_list_hit", "hit": True, "source": None,
            "source_ref": None, "checked_at": "2026-10-20", "note": None}]
    checks = {POULTRY: bad, CEA: _clear_checks(), ANIMALS: _clear_checks()}
    with pytest.raises(Exception) as exc:
        apply_gate(verified_pkg, checks, today_str="2026-10-20")
    assert "无源不许落命中" in str(exc.value)
