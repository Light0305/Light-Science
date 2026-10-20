"""light-design CLI（一期 + 二期）。

命令：
  init     建项目骨架（design-stage/ + designs/ + exports/ + review/ + 索引）
  new      建一份 draft 设计书（可 --from-handoff 导入 Idea 交接件承接区，
           缺项即列打回清单）
  validate 校验设计书（结构 + 硬规则 + 冻结哈希，逐条报错）
  advance  按状态机验门推进（draft → reviewed → frozen；旁路 returned/blocked）
  amend    frozen 后唯一修订通道：amendment 追加（命门字段须 --user-signed）
  review   定版评审子流程（二期）：prepare 生成自包含评审包 /
           record 落盘评审记录（同族拒收、REVIEW_UNAVAILABLE 降级通道）
  export   交接四件套导出（二期，仅 frozen；非 frozen 拒绝并列缺口）
  report   刷新 design-stage/DESIGN_REPORT.md（二期，手工区保留）
  list     列出项目内全部设计书与状态
  render   由 design.yaml 重渲染 design.md
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .export import ExportError, build_report, export_design
from .gates import GateError, advance as gate_advance, apply_amendment
from .project import (
    init_project,
    list_designs,
    load_design,
    new_design,
    refresh_index,
    save_design,
)
from .review import (
    ReviewError,
    load_checklist_items,
    prepare_review,
    record_review,
    record_review_unavailable,
    review_dir,
)
from .schema import ALL_STATES, TIERS, validate_design
from .util import today


def _fail(msg: str) -> int:
    print(f"错误：{msg}", file=sys.stderr)
    return 1


def cmd_init(args) -> int:
    root = Path(args.dir)
    try:
        init_project(root, args.direction)
    except FileExistsError as e:
        return _fail(str(e))
    print(f"项目已建：{root}（方向：{args.direction}）")
    return 0


def cmd_new(args) -> int:
    root = Path(args.project)
    handoff = Path(args.from_handoff) if args.from_handoff else None
    if handoff is not None and not handoff.exists():
        return _fail(f"交接件不存在：{handoff}")
    try:
        design, missing = new_design(root, args.title, args.idea_id or "",
                                     tier=args.tier, handoff_path=handoff)
    except (FileExistsError, ValueError) as e:
        return _fail(str(e))
    print(f"已建设计书：{design['design_id']}（status=draft，tier={design['tier']}）")
    if handoff is not None:
        if missing:
            print(f"入口校验打回清单（{len(missing)} 项缺失/为空，设计停在 draft，"
                  "须回 Idea 回补，不许 Design 临场发明）：")
            for m in missing:
                print(f"  - exec_spec.{m}")
        else:
            print("交接六项承接齐全（详见 intake 区与 design-stage/intake_log.md）。")
    else:
        print("提示：未给交接件，intake 承接区为空 — 补齐六项承接前不许离开 draft。")
    return 0


def cmd_validate(args) -> int:
    root = Path(args.project)
    try:
        design = load_design(root, args.design_id)
    except FileNotFoundError as e:
        return _fail(str(e))
    errors = validate_design(design)
    if errors:
        print(f"{args.design_id} 不合法（{len(errors)} 条）：")
        for e in errors:
            print(f"  - {e}")
        return 1
    print(f"{args.design_id} 合法（status={design.get('status')}，tier={design.get('tier')}）")
    return 0


def cmd_advance(args) -> int:
    root = Path(args.project)
    try:
        design = load_design(root, args.design_id)
    except FileNotFoundError as e:
        return _fail(str(e))
    try:
        gate_advance(design, args.to, by=args.by, date=today(), note=args.note or "")
    except GateError as e:
        print(f"推进被拦：{args.design_id} → {args.to}（{len(e.errors)} 条未过门）：")
        for err in e.errors:
            print(f"  - {err}")
        return 1
    save_design(root, design)
    refresh_index(root)
    print(f"已推进：{args.design_id} → {args.to}")
    if args.to == "frozen":
        print(f"冻结哈希：{(design.get('freeze') or {}).get('content_hash')}")
    return 0


def cmd_amend(args) -> int:
    root = Path(args.project)
    try:
        design = load_design(root, args.design_id)
    except FileNotFoundError as e:
        return _fail(str(e))
    try:
        value = json.loads(args.value)
    except (json.JSONDecodeError, ValueError):
        value = args.value
    try:
        amd = apply_amendment(
            design, args.field, value,
            reason=args.reason, results_seen=args.results_seen,
            user_signed=args.user_signed, by=args.by, date=today())
    except (GateError, ValueError, KeyError, IndexError) as e:
        if isinstance(e, GateError):
            for err in e.errors:
                print(f"  - {err}")
            return 1
        return _fail(f"amendment 失败：{e}")
    save_design(root, design)
    refresh_index(root)
    kind = "命门字段（用户签）" if amd.get("critical") else "普通字段（自动留痕）"
    print(f"amendment 已追加：{args.field}（{kind}），新哈希 {amd['new_hash'][:12]}…")
    return 0


def cmd_review_prepare(args) -> int:
    root = Path(args.project)
    try:
        design = load_design(root, args.design_id)
    except FileNotFoundError as e:
        return _fail(str(e))
    try:
        out = prepare_review(root, design, date=today())
    except ReviewError as e:
        for err in e.errors:
            print(f"  - {err}", file=sys.stderr)
        return 1
    print(f"评审包已生成：{out['dir']}")
    print(f"  - review_packet.md（自包含：全文交给异家族模型/专家评审）")
    print(f"  - review_checklist.yaml（评审者逐项填写版）")
    print("判定回来后：review record --from-json <判定.json> 落盘。")
    return 0


def cmd_review_record(args) -> int:
    root = Path(args.project)
    try:
        design = load_design(root, args.design_id)
    except FileNotFoundError as e:
        return _fail(str(e))
    try:
        if args.review_unavailable:
            record = record_review_unavailable(
                root, design, date=today(), note=args.note or "")
            save_design(root, design)
            refresh_index(root)
            print(f"已落盘降级记录：{args.design_id} review_status="
                  "REVIEW_UNAVAILABLE（硬门未过，不许定版；恢复后补评审）")
            print(f"收据：{record['review_id']}")
            return 0
        if args.from_json:
            jp = Path(args.from_json)
            if not jp.exists():
                return _fail(f"判定 JSON 不存在：{jp}")
            data = json.loads(jp.read_text(encoding="utf-8"))
            source = "external_json"
        else:
            cp = Path(args.checklist) if args.checklist else \
                review_dir(root, args.design_id) / "review_checklist.yaml"
            if not cp.exists():
                return _fail(f"评审清单不存在：{cp}（先跑 review prepare，"
                             "或用 --from-json 回填外部判定）")
            data = load_checklist_items(cp)
            source = "checklist"
        # 命令行显式参数覆盖清单/JSON 中的评审者与决议
        if args.reviewer_model:
            data["reviewer_model"] = args.reviewer_model
        if args.reviewer_family:
            data["reviewer_family"] = args.reviewer_family
        if args.decision:
            data["decision"] = args.decision
        record = record_review(root, design, data, date=today(), source=source)
    except ReviewError as e:
        print(f"评审记录被拒：{args.design_id}（{len(e.errors)} 条）：")
        for err in e.errors:
            print(f"  - {err}")
        return 1
    except (json.JSONDecodeError, ValueError) as e:
        return _fail(f"判定文件解析失败：{e}")
    save_design(root, design)
    refresh_index(root)
    print(f"评审记录已落盘：{args.design_id} → decision={record['decision']}"
          f"（评审者 {record['reviewer']} / {record['family']}）")
    print(f"收据：{record['review_id']}；存根 review/{args.design_id}/review_record.json")
    return 0


def cmd_export(args) -> int:
    root = Path(args.project)
    try:
        design = load_design(root, args.design_id)
    except FileNotFoundError as e:
        return _fail(str(e))
    try:
        out = export_design(root, design)
    except ExportError as e:
        print(f"导出被拒：{args.design_id}（{len(e.errors)} 条缺口）：")
        for err in e.errors:
            print(f"  - {err}")
        return 1
    print(f"交接四件套已导出：{out['dir']}")
    for key in ("brief", "design_card", "expected_registry", "reproducibility"):
        print(f"  - {out[key].name}")
    print(f"运行清单拓扑序：{' → '.join(out['runs'])}")
    return 0


def cmd_report(args) -> int:
    root = Path(args.project)
    if not root.exists():
        return _fail(f"项目不存在：{root}")
    summary = build_report(root)
    counts = "、".join(f"{k} × {v}" for k, v in summary["status_counts"].items())
    print(f"DESIGN_REPORT 已刷新：{summary['report_path']}")
    print(f"设计总数 {summary['total']}（{counts or '无'}）；"
          f"冻结 {len(summary['frozen'])}；amendment {summary['amendments']}；"
          f"打回条目 {summary['returned_items']}")
    return 0


def cmd_list(args) -> int:
    root = Path(args.project)
    designs = list_designs(root)
    if not designs:
        print("（无设计书）")
        return 0
    for d in designs:
        print(f"{d['design_id']}  [{d.get('status')}/{d.get('tier')}]  "
              f"{d.get('title')}（idea: {d.get('idea_id')}）")
    return 0


def cmd_render(args) -> int:
    root = Path(args.project)
    try:
        design = load_design(root, args.design_id)
    except FileNotFoundError as e:
        return _fail(str(e))
    save_design(root, design)
    print(f"已渲染：designs/{args.design_id}/design.md")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="light-design",
        description="light-design：定版想法卡 → 可开工可证伪的研究设计书")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init", help="建项目骨架")
    p.add_argument("dir")
    p.add_argument("--direction", required=True)
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("new", help="建一份 draft 设计书")
    p.add_argument("project")
    p.add_argument("--title", required=True)
    p.add_argument("--idea-id", default="", help="承接的定版想法卡 idea_id")
    p.add_argument("--tier", choices=TIERS, default="full")
    p.add_argument("--from-handoff", default=None,
                   help="Idea 交接件路径（idea_card.json / idea.yaml）")
    p.set_defaults(func=cmd_new)

    p = sub.add_parser("validate", help="校验设计书（结构 + 硬规则 + 冻结哈希）")
    p.add_argument("project")
    p.add_argument("design_id")
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("advance", help="按状态机验门推进状态")
    p.add_argument("project")
    p.add_argument("design_id")
    p.add_argument("--to", required=True, choices=ALL_STATES)
    p.add_argument("--by", default="")
    p.add_argument("--note", default="")
    p.set_defaults(func=cmd_advance)

    p = sub.add_parser("amend", help="frozen 后 amendment 追加修订")
    p.add_argument("project")
    p.add_argument("design_id")
    p.add_argument("--field", required=True, help="字段路径，如 evaluation.readout.positive.meaning")
    p.add_argument("--value", required=True, help="新值（JSON 解析失败则按原文字符串）")
    p.add_argument("--reason", required=True)
    p.add_argument("--results-seen", required=True,
                   help="改时是否已见结果（声明，如 '未跑任何运行' / '已见判别实验结果'）")
    p.add_argument("--user-signed", action="store_true",
                   help="命门字段修订的用户签（判读/主指标/主张/熔断线必填）")
    p.add_argument("--by", default="")
    p.set_defaults(func=cmd_amend)

    p = sub.add_parser("review", help="定版评审子流程（prepare / record）")
    rsub = p.add_subparsers(dest="review_command", required=True)
    rp = rsub.add_parser("prepare", help="生成自包含评审包 review/<design_id>/")
    rp.add_argument("project")
    rp.add_argument("design_id")
    rp.set_defaults(func=cmd_review_prepare)
    rr = rsub.add_parser("record", help="落盘评审记录（同族拒收；"
                                       "--review-unavailable 走降级通道）")
    rr.add_argument("project")
    rr.add_argument("design_id")
    rr.add_argument("--from-json", default=None,
                    help="外部判定 JSON 路径（reviewer_model/family、decision、items）")
    rr.add_argument("--checklist", default=None,
                    help="评审清单路径（默认 review/<design_id>/review_checklist.yaml）")
    rr.add_argument("--reviewer-model", default=None)
    rr.add_argument("--reviewer-family", default=None)
    rr.add_argument("--decision", default=None, choices=("pass", "reject"))
    rr.add_argument("--review-unavailable", action="store_true",
                    help="跨模型评审不可得：显式落 REVIEW_UNAVAILABLE 降级记录")
    rr.add_argument("--note", default="", help="降级记录附注")
    rr.set_defaults(func=cmd_review_record)

    p = sub.add_parser("export", help="交接四件套导出（仅 frozen）")
    p.add_argument("project")
    p.add_argument("design_id")
    p.set_defaults(func=cmd_export)

    p = sub.add_parser("report", help="刷新 DESIGN_REPORT.md（手工区保留）")
    p.add_argument("project")
    p.set_defaults(func=cmd_report)

    p = sub.add_parser("list", help="列出全部设计书")
    p.add_argument("project")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("render", help="重渲染 design.md")
    p.add_argument("project")
    p.add_argument("design_id")
    p.set_defaults(func=cmd_render)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
