"""状态机：全流推进 + 逐门拦截 + 旁路。"""

from __future__ import annotations

import pytest
from conftest import add_review, clone

from light_design.gates import GateError, advance
from light_design.schema import validate_design
from light_design.util import today


def test_full_flow_draft_reviewed_frozen(design):
    add_review(design)
    advance(design, "reviewed", date=today())
    assert design["status"] == "reviewed"
    advance(design, "frozen", date=today())
    assert design["status"] == "frozen"
    fr = design["freeze"]
    assert fr["frozen_at"] == today()
    assert fr["content_hash"]
    assert validate_design(design) == []  # 冻结后哈希自洽
    hist = [(h["from"], h["to"]) for h in design["status_history"]]
    assert ("draft", "reviewed") in hist and ("reviewed", "frozen") in hist


def test_skip_reviewed_blocked(design):
    with pytest.raises(GateError) as e:
        advance(design, "frozen", date=today())
    assert "非法跃迁" in str(e.value)


def test_reviewed_blocked_when_design_invalid(design):
    design["claims"]["anti_claims"] = []
    with pytest.raises(GateError) as e:
        advance(design, "reviewed", date=today())
    assert any("anti_claims" in x for x in e.value.errors)
    assert design["status"] == "draft"  # 不过门不落状态


def test_reviewed_blocked_when_intake_incomplete(design):
    design["intake"]["spec_intake"][2]["status"] = "returned"
    with pytest.raises(GateError) as e:
        advance(design, "reviewed", date=today())
    assert any("metrics" in x for x in e.value.errors)


def test_reviewed_blocked_when_intake_missing_item(design):
    design["intake"]["spec_intake"] = design["intake"]["spec_intake"][:5]
    with pytest.raises(GateError) as e:
        advance(design, "reviewed", date=today())
    assert any("key_details" in x for x in e.value.errors)


def test_reviewed_blocked_when_returned_items_unresolved(design):
    design["intake"]["returned_items"] = [{
        "item": "metrics", "reason": "交接缺惯例出处", "needed": "回补",
        "date": today(), "resolved": False}]
    with pytest.raises(GateError) as e:
        advance(design, "reviewed", date=today())
    assert any("打回项未清" in x for x in e.value.errors)


def test_frozen_blocked_without_review(design):
    advance(design, "reviewed", date=today())
    with pytest.raises(GateError) as e:
        advance(design, "frozen", date=today())
    assert any("review" in x for x in e.value.errors)


def test_frozen_blocked_review_unavailable(design):
    add_review(design, review_status="REVIEW_UNAVAILABLE")
    advance(design, "reviewed", date=today())
    with pytest.raises(GateError) as e:
        advance(design, "frozen", date=today())
    assert any("REVIEW_UNAVAILABLE" in x for x in e.value.errors)


def test_frozen_blocked_same_family_review(design):
    add_review(design, family="anthropic-claude")  # 与 designer 同族
    advance(design, "reviewed", date=today())
    with pytest.raises(GateError) as e:
        advance(design, "frozen", date=today())
    assert any("同模型家族" in x for x in e.value.errors)


def test_frozen_blocked_stage1_item_not_pass(design):
    add_review(design)
    design["freeze"]["review"]["items"]["competing_explanations"] = {
        "status": "fail", "note": "未区分竞争性解释"}
    advance(design, "reviewed", date=today())
    with pytest.raises(GateError) as e:
        advance(design, "frozen", date=today())
    assert any("competing_explanations" in x for x in e.value.errors)


def test_frozen_blocked_decision_reject(design):
    add_review(design, decision="reject")
    advance(design, "reviewed", date=today())
    with pytest.raises(GateError):
        advance(design, "frozen", date=today())


def test_frozen_is_terminal(design):
    add_review(design)
    advance(design, "reviewed", date=today())
    advance(design, "frozen", date=today())
    for to in ("draft", "reviewed", "returned", "blocked"):
        with pytest.raises(GateError):
            advance(design, to, date=today())


def test_returned_requires_missing_items(design):
    with pytest.raises(GateError) as e:
        advance(design, "returned", date=today())
    assert any("missing_items" in x for x in e.value.errors)
    design["return_record"] = {"missing_items": ["strongest_baseline"],
                                "reason": "基线只写「与 SOTA 比较」", "date": today()}
    advance(design, "returned", date=today())
    assert design["status"] == "returned"


def test_returned_back_to_draft_needs_resolved(design):
    design["return_record"] = {"missing_items": ["metrics"],
                                "reason": "缺指标", "date": today()}
    design["intake"]["returned_items"] = [{
        "item": "metrics", "reason": "缺指标", "needed": "回补",
        "date": today(), "resolved": False}]
    advance(design, "returned", date=today())
    with pytest.raises(GateError) as e:
        advance(design, "draft", date=today())
    assert any("未回补" in x for x in e.value.errors)
    design["intake"]["returned_items"][0]["resolved"] = True
    advance(design, "draft", date=today())
    assert design["status"] == "draft"


def test_blocked_requires_reason_and_unblock(design):
    with pytest.raises(GateError):
        advance(design, "blocked", date=today())
    design["block_record"] = {"reason": "数据未到位",
                               "unblock_condition": "自建 6 段视频采集完成",
                               "date": today()}
    advance(design, "blocked", date=today())
    assert design["status"] == "blocked"
    advance(design, "draft", date=today())
    assert design["status"] == "draft"


def test_minimal_can_freeze():
    from conftest import make_design
    d = add_review(make_design(tier="minimal"))
    advance(d, "reviewed", date=today())
    advance(d, "frozen", date=today())
    assert d["status"] == "frozen"


def test_frozen_hash_changes_are_detectable(design):
    d = clone(design)
    add_review(d)
    advance(d, "reviewed", date=today())
    advance(d, "frozen", date=today())
    d["evaluation"]["readout"]["positive"]["meaning"] = "手改过的判读"
    errs = validate_design(d)
    assert any("冻结哈希不一致" in x for x in errs)
