from light_leader import scan as scan_mod

from conftest import (make_analysis, make_design, make_execution, make_figure,
                      make_idea, make_literature, make_manuscript, make_memory,
                      make_review, make_selection)


def test_scan_empty_project(tmp_path):
    rep = scan_mod.scan_project(tmp_path)
    assert all(not s["found"] for s in rep["stages"].values())


def test_scan_literature_counts(tmp_path):
    make_literature(tmp_path, papers=(("p1", "精读完成"), ("p2", "速读完成"),
                                      ("p3", "精读完成")), evidence_rows=7)
    lit = scan_mod.scan_project(tmp_path)["stages"]["literature"]
    assert lit["found"]
    item = lit["items"][0]
    assert item["papers"] == 3
    assert item["status_counts"] == {"精读完成": 2, "速读完成": 1}
    assert item["evidence_rows"] == 7


def test_scan_each_yaml_stage_status(tmp_path):
    make_idea(tmp_path, status="pre_mortem_passed")
    make_design(tmp_path, status="reviewed")
    make_execution(tmp_path, status="executing")
    make_analysis(tmp_path, status="graded")
    make_selection(tmp_path, status="decided")
    make_manuscript(tmp_path, status="audited")
    make_figure(tmp_path, status="produced")
    make_review(tmp_path, status="reported")
    rep = scan_mod.scan_project(tmp_path)["stages"]
    assert scan_mod.stage_statuses(rep["idea"]) == ["pre_mortem_passed"]
    assert scan_mod.stage_statuses(rep["design"]) == ["reviewed"]
    assert scan_mod.stage_statuses(rep["experiment"]) == ["executing"]
    assert scan_mod.stage_statuses(rep["analysis"]) == ["graded"]
    assert scan_mod.stage_statuses(rep["journal-select"]) == ["decided"]
    assert scan_mod.stage_statuses(rep["write"]) == ["audited"]
    assert scan_mod.stage_statuses(rep["figure"]) == ["produced"]
    assert scan_mod.stage_statuses(rep["review"]) == ["reported"]


def test_scan_gate_markers_deep_found(tmp_path):
    # 门标记嵌套位置逐包不同，深搜都要命中
    make_idea(tmp_path, status="pre_mortem_passed",
              review_status="REVIEW_UNAVAILABLE")
    make_design(tmp_path, status="reviewed",
                review_status="REVIEW_UNAVAILABLE")
    make_manuscript(tmp_path, status="audited",
                    blocked_reason="REVIEW_UNAVAILABLE：跨模型复核不可用")
    rep = scan_mod.scan_project(tmp_path)["stages"]
    assert scan_mod.any_gate(rep["idea"])
    assert scan_mod.any_gate(rep["design"])
    assert scan_mod.any_gate(rep["write"])


def test_scan_analysis_blocked_reason(tmp_path):
    make_analysis(tmp_path, status="blocked",
                  blocked_reason="判定复核不可用（REVIEW_UNAVAILABLE）")
    item = scan_mod.scan_project(tmp_path)["stages"]["analysis"]["items"][0]
    assert item["blocked_reason"].startswith("判定复核不可用")


def test_scan_memory_counts_and_view_flag(tmp_path):
    make_memory(tmp_path, with_view=True, n_objects=5)
    mem = scan_mod.scan_project(tmp_path)["stages"]["memory"]["items"][0]
    assert mem["counts"] == {"objects": 5, "events": 1, "facts": 2,
                             "relations": 0}
    assert mem["registry_view"] is True


def test_scan_broken_header_named_not_guessed(tmp_path):
    p = tmp_path / "write" / "manuscript.yaml"
    p.parent.mkdir(parents=True)
    p.write_text("status: [未闭合\n", encoding="utf-8")
    item = scan_mod.scan_project(tmp_path)["stages"]["write"]["items"][0]
    assert item["status"] is None
    assert "error" in item


def test_scan_missing_status_field_named(tmp_path):
    from conftest import write_yaml
    write_yaml(tmp_path / "figure" / "figure.yaml", {"package_id": "x"})
    item = scan_mod.scan_project(tmp_path)["stages"]["figure"]["items"][0]
    assert item["status"] is None
    assert "status" in item["error"]
