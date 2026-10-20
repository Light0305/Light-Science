"""DES-D02：amendment 增量评审命令化 + 类别分流（C-补04）。

覆盖：命门 amendment 全程（待审 → 开包 → 落盘 → 导出放行）、待审/
驳回拦导出、非命门不触发、REVIEW_UNAVAILABLE 显式落字、同族拒收、
预写分支类别与影响面不符点名拒绝、轻评审两项、全评审只审子集。
"""

from __future__ import annotations

import json

import pytest
import yaml
from conftest import add_review, frozen_design, make_design

from light_design.export import ExportError, export_design
from light_design.gates import GateError, advance, apply_amendment
from light_design.project import save_design
from light_design.review import (
    LIGHT_REVIEW_ITEMS,
    ReviewError,
    prepare_amendment_review,
    record_amendment_review,
    record_amendment_review_unavailable,
)
from light_design.schema import validate_design
from light_design.util import today

DID = "design_test_abc123"
READOUT_FIELD = "evaluation.readout.positive.meaning"


def _critical_amd(d, **kw):
    kw.setdefault("user_signed", True)
    kw.setdefault("by", "user")
    return apply_amendment(
        d, READOUT_FIELD, "用户签署后的新判读（增量评审对象）",
        reason="判读措辞歧义，用户确认修订", results_seen="未跑任何运行",
        date=today(), **kw)


def _items(*names, verdict="pass"):
    return {n: {"verdict": verdict, "note": "逐项核对，依据充分"}
            for n in names}


def _data(items, **over):
    data = {"reviewer_model": "gpt-reviewer",
            "reviewer_family": "openai-gpt",
            "decision": "pass", "items": items}
    data.update(over)
    return data


# ---------- 全程：待审 → 开包 → 落盘 → 放行 ----------

def test_critical_amendment_full_flow(project):
    d = frozen_design()
    amd = _critical_amd(d)
    # 落盘即待审 + 前后值在案 + 类别默认 unforeseen（最严口径）
    assert amd["review"]["status"] == "pending_review"
    assert amd["review"]["track"] == "full"
    assert amd["category"] == "unforeseen"
    assert amd["changes"][0]["field"] == READOUT_FIELD
    assert "留出 MOTA 达神谕 98%" in amd["changes"][0]["before"]
    assert amd["changes"][0]["after"].startswith("用户签署后的新判读")
    save_design(project, d)
    # 待审时导出被拦并点名
    with pytest.raises(ExportError) as e:
        export_design(project, d)
    assert any("amendment #1" in x and "增量评审" in x
               for x in e.value.errors)
    # 开包：影响面 = readout 圈定的登记行全行 + analysis_predetermined
    out = prepare_amendment_review(project, d, 1, date=today())
    assert out["track"] == "full"
    assert out["items_required"] == ["analysis_predetermined"]
    packet = out["packet"].read_text(encoding="utf-8")
    assert "变更前" in packet and "用户签署后的新判读" in packet
    assert "R-CTRL" in packet  # 受影响登记行（夹具登记表仅 R-CTRL 一行）
    # 原冻结评审收据指针在包内
    assert (d["freeze"]["review"].get("review_id") or "review_id") in packet \
        or "RV-" in packet
    checklist = yaml.safe_load(out["checklist"].read_text(encoding="utf-8"))
    assert set(checklist["items"]) == {"analysis_predetermined"}
    # 落盘 pass → 导出放行
    rec = record_amendment_review(
        project, d, 1, _data(_items("analysis_predetermined")), date=today())
    assert rec["status"] == "passed"
    assert d["freeze"]["amendments"][0]["review"]["status"] == "passed"
    stub = project / "review" / DID / "amendments" / "amd-1" / \
        "amendment_review_record.json"
    assert json.loads(stub.read_text(encoding="utf-8"))["review_id"] == \
        rec["review_id"]
    save_design(project, d)
    out = export_design(project, d)
    assert out["expected_registry"].exists()
    assert validate_design(d) == []  # 评审子记录不破坏哈希链/合法性


def test_record_requires_prepare_first(project):
    d = frozen_design()
    _critical_amd(d)
    save_design(project, d)
    with pytest.raises(ReviewError) as e:
        record_amendment_review(
            project, d, 1, _data(_items("analysis_predetermined")),
            date=today())
    assert any("先跑 review prepare" in x for x in e.value.errors)


def test_reject_decision_still_blocks_export(project):
    d = frozen_design()
    _critical_amd(d)
    save_design(project, d)
    prepare_amendment_review(project, d, 1, date=today())
    rec = record_amendment_review(
        project, d, 1,
        _data(_items("analysis_predetermined", verdict="fail"),
              decision="reject"),
        date=today())
    assert rec["status"] == "rejected"
    save_design(project, d)
    with pytest.raises(ExportError) as e:
        export_design(project, d)
    assert any("reject" in x for x in e.value.errors)


def test_record_rejects_inconsistent_and_missing(project):
    d = frozen_design()
    _critical_amd(d)
    save_design(project, d)
    prepare_amendment_review(project, d, 1, date=today())
    # 缺项
    with pytest.raises(ReviewError):
        record_amendment_review(project, d, 1, _data({}), date=today())
    # 决议与逐项矛盾
    with pytest.raises(ReviewError):
        record_amendment_review(
            project, d, 1,
            _data(_items("analysis_predetermined", verdict="fail")),
            date=today())
    # 无注
    with pytest.raises(ReviewError):
        record_amendment_review(
            project, d, 1,
            _data({"analysis_predetermined": {"verdict": "pass",
                                              "note": ""}}),
            date=today())


def test_record_same_family_rejected(project):
    d = frozen_design()
    _critical_amd(d)
    save_design(project, d)
    prepare_amendment_review(project, d, 1, date=today())
    with pytest.raises(ReviewError) as e:
        record_amendment_review(
            project, d, 1,
            _data(_items("analysis_predetermined"),
                  reviewer_family="anthropic-claude"),
            date=today())
    assert any("同模型家族" in x for x in e.value.errors)


# ---------- 非命门不触发 ----------

def test_noncritical_amendment_not_reviewed(project):
    d = frozen_design()
    amd = apply_amendment(d, "plan.blocking_stratification", "按时长分层",
                          reason="补充分层", results_seen="未跑任何运行",
                          date=today())
    assert amd["review"]["status"] == "not_required"
    save_design(project, d)
    with pytest.raises(ReviewError) as e:
        prepare_amendment_review(project, d, 1, date=today())
    assert any("不触发增量评审" in x for x in e.value.errors)
    out = export_design(project, d)  # 导出不受影响
    assert out["expected_registry"].exists()


# ---------- REVIEW_UNAVAILABLE 显式落字 ----------

def test_review_unavailable_path(project):
    d = frozen_design()
    _critical_amd(d)
    save_design(project, d)
    rec = record_amendment_review_unavailable(project, d, 1, date=today())
    assert rec["status"] == "unavailable_noted"
    save_design(project, d)
    out = export_design(project, d)  # 放行
    brief = out["brief"].read_text(encoding="utf-8")
    repro = out["reproducibility"].read_text(encoding="utf-8")
    assert "增量评审未完成" in brief  # 导出件注明
    assert "增量评审注记" in repro and "REVIEW_UNAVAILABLE" in repro
    # 恢复后可重新开包补审并覆盖降级记录
    out2 = prepare_amendment_review(project, d, 1, date=today())
    assert out2["items_required"] == ["analysis_predetermined"]
    rec2 = record_amendment_review(
        project, d, 1, _data(_items("analysis_predetermined")), date=today())
    assert rec2["status"] == "passed"


# ---------- 类别分流（C-补04） ----------

def _frozen_with_branch():
    d = make_design()
    d["plan"]["deviation_branches"] = [{
        "id": "BR-NULL-EXPAND",
        "trigger": "判读落 null（判别力不足）",
        "fields": ["resources.budget"],
        "fallback": "按预写把评估集规模 6 段扩到 10 段，预算随之调整",
    }]
    add_review(d)
    advance(d, "reviewed", date=today())
    advance(d, "frozen", date=today())
    return d


def test_prewritten_branch_requires_ref():
    d = _frozen_with_branch()
    with pytest.raises(GateError) as e:
        apply_amendment(d, "resources.budget.compute", "45 GPU 时",
                        reason="触发预写分支", results_seen="已见判别结果",
                        category="prewritten_branch", date=today())
    assert any("branch_ref" in x for x in e.value.errors)
    assert d["freeze"]["amendments"] == []


def test_prewritten_branch_unknown_ref_named():
    d = _frozen_with_branch()
    with pytest.raises(GateError) as e:
        apply_amendment(d, "resources.budget.compute", "45 GPU 时",
                        reason="触发预写分支", results_seen="已见判别结果",
                        category="prewritten_branch", branch_ref="BR-NOPE",
                        date=today())
    assert any("不存在" in x and "类别与影响面不符" in x
               for x in e.value.errors)


def test_prewritten_branch_out_of_scope_named():
    d = _frozen_with_branch()
    with pytest.raises(GateError) as e:
        apply_amendment(d, "plan.blocking_stratification", "x",
                        reason="借分支改别的", results_seen="已见判别结果",
                        category="prewritten_branch",
                        branch_ref="BR-NULL-EXPAND", date=today())
    assert any("不在预写分支" in x and "影响面" in x for x in e.value.errors)


def test_prewritten_branch_light_track(project):
    d = make_design()
    d["plan"]["deviation_branches"] = [{
        "id": "BR-READOUT-FALLBACK",
        "trigger": "判别实验显示原判读措辞在段级不可执行",
        "fields": ["evaluation.readout"],
        "fallback": "判读正向 meaning 改用预写备援表述",
    }]
    add_review(d)
    advance(d, "reviewed", date=today())
    advance(d, "frozen", date=today())
    amd = apply_amendment(
        d, READOUT_FIELD, "预写备援判读表述",
        reason="触发 BR-READOUT-FALLBACK", results_seen="已见判别实验结果",
        user_signed=True, category="prewritten_branch",
        branch_ref="BR-READOUT-FALLBACK", date=today())
    assert amd["category"] == "prewritten_branch"
    assert amd["branch_ref"] == "BR-READOUT-FALLBACK"
    assert amd["review"] == {"status": "pending_review", "track": "light"}
    assert validate_design(d) == []
    save_design(project, d)
    out = prepare_amendment_review(project, d, 1, date=today())
    assert out["track"] == "light"
    assert out["items_required"] == list(LIGHT_REVIEW_ITEMS)
    packet = out["packet"].read_text(encoding="utf-8")
    assert "BR-READOUT-FALLBACK" in packet and "触发条件" in packet
    # 轻评审只认两项：缺 fallback 项被拒，两项齐 + pass 落盘
    with pytest.raises(ReviewError):
        record_amendment_review(
            project, d, 1, _data(_items("trigger_verified")), date=today())
    rec = record_amendment_review(
        project, d, 1, _data(_items(*LIGHT_REVIEW_ITEMS)), date=today())
    assert rec["status"] == "passed" and rec["track"] == "light"
    save_design(project, d)
    assert export_design(project, d)["expected_registry"].exists()


def test_invalid_category_rejected():
    d = frozen_design()
    with pytest.raises(GateError):
        _critical_amd(d, category="whatever")
    assert d["freeze"]["amendments"] == []


def test_critical_amendment_still_needs_user_signature():
    # 既有纪律不放松：DES-D02 不改变命门用户签
    d = frozen_design()
    with pytest.raises(GateError):
        apply_amendment(d, READOUT_FIELD, "无签改判读",
                        reason="r", results_seen="未跑", date=today())
    assert d["freeze"]["amendments"] == []


def test_sesoi_amendment_items_subset(project):
    # SESOI（命门）增量评审圈定 methodological + analysis 两条，
    # 不重开其余三条（只审影响面）
    d = frozen_design()
    amd = apply_amendment(
        d, "evaluation.sesoi.value", 2.5,
        reason="SESOI 依据更新", results_seen="未跑任何运行",
        user_signed=True, date=today())
    assert amd["review"]["track"] == "full"
    save_design(project, d)
    out = prepare_amendment_review(project, d, 1, date=today())
    assert out["items_required"] == ["methodological_soundness",
                                     "analysis_predetermined"]


def test_prepare_out_of_range(project):
    d = frozen_design()
    save_design(project, d)
    with pytest.raises(ReviewError):
        prepare_amendment_review(project, d, 3, date=today())
