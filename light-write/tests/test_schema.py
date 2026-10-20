"""schema 口径：writable_form 导出规则 + 双语措辞词表 + 撤稿四态/九组字段。"""

import pytest

from light_write import schema


@pytest.mark.parametrize("status,grade,expected", [
    ("supported", "conclusive", "full"),
    ("supported", "strong", "full"),
    ("supported", "suggestive", "qualified"),
    ("supported", "insufficient", "downgraded"),
    ("partial", "strong", "qualified"),
    ("partial", "insufficient", "downgraded"),
    ("undetermined", "conclusive", "downgraded"),
    ("undetermined", "insufficient", "downgraded"),
    ("untested", "conclusive", "limitations_only"),
    ("untested", "insufficient", "limitations_only"),
])
def test_writable_ceiling_matrix(status, grade, expected):
    assert schema.writable_ceiling(status, grade) == expected


def test_form_rank_order():
    ranks = [schema.form_rank(f) for f in schema.WRITABLE_FORMS]
    assert ranks == sorted(ranks, reverse=True)


def test_wording_tables_bilingual():
    zh = schema.WORDING_TABLES["zh"]["banned_terms"]
    assert "证明了" in zh and "显著" in zh and "不显著" in zh
    en = schema.WORDING_TABLES["en"]["banned_terms"]
    assert "proves" in en and "no effect" in en
    for lang in ("en", "zh"):
        entry = schema.wording_ceiling_for(lang, "suggestive")
        assert entry["language"] == lang
        assert entry["ceiling_label"] == "hedged"
        assert entry["allowed_terms"]


def test_retraction_four_states_and_fabrication_levels_named_separately():
    assert schema.RETRACTION_STATES == ["retracted", "no_doi", "unknown", "clean"]
    levels = schema.CITATION_FABRICATION_LEVELS
    # 差异 (a)：字段级筛与身份级判定分名、口径不同
    assert levels["field_level_hallucination_screen"]["granularity"] == "field"
    assert levels["identity_level_fabrication"]["granularity"] == "identity"
    assert "任二" in levels["field_level_hallucination_screen"]["rule"]


def test_template_groups_nine_with_ai_policy_extras():
    # 差异 (e)：九组为准；差异 (f)：AI 组含声明标题/措辞模板/多值位置子项
    assert sorted(schema.TEMPLATE_GROUPS) == list("ABCDEFGHI")
    g = schema.TEMPLATE_GROUPS["G"]
    assert "declarations" in g["required"] and "ai_policy" in g["required"]
    assert schema.TEMPLATE_GROUPS["D"]["at_least_one"] is True
