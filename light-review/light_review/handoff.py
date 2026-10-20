"""concern 回填清单导出（R6 接口）：Review 只出清单，不出补丁。

产物 handoff_to_write.md / .json，按 concern stable ID 逐条：
- severity 是导出时按 proposals 代码重算的值（不信登记头手填）；
- 双指针锚（claim_pointer / evidence_pointer）原样带出，缺位标
  None 不许编造（D-R03）；
- 建议动作分类由登记的机械规则定，逐条带 action_basis 留痕：
  证据指针命中法医发现 → 按其分类/层定（conclusion_flip 或
  provenance_gap / unresolved_input 须补新证据，其余可在正文修）；
  双指针齐 → 正文可修；只有证据侧 → 须补新证据；只有主张侧 →
  正文可修；双指针皆缺 → 须作者裁决；
- 条目字段是白名单（schema.HANDOFF_ITEM_FIELDS）：结构上没有
  安放稿件正文改写段落的位置，校验器按白名单 + 长度上限钉死。

Write 侧决定采纳与执行；Review 不直接产稿件补丁、不回注。
"""

from __future__ import annotations

from pathlib import Path

from . import schema
from .project import (
    clear_pending, fold_findings, load_package, save_review,
)
from .util import dump_json, today

_FINDING_KINDS_NEEDING_EVIDENCE = ("provenance_gap", "unresolved_input")


class HandoffError(Exception):
    def __init__(self, gaps):
        self.gaps = list(gaps)
        super().__init__("；".join(self.gaps))


def classify_action(concern, findings_by_id) -> tuple[str, str]:
    """建议动作分类（机械规则，返回 (action_class, action_basis)）。"""
    pointers = concern.get("pointers") or {}
    claim_pointer = pointers.get("claim_pointer")
    evidence_pointer = pointers.get("evidence_pointer")
    for fid, finding in findings_by_id.items():
        if evidence_pointer and fid in str(evidence_pointer):
            if finding.get("layer") == "conclusion_flip" \
                    or finding.get("category") \
                    in _FINDING_KINDS_NEEDING_EVIDENCE:
                return "needs-new-evidence", \
                    f"forensic:{fid}:{finding.get('category')}/" \
                    f"{finding.get('layer')}（结论翻转或证据缺口，须补新证据）"
            return "fixable-in-text", \
                f"forensic:{fid}:{finding.get('category')}（正文侧可修）"
    if claim_pointer and evidence_pointer:
        return "fixable-in-text", "pointers_complete（双指针齐，正文侧可修）"
    if evidence_pointer:
        return "needs-new-evidence", "evidence_side_only（主张侧无锚，须先补证据）"
    if claim_pointer:
        return "fixable-in-text", "claim_side_only（证据侧无锚，正文侧可修）"
    return "needs-author-decision", "no_pointers（双指针皆缺，须作者裁决）"


def build_items(pkg) -> list:
    """按白名单组装回填条目：字段之外一律不带出。"""
    findings_by_id = {f.get("finding_id"): f
                      for f in fold_findings(pkg["findings"] or [])}
    items = []
    for c in (pkg["consensus"] or {}).get("concerns") or []:
        pointers = c.get("pointers") or {}
        action_class, basis = classify_action(c, findings_by_id)
        items.append({
            "concern_id": c.get("concern_id"),
            # severity 导出时代码重算，不信共识账里的落字（RV-05）
            "severity": schema.computed_severity(
                c.get("severity_proposals") or {}),
            "statement": c.get("statement"),
            "claim_pointer": pointers.get("claim_pointer"),
            "evidence_pointer": pointers.get("evidence_pointer"),
            "action_class": action_class,
            "action_basis": basis,
            "source_seats": list(c.get("raised_by") or []),
            "consensus": bool(c.get("consensus")),
            "close_criterion": c.get("close_criterion"),
        })
    return items


def _render_md(review, payload) -> str:
    lines = [
        f"# 回填清单（Review → Write）— {review.get('review_id')}"
        f"（round {review.get('round')}）",
        "",
        f"- 生成：{payload['generated_at']}；条目 {len(payload['items'])} 条；"
        f"决定形态：{payload.get('decision_mode') or '未登记'}",
        "- 本清单只列建议修订（双指针 + 严重度 + 关闭判据），采纳与"
        "执行由 Write 侧决定；Review 不产稿件补丁、不回注（R6）。",
        "",
    ]
    if payload["items"]:
        for it in payload["items"]:
            lines.append(
                f"- {it['concern_id']}（severity={it['severity']}，"
                f"consensus={it['consensus']}，"
                f"动作={it['action_class']}）：{it['statement']}")
            lines.append(
                f"  - 锚：claim={it['claim_pointer']}；"
                f"evidence={it['evidence_pointer']}；"
                f"来源席位 {'、'.join(it['source_seats'])}；"
                f"关闭判据 {it['close_criterion'] or '未登记'}")
    else:
        lines.append("- 无 concern 条目。")
    lines.append("")
    return "\n".join(lines)


def run_export(root) -> dict:
    """导出回填清单（.json 权威 + .md 渲染），登记头落 handoff 区。"""
    root = Path(root)
    pkg = load_package(root)
    review = pkg["review"]
    if review is None:
        raise HandoffError(["评审包不存在（先 init）"])
    if pkg["consensus"] is None:
        raise HandoffError(["缺 consensus.yaml：无 concern 可回填"
                            "（先 consensus）"])
    items = build_items(pkg)
    payload = {
        "kind": "light-review/handoff-to-write",
        "version": 1,
        "review_id": review.get("review_id"),
        "round": review.get("round"),
        "generated_at": today(),
        "decision_mode": (review.get("decision") or {}).get("mode"),
        "items": items,
    }
    dump_json(root / "handoff_to_write.json", payload)
    (root / "handoff_to_write.md").write_text(
        _render_md(review, payload), encoding="utf-8")
    review["handoff"] = {"exported_at": payload["generated_at"],
                         "items": len(items),
                         "files": ["handoff_to_write.md",
                                   "handoff_to_write.json"]}
    clear_pending(review, "handoff_to_write")
    review["updated_at"] = today()
    save_review(root, review)
    return payload
