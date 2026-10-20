"""状态机全序 + 阻断纪律 + 降档声明强制 + STALE 门（§6、R1/R2）。"""

import pytest

from conftest import drive_panel, make_analysis, make_figure, make_manuscript
from light_review.forensic import adjudicate_finding, run_forensic
from light_review.gates import GateError, advance_package, deliver_package
from light_review.intake import run_intake
from light_review.panel import build_consensus, freeze_reports
from light_review.project import init_package, load_package
from light_review.validate import validate_package

CONCERNS = [{"concern_id": "RV-C001", "statement": "方法节缺关键参数",
             "raised_by": ["S1", "S2"],
             "severity_proposals": {"S1": "minor", "S2": "minor"}}]


def _pkg(tmp_path, name="rp", manuscript_kw=None, **intake_kw):
    ms = make_manuscript(tmp_path / f"{name}-ms", **(manuscript_kw or {}))
    an = make_analysis(tmp_path / f"{name}-an")
    fig = make_figure(tmp_path / f"{name}-fig")
    root = init_package(tmp_path / name)
    kw = {"intensity": "standard"}
    kw.update(intake_kw)
    run_intake(root, ms, analysis_path=an, figure_path=fig, **kw)
    return root


def _to_reported(root):
    run_forensic(root)
    advance_package(root)          # forensic_checked
    drive_panel(root)
    advance_package(root)          # paneled
    freeze_reports(root)
    build_consensus(root, CONCERNS)
    advance_package(root)          # reported


def test_full_state_sequence_to_delivered(tmp_path, review_pkg):
    _to_reported(review_pkg)
    assert advance_package(review_pkg) == "adjudicated"
    delivery = deliver_package(review_pkg)
    review = load_package(review_pkg)["review"]
    assert review["status"] == "delivered"
    assert delivery["manifest_hash"]
    assert (review_pkg / "REVIEW_DELIVERY.md").exists()
    assert validate_package(review_pkg) == []


def test_advance_names_gaps(tmp_path, review_pkg):
    with pytest.raises(GateError) as ei:
        advance_package(review_pkg)
    assert any("reconciliation" in g for g in ei.value.gaps)


def test_confirmed_error_blocks_then_adjudication_releases(tmp_path):
    sections = {"03-results.md":
                "# Results\n\nDiffered by [num:N001] 5.30 points [@dong2025].\n"}
    root = _pkg(tmp_path, manuscript_kw={"sections": sections})
    _to_reported(root)
    with pytest.raises(GateError) as ei:
        advance_package(root)      # → adjudicated 被 confirmed error 拦
    assert any("未裁决" in g for g in ei.value.gaps)
    with pytest.raises(GateError):
        deliver_package(root)      # 未到 adjudicated，deliver 同样过不去
    adjudicate_finding(root, "F001", "overruled", "张三",
                       "正文笔误，台账与复算一致，已回 Write 更正")
    assert advance_package(root) == "adjudicated"
    deliver_package(root)
    assert load_package(root)["review"]["status"] == "delivered"
    assert validate_package(root) == []


def test_degraded_deliver_requires_statement(tmp_path):
    root = _pkg(tmp_path, name="rp-deg", isolation_mode="degraded",
                isolation_reason="单模型环境，席位无法跨家族隔离")
    _to_reported(root)
    advance_package(root)          # adjudicated
    with pytest.raises(GateError) as ei:
        deliver_package(root)
    assert any("降档声明" in g for g in ei.value.gaps)
    deliver_package(root, degradation_statement=(
        "本轮评审在单模型环境完成，席位隔离为同家族分席位 + 可见性矩阵"
        "模拟，未做跨家族隔离；独立性弱于全规格。"))
    review = load_package(root)["review"]
    assert review["delivery"]["degradation_statement"]
    assert "降档声明" in (root / "REVIEW_DELIVERY.md").read_text(
        encoding="utf-8")
    assert validate_package(root) == []


def test_stale_blocks_forensic_checked_gate(tmp_path):
    root = _pkg(tmp_path)
    run_forensic(root)
    section = tmp_path / "rp-ms" / "sections" / "03-results.md"
    section.write_text(section.read_text(encoding="utf-8") + "事后改稿\n",
                       encoding="utf-8")
    with pytest.raises(GateError) as ei:
        advance_package(root)
    assert any("STALE" in g for g in ei.value.gaps)


def test_deliver_before_adjudicated_rejected(tmp_path):
    root = _pkg(tmp_path)
    _to_reported(root)
    with pytest.raises(GateError):
        deliver_package(root)
