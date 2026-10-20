"""状态机：draft → candidates_ready → verified → gated → decided
→ handed_off。每段跃迁有确定性门条件，缺口逐项点名，不许跳段。
"""

from __future__ import annotations

from pathlib import Path

from . import schema
from .project import load_selection, save_selection
from .util import today


class GateError(Exception):
    def __init__(self, gaps):
        self.gaps = list(gaps)
        super().__init__("；".join(self.gaps))


def require_selection(root) -> dict:
    selection = load_selection(root)
    if selection is None:
        raise GateError(["选刊包不存在（先 init）"])
    return selection


def transition_gaps(selection: dict, target: str) -> list[str]:
    """跃迁到 target 的缺口清单（空 = 可跃迁）。"""
    current = selection.get("status")
    if target not in schema.STATES:
        return [f"未知状态 {target!r}"]
    allowed = schema.TRANSITIONS.get(current, [])
    if target not in allowed:
        return [f"状态 {current} 不许直接跃迁到 {target}"
                f"（允许：{allowed or '无'}）"]
    gaps: list[str] = []
    if target == "candidates_ready":
        if not selection.get("fingerprint"):
            gaps.append("稿件指纹未落盘（先 fingerprint）")
        if not (selection.get("candidates") or []):
            gaps.append("候选池为空（先 precedent 生成或 add-candidate 登记）")
    elif target == "verified":
        for cand in selection.get("candidates") or []:
            if cand.get("verification") is None:
                gaps.append(f"候选 {cand.get('name')} 未登记核验块"
                            "（查不到也要落 attempted/skipped 四态）")
    elif target == "gated":
        for cand in selection.get("candidates") or []:
            if cand.get("risk") is None:
                gaps.append(f"候选 {cand.get('name')} 未过风险门")
    elif target == "decided":
        if not selection.get("decision"):
            gaps.append("未定刊（decision 未回填）")
    elif target == "handed_off":
        if not selection.get("handoff"):
            gaps.append("交接物未生成（handoff 未回填）")
    return gaps


def advance_to(root, target: str, by: str) -> dict:
    """在门条件满足时跃迁并落 status_history；不满足逐项点名。"""
    root = Path(root)
    selection = require_selection(root)
    gaps = transition_gaps(selection, target)
    if gaps:
        raise GateError(gaps)
    selection["status"] = target
    selection.setdefault("status_history", []).append(
        {"state": target, "at": today(), "by": by})
    save_selection(root, selection)
    return selection
