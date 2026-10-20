"""light-review CLI（Phase 1 + Phase 2）。

  init        建评审包骨架（review.yaml / seats.yaml / consensus.yaml /
              forensic/ / reports/drafts/）
  intake      R0 承接：消费 Write 稿件包 + Analysis 结论包（+ Figure 图包），
              三包快照哈希冻结 + 约束/隔离登记（缺项逐项点名）
  forensic    法医层：四方对账四边 + GRIM 并账 → reconciliation /
              findings / compatibility 落盘
  grim        登记被检汇总量（--register）并单独重跑 GRIM 相容性
  seat        登记评审席位（角色/模型家族/可见性矩阵）
  panel       落席位草稿（reports/drafts/<seat>.md，席间物理隔离）
  freeze      冻结全部席位报告（哈希钉住，append-only）
  consensus   由逐席关切输入生成共识与分歧账（共识门落盘口强制）
  domain      领域门三层：通用轴地板 + 按刊事实层（同一事实源、时效
              UNVERIFIED 纪律）+ 蒸馏覆盖层 → domain_gate.jsonl
  calibration 校准门登记：calibration.yaml 模板落盘 + 四件齐备性评估
  bench       验证台：缺陷注入金标准集 → reports/bench_report.json
              （绑定评审配置哈希，漂移即过期）
  meta        meta 合成（只消费冻结报告）+ 决定建议：校准门四件齐
              才出 decision.md，缺一降级 problem_list.md
  selfcheck   评审产物自审门（RV-13）：五类命名可靠性测试 +
              与冻结清单对账 → reports/selfcheck.json
  export      concern 回填清单导出（handoff_to_write.md/.json，
              字段白名单，只出清单不出补丁）
  adjudicate  人工裁决位：给 confirmed error 落裁决（具名 + 理由）
  advance     状态机推进一段（逐段过门，缺口逐项列出）
  deliver     交付：过 delivered 门 + 生成 REVIEW_DELIVERY.md
  validate    校验评审包（结构 + 全部纪律，逐条点名）
  status      看状态、计数与下一段门的缺口预演
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .bench import BenchError, run_bench
from .calibration import CalibrationError, assess_calibration, init_calibration
from .domain import DomainError, run_domain
from .forensic import ForensicError, adjudicate_finding, register_summaries, run_forensic
from .obligations import ObligationError
from .gates import NEXT, GateError, advance_package, deliver_package, gate_gaps_for
from .handoff import HandoffError, run_export
from .intake import IntakeError, run_intake
from .meta import MetaError, run_meta
from .panel import PanelError, build_consensus, freeze_reports, register_seat, write_draft
from .project import init_package, load_package
from .selfcheck import SelfcheckError, run_selfcheck
from .util import load_structured
from .validate import validate_package


def _fail(msg: str) -> int:
    print(f"错误：{msg}", file=sys.stderr)
    return 1


def _gaps_fail(exc) -> int:
    print("被拦（逐项缺口）：", file=sys.stderr)
    for g in exc.gaps:
        print(f"  - {g}", file=sys.stderr)
    return 1


def cmd_init(args) -> int:
    try:
        root = init_package(Path(args.path), title=args.title or "",
                            round_no=args.round)
    except FileExistsError as e:
        return _fail(str(e))
    print(f"已建评审包骨架：{root}（状态 intake）")
    return 0


def cmd_intake(args) -> int:
    try:
        info = run_intake(
            Path(args.path), args.manuscript, analysis_path=args.analysis,
            figure_path=args.figure, journal_name=args.journal,
            target_record=args.target_record, intensity=args.intensity,
            seats_spec=args.seats_spec, want_decision=args.want_decision,
            isolation_mode=args.isolation,
            isolation_reason=args.isolation_reason)
    except IntakeError as e:
        return _gaps_fail(e)
    parts = info["input_scope"]["packages"]
    print(f"承接完成：快照冻结（{'/'.join(parts)}），"
          f"目标刊 {(info['target_journal'] or {}).get('name') or '未登记'}")
    if info.get("figure_note"):
        print(f"  注：{info['figure_note']}")
    return 0


def cmd_forensic(args) -> int:
    try:
        s = run_forensic(Path(args.path))
    except ForensicError as e:
        return _gaps_fail(e)
    print(f"法医层完成：检查 {s['checks']} 项、发现 {s['findings']} 条、"
          f"GRIM {'已跑 ' + str(s['grim_checked']) + ' 条' if s['grim_registered'] else '未登记被检量，未跑'}")
    for row in s["summaries"]:
        print(f"  边 {row['edge']}：应检 {row['checked']}、"
              f"not_assessable {row['not_assessable']}、"
              f"error {row['errors']}、decision_error {row['decision_errors']}")
    return 0


def cmd_grim(args) -> int:
    try:
        rows = register_summaries(Path(args.path), args.register)
    except ForensicError as e:
        return _gaps_fail(e)
    bad = [r for r in rows if r["result"] == "incompatible"]
    na = [r for r in rows if r["result"] == "not_assessable"]
    print(f"GRIM 登记并重跑：{len(rows)} 条 — 相容 "
          f"{len(rows) - len(bad) - len(na)}、判败 {len(bad)}、"
          f"not_assessable {len(na)}")
    return 0


def cmd_seat(args) -> int:
    try:
        row = register_seat(Path(args.path), args.id, args.role, args.family,
                            persona=args.persona,
                            knows_authors=args.knows_authors)
    except PanelError as e:
        return _gaps_fail(e)
    print(f"席位已登记：{row['seat_id']}（{row['role']} / {row['model_family']}）")
    return 0


def cmd_panel(args) -> int:
    try:
        seat = write_draft(Path(args.path), args.seat, args.draft)
    except PanelError as e:
        return _gaps_fail(e)
    print(f"草稿已落：{seat['draft_path']}（席间隔离，冻结前互不可见）")
    return 0


def cmd_freeze(args) -> int:
    try:
        records = freeze_reports(Path(args.path))
    except PanelError as e:
        return _gaps_fail(e)
    print(f"已冻结 {len(records)} 席报告："
          + "、".join(r["seat_id"] for r in records))
    return 0


def cmd_consensus(args) -> int:
    data = load_structured(Path(args.file))
    if isinstance(data, dict):
        data = data.get("concerns") or []
    try:
        consensus = build_consensus(Path(args.path), data)
    except PanelError as e:
        return _gaps_fail(e)
    n = len(consensus["concerns"])
    k = sum(1 for c in consensus["concerns"] if c["consensus"])
    print(f"共识账已生成：concern {n} 条，其中 consensus {k} 条")
    return 0


def cmd_adjudicate(args) -> int:
    obligations = []
    for i, text in enumerate(args.obligation or []):
        finding = None
        if args.obligation_finding and i < len(args.obligation_finding):
            finding = args.obligation_finding[i]
        obligations.append({"text": text, "finding_id": finding})
    try:
        row = adjudicate_finding(Path(args.path), args.finding, args.outcome,
                                 args.by, args.reason,
                                 obligations=obligations or None)
    except (ForensicError, ObligationError) as e:
        return _gaps_fail(e)
    print(f"裁决已落：{row['finding_id']} → {row['outcome']}"
          f"（{row['adjudicator']}，追加留痕）")
    for o in obligations:
        print(f"  附带义务已入义务账：{o['text']}"
              f"（关联 {o['finding_id'] or args.finding}，open）")
    return 0


def cmd_obligation(args) -> int:
    from .obligations import (
        ObligationError, apply_obligation_event, fold_obligations,
        register_obligation,
    )
    root = Path(args.path)
    try:
        if args.add:
            row = register_obligation(root, args.add,
                                      finding_id=args.finding, by=args.by)
            print(f"义务已登记：{row['obligation_id']}（open）"
                  f"——{row['text']}")
            return 0
        if args.list:
            folded = fold_obligations(load_package(root)["obligations"]
                                      or [])
            if not folded:
                print("义务账为空（无裁决附带条件登记）")
            for o in folded:
                closure = o.get("closure") or {}
                tail = ""
                if o["status"] == "fulfilled":
                    tail = f"，证据 {closure.get('evidence_pointer')}"
                elif o["status"] == "waived":
                    tail = f"，理由：{closure.get('reason')}"
                print(f"  {o['obligation_id']} [{o['status']}] "
                      f"{o.get('text')}{tail}")
            return 0
        action = "fulfill" if args.fulfill else "waive"
        row = apply_obligation_event(
            root, args.id, action, by=args.by, reason=args.reason,
            evidence_pointer=args.evidence)
        print(f"义务 {row['obligation_id']} 已关闭：{action}"
              f"（{row['by']}，追加留痕）")
        return 0
    except ObligationError as e:
        return _gaps_fail(e)


def cmd_domain(args) -> int:
    try:
        info = run_domain(Path(args.path), overlay_path=args.overlay,
                          today_str=args.today, paradigm=args.paradigm,
                          paradigm_basis=args.paradigm_basis,
                          paradigm_by=args.paradigm_by)
    except DomainError as e:
        return _gaps_fail(e)
    s = info["summary"]
    print(f"领域门完成：条目 {s['checked']} — 命中 {s['hits']}、"
          f"未命中 {s['misses']}、不适用 {s['not_applicable']}"
          f"（有效命中 {s['effective_hits']}）")
    if info.get("paradigm"):
        print(f"  范式（第零层）：{info['paradigm']}")
    else:
        print("  范式（第零层）：未登记——定性权重层未启用"
              "（domain --paradigm 登记；条目带范式适用性时 "
              "reported 门将点名阻断）")
    if info.get("fact_source"):
        print(f"  按刊事实：{info['fact_source']['record_path']}"
              f"（状态 {info['fact_source']['fact_status']}）")
    if info.get("overlay"):
        print(f"  覆盖层：{info['overlay']['overlay_id']}"
              f"（优先序 {info['overlay']['precedence']}）")
    return 0


def cmd_calibration(args) -> int:
    try:
        init_calibration(Path(args.path))
        print("calibration.yaml 已按模板落盘（量表锚/封顶/不对称三件，"
              "改即配置漂移）")
    except CalibrationError as e:
        if "已存在" not in str(e):
            return _gaps_fail(e)
        print("calibration.yaml 已在册（不覆盖）")
    assessment = assess_calibration(Path(args.path))
    pieces = assessment["pieces"]
    print("校准门四件：" + "、".join(
        f"{k}={'齐' if v else '缺'}" for k, v in pieces.items()))
    for m in assessment["missing"]:
        print(f"  - 缺件：{m}")
    return 0 if assessment["complete"] else 1


def cmd_bench(args) -> int:
    try:
        report = run_bench(Path(args.path))
    except BenchError as e:
        return _gaps_fail(e)
    print(f"验证台完成：{len(report['cases'])} 例全过="
          f"{report['passed_all']}，误报率 "
          f"{report['false_positive']['rate']}")
    for cls, row in report["by_class"].items():
        print(f"  {cls}：检出 {row['detected']}/{row['total']}"
              f"（{row['detection_rate']}）")
    return 0


def cmd_meta(args) -> int:
    try:
        record = run_meta(Path(args.path), narrative_file=args.file)
    except MetaError as e:
        return _gaps_fail(e)
    print(f"meta 合成完成：reports/meta_review.md（形态 "
          f"{record['mode']}）")
    if record["mode"] == "full":
        print(f"  决定建议：reports/decision.md（档位 {record['band']}，"
              "bounded 非编辑判断）")
    else:
        print("  已降级：reports/problem_list.md（校准门缺件 "
              f"{len(record['calibration_missing'])} 项，逐项见登记头）")
    return 0


def cmd_selfcheck(args) -> int:
    try:
        report = run_selfcheck(Path(args.path))
    except SelfcheckError as e:
        return _gaps_fail(e)
    for t in report["tests"]:
        print(f"  {t['test_id']}：{t['result']}（{t['detail']}）")
    print(f"自审门：{'通过' if report['passed'] else '未过'}"
          "（reports/selfcheck.json）")
    return 0 if report["passed"] else 1


def cmd_export(args) -> int:
    try:
        payload = run_export(Path(args.path))
    except HandoffError as e:
        return _gaps_fail(e)
    print(f"回填清单已导出：handoff_to_write.md/.json"
          f"（{len(payload['items'])} 条，Review 只出清单不出补丁）")
    return 0


def cmd_advance(args) -> int:
    try:
        new_state = advance_package(Path(args.path))
    except GateError as e:
        return _gaps_fail(e)
    print(f"已推进 → {new_state}")
    return 0


def cmd_deliver(args) -> int:
    try:
        delivery = deliver_package(
            Path(args.path),
            degradation_statement=args.degradation_statement)
    except GateError as e:
        return _gaps_fail(e)
    print(f"已交付：{delivery['delivered_at']}（REVIEW_DELIVERY.md 已生成）")
    if delivery.get("degradation_statement"):
        print(f"  降档声明：{delivery['degradation_statement']}")
    return 0


def cmd_validate(args) -> int:
    errors = validate_package(Path(args.path))
    if errors:
        print(f"校验未过（{len(errors)} 项）：")
        for e in errors:
            print(f"  - {e}")
        return 1
    print("校验通过：0 项错误")
    return 0


def cmd_status(args) -> int:
    pkg = load_package(Path(args.path))
    review = pkg["review"]
    if review is None:
        return _fail("评审包不存在（先 init）")
    counts = review.get("counts") or {}
    print(f"评审包：{review.get('review_id')}  状态：{review.get('status')}"
          f"（round {review.get('round')}）")
    iso = review.get("isolation") or {}
    if iso:
        print(f"  隔离模式：{iso.get('mode')}"
              + (f"（{iso.get('reason')}）" if iso.get("reason") else ""))
    print("  计数：" + "、".join(
        f"{k}={counts.get(k, 0)}" for k in
        ("findings", "confirmed_error_open", "not_assessable",
         "concerns", "consensus")))
    if review.get("domain"):
        s = review["domain"].get("summary") or {}
        print(f"  领域门：命中 {s.get('hits', 0)}/条目 {s.get('checked', 0)}"
              f"（ran_at {review['domain'].get('ran_at')}）")
    paradigm = review.get("paradigm") or {}
    print(f"  范式（第零层）：{paradigm.get('paradigm') or '未登记'}")
    from .obligations import fold_obligations, open_obligations
    folded_ob = fold_obligations(pkg["obligations"] or [])
    if folded_ob:
        print(f"  义务账：{len(folded_ob)} 条，open "
              f"{len(open_obligations(folded_ob))} 条"
              "（open 义务阻断交付，REV-D05）")
    if review.get("decision"):
        d = review["decision"]
        print(f"  决定形态：{d.get('mode')}"
              + (f"（档位 {d.get('band')}）" if d.get("band") else
                 "（降级：问题清单）"))
    if review.get("handoff"):
        print(f"  回填清单：{review['handoff'].get('items', 0)} 条已导出")
    target = NEXT.get(review.get("status"))
    if target:
        gaps = gate_gaps_for(Path(args.path), target) \
            if target != "delivered" else []
        if target == "delivered":
            print("  下一段 → delivered：走 deliver 命令")
        elif gaps:
            print(f"  下一段 → {target} 尚有 {len(gaps)} 项缺口：")
            for g in gaps:
                print(f"    - {g}")
        else:
            print(f"  下一段 → {target}：门已齐，可 advance")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="light-review",
        description="light-review：投稿前内部评审包（Phase 1 + Phase 2）")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("init", help="建评审包骨架")
    p.add_argument("path")
    p.add_argument("--title", default="")
    p.add_argument("--round", type=int, default=1)
    p.set_defaults(fn=cmd_init)

    p = sub.add_parser("intake", help="R0 承接：三包快照 + 约束/隔离登记")
    p.add_argument("path")
    p.add_argument("--manuscript", required=True)
    p.add_argument("--analysis", required=True)
    p.add_argument("--figure", default=None)
    p.add_argument("--journal", default=None)
    p.add_argument("--target-record", default=None)
    p.add_argument("--intensity", required=True,
                   choices=["light", "standard", "thorough"],
                   help="评审强度档（必填：约束缺项不许静默默认）")
    p.add_argument("--seats-spec", default="full")
    p.add_argument("--want-decision", action="store_true", default=None)
    p.add_argument("--isolation", default="full",
                   choices=["full", "degraded"])
    p.add_argument("--isolation-reason", default=None)
    p.set_defaults(fn=cmd_intake)

    p = sub.add_parser("forensic", help="法医层：四方对账 + GRIM 并账")
    p.add_argument("path")
    p.set_defaults(fn=cmd_forensic)

    p = sub.add_parser("grim", help="登记被检汇总量并重跑 GRIM 相容性")
    p.add_argument("path")
    p.add_argument("--register", required=True,
                   help="汇总量登记 YAML：{entries: [{stat_id, kind, value, decimals, n, items, scale_type, parts}]}")
    p.set_defaults(fn=cmd_grim)

    p = sub.add_parser("seat", help="登记评审席位")
    p.add_argument("path")
    p.add_argument("--id", required=True)
    p.add_argument("--role", required=True)
    p.add_argument("--family", required=True)
    p.add_argument("--persona", default=None)
    p.add_argument("--knows-authors", action="store_true")
    p.set_defaults(fn=cmd_seat)

    p = sub.add_parser("panel", help="落席位草稿（席间隔离）")
    p.add_argument("path")
    p.add_argument("--seat", required=True)
    p.add_argument("--draft", required=True)
    p.set_defaults(fn=cmd_panel)

    p = sub.add_parser("freeze", help="冻结全部席位报告")
    p.add_argument("path")
    p.set_defaults(fn=cmd_freeze)

    p = sub.add_parser("consensus", help="生成共识与分歧账")
    p.add_argument("path")
    p.add_argument("--file", required=True,
                   help="逐席关切输入（YAML/JSON：{concerns: [...]} 或列表）")
    p.set_defaults(fn=cmd_consensus)

    p = sub.add_parser("domain", help="领域门三层（通用轴/按刊事实/蒸馏覆盖层）+ 第零层范式登记")
    p.add_argument("path")
    p.add_argument("--overlay", default=None,
                   help="蒸馏覆盖层文件（YAML，格式见 domain.load_overlay）")
    p.add_argument("--today", default=None,
                   help="事实时效判定日（YYYY-MM-DD，缺省取当日）")
    p.add_argument("--paradigm", default=None,
                   choices=["methods", "empirical", "benchmark", "theory",
                            "humanities"],
                   help="范式登记（第零层）：随本次领域门运行落字")
    p.add_argument("--paradigm-basis", default=None,
                   help="范式判定依据（落字，--paradigm 时必填）")
    p.add_argument("--paradigm-by", default=None, help="范式登记人")
    p.set_defaults(fn=cmd_domain)

    p = sub.add_parser("obligation", help="裁决义务账（REV-D05）：登记/履行/豁免/列账")
    p.add_argument("path")
    p.add_argument("--add", default=None, help="登记一条义务（文本）")
    p.add_argument("--finding", default=None, help="关联发现 ID")
    p.add_argument("--id", default=None, help="义务 ID（fulfill/waive 用）")
    p.add_argument("--fulfill", action="store_true", help="标记履行")
    p.add_argument("--waive", action="store_true", help="标记豁免")
    p.add_argument("--by", default=None, help="执行人（具名）")
    p.add_argument("--reason", default=None, help="豁免理由（waive 必填）")
    p.add_argument("--evidence", default=None,
                   help="履行证据指针（fulfill 必填）")
    p.add_argument("--list", action="store_true", help="列出义务账")
    p.set_defaults(fn=cmd_obligation)

    p = sub.add_parser("calibration", help="校准门登记（模板落盘 + 四件齐备性）")
    p.add_argument("path")
    p.set_defaults(fn=cmd_calibration)

    p = sub.add_parser("bench", help="验证台：缺陷注入金标准集判别力报表")
    p.add_argument("path")
    p.set_defaults(fn=cmd_bench)

    p = sub.add_parser("meta", help="meta 合成 + 决定建议（校准门定形态）")
    p.add_argument("path")
    p.add_argument("--file", default=None,
                   help="合成叙述文件（可选，模型撰写；缺省机械生成）")
    p.set_defaults(fn=cmd_meta)

    p = sub.add_parser("selfcheck", help="评审产物自审门（RV-13 五类命名测试）")
    p.add_argument("path")
    p.set_defaults(fn=cmd_selfcheck)

    p = sub.add_parser("export", help="concern 回填清单导出（只出清单不出补丁）")
    p.add_argument("path")
    p.set_defaults(fn=cmd_export)

    p = sub.add_parser("adjudicate", help="人工裁决位：给发现落裁决（可附带义务）")
    p.add_argument("path")
    p.add_argument("--finding", required=True)
    p.add_argument("--outcome", required=True,
                   choices=["confirmed", "overruled"])
    p.add_argument("--by", required=True, help="裁决人（具名）")
    p.add_argument("--reason", required=True)
    p.add_argument("--obligation", action="append", default=None,
                   help="裁决附带义务（可重复）：条件文本，随裁决入义务账")
    p.add_argument("--obligation-finding", action="append", default=None,
                   help="与 --obligation 按序配对的关联发现（缺省挂本条发现）")
    p.set_defaults(fn=cmd_adjudicate)

    p = sub.add_parser("advance", help="状态机推进一段")
    p.add_argument("path")
    p.set_defaults(fn=cmd_advance)

    p = sub.add_parser("deliver", help="交付（过 delivered 门 + 交付清单）")
    p.add_argument("path")
    p.add_argument("--degradation-statement", default=None,
                   help="隔离降档时的降档声明（degraded 必填）")
    p.set_defaults(fn=cmd_deliver)

    p = sub.add_parser("validate", help="校验评审包")
    p.add_argument("path")
    p.set_defaults(fn=cmd_validate)

    p = sub.add_parser("status", help="看状态与下一段门缺口")
    p.add_argument("path")
    p.set_defaults(fn=cmd_status)

    args = parser.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
