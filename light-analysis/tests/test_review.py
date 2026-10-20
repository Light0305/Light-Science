"""判定复核子流程（Phase 2）：边界行选取、同族拒、UNAVAILABLE 拦 delivered、
外部回填 schema 与异议拒收、全程贯通 delivered。"""

import json

import pytest

from conftest import do_judge
from light_analysis.conclude import run_grade
from light_analysis.gates import GateError, advance_package
from light_analysis.project import load_package, save_analysis
from light_analysis.review import (
    ReviewError, boundary_lines, import_review, prepare_review,
    record_review, record_unavailable,
)


@pytest.fixture()
def judged_pkg(checked_pkg, tmp_path):
    do_judge(checked_pkg, tmp_path)
    assert advance_package(checked_pkg) == "judged"
    return checked_pkg


def _set_analyst(root, name="analyst-x", family="fam-a"):
    pkg = load_package(root)
    pkg["analysis"]["analyst"] = {"name": name, "family": family}
    save_analysis(root, pkg["analysis"])


def test_prepare_packet_scopes_boundary_lines(judged_pkg):
    info = prepare_review(judged_pkg)
    packet = (judged_pkg / "review_packet.md").read_text(encoding="utf-8")
    assert "判定口径宪法" in packet and "全部判定摘要" in packet
    # L-PART 是 judge 落的 undetermined（边界情形）；L-OK 全票 conclusive 不入选
    assert info["scope_line_ids"] == ["L-PART"]
    picked = boundary_lines(load_package(judged_pkg))
    assert [p["registry_line_id"] for p in picked] == ["L-PART"]


def test_record_same_family_rejected(judged_pkg):
    _set_analyst(judged_pkg, family="fam-a")
    prepare_review(judged_pkg)
    with pytest.raises(ReviewError) as ei:
        record_review(judged_pkg, "reviewer-y", "fam-a")
    assert any("同族" in g for g in ei.value.gaps)
    with pytest.raises(ReviewError):
        record_review(judged_pkg, "analyst-x", "fam-b")  # 写者自审
    review = record_review(judged_pkg, "reviewer-y", "fam-b")
    assert review["receipt_id"].startswith("RV-")
    assert review["review_status"] == "approved"


def test_record_requires_prepare_and_identity(judged_pkg):
    with pytest.raises(ReviewError):
        record_review(judged_pkg, "reviewer-y", "fam-b")  # 未 prepare
    prepare_review(judged_pkg)
    with pytest.raises(ReviewError):
        record_review(judged_pkg, None, "fam-b")


def _write_import(tmp_path, decisions, reviewer="ext-z", family="fam-b",
                  extra=None):
    data = {"reviewer": reviewer, "family": family, "decisions": decisions}
    if extra:
        data.update(extra)
    p = tmp_path / "review-import.json"
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return p


def test_import_review_happy_and_schema_guards(judged_pkg, tmp_path):
    prepare_review(judged_pkg)
    good = _write_import(tmp_path, [
        {"registry_line_id": "L-PART", "agree": True, "comment": "门缺口属实"}])
    review = import_review(judged_pkg, good)
    assert review["via"] == "import"
    assert review["receipt_id"].startswith("RV-")


def test_import_review_disagree_rejected(judged_pkg, tmp_path):
    prepare_review(judged_pkg)
    bad = _write_import(tmp_path, [
        {"registry_line_id": "L-PART", "agree": False, "comment": "预警引用有误"}])
    with pytest.raises(ReviewError) as ei:
        import_review(judged_pkg, bad)
    assert any("异议" in g for g in ei.value.gaps)


def test_import_review_missing_line_and_unknown_field(judged_pkg, tmp_path):
    prepare_review(judged_pkg)
    empty = _write_import(tmp_path, [])
    with pytest.raises(ReviewError):
        import_review(judged_pkg, empty)
    extra = _write_import(tmp_path, [
        {"registry_line_id": "L-PART", "agree": True, "comment": "可"}],
        extra={"surprise": 1})
    with pytest.raises(ReviewError) as ei:
        import_review(judged_pkg, extra)
    assert any("未知字段" in g for g in ei.value.gaps)


def test_unavailable_blocks_delivered_then_recovers(judged_pkg, tmp_path):
    notes = tmp_path / "notes.json"
    notes.write_text(json.dumps({
        "boundaries": [{"claim_id": "C1", "conditions": "合成演示数据内",
                        "not_extrapolatable": "未检验行覆盖的臂",
                        "would_change_if": "补齐数据版本后重判"}],
        "limitations": ["L-PART 覆盖 n 不足，null 方向不可判"],
    }, ensure_ascii=False), encoding="utf-8")
    run_grade(judged_pkg, notes_path=notes)
    assert advance_package(judged_pkg) == "graded"
    record_unavailable(judged_pkg, reason="本环境无异家族复核者")
    with pytest.raises(GateError) as ei:
        advance_package(judged_pkg)
    assert any("REVIEW_UNAVAILABLE" in g for g in ei.value.gaps)
    analysis = load_package(judged_pkg)["analysis"]
    assert analysis["status"] == "blocked"
    # 复核恢复：prepare + 异家族 record → 从 blocked 续推 delivered
    prepare_review(judged_pkg)
    record_review(judged_pkg, "reviewer-y", "fam-b")
    assert advance_package(judged_pkg) == "delivered"
    assert (judged_pkg / "ANALYSIS_REPORT.md").exists()
