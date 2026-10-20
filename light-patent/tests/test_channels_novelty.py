"""渠道层（Q3/Q9）+ 查新（LP-01/05/06）：自动化默认关、最小披露、
失败分型、未核验不得锁 D1、Fk 编号、不过降级。"""

import pytest

from light_patent import channels, novelty
from light_patent.project import PatentError, load_case

from conftest import audit_clear, drive_to_mined, drive_to_searched


def test_registry_has_auditability_fields():
    for ch in channels.channel_registry():
        assert ch["auditability"] and ch["reproducibility"]
        assert ch["disclosure_note"]
    auto = [c for c in channels.channel_registry()
            if c["mode"] == "automation"]
    assert auto and all(c["automation_default"] == "off" for c in auto)


def test_enable_automation_requires_crawler_ref(case_root):
    with pytest.raises(PatentError) as ei:
        channels.enable_channel(case_root, "cnipa-epub-automation",
                                {"enabled_by": "测试"})
    assert "crawler" in str(ei.value)
    state = channels.enable_channel(case_root, "cnipa-epub-automation", {
        "enabled_by": "测试",
        "crawler_precheck_ref": "crawler-precheck-2026-001"})
    assert state["enabled"] is True


def test_enable_vendor_api_requires_disclosure_ack(case_root):
    with pytest.raises(PatentError):
        channels.enable_channel(case_root, "patsnap-api", {})
    state = channels.enable_channel(case_root, "patsnap-api", {
        "disclosure_acknowledged": True})
    assert state["enabled"] is True


def test_query_minimal_disclosure(case_root):
    case = load_case(case_root)
    q = channels.build_query(case, ipc_codes=["G06V"],
                             means_phrases=["家禽行为检测", "异常报警"])
    assert "IPC:G06V" in q and "家禽行为检测" in q


def test_query_rejects_title_and_sentence(case_root):
    case = load_case(case_root)
    with pytest.raises(PatentError):
        channels.build_query(case, means_phrases=[case["title"]])
    with pytest.raises(PatentError):
        channels.build_query(
            case, means_phrases=["一种通过时序融合模型对家禽行为进行检测并输出报警信息的方法。"])
    with pytest.raises(PatentError):
        channels.build_query(case, ipc_codes=["不是分类号"])


def test_search_failure_typing(case_root):
    drive_to_mined(case_root)
    novelty.register_search(case_root, {
        "round": "means_phrases", "channel_id": "cnipa-epub-manual",
        "query": "IPC:G06V", "outcome": "channel_failure",
        "note": "站点不可达", "results": []})
    novelty.register_search(case_root, {
        "round": "classification_neighborhood",
        "channel_id": "cnipa-epub-manual",
        "query": "IPC:G06V10", "outcome": "zero_results", "results": []})
    summary = novelty.search_summary(case_root)
    assert len(summary["failures"]) == 1
    assert len(summary["zero_result_rounds"]) == 1
    assert summary["pool_size"] == 0


def test_search_rejects_bad_outcome(case_root):
    drive_to_mined(case_root)
    with pytest.raises(PatentError):
        novelty.register_search(case_root, {
            "round": "means_phrases", "channel_id": "cnipa-epub-manual",
            "query": "q", "outcome": "no_prior_art", "results": []})


def test_lock_d1_rejects_unverified(case_root):
    drive_to_mined(case_root)
    novelty.register_search(case_root, {
        "round": "means_phrases", "channel_id": "cnipa-epub-manual",
        "query": "q", "outcome": "ok",
        "results": [{"pub_number": "CN333333333A", "title": "t",
                     "verified": False}]})
    with pytest.raises(PatentError) as ei:
        novelty.lock_d1(case_root, {
            "pub_number": "CN333333333A", "rationale": "r",
            "evidence_level": "abstract", "gate": "pass",
            "feature_comparison": [
                {"feature_ref": "CF-02", "in_d1": False}]})
    assert "未核验" in str(ei.value)


def test_lock_d1_fk_numbering_and_gate(case_root):
    drive_to_searched(case_root)
    from light_patent.project import load_yaml_or
    d1 = load_yaml_or(case_root, "d1", None)
    assert [f["fk"] for f in d1["distinguishing_features"]] == ["F1", "F2"]
    assert d1["gate"] == "pass_with_doubts"
    assert "只作初筛底稿、不作法律意见" in d1["disclaimers"]


def test_lock_d1_fail_sets_degraded(case_root):
    drive_to_mined(case_root)
    novelty.register_search(case_root, {
        "round": "means_phrases", "channel_id": "cnipa-epub-manual",
        "query": "q", "outcome": "ok",
        "results": [{"pub_number": "CN111111111A", "title": "t",
                     "applicant": "a", "pub_date": "2023-01-01",
                     "verified": True, "evidence_level": "full_text"}]})
    novelty.lock_d1(case_root, {
        "pub_number": "CN111111111A", "rationale": "最接近",
        "evidence_level": "full_text", "gate": "fail",
        "gate_reasons": ["区别特征被 D1 与公知常识组合覆盖"],
        "feature_comparison": [
            {"feature_ref": "CF-02", "in_d1": False}]})
    case = load_case(case_root)
    assert case["degraded"]["gate_id"] == "novelty_gate_fail_degraded"
