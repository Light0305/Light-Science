"""light-analysis CLI（Phase 1 + Phase 2）。

  init            建分析包骨架（analysis.yaml / verdicts.jsonl / spec_ledger.yaml /
                  spec_results.jsonl / conclusions.yaml / exploratory/）
  intake          A0 承接：消费 execution_card.json + expected_registry.jsonl，
                  哈希对齐 + 逐行可判性点名（audit 双份落盘）+ 不可判行预登记
  validate        校验分析包（结构 + 全部纪律，逐条点名）
  advance         包级状态机推进一段（逐段过门，缺口逐项列出）
  status          看状态、判定计数与下一段门的缺口预演
  register-sesoi  从 Design 来源文件按指针登记 SESOI 快照进分析规格（spec 区）
  judge           判定子流程：逐可判行计算量组 → 联合推断 → 四象限落字 →
                  按族校正 → verdicts 落盘 + spec_results 账平
  review          判定复核子流程：prepare 备自包含复核包 / record 落收据 /
                  import 外部判定回填 / unavailable 显式不可用通道
  grade           结论包填充：主张映射 + 强度机械合成 + 数字溯源表
  export          A7 交接：conclusion_card.json + ANALYSIS_REPORT.md
  reflux          生成回流条目（补充消融 ≤1 轮 / 标准缺失 / 证据状态通知）
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .conclude import ConcludeError, export_conclusion, run_grade
from .gates import NEXT, GateError, advance_package, gate_gaps_for
from .intake import IntakeError, run_intake
from .judge import JudgeError, register_sesoi, request_reflux, run_judge
from .project import init_package, load_package
from .review import (
    ReviewError, import_review, prepare_review, record_review,
    record_unavailable,
)
from .validate import validate_package


def _fail(msg: str) -> int:
    print(f"错误：{msg}", file=sys.stderr)
    return 1


def cmd_init(args) -> int:
    try:
        root = init_package(Path(args.path), title=args.title or "")
    except FileExistsError as e:
        return _fail(str(e))
    print(f"已建分析包骨架：{root}（状态 intake）")
    return 0


def cmd_intake(args) -> int:
    try:
        audit = run_intake(
            Path(args.path), args.execution_card, args.registry,
            design_card_path=args.design_card,
            analyst_name=args.analyst, analyst_family=args.family)
    except IntakeError as e:
        print("承接被拦（逐项缺口）：", file=sys.stderr)
        for g in e.gaps:
            print(f"  - {g}", file=sys.stderr)
        return 1
    s = audit["summary"]
    print(f"承接完成：{s['total']} 行 — 可判 {s['judgeable']}、"
          f"untested 预登记 {s['untested_candidate']}、"
          f"undetermined 预登记 {s['undetermined_candidate']}、"
          f"null 精度预警 {s['null_precision_warnings']}")
    print("逐行可判性清单已落 audit.json / audit.md")
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


def cmd_advance(args) -> int:
    try:
        new_state = advance_package(Path(args.path))
    except GateError as e:
        print("过门被拦（逐项缺口）：", file=sys.stderr)
        for g in e.gaps:
            print(f"  - {g}", file=sys.stderr)
        return 1
    print(f"已推进 → {new_state}")
    return 0


def cmd_status(args) -> int:
    pkg = load_package(Path(args.path))
    analysis = pkg["analysis"]
    if analysis is None:
        return _fail("分析包不存在（先 init）")
    counts = analysis.get("counts") or {}
    print(f"分析包：{analysis.get('analysis_id')}  状态：{analysis.get('status')}")
    if analysis.get("blocked"):
        b = analysis["blocked"]
        print(f"  blocked：自 {b.get('from_state')} 推进时被拦 — {b.get('reason')}")
    print("  判定计数：" + "、".join(
        f"{k}={counts.get(k, 0)}" for k in
        ("positive", "negative", "null", "undetermined", "untested"))
        + f"（登记行 {counts.get('total_lines', 0)}）")
    status = analysis.get("status")
    from_state = (analysis.get("blocked") or {}).get("from_state") \
        if status == "blocked" else status
    target = NEXT.get(from_state)
    if target:
        gaps = gate_gaps_for(Path(args.path), target)
        if gaps:
            print(f"  下一段 → {target} 尚有 {len(gaps)} 项缺口：")
            for g in gaps:
                print(f"    - {g}")
        else:
            print(f"  下一段 → {target}：门已齐，可 advance")
    return 0


def _gaps_fail(exc) -> int:
    print("被拦（逐项缺口）：", file=sys.stderr)
    for g in exc.gaps:
        print(f"  - {g}", file=sys.stderr)
    return 1


def cmd_register_sesoi(args) -> int:
    try:
        entry = register_sesoi(Path(args.path), args.from_file, args.pointer,
                               line_ids=args.line)
    except JudgeError as e:
        return _gaps_fail(e)
    print(f"SESOI 已登记：指针 {entry['sesoi_pointer']} → 快照值 "
          f"{entry['sesoi_value']}（来源哈希 {entry['source_hash'][:12]}…）")
    return 0


def cmd_judge(args) -> int:
    try:
        summary = run_judge(Path(args.path), args.data, decided_by=args.by)
    except JudgeError as e:
        return _gaps_fail(e)
    print(f"判定完成：已判 {len(summary['judged'])} 行"
          f"（主规格 {summary['primary_spec_id']}），"
          f"undetermined {len(summary['undetermined'])} 行，"
          f"spec_results 新增 {summary['spec_results_rows']} 行")
    if summary["undetermined"]:
        print("  undetermined 行：" + "、".join(summary["undetermined"])
              + "（原因逐项落在各行 note）")
    return 0


def cmd_review(args) -> int:
    try:
        if args.review_cmd == "prepare":
            info = prepare_review(Path(args.path))
            print(f"复核包已生成：{info['packet']}（边界行 "
                  f"{len(info['scope_line_ids'])}："
                  f"{'、'.join(info['scope_line_ids']) or '无'}）")
        elif args.review_cmd == "record":
            if args.review_unavailable:
                record_unavailable(Path(args.path), reason=args.reason)
                print("已落 REVIEW_UNAVAILABLE：delivered 将被拦，"
                      "复核恢复后 record 正式收据再续推")
            else:
                review = record_review(
                    Path(args.path), args.reviewer, args.family,
                    outcome=args.outcome, notes=args.notes)
                print(f"复核收据已落：{review['receipt_id']}"
                      f"（{review['reviewer']} / {review['family']}）")
        elif args.review_cmd == "import":
            review = import_review(Path(args.path), args.from_json)
            print(f"外部判定已回填：{review['receipt_id']}"
                  f"（{review['reviewer']} / {review['family']}，"
                  f"逐行 agree {len(review['scope_line_ids'])} 行）")
    except ReviewError as e:
        return _gaps_fail(e)
    return 0


def cmd_grade(args) -> int:
    try:
        summary = run_grade(Path(args.path), notes_path=args.notes)
    except ConcludeError as e:
        return _gaps_fail(e)
    print("结论包已填充：主张支持度 "
          + "、".join(f"{k}={v}" for k, v in summary["claims"].items())
          + "；强度 "
          + "、".join(f"{k}={v}" for k, v in summary["grades"].items())
          + f"；数字溯源 {summary['provenance_rows']} 行")
    return 0


def cmd_export(args) -> int:
    try:
        out = export_conclusion(Path(args.path), out_dir=args.out_dir)
    except ConcludeError as e:
        return _gaps_fail(e)
    print(f"交接完成：{out['conclusion_card']} + {out['report']}"
          f"（主张 {out['claims']} 条）")
    return 0


def cmd_reflux(args) -> int:
    try:
        entry = request_reflux(Path(args.path), args.kind, args.lines,
                               args.reason, target=args.target)
    except JudgeError as e:
        return _gaps_fail(e)
    print(f"回流条目已生成：{entry['reflux_id']}（{entry['kind']} → "
          f"{entry['target']}），文件 {entry['file']}")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="light-analysis",
        description="light-analysis：可审计的分析结论包（Phase 2）")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("init", help="建分析包骨架")
    p.add_argument("path")
    p.add_argument("--title", default="")
    p.set_defaults(fn=cmd_init)

    p = sub.add_parser("intake", help="A0 承接与可判性校验")
    p.add_argument("path")
    p.add_argument("--execution-card", required=True)
    p.add_argument("--registry", required=True)
    p.add_argument("--design-card", default=None)
    p.add_argument("--analyst", default=None)
    p.add_argument("--family", default=None)
    p.set_defaults(fn=cmd_intake)

    p = sub.add_parser("validate", help="校验分析包")
    p.add_argument("path")
    p.set_defaults(fn=cmd_validate)

    p = sub.add_parser("advance", help="状态机推进一段")
    p.add_argument("path")
    p.set_defaults(fn=cmd_advance)

    p = sub.add_parser("status", help="看状态与下一段门缺口")
    p.add_argument("path")
    p.set_defaults(fn=cmd_status)

    p = sub.add_parser("register-sesoi", help="登记 SESOI 快照进分析规格")
    p.add_argument("path")
    p.add_argument("--from", dest="from_file", required=True,
                   help="Design 来源文件（design.yaml / design_card.json）")
    p.add_argument("--pointer", required=True,
                   help="来源文件内的点分路径，如 evaluation.sesoi")
    p.add_argument("--line", action="append", default=None,
                   help="登记到哪条登记行（可重复；缺省=全部可判行）")
    p.set_defaults(fn=cmd_register_sesoi)

    p = sub.add_parser("judge", help="判定子流程（须先过 checked）")
    p.add_argument("path")
    p.add_argument("--data", required=True, help="判定材料 JSON（两臂值/摘要）")
    p.add_argument("--by", default=None, help="判定者身份（缺省取登记头 analyst）")
    p.set_defaults(fn=cmd_judge)

    p = sub.add_parser("review", help="判定复核子流程")
    p.add_argument("path")
    rsub = p.add_subparsers(dest="review_cmd", required=True)
    rp = rsub.add_parser("prepare", help="生成自包含复核包")
    rr = rsub.add_parser("record", help="落复核收据或 REVIEW_UNAVAILABLE")
    rr.add_argument("--reviewer", default=None)
    rr.add_argument("--family", default=None)
    rr.add_argument("--outcome", default="agree",
                    choices=["agree", "agree_with_notes"])
    rr.add_argument("--notes", default=None)
    rr.add_argument("--review-unavailable", action="store_true",
                    help="显式登记复核不可用（拦 delivered，不许假装复核过）")
    rr.add_argument("--reason", default=None)
    ri = rsub.add_parser("import", help="外部判定 JSON 回填")
    ri.add_argument("--from-json", required=True)
    p.set_defaults(fn=cmd_review)

    p = sub.add_parser("grade", help="结论包填充（主张映射/强度/溯源）")
    p.add_argument("path")
    p.add_argument("--notes", default=None,
                   help="可选 JSON：{boundaries, limitations} 补入结论包")
    p.set_defaults(fn=cmd_grade)

    p = sub.add_parser("export", help="A7 交接：conclusion_card.json + 报告")
    p.add_argument("path")
    p.add_argument("--out-dir", default=None)
    p.set_defaults(fn=cmd_export)

    p = sub.add_parser("reflux", help="生成回流条目（只生成不越权）")
    p.add_argument("path")
    p.add_argument("--kind", required=True,
                   choices=["supplementary_ablation", "standard_gap",
                            "evidence_notice"])
    p.add_argument("--lines", required=True,
                   help="涉及登记行 id，逗号分隔")
    p.add_argument("--reason", required=True)
    p.add_argument("--target", default=None)
    p.set_defaults(fn=lambda a: cmd_reflux(_split_lines(a)))

    args = parser.parse_args(argv)
    return args.fn(args)


def _split_lines(args):
    args.lines = [s.strip() for s in args.lines.split(",") if s.strip()]
    return args


if __name__ == "__main__":
    raise SystemExit(main())
