"""WRT-D08 五处小账清零的回归测试（v1.1，每处至少一条钉住）。"""

import copy

from light_write import schema
from light_write.validate import Report, check_template_record
from conftest import make_record


def _errors(record):
    rep = Report()
    check_template_record(record, rep)
    return rep.errors


def _codes(record):
    return {e["code"] for e in _errors(record)}


# (1) 字段数实数 46（schema 注释 / SKILL 6.1 / README 口径的事实源）
def test_d08_1_template_field_count_is_46():
    total = sum(len(spec["fields"]) for spec in schema.TEMPLATE_GROUPS.values())
    assert total == 46


# (3) declarations 四键实查：缺 required / field_name 必报错，全键必过
def test_d08_3_declarations_missing_required_key():
    record = make_record()
    del record["G"]["declarations"][0]["required"]
    assert "template.declaration_shape" in _codes(record)


def test_d08_3_declarations_missing_field_name():
    record = make_record()
    record["G"]["declarations"][0]["field_name"] = ""
    assert "template.declaration_shape" in _codes(record)


def test_d08_3_declarations_full_shape_passes():
    assert "template.declaration_shape" not in _codes(make_record())


# (4) official_channel 词表 + keyword_limit / review_cycle_days 类型
def test_d08_4_official_channel_vocab():
    record = make_record()
    record["H"]["official_channel"] = "a_blog_post"
    assert "template.official_channel_vocab" in _codes(record)
    for ok_value in schema.OFFICIAL_CHANNELS:
        record = make_record()
        record["H"]["official_channel"] = ok_value
        assert "template.official_channel_vocab" not in _codes(record)


def test_d08_4_keyword_limit_must_be_int():
    record = make_record()
    record["C"]["keyword_limit"] = "6"
    assert "template.keyword_limit_type" in _codes(record)
    record = make_record()
    record["C"]["keyword_limit"] = True
    assert "template.keyword_limit_type" in _codes(record)
    record = make_record()
    record["C"]["keyword_limit"] = 6
    assert "template.keyword_limit_type" not in _codes(record)


def test_d08_4_review_cycle_days_must_be_numeric():
    record = make_record()
    record["H"]["review_cycle_days"] = "180d"
    assert "template.review_cycle_type" in _codes(record)
    record = make_record()
    record["H"]["review_cycle_days"] = 180
    assert "template.review_cycle_type" not in _codes(record)


# (5) AI 政策组逐项必填：删任一子字段键必报错（值 null 不算缺席）
def test_d08_5_ai_policy_all_subfields_required():
    for field in schema.TEMPLATE_GROUPS["G"]["ai_policy_required"]:
        record = make_record()
        del record["G"]["ai_policy"][field]
        assert "template.ai_policy_field" in _codes(record), field


def test_d08_5_ai_policy_null_values_still_present():
    record = make_record()
    record["G"]["ai_policy"]["output_validity_evaluation"] = None
    record["G"]["ai_policy"]["disclosure_title"] = None
    assert "template.ai_policy_field" not in _codes(record)


def test_d08_baseline_record_still_valid():
    assert _errors(make_record()) == []
