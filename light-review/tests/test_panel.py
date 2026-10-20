"""席位与冻结：可见性强制、冻结防篡改、共识门与佐证不抬级（RV-01/05/12）。"""

from pathlib import Path

import pytest

from conftest import drive_panel
from light_review.panel import (
    PanelError, VisibilityError, build_consensus, freeze_reports,
    read_for_seat, register_seat, verify_frozen, write_draft,
)
from light_review.project import load_package, save_review


def _draft(root, sid, text="# 草稿\n"):
    src = Path(root) / f"src-{sid}.md"
    src.write_text(text, encoding="utf-8")
    return write_draft(root, sid, src)


# ---------------------------------------------------------------- 可见性

def test_panel_stage_blinds_other_seats(review_pkg):
    register_seat(review_pkg, "S1", "methods", "claude")
    register_seat(review_pkg, "S2", "domain", "gpt")
    _draft(review_pkg, "S1")
    _draft(review_pkg, "S2")
    # panel 阶段：读他人草稿被数据模型拒
    with pytest.raises(VisibilityError):
        read_for_seat(review_pkg, "S1",
                      review_pkg / "reports" / "drafts" / "S2.md")
    # 读自己的草稿、读稿件物料：放行
    own = read_for_seat(review_pkg, "S1",
                        review_pkg / "reports" / "drafts" / "S1.md")
    assert own == "# 草稿\n"
    manuscript = load_package(review_pkg)["review"]["intake"]["manuscript"]
    text = read_for_seat(review_pkg, "S1",
                         Path(manuscript["package_path"]) / "manuscript.yaml")
    assert "demo-manuscript" in text


def test_custom_visibility_cannot_unblind_panel(review_pkg):
    with pytest.raises(PanelError):
        register_seat(review_pkg, "S1", "methods", "claude", visibility={
            "panel": ["manuscript", "other_reports"]})


def test_duplicate_seat_rejected(review_pkg):
    register_seat(review_pkg, "S1", "methods", "claude")
    with pytest.raises(PanelError):
        register_seat(review_pkg, "S1", "domain", "gpt")


def test_reported_stage_allows_reading_frozen_reports(review_pkg):
    drive_panel(review_pkg)
    freeze_reports(review_pkg)
    review = load_package(review_pkg)["review"]
    review["status"] = "reported"  # 仅为测可见性阶段映射
    save_review(review_pkg, review)
    text = read_for_seat(review_pkg, "S1",
                         review_pkg / "reports" / "S2.md")
    assert "S2" in text


# ---------------------------------------------------------------- 冻结

def test_freeze_pins_hash_and_tamper_is_stale(review_pkg):
    drive_panel(review_pkg)
    records = freeze_reports(review_pkg)
    assert {r["seat_id"] for r in records} == {"S1", "S2"}
    assert verify_frozen(review_pkg) == []
    frozen = review_pkg / "reports" / "S1.md"
    frozen.write_text(frozen.read_text(encoding="utf-8") + "事后改动\n",
                      encoding="utf-8")
    stale = verify_frozen(review_pkg)
    assert stale and "STALE" in stale[0]


def test_freeze_is_append_only(review_pkg):
    drive_panel(review_pkg)
    freeze_reports(review_pkg)
    with pytest.raises(PanelError):
        freeze_reports(review_pkg)


def test_freeze_requires_all_drafts(review_pkg):
    register_seat(review_pkg, "S1", "methods", "claude")
    register_seat(review_pkg, "S2", "domain", "gpt")
    _draft(review_pkg, "S1")
    with pytest.raises(PanelError) as ei:
        freeze_reports(review_pkg)
    assert any("S2" in g for g in ei.value.gaps)


def test_frozen_seat_cannot_redraft(review_pkg):
    drive_panel(review_pkg)
    freeze_reports(review_pkg)
    with pytest.raises(PanelError):
        _draft(review_pkg, "S1", "# 改稿\n")


# ---------------------------------------------------------------- 共识门

def _concern(raised_by, proposals, **kw):
    row = {"concern_id": "RV-C001", "statement": "方法节缺关键参数",
           "raised_by": raised_by, "severity_proposals": proposals}
    row.update(kw)
    return row


def test_consensus_two_independent_seats(review_pkg):
    drive_panel(review_pkg)
    freeze_reports(review_pkg)
    out = build_consensus(review_pkg, [
        _concern(["S1", "S2"], {"S1": "major", "S2": "minor"})])
    row = out["concerns"][0]
    assert row["consensus"] is True
    assert row["tally"] == 2
    assert row["severity"] == "major"  # 代码取 MAX


def test_consensus_single_seat_cannot_claim_consensus(review_pkg):
    drive_panel(review_pkg)
    freeze_reports(review_pkg)
    with pytest.raises(PanelError):
        build_consensus(review_pkg, [
            _concern(["S1"], {"S1": "major"}, consensus=True)])
    # 单席 concern 本身可登记，但 consensus 恒为假
    out = build_consensus(review_pkg, [
        _concern(["S1"], {"S1": "major"})])
    assert out["concerns"][0]["consensus"] is False


def test_corroboration_never_lifts_severity(review_pkg):
    drive_panel(review_pkg)
    freeze_reports(review_pkg)
    # 两席都只提 minor：手填 major（借佐证抬级）被落盘口拒绝
    with pytest.raises(PanelError):
        build_consensus(review_pkg, [
            _concern(["S1", "S2"], {"S1": "minor", "S2": "minor"},
                     severity="major")])
    out = build_consensus(review_pkg, [
        _concern(["S1", "S2"], {"S1": "minor", "S2": "minor"})])
    assert out["concerns"][0]["severity"] == "minor"


def test_closed_concern_requires_reason(review_pkg):
    drive_panel(review_pkg)
    freeze_reports(review_pkg)
    with pytest.raises(PanelError):
        build_consensus(review_pkg, [
            _concern(["S1"], {"S1": "minor"}, status="closed")])
    out = build_consensus(review_pkg, [
        _concern(["S1"], {"S1": "minor"}, status="closed",
                 close_reason="作者已在修订说明中澄清")])
    assert out["concerns"][0]["status"] == "closed"
