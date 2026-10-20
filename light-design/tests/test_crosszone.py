"""DES-D04：intake expanded 跨区实体核查——只改状态字、不落实体的
承接造假必须被校验器逐项点名；实体齐备的 expanded 全过；
accepted 不触发本核查（既有行为不变）。"""

from __future__ import annotations

import pytest
from conftest import clone, make_design

from light_design.schema import validate_design


def _set_status(d: dict, item: str, status: str) -> None:
    for s in d["intake"]["spec_intake"]:
        if s["item"] == item:
            s["status"] = status


def _d04_errors(d: dict, item: str) -> list[str]:
    return [e for e in validate_design(d)
            if "DES-D04" in e and f"承接 {item} " in e]


# 六项「只改状态字」反例：逐项必红且点名
REMOVERS = {
    "datasets": lambda d: (d["plan"].update({"variables": []}),
                           d["evaluation"].update({"data_protocol": None})),
    "strongest_baseline": lambda d: d["contract"]["controls"][0]
    .update({"status_quo": False}),
    "metrics": lambda d: d["evaluation"].update({"primary_metric": None}),
    "ablations": lambda d: d["contract"].update({"ablations": []}),
    "resource_budget": lambda d: d["resources"].update(
        {"budget": {}, "power": None}),
    "key_details": lambda d: (d["plan"].update(
        {"intervention_mechanism": [], "intervention_checkpoints": []}),
        d["handoff"].update({"repro_fields": None})),
}


@pytest.mark.parametrize("item", sorted(REMOVERS))
def test_expanded_without_entity_named(item):
    d = make_design()
    _set_status(d, item, "expanded")
    REMOVERS[item](d)
    errs = _d04_errors(d, item)
    assert errs, f"{item} 只改状态字未落实体，应被 DES-D04 点名"
    assert "查无" in errs[0]


def test_expanded_all_entities_present_passes():
    d = make_design()
    for s in d["intake"]["spec_intake"]:
        s["status"] = "expanded"
    assert validate_design(d) == []


def test_accepted_does_not_trigger_entity_check():
    d = make_design()
    # datasets 保持 accepted：即使实体缺失也不触发 DES-D04（其他规则
    # 的报错与本核查无关，只断言无 DES-D04 点名）
    REMOVERS["datasets"](d)
    assert _d04_errors(d, "datasets") == []


def test_demo_like_expanded_subset_passes():
    # 与演示主设计同形态：4 项 expanded、实体都在位
    d = make_design()
    for item in ("metrics", "ablations", "resource_budget", "key_details"):
        _set_status(d, item, "expanded")
    assert validate_design(d) == []


def test_returned_and_pending_not_checked():
    for status in ("returned", "pending"):
        d = make_design()
        _set_status(d, "ablations", status)
        d["contract"].update({"ablations": []})
        assert _d04_errors(d, "ablations") == []


def test_clone_of_valid_design_unaffected():
    d = clone(make_design())
    assert validate_design(d) == []
