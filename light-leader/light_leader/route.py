"""route：规则表驱动的下一步建议（只读，输入是 scan 的扫描结果）。

规则（与 SKILL.md §4 同源）：
- 硬门点名：阶段未达终态且登记头带 REVIEW_UNAVAILABLE 标记（或
  analysis 的 blocked.reason 含之）时，先点名其门与解法指针。
- 下一步：沿流水线找第一个未达终态的阶段，给开工建议与理由；
  开工条件未满足时理由里写明缺的上游终态。
- 并行与横贯提示：figure 在 write drafted 后可并行；memory 收编
  触发点在各阶段定版/终态点，未建 memory 时提示先建。
- 全部终态：报告全链收官与投稿后边界（真实审稿意见归 write W7）。
"""

from __future__ import annotations

from .layout import GATE_FIX_POINTER, PIPELINE, STAGES
from .scan import any_gate, stage_statuses

_GATE_NAMES = {
    "idea": "idea 定版硬门（跨模型判定）",
    "design": "design 冻结门（Stage-1 五条 + 跨家族复核）",
    "analysis": "analysis 交付门（判定复核）",
    "write": "write 定版复核门",
}


def _terminal_reached(stage: str, scan: dict) -> bool:
    term = STAGES[stage]["terminal"]
    if not term:
        return False
    return any(s in term for s in stage_statuses(scan["stages"][stage]))


def _literature_ready(scan: dict) -> bool:
    lit = scan["stages"]["literature"]
    return any(it.get("papers", 0) > 0 for it in lit.get("items", []))


def route(scan: dict) -> dict:
    stages = scan["stages"]
    gates, notes = [], []

    # ---- 硬门点名（未达终态且带标记的阶段） ----
    for sid in PIPELINE:
        ss = stages[sid]
        if not ss["found"] or _terminal_reached(sid, scan):
            continue
        hits = any_gate(ss)
        blocked_hit = any(
            "REVIEW_UNAVAILABLE" in (it.get("blocked_reason") or "")
            for it in ss.get("items", []))
        if hits or blocked_hit:
            gates.append({
                "stage": sid,
                "gate": _GATE_NAMES.get(sid, f"{sid} 复核门"),
                "evidence": [h["value"] for h in hits] or ["blocked.reason"],
                "fix": GATE_FIX_POINTER,
            })

    # ---- 下一步（流水线第一个未达终态的阶段） ----
    nxt = None
    if not _literature_ready(scan):
        nxt = {"stage": "literature", "action": "启动 light-literature",
               "reason": "文献索引不存在或尚无入库篇目；全链自文献起步，"
                         "先走 Find 线检索核实并入库精读"}
    else:
        for sid in PIPELINE[1:]:
            if _terminal_reached(sid, scan):
                continue
            ss = stages[sid]
            spec = STAGES[sid]
            if not ss["found"]:
                action = f"开工 light-{sid}"
                reason = f"上游已就位而本阶段尚无登记头；开工条件：{spec['opens_when']}"
                if sid == "design" and not _design_ready(scan):
                    reason = ("idea 尚无 finalized_executable 定版卡"
                              "（conceptual 级不得直接开工），先完成 idea 定版")
                if sid == "write" and not _terminal_reached("journal-select", scan):
                    reason = ("选刊前置位未完成：light-journal-select 尚未 "
                              "handed_off，先选刊定刊再开写")
            else:
                action = f"推进 light-{sid}"
                cur = "、".join(sorted(set(stage_statuses(ss)))) or "状态缺失"
                reason = f"本阶段进行中（当前状态：{cur}），终态为 {'/'.join(spec['terminal'])}"
            nxt = {"stage": sid, "action": action, "reason": reason}
            break

    # ---- 并行提示：figure 可在 write drafted 后并行 ----
    w = stage_statuses(stages["write"])
    if any(s in ("drafted", "audited") for s in w) \
            and not _terminal_reached("figure", scan):
        notes.append("figure 可并行：write 已 drafted，light-figure 可按 "
                     "figures_manifest 开工，不必等 write 定版")

    # ---- memory 横贯提示 ----
    mem = stages["memory"]
    done_stages = [s for s in PIPELINE if _terminal_reached(s, scan)]
    if not mem["found"]:
        notes.append("memory 未建：任一阶段定版点即收编触发点，建议先在 "
                     "memory/ 下用 light-memory 建包，再逐阶段 ingest 收编"
                     "（已达终态阶段：" + ("、".join(done_stages) or "暂无") + "）")
    elif done_stages:
        notes.append("memory 收编触发点：已达终态的阶段（"
                     + "、".join(done_stages)
                     + "）在各自定版点应已由 light-memory ingest 收编；"
                       "以 memory.yaml 的 watermarks 核对是否漏收")

    done = nxt is None and not gates
    return {"gates": gates, "next": nxt, "notes": notes, "done": done}


def _design_ready(scan: dict) -> bool:
    return any(s in STAGES["idea"]["design_ready"]
               for s in stage_statuses(scan["stages"]["idea"]))
