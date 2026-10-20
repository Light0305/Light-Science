"""Phase 2 · concern 回填清单导出（R6）。

只出清单不出补丁：字段白名单 + 文本上限 + severity 代码重算 +
动作分类（fixable-in-text / needs-new-evidence / needs-author-decision）。
"""
import pytest

from conftest import drive_to_reported
from light_review.handoff import classify_action, run_export
from light_review.project import FILES, load_package
from light_review.util import dump_json
from light_review.validate import validate_package


def _item(payload, cid):
    return next(i for i in payload["items"] if i["concern_id"] == cid)


def test_export_items_and_registration(review_pkg):
    drive_to_reported(review_pkg)
    payload = run_export(review_pkg)
    assert payload["kind"] == "light-review/handoff-to-write"
    assert len(payload["items"]) == 2
    c1 = _item(payload, "RV-C001")
    assert c1["severity"] == "major"          # 代码重算（MAX of major/minor）
    assert c1["source_seats"] == ["S1", "S2"]
    assert c1["consensus"] is True
    assert c1["action_class"] == "fixable-in-text"   # 双指针齐
    assert (review_pkg / FILES["handoff_md"]).exists()
    pkg = load_package(review_pkg)
    assert "handoff_to_write" not in pkg["review"]["phase2_pending"]
    assert validate_package(review_pkg) == []


def test_classify_action_matrix():
    findings = {
        "F001": {"finding_id": "F001", "layer": "conclusion_flip",
                 "status": "confirmed_error", "category": "confirmed_error"},
        "F002": {"finding_id": "F002", "layer": "numbers_numbers",
                 "status": "inconsistency", "category": "inconsistency"},
    }
    both = {"claim_pointer": "claims_register:C1",
            "evidence_pointer": "conclusions:C1"}
    assert classify_action({"pointers": both}, findings)[0] \
        == "fixable-in-text"
    flip = {"claim_pointer": None, "evidence_pointer": "forensic:F001"}
    assert classify_action({"pointers": flip}, findings)[0] \
        == "needs-new-evidence"
    plain = {"claim_pointer": None, "evidence_pointer": "forensic:F002"}
    assert classify_action({"pointers": plain}, findings)[0] \
        == "fixable-in-text"
    ev_only = {"claim_pointer": None, "evidence_pointer": "conclusions:C1"}
    assert classify_action({"pointers": ev_only}, findings)[0] \
        == "needs-new-evidence"
    claim_only = {"claim_pointer": "claims_register:C1",
                  "evidence_pointer": None}
    assert classify_action({"pointers": claim_only}, findings)[0] \
        == "fixable-in-text"
    none = {"claim_pointer": None, "evidence_pointer": None}
    assert classify_action({"pointers": none}, findings)[0] \
        == "needs-author-decision"
    assert classify_action({}, findings)[0] == "needs-author-decision"


def test_export_whitelist_violation_rejected(review_pkg):
    """手往导出物里塞补丁字段 → 校验器咬（只出清单不出补丁）。"""
    drive_to_reported(review_pkg)
    run_export(review_pkg)
    path = review_pkg / FILES["handoff_json"]
    payload = load_package(review_pkg)["handoff_json"]
    payload["items"][0]["patch_text"] = "把第三段改成……"
    dump_json(path, payload)
    errors = validate_package(review_pkg)
    assert any("白名单" in e for e in errors)


def test_export_long_text_rejected(review_pkg):
    drive_to_reported(review_pkg)
    run_export(review_pkg)
    path = review_pkg / FILES["handoff_json"]
    payload = load_package(review_pkg)["handoff_json"]
    payload["items"][0]["statement"] = "长" * 600
    dump_json(path, payload)
    errors = validate_package(review_pkg)
    assert any("只出清单不出补丁" in e for e in errors)


def test_export_severity_tamper_rejected(review_pkg):
    """导出物 severity 被手改 → 与代码重算不符，校验器咬。"""
    drive_to_reported(review_pkg)
    run_export(review_pkg)
    path = review_pkg / FILES["handoff_json"]
    payload = load_package(review_pkg)["handoff_json"]
    payload["items"][0]["severity"] = "minor"     # RV-C001 实为 major
    dump_json(path, payload)
    errors = validate_package(review_pkg)
    assert any("代码重算" in e for e in errors)
