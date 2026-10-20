"""amendment：分级签核 + 只追加 + 哈希防回改。"""

from __future__ import annotations

import pytest
from conftest import frozen_design

from light_design.gates import GateError, apply_amendment
from light_design.schema import compute_content_hash, current_frozen_hash, validate_design
from light_design.util import today


def test_amend_normal_field_auto():
    d = frozen_design()
    old_hash = current_frozen_hash(d)
    amd = apply_amendment(
        d, "plan.blocking_stratification", "按视频时长分层",
        reason="执行端反馈需要分层说明", results_seen="未跑任何运行",
        date=today())
    assert amd["user_signed"] is False
    assert amd["critical"] is False
    assert amd["new_hash"] != old_hash
    assert d["plan"]["blocking_stratification"] == "按视频时长分层"
    assert validate_design(d) == []  # 追加后哈希链自洽
    assert len(d["freeze"]["amendments"]) == 1
    assert d["freeze"]["content_hash"] != amd["new_hash"]  # 原始冻结哈希保留


def test_amend_critical_field_requires_user_signature():
    d = frozen_design()
    with pytest.raises(GateError) as e:
        apply_amendment(
            d, "evaluation.readout.positive.meaning", "放宽后的判读",
            reason="想改", results_seen="已见判别实验结果", date=today())
    assert any("命门字段" in x for x in e.value.errors)
    assert d["freeze"]["amendments"] == []  # 未落盘


def test_amend_critical_field_with_signature():
    d = frozen_design()
    amd = apply_amendment(
        d, "evaluation.readout.positive.meaning", "用户签署后的新判读",
        reason="判读措辞歧义，用户确认修订", results_seen="未跑任何运行",
        user_signed=True, by="user", date=today())
    assert amd["critical"] is True and amd["user_signed"] is True
    assert d["evaluation"]["readout"]["positive"]["meaning"] == "用户签署后的新判读"
    assert validate_design(d) == []


@pytest.mark.parametrize("field", [
    "evaluation.primary_metric.name",
    "claims.primary_claims[0].statement",
    "resources.circuit_breakers[0].threshold",
])
def test_all_critical_prefixes_enforced(field):
    d = frozen_design()
    with pytest.raises(GateError):
        apply_amendment(d, field, "x", reason="r",
                        results_seen="未跑任何运行", date=today())


def test_amend_requires_reason_and_results_seen():
    d = frozen_design()
    with pytest.raises(GateError):
        apply_amendment(d, "plan.blocking_stratification", "x",
                        reason="", results_seen="未跑", date=today())
    with pytest.raises(GateError):
        apply_amendment(d, "plan.blocking_stratification", "x",
                        reason="r", results_seen="", date=today())


def test_amend_only_for_frozen(design):
    with pytest.raises(GateError) as e:
        apply_amendment(design, "plan.blocking_stratification", "x",
                        reason="r", results_seen="未跑", date=today())
    assert any("只许对 frozen" in x for x in e.value.errors)


def test_amend_cannot_touch_freeze_zone():
    d = frozen_design()
    with pytest.raises(GateError):
        apply_amendment(d, "freeze.content_hash", "0" * 64,
                        reason="伪造哈希", results_seen="未跑", date=today())


def test_amend_chain_two_in_a_row():
    d = frozen_design()
    a1 = apply_amendment(d, "plan.blocking_stratification", "分层 A",
                         reason="r1", results_seen="未跑", date=today())
    a2 = apply_amendment(d, "handoff.alignment_gate", "对齐声明 v2",
                         reason="r2", results_seen="已见 sanity 结果", date=today())
    assert a1["new_hash"] != a2["new_hash"]
    assert current_frozen_hash(d) == a2["new_hash"]
    assert compute_content_hash(d) == a2["new_hash"]
    assert validate_design(d) == []
    assert [a["fields"] for a in d["freeze"]["amendments"]] == [
        ["plan.blocking_stratification"], ["handoff.alignment_gate"]]


def test_hand_edit_after_amend_detected():
    d = frozen_design()
    apply_amendment(d, "plan.blocking_stratification", "分层 A",
                    reason="r", results_seen="未跑", date=today())
    d["resources"]["budget"]["compute"] = "偷偷改成 300 GPU 时"
    errs = validate_design(d)
    assert any("冻结哈希不一致" in x for x in errs)


def test_amend_invalid_result_rejected_atomically():
    d = frozen_design()
    before = current_frozen_hash(d)
    with pytest.raises(GateError):
        # 把主指标名清空 → 修订后不合法，须整体拒绝、原书不动
        apply_amendment(d, "evaluation.primary_metric.name", "",
                        reason="误操作", results_seen="未跑",
                        user_signed=True, date=today())
    assert current_frozen_hash(d) == before
    assert d["freeze"]["amendments"] == []
    assert validate_design(d) == []


def test_recorded_unsigned_critical_amendment_fails_validate():
    d = frozen_design()
    # 绕过 apply_amendment 手工伪造一条无签命门 amendment
    d["freeze"]["amendments"].append({
        "date": today(), "fields": ["evaluation.readout.null.meaning"],
        "reason": "伪造", "results_seen": "已见结果", "user_signed": False,
        "new_hash": current_frozen_hash(d)})
    errs = validate_design(d)
    assert any("无用户签" in x for x in errs)
