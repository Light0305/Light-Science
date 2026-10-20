"""light-experiment CLI（二期）。

一期命令：
  init        建项目骨架（experiment-stage/ + executions/ + 索引）
  intake      消费 Design 交接四件套建执行包（哈希/行对应核对，
              缺项逐条列清单打回，执行包停在 intake）
  run-new     为 brief 条目新建一次尝试（--retry-of 接已终止旧尝试，
              新 run 独立成号 + 血缘指回；--spec 填身份成分）
  run-start   开跑：身份下限全过 → 冻结 identity/params 哈希 + 出生证明
  run-finish  终止：落 exit_status（终止分类词表）+ 指标/抢救产物登记
  event       向 events.jsonl 追加一条轨迹事件（只增）
  validate    校验执行包（结构 + 哈希重算 + 事件只增 + 对账行对齐）
  advance     包级状态机推进（--run 时改为推进单个 run）
  list        列执行包（给 exec_id 时列其 runs）
  render      渲染 EXECUTION_REPORT.md（摘要视图）

二期命令：
  acceptance  基线复现验收（init 冻结验收表 / record 逐叶判定，
              证据只认冷启动重跑；show 看结论）
  deviation   偏离登记与闭包作废（raise → publish 公示 → apply 生效；
              override 显式豁免留痕；list 列表）
  failure     失败双层分类（classify 落 MAST × IVE 并自动回流；
              review 人工抽验落痕）
  reflux      回流条目跟踪（list / update 状态 pending→sent→resolved）
  reconcile   对账实质化（fill 逐行回填事实层；check 逐行清零检查）
  budget      预算闸（check 对照熔断线触发即停报；无任何放宽命令）
  export-card 导出 execution_card.json（给 Analysis 的结构化投影）

三期命令（v1.1）：
  stale       事前 stale 清单（EXP-D02）：以现行设计链 + --spec 声明
              逐维比对出生证明，输出 current/stale/voided 三态清单
              （机读 JSON + 人读 MD 两份）；只读，不改包状态。
  （run-finish 内置 EXP-D03 干预机械核验：声称 vs 实际生效值由工具
   按登记的核验方式机械比对，不符自动转 deviated 候选。）
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .events import append_event
from .gates import GateError, advance_package, advance_run
from .project import (
    IntakeError,
    exec_dir,
    finish_run,
    init_project,
    intake,
    list_executions,
    list_runs,
    load_package,
    load_run,
    new_run,
    refresh_index,
    save_execution,
    save_run,
    start_run,
)
from .acceptance import init_acceptance, record_leaf
from .budget import check_budget
from .deviations import (
    apply_deviation,
    override_deviation,
    publish_deviation,
    raise_deviation,
)
from .failures import (
    classify_failure,
    list_reflux,
    reflux_status_of,
    review_failure,
    update_reflux_entry,
)
from .project import load_acceptance
from .reconcile import check_reconciliation, export_card, fill_row
from .render import render_report
from .schema import PKG_STATES, RUN_STATES, validate_package
from .stale import compute_stale_report, write_stale_reports
from .util import load_structured, today


def _fail(msg: str) -> int:
    print(f"错误：{msg}", file=sys.stderr)
    return 1


def _load_spec(path_str: str | None) -> dict | None:
    if not path_str:
        return None
    p = Path(path_str)
    if not p.exists():
        raise FileNotFoundError(f"规格文件不存在：{p}")
    return load_structured(p)


def cmd_init(args) -> int:
    root = Path(args.dir)
    try:
        init_project(root, args.direction)
    except FileExistsError as e:
        return _fail(str(e))
    print(f"项目已建：{root}（方向：{args.direction}）")
    return 0


def cmd_intake(args) -> int:
    root = Path(args.project)
    export_dir = Path(args.from_export)
    if not export_dir.exists():
        return _fail(f"交接目录不存在：{export_dir}")
    try:
        execution, gaps = intake(root, export_dir)
    except IntakeError as e:
        print("承接无法进行（连设计都识别不了）：")
        for g in e.gaps:
            print(f"  - {g}")
        return 1
    exec_id = execution["exec_id"]
    if gaps:
        print(f"执行包已建：{exec_id}（status=intake）——承接打回清单"
              f"（{len(gaps)} 项，对不齐不开跑）：")
        for g in gaps:
            print(f"  - {g}")
        print("缺口已落 intake_report 与 experiment-stage/intake_log.md；"
              "回 Design 解决后重新 intake（新批次，不覆盖本包）。")
        return 1
    n_runs = len(execution.get("brief_runs") or [])
    print(f"执行包已建：{exec_id}（status=intake，承接齐全，"
          f"brief 条目 {n_runs} 个、run 已按条目各建一次尝试、"
          "对账占位表已生成）")
    return 0


def cmd_run_new(args) -> int:
    root = Path(args.project)
    try:
        spec = _load_spec(args.spec)
        run = new_run(root, args.exec_id, args.design_run_id,
                      spec=spec, retry_of=args.retry_of)
    except (FileNotFoundError, ValueError) as e:
        return _fail(str(e))
    extra = f"，血缘接 {args.retry_of}" if args.retry_of else ""
    print(f"已建 run：{run['run_id']}（条目 {args.design_run_id} "
          f"第 {run['attempt']} 次尝试{extra}，status=planned；"
          "身份成分在 run-start 时定型冻结）")
    return 0


def cmd_run_start(args) -> int:
    root = Path(args.project)
    try:
        spec = _load_spec(args.spec)
        run = start_run(root, args.exec_id, args.run_id, spec=spec, by=args.by)
    except FileNotFoundError as e:
        return _fail(str(e))
    except GateError as e:
        print(f"开跑被拦：{args.run_id}（{len(e.errors)} 条）：")
        for err in e.errors:
            print(f"  - {err}")
        return 1
    ident = run["identity"]
    print(f"已开跑：{args.run_id}（identity_hash={ident['identity_hash'][:16]}…，"
          f"params_hash={ident['params_hash'][:16]}…，出生证明已冻结）")
    return 0


def cmd_run_finish(args) -> int:
    root = Path(args.project)
    try:
        run = finish_run(
            root, args.exec_id, args.run_id,
            exit_status=args.exit_status,
            metrics_file=Path(args.metrics_file) if args.metrics_file else None,
            salvage_files=tuple(Path(p) for p in args.salvage or ()),
            salvage_note=args.salvage_note or "",
            no_salvage=args.no_salvage,
            failure_ref=args.failure_ref,
            mark_deviated=args.mark_deviated,
            wall_clock_s=args.wall_clock_s, gpu_hours=args.gpu_hours,
            api_cost=args.api_cost, by=args.by)
    except (FileNotFoundError, ValueError) as e:
        return _fail(str(e))
    except GateError as e:
        print(f"终止被拦：{args.run_id}（{len(e.errors)} 条）：")
        for err in e.errors:
            print(f"  - {err}")
        return 1
    print(f"已终止：{args.run_id} → {run['status']}"
          f"（exit_status={args.exit_status}）")
    ver = (run.get("conclusion") or {}).get("intervention_verification") or {}
    results = ver.get("results") or []
    if results:
        print(f"  干预机械核验（EXP-D03）：总判 {ver.get('verdict')}"
              f"（{len(results)} 条核查点，实际值由工具从产物机械读取）")
        for r in results:
            if r.get("status") != "pass":
                print(f"  🔴 {r.get('point')}：{r.get('status')}——"
                      f"{r.get('detail')}")
            else:
                print(f"  ✓ {r.get('point')}：pass（{r.get('detail')}）")
        if run["status"] == "deviated" and args.exit_status == "completed":
            print("  核验不符已自动标 deviated 候选：不许静默通过，"
                  "按偏离规程处置（登记/替代）后再对账")
    return 0


def cmd_event(args) -> int:
    root = Path(args.project)
    payload = {}
    if args.payload:
        try:
            payload = json.loads(args.payload)
        except json.JSONDecodeError as e:
            return _fail(f"--payload 不是合法 JSON：{e}")
        if not isinstance(payload, dict):
            return _fail("--payload 须为 JSON 对象")
    try:
        ev = append_event(exec_dir(root, args.exec_id), args.type,
                          source=args.source, run_id=args.run_id,
                          payload=payload)
    except (FileNotFoundError, ValueError) as e:
        return _fail(str(e))
    print(f"事件已追加：{ev['event_id']}（{args.type}）")
    return 0


def cmd_validate(args) -> int:
    root = Path(args.project)
    try:
        pkg = load_package(root, args.exec_id)
    except FileNotFoundError as e:
        return _fail(str(e))
    errors = validate_package(pkg)
    if errors:
        print(f"{args.exec_id} 不合法（{len(errors)} 条）：")
        for e in errors:
            print(f"  - {e}")
        return 1
    print(f"{args.exec_id} 合法（status={pkg['execution'].get('status')}，"
          f"runs={len(pkg['runs'])}，events={len(pkg['events'])}）")
    return 0


def cmd_advance(args) -> int:
    root = Path(args.project)
    if args.run:
        try:
            run = load_run(root, args.exec_id, args.run)
            advance_run(run, args.to, by=args.by, date=today(),
                        note=args.note or "")
        except FileNotFoundError as e:
            return _fail(str(e))
        except GateError as e:
            print(f"推进被拦：{args.run} → {args.to}（{len(e.errors)} 条）：")
            for err in e.errors:
                print(f"  - {err}")
            return 1
        save_run(root, args.exec_id, run)
        print(f"已推进：run {args.run} → {args.to}")
        return 0
    try:
        pkg = load_package(root, args.exec_id)
        advance_package(pkg, args.to, by=args.by, date=today(),
                        note=args.note or "",
                        block_reason=args.reason or "",
                        unblock_condition=args.unblock or "")
    except FileNotFoundError as e:
        return _fail(str(e))
    except GateError as e:
        print(f"推进被拦：{args.exec_id} → {args.to}（{len(e.errors)} 条）：")
        for err in e.errors:
            print(f"  - {err}")
        return 1
    save_execution(root, pkg["execution"])
    refresh_index(root)
    print(f"已推进：{args.exec_id} → {args.to}")
    return 0


def cmd_list(args) -> int:
    root = Path(args.project)
    if args.exec_id:
        try:
            runs = list_runs(root, args.exec_id)
        except FileNotFoundError as e:
            return _fail(str(e))
        if not runs:
            print(f"{args.exec_id} 下暂无 run")
            return 0
        for r in runs:
            es = (r.get("conclusion") or {}).get("exit_status") or "—"
            print(f"{r['run_id']}\t{r.get('status')}\t条目 {r.get('design_run_id')}"
                  f"\t尝试 {r.get('attempt')}\texit {es}")
        return 0
    executions = list_executions(root)
    if not executions:
        print("暂无执行包（先 intake 一份 Design 交接四件套）")
        return 0
    for e in executions:
        dref = e.get("design_ref") or {}
        print(f"{e['exec_id']}\t{e.get('status')}\t承接 {dref.get('design_id')}")
    return 0


def cmd_render(args) -> int:
    root = Path(args.project)
    try:
        summary = render_report(root, args.exec_id)
    except FileNotFoundError as e:
        return _fail(str(e))
    print(f"报告已刷新：{summary['report_path']}"
          f"（runs={summary['runs']}，events={summary['events']}）")
    return 0


def _load_json_arg(value: str) -> dict:
    """JSON 参数：给文件路径则读文件，给字面量则直接解析。"""
    p = Path(value)
    if p.exists():
        data = load_structured(p)
    else:
        try:
            data = json.loads(value)
        except json.JSONDecodeError as e:
            raise ValueError(f"JSON 参数既不是文件也不是合法 JSON：{e}") from e
    if not isinstance(data, dict):
        raise ValueError("JSON 参数须为对象")
    return data


def _gate_print(title: str, errors: list[str]) -> int:
    print(f"{title}（{len(errors)} 条）：")
    for e in errors:
        print(f"  - {e}")
    return 1


# ---------- 二期：acceptance ----------

def cmd_acceptance_init(args) -> int:
    root = Path(args.project)
    try:
        acc = init_acceptance(
            root, args.exec_id,
            targets=tuple(x.strip() for x in (args.runs or "").split(",") if x.strip()),
            threshold=args.threshold, tolerance_pct=args.tolerance_pct,
            by=args.by)
    except FileNotFoundError as e:
        return _fail(str(e))
    except GateError as e:
        return _gate_print("验收表生成被拦", e.errors)
    except ValueError as e:
        return _fail(str(e))
    print(f"验收表已生成并冻结：{args.exec_id}"
          f"（对象 {'、'.join(acc['targets'])}，叶子 {len(acc['leaves'])} 片，"
          f"阈值 {acc['threshold']}；baseline_acceptance.md 已渲染）")
    return 0


def cmd_acceptance_record(args) -> int:
    root = Path(args.project)
    try:
        acc = record_leaf(
            root, args.exec_id, args.leaf_id, verdict=args.verdict,
            evidence_run=args.evidence_run,
            evidence_files=tuple(Path(p) for p in args.evidence or ()),
            observed_value=args.observed, expected_value=args.expected,
            reported_variance=args.variance, note=args.note or "", by=args.by)
    except (FileNotFoundError, ValueError) as e:
        return _fail(str(e))
    judged = sum(1 for x in acc["leaves"] if x.get("verdict"))
    print(f"已登记：{args.leaf_id} = {args.verdict}"
          f"（叶子 {judged}/{len(acc['leaves'])} 已判，"
          f"包级验收结论 {acc['verdict']}）")
    return 0


def cmd_acceptance_show(args) -> int:
    root = Path(args.project)
    acc = load_acceptance(root, args.exec_id)
    if acc is None:
        print(f"{args.exec_id} 尚无验收表（acceptance init 未跑）")
        return 0
    print(f"验收结论：{acc.get('verdict')}（阈值 {acc.get('threshold')}，"
          f"对象 {'、'.join(acc.get('targets') or [])}）")
    for leaf in acc.get("leaves") or []:
        print(f"  {leaf.get('leaf_id')}\t{leaf.get('verdict') or '（未判）'}"
              f"\t证据 {leaf.get('evidence_run') or '—'}")
    return 0


# ---------- 二期：deviation ----------

def cmd_deviation_raise(args) -> int:
    root = Path(args.project)
    try:
        entry = raise_deviation(
            root, args.exec_id, run_id=args.run_id, context=args.context or "",
            type=args.type, dimension=args.dimension,
            description=args.description, claimed=args.claimed or "",
            actual=args.actual or "",
            declared=tuple(x.strip() for x in (args.declared or "").split(",")
                           if x.strip()),
            disposition=args.disposition, declaration=args.declaration or "",
            decided_by=args.decided_by or "", by=args.by)
    except (FileNotFoundError, ValueError) as e:
        return _fail(str(e))
    print(f"偏离已登记：{entry['deviation_id']}（type={entry['type']}，"
          f"处置 {entry['disposition']}）")
    print(f"  人工估计影响集：{entry['affected_runs_declared'] or '（未给）'}")
    print(f"  工具闭包影响集：{entry['affected_runs_closure'] or '（空）'}"
          "（作废靠算不靠点名；下一步 deviation publish 公示）")
    return 0


def cmd_deviation_publish(args) -> int:
    root = Path(args.project)
    try:
        entry = publish_deviation(root, args.exec_id, args.deviation_id, by=args.by)
    except FileNotFoundError as e:
        return _fail(str(e))
    except GateError as e:
        return _gate_print("公示被拦", e.errors)
    except ValueError as e:
        return _fail(str(e))
    print(f"生效清单已公示：{args.deviation_id} → {entry['notice']}"
          f"（闭包 {len(entry['closure'])} 条 run）")
    return 0


def cmd_deviation_apply(args) -> int:
    root = Path(args.project)
    try:
        entry = apply_deviation(root, args.exec_id, args.deviation_id, by=args.by)
    except FileNotFoundError as e:
        return _fail(str(e))
    except GateError as e:
        return _gate_print("生效被拦", e.errors)
    except ValueError as e:
        return _fail(str(e))
    print(f"偏离已生效：{args.deviation_id}"
          f"（作废 {entry.get('invalidated') or []}，"
          f"下游待处置 {entry.get('downstream_planned') or []}，"
          f"豁免 {entry.get('exempted') or []}）")
    return 0


def cmd_deviation_override(args) -> int:
    root = Path(args.project)
    try:
        entry = override_deviation(
            root, args.exec_id, args.deviation_id,
            exempted_runs=tuple(x.strip() for x in args.runs.split(",") if x.strip()),
            by=args.by, reason=args.reason)
    except FileNotFoundError as e:
        return _fail(str(e))
    except GateError as e:
        return _gate_print("覆写被拦", e.errors)
    except ValueError as e:
        return _fail(str(e))
    print(f"覆写已登记：{args.deviation_id} 豁免 "
          f"{'、'.join(entry['exempted_runs'])}（覆写者 {entry['by']}；"
          "报告将标红提示溯源代价）")
    return 0


def cmd_deviation_list(args) -> int:
    root = Path(args.project)
    try:
        pkg = load_package(root, args.exec_id)
    except FileNotFoundError as e:
        return _fail(str(e))
    devs = pkg.get("deviations") or []
    if not devs:
        print(f"{args.exec_id} 无偏离登记")
        return 0
    for d in devs:
        state = "已生效" if d.get("applied") else (
            "已公示" if d.get("published") else "已登记")
        print(f"{d.get('deviation_id')}\t{state}\t{d.get('type')}\t"
              f"{d.get('disposition')}\t闭包 {len(d.get('closure_current') or [])}"
              f"\t{d.get('description')}")
    return 0


# ---------- 二期：failure / reflux ----------

def cmd_failure_classify(args) -> int:
    root = Path(args.project)
    try:
        rec = classify_failure(
            root, args.exec_id, run_id=args.run, mast_code=args.mast,
            failure_class=args.failure_class, root_cause=args.root_cause or "",
            boundary_conditions=args.boundary or "",
            retry_guidance=args.retry_guidance or "",
            diagnosis=args.diagnosis or "", attempt_kind=args.attempt_kind,
            idea_bound=args.idea_bound, reviewer=args.reviewer or "",
            review_agrees=args.review_agrees, by=args.by)
    except (FileNotFoundError, ValueError) as e:
        return _fail(str(e))
    except GateError as e:
        return _gate_print("分类被拦", e.errors)
    print(f"失败已分类：{rec['failure_id']}（{rec['mast_code']} "
          f"{rec['mast_name']} / {rec['failure_class']}），"
          f"回流条目已自动生成 → {rec['reflux_target']}（pending）")
    if rec["budget_exceeded"]:
        print("🔴 报警：同签名失败已超预算（2 补丁 + 2 重写上限）——"
              "停下报告「计划或环境错了」，不许换个姿势继续烧")
        return 1
    return 0


def cmd_failure_review(args) -> int:
    root = Path(args.project)
    try:
        review_failure(root, args.exec_id, args.failure_id,
                       reviewer=args.reviewer, agrees=args.agrees,
                       note=args.note or "")
    except (FileNotFoundError, ValueError) as e:
        return _fail(str(e))
    print(f"抽验已落痕：{args.failure_id}（抽验人 {args.reviewer}，"
          f"{'同意' if args.agrees else '不同意'}自动初筛）")
    return 0


def cmd_reflux_list(args) -> int:
    root = Path(args.project)
    try:
        reflux = list_reflux(root, args.exec_id)
    except FileNotFoundError as e:
        return _fail(str(e))
    shown = False
    for name, entries in (("retry_queue", reflux["retry_queue"]),
                          ("design_inbox", reflux["design_inbox"])):
        mains = [e for e in entries if e.get("kind") != "status_update"]
        for e in mains:
            shown = True
            print(f"{e.get('entry_id')}\t{name}\t{e.get('kind')}\t"
                  f"{reflux_status_of(entries, e.get('entry_id'))}\t"
                  f"源 {e.get('source')}:{e.get('source_id')}")
    for d in reflux["idea_dossiers"]:
        shown = True
        print(f"dossier\t{d}（reflux/idea_dossiers/）")
    if not shown:
        print(f"{args.exec_id} 无回流条目")
    return 0


def cmd_reflux_update(args) -> int:
    root = Path(args.project)
    try:
        update_reflux_entry(root, args.exec_id, args.entry_id,
                            status=args.status, by=args.by)
    except (FileNotFoundError, ValueError) as e:
        return _fail(str(e))
    print(f"回流条目已更新：{args.entry_id} → {args.status}")
    return 0


# ---------- 二期：reconcile / budget / export-card ----------

def cmd_reconcile_fill(args) -> int:
    root = Path(args.project)
    try:
        row = fill_row(
            root, args.exec_id, args.row_id,
            readout=_load_json_arg(args.readout),
            random_sources=_load_json_arg(args.random_sources),
            layers=_load_json_arg(args.layers),
            evidence=tuple(args.evidence or ()), by=args.by)
    except FileNotFoundError as e:
        return _fail(str(e))
    except GateError as e:
        return _gate_print("回填被拦", e.errors)
    except ValueError as e:
        return _fail(str(e))
    warns = (row.get("random_sources") or {}).get("bias_warnings") or []
    print(f"对账行已回填：{args.row_id} → filled")
    for w in warns:
        print(f"  ⚠️ {w}")
    return 0


def cmd_reconcile_check(args) -> int:
    root = Path(args.project)
    try:
        problems = check_reconciliation(root, args.exec_id)
    except FileNotFoundError as e:
        return _fail(str(e))
    if problems:
        return _gate_print(f"{args.exec_id} 对账未清零", problems)
    print(f"{args.exec_id} 对账逐行清零（无缺行 / 未填 / 作废未替代）")
    return 0


def cmd_budget_check(args) -> int:
    root = Path(args.project)
    try:
        result = check_budget(root, args.exec_id, by=args.by)
    except FileNotFoundError as e:
        return _fail(str(e))
    if not result["lines"]:
        print("无熔断线（Design 交接未声明 circuit_breakers）：无从设闸")
        return 0
    if result["tripped"]:
        for t in result["tripped"]:
            print(f"🔴 熔断触发：{t['metric']} 已耗 {t['spent']} ≥ 线 "
                  f"{t['threshold']}（单 run 越线：{t['offending_runs'] or '无'}）")
        print(f"killed_budget 候选（仍在 running）："
              f"{result['candidates'] or '（无）'}——只许停不许改，"
              "上调熔断线回 Design 走 amendment")
        return 1
    print("预算未触线：" + "、".join(
        f"{l['metric']} 线 {l['threshold']}" for l in result["lines"]))
    return 0


def cmd_export_card(args) -> int:
    root = Path(args.project)
    try:
        card = export_card(root, args.exec_id,
                           out=Path(args.out) if args.out else None)
    except FileNotFoundError as e:
        return _fail(str(e))
    out = args.out or str(exec_dir(root, args.exec_id) / "execution_card.json")
    print(f"execution_card.json 已导出：{out}"
          f"（runs {len(card['runs'])}，对账行 "
          f"{len(card['reconciliation']['rows'])}）")
    return 0


def cmd_stale(args) -> int:
    root = Path(args.project)
    spec = None
    if args.spec:
        try:
            spec = _load_spec(args.spec)
        except (FileNotFoundError, ValueError) as e:
            return _fail(str(e))
    try:
        report = compute_stale_report(
            root, args.exec_id, current_spec=spec,
            spec_source=str(args.spec) if args.spec else "")
    except FileNotFoundError as e:
        return _fail(str(e))
    out_json, out_md = write_stale_reports(
        root, args.exec_id, report,
        out_json=Path(args.out_json) if args.out_json else None,
        out_md=Path(args.out_md) if args.out_md else None)
    s = report["summary"]
    print(f"stale 预检：{args.exec_id}（current {s['current']} · "
          f"stale {s['stale']} · voided {s['voided']}）")
    print(f"  报告：{out_json}（机读）/ {out_md}（人读）；只读视图，"
          "未改任何包状态")
    if report["uncompared_dimensions"]:
        print(f"  未比对维度：{'、'.join(report['uncompared_dimensions'])}"
              "（现行参照未覆盖，不下结论）")
    for e in report["runs"]:
        if e["state"] == "stale":
            dims = "、".join(d["dimension"] for d in e["stale_dimensions"])
            print(f"  🟠 {e['run_id']} stale（触发维 {dims}）：{e['advice']}")
        elif e["state"] == "voided":
            print(f"  ⚫ {e['run_id']} voided（作废于 "
                  f"{'、'.join(e['voided_by'])}，既成事实）")
    return 1 if s["stale"] else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="light-experiment",
        description="light-experiment：按冻结设计书执行、逐 run 留痕、逐行对账")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init", help="建项目骨架")
    p.add_argument("dir")
    p.add_argument("--direction", required=True)
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("intake", help="消费 Design 交接四件套建执行包")
    p.add_argument("project")
    p.add_argument("--from-export", required=True, dest="from_export")
    p.set_defaults(func=cmd_intake)

    p = sub.add_parser("run-new", help="为 brief 条目新建一次尝试")
    p.add_argument("project")
    p.add_argument("exec_id")
    p.add_argument("design_run_id")
    p.add_argument("--spec", help="身份成分规格文件（JSON/YAML）")
    p.add_argument("--retry-of", dest="retry_of",
                   help="接哪条已终止的旧尝试（新 run + 血缘）")
    p.set_defaults(func=cmd_run_new)

    p = sub.add_parser("run-start", help="开跑（身份下限过后冻结哈希与出生证明）")
    p.add_argument("project")
    p.add_argument("exec_id")
    p.add_argument("run_id")
    p.add_argument("--spec", help="身份成分规格文件（JSON/YAML）")
    p.add_argument("--by", default="")
    p.set_defaults(func=cmd_run_start)

    p = sub.add_parser("run-finish", help="终止 run 并登记产物")
    p.add_argument("project")
    p.add_argument("exec_id")
    p.add_argument("run_id")
    p.add_argument("--exit-status", required=True, dest="exit_status")
    p.add_argument("--metrics-file", dest="metrics_file")
    p.add_argument("--salvage", action="append",
                   help="抢救产物文件（可多次给）")
    p.add_argument("--salvage-note", dest="salvage_note")
    p.add_argument("--no-salvage", action="store_true", dest="no_salvage",
                   help="显式声明无可抢救产物")
    p.add_argument("--failure-ref", dest="failure_ref")
    p.add_argument("--mark-deviated", action="store_true", dest="mark_deviated",
                   help="终止后落 deviated（结果待偏离处置）")
    p.add_argument("--wall-clock-s", type=float, default=0, dest="wall_clock_s")
    p.add_argument("--gpu-hours", type=float, default=0, dest="gpu_hours")
    p.add_argument("--api-cost", type=float, default=0, dest="api_cost")
    p.add_argument("--by", default="")
    p.set_defaults(func=cmd_run_finish)

    p = sub.add_parser("event", help="追加一条轨迹事件")
    p.add_argument("project")
    p.add_argument("exec_id")
    p.add_argument("--type", required=True)
    p.add_argument("--run-id", dest="run_id")
    p.add_argument("--source", default="tool")
    p.add_argument("--payload", help="JSON 对象")
    p.set_defaults(func=cmd_event)

    p = sub.add_parser("validate", help="校验执行包")
    p.add_argument("project")
    p.add_argument("exec_id")
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("advance", help="状态机推进（包级；--run 时推进单个 run）")
    p.add_argument("project")
    p.add_argument("exec_id")
    p.add_argument("--to", required=True, choices=PKG_STATES + RUN_STATES)
    p.add_argument("--run", help="给 run_id 时推进该 run（目标态取 run 级状态）")
    p.add_argument("--by", default="")
    p.add_argument("--note", default="")
    p.add_argument("--reason", default="", help="转 blocked 的阻塞原因")
    p.add_argument("--unblock", default="", help="转 blocked 的解阻条件")
    p.set_defaults(func=cmd_advance)

    p = sub.add_parser("list", help="列执行包 / 某包的 runs")
    p.add_argument("project")
    p.add_argument("exec_id", nargs="?")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("render", help="渲染 EXECUTION_REPORT.md")
    p.add_argument("project")
    p.add_argument("exec_id")
    p.set_defaults(func=cmd_render)

    # ---- 二期子命令组 ----
    p = sub.add_parser("acceptance", help="基线复现验收（E1）")
    asub = p.add_subparsers(dest="acceptance_command", required=True)
    q = asub.add_parser("init", help="从基线条目生成并冻结验收表")
    q.add_argument("project"); q.add_argument("exec_id")
    q.add_argument("--runs", help="验收对象条目（逗号分隔；缺省取 role=baseline 条目）")
    q.add_argument("--threshold", type=float, default=1.0,
                   help="加权通过分阈值（brief 声明优先，默认 1.0）")
    q.add_argument("--tolerance-pct", type=float, default=2.0, dest="tolerance_pct",
                   help="结果层默认容差%%（默认 2.0，草案 §5）")
    q.add_argument("--by", default="")
    q.set_defaults(func=cmd_acceptance_init)
    q = asub.add_parser("record", help="逐叶登记判定（证据只认冷启动重跑）")
    q.add_argument("project"); q.add_argument("exec_id"); q.add_argument("leaf_id")
    q.add_argument("--verdict", required=True, choices=("pass", "fail"))
    q.add_argument("--evidence-run", required=True, dest="evidence_run",
                   help="冷启动重跑 run 的 id（验收证据）")
    q.add_argument("--evidence", action="append", help="证据文件（可多次给，登记指纹）")
    q.add_argument("--observed", type=float, help="结果层：实际读数")
    q.add_argument("--expected", type=float, help="结果层：登记预期值")
    q.add_argument("--variance", type=float, help="结果层：报告方差（绝对界）")
    q.add_argument("--note", default="")
    q.add_argument("--by", default="")
    q.set_defaults(func=cmd_acceptance_record)
    q = asub.add_parser("show", help="看验收结论与逐叶状态")
    q.add_argument("project"); q.add_argument("exec_id")
    q.set_defaults(func=cmd_acceptance_show)

    p = sub.add_parser("deviation", help="偏离登记与闭包作废（E4）")
    dsub = p.add_subparsers(dest="deviation_command", required=True)
    q = dsub.add_parser("raise", help="登记偏离（工具自动算闭包）")
    q.add_argument("project"); q.add_argument("exec_id")
    q.add_argument("--run-id", dest="run_id", help="发现上下文 run")
    q.add_argument("--context", default="")
    q.add_argument("--type", required=True,
                   choices=("config", "code", "data", "environment",
                            "readout", "off_plan"))
    q.add_argument("--dimension",
                   choices=("code", "params", "input", "env", "data", "config"),
                   help="出生证明逐维比对的触发维")
    q.add_argument("--description", required=True)
    q.add_argument("--claimed", default="")
    q.add_argument("--actual", default="")
    q.add_argument("--declared", default="", help="人工估计影响集（逗号分隔 run_id）")
    q.add_argument("--disposition", required=True,
                   choices=("continue_with_note", "void_and_rerun",
                            "stop_and_return_design", "accept_with_declaration"))
    q.add_argument("--declaration", default="", help="接受并声明时的声明文本")
    q.add_argument("--decided-by", default="", dest="decided_by")
    q.add_argument("--by", default="")
    q.set_defaults(func=cmd_deviation_raise)
    q = dsub.add_parser("publish", help="生成生效清单并公示")
    q.add_argument("project"); q.add_argument("exec_id"); q.add_argument("deviation_id")
    q.add_argument("--by", default="")
    q.set_defaults(func=cmd_deviation_publish)
    q = dsub.add_parser("apply", help="按公示闭包生效（作废只追加）")
    q.add_argument("project"); q.add_argument("exec_id"); q.add_argument("deviation_id")
    q.add_argument("--by", default="")
    q.set_defaults(func=cmd_deviation_apply)
    q = dsub.add_parser("override", help="显式覆写：豁免闭包内 run（须留名留理由）")
    q.add_argument("project"); q.add_argument("exec_id"); q.add_argument("deviation_id")
    q.add_argument("--runs", required=True, help="豁免的 run_id（逗号分隔）")
    q.add_argument("--by", required=True, help="覆写者")
    q.add_argument("--reason", required=True, help="覆写理由")
    q.set_defaults(func=cmd_deviation_override)
    q = dsub.add_parser("list", help="列偏离登记")
    q.add_argument("project"); q.add_argument("exec_id")
    q.set_defaults(func=cmd_deviation_list)

    p = sub.add_parser("failure", help="失败双层分类（E5）")
    fsub = p.add_subparsers(dest="failure_command", required=True)
    q = fsub.add_parser("classify", help="落 MAST × IVE 分类并自动回流")
    q.add_argument("project"); q.add_argument("exec_id")
    q.add_argument("--run", required=True, help="失败 run 的 id")
    q.add_argument("--mast", required=True, help="MAST 转译码（如 FM-1.3）")
    q.add_argument("--class", required=True, dest="failure_class",
                   choices=("implementation", "fundamental"))
    q.add_argument("--root-cause", default="", dest="root_cause")
    q.add_argument("--boundary", default="", help="fundamental 的边界条件")
    q.add_argument("--retry-guidance", default="", dest="retry_guidance",
                   help="implementation 的重试指引")
    q.add_argument("--diagnosis", default="")
    q.add_argument("--attempt-kind", dest="attempt_kind",
                   choices=("patch", "rewrite"),
                   help="本失败属补丁尝试还是干净重写（签名预算计数）")
    q.add_argument("--idea-bound", action="store_true", dest="idea_bound",
                   help="根因指向想法本体：另附 idea dossier 草稿")
    q.add_argument("--reviewer", default="", help="同步抽验人")
    q.add_argument("--review-agrees", action=argparse.BooleanOptionalAction,
                   default=None, dest="review_agrees")
    q.add_argument("--by", default="")
    q.set_defaults(func=cmd_failure_classify)
    q = fsub.add_parser("review", help="人工抽验落痕")
    q.add_argument("project"); q.add_argument("exec_id"); q.add_argument("failure_id")
    q.add_argument("--reviewer", required=True)
    q.add_argument("--agrees", action=argparse.BooleanOptionalAction, default=True)
    q.add_argument("--note", default="")
    q.set_defaults(func=cmd_failure_review)

    p = sub.add_parser("reflux", help="回流条目跟踪")
    rsub = p.add_subparsers(dest="reflux_command", required=True)
    q = rsub.add_parser("list", help="列回流条目与状态")
    q.add_argument("project"); q.add_argument("exec_id")
    q.set_defaults(func=cmd_reflux_list)
    q = rsub.add_parser("update", help="更新回流条目状态")
    q.add_argument("project"); q.add_argument("exec_id"); q.add_argument("entry_id")
    q.add_argument("--status", required=True,
                   choices=("pending", "sent", "resolved"))
    q.add_argument("--by", default="")
    q.set_defaults(func=cmd_reflux_update)

    p = sub.add_parser("reconcile", help="对账实质化（E6）")
    csub = p.add_subparsers(dest="reconcile_command", required=True)
    q = csub.add_parser("fill", help="逐行回填事实层（只收分布不收单点）")
    q.add_argument("project"); q.add_argument("exec_id"); q.add_argument("row_id")
    q.add_argument("--readout", required=True,
                   help="分布摘要 JSON（文件路径或字面量）{mean, spread, n, replication_level}")
    q.add_argument("--random-sources", required=True, dest="random_sources",
                   help="随机源清单 JSON {rerandomized: [...], frozen: [...]}")
    q.add_argument("--layers", required=True,
                   help="三层事实判定 JSON {implementation, execution, result_fact{verdict, reason}}")
    q.add_argument("--evidence", action="append", help="证据指针（可多次给）")
    q.add_argument("--by", default="")
    q.set_defaults(func=cmd_reconcile_fill)
    q = csub.add_parser("check", help="逐行清零检查（缺行/未填/作废未替代点名）")
    q.add_argument("project"); q.add_argument("exec_id")
    q.set_defaults(func=cmd_reconcile_check)

    p = sub.add_parser("budget", help="预算闸（E2）：只许停不许改，无放宽命令")
    bsub = p.add_subparsers(dest="budget_command", required=True)
    q = bsub.add_parser("check", help="对照 Design 熔断线检查 run 账与包总账")
    q.add_argument("project"); q.add_argument("exec_id")
    q.add_argument("--by", default="")
    q.set_defaults(func=cmd_budget_check)

    p = sub.add_parser("export-card", help="导出 execution_card.json（给 Analysis）")
    p.add_argument("project")
    p.add_argument("exec_id")
    p.add_argument("--out", help="输出路径（默认包目录内 execution_card.json）")
    p.set_defaults(func=cmd_export_card)

    p = sub.add_parser("stale", help="事前 stale 清单（EXP-D02，只读三态视图）")
    p.add_argument("project")
    p.add_argument("exec_id")
    p.add_argument("--spec", help="现行状态声明文件（JSON/YAML）：按条目键 "
                                  "{design_run_id: spec} 或全包一份 spec；"
                                  "逐维与出生证明比对")
    p.add_argument("--out-json", dest="out_json",
                   help="机读报告路径（默认包目录内 stale_report.json）")
    p.add_argument("--out-md", dest="out_md",
                   help="人读报告路径（默认包目录内 STALE_REPORT.md）")
    p.set_defaults(func=cmd_stale)

    args = parser.parse_args(argv)
    return args.func(args)
