"""包级状态机：intake → forensic_checked → paneled → reported →
adjudicated → delivered（草案 §四）。

逐段过门、任一不过即拦并逐项点名缺口（GateError.gaps）。
阻断纪律（R2 硬度 a）：forensic confirmed error 未裁决时，
adjudicated 与 delivered 两道门都过不去，须人工裁决位逐条解除。
隔离降档（R1）：isolation_mode=degraded 时交付必须带降档声明。
上游漂移即 STALE：forensic_checked 起每道门先验承接快照。
"""

from __future__ import annotations

from pathlib import Path

from .intake import snapshot_drift
from .panel import verify_frozen
from .project import (
    fold_findings, load_package, open_confirmed_errors, save_review,
)
from .util import component_hash, today
from .validate import validate_package

NEXT = {"intake": "forensic_checked",
        "forensic_checked": "paneled",
        "paneled": "reported",
        "reported": "adjudicated",
        "adjudicated": "delivered"}


class GateError(Exception):
    def __init__(self, gaps):
        self.gaps = list(gaps)
        super().__init__("；".join(self.gaps))


def _drift_gaps(pkg):
    if (pkg["review"] or {}).get("intake"):
        drift = snapshot_drift(pkg["root"])
        return [f"承接快照漂移（STALE）：{d}" for d in drift]
    return []


def _gate_forensic_checked(pkg):
    gaps = []
    review = pkg["review"]
    if not review.get("intake"):
        gaps.append("承接快照未冻结（先 intake）")
        return gaps
    gaps += _drift_gaps(pkg)
    if pkg["reconciliation"] is None:
        gaps.append("缺 forensic/reconciliation.jsonl：法医层未跑（先 forensic）")
    if pkg["findings"] is None:
        gaps.append("缺 forensic/findings.jsonl：法医层未跑（先 forensic）")
    if pkg["compatibility"] is None:
        gaps.append("缺 forensic/compatibility.jsonl：GRIM 并账未落盘")
    if pkg["reconciliation"]:
        edges = {r.get("edge") for r in pkg["reconciliation"]
                 if r.get("type") == "summary"}
        from . import schema
        missing = [e for e in schema.FORENSIC_EDGES if e not in edges]
        if missing:
            gaps.append("法医四边覆盖自报缺边：" + "、".join(missing))
    return gaps


def _gate_paneled(pkg):
    gaps = _drift_gaps(pkg)
    seats = (pkg["seats"] or {}).get("seats") or []
    if not seats:
        gaps.append("无登记席位：评审组未组建（先 seat 登记）")
    for s in seats:
        if s.get("status") not in ("drafted", "frozen"):
            gaps.append(f"席位 {s.get('seat_id')} 尚无草稿（先 panel 落草稿）")
    if not (pkg["review"].get("isolation")):
        gaps.append("隔离模式未登记（intake 时应已落 isolation）")
    return gaps


def _gate_reported(pkg):
    gaps = _drift_gaps(pkg)
    seats = (pkg["seats"] or {}).get("seats") or []
    if not seats:
        gaps.append("无登记席位")
    for s in seats:
        if s.get("status") != "frozen":
            gaps.append(f"席位 {s.get('seat_id')} 报告未冻结（先 freeze）")
    gaps += [f"冻结件 STALE：{s}" for s in verify_frozen(pkg["root"])]
    if pkg["consensus"] is None:
        gaps.append("缺 consensus.yaml：共识与分歧账未生成（先 consensus）")
    # 领域门落点（Phase 2）：状态机不新增状态，领域门登记后其结果
    # 并入 reported 门——领域门与法医同为开评前的确定性检查层，
    # 报告冻结前必须齐（落点理由见 SKILL §6）。
    if (pkg["review"] or {}).get("domain"):
        if pkg["domain_gate"] is None:
            gaps.append("领域门已登记但缺 domain_gate.jsonl（先 domain）")
        elif not any(r.get("type") == "summary"
                     for r in pkg["domain_gate"]):
            gaps.append("domain_gate.jsonl 缺 summary 覆盖自报行")
        # 范式点名（v1.1 REV-D01，登记键触发口径）：条目带范式适用性
        # （范式已成领域判定承重件）而本包未登记范式 → 点名阻断，
        # 须先 domain --paradigm 登记并重跑领域门再冻结报告。
        domain_reg = pkg["review"]["domain"]
        if domain_reg.get("paradigm_required") \
                and not (pkg["review"].get("paradigm") or {}) \
                .get("paradigm"):
            gaps.append("范式登记缺失：覆盖层条目带范式适用性"
                        "（paradigms），范式已成领域判定承重件，"
                        "本包 paradigm 未登记（先 domain --paradigm "
                        "登记并重跑，REV-D01 第零层）")
    gaps += [f"校验未过：{e}" for e in validate_package(pkg["root"])]
    return gaps


def _unadjudicated_gaps(pkg):
    folded = fold_findings(pkg["findings"] or [])
    open_ce = open_confirmed_errors(folded)
    return [f"confirmed error {f['finding_id']} 未裁决"
            "（人工裁决位逐条解除，R2 硬度 a）" for f in open_ce]


def _phase2_adjudication_gaps(pkg):
    """Phase 2 入 adjudicated 门的件（meta 登记后生效）：meta 产物
    形态与登记一致 + 自审门已过且未过期（RV-13）。"""
    from .selfcheck import target_hash
    review = pkg["review"] or {}
    decision = review.get("decision") or {}
    gaps = []
    if pkg["meta_review"] is None:
        gaps.append("缺 reports/meta_review.md：meta 合成未落盘（先 meta）")
    mode = decision.get("mode")
    if mode == "full":
        if pkg["decision_md"] is None:
            gaps.append("decision 登记为 full 但缺 reports/decision.md")
    elif mode == "degraded":
        if pkg["problem_list"] is None:
            gaps.append("decision 登记为 degraded 但缺 "
                        "reports/problem_list.md")
        if pkg["decision_md"] is not None:
            gaps.append("degraded 形态下 reports/decision.md 存在："
                        "校准门不齐不许出决定建议（先 meta 重跑降级）")
    selfcheck = pkg["selfcheck"]
    if selfcheck is None:
        gaps.append("缺 reports/selfcheck.json：评审产物未过自审门"
                    "（先 selfcheck，RV-13）")
    else:
        if not selfcheck.get("passed"):
            failed = [t.get("test_id") for t in selfcheck.get("tests") or []
                      if t.get("result") != "pass"]
            gaps.append("自审门未过：" + "、".join(failed or ["?"])
                        + "（点名见 reports/selfcheck.json）")
        elif selfcheck.get("target_hash") != target_hash(pkg):
            gaps.append("自审已过期：meta/decision 在自审后被改动"
                        "（target_hash 不符，须重跑 selfcheck）")
    return gaps


def _gate_adjudicated(pkg):
    gaps = _drift_gaps(pkg)
    gaps += _unadjudicated_gaps(pkg)
    if (pkg["review"] or {}).get("decision"):
        gaps += _phase2_adjudication_gaps(pkg)
    return gaps


def _obligation_gaps(pkg):
    """义务账门（v1.1 REV-D05）：open 义务逐项点名并阻断交付。"""
    from .obligations import fold_obligations, open_obligations
    folded = fold_obligations(pkg["obligations"] or [])
    return [f"义务 {o['obligation_id']} 未履行（open）：{o.get('text')}"
            "（履行落证据或具名豁免后才许交付，REV-D05）"
            for o in open_obligations(folded)]


def _gate_delivered(pkg):
    gaps = _drift_gaps(pkg)
    gaps += _unadjudicated_gaps(pkg)
    gaps += _obligation_gaps(pkg)
    review = pkg["review"]
    iso = review.get("isolation") or {}
    if iso.get("mode") == "degraded" and \
            not (review.get("_pending_degradation_statement") or "").strip():
        gaps.append("隔离降档（degraded）交付须带降档声明"
                    "（deliver --degradation-statement）")
    gaps += [f"校验未过：{e}" for e in validate_package(pkg["root"])
             if "delivered" not in e]
    return gaps


_GATES = {"forensic_checked": _gate_forensic_checked,
          "paneled": _gate_paneled,
          "reported": _gate_reported,
          "adjudicated": _gate_adjudicated,
          "delivered": _gate_delivered}


def advance_package(root):
    """推进一段（delivered 除外，走 deliver）。不过门抛 GateError。"""
    root = Path(root)
    pkg = load_package(root)
    review = pkg["review"]
    if review is None:
        raise GateError(["评审包不存在（先 init）"])
    status = review.get("status")
    if status == "delivered":
        raise GateError(["已 delivered，无后续状态"])
    target = NEXT.get(status)
    if target is None:
        raise GateError([f"状态 {status} 不可推进"])
    if target == "delivered":
        raise GateError(["delivered 走 deliver 命令（须生成交付清单，"
                         "降档时须带降档声明）"])
    gaps = _GATES[target](pkg)
    if gaps:
        raise GateError(gaps)
    review["status"] = target
    review.setdefault("status_history", []).append(
        {"state": target, "at": today(), "by": "light-review advance"})
    review["updated_at"] = today()
    save_review(root, review)
    return target


def _render_delivery(pkg) -> str:
    review = pkg["review"]
    intake = review.get("intake") or {}
    folded = fold_findings(pkg["findings"] or [])
    delivery = review.get("delivery") or {}
    lines = [
        f"# 评审交付清单 — {review.get('review_id')}（round {review.get('round')}）",
        "",
        f"- 状态：delivered（{delivery.get('delivered_at')}）",
        f"- 承接稿件：{(intake.get('manuscript') or {}).get('manuscript_id')}"
        f"（快照哈希 {(intake.get('manuscript') or {}).get('package_hash', '')[:12]}…）",
        f"- 隔离模式：{(review.get('isolation') or {}).get('mode')}",
    ]
    if delivery.get("degradation_statement"):
        lines.append(f"- **降档声明**：{delivery['degradation_statement']}")
    lines += ["", "## 法医发现", ""]
    if folded:
        for f in folded:
            adj = f.get("adjudication")
            adj_txt = (f"裁决 {adj['outcome']}（{adj['adjudicator']}）"
                       if adj else "未裁决")
            lines.append(f"- {f['finding_id']} [{f['category']}/"
                         f"{f['layer']}] {f.get('detail')} — {adj_txt}")
    else:
        lines.append("- 无（在已登记检查项与敏感性范围内未发现问题）")
    lines += ["", "## 共识账", ""]
    concerns = (pkg["consensus"] or {}).get("concerns") or []
    if concerns:
        for c in concerns:
            lines.append(
                f"- {c['concern_id']} severity={c.get('severity')} "
                f"tally={c.get('tally')} consensus={c.get('consensus')}："
                f"{c.get('statement')}")
    else:
        lines.append("- 无 concern 登记")
    domain = review.get("domain")
    if domain:
        s = domain.get("summary") or {}
        lines += ["", "## 领域门", "",
                  f"- 条目 {s.get('checked', 0)}：命中 {s.get('hits', 0)}、"
                  f"未命中 {s.get('misses', 0)}、不适用 "
                  f"{s.get('not_applicable', 0)}（有效命中 "
                  f"{s.get('effective_hits', 0)}）"]
        fact_source = domain.get("fact_source") or {}
        if fact_source:
            lines.append(
                f"- 按刊事实：{fact_source.get('record_path')}"
                f"（verified_at {fact_source.get('verified_at')}，"
                f"状态 {fact_source.get('fact_status')}）")
    decision = review.get("decision")
    if decision:
        lines += ["", "## 决定建议", ""]
        if decision.get("mode") == "full":
            lines.append(f"- 形态 full：建议档位 {decision.get('band')}"
                         "（bounded 非编辑判断，校准门四件齐备）")
        else:
            lines.append("- 形态 degraded：校准门不齐，只出问题清单 + "
                         "风险分级，不给决定建议")
            for m in decision.get("calibration_missing") or []:
                lines.append(f"  - 缺件：{m}")
    handoff = review.get("handoff")
    if handoff:
        lines += ["", "## 回填清单", "",
                  f"- handoff_to_write（{handoff.get('items', 0)} 条）"
                  "已导出：采纳与执行由 Write 侧决定"]
    from .obligations import fold_obligations
    obligations = fold_obligations(pkg["obligations"] or [])
    if obligations:
        lines += ["", "## 义务账（裁决附带条件）", ""]
        for o in obligations:
            closure = o.get("closure") or {}
            if o["status"] == "fulfilled":
                tail = (f"履行（{closure.get('by')}，证据 "
                        f"{closure.get('evidence_pointer')}）")
            elif o["status"] == "waived":
                tail = (f"豁免（{closure.get('by')}，理由："
                        f"{closure.get('reason')}）")
            else:
                tail = "未履行"
            link = (f"，关联 {o['finding_id']}" if o.get("finding_id")
                    else "")
            lines.append(f"- {o['obligation_id']} [{o['status']}] "
                         f"{o.get('text')}{link} — {tail}")
    lines += ["", "## 未尽件（Phase 2）", ""]
    pending = review.get("phase2_pending") or []
    if pending:
        for item in pending:
            lines.append(f"- {item}：Phase 2 落地，本轮未产出")
    else:
        lines.append("- 无（Phase 2 件已全部落地）")
    lines.append("")
    return "\n".join(lines)


def deliver_package(root, degradation_statement=None) -> dict:
    """交付：过 delivered 门 → 落 delivery 区 + REVIEW_DELIVERY.md。

    confirmed error 未裁决在此被拦（阻断纪律的执行点）；降档声明
    在此落进登记头并进交付清单，做不到全规格就明说（R1）。
    """
    root = Path(root)
    pkg = load_package(root)
    review = pkg["review"]
    if review is None:
        raise GateError(["评审包不存在（先 init）"])
    if review.get("status") != "adjudicated":
        raise GateError([f"当前状态 {review.get('status')}，"
                         "须先到 adjudicated 才许 deliver"])
    if degradation_statement:
        review["_pending_degradation_statement"] = degradation_statement
    gaps = _GATES["delivered"](pkg)
    review.pop("_pending_degradation_statement", None)
    if gaps:
        raise GateError(gaps)
    iso = review.get("isolation") or {}
    delivery = {
        "delivered_at": today(),
        "degradation_statement": degradation_statement
        if iso.get("mode") == "degraded" else None,
    }
    review["delivery"] = delivery
    review["status"] = "delivered"
    review.setdefault("status_history", []).append(
        {"state": "delivered", "at": today(), "by": "light-review deliver"})
    review["updated_at"] = today()
    text = _render_delivery(pkg | {"review": review})
    delivery["manifest_hash"] = component_hash(
        {"review_id": review["review_id"], "round": review["round"],
         "delivered_at": delivery["delivered_at"],
         "findings": [f["finding_id"]
                      for f in fold_findings(pkg["findings"] or [])],
         "degradation_statement": delivery["degradation_statement"]})
    review["delivery"] = delivery
    save_review(root, review)
    (root / "REVIEW_DELIVERY.md").write_text(text, encoding="utf-8")
    return delivery


def gate_gaps_for(root, target):
    """只读预演：返回推进到 target 的缺口清单（status 命令用，不落盘）。"""
    pkg = load_package(root)
    if pkg["review"] is None:
        return ["评审包不存在"]
    return _GATES[target](pkg)
