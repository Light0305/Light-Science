from light_leader import route as route_mod
from light_leader import scan as scan_mod

from conftest import (make_analysis, make_design, make_execution, make_figure,
                      make_idea, make_literature, make_manuscript, make_memory,
                      make_review, make_selection)


def _route(root):
    return route_mod.route(scan_mod.scan_project(root))


def test_route_empty_project_starts_at_literature(tmp_path):
    r = _route(tmp_path)
    assert r["next"]["stage"] == "literature"
    assert not r["done"]


def test_route_gate_named_for_idea(tmp_path):
    make_literature(tmp_path)
    make_idea(tmp_path, status="pre_mortem_passed",
              review_status="REVIEW_UNAVAILABLE")
    r = _route(tmp_path)
    gates = {g["stage"]: g for g in r["gates"]}
    assert "idea" in gates
    assert "跨模型判定" in gates["idea"]["gate"]
    assert "异家族" in gates["idea"]["fix"]


def test_route_gate_named_for_design_freeze(tmp_path):
    make_literature(tmp_path)
    make_idea(tmp_path)
    make_design(tmp_path, status="reviewed",
                review_status="REVIEW_UNAVAILABLE")
    r = _route(tmp_path)
    assert any(g["stage"] == "design" for g in r["gates"])
    assert r["next"]["stage"] == "design"


def test_route_gate_named_for_analysis_blocked(tmp_path):
    make_literature(tmp_path)
    make_idea(tmp_path)
    make_design(tmp_path)
    make_execution(tmp_path)
    make_analysis(tmp_path, status="blocked",
                  blocked_reason="判定复核不可用（REVIEW_UNAVAILABLE）",
                  review_status="REVIEW_UNAVAILABLE")
    r = _route(tmp_path)
    assert any(g["stage"] == "analysis" for g in r["gates"])


def test_route_gate_named_for_write(tmp_path):
    make_literature(tmp_path)
    make_idea(tmp_path)
    make_design(tmp_path)
    make_execution(tmp_path)
    make_analysis(tmp_path)
    make_selection(tmp_path)
    make_manuscript(tmp_path, status="audited",
                    blocked_reason="REVIEW_UNAVAILABLE：跨模型复核不可用")
    r = _route(tmp_path)
    assert any(g["stage"] == "write" for g in r["gates"])


def test_route_no_gate_when_marker_absent(tmp_path):
    make_literature(tmp_path)
    make_idea(tmp_path, status="pre_mortem_passed")  # 无 REVIEW_UNAVAILABLE
    r = _route(tmp_path)
    assert r["gates"] == []


def test_route_terminal_gate_marker_ignored(tmp_path):
    # 已定版的卡即使留痕 REVIEW_UNAVAILABLE 也不再点名为当前门
    make_literature(tmp_path)
    make_idea(tmp_path, status="finalized_executable",
              review_status="REVIEW_UNAVAILABLE")
    r = _route(tmp_path)
    assert r["gates"] == []
    assert r["next"]["stage"] == "design"


def test_route_journal_select_before_write(tmp_path):
    make_literature(tmp_path)
    make_idea(tmp_path)
    make_design(tmp_path)
    make_execution(tmp_path)
    make_analysis(tmp_path)
    r = _route(tmp_path)
    assert r["next"]["stage"] == "journal-select"


def test_route_conceptual_idea_cannot_open_design(tmp_path):
    make_literature(tmp_path)
    make_idea(tmp_path, status="finalized_conceptual")
    r = _route(tmp_path)
    # conceptual 是 idea 终态但不得直接开工：下一步停在 design 并在理由点名
    assert r["next"]["stage"] == "design"
    assert "conceptual" in r["next"]["reason"]


def test_route_figure_parallel_note(tmp_path):
    make_literature(tmp_path)
    make_idea(tmp_path)
    make_design(tmp_path)
    make_execution(tmp_path)
    make_analysis(tmp_path)
    make_selection(tmp_path)
    make_manuscript(tmp_path, status="drafted")
    r = _route(tmp_path)
    assert any("figure 可并行" in n for n in r["notes"])


def test_route_memory_missing_note(tmp_path):
    make_literature(tmp_path)
    make_idea(tmp_path)  # idea 已达终态
    r = _route(tmp_path)
    assert any("memory 未建" in n and "idea" in n for n in r["notes"])


def test_route_full_chain_done(tmp_path):
    make_literature(tmp_path)
    make_idea(tmp_path)
    make_design(tmp_path)
    make_execution(tmp_path)
    make_analysis(tmp_path)
    make_selection(tmp_path)
    make_manuscript(tmp_path)
    make_figure(tmp_path)
    make_review(tmp_path)
    make_memory(tmp_path)
    r = _route(tmp_path)
    assert r["done"] is True
    assert r["next"] is None
    assert r["gates"] == []
