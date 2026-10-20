"""P3 撰写 + P4 审核：三箱分拣、支持纪律、引用规则、剥离洁净、
检查器咬合、红队缺位封顶、交付分级。"""

import pytest

from light_patent import check, draft
from light_patent.project import PatentError, load_yaml_or

from conftest import claims_payload, drive_to_drafted, drive_to_searched


def _redteam_payload():
    return {
        "claims_team": {"checked": ["新颖性", "创造性", "客体"],
                        "not_checked": [], "findings": []},
        "package_team": {"checked": ["跨文件一致性", "哈希时序"],
                         "not_checked": [], "findings": []},
    }


def test_claims_registration_and_fee(case_root):
    drive_to_searched(case_root)
    result = draft.register_claims(case_root, claims_payload())
    assert result["claims"] == 4
    assert result["extra_fee_claims"] == 0


def test_claim1_rejects_embodiment_box(case_root):
    drive_to_searched(case_root)
    payload = claims_payload()
    payload["claims"][0]["features"][0]["box"] = "embodiment_choice"
    with pytest.raises(PatentError) as ei:
        draft.register_claims(case_root, payload)
    assert "独权" in str(ei.value)


def test_claims_reject_unsupported_feature(case_root):
    drive_to_searched(case_root)
    payload = claims_payload()
    payload["claims"][1]["features"][0]["support"]["state"] = "unsupported"
    with pytest.raises(PatentError) as ei:
        draft.register_claims(case_root, payload)
    assert "unsupported" in str(ei.value)


def test_claims_reject_forward_reference(case_root):
    drive_to_searched(case_root)
    payload = claims_payload()
    payload["claims"][1]["depends_on"] = [3]
    with pytest.raises(PatentError):
        draft.register_claims(case_root, payload)


def test_support_map_rows_match_features(case_root, tmp_path):
    drive_to_drafted(case_root, tmp_path)
    support = load_yaml_or(case_root, "support_map", {})
    assert len(support["rows"]) == 8


def test_strip_filing_is_clean(case_root, tmp_path):
    drive_to_drafted(case_root, tmp_path)
    result = draft.strip_filing(case_root)
    assert result["files"] == 3
    assert result["unclean"] == []


def test_strip_flags_process_in_body(case_root, tmp_path):
    drive_to_drafted(case_root, tmp_path)
    from light_patent.project import case_path
    from light_patent.util import read_text
    spec = case_path(case_root, "specification_md")
    spec.write_text(read_text(spec).replace(
        "## 背景技术", "## 背景技术\n查新过程另记一笔。", 1),
        encoding="utf-8")
    result = draft.strip_filing(case_root)
    assert "specification.md" in result["unclean"]


def test_check_clean_with_redteam(case_root, tmp_path):
    drive_to_drafted(case_root, tmp_path)
    draft.strip_filing(case_root)
    check.register_redteam(case_root, _redteam_payload())
    report = check.run_check(case_root)
    assert report["errors"] == 0, report["findings"]
    assert report["delivery_grade"] == "deliverable_draft"


def test_check_without_redteam_caps_grade(case_root, tmp_path):
    drive_to_drafted(case_root, tmp_path)
    report = check.run_check(case_root)
    assert report["delivery_grade"] == "incomplete_draft"
    assert report["redteam_present"] is False


def test_check_bites_uncertain_word(case_root, tmp_path):
    drive_to_searched(case_root)
    payload = claims_payload()
    payload["claims"][1]["features"][0]["text"] = \
        "时序聚合模块优选采用滑动窗口注意力对视频帧序列进行加权聚合"
    draft.register_claims(case_root, payload)
    report = check.run_check(case_root)
    hits = [f for f in report["findings"] if f["check_id"] == "C-03"]
    assert hits and "优选" in hits[0]["detail"]
    assert report["delivery_grade"] == "incomplete_draft"


def test_check_bites_multi_reference(case_root):
    drive_to_searched(case_root)
    payload = claims_payload()
    payload["claims"].append(
        {"claim_no": 5, "type": "method", "depends_on": [1, 2],
         "preamble": "根据权利要求1或2所述的方法，其特征在于：",
         "features": [{"feature_ref": "CF-09", "box": "embodiment_choice",
                       "text": "报警信息通过声光装置输出",
                       "support": {"state": "explicit", "anchors": ["P001"],
                                   "spec_section": "具体实施方式"}}]})
    payload["claims"].append(
        {"claim_no": 6, "type": "method", "depends_on": [2, 5],
         "preamble": "根据权利要求2或5所述的方法，其特征在于：",
         "features": [{"feature_ref": "CF-10", "box": "embodiment_choice",
                       "text": "报警信息同步推送至管理终端",
                       "support": {"state": "explicit", "anchors": ["P001"],
                                   "spec_section": "具体实施方式"}}]})
    draft.register_claims(case_root, payload)
    report = check.run_check(case_root)
    hits = [f for f in report["findings"] if f["check_id"] == "C-04"]
    assert hits


def test_check_ai_sufficiency_missing(case_root, tmp_path):
    drive_to_searched(case_root)
    payload = claims_payload()
    payload["ai_sufficiency"] = {"items": ["model_modules"]}
    draft.register_claims(case_root, payload)
    report = check.run_check(case_root)
    hits = [f for f in report["findings"] if f["check_id"] == "C-11"]
    assert len(hits) == 4


def test_check_abstract_over_limit(case_root, tmp_path):
    drive_to_drafted(case_root, tmp_path)
    from light_patent.project import case_path
    case_path(case_root, "abstract_md").write_text(
        "# 说明书摘要\n\n" + "长" * 320, encoding="utf-8")
    report = check.run_check(case_root)
    hits = [f for f in report["findings"] if f["check_id"] == "C-07"]
    assert hits and hits[0]["level"] == "ERROR"
