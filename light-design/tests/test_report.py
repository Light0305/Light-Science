"""二期：DESIGN_REPORT 刷新（report 命令，手工区保留）。"""

from __future__ import annotations

from conftest import clone, frozen_design, make_design
from light_design import cli
from light_design.export import MANUAL_END, MANUAL_START, build_report
from light_design.gates import apply_amendment
from light_design.project import project_paths, save_design
from light_design.util import today


def _project_with_mixed_designs(project):
    """一本冻结（带 1 条 amendment）+ 一本带打回条目的 draft。"""
    d1 = frozen_design()
    apply_amendment(d1, "plan.blocking_stratification", "按时长分层",
                    reason="补充分层", results_seen="未跑任何运行", date=today())
    save_design(project, d1)
    d2 = clone(make_design())
    d2["design_id"] = "design_other_xyz789"
    d2["intake"]["returned_items"] = [
        {"item": "datasets", "reason": "交接缺失", "needed": "回补数据集",
         "date": today(), "resolved": False},
        {"item": "metrics", "reason": "交接为空", "needed": "回补指标",
         "date": today(), "resolved": True},
    ]
    save_design(project, d2)
    return d1, d2


def test_report_counts_and_sections(project):
    _project_with_mixed_designs(project)
    summary = build_report(project)
    assert summary["total"] == 2
    assert summary["frozen"] == ["design_test_abc123"]
    assert summary["amendments"] == 1
    assert summary["returned_items"] == 2
    text = project_paths(project)["design_report"].read_text(encoding="utf-8")
    assert "设计总数：2" in text and "已冻结（frozen）：1" in text
    assert "amendment 总数：1" in text
    assert "打回 **datasets**" in text and "**未清**" in text
    assert "RV-" in text or "评审收据" in text  # 定版清单带评审收据


def test_report_manual_section_preserved(project):
    _project_with_mixed_designs(project)
    build_report(project)
    path = project_paths(project)["design_report"]
    text = path.read_text(encoding="utf-8")
    custom = "人工备注：本方向先冻结判别实验设计，主实验等数据到位。"
    path.write_text(text.replace(MANUAL_START, MANUAL_START + "\n" + custom),
                    encoding="utf-8")
    summary = build_report(project)  # 再次刷新
    text2 = path.read_text(encoding="utf-8")
    assert custom in text2
    assert summary["total"] == 2  # 统计照常刷新


def test_report_empty_project(project):
    summary = build_report(project)
    assert summary["total"] == 0 and summary["amendments"] == 0
    text = project_paths(project)["design_report"].read_text(encoding="utf-8")
    assert "（暂无设计书）" in text and MANUAL_START in text


def test_report_via_cli(project):
    _project_with_mixed_designs(project)
    assert cli.main(["report", str(project)]) == 0
