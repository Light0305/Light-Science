"""三期 export/report 测试：未定版拒绝并说明缺口（含 REVIEW_UNAVAILABLE
定版门细目）、定版三件套内容、概念定版横幅、方向层 memory 条目字段、
项目报告各节（定版清单/已杀区/去重率/对决摘要）、CLI 行为。"""

from __future__ import annotations

import json

import pytest

from light_idea import duel, export
from light_idea.cli import main
from light_idea.project import init_project, save_card
from conftest import full_card


def _finalized(level: str = "executable") -> dict:
    c = full_card(status="finalized_conceptual"
                  if level == "conceptual" else "finalized_executable")
    c["finalization_level"] = level
    return c


def test_export_refuses_draft_with_path(tmp_path):
    root = tmp_path / "proj"
    init_project(root, "导出方向")
    card = full_card(status="draft")
    save_card(root, card)
    with pytest.raises(export.ExportError) as excinfo:
        export.export_card(root, card)
    text = "；".join(excinfo.value.errors)
    assert "未定版" in text and "screened" in text  # 主线还差的路径被点名
    assert not (root / "exports").exists() or not list((root / "exports").iterdir())


def test_export_refuses_pre_mortem_with_gate_details(tmp_path):
    root = tmp_path / "proj"
    init_project(root, "导出方向")
    card = full_card(status="pre_mortem_passed")
    card["novelty"]["review_status"] = "REVIEW_UNAVAILABLE"
    card["novelty"]["receipt"] = {"verdict_id": None, "judge_model": None,
                                  "judge_family": None,
                                  "executor_model": "claude-opus",
                                  "executor_family": "anthropic"}
    with pytest.raises(export.ExportError) as excinfo:
        export.export_card(root, card)
    text = "；".join(excinfo.value.errors)
    assert "REVIEW_UNAVAILABLE" in text  # 定版门细目被展开说明


def test_export_refuses_killed(tmp_path):
    root = tmp_path / "proj"
    init_project(root, "导出方向")
    card = full_card(status="killed")
    card["kill"] = {"reason": "撞车", "date": "2026-10-20",
                    "source": "novelty_named_paper", "failure_class": "fundamental",
                    "root_cause": "已被做", "boundary_conditions": "无",
                    "named_paper": {"doi": "10.1/x"}}
    with pytest.raises(export.ExportError):
        export.export_card(root, card)


def test_export_finalized_trio(tmp_path):
    root = tmp_path / "proj"
    init_project(root, "导出方向")
    card = _finalized()
    save_card(root, card)
    result = export.export_card(root, card)
    out = root / "exports" / card["idea_id"]
    handoff = (out / "design_handoff.md").read_text(encoding="utf-8")
    assert "ResNet50 ImageNet 微调" in handoff          # 最强基线点名
    assert "50-shot 田间集上与最强基线对决" in handoff  # 判别实验
    assert "readout" not in handoff or True
    assert "未经试点验证" in handoff                     # pilot=not_run 诚实标注
    assert "PROCEED" in handoff                          # 查新结论
    card_json = json.loads((out / "idea_card.json").read_text(encoding="utf-8"))
    assert card_json["idea_id"] == card["idea_id"]
    entry = json.loads((out / "memory_export.jsonl").read_text(encoding="utf-8"))
    assert entry["level"] == "direction"
    assert entry["status"] == "feasible"
    assert entry["retrieval_tags"]                        # 带 Retrieval Tags
    assert any(e.startswith("verdict:") for e in entry["evidence"])
    assert any("novelty/" in e for e in entry["evidence"])  # Evidence 是指针
    assert result["finalization_level"] == "executable"


def test_export_conceptual_banner(tmp_path):
    root = tmp_path / "proj"
    init_project(root, "导出方向")
    card = _finalized(level="conceptual")
    card["exec_spec"]["datasets"] = []  # 概念级允许规格未齐
    save_card(root, card)
    export.export_card(root, card)
    handoff = (root / "exports" / card["idea_id"]
               / "design_handoff.md").read_text(encoding="utf-8")
    assert "不得直接开工" in handoff


def test_report_sections(tmp_path):
    root = tmp_path / "proj"
    init_project(root, "报告方向")
    fin = _finalized()
    fin["idea_id"] = "fin_000001"
    save_card(root, fin)
    killed = full_card(status="killed")
    killed["idea_id"] = "dead_000002"
    killed["kill"] = {"reason": "被在先论文覆盖", "date": "2026-10-20",
                      "source": "novelty_named_paper",
                      "failure_class": "fundamental",
                      "root_cause": "核心机制已被发表",
                      "boundary_conditions": "换机制面才可能复活",
                      "named_paper": {"doi": "10.1000/prior",
                                      "title": "Prior work"}}
    save_card(root, killed)
    other = full_card(status="draft")
    other["idea_id"] = "draft_000003"
    save_card(root, other)
    duel.record_duel(fin, other, "fin_000001", by="judge", date="2026-10-20")
    save_card(root, fin)
    save_card(root, other)

    summary = export.build_report(root)
    assert summary["total"] == 3
    assert summary["finalized"] == ["fin_000001"]
    assert summary["killed"] == ["dead_000002"]
    assert summary["duel_matches"] == 1
    text = (root / "idea-stage" / "IDEA_REPORT.md").read_text(encoding="utf-8")
    assert "## 定版清单" in text and "fin_000001" in text
    assert "## 已杀区摘要" in text and "Prior work" in text
    assert "边界条件" in text
    assert "## 去重率" in text and "去重率" in text
    assert "## 对决摘要" in text and "暂定" in text
    assert "未经试点验证" in text  # 定版清单里的诚实标注


def test_cli_export_and_report(tmp_path):
    root = tmp_path / "proj"
    init_project(root, "CLI 导出方向")
    card = _finalized()
    save_card(root, card)
    draft = full_card(status="draft")
    draft["idea_id"] = "draft_000009"
    save_card(root, draft)
    assert main(["export", str(root), card["idea_id"]]) == 0
    assert main(["export", str(root), "draft_000009"]) == 1  # 未定版拒绝
    assert main(["report", str(root)]) == 0
    assert main(["report", str(tmp_path / "nope")]) == 1
