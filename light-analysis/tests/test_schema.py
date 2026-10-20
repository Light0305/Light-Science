"""词表与 schema 骨架测试。"""

from light_analysis import schema


def test_vocabularies():
    assert schema.VERDICTS == ["positive", "negative", "null",
                                "undetermined", "untested"]
    assert schema.GRADES == ["conclusive", "strong", "suggestive", "insufficient"]
    assert "undetermined" in schema.QUADRANTS
    assert schema.SPEC_CAP == 512
    assert schema.R_HAT_MAX == 1.01 and schema.ESS_MIN == 400


def test_power_basis_field_rule():
    assert schema.POWER_BASIS_OK == ["sesoi_frozen", "prior_external"]
    assert "observed" in schema.POWER_BASIS_BANNED
    assert schema.TOST_BOUNDS_SOURCES_OK == ["design_sesoi"]


def test_scan_forbidden_hits():
    assert schema.scan_forbidden("结果显著优于对照") == ["显著"]
    assert "证明了" in schema.scan_forbidden("本实验证明了该映射成立")
    assert "无影响" in schema.scan_forbidden("处理对结果无影响")
    assert "significant" in schema.scan_forbidden("a significant difference")


def test_scan_forbidden_clean():
    assert schema.scan_forbidden("P(A>B)=0.83，落 positive / strong 档") == []
    assert schema.scan_forbidden("") == []
    assert schema.scan_forbidden(None) == []


def test_scan_banned_words_whole_word():
    # 整词匹配：strong 命中，stronger 不命中（防误伤普通叙述）
    assert "strong" in schema.scan_banned_words("a strong pattern emerged")
    assert schema.scan_banned_words("a stronger pattern emerged") == []
    assert "positive" in schema.scan_banned_words("positive correlation noted")


def test_verdict_row_template_has_five_groups():
    row = schema.verdict_row("L-1", "positive")
    for key in ("verdict", "quadrant", "basis_spec_id",          # 判定组
                "effect_size", "interval", "p_ab",               # 量组
                "n_effective", "n_registered",
                "type_sm",                                       # 校准组
                "tost",                                          # 等价组
                "diagnostics",                                   # 诊断组
                "correction",                                    # 校正组
                "strength_grade",                                # 强度组
                "note", "decided_by", "decided_at"):
        assert key in row, key
    assert row["verdict"] == "positive"


def test_empty_structures():
    a = schema.new_analysis("ana-1")
    assert a["status"] == "intake"
    assert a["counts"] == schema.empty_counts()
    assert schema.new_conclusions()["claims_verdict"] == []
    assert schema.new_exploratory()["entries"] == []
    assert schema.new_spec_ledger()["frozen_hash"] is None
