"""评审包的落盘结构：init 建骨架、load/save 读写文件群。

一个评审包 = 一个目录（权威源是结构化文件群，MD 是渲染）：

    review.yaml            登记头（权威）：承接快照、约束、隔离模式、冻结账
    seats.yaml             席位登记 + 可见性矩阵（RV-01）
    consensus.yaml         共识与分歧账（RV-05）
    forensic/
      reconciliation.jsonl 四方对账逐项结果 + 边级覆盖自报
      findings.jsonl       法医发现账（只增不改；裁决走追加行）
      compatibility.jsonl  GRIM 族相容性结果（适用性元数据 + 算式证据）
      summaries.yaml       GRIM 被检汇总量的登记（值/小数位/n/items/量表）
    reports/
      drafts/<seat>.md     逐席草稿（席间物理隔离，冻结前互不可见）
      <seat>.md            逐席报告冻结件（哈希钉住，冻结后只许比较与引用）
    REVIEW_DELIVERY.md     交付清单（deliver 渲染）

Phase 2 件（领域门 domain_gate.jsonl、校准 calibration.yaml、验证台
reports/bench_report.json、meta reports/meta_review.md、决定建议
reports/decision.md 或降级问题清单 reports/problem_list.md、自审
reports/selfcheck.json、回填清单 handoff_to_write.md/.json）随各命令
落地，落地一件即从登记头 phase2_pending 摘除一件。
"""

from __future__ import annotations

from pathlib import Path

from . import schema
from .util import dump_jsonl, dump_yaml, load_structured, read_jsonl

FILES = {
    "review": "review.yaml",
    "seats": "seats.yaml",
    "consensus": "consensus.yaml",
    "reconciliation": "forensic/reconciliation.jsonl",
    "findings": "forensic/findings.jsonl",
    "compatibility": "forensic/compatibility.jsonl",
    "summaries": "forensic/summaries.yaml",
    "delivery_md": "REVIEW_DELIVERY.md",
    # Phase 2 件（领域门 / 校准 / 验证台 / meta / 自审 / 回填清单）
    "domain_gate": "domain_gate.jsonl",
    "calibration": "calibration.yaml",
    "bench_report": "reports/bench_report.json",
    "meta_review": "reports/meta_review.md",
    "decision_md": "reports/decision.md",
    "problem_list": "reports/problem_list.md",
    "selfcheck": "reports/selfcheck.json",
    "handoff_md": "handoff_to_write.md",
    "handoff_json": "handoff_to_write.json",
}


def pkg_path(root, name: str) -> Path:
    return Path(root) / name


def init_package(root, title: str = "", round_no: int = 1) -> Path:
    """在 root 处建评审包骨架；review_id 取目录名。已存在关键文件则拒绝覆盖。"""
    root = Path(root)
    if (root / FILES["review"]).exists():
        raise FileExistsError(f"评审包已存在：{root / FILES['review']}")
    (root / "forensic").mkdir(parents=True, exist_ok=True)
    (root / "reports" / "drafts").mkdir(parents=True, exist_ok=True)
    review_id = root.name
    dump_yaml(root / FILES["review"],
              schema.new_review(review_id, title=title or review_id,
                                round_no=round_no))
    dump_yaml(root / FILES["seats"], schema.new_seats())
    dump_yaml(root / FILES["consensus"], schema.new_consensus())
    return root


def load_package(root) -> dict:
    """读整个评审包为 dict；缺文件记 None（校验器负责点名，不在这里抛）。"""
    root = Path(root)
    pkg = {"root": root}
    for key, name in FILES.items():
        p = root / name
        if not p.exists():
            pkg[key] = None
        elif name.endswith(".jsonl"):
            pkg[key] = read_jsonl(p)
        elif name.endswith(".md"):
            pkg[key] = p.read_text(encoding="utf-8")
        else:
            pkg[key] = load_structured(p)
    return pkg


def save_review(root, review: dict) -> None:
    dump_yaml(Path(root) / FILES["review"], review)


def save_seats(root, seats: dict) -> None:
    dump_yaml(Path(root) / FILES["seats"], seats)


def save_consensus(root, consensus: dict) -> None:
    dump_yaml(Path(root) / FILES["consensus"], consensus)


def save_reconciliation(root, rows) -> None:
    dump_jsonl(Path(root) / FILES["reconciliation"], rows)


def save_findings(root, rows) -> None:
    dump_jsonl(Path(root) / FILES["findings"], rows)


def append_finding_rows(root, rows) -> None:
    p = Path(root) / FILES["findings"]
    existing = read_jsonl(p) if p.exists() else []
    dump_jsonl(p, existing + list(rows))


def save_compatibility(root, rows) -> None:
    dump_jsonl(Path(root) / FILES["compatibility"], rows)


def save_summaries_registration(root, registration: dict) -> None:
    dump_yaml(Path(root) / FILES["summaries"], registration)


# ---------------------------------------------------------------- Phase 2 落盘

def save_domain_gate(root, rows) -> None:
    dump_jsonl(Path(root) / FILES["domain_gate"], rows)


def save_calibration(root, calibration: dict) -> None:
    dump_yaml(Path(root) / FILES["calibration"], calibration)


def clear_pending(review: dict, *items: str) -> None:
    """Phase 2 件落地后从 phase2_pending 摘除（登记头如实记未尽件）。"""
    pending = review.get("phase2_pending") or []
    review["phase2_pending"] = [p for p in pending if p not in items]


def fold_findings(rows) -> list:
    """把 findings.jsonl 折叠成现行发现表：裁决追加行并入对应发现。

    findings 本体只增不改（RV-11/草案 §五）：裁决以 type=adjudication
    的追加行留痕，这里按 finding_id 归并出每条发现的现行裁决状态。
    """
    findings: dict[str, dict] = {}
    order: list[str] = []
    for row in rows or []:
        if row.get("type") == "finding":
            fid = row.get("finding_id")
            entry = dict(row)
            entry["adjudication"] = None
            findings[fid] = entry
            order.append(fid)
        elif row.get("type") == "adjudication":
            fid = row.get("finding_id")
            if fid in findings:
                findings[fid]["adjudication"] = {
                    "outcome": row.get("outcome"),
                    "adjudicator": row.get("adjudicator"),
                    "reason": row.get("reason"),
                    "at": row.get("at"),
                }
    return [findings[fid] for fid in order]


def open_confirmed_errors(folded) -> list:
    """未裁决的 confirmed error 发现（delivered 阻断集，R2 硬度 a）。"""
    out = []
    for f in folded or []:
        if f.get("category") != "confirmed_error":
            continue
        adj = f.get("adjudication")
        if adj is None:
            out.append(f)
    return out


def refresh_counts(review: dict, folded, consensus: dict) -> dict:
    """汇总区计数由工具机械汇总，不许手填。"""
    folded = folded or []
    concerns = (consensus or {}).get("concerns") or []
    review["counts"] = {
        "findings": len(folded),
        "confirmed_error_open": len(open_confirmed_errors(folded)),
        "not_assessable": sum(1 for f in folded
                              if f.get("category") == "not_assessable"),
        "concerns": len(concerns),
        "consensus": sum(1 for c in concerns if c.get("consensus")),
    }
    return review["counts"]
