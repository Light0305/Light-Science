"""分档与证据卡渲染（草案 §三.5 / §五、JS-04 证据序、E4）。

分档纪律（写死）：
- 分档函数**只读 verified 字段**：未确认指标不参与分档（JS-02）；
  众包审稿周期不单独决定分档（E4）——约束核对时众包周期视为
  未确认，只用官方口径周期判超限；派生周期（JS-10）同样不
  参与约束判定。
- 证据序（JS-04）：先例 > scope > 主题 > 指标。只有刊名/指标
  支撑、无先例无 scope 核验的候选标 provisional（暂定），
  至多落 safety。
- 取卡排序（JS-D01，v1.1）：先过卡位证据量门槛（与入池门槛
  同构的三叉，schema.CARD_GATE_*），门槛内按复合键——覆盖
  检索式数优先、其次复合权（先例篇数乘以 ln(1+归一化率)，
  篇数加权压住小分母率值膨胀）、再篇数/率/刊名兜底。每刊的
  门槛判定与各因子落 ranking 分解块，卡面渲染排序因子行，
  逐项可溯。v1.0 的 rate_per_10k 单键排序已废（演示实测微型
  刊 1 篇先例率 270/万篇压过旗舰刊 7 篇/3 式）。
- 档是投稿策略分层、不是质量判定、不预测录用（草案边界）；
  challenge 无合格者时如实留空，不许凑数；空档的原因在
  「证据构成」段落字（JS-D06），不只留空档。
"""

from __future__ import annotations

import math
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


def passes_card_gate(cand: dict) -> tuple[bool, str]:
    """卡位证据量门槛（JS-D01）：返回 (是否过门, 依据落字)。

    只对有先例统计的候选适用；无先例统计者（检索补充/finder
    路）走暂定路径、门槛不适用。三叉与入池门槛同构，阈值以
    演示数据回放校准定版（构建单判断 J1）。
    """
    stats = cand.get("precedent")
    if not stats:
        return True, "无先例统计（暂定路径，门槛不适用）"
    n = stats.get("similar_works_n") or 0
    cov = stats.get("queries_covered") or 0
    rank = stats.get("best_rank")
    if n >= schema.CARD_GATE_MIN_SIMILAR:
        return True, f"先例篇数 {n} 不少于 {schema.CARD_GATE_MIN_SIMILAR}"
    if cov >= schema.CARD_GATE_MIN_QUERIES and \
            n >= schema.CARD_GATE_MIN_SIMILAR_WITH_QUERIES:
        return True, (f"覆盖 {cov} 式且先例 {n} 篇（覆盖叉）")
    if rank is not None and rank <= schema.CARD_GATE_TOP_RANK:
        return True, f"单式最佳名次 {rank} 不大于 {schema.CARD_GATE_TOP_RANK}"
    return False, (f"先例 {n} 篇 / 覆盖 {cov} 式 / 最佳名次 {rank}，"
                   "三叉全不沾，证据量不足以占卡位")


def ranking_breakdown(cand: dict) -> dict:
    """排序因子分解（JS-D01：逐项可溯，不许只给一个总分）。"""
    stats = cand.get("precedent") or {}
    n = stats.get("similar_works_n") or 0
    rate = stats.get("rate_per_10k")
    weight = n * math.log1p(rate) if rate is not None else 0.0
    gate_ok, gate_basis = passes_card_gate(cand)
    return {
        "card_gate": gate_ok,
        "gate_basis": gate_basis,
        "queries_covered": stats.get("queries_covered") or 0,
        "similar_works_n": n,
        "rate_per_10k": rate,
        "weight": round(weight, 4),
        "prestige": _prestige(cand),
        "risk_level": (cand.get("risk") or {}).get("level"),
    }


def _ranking_key(cand: dict):
    """复合排序键（JS-D01）：覆盖优先，其次复合权（篇数加权
    的对数率，压小分母膨胀），再篇数、率、刊名兜底。"""
    rank = cand.get("ranking") or ranking_breakdown(cand)
    rate = rank.get("rate_per_10k")
    return (-(rank.get("queries_covered") or 0),
            -(rank.get("weight") or 0.0),
            -(rank.get("similar_works_n") or 0),
            -(rate if rate is not None else -1.0),
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


def _apc_price(entry: dict):
    """APC 计价取值：结构化费用组读 list_price（JS-12），旧
    标量按标价兼容读（构建单判断 J2）。"""
    value = (entry or {}).get("value")
    if isinstance(value, dict):
        return value.get("list_price")
    return value


def constraint_flags(cand: dict, constraints: dict) -> list[str]:
    """约束冲突标记：全部只读 verified 指标（众包周期不算数，
    E4；派生周期同样不算数，JS-10）；政策冲突计入标记
    （JS-13：冲突是阻断项，先在卡面显形并封 challenge）。"""
    flags = []
    apc = verified_metric(cand, "apc")
    price = _apc_price(apc) if apc else None
    budget = constraints.get("apc_budget")
    if isinstance(price, (int, float)) and not isinstance(price, bool) \
            and isinstance(budget, (int, float)) and price > budget:
        flags.append("apc_over_budget")
    cycle = verified_metric(cand, "review_cycle")
    limit = constraints.get("review_cycle_limit")
    if cycle and cycle.get("provenance") != "crowd" \
            and cycle.get("derived") is not True \
            and isinstance(cycle.get("value"), (int, float)) \
            and isinstance(limit, (int, float)) \
            and cycle["value"] > limit:
        flags.append("cycle_over_limit")
    for item in cand.get("policy_checks") or []:
        if isinstance(item, dict) and item.get("status") == "conflict":
            flags.append("policy_conflict")
            break
    return flags


def scope_check_basis(cand: dict) -> str | None:
    """scope 核验方式（JS-06）：三项核验皆 verified 才算
    「实发核验」；只有 scope_fit 指标时是「文案核对」——Aims
    文案只是自述，不许把文案核对说成实发匹配。"""
    checks = cand.get("scope_checks") or {}
    done = [item for item in schema.SCOPE_CHECK_ITEMS
            if isinstance(checks.get(item), dict)
            and checks[item].get("status") == "verified"]
    if len(done) == len(schema.SCOPE_CHECK_ITEMS):
        return "实发核验（近 2 年实发 + 最近 3 期目录 + 文章类型核读）"
    if verified_metric(cand, "scope_fit") is not None:
        return "文案核对（Aims & Scope 页面，未做实发核验）"
    return None


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
        basis = scope_check_basis(cand)
        basis_txt = f"，核验方式：{basis}" if basis else ""
        reasons.append(f"官网 scope 核验：{scope['value']}"
                       f"（{scope['source_url']}，查询于 {scope['queried_at']}"
                       f"{basis_txt}）")
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
    """给过门候选分档；返回 {candidate_id: tier}（未入卡者不在内）。

    取卡两步（JS-D01）：先过卡位证据量门槛，未过门者留备选；
    门槛内按复合键排序取前 CARD_MAX。每刊落 ranking 分解块。
    """
    constraints = selection.get("constraints") or {}
    eligible = [c for c in selection.get("candidates") or []
                if is_eligible(c)]
    for cand in eligible:
        stats = cand.get("precedent")
        cand["provisional"] = not stats and \
            verified_metric(cand, "scope_fit") is None
        cand["flags"] = constraint_flags(cand, constraints)
        cand["match_reasons"] = match_reasons(cand)
        cand["ranking"] = ranking_breakdown(cand)
        cand["tier"] = None
    gated = [c for c in eligible if c["ranking"]["card_gate"]]
    selected = sorted(gated, key=_ranking_key)[:schema.CARD_MAX]
    tiers = {}
    for cand in selected:
        prestige = _prestige(cand)
        hard_flags = [f for f in cand["flags"]
                      if f in ("apc_over_budget", "cycle_over_limit",
                                "policy_conflict")]
        if cand["provisional"] or (prestige is not None and prestige <= 2):
            tier = "safety"
        elif prestige == 4 and not hard_flags:
            tier = "challenge"
        else:
            tier = "target"
        cand["tier"] = tier
        tiers[cand["candidate_id"]] = tier
    return tiers


def evidence_composition(selection: dict) -> dict:
    """本轮分档证据构成（JS-D06）：逐档数清分档靠什么撑——
    先例量、verified/unconfirmed 指标条数、白名单在册命中、
    众包与派生周期条数；数字全部由 selection 数据机械统计，
    与报告段落同源（render 读本函数结果，不另算一份）。"""
    def _blank():
        return {"journals": 0, "precedent_works": 0, "max_coverage": 0,
                "verified_metrics": 0, "unconfirmed_metrics": 0,
                "whitelist_hits": 0, "crowd_cycles": 0,
                "derived_cycles": 0, "policy_conflicts": 0}

    tiers = {t: _blank() for t in schema.CARD_TIERS}
    carded = [c for c in selection.get("candidates") or [] if c.get("tier")]
    for cand in carded:
        row = tiers[cand["tier"]]
        row["journals"] += 1
        stats = cand.get("precedent") or {}
        row["precedent_works"] += stats.get("similar_works_n") or 0
        row["max_coverage"] = max(row["max_coverage"],
                                  stats.get("queries_covered") or 0)
        metrics = (cand.get("verification") or {}).get("metrics") or {}
        for entry in metrics.values():
            if not isinstance(entry, dict):
                continue
            if entry.get("status") == "verified":
                row["verified_metrics"] += 1
                if entry.get("provenance") == "crowd":
                    row["crowd_cycles"] += 1
                if entry.get("derived") is True:
                    row["derived_cycles"] += 1
            elif entry.get("status") == "unconfirmed":
                row["unconfirmed_metrics"] += 1
        facts = cand.get("source_facts") or {}
        if facts.get("is_in_doaj") is True or facts.get("listed_in"):
            row["whitelist_hits"] += 1
        if "policy_conflict" in (cand.get("flags") or []):
            row["policy_conflicts"] += 1
    below_gate = sum(
        1 for c in selection.get("candidates") or []
        if c.get("ranking") and not c["ranking"].get("card_gate")
        and not c.get("tier"))
    return {"tiers": tiers,
            "carded_total": len(carded),
            "below_card_gate": below_gate,
            "source_type_excluded": len(
                selection.get("source_type_exclusions") or [])}


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
        if key == "review_cycle" and entry.get("derived") is True:
            extra += ("；派生估计（由实发文章日期倒推，方法："
                      f"{entry.get('derivation')}；与官方统计分列，"
                      "不参与约束判定，JS-10）")
        value = entry.get("value")
        if key == "apc" and isinstance(value, dict):
            value = _fee_group_text(value)
        elif key == "apc":
            value = f"{value}（仅标价，费用组未结构化，JS-12）"
        rows.append(f"| {key} | {value}{extra} "
                    f"| {entry.get('source_url')} "
                    f"| {entry.get('source_year')} / {entry.get('queried_at')} |")
    return rows


def _fee_group_text(fee: dict) -> str:
    """费用组卡面文本（JS-12）：全成本结构逐项显形，缺项如实
    写未披露/未知，不许只剩一个标价数字。"""
    price = fee.get("list_price")
    price_txt = (f"{price} {fee.get('currency') or ''}".strip()
                 if price is not None else "未披露")
    timing_map = {"at_submission": "投稿时", "after_acceptance": "录用后",
                  "at_publication": "发表时"}
    timing = timing_map.get(fee.get("charge_timing"), "未披露")
    extras = fee.get("extra_fees") or []
    extras_txt = ("、".join(
        f"{f.get('name')} {f.get('amount') or '未标价'}"
        f"{f.get('currency') or ''}".strip() for f in extras)
        if extras else "无登记")
    waiver = fee.get("waiver_available")
    waiver_txt = "有" if waiver is True else \
        ("无" if waiver is False else "未知")
    coverage_map = {"covered": "本单位协议覆盖",
                    "not_covered": "本单位协议未覆盖",
                    "unknown": "协议覆盖状态未知"}
    return (f"标价 {price_txt}；收费时点 {timing}；附加费 {extras_txt}；"
            f"减免 {waiver_txt}；"
            f"{coverage_map.get(fee.get('agreement_coverage'), '协议覆盖状态未知')}"
            "（标价不等于实付，JS-12）")


def _risk_notes(cand: dict) -> list[str]:
    risk = cand.get("risk") or {}
    notes = []
    for check in risk.get("checks") or []:
        if check.get("hit") is True:
            version_txt = ""
            if check.get("list_version") or check.get("list_year"):
                version_txt = (f"，名单版本 "
                               f"{check.get('list_version') or '未标'}"
                               f" / {check.get('list_year') or '年份未标'}")
            notes.append(f"{check.get('condition')}：命中"
                         f"（来源 {check.get('source')}，"
                         f"{check.get('source_ref') or '无版本标注'}"
                         f"{version_txt}，"
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
                if cand.get("source_detail") else "")]
    rank = cand.get("ranking") or {}
    if rank:
        rate = rank.get("rate_per_10k")
        lines.append(
            f"- 排序因子（JS-D01）：覆盖 {rank.get('queries_covered')} 式 / "
            f"先例 {rank.get('similar_works_n')} 篇 / 归一化率 "
            f"{rate if rate is not None else UNCONFIRMED} / 复合权 "
            f"{rank.get('weight')}；卡位门槛：{rank.get('gate_basis')}")
    lines += ["",
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
    license_block = cand.get("oa_license")
    if isinstance(license_block, dict):
        lines += ["", "**许可组（JS-12：OA 须核到许可层）**", "",
                  f"- OA 模型：{license_block.get('oa_model') or UNCONFIRMED}"
                  f"；许可类型：{license_block.get('license_type') or UNCONFIRMED}"
                  f"；作者保留权利：{license_block.get('author_rights_retained')}"
                  f"；自存档政策：{license_block.get('self_archiving') or UNCONFIRMED}"
                  f"（来源 {license_block.get('source_url')}，"
                  f"查询于 {license_block.get('queried_at')}）"]
    policies = [p for p in cand.get("policy_checks") or []
                if isinstance(p, dict)]
    if policies:
        lines += ["", "**政策核读（JS-13：逐刊现行页面，点名带回）**", ""]
        for item in policies:
            mark = "冲突（阻断项）" if item.get("status") == "conflict" \
                else item.get("status")
            lines.append(
                f"- {item.get('topic')}：{mark}——{item.get('finding') or ''}"
                f"（{item.get('source_url')}，访问于 "
                f"{item.get('accessed_at')}；快照过期须复核）")
    lines += ["", "**风险提示**", ""]
    notes = _risk_notes(cand)
    lines += [f"- {n}" for n in notes] or ["- 无命中项（clear）"]
    if cand.get("flags"):
        lines.append(f"- 约束冲突标记：{', '.join(cand['flags'])}"
                     "（verified 指标与政策冲突，JS-13）")
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
    lines += _composition_lines(selection)
    untiered = [c for c in selection.get("candidates") or []
                if not c.get("tier")]
    lines += ["## 四、未入卡候选（备选）", ""]
    if untiered:
        for cand in untiered:
            rank = cand.get("ranking") or {}
            gate_txt = ""
            if rank and not rank.get("card_gate"):
                gate_txt = f"，未过卡位门槛（{rank.get('gate_basis')}）"
            lines.append(f"- {cand.get('name')}（来源 {cand.get('source')}，"
                         f"风险 {((cand.get('risk') or {}).get('level'))}"
                         f"{gate_txt}）")
    else:
        lines.append("- 无")
    lines += ["", "## 五、已排除清单（只增不改留痕）", ""]
    excluded = selection.get("excluded") or []
    if excluded:
        for row in excluded:
            lines.append(f"- **{row.get('name')}**"
                         f"（{row.get('level')}，{row.get('at')}）："
                         + "；".join(row.get("reasons") or []))
    else:
        lines.append("- 无")
    lines += ["", "## 六、数据时效声明", "",
              "- 本报告全部指标为本次运行联网现查，未用模型记忆数值；",
              "- 每值带来源 URL、指标年份/版本与查询日期；查不到写"
              "「未确认」，未确认不加分、不参与分档；",
              "- 风险名单核查范围与不可用情况如实登记于 selection.yaml"
              "（risk.checks）；不存在「绝对安全」的表述。",
              "", "## 七、出版商 finder 人工复核清单（手工区，E2）", "",
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
    for row in selection.get("source_type_exclusions") or []:
        lines.append(f"- 来源类型排除（不入期刊候选池，JS-D03）："
                     f"{row.get('name')}（type={row.get('source_type')}，"
                     f"同题先例 {row.get('similar_works_n')} 篇，"
                     f"{row.get('queried_at')}）：{row.get('reason')}")
    lines.append("")
    return "\n".join(lines)


def _composition_lines(selection: dict) -> list[str]:
    """证据构成段渲染（JS-D06）：数字取自 evidence_composition
    （run_report 与 selection 同步落盘，报告与导出同源）。"""
    comp = selection.get("evidence_composition") or \
        evidence_composition(selection)
    lines = ["", "## 三、本轮分档证据构成（JS-D06）", "",
             "- 本段数清每档的推荐靠什么证据撑：当前开放数据条件"
             "下专有指标多为未确认，分档主要由先例证据与已核验"
             "指标驱动，三档不是完备评估，勿把档位当质量结论。",
             ""]
    for tier in schema.CARD_TIERS:
        row = comp["tiers"][tier]
        if row["journals"] == 0:
            lines.append(
                f"- **{tier}**：本档为空——本轮证据构成不足以支撑"
                f" {tier}（无候选同时满足该档的证据量与声望/约束"
                "条件），如实留空，不凑数。")
            continue
        lines.append(
            f"- **{tier}**：{row['journals']} 刊；先例 "
            f"{row['precedent_works']} 篇（覆盖最高 "
            f"{row['max_coverage']} 式）；verified 指标 "
            f"{row['verified_metrics']} 条 / 未确认 "
            f"{row['unconfirmed_metrics']} 条；白名单在册命中 "
            f"{row['whitelist_hits']} 刊；众包周期 "
            f"{row['crowd_cycles']} 条、派生周期 "
            f"{row['derived_cycles']} 条（均不单独决定分档）；"
            f"政策冲突 {row['policy_conflicts']} 刊。")
    lines.append(
        f"- 未过卡位证据量门槛留备选 {comp['below_card_gate']} 刊；"
        f"来源类型排除（非期刊）{comp['source_type_excluded']} 条"
        "（附录留痕）。")
    return lines


def run_report(root, today_str: str | None = None) -> dict:
    root = Path(root)
    selection = require_selection(root)
    if selection.get("status") not in ("gated", "decided", "handed_off"):
        raise GateError([f"状态 {selection.get('status')} 不许出报告"
                         "（须先过风险门 gated）"])
    today_str = today_str or today()
    tiers = assign_tiers(selection)
    selection["evidence_composition"] = evidence_composition(selection)
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
