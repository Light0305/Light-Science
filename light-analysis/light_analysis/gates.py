"""包级状态机：intake → checked → judged → graded → delivered。

逐段过门、任一不过即拦并逐项点名缺口（GateError.gaps）。
行级 undetermined/untested 是一等终态：不阻断包级流转，
但必须在判定总表里全量呈现、结论包如实计数。
复核不可用（REVIEW_UNAVAILABLE）→ 包落 blocked 态停 delivered 之前，
不许执行者自判自赦放行（约束 13、拍板③）。
"""

from __future__ import annotations

from pathlib import Path

from . import schema
from .project import (
    current_verdicts, load_package, refresh_counts, save_analysis,
)
from .render import render_report
from .specs import verify_ledger_hash
from .util import today
from .validate import validate_package

NEXT = {"intake": "checked", "checked": "judged",
        "judged": "graded", "graded": "delivered"}


class GateError(Exception):
    def __init__(self, gaps):
        self.gaps = list(gaps)
        super().__init__("；".join(self.gaps))


def _gate_checked(pkg):
    gaps = []
    analysis = pkg["analysis"]
    if not pkg["audit"]:
        gaps.append("缺 audit.json：承接可判性校验未落盘（先跑 intake）")
    elif pkg["audit"].get("failures"):
        gaps.append("audit 存在失败项：" + "；".join(pkg["audit"]["failures"]))
    if not analysis.get("execution_ref"):
        gaps.append("登记头承接区未冻结（execution_ref 为空）")
    if not analysis.get("correction_families"):
        gaps.append("校正族未声明")
    ledger = pkg["spec_ledger"] or {}
    ok, detail = verify_ledger_hash(ledger)
    if not ok:
        gaps.append(f"规格集账本未冻结或已篡改：{detail}")
    lines = (analysis.get("registry_snapshot") or {}).get("lines") or []
    if not lines:
        gaps.append("登记行快照为空：逐行可判性未点名")
    return gaps


def _gate_judged(pkg):
    gaps = []
    analysis = pkg["analysis"]
    rows = pkg["verdicts"] or []
    current = current_verdicts(rows)
    line_ids = (analysis.get("registry_snapshot") or {}).get("line_ids") or []
    for lid in line_ids:
        if lid not in current:
            gaps.append(f"登记行 {lid} 尚无现行判定行（不许缺行）")
    # 规格 × 判定矩阵账平：每 included 规格 × 每登记行须有结果或显式失败行
    ledger = pkg["spec_ledger"] or {}
    included = [s["spec_id"] for s in ledger.get("specs") or []
                if s.get("status") == "included"]
    have = {(r.get("spec_id"), r.get("registry_line_id"))
            for r in pkg["spec_results"] or []}
    for sid in included:
        for lid in line_ids:
            if (sid, lid) not in have:
                gaps.append(f"规格×判定矩阵未账平：缺 ({sid}, {lid}) 的结果行"
                            "（无结果须落显式失败行）")
    errors = validate_package(pkg["root"])
    gaps += [f"校验未过：{e}" for e in errors]
    return gaps


def _gate_graded(pkg):
    gaps = []
    analysis = pkg["analysis"]
    conclusions = pkg["conclusions"] or {}
    claim_ids = analysis.get("claim_ids") or []
    mapped = {cv.get("claim_id") for cv in conclusions.get("claims_verdict") or []}
    for cid in claim_ids:
        if cid not in mapped:
            gaps.append(f"主张 {cid} 缺 claims_verdict 映射")
    graded = {s.get("claim_id") for s in conclusions.get("strength") or []}
    for cid in claim_ids:
        if cid not in graded:
            gaps.append(f"主张 {cid} 缺强度分级（合成输入须逐项落字）")
    for st in conclusions.get("strength") or []:
        if not (st.get("inputs") or {}):
            gaps.append(f"主张 {st.get('claim_id')} 强度分级缺 inputs 合成输入")
    if not conclusions.get("boundaries"):
        gaps.append("结论包缺 boundaries（成立条件/不可外推/什么证据会改变判定）")
    if not conclusions.get("limitations"):
        gaps.append("结论包缺 limitations（结果期效度威胁只记局限不许倒填）")
    return gaps


def _gate_delivered(pkg):
    gaps = []
    analysis = pkg["analysis"]
    review = analysis.get("review") or {}
    if not review.get("review_status"):
        gaps.append("缺判定复核记录（review.review_status 为空）")
    elif review["review_status"] == "REVIEW_UNAVAILABLE":
        gaps.append("REVIEW_UNAVAILABLE：跨模型复核不可用，停 delivered 之前"
                    "（执行者不许自判自赦，约束 13）")
    conclusions = pkg["conclusions"] or {}
    prov_lines = {p.get("registry_line_id")
                  for p in conclusions.get("number_provenance") or []}
    for cv in conclusions.get("claims_verdict") or []:
        for lid in (cv.get("line_verdicts") or {}):
            if lid not in prov_lines:
                gaps.append(f"数字溯源表未覆盖登记行 {lid}（主张 {cv.get('claim_id')}）")
    return gaps


_GATES = {"checked": _gate_checked, "judged": _gate_judged,
          "graded": _gate_graded, "delivered": _gate_delivered}


def advance_package(root):
    """推进一段。返回新状态；不过门抛 GateError（逐项缺口）。

    REVIEW_UNAVAILABLE 拦 delivered 时包落 blocked 态并落原因，
    复核恢复后可从 blocked 续推（from_state 记在 blocked 字段）。
    """
    root = Path(root)
    pkg = load_package(root)
    analysis = pkg["analysis"]
    if analysis is None:
        raise GateError(["分析包不存在（先 init）"])
    status = analysis.get("status")
    if status == "delivered":
        raise GateError(["已 delivered，无后续状态"])
    from_state = (analysis.get("blocked") or {}).get("from_state") \
        if status == "blocked" else status
    target = NEXT.get(from_state)
    if target is None:
        raise GateError([f"状态 {status} 不可推进"])

    gaps = _GATES[target](pkg)
    if gaps:
        if target == "delivered" and any("REVIEW_UNAVAILABLE" in g for g in gaps):
            analysis["status"] = "blocked"
            analysis["blocked"] = {
                "from_state": from_state,
                "reason": "判定复核不可用（REVIEW_UNAVAILABLE）",
                "at": today(),
            }
            analysis.setdefault("status_history", []).append(
                {"state": "blocked", "at": today(),
                 "by": "light-analysis advance", "target": "delivered"})
            save_analysis(root, analysis)
        raise GateError(gaps)

    analysis["status"] = target
    analysis["blocked"] = None
    analysis.setdefault("status_history", []).append(
        {"state": target, "at": today(), "by": "light-analysis advance"})
    refresh_counts(analysis, pkg["verdicts"] or [])
    save_analysis(root, analysis)
    if target == "delivered":
        fresh = load_package(root)
        (root / "ANALYSIS_REPORT.md").write_text(
            render_report(fresh), encoding="utf-8")
    return target


def gate_gaps_for(root, target):
    """只读预演：返回推进到 target 的缺口清单（status 命令用，不落盘）。"""
    pkg = load_package(root)
    if pkg["analysis"] is None:
        return ["分析包不存在"]
    return _GATES[target](pkg)
