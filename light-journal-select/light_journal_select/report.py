"""分档与证据卡渲染（草案 §三.5 / §五、JS-04 证据序、E4）。

分档纪律（写死）：
- 分档函数**只读 verified 字段**：未确认指标不参与分档（JS-02）；
  众包审稿周期不单独决定分档（E4）——约束核对时众包周期视为
  未确认，只用官方口径周期判超限。
- 证据序（JS-04）：先例 > scope > 主题 > 指标。排序键以先例
  归一化率为主；只有刊名/指标支撑、无先例无 scope 核验的
  候选标 provisional（暂定），至多落 safety。
- 档是投稿策略分层、不是质量判定、不预测录用（草案边界）；
  challenge 无合格者时如实留空，不许凑数。
"""

from __future__ import annotations

from pathlib import Path

from . import schema
from .gates import GateError, require_selection
from .project import FILES, save_selection
from .util import dump_json, today

UNCONFIRMED = "未确认"


def verified_metric(cand: dict, key: str):
    """取 verified 指标条目；未确认/未登记一律 None（分档不许读）。"""
    block = cand.get("verification") or {}
    entry = (block.get("metrics") or {}).get(key)
    if isinstance(entry, dict) and entry.get("status") == "verified":
        return entry
    return None


def _prestige(cand: dict):
    """声望序数（仅 verified 分区）：Q1/1区=4 … Q4/4区=1。"""
    best = None
    jcr = verified_metric(cand, "quartile_jcr")
    if jcr:
        best = 5 - int(str(jcr["value"])[1])
    cas = verified_metric(cand, "quartile_cas")
    if cas:
        rank = 5 - int(str(cas["value"])[0])
        best = rank if best is None else max(best, rank)
    return best


def _evidence_key(cand: dict):
    stats = cand.get("precedent") or {}
    rate = stats.get("rate_per_10k")
    return (-(rate if rate is not None else -1.0),
            -(stats.get("similar_works_n") or 0),
            -(stats.get("queries_covered") or 0),
            cand.get("name") or "")


def is_eligible(cand: dict) -> bool:
    risk = cand.get("risk") or {}
    level = risk.get("level")
    if level in ("clear", "soft_warn"):
        return True
    if level == "quasi_hard":
        from .gate import valid_override
        ok, _ = valid_override(risk.get("override"))
        return ok
    return False


def constraint_flags(cand: dict, constraints: dict) -> list[str]:
    """约束冲突标记：全部只读 verified 指标（众包周期不算数，E4）。"""
    flags = []
    apc = verified_metric(cand, "apc")
    budget = constraints.get("apc_budget")
    if apc and isinstance(apc.get("value"), (int, float)) \
            and isinstance(budget, (int, float)) \
            and apc["value"] > budget:
        flags.append("apc_over_budget")
    cycle = verified_metric(cand, "review_cycle")
    limit = constraints.get("review_cycle_limit")
    if cycle and cycle.get("provenance") != "crowd" \
            and isinstance(cycle.get("value"), (int, float)) \
            and isinstance(limit, (int, float)) \
            and cycle["value"] > limit:
        flags.append("cycle_over_limit")
    return flags


def match_reasons(cand: dict) -> list[str]:
    """匹配理由由证据机械生成，不许凭空写推荐语。"""
    reasons = []
    stats = cand.get("precedent") or {}
    if stats.get("similar_works_n"):
        rate = stats.get("rate_per_10k")
        rate_txt = (f"归一化 {rate} 篇/万篇" if rate is not None
                    else "归一化率未取得（刊发文量未确认）")
        reasons.append(
            f"先例路：近 {schema.WINDOW_YEARS} 年同题论文 "
            f"{stats['similar_works_n']} 篇发在本刊（{rate_txt}，"
            f"覆盖 {stats.get('queries_covered')} 条检索式）")
    scope = verified_metric(cand, "scope_fit")
    if scope:
        reasons.append(f"官网 scope 核验：{scope['value']}"
                       f"（{scope['source_url']}，查询于 {scope['queried_at']}）")
    for key, label in (("quartile_jcr", "JCR 分区"), ("quartile_cas", "中科院分区"),
                       ("impact_factor", "影响因子")):
        entry = verified_metric(cand, key)
        if entry:
            reasons.append(f"{label} {entry['value']}"
                           f"（{entry['source_year']} 版，来源 "
                           f"{entry['source_url']}，查询于 {entry['queried_at']}）")
    if cand.get("source") == "search":
        reasons.append("检索补充路入池（先例稀疏，靠 scope/目录核验支撑）")
    if cand.get("source") == "finder_manual":
        reasons.append("出版商 finder 结果人工带回入池（已过同一核验与风险门）")
    return reasons


def assign_tiers(selection: dict) -> dict:
    """给过门候选分档；返回 {candidate_id: tier}（未入卡者不在内）。"""
    constraints = selection.get("constraints") or {}
    eligible = [c for c in selection.get("candidates") or []
                if is_eligible(c)]
    for cand in eligible:
        stats = cand.get("precedent")
        cand["provisional"] = not stats and \
            verified_metric(cand, "scope_fit") is None
        cand["flags"] = constraint_flags(cand, constraints)
        cand["match_reasons"] = match_reasons(cand)
        cand["tier"] = None
    selected = sorted(eligible, key=_evidence_key)[:schema.CARD_MAX]
    tiers = {}
    for cand in selected:
        prestige = _prestige(cand)
        hard_flags = [f for f in cand["flags"]
                      if f in ("apc_over_budget", "cycle_over_limit")]
        if cand["provisional"] or (prestige is not None and prestige <= 2):
            tier = "safety"
        elif prestige == 4 and not hard_flags:
            tier = "challenge"
        else:
            tier = "target"
        cand["tier"] = tier
        tiers[cand["candidate_id"]] = tier
    return tiers


# ------------------------------------------------------------ 渲染

def _metric_rows(cand: dict) -> list[str]:
    block = cand.get("verification") or {}
    metrics = block.get("metrics") or {}
    rows = []
    for key in schema.METRIC_KEYS:
        entry = metrics.get(key)
        if not isinstance(entry, dict):
            rows.append(f"| {key} | {UNCONFIRMED}（未登记） | — | — |")
            continue
        if entry.get("status") != "verified":
            rows.append(f"| {key} | {UNCONFIRMED}"
                        f"（source_status={entry.get('source_status')}）"
                        " | — | — |")
            continue
        extra = ""
        if key == "review_cycle" and entry.get("provenance") == "crowd":
            ann = entry.get("annotations") or {}
            extra = (f"；众包口径：{ann.get('basis')}，样本量："
                     f"{ann.get('sample_size')}（E4 三标注）")
        rows.append(f"| {key} | {entry.get('value')}{extra} "
                    f"| {entry.get('source_url')} "
                    f"| {entry.get('source_year')} / {entry.get('queried_at')} |")
    return rows


def _risk_notes(cand: dict) -> list[str]:
    risk = cand.get("risk") or {}
    notes = []
    for check in risk.get("checks") or []:
        if check.get("hit") is True:
            notes.append(f"{check.get('condition')}：命中"
                         f"（来源 {check.get('source')}，"
                         f"{check.get('source_ref') or '无版本标注'}，"
                         f"核查于 {check.get('checked_at')}）")
    if risk.get("level") == "quasi_hard" and risk.get("override"):
        ov = risk["override"]
        notes.append(f"准硬门经用户书面知情确认放行：{ov.get('confirmed_by')}"
                     f" 于 {ov.get('date')} 确认（原文留痕于 selection.yaml）")
    return notes


def _card(cand: dict) -> str:
    stats = cand.get("precedent") or {}
    lines = [f"### {cand.get('name')}",
             "",
             f"- 档位：**{cand.get('tier')}**"
             + ("（暂定：仅刊名/指标支撑，无先例与 scope 核验，JS-04）"
                if cand.get("provisional") else ""),
             f"- ISSN / eISSN：{cand.get('issn') or UNCONFIRMED} / "
             f"{cand.get('eissn') or UNCONFIRMED}",
             f"- 出版商：{cand.get('publisher') or UNCONFIRMED}",
             f"- 官网 / 指南：{cand.get('homepage_url') or UNCONFIRMED} / "
             f"{cand.get('guide_url') or UNCONFIRMED}",
             f"- 来源路：{cand.get('source')}"
             + (f"（{cand.get('source_detail')}）"
                if cand.get("source_detail") else ""),
             "",
             "**匹配理由（由证据生成）**",
             ""]
    reasons = cand.get("match_reasons") or []
    lines += [f"- {r}" for r in reasons] or [f"- {UNCONFIRMED}"]
    lines += ["", "**先例样例（真实论文，可复核）**", ""]
    precedents = (stats.get("precedents") or [])[:3]
    if precedents:
        for p in precedents:
            lines.append(f"- {p.get('title')}（{p.get('year')}）"
                         f"，DOI：{p.get('doi') or UNCONFIRMED}")
    else:
        lines.append(f"- {UNCONFIRMED}（无先例路样例）")
    lines += ["", "**指标（值 / 来源 / 年份·查询日期；未确认不加分）**",
              "", "| 指标 | 值 | 来源 | 年份 / 查询日期 |", "|---|---|---|---|"]
    lines += _metric_rows(cand)
    lines += ["", "**风险提示**", ""]
    notes = _risk_notes(cand)
    lines += [f"- {n}" for n in notes] or ["- 无命中项（clear）"]
    if cand.get("flags"):
        lines.append(f"- 约束冲突标记：{', '.join(cand['flags'])}"
                     "（仅据 verified 指标判定）")
    lines.append("")
    return "\n".join(lines)


def render_report(selection: dict, today_str: str) -> str:
    cons = selection.get("constraints") or {}
    lines = [f"# 选刊报告：{selection.get('title')}",
             "",
             f"- 选刊包：{selection.get('selection_id')}；生成日期：{today_str}"
             f"；状态：{selection.get('status')}",
             "- 边界声明：档位是投稿策略分层，不是期刊质量判定，"
             "本报告不预测录用；指标全部为联网现查并带来源与日期"
             "（JS-01），未确认字段不参与分档（JS-02）。",
             "", "## 一、约束清单", ""]
    for key in schema.CONSTRAINT_KEYS:
        value = cons.get(key)
        lines.append(f"- {key}：{value if value is not None else '未设'}")
    lines += ["", "## 二、三档证据卡", ""]
    tiered = [c for c in selection.get("candidates") or [] if c.get("tier")]
    for tier in schema.CARD_TIERS:
        group = [c for c in tiered if c["tier"] == tier]
        lines.append(f"## 档位：{tier}（{len(group)} 刊）")
        lines.append("")
        if not group:
            lines.append("（本档无合格候选，如实留空）")
            lines.append("")
        for cand in group:
            lines.append(_card(cand))
    untiered = [c for c in selection.get("candidates") or []
                if not c.get("tier")]
    lines += ["## 三、未入卡候选（备选）", ""]
    if untiered:
        for cand in untiered:
            lines.append(f"- {cand.get('name')}（来源 {cand.get('source')}，"
                         f"风险 {((cand.get('risk') or {}).get('level'))}）")
    else:
        lines.append("- 无")
    lines += ["", "## 四、已排除清单（只增不改留痕）", ""]
    excluded = selection.get("excluded") or []
    if excluded:
        for row in excluded:
            lines.append(f"- **{row.get('name')}**"
                         f"（{row.get('level')}，{row.get('at')}）："
                         + "；".join(row.get("reasons") or []))
    else:
        lines.append("- 无")
    lines += ["", "## 五、数据时效声明", "",
              "- 本报告全部指标为本次运行联网现查，未用模型记忆数值；",
              "- 每值带来源 URL、指标年份/版本与查询日期；查不到写"
              "「未确认」，未确认不加分、不参与分档；",
              "- 风险名单核查范围与不可用情况如实登记于 selection.yaml"
              "（risk.checks）；不存在「绝对安全」的表述。",
              "", "## 六、出版商 finder 人工复核清单（手工区，E2）", "",
              "- finder 只推自家刊（偏倚提示，JS-07）：Elsevier Journal "
              "Finder / Springer Journal Suggester / Wiley Journal Finder "
              "等结果不进自动候选池；如需人工复核，把下方文本粘贴到"
              "各 finder 自行查询，带回的刊名可用 add-candidate "
              "--source finder_manual 入池，过同一核验与风险门。",
              "", "```text",
              f"Title: {selection.get('title')}",
              f"Abstract: {(selection.get('manuscript') or {}).get('abstract') or UNCONFIRMED}",
              "```",
              "", "## 附录：指纹、检索式与先例路留痕", "",
              f"- 指纹：{selection.get('fingerprint')}",
              f"- 检索式：{selection.get('queries')}"]
    for run in selection.get("precedent_runs") or []:
        lines.append(f"- 先例查询 #{run.get('query_index')}："
                     f"{run.get('query')} → {run.get('status')}"
                     f"（返回 {run.get('works_returned')} 篇，"
                     f"证据 {run.get('evidence_file') or '无'}，"
                     f"{run.get('queried_at')}）")
    for miss in selection.get("precedent_near_misses") or []:
        lines.append(f"- 近失刊：{miss.get('name')}（相似 "
                     f"{miss.get('similar_works_n')} 篇，未过入门门槛）")
    lines.append("")
    return "\n".join(lines)


def run_report(root, today_str: str | None = None) -> dict:
    root = Path(root)
    selection = require_selection(root)
    if selection.get("status") not in ("gated", "decided", "handed_off"):
        raise GateError([f"状态 {selection.get('status')} 不许出报告"
                         "（须先过风险门 gated）"])
    today_str = today_str or today()
    tiers = assign_tiers(selection)
    save_selection(root, selection)
    text = render_report(selection, today_str)
    (root / FILES["report"]).write_text(text, encoding="utf-8")
    export = dict(selection)
    export["kind"] = "light-journal-select/selection-export"
    export["exported_at"] = today_str
    dump_json(root / FILES["selection_json"], export)
    counts = {t: sum(1 for v in tiers.values() if v == t)
              for t in schema.CARD_TIERS}
    return {"tiers": counts, "cards_total": len(tiers),
            "report": FILES["report"], "export": FILES["selection_json"],
            "status": selection.get("status")}
