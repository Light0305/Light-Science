"""状态机门：每条门的正/反例。"""

import pytest
from conftest import full_card
from light_idea.gates import GateError, advance, check_transition


def adv(card, to, **kw):
    return advance(card, to, by="test", date="2026-10-20", **kw)


# ---------- screened ----------

def test_draft_to_screened_ok():
    c = full_card("draft")
    adv(c, "screened")
    assert c["status"] == "screened"
    assert c["status_history"][-1]["to"] == "screened"


def test_screened_blocks_unchecked_dedup():
    c = full_card("draft")
    c["dedup"]["checked"] = False
    errs = check_transition(c, "screened")
    assert any("去重" in e for e in errs)


def test_screened_blocks_duplicate_adjudication():
    c = full_card("draft")
    c["dedup"]["adjudication"] = "duplicate"
    assert any("重复" in e for e in check_transition(c, "screened"))


def test_screened_blocks_infeasible():
    c = full_card("draft")
    c["feasibility"]["compute_within_budget"] = False
    assert any("compute_within_budget" in e for e in check_transition(c, "screened"))
    c2 = full_card("draft")
    c2["feasibility"]["data_note"] = ""
    assert any("data_note" in e for e in check_transition(c2, "screened"))


def test_no_skipping_states():
    c = full_card("draft")
    with pytest.raises(GateError):
        adv(c, "finalized_executable")
    assert c["status"] == "draft"  # 失败不改状态


# ---------- novelty_checked ----------

def test_screened_to_novelty_ok():
    c = full_card("screened")
    adv(c, "novelty_checked")
    assert c["status"] == "novelty_checked"


def test_novelty_blocks_missing_scope():
    c = full_card("screened")
    c["novelty"]["search_scope"]["sources"] = []
    assert any("检索范围" in e for e in check_transition(c, "novelty_checked"))


def test_novelty_blocks_abandon():
    c = full_card("screened")
    c["novelty"]["verdict"] = "ABANDON"
    assert any("ABANDON" in e for e in check_transition(c, "novelty_checked"))


def test_novelty_blocks_missing_checked_at():
    c = full_card("screened")
    c["novelty"]["checked_at"] = None
    assert any("checked_at" in e for e in check_transition(c, "novelty_checked"))


# ---------- pre_mortem_passed ----------

def test_novelty_to_pre_mortem_ok():
    c = full_card("novelty_checked")
    adv(c, "pre_mortem_passed")
    assert c["status"] == "pre_mortem_passed"


def test_pre_mortem_blocks_open_items():
    c = full_card("novelty_checked")
    c["pre_mortem"]["open_items"] = ["基线攻击未回应"]
    assert any("open_items" in e for e in check_transition(c, "pre_mortem_passed"))


def test_pre_mortem_blocks_unfinished_checklist():
    c = full_card("novelty_checked")
    c["pre_mortem"]["checklist"]["method_instantiable"] = {"status": "pending", "note": ""}
    assert any("method_instantiable" in e for e in check_transition(c, "pre_mortem_passed"))


def test_pre_mortem_na_needs_reason():
    c = full_card("novelty_checked")
    c["pre_mortem"]["checklist"]["ablations_complete"] = {"status": "na", "note": ""}
    assert any("na" in e for e in check_transition(c, "pre_mortem_passed"))
    c["pre_mortem"]["checklist"]["ablations_complete"] = {
        "status": "na", "note": "理论型想法，无消融对象"}
    assert check_transition(c, "pre_mortem_passed") == []


def test_pre_mortem_blocks_missing_experiment():
    c = full_card("novelty_checked")
    c["exec_spec"]["discriminating_experiment"] = None
    assert any("判别实验" in e for e in check_transition(c, "pre_mortem_passed"))


def test_pre_mortem_blocks_missing_objection():
    c = full_card("novelty_checked")
    c["negative"]["strongest_objection"] = ""
    assert any("strongest_objection" in e for e in check_transition(c, "pre_mortem_passed"))


def test_pre_mortem_missing_record():
    c = full_card("novelty_checked")
    c["pre_mortem"] = None
    assert any("pre_mortem 记录不存在" in e
               for e in check_transition(c, "pre_mortem_passed"))


# ---------- finalized_executable ----------

def test_finalize_executable_ok():
    c = full_card("pre_mortem_passed")
    adv(c, "finalized_executable")
    assert c["status"] == "finalized_executable"
    assert c["finalization_level"] == "executable"


def test_finalize_blocks_each_missing_exec_item():
    for item in ("datasets", "strongest_baseline", "metrics",
                 "ablations", "resource_budget", "key_details"):
        c = full_card("pre_mortem_passed")
        c["exec_spec"][item] = [] if isinstance(c["exec_spec"][item], list) else None
        errs = check_transition(c, "finalized_executable")
        assert any(item in e for e in errs), f"缺 {item} 时应报错，实际：{errs}"


def test_finalize_blocks_vague_baseline():
    c = full_card("pre_mortem_passed")
    c["exec_spec"]["strongest_baseline"] = "与 SOTA 比较"
    assert any("strongest_baseline" in e
               for e in check_transition(c, "finalized_executable"))


def test_finalize_blocks_same_family_receipt():
    c = full_card("pre_mortem_passed")
    c["novelty"]["receipt"]["judge_model"] = "claude-sonnet"
    c["novelty"]["receipt"]["judge_family"] = "anthropic"
    assert any("同属一个模型家族" in e
               for e in check_transition(c, "finalized_executable"))


def test_finalize_blocks_review_unavailable():
    c = full_card("pre_mortem_passed")
    c["novelty"]["review_status"] = "REVIEW_UNAVAILABLE"
    assert any("REVIEW_UNAVAILABLE" in e
               for e in check_transition(c, "finalized_executable"))


def test_finalize_blocks_unverified_closest_work():
    c = full_card("pre_mortem_passed")
    c["novelty"]["closest_works"][0]["verified"] = False
    assert any("未过 Literature 核实口径" in e
               for e in check_transition(c, "finalized_executable"))


def test_finalize_blocks_caution_without_reason():
    c = full_card("pre_mortem_passed")
    c["novelty"]["verdict"] = "PROCEED_WITH_CAUTION"
    c["novelty"]["caution_reason"] = ""
    assert any("caution_reason" in e
               for e in check_transition(c, "finalized_executable"))


def test_finalize_blocks_negative_pilot():
    c = full_card("pre_mortem_passed")
    c["pilot"]["status"] = "negative"
    assert any("试点为负信号" in e
               for e in check_transition(c, "finalized_executable"))


# ---------- finalized_conceptual ----------

def test_finalize_conceptual_ok_with_incomplete_exec():
    c = full_card("pre_mortem_passed")
    c["exec_spec"]["ablations"] = []  # 执行规格未齐
    c["finalization_level"] = "conceptual"  # 卡面显式标注
    adv(c, "finalized_conceptual")
    assert c["status"] == "finalized_conceptual"


def test_finalize_conceptual_requires_explicit_mark():
    c = full_card("pre_mortem_passed")
    c["exec_spec"]["ablations"] = []
    errs = check_transition(c, "finalized_conceptual")
    assert any("conceptual" in e for e in errs)


def test_finalize_conceptual_still_needs_receipt():
    c = full_card("pre_mortem_passed")
    c["finalization_level"] = "conceptual"
    c["novelty"]["receipt"]["verdict_id"] = None
    assert any("verdict_id" in e
               for e in check_transition(c, "finalized_conceptual"))


# ---------- killed ----------

def _killable(status="screened"):
    c = full_card(status)
    c["kill"] = {
        "reason": "撞车：已有论文包含该机制",
        "date": "2026-10-20",
        "source": "novelty_named_paper",
        "failure_class": "fundamental",
        "root_cause": "机制增量已被在先工作覆盖",
        "boundary_conditions": "若出现新的田间域数据分布，或许可行",
        "named_paper": {"paper_id": "mae-plant_999fff"},
    }
    return c


def test_kill_ok():
    c = _killable()
    adv(c, "killed")
    assert c["status"] == "killed"


def test_kill_requires_failure_class():
    c = _killable()
    c["kill"]["failure_class"] = None
    assert any("failure_class" in e for e in check_transition(c, "killed"))


def test_kill_fundamental_requires_boundary():
    c = _killable()
    c["kill"]["boundary_conditions"] = ""
    assert any("boundary_conditions" in e for e in check_transition(c, "killed"))


def test_kill_implementation_requires_retry_guidance():
    c = _killable()
    c["kill"].update({"failure_class": "implementation", "source": "pre_mortem",
                      "retry_guidance": "", "named_paper": None})
    assert any("retry_guidance" in e for e in check_transition(c, "killed"))
    c["kill"]["retry_guidance"] = "换更强的骨干网络后重试"
    assert check_transition(c, "killed") == []


def test_kill_by_novelty_must_name_paper():
    c = _killable()
    c["kill"]["named_paper"] = {"title": "某论文"}  # 无 id/doi = 没点名
    assert any("点名" in e for e in check_transition(c, "killed"))


def test_kill_from_finalized_blocked():
    c = _killable("finalized_executable")
    assert any("不许再转入" in e for e in check_transition(c, "killed"))


# ---------- parked / 复活 ----------

def test_park_ok_and_revive():
    c = full_card("screened")
    c["park"] = {"reason": "等田间集 v2 发布", "revival_condition": "数据集开放下载",
                  "date": "2026-10-20"}
    adv(c, "parked")
    assert c["status"] == "parked"
    adv(c, "draft")
    assert c["status"] == "draft"


def test_park_requires_revival_condition():
    c = full_card("screened")
    c["park"] = {"reason": "先放放", "revival_condition": ""}
    assert any("revival_condition" in e for e in check_transition(c, "parked"))
