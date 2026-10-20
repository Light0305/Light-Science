"""裁决义务账（v1.1，REV-D05）：附条件放行单独成账跟踪。

纪律：
- 义务落 forensic/obligations.jsonl，只增不改：登记行 + 状态事件行
  （fulfill / waive），与 findings 账同构，fold 出每条义务的现行状态；
- fulfilled 须落履行证据指针 + 具名；waived 须具名 + 理由——豁免是
  责任动作，无名无理由不许落（与人工裁决位同一纪律）；
- open 义务逐项在 delivered 门点名并阻断（gates 消费 open_obligations）：
  附条件放行不再是「放行但须补 X」说完就没人追。
"""

from __future__ import annotations

from pathlib import Path

from . import schema
from .project import load_package
from .util import dump_jsonl, read_jsonl, today

OBLIGATIONS_REL = "forensic/obligations.jsonl"


class ObligationError(Exception):
    def __init__(self, gaps):
        self.gaps = list(gaps)
        super().__init__("；".join(self.gaps))


def _rows(root) -> list:
    p = Path(root) / OBLIGATIONS_REL
    return read_jsonl(p) if p.exists() else []


def _save(root, rows) -> None:
    p = Path(root) / OBLIGATIONS_REL
    p.parent.mkdir(parents=True, exist_ok=True)
    dump_jsonl(p, rows)


def fold_obligations(rows) -> list:
    """折叠成现行义务表：每条 {义务登记, status, fulfilled/waived 留痕}。"""
    obligations: dict[str, dict] = {}
    order: list[str] = []
    for row in rows or []:
        if row.get("type") == "obligation":
            oid = row.get("obligation_id")
            entry = dict(row)
            entry["status"] = "open"
            entry["closure"] = None
            obligations[oid] = entry
            order.append(oid)
        elif row.get("type") == "obligation_event":
            oid = row.get("obligation_id")
            if oid in obligations:
                obligations[oid]["status"] = (
                    "fulfilled" if row.get("action") == "fulfill"
                    else "waived")
                obligations[oid]["closure"] = {
                    "action": row.get("action"),
                    "by": row.get("by"),
                    "reason": row.get("reason"),
                    "evidence_pointer": row.get("evidence_pointer"),
                    "at": row.get("at"),
                }
    return [obligations[o] for o in order]


def open_obligations(folded) -> list:
    """未履行义务（delivered 阻断集）。"""
    return [o for o in folded or [] if o.get("status") == "open"]


def register_obligation(root, text, *, finding_id=None, by=None) -> dict:
    """登记一条义务（裁决附带条件的主入口，亦可独立登记）。

    具名纪律与裁决位同构：登记人缺名、义务文本为空，一律拒绝。
    finding_id 给了就必须指向现存发现——义务不许挂空发现。
    """
    root = Path(root)
    gaps = []
    if not (text or "").strip():
        gaps.append("义务文本为空：附条件放行的条件必须落字")
    if not (by or "").strip():
        gaps.append("缺登记人（具名）：义务登记不许匿名落字")
    pkg = load_package(root)
    if pkg["review"] is None:
        gaps.append("评审包不存在（先 init）")
    if finding_id:
        from .project import fold_findings
        known = {f["finding_id"] for f in fold_findings(pkg["findings"] or [])}
        if finding_id not in known:
            gaps.append(f"关联发现 {finding_id} 不存在：义务不许挂空发现")
    if gaps:
        raise ObligationError(gaps)
    rows = _rows(root)
    seq = sum(1 for r in rows if r.get("type") == "obligation") + 1
    row = schema.obligation_row(f"OB{seq:03d}", text.strip(),
                                finding_id=finding_id, by=by.strip())
    rows.append(row)
    _save(root, rows)
    return row


def apply_obligation_event(root, obligation_id, action, *, by=None,
                           reason=None, evidence_pointer=None) -> dict:
    """履行 / 豁免一条义务（状态事件追加行，本体不改）。

    fulfill 须证据指针（履行要可核）；waive 须理由（豁免要留痕）；
    两者都须具名。已关闭的义务不许重复关闭。
    """
    root = Path(root)
    gaps = []
    if action not in ("fulfill", "waive"):
        gaps.append(f"义务动作 {action!r} 不在词表（fulfill / waive）")
    if not (by or "").strip():
        gaps.append("缺执行人（具名）：义务关闭不许匿名落字")
    if action == "fulfill" and not (evidence_pointer or "").strip():
        gaps.append("fulfill 须落履行证据指针：履行要可核，不许口头履行")
    if action == "waive" and not (reason or "").strip():
        gaps.append("waive 须落理由：豁免是责任动作，无理由不许关闭义务")
    rows = _rows(root)
    folded = fold_obligations(rows)
    target = next((o for o in folded
                   if o["obligation_id"] == obligation_id), None)
    if target is None:
        gaps.append(f"义务 {obligation_id} 不存在")
    elif target["status"] != "open":
        gaps.append(f"义务 {obligation_id} 已关闭（{target['status']}）："
                    "不许重复关闭，状态变更只走追加留痕")
    if gaps:
        raise ObligationError(gaps)
    row = schema.obligation_event_row(
        obligation_id, action, by=by.strip(),
        reason=(reason or "").strip() or None,
        evidence_pointer=(evidence_pointer or "").strip() or None)
    rows.append(row)
    _save(root, rows)
    return row


def register_from_adjudication(root, obligations, *, by) -> list:
    """adjudicate 的 --obligation 挂载点：逐条登记并返回登记行。

    obligations 为 [{text, finding_id}]；登记人沿用裁决人（同一责任
    动作、同一次具名），纪律细节走 register_obligation。
    """
    out = []
    for spec in obligations or []:
        out.append(register_obligation(
            root, spec.get("text"), finding_id=spec.get("finding_id"),
            by=by))
    return out
