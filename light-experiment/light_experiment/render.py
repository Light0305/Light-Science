"""EXECUTION_REPORT.md 渲染（摘要视图）。

轨迹粒度口径（拍板 ⑦）：全量事件落盘（events.jsonl 是本体）+ 摘要
视图双份——本报告是只读投影：状态分布、退出状态分布、预算总账、
事件按类型计数与最近事件摘录。只报成功数视为报告不合格（约束 4/11）：
失败与偏离必须与成功同版面出现。
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from .gates import BUDGET_KEYS
from .project import load_package
from .util import today

RECENT_EVENTS = 10


def render_report(root: Path, exec_id: str, *, date: str | None = None) -> dict:
    """生成/刷新 executions/<exec_id>/EXECUTION_REPORT.md，返回汇总 dict。"""
    date = date or today()
    pkg = load_package(root, exec_id)
    execution = pkg["execution"]
    runs = list(pkg["runs"].values())
    events = pkg["events"]
    recon = pkg["reconciliation"]
    dref = execution.get("design_ref") or {}

    status_counts = Counter(r.get("status") for r in runs)
    exit_counts = Counter((r.get("conclusion") or {}).get("exit_status")
                          for r in runs if (r.get("conclusion") or {}).get("exit_status"))
    type_counts = Counter(e.get("type") for e in events)
    ledger = execution.get("budget_ledger") or {}
    spent = ledger.get("spent") or {}
    limits = ledger.get("limits") or {}

    L: list[str] = []
    L.append(f"# EXECUTION_REPORT — {exec_id}")
    L.append("")
    L.append(f"> 渲染于 {date}（摘要视图，权威源为 execution.yaml / run.yaml / "
             "events.jsonl）：承接设计 `{(dref.get('design_id'))}`，"
             f"冻结哈希 `{(dref.get('content_hash') or '')[:16]}…`，"
             f"执行包状态 **{execution.get('status')}**。")
    L.append("")
    L.append("## 状态分布")
    L.append("")
    L.append(f"- run 总数：{len(runs)}")
    for s, n in sorted(status_counts.items()):
        L.append(f"- {s}：{n}")
    L.append("")
    L.append("## 退出状态分布（失败与成功同版面）")
    L.append("")
    if exit_counts:
        for s, n in sorted(exit_counts.items()):
            L.append(f"- {s}：{n}")
    else:
        L.append("（尚无 run 终止）")
    L.append("")
    L.append("## 预算总账")
    L.append("")
    L.append("| 维度 | 已耗 | 上限 |")
    L.append("|---|---|---|")
    for k in BUDGET_KEYS:
        lim = limits.get(k)
        L.append(f"| {k} | {spent.get(k, 0)} | {lim if lim is not None else '（未设）'} |")
    db = ledger.get("design_budget") or {}
    if db:
        L.append(f"- 设计侧预算声明：{db}")
    L.append("")
    L.append("## run 清单")
    L.append("")
    if runs:
        L.append("| run_id | 条目 | 尝试 | 状态 | exit_status | 身份哈希 |")
        L.append("|---|---|---|---|---|---|")
        for r in sorted(runs, key=lambda x: x["run_id"]):
            ih = (r.get("identity") or {}).get("identity_hash") or ""
            ih_cell = f"`{ih[:12]}…`" if ih else "—"
            es = (r.get("conclusion") or {}).get("exit_status") or "—"
            L.append(f"| {r['run_id']} | {r.get('design_run_id')} | {r.get('attempt')} "
                     f"| {r.get('status')} | {es} | {ih_cell} |")
    else:
        L.append("（暂无 run）")
    L.append("")
    # —— 二期版面：验收 / 对账 / 偏离 / 失败分布 / 熔断状态 ——
    acc = pkg.get("acceptance")
    L.append("## 基线复现验收（E1）")
    L.append("")
    if acc:
        leaves = acc.get("leaves") or []
        judged = sum(1 for x in leaves if x.get("verdict"))
        L.append(f"- 结论：**{acc.get('verdict')}**（叶子 {judged}/{len(leaves)} "
                 f"已判，阈值 {acc.get('threshold')}，对象 "
                 f"{'、'.join(acc.get('targets') or [])}）")
    else:
        L.append("- 未生成验收表（brief 无基线条目或尚未 acceptance init）")
    L.append("")
    L.append("## 对账（E6）")
    L.append("")
    if recon:
        rows = recon.get("rows") or []
        by_status = Counter(r.get("status") for r in rows)
        L.append(f"- 对账行：{len(rows)}（"
                 + "、".join(f"{s} {n}" for s, n in sorted(by_status.items()))
                 + "）")
        for r in rows:
            warns = (r.get("random_sources") or {}).get("bias_warnings") or []
            for w in warns:
                L.append(f"- ⚠️ 对账行 {r.get('registry_run_id')}：{w}")
    else:
        L.append("- 对账表未生成（承接未清零时不生成）")
    L.append("")
    L.append("## 偏离清单（E4）")
    L.append("")
    deviations = pkg.get("deviations") or []
    if deviations:
        for d in deviations:
            applied = d.get("applied") or {}
            state = ("已作废 " + "、".join(applied.get("invalidated") or [])
                     ) if applied else "未处置"
            L.append(f"- {d.get('deviation_id')}（{d.get('type')} / "
                     f"{d.get('disposition')}）：{d.get('description')} → {state}")
            for ov in d.get("overrides") or []:
                L.append(f"  - 🔴 **覆写警告**：{ov.get('by')} 豁免了 "
                         f"{'、'.join(ov.get('exempted_runs') or [])}"
                         f"（理由：{ov.get('reason')}）——被豁免 run 的结果"
                         "溯源链自此带人工担责标记，审计先查此处")
    else:
        L.append("（无偏离登记）")
    L.append("")
    L.append("## 失败分类分布（E5，只报成功数视为不合格）")
    L.append("")
    failures = pkg.get("failures") or []
    if failures:
        mast_counts = Counter(f.get("mast_code") for f in failures)
        class_counts = Counter(f.get("failure_class") for f in failures)
        L.append("- MAST 根因类：" + "、".join(
            f"{k} × {n}" for k, n in sorted(mast_counts.items())))
        L.append("- IVE 二分类：" + "、".join(
            f"{k} × {n}" for k, n in sorted(class_counts.items())))
        for f in failures:
            if f.get("budget_exceeded"):
                L.append(f"- 🔴 {f.get('failure_id')} 同签名失败预算已超限"
                         "（停下报告，不许继续烧）")
    else:
        L.append("（无失败分类记录）")
    L.append("")
    # —— 第四批版面：自动捕获 / 内容寻址池 / 无进展判定 ——
    L.append("## 自动捕获与产物池（第四批）")
    L.append("")
    captured = [r for r in runs
                if ((r.get("observation") or {}).get("capture") or {})
                .get("start")]
    pooled_entries = 0
    for r in runs:
        obs = r.get("observation") or {}
        pooled_entries += sum(
            1 for e in obs.get("artifacts") or []
            if isinstance(e, dict) and e.get("pool_ref"))
        mr = obs.get("metrics_ref")
        if isinstance(mr, dict) and mr.get("pool_ref"):
            pooled_entries += 1
    L.append(f"- 开跑捕获在位的 run：{len(captured)}/{len(runs)}"
             "（git 探针 / 环境指纹 / 执行者由工具实测落账，"
             "capture_hash 钉 run_started 事件锚；无捕获块的为旧包"
             "存档形态）")
    for r in sorted(captured, key=lambda x: x["run_id"]):
        cap = (r.get("observation") or {}).get("capture") or {}
        start = cap.get("start") or {}
        git = start.get("git") or {}
        git_desc = (f"commit {str(git.get('commit'))[:12]}…，"
                    f"dirty {git.get('dirty')}"
                    if git else
                    f"无（{start.get('git_unavailable_reason') or '—'}）")
        fin = cap.get("finish") or {}
        L.append(f"  - {r['run_id']}：git {git_desc}；声明输入实测 "
                 f"{len(start.get('inputs') or [])} 个；终止输出 "
                 f"{fin.get('outputs') or '（未终止）'}")
    from .capture import verify_pool
    pool = verify_pool(root / "executions" / exec_id)
    L.append(f"- 内容寻址池：对象 {pool['objects']} 个 / {pool['bytes']} "
             f"字节，带池引用的登记条 {pooled_entries} 条"
             f"（损坏 {len(pool['corrupt'])} 个；validate 逐条巡检"
             "池对象，artifact verify 给全池体检）")
    for c in pool["corrupt"]:
        L.append(f"  - 🔴 池对象损坏：{c['pool_ref']}——{c['reason']}")
    verdicts = [e for e in events if e.get("type") == "no_progress_verdict"]
    if verdicts:
        L.append(f"- 无进展判定（watchdog 巡检留痕）：{len(verdicts)} 条，"
                 f"涉及 run "
                 f"{'、'.join(sorted({e.get('run_id') or '' for e in verdicts}))}"
                 "（候选留痕，终止处置见 run 的 exit_status）")
    L.append("")
    tripped = (ledger.get("last_check") or {}).get("tripped") or []
    if tripped:
        L.append("## 熔断状态")
        L.append("")
        L.append(f"- 🔴 已触发熔断线：{'、'.join(tripped)}"
                 f"（候选 killed_budget："
                 f"{'、'.join((ledger.get('last_check') or {}).get('candidates') or [])}"
                 "；熔断只许停不许改，上调回 Design 走 amendment）")
        L.append("")
    L.append("## 事件摘要（全量见 events.jsonl）")
    L.append("")
    L.append(f"- 事件总数：{len(events)}")
    for t, n in sorted(type_counts.items()):
        L.append(f"- {t}：{n}")
    if events:
        L.append("")
        L.append(f"最近 {min(RECENT_EVENTS, len(events))} 条：")
        for e in events[-RECENT_EVENTS:]:
            L.append(f"- `{e.get('event_id')}` {e.get('ts')} {e.get('type')}"
                     f"（run: {e.get('run_id') or '—'}，来源: {e.get('source')}）")
    L.append("")
    gaps = (execution.get("intake_report") or {}).get("gaps") or []
    if gaps:
        L.append("## 承接缺口（未清零）")
        L.append("")
        for g in gaps:
            L.append(f"- {g}")
        L.append("")

    out = root / "executions" / exec_id / "EXECUTION_REPORT.md"
    out.write_text("\n".join(L), encoding="utf-8")
    return {
        "date": date,
        "exec_id": exec_id,
        "status": execution.get("status"),
        "runs": len(runs),
        "status_counts": dict(status_counts),
        "exit_counts": dict(exit_counts),
        "events": len(events),
        "report_path": str(out),
    }
