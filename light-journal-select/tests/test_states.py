"""状态机门与包级校验：不许跳段、留痕形态、约束键纪律。"""

from __future__ import annotations

import pytest

from conftest import FakeFetcher
from light_journal_select.gates import GateError, advance_to, transition_gaps
from light_journal_select.precedent import run_precedent
from light_journal_select.project import init_package, load_selection
from light_journal_select.validate import validate_package, validate_selection


def test_no_skipping_states(pkg):
    selection = load_selection(pkg)
    gaps = transition_gaps(selection, "verified")
    assert gaps  # draft 不许直跳 verified
    with pytest.raises(GateError):
        advance_to(pkg, "gated", by="test")


def test_candidates_ready_requires_candidates(pkg):
    selection = load_selection(pkg)
    gaps = transition_gaps(selection, "candidates_ready")
    assert any("候选池为空" in g for g in gaps)


def test_verified_gate_names_unverified_candidates(candidates_pkg):
    selection = load_selection(candidates_pkg)
    gaps = transition_gaps(selection, "verified")
    assert len(gaps) == 3  # 三刊逐项点名
    assert all("未登记核验块" in g for g in gaps)


def test_happy_path_history(candidates_pkg):
    selection = load_selection(candidates_pkg)
    history = [h["state"] for h in selection["status_history"]]
    assert history == ["draft", "candidates_ready"]


def test_fresh_package_validates_with_only_warnings(pkg):
    report = validate_package(pkg)
    assert report["ok"]  # 约束未设只 warning，不许 error 冒充
    assert any(i["code"] == "constraints.unset" for i in report["warnings"])


def test_tampered_excluded_entry_fails(verified_pkg):
    selection = load_selection(verified_pkg)
    selection["excluded"].append({"candidate_id": "J-x", "name": "Ghost",
                                  "level": "hard_exclude"})  # 缺 reasons/at
    rep = validate_selection(selection)
    assert any(i["code"] == "excluded.field" for i in rep.errors)


def test_quasi_hard_tiered_without_override_fails():
    from light_journal_select.project import new_candidate
    cand = new_candidate("Risky Journal", "search")
    cand["tier"] = "target"
    cand["risk"] = {"level": "quasi_hard", "checks": [], "override": None,
                    "evaluated_at": "2026-10-20"}
    sel = {"status": "gated",
           "status_history": [{"state": "draft"}, {"state": "gated"}],
           "manuscript": {"language": "en", "type": "research"},
           "fingerprint": None, "queries": [], "constraints": {},
           "candidates": [cand], "excluded": [], "precedent_runs": []}
    rep = validate_selection(sel)
    assert any(i["code"] == "candidate.quasi_hard_tiered"
               for i in rep.errors)


def test_rate_without_volume_fails():
    from light_journal_select.project import new_candidate
    cand = new_candidate("Sourceless Rate Journal", "precedent")
    cand["precedent"] = {"similar_works_n": 3, "rate_per_10k": 2.0,
                         "journal_volume_window": None,
                         "queries_covered": 2, "best_rank": 1,
                         "window": {"from": "2022-01-01", "to": "2026-12-31"},
                         "queried_at": "2026-10-20", "precedents": []}
    sel = {"status": "candidates_ready",
           "status_history": [{"state": "draft"},
                              {"state": "candidates_ready"}],
           "manuscript": {"language": "en", "type": "research"},
           "fingerprint": None, "queries": [], "constraints": {},
           "candidates": [cand], "excluded": [], "precedent_runs": []}
    rep = validate_selection(sel)
    assert any(i["code"] == "candidate.rate_without_volume"
               for i in rep.errors)


def test_duplicate_init_rejected(tmp_path):
    root = tmp_path / "sel"
    init_package(root, "T", "en")
    with pytest.raises(FileExistsError):
        init_package(root, "T", "en")


def test_cli_end_to_end(tmp_path, monkeypatch):
    """CLI 全链（precedent 走 fixture 注入的模块级 fetcher 替身）。"""
    import light_journal_select.precedent as precedent_mod
    from light_journal_select.cli import main

    root = str(tmp_path / "sel")
    assert main(["init", root, "--title", "T turkey", "--language", "en"]) == 0

    import json
    fp = tmp_path / "fp.json"
    from conftest import FINGERPRINT_PAYLOAD
    fp.write_text(json.dumps(FINGERPRINT_PAYLOAD), encoding="utf-8")
    assert main(["fingerprint", root, "--file", str(fp)]) == 0

    monkeypatch.setattr(precedent_mod, "live_fetcher", FakeFetcher())
    assert main(["precedent", root]) == 0
    assert main(["status", root]) == 0
    assert main(["validate", root]) == 0
    # Phase 2 命令如实报未实现，不许假装
    assert main(["decide", root, "--candidate", "x"]) == 1
    assert main(["handoff", root]) == 1
