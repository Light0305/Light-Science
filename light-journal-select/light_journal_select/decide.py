"""定刊回填（decide，Phase 2）。

用户在报告三档证据卡里点定一刊后，把 decision 落回 selection：
{刊、日期、定刊人、理由} 四项缺一不可（理由是给未来复盘留的
决策痕，不是装饰字段）。状态 gated → decided。

硬度纪律（与风险门 E3 同口径，定刊口不许绕门）：
- 已被风险门排除的刊（excluded[] 留痕在册）不许定刊——无论
  hard_exclude 还是未放行的 quasi_hard，报错时点名排除级别
  与理由；
- 万一候选仍在池中但 risk.level 为 hard_exclude（数据被外力
  改坏的情形），同样拒绝；
- quasi_hard 候选只有带有效书面放行记录（gate.valid_override）
  才许定刊。
"""

from __future__ import annotations

from pathlib import Path

from .gate import valid_override
from .gates import GateError, advance_to, require_selection
from .project import find_candidate, save_selection
from .util import today

DECISION_FIELDS = ["candidate_id", "journal", "decided_at",
                   "decided_by", "reason"]


def apply_decide(root, candidate_ref: str, decided_by: str | None = None,
                 reason: str | None = None,
                 date_str: str | None = None) -> dict:
    """回填定刊并跃迁 decided。缺口逐项点名，不许半落盘。"""
    root = Path(root)
    selection = require_selection(root)
    if selection.get("status") != "gated":
        raise GateError([f"状态 {selection.get('status')} 不许定刊"
                         "（须先过风险门到 gated）"])
    gaps: list[str] = []
    if not decided_by:
        gaps.append("定刊人未填（--by，谁拍的板必须落字）")
    if not reason:
        gaps.append("定刊理由未填（--reason，决策痕必须留）")
    excluded_row = None
    cand = find_candidate(selection, candidate_ref)
    if cand is None:
        for row in selection.get("excluded") or []:
            if row.get("candidate_id") == candidate_ref or \
                    row.get("name") == candidate_ref:
                excluded_row = row
                break
    if excluded_row is not None:
        reasons = "；".join(excluded_row.get("reasons") or []) or "无理由留痕"
        gaps.append(
            f"候选 {excluded_row.get('name')} 已被风险门排除"
            f"（{excluded_row.get('level')}：{reasons}），不许定刊")
    elif cand is None:
        gaps.append(f"候选 {candidate_ref!r} 不在候选池中"
                    "（定刊只能从已过风险门的池内刊选）")
    else:
        risk = cand.get("risk") or {}
        level = risk.get("level")
        if level == "hard_exclude":
            gaps.append(f"候选 {cand.get('name')} 风险级 hard_exclude"
                        "（硬排除），用户确认不许放行、不许定刊（E3）")
        elif level == "quasi_hard":
            ok, ogaps = valid_override(risk.get("override"))
            if not ok:
                gaps.append(f"候选 {cand.get('name')} 为准硬门命中且无有效"
                            "书面放行记录，不许定刊（E3）：" + "；".join(ogaps))
    if gaps:
        raise GateError(gaps)
    decision = {
        "candidate_id": cand["candidate_id"],
        "journal": cand["name"],
        "decided_at": date_str or today(),
        "decided_by": decided_by,
        "reason": reason,
        "tier": cand.get("tier"),
        "risk_level": (cand.get("risk") or {}).get("level"),
    }
    selection["decision"] = decision
    save_selection(root, selection)
    advance_to(root, "decided", by="light-journal-select decide")
    return {"decision": decision, "status": "decided"}
