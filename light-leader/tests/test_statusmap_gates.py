"""LD-03 映射表与 LD-04 门字段族的新增用例（v1.1 第 3 步之十一）。

覆盖：映射表全覆盖断言、未知状态值原样报告、design 打回/阻塞两类
新门点名（含缺项/解阻指针）、blocked_gate 统一字段点名与形态纪律、
缺字段不点名。既有 32 项用例在原文件，一字未改。
"""

from light_leader import route as route_mod
from light_leader import scan as scan_mod
from light_leader import statusmap
from light_leader.layout import GATE_FIELD_FAMILIES, STAGES

from conftest import (make_design, make_idea, make_literature,
                      write_yaml)


def _route(root):
    return route_mod.route(scan_mod.scan_project(root))


# ---------------------------------------------------------------- LD-03

def test_statusmap_covers_every_known_state_exactly():
    # 诊断 LD-03 测试口径：layout 表中每个阶段的每个已知状态值在
    # 映射表有条目（KNOWN_STATES 与 STATUS_MAP 键集逐阶段全等）
    for stage, known in statusmap.KNOWN_STATES.items():
        assert set(known) == set(statusmap.STATUS_MAP[stage]), stage
        assert len(known) == len(set(known)), stage  # 无重复条目
        for value in statusmap.STATUS_MAP[stage].values():
            assert value in statusmap.CANONICAL_STATES


def test_statusmap_terminals_map_to_terminal():
    for stage, spec in STAGES.items():
        for term in spec["terminal"]:
            assert statusmap.canonical(stage, term) == "已达终态", \
                (stage, term)
    # design 的开工前置值也须是终态口径
    for ready in STAGES["idea"]["design_ready"]:
        assert statusmap.canonical("idea", ready) == "已达终态"


def test_statusmap_gate_and_bypass_classification():
    # J1 归类：blocked 归被门拦；returned/killed/parked 归旁路；
    # journal-select 的 gated 是主线步骤名，归进行中不得误判
    assert statusmap.canonical("analysis", "blocked") == "被门拦"
    assert statusmap.canonical("design", "blocked") == "被门拦"
    assert statusmap.canonical("experiment", "blocked") == "被门拦"
    assert statusmap.canonical("design", "returned") == "旁路"
    assert statusmap.canonical("idea", "killed") == "旁路"
    assert statusmap.canonical("idea", "parked") == "旁路"
    assert statusmap.canonical("journal-select", "gated") == "进行中"
    assert statusmap.canonical("literature", "精读完成") == "已达终态"
    assert statusmap.canonical("literature", "excluded") == "旁路"


def test_scan_annotates_canonical(tmp_path):
    make_design(tmp_path, status="reviewed")
    item = scan_mod.scan_project(tmp_path)["stages"]["design"]["items"][0]
    assert item["canonical"] == "进行中"


def test_unknown_status_verbatim_and_unmapped(tmp_path):
    # 未知状态值原样报告、不 reinterpret（既有纪律的映射表版回归）
    make_design(tmp_path, status="some_future_state")
    rep = scan_mod.scan_project(tmp_path)
    item = rep["stages"]["design"]["items"][0]
    assert item["status"] == "some_future_state"
    assert item["canonical"] is None
    assert statusmap.canonical("design", "some_future_state") is None
    assert statusmap.canonical("design", None) is None


# ---------------------------------------------------------------- LD-04

def test_gate_families_registered():
    assert set(GATE_FIELD_FAMILIES) == {
        "review_unavailable", "blocked_gate", "return_block"}
    assert GATE_FIELD_FAMILIES["blocked_gate"]["field"] == "blocked_gate"
    assert GATE_FIELD_FAMILIES["return_block"]["stages"] == ("design",)


def _make_design_extra(root, data):
    return write_yaml(
        root / "design" / "designs" / "demo-design" / "design.yaml", data)


def test_route_names_design_returned_with_gap_pointer(tmp_path):
    make_literature(tmp_path)
    make_idea(tmp_path)
    _make_design_extra(tmp_path, {
        "design_id": "demo-design", "status": "returned",
        "return_record": {"returned_items": [
            {"item": "承接项 metrics", "reason": "登记行缺失",
             "needed": "补 expected_registry 行", "resolved": False},
            {"item": "旧缺项", "reason": "已补", "needed": "-",
             "resolved": True},
        ]}})
    r = _route(tmp_path)
    hits = [g for g in r["gates"] if g["family"] == "return_block"]
    assert len(hits) == 1
    assert "打回" in hits[0]["gate"]
    assert "承接项 metrics" in hits[0]["pointer"]  # 缺项逐项点名
    assert "旧缺项" not in hits[0]["pointer"]     # 已回补不点名
    assert r["next"]["stage"] == "design"
    assert "规范态：旁路" in r["next"]["reason"]


def test_route_returned_all_resolved_not_named(tmp_path):
    make_literature(tmp_path)
    make_idea(tmp_path)
    _make_design_extra(tmp_path, {
        "design_id": "demo-design", "status": "returned",
        "return_record": {"returned_items": [
            {"item": "旧缺项", "reason": "已补", "needed": "-",
             "resolved": True}]}})
    r = _route(tmp_path)
    assert [g for g in r["gates"] if g["family"] == "return_block"] == []


def test_route_names_design_blocked_with_unblock_pointer(tmp_path):
    make_literature(tmp_path)
    make_idea(tmp_path)
    _make_design_extra(tmp_path, {
        "design_id": "demo-design", "status": "blocked",
        "block_record": {"reason": "算力配额未批",
                         "unblock_condition": "配额批复到位"}})
    r = _route(tmp_path)
    hits = [g for g in r["gates"] if g["family"] == "return_block"]
    assert len(hits) == 1
    assert "算力配额未批" in hits[0]["evidence"][0]
    assert "配额批复到位" in hits[0]["pointer"]  # 解阻条件即指针
    assert "规范态：被门拦" in r["next"]["reason"]


def test_route_names_blocked_gate_field(tmp_path):
    make_literature(tmp_path)
    make_idea(tmp_path, status="pre_mortem_passed")
    card = tmp_path / "idea" / "cards" / "demo_123abc" / "idea.yaml"
    import yaml
    data = yaml.safe_load(card.read_text(encoding="utf-8"))
    data["blocked_gate"] = {"gate_id": "ethics_review",
                            "detail": "伦理审查未过",
                            "fix_pointer": "补伦理批件后回填"}
    card.write_text(yaml.safe_dump(data, allow_unicode=True),
                    encoding="utf-8")
    r = _route(tmp_path)
    hits = [g for g in r["gates"] if g["family"] == "blocked_gate"]
    assert len(hits) == 1
    assert "ethics_review" in hits[0]["gate"]
    assert hits[0]["pointer"] == "补伦理批件后回填"


def test_blocked_gate_malformed_not_named_but_noted(tmp_path):
    make_literature(tmp_path)
    make_idea(tmp_path, status="pre_mortem_passed")
    card = tmp_path / "idea" / "cards" / "demo_123abc" / "idea.yaml"
    import yaml
    data = yaml.safe_load(card.read_text(encoding="utf-8"))
    data["blocked_gate"] = "not-a-mapping"
    card.write_text(yaml.safe_dump(data, allow_unicode=True),
                    encoding="utf-8")
    rep = scan_mod.scan_project(tmp_path)
    item = rep["stages"]["idea"]["items"][0]
    assert "gate_blocks" not in item            # 形态不合不点名
    assert any("形态不合" in n for n in item["gate_notes"])
    assert route_mod.route(rep)["gates"] == []  # 不猜门


def test_missing_gate_fields_no_naming(tmp_path):
    # A7：无任何门字段的进行中阶段，route 不点名门（缺字段不等于无门，
    # 但也不许凭空断言有门）
    make_literature(tmp_path)
    make_idea(tmp_path, status="pre_mortem_passed")
    make_design(tmp_path, status="reviewed")
    r = _route(tmp_path)
    assert r["gates"] == []
