"""light-design CLI（一期 + 二期）。

命令：
  init     建项目骨架（design-stage/ + designs/ + exports/ + review/ + 索引）
  new      建一份 draft 设计书（可 --from-handoff 导入 Idea 交接件承接区，
           缺项即列打回清单）
  validate 校验设计书（结构 + 硬规则 + 冻结哈希，逐条报错；
           另点名功效借位警告 power_warnings，不拦截）
  power    功效真计算（v1.2）：精确解求解器（非中心 t/F）——SESOI 只
           读 evaluation.sesoi 登记块，σ/f 为设计前提参数；--apply 把
           design_size 落格写回设计书（仅 draft），--simulate 附蒙特
           卡洛交叉验证（口径同 measured-round1）
  advance  按状态机验门推进（draft → reviewed → frozen；旁路 returned/blocked）
  amend    frozen 后唯一修订通道：amendment 追加（命门字段须 --user-signed）
  review   定版评审子流程（二期）：prepare 生成自包含评审包 /
           record 落盘评审记录（同族拒收、REVIEW_UNAVAILABLE 降级通道）；
           带 --amendment <n> 时走 amendment 增量评审（DES-D02，只审
           命门 amendment 的变更项及其影响面，类别分流轻/全两轨）
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
    amendment_review_dir,
    load_checklist_items,
    prepare_amendment_review,
    prepare_review,
    record_amendment_review,
    record_amendment_review_unavailable,
    record_review,
    record_review_unavailable,
    review_dir,
)
from .power import solve_from_design
from .schema import (
    ALL_STATES,
    AMD_CATEGORIES,
    TIERS,
    power_warnings,
    validate_design,
)
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
    for w in power_warnings(design):
        print(f"  ! 警告：{w}")
    if errors:
        print(f"{args.design_id} 不合法（{len(errors)} 条）：")
        for e in errors:
            print(f"  - {e}")
        return 1
    print(f"{args.design_id} 合法（status={design.get('status')}，tier={design.get('tier')}）")
    return 0


def cmd_power(args) -> int:
    root = Path(args.project)
    try:
        design = load_design(root, args.design_id)
    except FileNotFoundError as e:
        return _fail(str(e))
    points = None
    if args.sesoi_points:
        try:
            points = [float(x) for x in args.sesoi_points.split(",")
                      if x.strip()]
        except ValueError:
            return _fail("--sesoi-points 须为逗号分隔的数字")
    try:
        out = solve_from_design(
            design, args.form, sigma=args.sigma,
            sigma_diff=args.sigma_diff, cohen_f=args.cohen_f,
            k_groups=args.groups, sesoi_points=points,
            simulate=args.simulate, reps=args.reps, seed=args.seed)
    except ValueError as e:
        return _fail(str(e))
    ds = out["design_size"]
    spread = ""
    if ds["form"] == "two_arm":
        spread = f"σ={ds['sigma']}"
    elif ds["form"] == "paired":
        spread = f"σ_diff={ds['sigma_diff']}"
    else:
        spread = f"Cohen f={ds['cohen_f']}"
    print(f"功效精确解（route={ds['route']}，唯一产出口径）："
          f"SESOI={ds['sesoi_value']}（evaluation.sesoi 登记值）｜"
          f"{spread}｜alpha={ds['alpha']}｜target_power={ds['target_power']}")
    if ds["form"] == "anova":
        print(f"  总 N 原值={ds['raw_n']:.4f} → 每组 {ds['per_group_n']}"
              f"（总 N={ds['total_n']}），实际功效 {ds['achieved_power']:.6f}")
    else:
        unit = "对" if ds["form"] == "paired" else "每臂"
        print(f"  原值 n={ds['raw_n']:.4f} → {unit} {ds['per_group_n']}"
              f"（总 {ds['total_n']}），实际功效 {ds['achieved_power']:.6f}")
    zr = ds.get("z_reference")
    if zr:
        print(f"  z 近似速查（{zr['route']}，不作产出）：每单位 "
              f"{zr['per_group_n']}")
    sim = ds.get("sim_check")
    if sim:
        print(f"  模拟交叉验证：n={sim['n']} 处估计 {sim['estimate']:.4f} "
              f"± {sim['mc_se']:.4f}（{sim['reps']} 次，种子 {sim['seed']}）")
    if ds.get("route_note"):
        print(f"  {ds['route_note']}")
    for row in out.get("sensitivity_table") or []:
        print(f"  敏感性 SESOI={row['sesoi_value']} → 原值 "
              f"{row['raw_n']:.4f} → 每单位 {row['per_group_n']}，"
              f"实际功效 {row['achieved_power']:.6f}")
    if args.apply:
        if design.get("status") != "draft":
            return _fail("--apply 只许 draft 设计书（已推进状态的设计书"
                         "请走 amend 修订 resources.power.design_size）")
        res = design.setdefault("resources", {})
        power_block = res.get("power")
        if not isinstance(power_block, dict):
            power_block = {}
            res["power"] = power_block
        power_block["design_size"] = ds
        if out.get("sensitivity_table"):
            power_block["sensitivity_table"] = out["sensitivity_table"]
        save_design(root, design)
        print("已落格：resources.power.design_size 已写入设计书（draft）")
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
            user_signed=args.user_signed, by=args.by, date=today(),
            category=args.category, branch_ref=args.branch_ref)
    except (GateError, ValueError, KeyError, IndexError) as e:
        if isinstance(e, GateError):
            for err in e.errors:
                print(f"  - {err}")
            return 1
        return _fail(f"amendment 失败：{e}")
    save_design(root, design)
    refresh_index(root)
    kind = "命门字段（用户签）" if amd.get("critical") else "普通字段（自动留痕）"
    idx = len((design.get("freeze") or {}).get("amendments") or [])
    print(f"amendment 已追加：#{idx} {args.field}（{kind}，类别 "
          f"{amd.get('category')}），新哈希 {amd['new_hash'][:12]}…")
    if (amd.get("review") or {}).get("status") == "pending_review":
        print(f"该 amendment 为命门修订，已标 pending_review：导出前须走 "
              f"review prepare --amendment {idx} → 异家族增量评审 → "
              f"review record --amendment {idx}（或 --review-unavailable "
              "显式落字）。")
    return 0


def cmd_review_prepare(args) -> int:
    root = Path(args.project)
    try:
        design = load_design(root, args.design_id)
    except FileNotFoundError as e:
        return _fail(str(e))
    try:
        if args.amendment:
            out = prepare_amendment_review(root, design, args.amendment,
                                           date=today())
            save_design(root, design)
            print(f"增量评审包已生成：{out['dir']}")
            print(f"  - amendment_review_packet.md（自包含：变更前后值 + "
                  "影响面 + 原冻结收据指针）")
            print(f"  - amendment_review_checklist.yaml（评审者逐项填写版）")
            print(f"  - 轨道：{out['track']}；须核条目："
                  f"{'、'.join(out['items_required'])}")
            print(f"判定回来后：review record --amendment {args.amendment} "
                  "--from-json <判定.json> 落盘。")
            return 0
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
        if args.amendment:
            return _record_amendment(args, root, design)
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


def _record_amendment(args, root: Path, design: dict) -> int:
    """review record --amendment <n>：增量评审落盘（DES-D02）。
    与定版评审同构：--review-unavailable 走显式落字通道；判定来自
    --from-json 或增量评审清单；同族拒收在 record 层执行。"""
    idx = args.amendment
    try:
        if args.review_unavailable:
            record = record_amendment_review_unavailable(
                root, design, idx, date=today(), note=args.note or "")
            save_design(root, design)
            refresh_index(root)
            print(f"已落字降级记录：{args.design_id} amendment #{idx} "
                  "增量评审 REVIEW_UNAVAILABLE（待审解除；导出件将注明"
                  "增量评审未完成，恢复后补评审）")
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
                amendment_review_dir(root, args.design_id, idx) / \
                "amendment_review_checklist.yaml"
            if not cp.exists():
                return _fail(f"增量评审清单不存在：{cp}（先跑 review "
                             f"prepare --amendment {idx}，或用 --from-json "
                             "回填外部判定）")
            data = load_checklist_items(cp)
            source = "checklist"
        if args.reviewer_model:
            data["reviewer_model"] = args.reviewer_model
        if args.reviewer_family:
            data["reviewer_family"] = args.reviewer_family
        if args.decision:
            data["decision"] = args.decision
        record = record_amendment_review(root, design, idx, data,
                                         date=today(), source=source)
    except ReviewError as e:
        print(f"增量评审记录被拒：{args.design_id} amendment #{idx}"
              f"（{len(e.errors)} 条）：")
        for err in e.errors:
            print(f"  - {err}")
        return 1
    except (json.JSONDecodeError, ValueError) as e:
        return _fail(f"判定文件解析失败：{e}")
    save_design(root, design)
    refresh_index(root)
    print(f"增量评审记录已落盘：{args.design_id} amendment #{idx} → "
          f"status={record['status']}（轨道 {record['track']}，评审者 "
          f"{record['reviewer']} / {record['family']}）")
    print(f"收据：{record['review_id']}；存根 review/{args.design_id}/"
          f"amendments/amd-{idx}/amendment_review_record.json")
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
    p.add_argument("--category", choices=AMD_CATEGORIES, default="unforeseen",
                   help="修订类别（DES-D02/C-补04 分流）：prewritten_branch="
                        "执行定版预写的偏离分支（须 --branch-ref 点名）；"
                        "unforeseen=未预见变更（默认，最严口径）")
    p.add_argument("--branch-ref", default=None,
                   help="prewritten_branch 类别时点名 plan.deviation_branches "
                        "中的分支 id")
    p.add_argument("--by", default="")
    p.set_defaults(func=cmd_amend)

    p = sub.add_parser("review", help="定版评审子流程（prepare / record）")
    rsub = p.add_subparsers(dest="review_command", required=True)
    rp = rsub.add_parser("prepare", help="生成自包含评审包 review/<design_id>/"
                                        "（--amendment 走增量评审包）")
    rp.add_argument("project")
    rp.add_argument("design_id")
    rp.add_argument("--amendment", type=int, default=None,
                    help="amendment 序号（1 起）：生成该命门 amendment 的"
                         "增量评审包（DES-D02）")
    rp.set_defaults(func=cmd_review_prepare)
    rr = rsub.add_parser("record", help="落盘评审记录（同族拒收；"
                                       "--review-unavailable 走降级通道；"
                                       "--amendment 落盘增量评审记录）")
    rr.add_argument("project")
    rr.add_argument("design_id")
    rr.add_argument("--amendment", type=int, default=None,
                    help="amendment 序号（1 起）：落盘该 amendment 的"
                         "增量评审记录（DES-D02）")
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

    p = sub.add_parser("power", help="功效真计算：精确解求解器（非中心 t/F）；"
                                     "SESOI 读 evaluation.sesoi 登记块")
    p.add_argument("project")
    p.add_argument("design_id")
    p.add_argument("--form", required=True,
                   choices=("two_arm", "paired", "anova"))
    p.add_argument("--sigma", type=float, default=None,
                   help="two_arm：组内标准差（设计前提，依据须在 power.basis 落字）")
    p.add_argument("--sigma-diff", type=float, default=None,
                   help="paired：配对差标准差（设计前提）")
    p.add_argument("--cohen-f", type=float, default=None,
                   help="anova：Cohen f（设计前提）")
    p.add_argument("--groups", type=int, default=None, help="anova：组数")
    p.add_argument("--sesoi-points", default=None,
                   help="敏感性表 SESOI 点，逗号分隔（如 1,2,3）")
    p.add_argument("--simulate", action="store_true",
                   help="附蒙特卡洛交叉验证（种子 20261021 / 2000 次口径）")
    p.add_argument("--reps", type=int, default=2000)
    p.add_argument("--seed", type=int, default=20261021)
    p.add_argument("--apply", action="store_true",
                   help="把 design_size 落格写回设计书（仅 draft）")
    p.set_defaults(func=cmd_power)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
