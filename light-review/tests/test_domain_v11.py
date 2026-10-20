"""领域门 v1.1：REV-D08 检索式扩形 + REV-D01 范式第零层。"""

import pytest

from conftest import make_analysis, make_figure, make_manuscript, \
    make_target_record
from light_review.domain import DomainError, run_domain
from light_review.intake import run_intake
from light_review.project import init_package, load_package
from light_review.util import dump_yaml, today

AI_GROUPS = {"G": {"ai_policy": {"has_guideline": True,
                                 "disclosure_required": True}}}


def _pkg(tmp_path, sections, groups=AI_GROUPS, name="review"):
    ms = make_manuscript(tmp_path / f"{name}-ms", sections=sections)
    an = make_analysis(tmp_path / f"{name}-an")
    fg = make_figure(tmp_path / f"{name}-fg")
    record = make_target_record(tmp_path, groups=groups)
    root = tmp_path / name
    init_package(root, "review-pkg")
    run_intake(root, ms, an, figure_path=fg, intensity="standard",
               journal_name="Demo Journal", target_record=record)
    return root


def _by_id(root):
    rows = load_package(root)["domain_gate"]
    return {r["item_id"]: r for r in rows if r.get("type") == "domain_check"}


def _sections(disclosure_section):
    return {
        "02-methods.md": "# Methods\n\nWe tracked birds with a model.\n",
        "03-results.md": "# Results\n\nThe oracle arm differed by "
                         "[num:N001] 5.25 points [@dong2025].\n",
        "05-declarations.md": disclosure_section,
    }


# ------------------------------------------------------------ REV-D08 扩形

def test_j05_declaration_of_ai_use_title_found(world, tmp_path):
    """演示 DG-J05 复现：披露标题 Declaration of AI Use 在 v1.0 检索式
    之外判 hit；扩形后标题同义形命中 → miss（检出披露）。"""
    root = _pkg(tmp_path, _sections(
        "# Declaration of AI Use\n\nGenerative AI tools assisted "
        "language editing; all scientific content is the authors' own.\n"))
    run_domain(root)
    row = _by_id(root)["DG-J05"]
    assert row["result"] == "miss"
    assert "declaration of ai use" in row["detail"]


def test_j05_case_and_punctuation_variant_found(world, tmp_path):
    root = _pkg(tmp_path, _sections(
        "# AI-DISCLOSURE:\n\nThis work is AI assisted in copy editing.\n"))
    run_domain(root)
    assert _by_id(root)["DG-J05"]["result"] == "miss"


def test_j05_chinese_title_found(world, tmp_path):
    root = _pkg(tmp_path, _sections(
        "# 人工智能使用声明\n\n本研究使用生成式人工智能工具辅助语言润色。\n"))
    run_domain(root)
    assert _by_id(root)["DG-J05"]["result"] == "miss"


def test_j05_true_missing_still_hit(world, tmp_path):
    root = _pkg(tmp_path, _sections(
        "# Declarations\n\nThe authors declare no competing interests.\n"))
    run_domain(root)
    row = _by_id(root)["DG-J05"]
    assert row["result"] == "hit"
    assert "人工复核" in row["detail"]


# ------------------------------------------------------------ REV-D01 范式层

def test_paradigm_registration_recorded(world, tmp_path):
    root = _pkg(tmp_path, _sections("# Declarations\n\nNone.\n"))
    info = run_domain(root, paradigm="empirical",
                      paradigm_basis="段级行为检测实证研究：假设可检验、"
                                     "效应量与区间为判定主轴")
    review = load_package(root)["review"]
    assert review["paradigm"]["paradigm"] == "empirical"
    assert "段级" in review["paradigm"]["basis"]
    assert info["paradigm"] == "empirical"


def test_paradigm_registration_discipline(world, tmp_path):
    root = _pkg(tmp_path, _sections("# Declarations\n\nNone.\n"))
    with pytest.raises(DomainError):
        run_domain(root, paradigm="empirical")          # 缺判定依据
    with pytest.raises(DomainError):
        run_domain(root, paradigm="alchemy", paradigm_basis="乱填")
    run_domain(root, paradigm="empirical", paradigm_basis="实证研究")
    run_domain(root, paradigm="empirical", paradigm_basis="实证研究")
    with pytest.raises(DomainError) as ei:              # 异值静默改写
        run_domain(root, paradigm="theory", paradigm_basis="改口")
    assert any("新 round" in g or "round" in g for g in ei.value.gaps)


def _overlay_with_paradigms(tmp_path, paradigms):
    item = {"item_id": "DG-X01", "statement": "须报告消融归因",
            "source_kind": "historical_calibration",
            "explicit_or_inferred": "explicit",
            "confidence": 0.9, "severity_if_hit": "major",
            "scope": "基准类稿件", "executor": "code",
            "paradigms": paradigms,
            "check": {"kind": "keyword_present",
                      "keywords": ["ablation"]}}
    overlay = {"overlay_id": "paradigm-overlay", "version": "0.1",
               "source": {"kind": "historical_calibration",
                          "ref": "demo 校准集", "checked_at": today()},
               "dual_store_pointer": "light-memory://overlays/paradigm",
               "precedence": {"on_conflict": "core_wins"},
               "items": [item]}
    path = tmp_path / "overlay.yaml"
    dump_yaml(path, overlay)
    return path


def test_paradigm_applicability_filters_overlay(world, tmp_path):
    sections = _sections("# Declarations\n\nNone.\n")
    root = _pkg(tmp_path, sections)
    overlay = _overlay_with_paradigms(tmp_path, ["benchmark"])
    # 范式 empirical 不在条目适用集 → not_applicable 且依据落字
    run_domain(root, overlay_path=overlay, paradigm="empirical",
               paradigm_basis="实证研究")
    row = _by_id(root)["DG-X01"]
    assert row["result"] == "not_applicable"
    assert "范式 empirical" in row["detail"]
    # 换到适用范式的新包：条目正常判定（关键词缺失 → hit）
    root2 = _pkg(tmp_path, sections, name="review2")
    run_domain(root2, overlay_path=overlay, paradigm="benchmark",
               paradigm_basis="基准评测研究")
    row2 = _by_id(root2)["DG-X01"]
    assert row2["result"] == "hit"


def test_paradigm_required_gate_names_missing(world, tmp_path):
    from conftest import drive_panel
    from light_review.forensic import run_forensic
    from light_review.gates import GateError, advance_package
    from light_review.panel import build_consensus, freeze_reports
    sections = _sections("# Declarations\n\nNone.\n")
    root = _pkg(tmp_path, sections)
    overlay = _overlay_with_paradigms(tmp_path, ["benchmark"])
    info = run_domain(root, overlay_path=overlay)
    assert info["paradigm_required"] is True
    run_forensic(root)
    advance_package(root)
    drive_panel(root)
    advance_package(root)
    freeze_reports(root)
    build_consensus(root, [{"concern_id": "RV-C001", "statement": "x",
                            "raised_by": ["S1", "S2"],
                            "severity_proposals": {"S1": "minor",
                                                   "S2": "minor"}}])
    with pytest.raises(GateError) as ei:
        advance_package(root)          # → reported 被范式点名拦
    assert any("范式登记缺失" in g for g in ei.value.gaps)
    # 登记范式并重跑领域门后过门
    run_domain(root, overlay_path=overlay, paradigm="benchmark",
               paradigm_basis="基准评测研究")
    assert advance_package(root) == "reported"


def test_forensic_identical_across_paradigms(world, tmp_path):
    """钉死范式不污染确定性层：同稿不同范式，法医三件逐字一致。"""
    from light_review.forensic import run_forensic
    sections = _sections("# Declarations\n\nNone.\n")
    outs = []
    for name, paradigm in (("revA", "empirical"), ("revB", "humanities")):
        root = _pkg(tmp_path, sections,
                    groups={"G": {"ai_policy": {"has_guideline": True,
                                                "disclosure_required":
                                                False}}},
                    name=name)
        run_domain(root, paradigm=paradigm,
                   paradigm_basis=f"判定为 {paradigm}")
        run_forensic(root)
        outs.append({f: (root / "forensic" / f).read_bytes()
                     for f in ("reconciliation.jsonl", "findings.jsonl",
                               "compatibility.jsonl")})
    assert outs[0] == outs[1]
