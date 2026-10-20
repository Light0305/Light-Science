"""校验器：评审包全部纪律的确定性核查（只拦不赦）。

每条纪律对应 REDESIGN-DRAFT / LEARNING 的一条硬约束，逐条有正反例测试。
本模块只做结构与纪律校验——不跑检查器、不产生任何评审判断。
重点钉死三件事：边级覆盖自报与逐项行机械对账（RV-07）、两层分类
不许越层（RV-08）、共识门与 severity 代码计算（RV-05）、冻结防篡改
（RV-12）、降档声明与裁决纪律（R1/R2）。
"""

from __future__ import annotations

from pathlib import Path

from . import schema
from .intake import snapshot_drift
from .panel import verify_frozen
from .project import fold_findings, load_package, open_confirmed_errors


def _validate_review_head(errors, pkg):
    review = pkg["review"]
    if review is None:
        errors.append("缺 review.yaml（先 init）")
        return
    status = review.get("status")
    if status not in schema.PKG_STATES:
        errors.append(f"登记头 status {status!r} 不在状态词表")
    intake = review.get("intake")
    if intake is not None:
        for part in ("manuscript", "analysis"):
            if not intake.get(part):
                errors.append(f"承接快照缺 {part}（必承件不可缺）")
        iso = review.get("isolation") or {}
        if iso.get("mode") == "degraded" and \
                not (iso.get("reason") or "").strip():
            errors.append("isolation_mode=degraded 但未登记理由"
                          "（R1 硬纪律：做不到全规格就明说）")
        if iso.get("mode") not in schema.ISOLATION_MODES:
            errors.append(f"隔离模式 {iso.get('mode')!r} 不在词表")
    # 范式登记（v1.1 REV-D01）：词表 + 判定依据落字
    paradigm = review.get("paradigm")
    if paradigm is not None:
        if paradigm.get("paradigm") not in schema.PARADIGMS:
            errors.append(f"范式登记 {paradigm.get('paradigm')!r} "
                          f"不在范式词表 {schema.PARADIGMS}")
        if not (paradigm.get("basis") or "").strip():
            errors.append("范式登记缺判定依据（basis 落字，REV-D01）")


def _validate_forensic(errors, pkg):
    rows = pkg["reconciliation"]
    if rows is None:
        return  # 未跑法医：由状态门点名，校验器不重复
    checks = [r for r in rows if r.get("type") == "check"]
    summaries = {r.get("edge"): r for r in rows if r.get("type") == "summary"}
    for c in checks:
        if c.get("edge") not in schema.FORENSIC_EDGES:
            errors.append(f"检查行 {c.get('check_id')} 的 edge "
                          f"{c.get('edge')!r} 不在四边词表")
        if c.get("result") not in schema.CHECK_RESULTS:
            errors.append(f"检查行 {c.get('check_id')} 的 result "
                          f"{c.get('result')!r} 不在结果词表")
    # 覆盖自报机械对账（RV-07）：summary 必须与逐项行重算一致
    for edge in schema.FORENSIC_EDGES:
        items = [c for c in checks if c.get("edge") == edge]
        s = summaries.get(edge)
        if items and s is None:
            errors.append(f"边 {edge} 有逐项行但缺覆盖自报 summary 行")
            continue
        if s is None:
            continue
        recount = {
            "checked": len(items),
            "assessable": sum(1 for c in items
                              if c["result"] != "not_assessable"),
            "not_assessable": sum(1 for c in items
                                  if c["result"] == "not_assessable"),
            "errors": sum(1 for c in items if c["result"] == "error"),
            "decision_errors": sum(1 for c in items
                                   if c["result"] == "decision_error"),
        }
        for k, v in recount.items():
            if s.get(k) != v:
                errors.append(
                    f"边 {edge} 覆盖自报 {k}={s.get(k)} 与逐项行重算 {v} "
                    "不符（覆盖自报只许机械汇总，RV-07）")
    # 发现账：分类/两层/指针/裁决
    check_by_id = {c.get("check_id"): c for c in checks}
    folded = fold_findings(pkg["findings"] or [])
    for f in folded:
        fid = f.get("finding_id")
        if f.get("category") not in schema.FINDING_CATEGORIES:
            errors.append(f"发现 {fid} 的 category {f.get('category')!r} "
                          "不在 D-R02 词表")
        if f.get("layer") not in schema.FINDING_LAYERS:
            errors.append(f"发现 {fid} 的 layer {f.get('layer')!r} 不在两层词表")
        # 两层纪律（RV-08）：结论翻转只许挂在 decision_error 的检查行上
        if f.get("layer") == "conclusion_flip":
            chk = check_by_id.get(f.get("check_id"))
            if chk is not None and chk.get("result") != "decision_error":
                errors.append(
                    f"发现 {fid} 标 conclusion_flip，但其检查行 "
                    f"{f.get('check_id')} 结果是 {chk.get('result')}："
                    "结论翻转只许在数值不一致已成立（decision_error）之上")
        adj = f.get("adjudication")
        if adj is not None:
            if adj.get("outcome") not in schema.ADJUDICATION_OUTCOMES:
                errors.append(f"发现 {fid} 的裁决结论不在词表")
            if not (adj.get("adjudicator") or "").strip():
                errors.append(f"发现 {fid} 的裁决缺裁决人（不许匿名）")
            if not (adj.get("reason") or "").strip():
                errors.append(f"发现 {fid} 的裁决缺理由")
    # GRIM 发现必须能在 compatibility 找到判败行
    compat_ids = {r.get("stat_id") for r in pkg["compatibility"] or []
                  if r.get("result") == "incompatible"}
    for f in folded:
        if f.get("edge") == "grim_compatibility":
            stat = (f.get("evidence_pointer") or "").split(":")[-1]
            if stat not in compat_ids:
                errors.append(
                    f"发现 {f.get('finding_id')} 指向 GRIM 汇总量 {stat}，"
                    "但 compatibility 中无对应判败行")


def _validate_seats_consensus(errors, pkg):
    seats = (pkg["seats"] or {}).get("seats") or []
    seat_ids = set()
    for s in seats:
        seat_ids.add(s.get("seat_id"))
        if s.get("status") not in schema.SEAT_STATUSES:
            errors.append(f"席位 {s.get('seat_id')} 状态不在词表")
        for stage, kinds in (s.get("visibility") or {}).items():
            if stage not in schema.PANEL_STAGES:
                errors.append(f"席位 {s.get('seat_id')} 可见性阶段 "
                              f"{stage!r} 不在词表")
            bad = [k for k in kinds if k not in schema.ARTIFACT_KINDS]
            if bad:
                errors.append(f"席位 {s.get('seat_id')} 可见性含非法工件类 {bad}")
        panel_kinds = (s.get("visibility") or {}).get("panel") or []
        if "other_reports" in panel_kinds or "consensus" in panel_kinds:
            errors.append(
                f"席位 {s.get('seat_id')} 的 panel 阶段可见 other_reports/"
                "consensus：冻结前互盲被绕过（RV-01）")
    for stale in verify_frozen(pkg["root"]):
        errors.append(f"冻结件 STALE：{stale}")
    review = pkg["review"] or {}
    frozen_hashes = {r.get("seat_id"): r.get("report_hash")
                     for r in review.get("freezes") or []}
    for s in seats:
        if s.get("status") == "frozen":
            if frozen_hashes.get(s.get("seat_id")) != s.get("report_hash"):
                errors.append(
                    f"席位 {s.get('seat_id')} 的冻结账与 seats 登记哈希不一致")
    # 共识账：severity 代码重算、共识门、终态理由（RV-05/RV-11）
    for c in (pkg["consensus"] or {}).get("concerns") or []:
        cid = c.get("concern_id")
        raised = list(dict.fromkeys(c.get("raised_by") or []))
        unknown = [s for s in raised if s not in seat_ids]
        if unknown:
            errors.append(f"concern {cid} 的 raised_by 含未登记席位 {unknown}")
        if c.get("tally") != len(raised):
            errors.append(f"concern {cid} 的 tally 与 raised_by 去重数不符")
        computed = schema.computed_severity(c.get("severity_proposals") or {})
        if c.get("severity") != computed:
            errors.append(
                f"concern {cid} 的 severity={c.get('severity')} ≠ 代码计算 "
                f"{computed}：佐证不许抬级，severity 只许取独立提案 MAX"
                "（RV-05）")
        if c.get("consensus") and len(raised) < 2:
            errors.append(
                f"concern {cid} 单席提出却标 consensus：共识门要求 ≥2 席"
                "独立同向（RV-05）")
        if c.get("status") == "closed" and \
                not (c.get("close_reason") or "").strip():
            errors.append(f"concern {cid} 已关闭但缺理由（RV-11）")
        # 升格三查落账一致性（v1.1 REV-D10）：结果在册的 concern，
        # 总判定不许为 fail（三查不过在落盘口已拒，入账即手改）
        esc = c.get("escalation_checks")
        if esc is not None:
            if esc.get("verdict") == "fail":
                errors.append(
                    f"concern {cid} 的升格三查总判定为 fail 却在共识账中："
                    "三查不过不许入账（REV-D10），须经 consensus 正道重落")
            for key in ("pointer_resolution", "verbatim_support",
                        "severity_cap"):
                sub = esc.get(key) or {}
                if not sub.get("result"):
                    errors.append(f"concern {cid} 的升格三查缺 {key} 结果"
                                  "（三查结果逐条落账，REV-D10）")


def _validate_delivery(errors, pkg):
    review = pkg["review"] or {}
    if review.get("status") != "delivered":
        return
    delivery = review.get("delivery")
    if not delivery:
        errors.append("状态 delivered 但登记头无 delivery 区")
        return
    folded = fold_findings(pkg["findings"] or [])
    open_ce = open_confirmed_errors(folded)
    if open_ce:
        errors.append(
            "delivered 时仍有未裁决 confirmed error："
            + "、".join(f["finding_id"] for f in open_ce)
            + "（R2 硬度 a：须人工裁决位解除）")
    iso = review.get("isolation") or {}
    if iso.get("mode") == "degraded" and \
            not (delivery.get("degradation_statement") or "").strip():
        errors.append("隔离降档（degraded）交付缺降档声明："
                      "做不到全规格时交付产物必须明说（R1）")
    drift = snapshot_drift(pkg["root"])
    if drift:
        errors.append("delivered 后上游快照漂移：" + "；".join(drift))


def _validate_counts(errors, pkg):
    review = pkg["review"] or {}
    counts = review.get("counts")
    if counts is None:
        return
    folded = fold_findings(pkg["findings"] or [])
    expected = {
        "findings": len(folded),
        "confirmed_error_open": len(open_confirmed_errors(folded)),
        "not_assessable": sum(1 for f in folded
                              if f.get("category") == "not_assessable"),
        "concerns": len((pkg["consensus"] or {}).get("concerns") or []),
        "consensus": sum(1 for c in (pkg["consensus"] or {}).get("concerns") or []
                         if c.get("consensus")),
    }
    for k, v in expected.items():
        if counts.get(k) != v:
            errors.append(f"登记头 counts.{k}={counts.get(k)} 与机械重算 "
                          f"{v} 不符（汇总只许工具机械生成）")


# ---------------------------------------------------------------- Phase 2 件

def _validate_domain(errors, pkg):
    rows = pkg["domain_gate"]
    review = pkg["review"] or {}
    if rows is None:
        if review.get("domain"):
            errors.append("登记头已登记领域门但缺 domain_gate.jsonl")
        return
    from datetime import date
    checks = [r for r in rows if r.get("type") == "domain_check"]
    summaries = [r for r in rows if r.get("type") == "summary"]
    for r in checks:
        iid = r.get("item_id")
        if r.get("layer") not in schema.DOMAIN_LAYERS:
            errors.append(f"领域门条目 {iid} 的 layer 不在三层词表")
        if r.get("result") not in schema.DOMAIN_RESULTS:
            errors.append(f"领域门条目 {iid} 的 result 不在判定词表")
        if r.get("source_kind") is not None \
                and r.get("source_kind") not in schema.SOURCE_KINDS:
            errors.append(f"领域门条目 {iid} 的 source_kind 不在来源四分词表")
        if r.get("layer") == "journal_fact":
            fact = r.get("fact") or {}
            status = fact.get("fact_status")
            if status not in schema.FACT_STATUSES:
                errors.append(f"按刊事实条目 {iid} 的 fact_status 不在词表")
            # 时效重算（RV-17）：过期事实必须已落 unverified 且不驱动判定
            expected = "unverified"
            verified_at = fact.get("verified_at")
            cycle = fact.get("cycle_days") \
                or schema.FACT_FRESHNESS_DEFAULT_DAYS
            if verified_at:
                try:
                    age = (date.today()
                           - date.fromisoformat(str(verified_at)[:10])).days
                    expected = "verified" if 0 <= age <= cycle \
                        else "unverified"
                except ValueError:
                    expected = "unverified"
            if status == "verified" and expected == "unverified":
                errors.append(
                    f"按刊事实条目 {iid} 标 verified，但核查日期 "
                    f"{verified_at} 已超复核周期 {cycle} 天：过期事实"
                    "必须落 UNVERIFIED（RV-17）")
            if expected == "unverified" and r.get("result") != "not_applicable":
                errors.append(
                    f"按刊事实条目 {iid} 的事实 UNVERIFIED 却给出判定 "
                    f"{r.get('result')}：过期事实不许驱动判定（RV-17）")
    # 覆盖自报机械对账（RV-07 口径，与法医边同法）
    if checks and not summaries:
        errors.append("domain_gate.jsonl 有逐条行但缺 summary 覆盖自报行")
    for s in summaries:
        recount = {
            "checked": len(checks),
            "hits": sum(1 for r in checks if r["result"] == "hit"),
            "misses": sum(1 for r in checks if r["result"] == "miss"),
            "not_applicable": sum(1 for r in checks
                                  if r["result"] == "not_applicable"),
            "effective_hits": sum(1 for r in checks
                                  if r["result"] == "hit"
                                  and r.get("effective")),
        }
        for k, v in recount.items():
            if s.get(k) != v:
                errors.append(f"领域门覆盖自报 {k}={s.get(k)} 与逐条行"
                              f"重算 {v} 不符（RV-07）")
    # 覆盖层冲突解析重算（RV-16c）：effective/superseded_by 必须与
    # 登记的 precedence 一致，不许手改解析结果
    overlay_reg = (review.get("domain") or {}).get("overlay") or {}
    precedence = overlay_reg.get("precedence")
    overlay_rows = [r for r in checks if r.get("layer") == "overlay"
                    and r.get("overrides")]
    if overlay_rows and not precedence:
        errors.append("领域门有 overrides 条目但登记头未登记覆盖层优先序")
    if precedence:
        by_id = {r.get("item_id"): r for r in checks}
        for r in overlay_rows:
            target = by_id.get(r.get("overrides"))
            if target is None:
                errors.append(f"覆盖层条目 {r.get('item_id')} 的 overrides "
                              f"指向不存在的条目 {r.get('overrides')}")
                continue
            if precedence == "overlay_wins":
                if target.get("effective") is not False \
                        or target.get("superseded_by") != r.get("item_id"):
                    errors.append(
                        f"覆盖层优先序 overlay_wins 下，条目 "
                        f"{target.get('item_id')} 应被 {r.get('item_id')} "
                        "supersede（effective=false）而未落字")
            else:
                if r.get("effective") is not False \
                        or r.get("superseded_by") != target.get("item_id"):
                    errors.append(
                        f"覆盖层优先序 core_wins 下，覆盖层条目 "
                        f"{r.get('item_id')} 应被核心条目 "
                        f"{target.get('item_id')} supersede 而未落字")


def _validate_calibration(errors, pkg):
    calibration = pkg["calibration"]
    if calibration is None:
        return
    from .calibration import _check_asymmetry, _check_caps, _check_scale
    for gap in _check_scale(calibration) + _check_caps(calibration) \
            + _check_asymmetry(calibration):
        errors.append(f"校准登记不合纪律：{gap}")


def _validate_decision(errors, pkg):
    review = pkg["review"] or {}
    decision = review.get("decision")
    if not decision:
        return
    mode = decision.get("mode")
    if mode not in schema.DECISION_MODES:
        errors.append(f"登记头 decision.mode {mode!r} 不在词表")
    if mode == "full":
        if pkg["decision_md"] is None:
            errors.append("decision 登记为 full 但缺 reports/decision.md")
        from .calibration import assess_calibration
        assessment = assess_calibration(pkg["root"])
        if not assessment["complete"]:
            errors.append("decision 登记为 full 但校准门四件不齐："
                          + "；".join(assessment["missing"]))
    elif mode == "degraded":
        if pkg["decision_md"] is not None:
            errors.append("degraded 形态下 reports/decision.md 存在："
                          "校准门不齐不许出决定建议（条件给纪律）")
        if pkg["problem_list"] is None:
            errors.append("decision 登记为 degraded 但缺 "
                          "reports/problem_list.md")
    selfcheck = pkg["selfcheck"]
    if selfcheck is not None and selfcheck.get("passed"):
        from .selfcheck import target_hash
        if selfcheck.get("target_hash") != target_hash(pkg):
            errors.append("reports/selfcheck.json 已过期：meta/decision "
                          "在自审后被改动（target_hash 不符，须重跑自审）")


def _validate_handoff(errors, pkg):
    payload = pkg["handoff_json"]
    if payload is None:
        return
    if payload.get("kind") != "light-review/handoff-to-write":
        errors.append("handoff_to_write.json 的 kind 不是 "
                      "light-review/handoff-to-write")
    concerns = {c.get("concern_id"): c
                for c in (pkg["consensus"] or {}).get("concerns") or []}
    allowed = set(schema.HANDOFF_ITEM_FIELDS)
    for item in payload.get("items") or []:
        cid = item.get("concern_id")
        extra = set(item) - allowed
        if extra:
            errors.append(f"回填条目 {cid} 含白名单外字段 {sorted(extra)}："
                          "Review 只出清单不出补丁，字段白名单外一律不许"
                          "（R6）")
        if item.get("action_class") not in schema.ACTION_CLASSES:
            errors.append(f"回填条目 {cid} 的 action_class "
                          f"{item.get('action_class')!r} 不在动作词表")
        for key, value in item.items():
            if isinstance(value, str) \
                    and len(value) > schema.HANDOFF_MAX_TEXT:
                errors.append(f"回填条目 {cid} 的字段 {key} 长 "
                              f"{len(value)} 字，超上限 "
                              f"{schema.HANDOFF_MAX_TEXT}：疑似稿件正文"
                              "段落偷渡（只出清单不出补丁）")
        concern = concerns.get(cid)
        if concern is None:
            errors.append(f"回填条目 {cid} 在共识账中不存在")
        else:
            computed = schema.computed_severity(
                concern.get("severity_proposals") or {})
            if item.get("severity") != computed:
                errors.append(f"回填条目 {cid} 的 severity="
                              f"{item.get('severity')} ≠ 代码重算 "
                              f"{computed}（RV-05）")


def _validate_obligations(errors, pkg):
    """义务账纪律（v1.1 REV-D05）：关闭留痕齐备 + 状态与事件行对账。"""
    rows = pkg["obligations"]
    if rows is None:
        return
    from .obligations import fold_obligations
    known = set()
    for r in rows:
        if r.get("type") == "obligation":
            oid = r.get("obligation_id")
            if oid in known:
                errors.append(f"义务 {oid} 重复登记（stable ID 不许复用）")
            known.add(oid)
            if not (r.get("text") or "").strip():
                errors.append(f"义务 {oid} 文本为空")
            if not (r.get("registered_by") or "").strip():
                errors.append(f"义务 {oid} 缺登记人（具名纪律）")
        elif r.get("type") == "obligation_event":
            oid = r.get("obligation_id")
            if oid not in known:
                errors.append(f"义务事件指向不存在的义务 {oid}")
            if r.get("action") not in ("fulfill", "waive"):
                errors.append(f"义务 {oid} 的事件动作 {r.get('action')!r} "
                              "不在词表")
            if not (r.get("by") or "").strip():
                errors.append(f"义务 {oid} 的关闭事件缺执行人（具名纪律）")
            if r.get("action") == "fulfill" \
                    and not (r.get("evidence_pointer") or "").strip():
                errors.append(f"义务 {oid} 的 fulfill 事件缺履行证据指针")
            if r.get("action") == "waive" \
                    and not (r.get("reason") or "").strip():
                errors.append(f"义务 {oid} 的 waive 事件缺理由"
                              "（豁免须具名加理由留痕）")
        else:
            errors.append(f"义务账出现未知行型 {r.get('type')!r}")
    folded = fold_obligations(rows)
    delivered = (pkg["review"] or {}).get("status") == "delivered"
    if delivered:
        for o in folded:
            if o.get("status") == "open":
                errors.append(f"delivered 时义务 {o['obligation_id']} "
                              "仍为 open（义务账阻断纪律，REV-D05）")


def validate_package(root) -> list:
    """全量校验，返回错误清单（空 = 通过）。只拦不赦。"""
    root = Path(root)
    pkg = load_package(root)
    errors: list[str] = []
    if pkg["review"] is None:
        return ["评审包不存在（缺 review.yaml，先 init）"]
    _validate_review_head(errors, pkg)
    _validate_forensic(errors, pkg)
    _validate_seats_consensus(errors, pkg)
    _validate_obligations(errors, pkg)
    _validate_domain(errors, pkg)
    _validate_calibration(errors, pkg)
    _validate_decision(errors, pkg)
    _validate_handoff(errors, pkg)
    _validate_delivery(errors, pkg)
    _validate_counts(errors, pkg)
    return errors
