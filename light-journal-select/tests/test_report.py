"""分档与证据卡：只读 verified、众包不决定分档、暂定封顶、
挑战不凑数、报告落盘形态（JS-02 / JS-04 / E4 / 草案 §五）。"""

from __future__ import annotations

from conftest import unconfirmed_entry, verified_entry
from light_journal_select.gate import apply_gate
from light_journal_select.project import load_selection, new_candidate
from light_journal_select.report import (
    assign_tiers, constraint_flags, run_report,
)

CEA = "Computers and Electronics in Agriculture"
ANIMALS = "Animals"


def _cand(name, source="precedent", precedent=None, metrics=None):
    cand = new_candidate(name, source)
    cand["precedent"] = precedent
    cand["risk"] = {"level": "clear", "checks": [], "override": None,
                    "evaluated_at": "2026-10-20"}
    if metrics is not None:
        cand["verification"] = {"checked_at": "2026-10-20",
                                 "source_status": "succeeded",
                                 "metrics": metrics}
    return cand


def _stats(n=3, rate=2.0):
    return {"similar_works_n": n, "rate_per_10k": rate,
            "journal_volume_window": 15000, "volume_status": "succeeded",
            "queries_covered": 2, "best_rank": 1,
            "window": {"from": "2022-01-01", "to": "2026-12-31"},
            "queried_at": "2026-10-20",
            "precedents": [{"title": "Paper", "year": 2024,
                            "doi": "https://doi.org/10.1/x",
                            "openalex_id": "https://openalex.org/W1"}]}


def test_tiering_reads_only_verified():
    sel = {"constraints": {}, "candidates": [
        _cand("Unverified Q1 Journal", precedent=_stats(),
              metrics={"quartile_jcr": unconfirmed_entry()}),
        _cand("Verified Q1 Journal", precedent=_stats(),
              metrics={"quartile_jcr": verified_entry("Q1")}),
    ]}
    tiers = assign_tiers(sel)
    by_name = {c["name"]: c["tier"] for c in sel["candidates"]}
    assert by_name["Verified Q1 Journal"] == "challenge"
    assert by_name["Unverified Q1 Journal"] != "challenge"


def test_challenge_not_forced_when_none_qualify():
    sel = {"constraints": {}, "candidates": [
        _cand("Mid Journal", metrics={"quartile_jcr": verified_entry("Q3")}),
        _cand("Low Journal", metrics={"quartile_jcr": verified_entry("Q4")}),
    ]}
    assign_tiers(sel)
    tiers = {c["tier"] for c in sel["candidates"]}
    assert "challenge" not in tiers  # 无合格者如实留空


def test_provisional_capped_at_safety():
    cand = _cand("Metrics Only Journal", source="search", precedent=None,
                 metrics={"quartile_jcr": verified_entry("Q1")})
    sel = {"constraints": {}, "candidates": [cand]}
    assign_tiers(sel)
    assert cand["provisional"] is True
    assert cand["tier"] == "safety"  # 仅指标支撑 → 暂定，至多 safety（JS-04）


def test_crowd_cycle_never_flags_constraint():
    cand = _cand("Crowd Cycle Journal", metrics={
        "review_cycle": {
            "value": 12, "status": "verified", "provenance": "crowd",
            "source_url": "https://example.org", "source_year": "2026",
            "queried_at": "2026-10-20",
            "annotations": {"basis": "众包", "sample_size": "未披露",
                            "queried_at": "2026-10-20"}}})
    flags = constraint_flags(cand, {"review_cycle_limit": 6})
    assert "cycle_over_limit" not in flags  # E4：众包不单独决定分档


def test_official_cycle_and_apc_flags():
    cand = _cand("Slow Expensive Journal", metrics={
        "review_cycle": verified_entry(12),
        "apc": verified_entry(5000)})
    flags = constraint_flags(
        cand, {"review_cycle_limit": 6, "apc_budget": 2000})
    assert flags == ["apc_over_budget", "cycle_over_limit"]


def _gated(verified_pkg):
    clear = [{"condition": "warning_list_hit", "hit": False,
              "source": "official-page", "source_ref": "2026-10-20",
              "checked_at": "2026-10-20", "note": None}]
    names = [c["name"] for c in load_selection(verified_pkg)["candidates"]]
    apply_gate(verified_pkg, {n: clear for n in names},
               today_str="2026-10-20")
    return verified_pkg


def test_report_end_to_end(verified_pkg, tmp_path):
    root = _gated(verified_pkg)
    result = run_report(root, today_str="2026-10-20")
    assert result["cards_total"] == 3
    assert result["tiers"] == {"challenge": 1, "target": 2, "safety": 0}
    selection = load_selection(root)
    tiers = {c["name"]: c["tier"] for c in selection["candidates"]}
    assert tiers[CEA] == "challenge"      # verified Q1 + 先例
    assert tiers[ANIMALS] == "target"     # verified Q2；众包周期未误伤
    text = (root / "SELECTION_REPORT.md").read_text(encoding="utf-8")
    assert CEA in text and "已排除清单" in text
    assert "未确认" in text               # Poultry 的 IF 如实未确认
    assert "众包口径" in text             # Animals 众包周期三标注显形
    assert "人工复核清单" in text         # finder 手工区（E2）
    export = (root / "selection.json").read_text(encoding="utf-8")
    assert "selection-export" in export


def test_report_requires_gated(verified_pkg):
    import pytest
    from light_journal_select.gates import GateError
    with pytest.raises(GateError):
        run_report(verified_pkg)  # 还没过风险门不许出报告
