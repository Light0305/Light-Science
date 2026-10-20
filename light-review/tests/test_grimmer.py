"""GRIMMER 三元组（v1.1 REV-D07）：相容/不相容/不适用 + 奇偶约束。"""

from light_review.grim import run_grim


def _rows(entry):
    return run_grim([entry])


def _grimmer(entry):
    rows = _rows(entry)
    return [r for r in rows if r["kind"] == "grimmer"]


# 数据 [2,3,3,4]：n=4，均值 3.00，SS=38，样本 SD=sqrt(2/3)=0.8165→0.82
_BASE = {"stat_id": "GS1", "kind": "grimmer", "value": "3.00",
         "sd": "0.82", "n": 4, "scale_type": "likert"}


def test_grimmer_compatible():
    rows = _grimmer(_BASE)
    assert len(rows) == 1
    assert rows[0]["result"] == "compatible"
    assert "T=12" in rows[0]["formula_evidence"]
    assert "SS=38" in rows[0]["formula_evidence"]


def test_grimmer_incompatible_sd():
    # SD 报 1.50：SS 须 ∈ [42.7, 42.8)，无整数
    row = _grimmer(dict(_BASE, sd="1.50"))[0]
    assert row["result"] == "incompatible"


def test_grimmer_parity_constraint_bites():
    # 均值 3.0 / SD 1.0（1 位小数）：SS 区间 [38.71, 39.31) 只含 39，
    # 但 SS 与 T=12 奇偶不同（整数平方和与总和恒同奇偶）→ 不相容。
    # 无奇偶约束时 SS=39 会被误判相容，本例钉死约束真实在岗。
    row = _grimmer({"stat_id": "GS1", "kind": "grimmer", "value": "3.0",
                    "sd": "1.0", "n": 4, "scale_type": "score"})[0]
    assert row["result"] == "incompatible"


def test_grimmer_missing_sd_not_assessable():
    row = _grimmer({"stat_id": "GS1", "kind": "grimmer", "value": "3.00",
                    "n": 4, "scale_type": "likert"})[0]
    assert row["result"] == "not_assessable"
    assert "sd" in row["missing"]


def test_grimmer_continuous_not_assessable():
    row = _grimmer(dict(_BASE, scale_type="continuous"))[0]
    assert row["result"] == "not_assessable"
    assert "整数粒度" in row["detail"]


def test_grimmer_n1_not_assessable():
    row = _grimmer(dict(_BASE, n=1))[0]
    assert row["result"] == "not_assessable"
    assert "n<2" in row["detail"]


def test_grimmer_composite_mean_not_assessable():
    row = _grimmer(dict(_BASE, items=3))[0]
    assert row["result"] == "not_assessable"
    assert "复合均值" in row["detail"]


def test_mean_entry_with_sd_appends_grimmer_row():
    rows = _rows({"stat_id": "GS9", "kind": "mean", "value": "3.00",
                  "decimals": 2, "sd": "0.82", "n": 4, "items": 1,
                  "scale_type": "likert"})
    assert [r["kind"] for r in rows] == ["mean", "grimmer"]
    assert rows[0]["result"] == "compatible"
    assert rows[1]["result"] == "compatible"
    assert rows[1]["stat_id"] == "GS9"


def test_mean_entry_without_sd_no_grimmer_row():
    rows = _rows({"stat_id": "GS9", "kind": "mean", "value": "3.00",
                  "decimals": 2, "n": 4, "items": 1,
                  "scale_type": "likert"})
    assert len(rows) == 1


def test_grimmer_failure_enters_findings_flag_only(review_pkg, tmp_path):
    """GRIMMER 判败并账纪律与 GRIM 同口径：flag_only + 算式证据。"""
    from light_review.forensic import register_summaries, run_forensic
    from light_review.project import load_package
    from light_review.util import dump_yaml
    reg = tmp_path / "summaries.yaml"
    dump_yaml(reg, {"entries": [
        {"stat_id": "GS1", "kind": "mean", "value": "3.00", "decimals": 2,
         "sd": "1.50", "n": 4, "items": 1, "scale_type": "likert"}]})
    register_summaries(review_pkg, reg)
    run_forensic(review_pkg)
    findings = [r for r in load_package(review_pkg)["findings"]
                if r.get("type") == "finding"]
    grim = [f for f in findings if f["edge"] == "grim_compatibility"]
    assert len(grim) == 1
    assert grim[0]["flag_only"] is True
    assert grim[0]["category"] == "confirmed_error"
    assert "grimmer" in grim[0]["detail"]
