"""meta 合成与决定建议（R3/RV-14）：只消费冻结报告，校准门定形态。

- meta_review.md：共识账 + 分歧账的合成叙述，数据源只有冻结后的
  共识账、法医发现账与领域门结果——不引用未冻结草稿（RV-12）；
- decision.md：仅当校准门四件齐备 + 当版验证台报表在册时生成。
  内容是 bounded 的非编辑判断（内部建议，不声称编辑决定），分数
  形态由不对称合成给出：reject 向信号按 reject_weight 加权、
  accept 向按 accept_weight，先验修正 AI 评分通胀（RV-14）；
  封顶规则由代码逐条评估触发并钳制档位，逐条留痕；
- 缺一 → 自动降级：产 problem_list.md（问题清单 + 风险分级），
  登记头落 decision_mode=degraded + 缺件原文。降级时若已有
  decision.md（如配置后来漂移），删除并留痕——校验器钉死
  degraded 下 decision.md 存在即报错。
"""

from __future__ import annotations

from pathlib import Path

from . import schema
from .calibration import assess_calibration
from .project import (
    clear_pending, fold_findings, load_package, open_confirmed_errors,
    save_review,
)
from .util import today


class MetaError(Exception):
    def __init__(self, gaps):
        self.gaps = list(gaps)
        super().__init__("；".join(self.gaps))


# ---------------------------------------------------------------- 信号合成

def _concern_signals(pkg, asymmetry) -> dict:
    """不对称合成的数值形态：风险分（reject 向）与支持分（accept 向）。

    共识 concern 的严重度权重乘 reject_weight；非共识乘 1.0（未过
    共识门的信号不冒充强信号）。accept 向 = 未提出任何 concern 的
    席位数 × accept_weight。权重数值全部来自 calibration 登记。
    """
    concerns = (pkg["consensus"] or {}).get("concerns") or []
    rw = (asymmetry or {}).get("reject_weight", 1.0)
    aw = (asymmetry or {}).get("accept_weight", 1.0)
    risk = 0.0
    per_concern = []
    for c in concerns:
        w = schema.SEVERITY_WEIGHTS.get(c.get("severity") or "minor", 1)
        factor = rw if c.get("consensus") else 1.0
        risk += w * factor
        per_concern.append({"concern_id": c.get("concern_id"),
                            "severity": c.get("severity"),
                            "consensus": bool(c.get("consensus")),
                            "weight": w, "factor": factor,
                            "contribution": w * factor})
    raising = {s for c in concerns for s in c.get("raised_by") or []}
    seats = (pkg["seats"] or {}).get("seats") or []
    quiet_seats = [s.get("seat_id") for s in seats
                   if s.get("seat_id") not in raising]
    support = len(quiet_seats) * aw
    return {"risk": risk, "support": support, "net": risk - support,
            "per_concern": per_concern, "quiet_seats": quiet_seats,
            "reject_weight": rw, "accept_weight": aw}


def _band_for_net(net: float) -> str:
    if net <= 0:
        return "ready"
    if net <= 2:
        return "minor_revision"
    if net <= 6:
        return "major_revision"
    return "reject_risk"


# ---------------------------------------------------------------- 封顶触发

def _trigger_fires(trigger: str, pkg) -> bool:
    folded = fold_findings(pkg["findings"] or [])
    if trigger == "open_confirmed_error":
        return bool(open_confirmed_errors(folded))
    if trigger == "unverified_facts_present":
        domain = (pkg["review"] or {}).get("domain") or {}
        fact_source = domain.get("fact_source") or {}
        return fact_source.get("fact_status") == "unverified"
    if trigger == "clerical_only":
        concerns = (pkg["consensus"] or {}).get("concerns") or []
        if any(c.get("severity") != "minor" for c in concerns):
            return False
        if any(f.get("category") == "confirmed_error" for f in folded):
            return False
        for row in pkg["domain_gate"] or []:
            if row.get("type") == "domain_check" \
                    and row.get("result") == "hit" \
                    and row.get("effective") \
                    and row.get("severity_if_hit") in ("major", "critical"):
                return False
        return True
    return False


def apply_caps(band: str, pkg, caps) -> tuple[str, list]:
    """逐条评估封顶规则并钳制档位，返回 (band, 已触发规则留痕)。"""
    applied = []
    for cap in caps or []:
        trigger = cap.get("trigger")
        if not _trigger_fires(trigger, pkg):
            continue
        eff = cap.get("effect") or {}
        kind, cap_band = eff.get("kind"), eff.get("band")
        before = band
        if kind == "max_favorable" \
                and schema.band_rank(band) < schema.band_rank(cap_band):
            band = cap_band
        elif kind == "min_favorable" \
                and schema.band_rank(band) > schema.band_rank(cap_band):
            band = cap_band
        applied.append({"cap_id": cap.get("cap_id"), "trigger": trigger,
                        "effect": eff, "band_before": before,
                        "band_after": band})
    return band, applied


# ---------------------------------------------------------------- 风险分级（降级形态）

def problem_items(pkg) -> list:
    """降级问题清单的条目集：concern + 法医发现 + 领域门有效命中。

    风险分级由代码定：concern 取其 severity；法医 confirmed_error
    记 high、其余发现 medium、not_assessable 记 info；领域门命中
    取条目 severity_if_hit。模型不参与分级（RV-03）。
    """
    items = []
    for c in (pkg["consensus"] or {}).get("concerns") or []:
        items.append({
            "item_id": c.get("concern_id"), "kind": "concern",
            "risk": c.get("severity") or "minor",
            "statement": c.get("statement"),
            "consensus": bool(c.get("consensus")),
            "close_criterion": c.get("close_criterion")})
    for f in fold_findings(pkg["findings"] or []):
        risk = {"confirmed_error": "critical"}.get(
            f.get("category"), "major"
            if f.get("category") != "not_assessable" else "minor")
        items.append({
            "item_id": f.get("finding_id"), "kind": "forensic",
            "risk": risk, "statement": f.get("detail"),
            "consensus": None, "close_criterion": None})
    for row in pkg["domain_gate"] or []:
        if row.get("type") == "domain_check" \
                and row.get("result") == "hit" and row.get("effective"):
            items.append({
                "item_id": row.get("item_id"), "kind": "domain",
                "risk": row.get("severity_if_hit") or "minor",
                "statement": row.get("title") or row.get("detail"),
                "consensus": None, "close_criterion": None})
    order = {"critical": 0, "major": 1, "minor": 2}
    items.sort(key=lambda i: (order.get(i["risk"], 3), i["item_id"] or ""))
    return items


def overall_risk(items) -> str:
    risks = {i["risk"] for i in items}
    if "critical" in risks:
        return "high"
    if "major" in risks:
        return "medium"
    return "low"


# ---------------------------------------------------------------- 渲染

def _render_meta(pkg, narrative_lines) -> str:
    review = pkg["review"]
    concerns = (pkg["consensus"] or {}).get("concerns") or []
    consensus = [c for c in concerns if c.get("consensus")]
    divergent = [c for c in concerns if not c.get("consensus")]
    folded = fold_findings(pkg["findings"] or [])
    open_ce = open_confirmed_errors(folded)
    lines = [
        f"# Meta 评审综合 — {review.get('review_id')}（round {review.get('round')}）",
        "",
        f"- 生成：{today()}；数据源只有冻结报告、共识账、法医发现账与"
        "领域门结果（RV-12：不引用未冻结材料）。",
        "",
        "## 合成叙述",
        "",
    ]
    lines += narrative_lines
    lines += ["", "## 共识账", ""]
    if consensus:
        for c in consensus:
            lines.append(
                f"- {c['concern_id']}（severity={c.get('severity')}，"
                f"tally={c.get('tally')}）：{c.get('statement')}")
    else:
        lines.append("- 过共识门 concern 0 条。")
    lines += ["", "## 分歧账", ""]
    if divergent:
        for c in divergent:
            props = "、".join(f"{k}={v}" for k, v in
                              (c.get("severity_proposals") or {}).items())
            lines.append(
                f"- {c['concern_id']}（severity={c.get('severity')}，"
                f"代码取独立提案 MAX；提案：{props or '无'}）："
                f"{c.get('statement')}")
        lines.append("- 裁断口径：severity 只由代码计算（RV-05），"
                     "佐证数只影响排序，不抬级。")
    else:
        lines.append("- 分歧 concern 0 条。")
    lines += ["", "## 法医与领域门并账", ""]
    lines.append(f"- 法医发现 {len(folded)} 条，其中 confirmed error "
                 f"未裁决 {len(open_ce)} 条"
                 + (f"：{'、'.join(f['finding_id'] for f in open_ce)}"
                    if open_ce else ""))
    domain_rows = [r for r in pkg["domain_gate"] or []
                   if r.get("type") == "domain_check"]
    if domain_rows:
        hits = [r for r in domain_rows if r.get("result") == "hit"
                and r.get("effective")]
        lines.append(f"- 领域门 {len(domain_rows)} 条，有效命中 "
                     f"{len(hits)} 条"
                     + (f"：{'、'.join(r['item_id'] for r in hits)}"
                        if hits else ""))
    else:
        lines.append("- 领域门未跑（domain_gate 并账 0 条）")
    lines += ["", "## 优先修订序", ""]
    ordered = sorted(
        concerns,
        key=lambda c: (-schema.severity_rank(c.get("severity") or "minor"),
                       -(c.get("tally") or 0), c.get("concern_id") or ""))
    if ordered:
        for i, c in enumerate(ordered, 1):
            lines.append(
                f"- P{i} {c['concern_id']}（severity={c.get('severity')}）："
                f"关闭判据 {c.get('close_criterion') or '未登记'}")
    else:
        lines.append("- concern 0 条，无修订序。")
    lines.append("")
    return "\n".join(lines)


def _mechanical_narrative(pkg, signals) -> list:
    concerns = (pkg["consensus"] or {}).get("concerns") or []
    n_cons = sum(1 for c in concerns if c.get("consensus"))
    top = sorted(concerns,
                 key=lambda c: -schema.severity_rank(c.get("severity")
                                                     or "minor"))[:2]
    lines = [
        f"- 本轮共 {len(concerns)} 条 concern，其中 {n_cons} 条过共识门；"
        f"风险分 {signals['risk']:.1f}、支持分 {signals['support']:.1f}、"
        f"净分 {signals['net']:.1f}（不对称合成，meta 决定形态见校准门）。",
    ]
    for c in top:
        lines.append(f"- 最高严重度关切 {c['concern_id']}"
                     f"（severity={c.get('severity')}）："
                     f"{c.get('statement')}")
    if not concerns:
        lines.append("- 本轮无 concern 登记：合成叙述无对象，"
                     "评审产物以法医与领域门结果为准。")
    return lines


def _render_decision(pkg, band, signals, applied_caps, assessment) -> str:
    review = pkg["review"]
    bench = assessment.get("bench") or {}
    lines = [
        f"# 决定建议 — {review.get('review_id')}（round {review.get('round')}）",
        "",
        "> bounded 非编辑判断：这是投稿前内部评审的建议姿态，不声称"
        "任何编辑决定；最终投稿决定由作者作出（RV-14）。",
        "",
        f"## 建议档位：{band}",
        "",
        "## 不对称合成（数值登记可查）",
        "",
        f"- reject 权重 {signals['reject_weight']}、accept 权重 "
        f"{signals['accept_weight']}（calibration.yaml 不对称登记）",
        f"- 风险分 {signals['risk']:.1f} − 支持分 "
        f"{signals['support']:.1f} = 净分 {signals['net']:.1f}",
    ]
    for pc in signals["per_concern"]:
        lines.append(
            f"- {pc['concern_id']}：severity={pc['severity']} "
            f"权重 {pc['weight']} × 因子 {pc['factor']} "
            f"= {pc['contribution']:.1f}"
            f"（consensus={pc['consensus']}）")
    if signals["quiet_seats"]:
        lines.append(f"- 未提关切席位（accept 向）："
                     f"{'、'.join(signals['quiet_seats'])}")
    lines += ["", "## 封顶规则（逐条评估）", ""]
    if applied_caps:
        for cap in applied_caps:
            lines.append(
                f"- {cap['cap_id']}（trigger={cap['trigger']}）触发："
                f"{cap['band_before']} → {cap['band_after']}")
    else:
        lines.append("- 触发封顶规则 0 条。")
    lines += ["", "## 验证台背书", "",
              f"- bench 报表：reports/bench_report.json"
              f"（config_hash {bench.get('config_hash', '')[:12]}…，"
              f"当版在册且与当前配置一致）",
              f"- 判别力：误报率 "
              f"{(bench.get('false_positive') or {}).get('rate')}",
              ""]
    return "\n".join(lines)


def _render_problem_list(pkg, items, missing) -> str:
    review = pkg["review"]
    lines = [
        f"# 问题清单（降级形态）— {review.get('review_id')}"
        f"（round {review.get('round')}）",
        "",
        "- 校准门四件不齐，决定建议自动降级为问题清单 + 风险分级"
        "（R3 条件给：缺一不给决定建议）。",
        "- 缺件逐项：" + ("；".join(missing) if missing else "无"),
        f"- 整体风险分级：{overall_risk(items)}",
        "",
        "## 问题清单（按风险序）",
        "",
    ]
    if items:
        for i, it in enumerate(items, 1):
            lines.append(
                f"- {i}. {it['item_id']}（{it['kind']}，risk={it['risk']}）："
                f"{it['statement']}")
    else:
        lines.append("- 问题条目 0 条（在已登记检查范围内未发现问题）。")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------- 编排

def run_meta(root, narrative_file=None) -> dict:
    """meta 合成：冻结后运行，校准门决定 decision / problem_list 形态。"""
    root = Path(root)
    pkg = load_package(root)
    review = pkg["review"]
    if review is None:
        raise MetaError(["评审包不存在（先 init）"])
    if review.get("status") not in ("reported", "adjudicated", "delivered"):
        raise MetaError([f"当前状态 {review.get('status')}：meta 只消费"
                         "冻结报告，须先到 reported（freeze + consensus）"])
    if pkg["consensus"] is None:
        raise MetaError(["缺 consensus.yaml：共识账未生成（先 consensus）"])

    assessment = assess_calibration(root)
    calibration = pkg["calibration"] or {}
    signals = _concern_signals(pkg, calibration.get("asymmetry"))

    narrative = None
    if narrative_file:
        nf = Path(narrative_file)
        if not nf.exists():
            raise MetaError([f"合成叙述文件不存在：{nf}"])
        narrative = [ln for ln in
                     nf.read_text(encoding="utf-8").splitlines() if ln.strip()]
    meta_text = _render_meta(
        pkg, narrative or _mechanical_narrative(pkg, signals))
    (root / "reports" / "meta_review.md").write_text(meta_text,
                                                     encoding="utf-8")

    decision_path = root / "reports" / "decision.md"
    problem_path = root / "reports" / "problem_list.md"
    record = {"at": today(), "meta_review": "reports/meta_review.md",
              "calibration_complete": assessment["complete"],
              "calibration_missing": assessment["missing"]}
    if assessment["complete"]:
        band, applied = apply_caps(_band_for_net(signals["net"]), pkg,
                                   calibration.get("caps"))
        decision_path.write_text(
            _render_decision(pkg, band, signals, applied, assessment),
            encoding="utf-8")
        if problem_path.exists():
            problem_path.unlink()
        record.update({"mode": "full", "band": band,
                       "caps_applied": [c["cap_id"] for c in applied],
                       "decision_file": "reports/decision.md",
                       "problem_list_file": None})
    else:
        items = problem_items(pkg)
        problem_path.write_text(
            _render_problem_list(pkg, items, assessment["missing"]),
            encoding="utf-8")
        removed = False
        if decision_path.exists():
            decision_path.unlink()
            removed = True
        record.update({"mode": "degraded", "band": None,
                       "caps_applied": [],
                       "decision_file": None,
                       "problem_list_file": "reports/problem_list.md",
                       "decision_file_removed": removed,
                       "overall_risk": overall_risk(items)})
    review["decision"] = record
    clear_pending(review, "meta_review", "decision")
    review["updated_at"] = today()
    save_review(root, review)
    return record
