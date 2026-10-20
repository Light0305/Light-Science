"""先例路引擎：聚合、归一化、入门门槛、失败落痕（JS-04/JS-05）。"""

from __future__ import annotations

import pytest

from conftest import FakeFetcher, Q0, Q1, works_payload
from light_journal_select.gates import GateError
from light_journal_select.precedent import aggregate, run_precedent
from light_journal_select.project import load_selection


def _by_name(selection):
    return {c["name"]: c for c in selection["candidates"]}


def test_aggregate_skips_retracted_and_nonresearch():
    journals = aggregate([works_payload(Q0), works_payload(Q1)])
    names = {e["name"] for e in journals.values()}
    # 撤稿刊与社论所在刊不产生任何聚合条目（其作品全被剔）
    assert "Journal of Obscure Results" not in names
    cea = next(e for e in journals.values()
               if e["name"].startswith("Computers"))
    assert len(cea["works"]) == 2  # W1 + W3，跨式不重复计


def test_run_precedent_pool_and_normalization(candidates_pkg):
    selection = load_selection(candidates_pkg)
    assert selection["status"] == "candidates_ready"
    pool = _by_name(selection)
    assert set(pool) == {"Computers and Electronics in Agriculture",
                         "Animals", "Poultry Science"}
    cea = pool["Computers and Electronics in Agriculture"]["precedent"]
    assert cea["similar_works_n"] == 2
    assert cea["journal_volume_window"] == 20000
    assert cea["rate_per_10k"] == pytest.approx(1.0)  # 2/20000*10^4
    animals = pool["Animals"]["precedent"]
    assert animals["similar_works_n"] == 2
    assert animals["rate_per_10k"] == pytest.approx(2.5)  # 归一化后反超大刊
    assert animals["queries_covered"] == 2
    poultry = pool["Poultry Science"]["precedent"]
    assert poultry["similar_works_n"] == 1
    assert poultry["best_rank"] == 2  # 靠单式名次入门
    assert len(poultry["precedents"]) == 1
    assert poultry["precedents"][0]["doi"] == "https://doi.org/10.3382/ps.2024.001"


def test_near_miss_recorded_not_admitted(candidates_pkg):
    selection = load_selection(candidates_pkg)
    misses = {m["name"] for m in selection["precedent_near_misses"]}
    assert misses == {"Small Venue Journal"}  # 相似 1、单式、名次 5


def test_raw_responses_archived(candidates_pkg):
    selection = load_selection(candidates_pkg)
    runs = selection["precedent_runs"]
    assert len(runs) == 2
    for run in runs:
        assert run["status"] == "succeeded"
        assert run["window"] == {"from": "2022-01-01", "to": "2026-12-31"}
        assert (candidates_pkg / run["evidence_file"]).exists()


def test_partial_failure_still_proceeds(pkg):
    result = run_precedent(pkg, fetcher=FakeFetcher(fail_queries={Q1}),
                           today_str="2026-10-20")
    assert result["queries_ok"] == 1
    selection = load_selection(pkg)
    statuses = [r["status"] for r in selection["precedent_runs"]]
    assert statuses == ["succeeded", "failed"]  # 失败如实落痕


def test_all_failures_raise_and_leave_no_candidates(pkg):
    with pytest.raises(GateError):
        run_precedent(pkg, fetcher=FakeFetcher(fail_all=True),
                      today_str="2026-10-20")
    selection = load_selection(pkg)
    assert selection["status"] == "draft"  # 不许拿空池冒充已生成
    assert selection["candidates"] == []
    assert all(r["status"] == "failed" for r in selection["precedent_runs"])
    assert all(r["error"] for r in selection["precedent_runs"])


def test_volume_failure_leaves_rate_empty(pkg, monkeypatch):
    class VolumeFailFetcher(FakeFetcher):
        def __call__(self, url):
            if "search" not in url:
                raise ConnectionError("volume endpoint down")
            return super().__call__(url)

    run_precedent(pkg, fetcher=VolumeFailFetcher(), today_str="2026-10-20")
    selection = load_selection(pkg)
    cea = _by_name(selection)["Computers and Electronics in Agriculture"]
    assert cea["precedent"]["rate_per_10k"] is None  # 分母取不到不猜数
    assert cea["precedent"]["volume_status"] == "attempted"
