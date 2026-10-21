"""登记校验与速率公式（S2/S3/S5/S6、HC-5）。"""

from conftest import make_reg

from light_crawler import schema


def test_valid_registration_passes():
    assert schema.validate_target(make_reg("https://example.org")) == []


def test_login_state_rejected_in_v1():
    problems = schema.validate_target(
        make_reg("https://example.org", login_state="cookie"))
    assert any("S2" in p for p in problems)


def test_concurrency_must_be_one():
    problems = schema.validate_target(
        make_reg("https://example.org", concurrency=4))
    assert any("concurrency" in p for p in problems)


def test_warc_tier_opened_by_batch5():
    # 沿革：v1 时 warc_full 为预留档、登记即拒（旧钉
    # test_warc_tier_reserved_for_v11）；第五批计算扩面（PLAN §13
    # P1）WARC 落地后转正式可用档，本钉随之改口径。
    problems = schema.validate_target(
        make_reg("https://example.org", retention_tier="warc_full"))
    assert problems == []


def test_unknown_retention_tier_rejected():
    problems = schema.validate_target(
        make_reg("https://example.org", retention_tier="tape_archive"))
    assert any("retention_tier" in p for p in problems)


def test_near_duplicate_config_validation():
    ok = schema.validate_target(make_reg(
        "https://example.org",
        near_duplicate={"enabled": True, "hamming_threshold": 5}))
    assert ok == []
    for bad in ({"hamming_threshold": 65}, {"hamming_threshold": -1},
                {"hamming_threshold": True}, {"enabled": "yes"}):
        problems = schema.validate_target(
            make_reg("https://example.org", near_duplicate=bad))
        assert any("near_duplicate" in p for p in problems), bad
    problems = schema.validate_target(
        make_reg("https://example.org", near_duplicate="off"))
    assert any("near_duplicate" in p for p in problems)


def test_near_duplicate_config_defaults_and_override():
    assert schema.near_duplicate_config({}) == {
        "enabled": True,
        "hamming_threshold": schema.DEFAULT_NEAR_DUP_HAMMING_THRESHOLD}
    cfg = schema.near_duplicate_config(
        {"near_duplicate": {"enabled": False, "hamming_threshold": 7}})
    assert cfg == {"enabled": False, "hamming_threshold": 7}


def test_single_fulltext_purpose_out_of_scope():
    problems = schema.validate_target(
        make_reg("https://example.org", purpose_kind="single_fulltext"))
    assert any("S5" in p for p in problems)


def test_personal_data_high_rejected():
    problems = schema.validate_target(
        make_reg("https://example.org", personal_data_risk="high"))
    assert any("HC-5" in p for p in problems)


def test_personal_data_low_needs_scope_note():
    problems = schema.validate_target(
        make_reg("https://example.org", personal_data_risk="low"))
    assert any("scope_note" in p for p in problems)
    ok = schema.validate_target(make_reg(
        "https://example.org", personal_data_risk="low",
        scope_note="只取已公开的作者名与机构，最小必要"))
    assert ok == []


def test_interval_below_template_needs_rate_basis():
    reg = make_reg("https://example.org", channel="web_page",
                   rate={"registered_interval_sec": 0.1})
    problems = schema.validate_target(reg)
    assert any("rate_basis" in p for p in problems)
    reg["rate"]["rate_basis"] = "目标 API 条款页第 3 条（许可 10 req/s）"
    assert schema.validate_target(reg) == []


def test_effective_interval_formula_takes_strictest():
    reg = make_reg("https://example.org", channel="web_page",
                   rate={"registered_interval_sec": 8})
    d = schema.effective_interval(reg, crawl_delay_sec=3)
    assert d["effective_interval_sec"] == 8  # 登记值最严
    d = schema.effective_interval(reg, crawl_delay_sec=20)
    assert d["effective_interval_sec"] == 20  # robots 延迟最严
    d = schema.effective_interval(reg)
    assert d["effective_interval_sec"] == 8
    reg2 = make_reg("https://example.org", channel="web_page")
    d = schema.effective_interval(reg2, lock_min_interval_sec=30)
    assert d["effective_interval_sec"] == 30  # 项目锁下限
    assert d["decided_by"] == "project_lock"


def test_template_defaults_are_conservative():
    for channel, floor in (("official_api", 1.0), ("open_data", 2.0),
                           ("web_page", 5.0), ("browser", 10.0)):
        d = schema.effective_interval(make_reg("https://x.org", channel=channel))
        assert d["effective_interval_sec"] == floor
