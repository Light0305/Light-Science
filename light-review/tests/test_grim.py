"""GRIM 族三件正反例 + 舍入区间边界 + 适用性硬门（RV-08/RV-09）。"""

from light_review.grim import consistent_with_rounding, run_grim


def _one(entry):
    return run_grim([entry])[0]


# ---------------------------------------------------------------- 舍入区间

def test_rounding_interval_boundaries():
    # 半上舍入：下界含、上界不含（正确舍入永不判错）
    assert consistent_with_rounding("5.25", 5.245) is True
    assert consistent_with_rounding("5.25", 5.255) is False
    assert consistent_with_rounding("5.25", 5.2493333) is True
    assert consistent_with_rounding("5.25", 5.26) is False
    assert consistent_with_rounding("abc", 1.0) is None


# ---------------------------------------------------------------- 均值粒度

def test_grim_mean_compatible():
    row = _one({"stat_id": "GS1", "kind": "mean", "value": "3.47",
                "decimals": 2, "n": 30, "items": 1, "scale_type": "likert"})
    assert row["result"] == "compatible"
    assert "k=" in row["formula_evidence"]


def test_grim_mean_incompatible():
    row = _one({"stat_id": "GS1", "kind": "mean", "value": "2.33",
                "decimals": 2, "n": 7, "items": 1, "scale_type": "likert"})
    assert row["result"] == "incompatible"
    assert "无整数解" in row["formula_evidence"]


def test_grim_mean_items_multiply_units():
    # 3 items × 10 人：总和单位 30，2.33*30=69.9 → k=70 时均值 2.333… 相容
    row = _one({"stat_id": "GS1", "kind": "mean", "value": "2.33",
                "decimals": 2, "n": 10, "items": 3, "scale_type": "score"})
    assert row["result"] == "compatible"


def test_grim_mean_missing_metadata_not_assessable():
    row = _one({"stat_id": "GS1", "kind": "mean", "value": "3.47",
                "decimals": 2, "scale_type": "likert"})
    assert row["result"] == "not_assessable"
    assert set(row["missing"]) == {"n", "items"}


def test_grim_mean_continuous_scale_not_assessable():
    row = _one({"stat_id": "GS1", "kind": "mean", "value": "3.47",
                "decimals": 2, "n": 30, "items": 1,
                "scale_type": "continuous"})
    assert row["result"] == "not_assessable"
    assert "连续量" in row["detail"]


# ---------------------------------------------------------------- 百分比粒度

def test_grim_percent_compatible():
    row = _one({"stat_id": "GS1", "kind": "percent", "value": "33.3",
                "decimals": 1, "n": 30, "scale_type": "count"})
    assert row["result"] == "compatible"


def test_grim_percent_incompatible():
    row = _one({"stat_id": "GS1", "kind": "percent", "value": "33.3",
                "decimals": 1, "n": 7, "scale_type": "count"})
    assert row["result"] == "incompatible"


def test_grim_percent_wrong_scale_not_assessable():
    row = _one({"stat_id": "GS1", "kind": "percent", "value": "33.3",
                "decimals": 1, "n": 30, "scale_type": "likert"})
    assert row["result"] == "not_assessable"


# ---------------------------------------------------------------- 合计相容性

def test_grim_total_compatible():
    row = _one({"stat_id": "GS1", "kind": "total", "value": "3.60",
                "decimals": 2, "parts": ["1.25", "2.35"]})
    assert row["result"] == "compatible"


def test_grim_total_incompatible():
    row = _one({"stat_id": "GS1", "kind": "total", "value": "3.65",
                "decimals": 2, "parts": ["1.25", "2.35"]})
    assert row["result"] == "incompatible"


def test_grim_total_boundary_exactly_at_bound():
    # d=1，分项 1 个：容差 =(1+1)×0.05=0.1；差恰为 0.1 → 相容（含界）
    row = _one({"stat_id": "GS1", "kind": "total", "value": "1.1",
                "decimals": 1, "parts": ["1.0"]})
    assert row["result"] == "compatible"
    row2 = _one({"stat_id": "GS1", "kind": "total", "value": "1.2",
                 "decimals": 1, "parts": ["1.0"]})
    assert row2["result"] == "incompatible"


def test_grim_total_missing_parts_not_assessable():
    row = _one({"stat_id": "GS1", "kind": "total", "value": "3.60",
                "decimals": 2})
    assert row["result"] == "not_assessable"
    assert "parts" in row["missing"]


def test_grim_unknown_kind_not_assessable():
    row = _one({"stat_id": "GS1", "kind": "grimmer", "value": "1.0"})
    assert row["result"] == "not_assessable"
