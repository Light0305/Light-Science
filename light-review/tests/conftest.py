"""测试夹具：构造与真实演示同形的上游三包（Write/Analysis/Figure）。

默认世界是全一致的「干净世界」：主张 C1（grade insufficient、
ceiling/form 均为 limitations_only）、数字 N001=5.25（复算源
spec_results S001@R-ORA = 5.2493…，落在 5.25 的舍入区间内）、
图 F001（两侧同名文件哈希一致、图注无未登记数字）、引用
[@dong2025] 在 lock 中且 entry_hash 齐、Write 审计归档件存在。
各测试按需 mutate 单点造反例。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
import yaml

FIG_BYTES = b"<svg>fig1</svg>"
FIG_HASH = hashlib.sha256(FIG_BYTES).hexdigest()


def _dump_yaml(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(obj, allow_unicode=True, sort_keys=False),
                    encoding="utf-8")


def _dump_json(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2),
                    encoding="utf-8")


def _dump_jsonl(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n"
                            for r in rows), encoding="utf-8")


def make_manuscript(base: Path, *, claims=None, numbers=None, sections=None,
                    figures=None, lock_entries=None, audit=True) -> Path:
    base.mkdir(parents=True, exist_ok=True)
    (base / "sections").mkdir(exist_ok=True)
    (base / "assets").mkdir(exist_ok=True)
    (base / "assets" / "fig1.svg").write_bytes(FIG_BYTES)
    _dump_yaml(base / "manuscript.yaml", {
        "manuscript_id": "demo-manuscript", "title": "Demo",
        "language": "en", "status": "audited"})
    _dump_yaml(base / "claims_register.yaml", {"claims": claims if claims is not None else [
        {"claim_id": "C1", "analysis_claim_ref": "C1",
         "upstream_status": "untested", "strength_grade": "insufficient",
         "line_verdicts": {"R-FIX": "undetermined", "R-ORA": "undetermined"},
         "writable_ceiling": "limitations_only",
         "writable_form": "limitations_only",
         "evidence_refs": [{"kind": "analysis_verdict_lines",
                            "refs": ["R-FIX", "R-ORA"]}]},
    ]})
    _dump_yaml(base / "numbers_ledger.yaml", {"numbers": numbers if numbers is not None else [
        {"num_id": "N001", "value_as_printed": "5.25",
         "trace_ref": "R-ORA#v1", "verdict_ref": "R-ORA", "spec_ref": "S001",
         "calc_provenance": "welch_effect_and_ci",
         "locations": [{"section": "03-results.md"}]},
    ]})
    _dump_yaml(base / "figures_manifest.yaml", {"figures": figures if figures is not None else [
        {"figure_id": "F001", "kind": "figure", "status": "backfilled",
         "source_ref": "assets/fig1.svg", "source_hash": FIG_HASH,
         "caption": "Distribution of segment-level scores.",
         "display_number": 1, "display_label": "Figure 1"},
    ]})
    _dump_json(base / "references.lock.json", {
        "kind": "light-write/references-lock", "version": "1.0",
        "entries": lock_entries if lock_entries is not None else [
            {"key": "dong2025", "entry_id": "ST001",
             "doi": "10.0000/demo.1", "entry_hash": "a" * 64,
             "retraction_state": "clean"},
        ]})
    body = sections if sections is not None else {
        "03-results.md": (
            "# Results\n\nThe oracle arm differed by [num:N001] 5.25 "
            "points [@dong2025].\n"),
    }
    for name, text in body.items():
        (base / "sections" / name).write_text(text, encoding="utf-8")
    if audit:
        _dump_json(base / "audit" / "audit_report.json", {"ok": True})
    return base


def make_analysis(base: Path, *, conclusions=None, spec_results=None) -> Path:
    base.mkdir(parents=True, exist_ok=True)
    _dump_yaml(base / "conclusions.yaml", conclusions or {
        "claims_verdict": [
            {"claim_id": "C1", "support": "untested",
             "line_verdicts": {"R-FIX": "undetermined",
                               "R-ORA": "undetermined"}}],
        "strength": [{"claim_id": "C1", "grade": "insufficient"}],
        "number_provenance": [
            {"value": 5.2493333, "quantity": "effect_size",
             "verdict_line": "R-ORA#v1", "registry_line_id": "R-ORA",
             "spec_id": "S001", "calc_provenance": "welch_effect_and_ci"}],
    })
    _dump_jsonl(base / "spec_results.jsonl", spec_results if spec_results is not None else [
        {"spec_id": "S001", "registry_line_id": "R-ORA", "status": "computed",
         "effect_size": {"type": "mean_diff", "value": 5.2493333}},
    ])
    _dump_jsonl(base / "verdicts.jsonl", [
        {"registry_line_id": "R-ORA", "verdict": "undetermined"}])
    return base


def make_figure(base: Path, *, figures=None) -> Path:
    base.mkdir(parents=True, exist_ok=True)
    _dump_yaml(base / "delivery.yaml", {
        "kind": "light-figure/delivery", "version": 1, "status": "current",
        "figures": figures if figures is not None else [
            {"fig_id": "fig-1", "kind": "data", "caption_hash": "b" * 64,
             "files": [{"path": "exports/fig1.svg", "sha256": FIG_HASH,
                        "role": "main_pdf"}]},
        ]})
    return base


@pytest.fixture()
def world(tmp_path):
    """干净世界：三包路径 dict。"""
    return {
        "manuscript": make_manuscript(tmp_path / "manuscript-pkg"),
        "analysis": make_analysis(tmp_path / "analysis-pkg"),
        "figure": make_figure(tmp_path / "figure-pkg"),
    }


@pytest.fixture()
def review_pkg(tmp_path, world):
    """已 init + intake 的评审包（干净世界，full 隔离）。"""
    from light_review.intake import run_intake
    from light_review.project import init_package
    root = init_package(tmp_path / "review-pkg", title="Demo review")
    run_intake(root, world["manuscript"], analysis_path=world["analysis"],
               figure_path=world["figure"], journal_name="Demo Journal",
               intensity="standard")
    return root


def drive_panel(root, seats=("S1", "S2")):
    """登记席位并逐席落草稿（测试辅助）。"""
    from light_review.panel import register_seat, write_draft
    for i, sid in enumerate(seats):
        register_seat(root, sid, f"role-{sid}", "claude",
                      persona=f"persona {sid}")
        src = Path(root) / f"draft-{sid}.md"
        src.write_text(f"# {sid} 评审草稿\n\n关切若干。\n", encoding="utf-8")
        write_draft(root, sid, src)
    return seats


DEFAULT_CONCERNS = [
    {"concern_id": "RV-C001", "statement": "方法节缺关键参数",
     "raised_by": ["S1", "S2"],
     "severity_proposals": {"S1": "major", "S2": "minor"},
     "close_criterion": "补齐参数表",
     "pointers": {"claim_pointer": "claims_register:C1",
                  "evidence_pointer": "conclusions:C1"}},
    {"concern_id": "RV-C002", "statement": "图注可更明确",
     "raised_by": ["S2"],
     "severity_proposals": {"S2": "minor"},
     "close_criterion": "改写图注",
     "pointers": {"claim_pointer": "figures_manifest:F001",
                  "evidence_pointer": None}},
]


def drive_to_reported(root, concerns=None):
    """法医 → 推进 → 席位草稿 → 推进 → 冻结 → 共识账 → reported。"""
    from light_review.forensic import run_forensic
    from light_review.gates import advance_package
    from light_review.panel import build_consensus, freeze_reports
    run_forensic(root)
    advance_package(root)                       # forensic_checked
    drive_panel(root)
    advance_package(root)                       # paneled
    freeze_reports(root)
    build_consensus(root, DEFAULT_CONCERNS if concerns is None else concerns)
    advance_package(root)                       # reported
    return root


def make_target_record(base: Path, *, groups=None, verified_at=None) -> Path:
    """九组目标刊核查记录（Journal-Select/Write 同一事实源的形态）。"""
    from light_review.util import today
    record = {
        "A": {"record_id": "TR-2026-000001", "journal_name": "Demo Journal",
              "publisher": "Demo Publisher", "template_version": "2026.1",
              "journal_language": "en"},
        "C": {"section_sequence": ["abstract", "methods", "results"]},
        "D": {"word_limit_total": 10000},
        "G": {"declarations": [],
              "ai_policy": {"has_guideline": True,
                            "disclosure_required": False}},
        "H": {"source_url": "https://example.org/guide",
              "official_channel": "官网",
              "verified_at": verified_at or today(),
              "review_cycle_days": 180},
        "I": {"redistribution": "channel_only"},
    }
    for g, fields in (groups or {}).items():
        record.setdefault(g, {}).update(fields)
    path = base / "target-record.yaml"
    _dump_yaml(path, record)
    return path
