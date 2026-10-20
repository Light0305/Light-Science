"""核验纪律：裸指标拦截、未确认不带数、众包三标注、冲突落字
（JS-01 / JS-02 / JS-03 / E4）。"""

from __future__ import annotations

import pytest

from conftest import unconfirmed_entry, verified_entry
from light_journal_select.gates import GateError
from light_journal_select.verify import Report, apply_verification, check_metric_entry

NAME = "Computers and Electronics in Agriculture"


def _one(metrics, **kw):
    return [{"candidate": NAME, "source_status": "succeeded",
             "metrics": metrics, **kw}]


def test_bare_metric_rejected(candidates_pkg):
    with pytest.raises(GateError) as exc:
        apply_verification(candidates_pkg, _one({"impact_factor": 7.9}))
    assert "裸数值" in str(exc.value)


def test_verified_missing_triplet_field_rejected(candidates_pkg):
    entry = verified_entry(7.9)
    del entry["source_year"]
    with pytest.raises(GateError) as exc:
        apply_verification(candidates_pkg, _one({"impact_factor": entry}))
    assert "source_year" in str(exc.value)


def test_unconfirmed_with_value_rejected(candidates_pkg):
    entry = {"value": 7.9, "status": "unconfirmed",
             "source_status": "attempted"}
    with pytest.raises(GateError):
        apply_verification(candidates_pkg, _one({"impact_factor": entry}))


def test_unconfirmed_needs_four_state_reason(candidates_pkg):
    entry = {"value": None, "status": "unconfirmed"}
    with pytest.raises(GateError):
        apply_verification(candidates_pkg, _one({"impact_factor": entry}))


def test_unconfirmed_clean_passes(candidates_pkg):
    result = apply_verification(
        candidates_pkg, _one({"impact_factor": unconfirmed_entry("partial")}))
    assert result["verified_candidates"] == [NAME]


def test_unknown_metric_key_rejected(candidates_pkg):
    with pytest.raises(GateError):
        apply_verification(
            candidates_pkg, _one({"prestige_score": verified_entry(9)}))


def test_crowd_cycle_requires_three_annotations():
    rep = Report()
    entry = {"value": 9, "status": "verified", "provenance": "crowd",
             "source_url": "https://example.org", "source_year": "2026",
             "queried_at": "2026-10-20",
             "annotations": {"basis": "LetPub 众包投稿经验",
                             "queried_at": "2026-10-20"}}  # 缺 sample_size
    check_metric_entry("review_cycle", entry, rep, where="t")
    assert any(i["code"] == "metric.crowd_annotation" for i in rep.errors)


def test_crowd_cycle_undisclosed_sample_size_ok():
    rep = Report()
    entry = {"value": 9, "status": "verified", "provenance": "crowd",
             "source_url": "https://example.org", "source_year": "2026",
             "queried_at": "2026-10-20",
             "annotations": {"basis": "LetPub 众包投稿经验",
                             "sample_size": "未披露",
                             "queried_at": "2026-10-20"}}
    check_metric_entry("review_cycle", entry, rep, where="t")
    assert rep.ok


def test_conflict_without_resolution_rejected():
    rep = Report()
    entry = verified_entry(3000, conflicts=[
        {"value": 2500, "source_url": "https://example.org/other"}])
    check_metric_entry("apc", entry, rep, where="t")
    assert any(i["code"] == "metric.conflict_unresolved" for i in rep.errors)
    entry["conflict_resolution"] = "官网价目优先（JS-03），聚合站值记为冲突"
    rep2 = Report()
    check_metric_entry("apc", entry, rep2, where="t")
    assert rep2.ok


def test_bad_quartile_value_rejected():
    rep = Report()
    check_metric_entry("quartile_jcr", verified_entry("Q9"), rep, where="t")
    assert any(i["code"] == "metric.jcr_value" for i in rep.errors)


def test_full_verification_advances_state(verified_pkg):
    from light_journal_select.project import load_selection
    selection = load_selection(verified_pkg)
    assert selection["status"] == "verified"
    blocks = {c["name"]: c["verification"] for c in selection["candidates"]}
    assert blocks["Animals"]["metrics"]["review_cycle"]["provenance"] == "crowd"
