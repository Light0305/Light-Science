"""schema 层：ID 派生、溯源、区间算术含界、算子表、关系权重地板。"""

from light_memory import schema


def test_object_id_derivation_deterministic():
    a = schema.derive_object_id("paper", "paper-turkey_abc")
    b = schema.derive_object_id("paper", "paper-turkey_abc")
    assert a == b == "paper:paper-turkey_abc"


def test_fact_id_derivation_stable_and_sensitive():
    a = schema.derive_fact_id("claim:C1", "陈述甲", "2026-01-01", "analysis")
    b = schema.derive_fact_id("claim:C1", "陈述甲", "2026-01-01", "analysis")
    c = schema.derive_fact_id("claim:C1", "陈述乙", "2026-01-01", "analysis")
    assert a == b and a != c and a.startswith("fact_")


def test_provenance_gaps():
    full = schema.make_provenance("idea", "memory_export.jsonl", "E1", "h")
    assert schema.provenance_gaps(full) == []
    broken = dict(full, source_anchor=None)
    assert schema.provenance_gaps(broken) == ["source_anchor"]
    assert len(schema.provenance_gaps(None)) == 5
    assert len(schema.provenance_gaps({})) == 5


def test_intervals_overlap_boundaries():
    ov = schema.intervals_overlap
    # 内部相交
    assert ov("2026-01-01", "2026-02-01", "2026-01-15", None) is True
    # 边界相接（半开区间）：a_end == b_start 不算重叠
    assert ov("2026-01-01", "2026-02-01", "2026-02-01", None) is False
    # 完全在之前
    assert ov("2026-01-01", "2026-02-01", "2025-01-01", "2025-06-01") \
        is False
    # 开区间对开区间
    assert ov("2026-01-01", None, "2026-06-01", None) is True
    # 缺开始时间不判重叠（调用方须先处理无时间戳情形）
    assert ov(None, None, "2026-01-01", None) is False


def test_check_interval():
    bad = {"fact_id": "f1", "valid_at": "2026-02-01",
           "invalid_at": "2026-01-01", "created_at": "2026-01-01",
           "expired_at": None}
    assert schema.check_interval(bad)
    good = {"fact_id": "f2", "valid_at": "2026-01-01",
            "invalid_at": "2026-02-01", "created_at": "2026-01-01",
            "expired_at": "2026-03-01"}
    assert schema.check_interval(good) == []
    # invalid_at == valid_at（零长区间）合法
    edge = dict(good, invalid_at="2026-01-01")
    assert schema.check_interval(edge) == []


def test_merge_operator_table():
    assert schema.merge_operator("conclusion") == "supersede_only"
    assert schema.merge_operator("decision") == "immutable"
    assert schema.merge_operator("lesson") == "merge_union"
    assert schema.merge_operator("method") == "patch"
    assert schema.merge_operator("没见过的类型") == "free"


def test_relation_weight_floor_protected():
    prov = schema.make_provenance("literature", "x", "a", "h")
    rel = schema.new_relation("refutes", "a", "b", prov, weight=0.1)
    assert rel["weight"] >= 0.7  # 否定边权重下限受保护（MM-20）
    rel2 = schema.new_relation("inspires", "a", "b", prov)
    assert rel2["generation"] == "judged"  # 弱关系只许判定生成


def test_new_fact_shape():
    prov = schema.make_provenance("analysis", "card", "C1", "h")
    f = schema.new_fact("陈述", "conclusion", "claim:C1", prov,
                        valid_at="2026-01-01")
    assert f["status"] == "current"
    assert f["superseded_by"] is None and f["supersedes"] is None
    assert f["stale"] is False
    assert f["strength"] == {"calls": 0, "last_called_at": None,
                             "dormant": False}
    assert f["provenance"][0]["source_package"] == "analysis"
