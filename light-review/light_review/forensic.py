"""法医层编排（R2）：四方对账四边 + GRIM 族并账 + 人工裁决位。

纪律：
- 开跑前先验承接快照：上游漂移即 STALE 拒绝（RV-12）；
- findings.jsonl 只增不改：已有裁决留痕时拒绝重跑（先保护留痕，
  重跑请开新 round）；reconciliation/compatibility 是检查快照，可覆盖；
- GRIM 判败进发现账时只作旗标（flag_only）+ 算式证据，分类落
  confirmed_error 候选——须经人工裁决位确认或推翻（R2 硬度 a、RV-09）；
- 每边出覆盖自报（summary 行：应检/可检/not assessable/两层错误数），
  校验器按逐项行机械重算比对，不许手写汇总（RV-07）。
"""

from __future__ import annotations

from pathlib import Path

from . import checkers, schema
from .grim import run_grim
from .intake import snapshot_drift
from .project import (
    append_finding_rows, fold_findings, load_package, refresh_counts,
    save_compatibility, save_findings, save_reconciliation, save_review,
)
from .util import load_structured, read_jsonl, today


class ForensicError(Exception):
    def __init__(self, gaps):
        self.gaps = list(gaps)
        super().__init__("；".join(self.gaps))


def _load_yaml(path: Path):
    if not path.exists():
        return None
    return load_structured(path) or {}


def _upstream(root, review) -> dict:
    intake = review["intake"]
    mp = Path(intake["manuscript"]["package_path"])
    ap = Path(intake["analysis"]["package_path"])
    sections = {}
    sdir = mp / "sections"
    if sdir.is_dir():
        for p in sorted(sdir.glob("*.md")):
            sections[p.name] = p.read_text(encoding="utf-8")
    lock = _load_yaml(mp / "references.lock.json") or {}
    delivery = None
    if intake.get("figure"):
        delivery = _load_yaml(
            Path(intake["figure"]["package_path"]) / "delivery.yaml")
    return {
        "claims": (_load_yaml(mp / "claims_register.yaml") or {}).get("claims") or [],
        "numbers": (_load_yaml(mp / "numbers_ledger.yaml") or {}).get("numbers") or [],
        "figures_manifest": (_load_yaml(mp / "figures_manifest.yaml") or {}).get("figures") or [],
        "sections_text": sections,
        "lock_entries": lock.get("entries") or [],
        "audit_archive_present": (mp / "audit" / "audit_report.json").exists(),
        "conclusions": _load_yaml(ap / "conclusions.yaml") or {},
        "spec_results": read_jsonl(ap / "spec_results.jsonl"),
        "delivery": delivery,
    }


def run_forensic(root) -> dict:
    """跑法医全层并落三件（reconciliation / findings / compatibility）。"""
    root = Path(root)
    pkg = load_package(root)
    review = pkg["review"]
    if review is None:
        raise ForensicError(["评审包不存在（先 init）"])
    if not review.get("intake"):
        raise ForensicError(["承接快照未冻结（先 intake）"])
    drift = snapshot_drift(root)
    if drift:
        raise ForensicError(["承接快照漂移，本轮 STALE，拒绝在旧快照上开检："]
                            + drift)
    existing = pkg["findings"] or []
    if any(r.get("type") == "adjudication" for r in existing):
        raise ForensicError(
            ["findings 已有人工裁决留痕：法医层拒绝重跑覆盖留痕"
             "（重跑请开新 round）"])

    up = _upstream(root, review)
    conclusions = up["conclusions"]
    provenance = conclusions.get("number_provenance") or []
    line_ids = set()
    for cv in conclusions.get("claims_verdict") or []:
        line_ids |= set((cv.get("line_verdicts") or {}).keys())
    ledger_values = {str(n.get("value_as_printed"))
                     for n in up["numbers"]}

    all_checks, raw_findings = [], []
    edge_fns = [
        ("claims_evidence",
         lambda: checkers.check_claims_evidence(up["claims"], conclusions)),
        ("numbers_numbers",
         lambda: checkers.check_numbers_numbers(
             up["numbers"], up["sections_text"], up["spec_results"],
             provenance)),
        ("numbers_figures",
         lambda: checkers.check_numbers_figures(
             up["figures_manifest"], up["delivery"], ledger_values)),
        ("citations_claims",
         lambda: checkers.check_citations_claims(
             up["sections_text"], up["lock_entries"], up["claims"],
             line_ids, up["audit_archive_present"])),
    ]
    summaries = []
    for edge, fn in edge_fns:
        checks, findings = fn()
        all_checks += checks
        raw_findings += findings
        summaries.append(schema.edge_summary_row(
            edge,
            checked=len(checks),
            assessable=sum(1 for c in checks
                           if c["result"] != "not_assessable"),
            not_assessable=sum(1 for c in checks
                               if c["result"] == "not_assessable"),
            errors=sum(1 for c in checks if c["result"] == "error"),
            decision_errors=sum(1 for c in checks
                                if c["result"] == "decision_error")))

    # ---- GRIM 族并账（登记了被检汇总量才跑；未登记如实记未跑）
    summaries_reg = pkg["summaries"]
    grim_rows = []
    grim_registered = bool(summaries_reg and summaries_reg.get("entries"))
    if grim_registered:
        grim_rows = run_grim(summaries_reg["entries"])
        for row in grim_rows:
            if row["result"] == "incompatible":
                raw_findings.append({
                    "check_id": f"F-GRIM-{row['stat_id']}",
                    "edge": "grim_compatibility",
                    "category": "confirmed_error",
                    "layer": "inconsistency",
                    "flag_only": True,
                    "claim_pointer": None,
                    "evidence_pointer": f"summaries:{row['stat_id']}",
                    "raw": row.get("formula_evidence"),
                    "detail": f"汇总量 {row['stat_id']}（{row['kind']}）"
                              f"相容性判败：{row['detail']}",
                })
    save_compatibility(root, grim_rows)

    # ---- 发现落账（stable ID 按生成序；只增不改）
    finding_rows = []
    for i, f in enumerate(raw_findings):
        finding_rows.append(schema.finding_row(
            f"F{i + 1:03d}", f["check_id"], f["edge"], f["category"],
            f["layer"], flag_only=f.get("flag_only", False),
            claim_pointer=f.get("claim_pointer"),
            evidence_pointer=f.get("evidence_pointer"),
            raw=f.get("raw"), detail=f.get("detail")))
    save_findings(root, finding_rows)
    save_reconciliation(root, all_checks + summaries)

    review.setdefault("forensic_run", {})
    review["forensic_run"] = {
        "run_at": today(),
        "grim_registered": grim_registered,
        "grim_checked": len(grim_rows),
        "edges": [s["edge"] for s in summaries],
    }
    folded = fold_findings(finding_rows)
    refresh_counts(review, folded, pkg["consensus"])
    review["updated_at"] = today()
    save_review(root, review)
    return {
        "checks": len(all_checks),
        "findings": len(finding_rows),
        "summaries": summaries,
        "grim_checked": len(grim_rows),
        "grim_registered": grim_registered,
    }


def register_summaries(root, register_file) -> list:
    """登记 GRIM 被检汇总量并单独重跑相容性（findings 并账走 forensic）。

    登记文件形态：{entries: [{stat_id, kind, value, decimals, n, items,
    scale_type, parts}]}。登记副本落 forensic/summaries.yaml，下一次
    forensic 全跑时 GRIM 判败自动并入发现账。
    """
    from .project import save_summaries_registration
    root = Path(root)
    pkg = load_package(root)
    if pkg["review"] is None:
        raise ForensicError(["评审包不存在（先 init）"])
    data = load_structured(Path(register_file)) or {}
    entries = data.get("entries") if isinstance(data, dict) else data
    if not entries:
        raise ForensicError(["登记文件无 entries：无被检汇总量可登记"])
    save_summaries_registration(root, {"entries": entries})
    rows = run_grim(entries)
    save_compatibility(root, rows)
    return rows


def adjudicate_finding(root, finding_id, outcome, adjudicator, reason,
                       obligations=None) -> dict:
    """人工裁决位：给一条发现落裁决（追加行留痕，本体不改）。

    confirmed error 未裁决阻断 delivered（R2 硬度 a）；裁决须具名 +
    理由，匿名或无理由不许落（裁决是责任动作，不是橡皮图章）。
    obligations（v1.1 REV-D05）：裁决附带条件 [{text, finding_id}]
    随裁决同批落义务账，登记人沿用裁决人；finding_id 缺省挂本条发现。
    """
    root = Path(root)
    gaps = []
    if outcome not in schema.ADJUDICATION_OUTCOMES:
        gaps.append(f"裁决结论 {outcome!r} 不在词表 "
                    f"{schema.ADJUDICATION_OUTCOMES}")
    if not (adjudicator or "").strip():
        gaps.append("缺裁决人（具名）：人工裁决位不许匿名落字")
    if not (reason or "").strip():
        gaps.append("缺裁决理由：confirmed / overruled 都必须给理由")
    pkg = load_package(root)
    folded = fold_findings(pkg["findings"] or [])
    target = next((f for f in folded if f["finding_id"] == finding_id), None)
    if target is None:
        gaps.append(f"发现 {finding_id} 不存在")
    if gaps:
        raise ForensicError(gaps)
    row = schema.adjudication_row(finding_id, outcome, adjudicator, reason)
    append_finding_rows(root, [row])
    if obligations:
        from .obligations import register_from_adjudication
        specs = [{"text": o.get("text"),
                  "finding_id": o.get("finding_id") or finding_id}
                 for o in obligations]
        register_from_adjudication(root, specs, by=adjudicator)
    pkg = load_package(root)
    folded = fold_findings(pkg["findings"] or [])
    review = pkg["review"]
    refresh_counts(review, folded, pkg["consensus"])
    review["updated_at"] = today()
    save_review(root, review)
    return row
