"""测试夹具：按各包真实登记头形态构造的迷你项目树。

字段形态照真实演示产物：idea.yaml 的 status + 查新区 review_status、
design.yaml 的 freeze.review.review_status、analysis.yaml 的 status +
blocked.reason、manuscript.yaml 的 status + submission_blocked_reason、
selection.yaml / figure.yaml / review.yaml / execution.yaml 的 status、
literature 的 文献索引.csv + 证据表.jsonl、memory 四账 + registry-view。
"""

from __future__ import annotations

import csv
import json

import pytest
import yaml


def write_yaml(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, allow_unicode=True),
                    encoding="utf-8")
    return path


def write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n"
                            for r in rows), encoding="utf-8")
    return path


def make_literature(root, papers=(("p1", "精读完成"), ("p2", "精读完成")),
                    evidence_rows=14):
    lit = root / "literature" / "Literature"
    lit.mkdir(parents=True, exist_ok=True)
    with (lit / "文献索引.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["paper_id", "title", "doi", "source_version", "sha256",
                    "pages", "status", "ingested_at"])
        for pid, st in papers:
            w.writerow([pid, f"Title {pid}", "10.0000/x", "vor", "ab12",
                        "10", st, "2026-10-20"])
    write_jsonl(lit / "证据表.jsonl",
                [{"paper_id": "p1", "row": i} for i in range(evidence_rows)])
    return lit


def make_idea(root, status="finalized_executable", review_status=None):
    card = {"idea_id": "demo_123abc", "status": status, "title": "演示想法"}
    if review_status is not None:
        card["novelty"] = {"review_status": review_status}
    return write_yaml(root / "idea" / "cards" / "demo_123abc" / "idea.yaml",
                      card)


def make_design(root, status="frozen", review_status=None):
    d = {"design_id": "demo-design", "status": status}
    if review_status is not None:
        d["freeze"] = {"review": {"review_status": review_status,
                                   "review_id": "RV-0000000000"}}
    return write_yaml(
        root / "design" / "designs" / "demo-design" / "design.yaml", d)


def make_execution(root, status="delivered"):
    return write_yaml(
        root / "experiment" / "executions" / "demo-b1" / "execution.yaml",
        {"exec_id": "demo-b1", "status": status})


def make_analysis(root, status="delivered", blocked_reason=None,
                  review_status=None):
    d = {"analysis_id": "demo", "status": status}
    if blocked_reason:
        d["blocked"] = {"reason": blocked_reason}
    if review_status:
        d["review"] = {"review_status": review_status}
    return write_yaml(root / "analysis" / "analysis-pkg" / "analysis.yaml", d)


def make_selection(root, status="handed_off"):
    return write_yaml(root / "journal-select" / "selection.yaml",
                      {"selection_id": "demo", "status": status})


def make_manuscript(root, status="submission_ready", blocked_reason=None):
    d = {"manuscript_id": "demo", "status": status, "language": "en"}
    if blocked_reason:
        d["submission_blocked_reason"] = blocked_reason
    return write_yaml(root / "write" / "manuscript-pkg" / "manuscript.yaml", d)


def make_figure(root, status="delivered"):
    return write_yaml(root / "figure" / "figure-pkg" / "figure.yaml",
                      {"package_id": "demo", "status": status})


def make_review(root, status="delivered"):
    return write_yaml(root / "review" / "review-pkg" / "review.yaml",
                      {"review_id": "demo", "status": status})


def make_memory(root, with_view=True, n_objects=3):
    mem = root / "memory"
    mem.mkdir(parents=True, exist_ok=True)
    write_yaml(mem / "memory.yaml",
               {"kind": "light-memory/project", "memory_id": "demo"})
    rows = [{"object_id": f"paper:p{i}", "object_type": "paper",
             "upstream_id": f"p{i}", "project": "demo", "title": f"论文{i}",
             "status": "active", "current_version": "abcdef0123456789",
             "source_package": "literature"} for i in range(n_objects)]
    write_jsonl(mem / "objects.jsonl", rows)
    write_jsonl(mem / "events.jsonl", [{"event_id": "e1"}])
    write_jsonl(mem / "facts.jsonl", [{"fact_id": "f1"}, {"fact_id": "f2"}])
    write_jsonl(mem / "relations.jsonl", [])
    if with_view:
        view = {
            "kind": "light-memory/registry-view",
            "version": "1.0",
            "memory_id": "demo",
            "generated_at": "2026-10-20T00:00:00+00:00",
            "counts": {"paper": n_objects},
            "objects_by_type": {"paper": [
                {k: r[k] for k in ("object_id", "upstream_id", "project",
                                    "title", "status", "current_version",
                                    "source_package")} for r in rows]},
        }
        (mem / "registry-view.json").write_text(
            json.dumps(view, ensure_ascii=False, indent=1), encoding="utf-8")
    return mem


@pytest.fixture()
def empty_project(tmp_path):
    return tmp_path / "proj"
