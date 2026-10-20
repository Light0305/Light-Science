"""测试夹具：记忆项目 + 九包迷你上游源（形态照各包真实导出物裁剪）。

迷你源的字段名与结构与真实演示产物一致（memory_export.jsonl /
execution_card.json / conclusion_card.json / provenance.yaml /
selection.json / design.yaml / 证据表.jsonl / manuscript.yaml /
handoff_to_write.json），保证适配器测的是真形态而非自造形态。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from light_memory import project as project_mod


def _write_jsonl(path: Path, rows) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n"
                            for r in rows), encoding="utf-8")
    return path


def _write_json(path: Path, obj) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2),
                    encoding="utf-8")
    return path


@pytest.fixture()
def mem_root(tmp_path) -> Path:
    root = tmp_path / "memory"
    project_mod.init_package(root, project_id="proj-demo", title="演示项目")
    return root


# ---------------------------------------------------------------- Idea

@pytest.fixture()
def idea_source(tmp_path) -> Path:
    row = {
        "entry_id": "DIR-idea-alpha_123abc",
        "level": "direction",
        "summary": "零调参阈值可由视频级统计量预测",
        "why": "成立则部署免逐集调参；查新判定 PROCEED_WITH_CAUTION",
        "evidence": ["cards/idea-alpha_123abc/idea.yaml",
                     "verdict:NV-0001"],
        "status": "feasible",
        "retrieval_tags": ["tracking", "threshold"],
        "boundary_conditions": ["仅限顶视固定机位"],
        "source": {"idea_id": "idea-alpha_123abc", "operator": "evo",
                   "finalization_level": "executable", "project": "demo"},
        "date": "2026-10-19",
    }
    return _write_jsonl(tmp_path / "idea" / "memory_export.jsonl", [row])


# ---------------------------------------------------------------- Experiment

@pytest.fixture()
def experiment_source(tmp_path) -> Path:
    d = tmp_path / "exec-b2"
    d.mkdir(parents=True)
    card = {
        "exec_id": "exec-b2", "exported_at": "2026-10-20",
        "status": "delivered",
        "acceptance": {"verdict": "passed", "targets": ["R-FIX"]},
        "runs": [{"run_id": "R-FIX-a1", "status": "reconciled"},
                 {"run_id": "R-NEG-a1", "status": "failed"}],
    }
    _write_json(d / "execution_card.json", card)
    events = [
        {"seq": 1, "event_id": "EV-000001", "type": "intake_done",
         "run_id": None, "payload": {"design_id": "design-1"}},
        {"seq": 2, "event_id": "EV-000002", "type": "run_created",
         "run_id": "R-FIX-a1", "payload": {"attempt": 1}},
    ]
    _write_jsonl(d / "events.jsonl", events)
    failures = [
        {"kind": "failure", "failure_id": "F-0001", "run_id": "R-NEG-a1",
         "date": "2026-10-20", "exit_status": "failed_data",
         "mast_code": "FM-2.3", "mast_name": "任务跑偏",
         "failure_class": "fundamental",
         "root_cause": "数据版本交付不完整，登记对象不存在完整形态",
         "signature": "FM-2.3|数据版本交付不完整",
         "reflux_target": "design", "reflux_status": "pending"},
        {"kind": "failure_review", "failure_id": "F-0001",
         "reviewer": "第二人", "agrees": True, "date": "2026-10-20"},
    ]
    _write_jsonl(d / "failures.jsonl", failures)
    return d


# ---------------------------------------------------------------- Analysis

@pytest.fixture()
def analysis_source(tmp_path) -> Path:
    card = {
        "kind": "light-analysis/conclusion-card", "version": "1.0",
        "analysis_id": "analysis-pkg", "exported_at": "2026-10-20",
        "status": "blocked",
        "execution_ref": {"execution_id": "exec-b2"},
        "design_ref": {"design_id": "design-1"},
        "review": {"review_status": "REVIEW_UNAVAILABLE",
                   "reason": "单一模型家族"},
        "claims": [{"claim_id": "C1", "support": "untested",
                    "grade": "insufficient",
                    "cap_reason": "含未检验行",
                    "line_verdicts": {"R-NEG": "untested"}}],
        "boundaries": [{"claim_id": "C1", "conditions": "仅覆盖本执行包"}],
    }
    return _write_json(tmp_path / "analysis" / "conclusion_card.json", card)


# ---------------------------------------------------------------- Figure

@pytest.fixture()
def figure_source(tmp_path) -> Path:
    d = tmp_path / "figure-pkg"
    d.mkdir(parents=True)
    prov = {
        "kind": "light-figure/provenance", "version": "1.0",
        "entries": [
            {"fig_id": "fig-1", "line": "data", "opened_at": "2026-10-20",
             "backend": "python", "script_hash": "aa11",
             "source_data_hash": "bb22"},
            {"fig_id": "fig-2", "line": "schematic",
             "opened_at": "2026-10-20", "prompt_version": "1",
             "generation_model": {"name": "gpt-image", "version": "1"},
             "reference_image_hash": "cc33"},
        ],
        "history": [
            {"fig_id": "fig-1", "at": "2026-10-20T10:00:00+00:00",
             "supersedes": "dd44", "changes": {"backend": {}}},
        ],
    }
    p = d / "provenance.yaml"
    p.write_text(yaml.safe_dump(prov, allow_unicode=True),
                 encoding="utf-8")
    return p


# ---------------------------------------------------------------- Journal-Select

@pytest.fixture()
def journal_source(tmp_path) -> Path:
    data = {
        "kind": "light-journal-select/selection-export", "version": "1.0",
        "selection_id": "sel-001", "title": "Turkey behaviour paper",
        "status": "handed_off", "updated_at": "2026-10-20",
        "decision": {"journal": "Smart Agricultural Technology",
                     "date": "2026-10-20", "by": "user"},
        "candidates": [
            {"journal": "Smart Agricultural Technology",
             "verification": {
                 "apc": {"status": "verified", "value": "USD 1200"},
                 "review_weeks": {"status": "unverified",
                                  "value": None}}},
            {"journal": "Some Journal",
             "verification": {"apc": {"status": "unverified",
                                      "value": None}}},
        ],
    }
    return _write_json(tmp_path / "js" / "selection.json", data)


# ---------------------------------------------------------------- Design

@pytest.fixture()
def design_source(tmp_path) -> Path:
    data = {
        "design_id": "design-1", "title": "阈值预测对照实验设计",
        "created": "2026-10-19", "status": "frozen",
        "claims": {"primary_claims": [
            {"id": "C1", "statement": "视频级统计量与最优阈值存在稳定映射",
             "confirmatory": True}]},
        "freeze": {"frozen_at": "2026-10-19", "content_hash": "ff00",
                   "amendments": [
                       {"field": "evaluation.segments", "from": 6,
                        "to": 10, "user_signed": True,
                        "summary": "命门字段变更：评估段数 6 → 10"},
                       {"summary": "补记一条无字段标识的修订"}]},
        "status_history": [{"from": "draft", "to": "frozen"}],
    }
    p = tmp_path / "design" / "design.yaml"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(yaml.safe_dump(data, allow_unicode=True),
                 encoding="utf-8")
    return p


# ---------------------------------------------------------------- Literature

@pytest.fixture()
def literature_source(tmp_path) -> Path:
    d = tmp_path / "Literature"
    d.mkdir(parents=True)
    rows = [
        {"evidence_id": "E001", "paper_id": "paper-turkey_abc",
         "finding": "异常检测在 7 段视频上 AUROC 92.1%",
         "statistic": "AUROC 92.1%", "page": 1, "quote": "q1",
         "supports_claim": "自监督异常检测有效", "claim_strength": "direct",
         "limitations": "", "note_path": "Literature/paper/阅读笔记.md",
         "note_anchor": "10", "created_at": "2026-10-18"},
        {"evidence_id": "E002", "paper_id": "paper-turkey_abc",
         "finding": "跟踪 MOTA 87.7%", "statistic": "87.7% MOTA",
         "page": 1, "quote": "q2", "supports_claim": "跟踪精度达标",
         "claim_strength": "direct", "limitations": "",
         "note_path": "Literature/paper/阅读笔记.md", "note_anchor": "10",
         "created_at": "2026-10-18"},
    ]
    _write_jsonl(d / "证据表.jsonl", rows)
    (d / "文献索引.csv").write_text(
        "paper_id,title\npaper-turkey_abc,Abnormal turkey behaviour\n",
        encoding="utf-8")
    return d


# ---------------------------------------------------------------- Write

@pytest.fixture()
def write_source(tmp_path) -> Path:
    d = tmp_path / "manuscript-pkg"
    d.mkdir(parents=True)
    data = {
        "manuscript_id": "ms-001", "title": "Turkey paper",
        "status": "audited",
        "use_log": [
            {"tool": "Claude", "model": "Claude Opus",
             "model_version": "opus-4.5", "purpose": "drafting",
             "section": "all", "date": "2026-10-20"},
            {"tool": "Claude", "model": "Claude Opus",
             "purpose": "polish", "section": "intro",
             "date": "2026-10-20"},
        ],
    }
    p = d / "manuscript.yaml"
    p.write_text(yaml.safe_dump(data, allow_unicode=True),
                 encoding="utf-8")
    reg = {"claims": [{"id": "C1", "statement": "阈值可由统计量预测"}]}
    (d / "claims_register.yaml").write_text(
        yaml.safe_dump(reg, allow_unicode=True), encoding="utf-8")
    return p


# ---------------------------------------------------------------- Review

@pytest.fixture()
def review_source(tmp_path) -> Path:
    data = {
        "kind": "light-review/handoff-to-write", "version": 1,
        "review_id": "review-pkg", "generated_at": "2026-10-20",
        "items": [
            {"concern_id": "RV-C001", "severity": "major",
             "statement": "主张 C1 含未检验行，成稿须保持可见",
             "claim_pointer": "claims_register:C1",
             "evidence_pointer": "conclusions:C1",
             "action_class": "fixable-in-text", "consensus": True,
             "source_seats": ["S1", "S2"],
             "close_criterion": "摘要明示未检验状态"},
        ],
    }
    return _write_json(tmp_path / "review" / "handoff_to_write.json", data)
