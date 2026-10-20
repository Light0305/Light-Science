"""route：规则表驱动的下一步建议（只读，输入是 scan 的扫描结果）。

规则（与 SKILL.md §4 同源）：
- 硬门点名：阶段未达终态且门字段族有命中时先点名（字段族登记见
  layout.GATE_FIELD_FAMILIES，route 只消费登记过的族）：review 族看
  REVIEW_UNAVAILABLE 标记（或 analysis 的 blocked.reason 含之）、
  blocked_gate 族看统一字段 gate_id、return_block 族看 design 的
  打回/阻塞记录。缺字段 = 该族无命中，不据此断言无门、不猜。
- 下一步：沿流水线找第一个未达终态的阶段，给开工建议与理由；
  开工条件未满足时理由里写明缺的上游终态。
- 并行与横贯提示：figure 在 write drafted 后可并行；memory 收编
  触发点在各阶段定版/终态点，未建 memory 时提示先建。
- 扩展位点名（LD-02）：三包不进下一步计算；patent 案件的 blocked
  门（blocked_gate 族字段名变体）并入硬门点名，期限在 90 日内或
  已逾期时点名提醒；software-copyright 补正回路点名期限；crawler
  逐目标点名预检 blocked / 未预检 / 待确认 / 待补项 / 已过期与熔断
  状态（预检当前态按 crawler 的折叠语义读，见 scan）。
  收官判定只看主流水线（下一步为空且主线无挂起硬门），扩展位门
  不拦收官口径，但照常点名。
- 全部终态：报告全链收官与投稿后边界（真实审稿意见归 write W7）。
"""

from __future__ import annotations

from datetime import date

from .layout import GATE_FIX_POINTER, PIPELINE, STAGES
from .scan import any_gate, stage_gate_blocks, stage_statuses
from .statusmap import canonical

#: 专利期限点名窗口（日）：到期日在窗口内或已逾期即点名。答复期与
#: 优先权窗均以月计、错过即权利受损，90 日是进入处理队列的提前量
#: （LD-02 集成步判断 J3，SKILL §4 同步落字）。
DEADLINE_REMIND_DAYS = 90

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
                "family": "review_unavailable",
                "evidence": [h["value"] for h in hits] or ["blocked.reason"],
                "fix": GATE_FIX_POINTER,
            })
        for blk in stage_gate_blocks(ss):
            gates.append(_block_gate_entry(sid, blk))

    # 收官口径只看主线挂起门（扩展位门在下方并入点名，不拦收官）
    pipeline_blocked = bool(gates)

    # ---- 扩展位硬门点名：patent 案件 blocked（LD-02） ----
    ext = scan.get("extensions") or {}
    for item in (ext.get("patent") or {}).get("items", []):
        for blk in item.get("gate_blocks", []):
            gates.append(_block_gate_entry("patent", blk))

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
                    action = "暂缓 light-design（先回 idea 补定版）"
                    reason = ("idea 尚无 finalized_executable 定版卡"
                              "（conceptual 级不得直接开工），先完成 idea 定版")
                if sid == "write" and not _terminal_reached("journal-select", scan):
                    action = "暂缓 light-write（先完成选刊交接）"
                    reason = ("选刊前置位未完成：light-journal-select 尚未 "
                              "handed_off，先选刊定刊再开写")
            else:
                action = f"推进 light-{sid}"
                cur = _status_label(sid, stage_statuses(ss))
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

    # ---- 扩展位提示（LD-02：只点名，不给必经下一步） ----
    notes.extend(_extension_notes(scan, ext))

    done = nxt is None and not pipeline_blocked
    return {"gates": gates, "next": nxt, "notes": notes, "done": done}


def _extension_notes(scan: dict, ext: dict) -> list:
    """LD-02 扩展位点名：patent 期限、软著补正与出口提示、爬虫预检/熔断。"""
    notes = []

    # ---- patent：期限窗口点名 ----
    patent = ext.get("patent") or {}
    for item in patent.get("items", []):
        case = item.get("case_id") or item.get("path")
        for d in item.get("deadlines") or []:
            due_raw = str(d.get("due") or "")[:10]
            try:
                due = date.fromisoformat(due_raw)
            except ValueError:
                continue  # 到期日形态不合：status 已原样呈现，不猜
            delta = (due - date.today()).days
            label = d.get("label") or d.get("kind") or "期限"
            if delta < 0:
                notes.append(
                    f"专利期限已逾期：案件 {case} 的「{label}」到期日 "
                    f"{due_raw}（逾期 {-delta} 天）；错过期限可能导致"
                    "权利丧失，请立即按 light-patent 台账处理")
            elif delta <= DEADLINE_REMIND_DAYS:
                notes.append(
                    f"专利期限临近：案件 {case} 的「{label}」到期日 "
                    f"{due_raw}（剩 {delta} 天）；请提前按 light-patent"
                    " 台账推进，错过即权利受损")

    # ---- software-copyright：补正回路点名期限 ----
    copyright_ext = ext.get("software-copyright") or {}
    for item in copyright_ext.get("items", []):
        if item.get("status") != "correcting":
            continue
        corr = item.get("correction") or {}
        deadline = corr.get("deadline")
        if deadline:
            notes.append(
                f"软著补正回路：案件（{item.get('path')}）补正期限 "
                f"{deadline}（通知日 {corr.get('notice_date')}，"
                f"{len(corr.get('items') or [])} 项）；逾期未补正视为"
                "撤回，请在期限内修正并重新打包"
                "（light-software-copyright）")
        else:
            notes.append(
                f"软著补正回路：案件（{item.get('path')}）处于 "
                "correcting，补正期限未在登记头读到，请回 "
                "light-software-copyright 核对通知期限")

    # ---- 出口层提示：review 已交付且尚无案件时各给一条 ----
    review_done = _terminal_reached("review", scan)
    if review_done and not patent.get("found"):
        notes.append(
            "出口层扩展位提示：review 已交付，如需把成果固化为专利，"
            "可启动 light-patent（出口层扩展位，非流水线必经）")
    if review_done and not copyright_ext.get("found"):
        notes.append(
            "出口层扩展位提示：review 已交付；若本项目产出软件且已"
            "定版，可启动 light-software-copyright 做登记材料"
            "（出口层扩展位，非流水线必经）")

    # ---- crawler：逐目标点名预检与熔断状态 ----
    for ws in (ext.get("crawler") or {}).get("items", []):
        for t in ws.get("targets", []):
            tid = t["target_id"]
            if t.get("circuit_broken"):
                notes.append(
                    f"通道层扩展位：数据源 {tid} 已熔断"
                    f"（{t.get('circuit_reason') or '连续被拒'}），"
                    "抓取已停；解阻须按 light-crawler 规程具名 "
                    "unblock，不许绕过预检门")
                continue
            status = t.get("precheck_status")
            pc = t.get("precheck") or {}
            if status == "blocked":
                reasons = "；".join(pc.get("blocked_reasons") or []) \
                    or "见预检记录"
                notes.append(
                    f"通道层扩展位：数据源 {tid} 预检 blocked，未过"
                    f"合规预检不得抓取：{reasons}")
            elif status is None:
                notes.append(
                    f"通道层扩展位：数据源 {tid} 已登记但未预检，"
                    "未过预检不得抓取（light-crawler 预检门）")
            elif status == "pending_confirmation":
                notes.append(
                    f"通道层扩展位：数据源 {tid} 预检待具名确认"
                    "（高危通道），确认前不得抓取")
            elif status == "incomplete":
                missing = "；".join(pc.get("missing") or []) or "见预检记录"
                notes.append(
                    f"通道层扩展位：数据源 {tid} 预检 incomplete，"
                    f"缺项待补：{missing}")
            elif status == "expired":
                notes.append(
                    f"通道层扩展位：数据源 {tid} 预检已过期"
                    f"（expires_at {pc.get('expires_at')}），须重跑"
                    "预检后才可抓取")
    return notes


def _design_ready(scan: dict) -> bool:
    return any(s in STAGES["idea"]["design_ready"]
               for s in stage_statuses(scan["stages"]["idea"]))


def _status_label(stage: str, statuses: list) -> str:
    """当前状态呈现：原值 + 规范态标注；映射外的值只报原值（LD-03）。"""
    if not statuses:
        return "状态缺失"
    parts = []
    for s in sorted(set(statuses)):
        canon = canonical(stage, s)
        parts.append(f"{s}（规范态：{canon}）" if canon else s)
    return "、".join(parts)


def _block_gate_entry(stage: str, blk: dict) -> dict:
    """字段族门记录 → route 点名条目（gate / evidence / fix / pointer）。"""
    if blk["family"] == "blocked_gate":
        return {
            "stage": stage,
            "gate": f"{stage} 门（blocked_gate：{blk['gate_id']}）",
            "family": "blocked_gate",
            "evidence": [blk.get("detail") or blk["gate_id"]],
            "fix": blk.get("fix_pointer")
                   or "按登记头 blocked_gate 的解法指针处理；无指针时"
                      "回该包 SKILL 查该门规程，总控不代办、不猜解法",
            "pointer": blk.get("fix_pointer"),
        }
    # return_block 族（design）：returned 给缺项指针，blocked 给解阻条件
    if blk.get("kind") == "returned":
        names = [f"{it.get('item') or '（未命名项）'}"
                 f"（需要：{it.get('needed') or '见打回单'}）"
                 for it in blk["open_items"]]
        return {
            "stage": stage,
            "gate": "design 承接打回门（returned 携缺项清单）",
            "family": "return_block",
            "evidence": [f"未回补缺项 {len(names)} 条"],
            "fix": "按 design.yaml 的 return_record.returned_items 逐项"
                   "回补，回 draft 后重走承接（light-design 打回规程）",
            "pointer": "缺项：" + "；".join(names),
        }
    return {
        "stage": stage,
        "gate": "design 阻塞门（blocked，外部条件未备）",
        "family": "return_block",
        "evidence": [blk.get("reason") or "block_record 未填 reason"],
        "fix": "满足解阻条件后回受阻前状态（light-design 阻塞规程）",
        "pointer": f"解阻条件：{blk.get('unblock_condition')}"
                   if blk.get("unblock_condition") else None,
    }
