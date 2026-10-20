"""交接四件套导出（D7）+ 项目级 DESIGN_REPORT 刷新（二期）。

export：仅 frozen 设计可导出（冻结 = 评审通过 + 内容哈希落盘，是唯一
有权威版本的时点）。非 frozen 拒绝并逐条列缺口（还差哪道门）。

    exports/<design_id>/
    ├── experiment_brief.md    给 Experiment 的运行清单：runs 按依赖
    │                          拓扑序（对照先行）逐个列明角色/对照/变量
    │                          取值域/判读标准/预期登记，照单执行
    ├── design_card.json       设计书结构化全量（design.yaml 的 JSON 投影）
    ├── expected_registry.jsonl 预期登记表：每 run 一行，含 readout 三向
    │                          与主指标，供 Analysis 事后逐条对账
    └── reproducibility.md     复现字段清单：种子/环境/数据版本/调参对等

report：刷新 design-stage/DESIGN_REPORT.md（设计总数/状态分布/冻结数/
amendment 计数/打回记录摘要）。文件末尾的手工区（标记之间）保留不覆盖。
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from .project import list_designs, project_paths
from .schema import ALL_STATES, _nonempty_str, current_frozen_hash
from .util import today

MANUAL_START = "<!-- MANUAL:START -->"
MANUAL_END = "<!-- MANUAL:END -->"


class ExportError(Exception):
    """导出被拦。errors 为逐条缺口。"""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("；".join(errors))


# ---------- 拓扑序 ----------

def topo_order(runs: list[dict]) -> list[dict]:
    """按 depends_on 拓扑排序（依赖在前，同层保持声明顺序）。
    对照先行在 schema 层已保证处理组依赖其对照，此处给出执行序。
    依赖成环/引用未知 run 抛 ExportError（合法设计书不会出现）。"""
    by_id: dict[str, dict] = {}
    for r in runs:
        if isinstance(r, dict) and _nonempty_str(r.get("run_id")):
            by_id[r["run_id"]] = r
    order: list[dict] = []
    placed: set[str] = set()
    remaining = list(by_id.values())
    while remaining:
        progressed = False
        nxt: list[dict] = []
        for r in remaining:
            deps = [d for d in (r.get("depends_on") or []) if d in by_id]
            if all(d in placed for d in deps):
                order.append(r)
                placed.add(r["run_id"])
                progressed = True
            else:
                nxt.append(r)
        if not progressed:
            stuck = [r["run_id"] for r in nxt]
            raise ExportError([f"运行清单依赖无法拓扑排序（成环或依赖缺失）：{stuck}"])
        remaining = nxt
    return order


# ---------- 导出 ----------

def export_blockers(design: dict) -> list[str]:
    """非 frozen 时逐条列出还差什么（导出拒绝的理由）。"""
    status = design.get("status")
    if status == "frozen":
        return []
    gaps = [f"设计未定版冻结（status={status}）：只有 frozen 设计有权威版本可交接"]
    fr = design.get("freeze") or {}
    rev = fr.get("review")
    if status == "draft":
        gaps.append("尚未过 reviewed 门（校验 + 承接六项 + 无未清打回项）")
    if not isinstance(rev, dict):
        gaps.append("缺定版评审记录 freeze.review（先走 review prepare → "
                    "异家族评审 → review record）")
    elif rev.get("review_status") == "REVIEW_UNAVAILABLE":
        gaps.append("评审为 REVIEW_UNAVAILABLE 降级状态：跨模型复核恢复后"
                    "补评审才许定版导出")
    elif rev.get("decision") != "pass":
        gaps.append(f"评审决议未 pass（当前 {rev.get('decision')!r}）")
    return gaps


def export_design(root: Path, design: dict, *, date: str | None = None) -> dict:
    """导出交接四件套到 exports/<design_id>/。非 frozen 抛 ExportError。"""
    date = date or today()
    gaps = export_blockers(design)
    if gaps:
        raise ExportError(gaps)
    out_dir = project_paths(root)["exports"] / design["design_id"]
    out_dir.mkdir(parents=True, exist_ok=True)

    runs = topo_order((design.get("contract") or {}).get("runs") or [])

    brief = out_dir / "experiment_brief.md"
    brief.write_text(_render_brief(design, runs, date), encoding="utf-8")

    card = out_dir / "design_card.json"
    card.write_text(json.dumps(design, ensure_ascii=False, indent=2, default=str),
                    encoding="utf-8")

    registry = out_dir / "expected_registry.jsonl"
    lines = [_registry_line(design, r) for r in runs]
    registry.write_text(
        "".join(json.dumps(x, ensure_ascii=False, default=str) + "\n" for x in lines),
        encoding="utf-8")

    repro = out_dir / "reproducibility.md"
    repro.write_text(_render_repro(design, date), encoding="utf-8")

    return {"dir": out_dir, "brief": brief, "design_card": card,
            "expected_registry": registry, "reproducibility": repro,
            "runs": [r["run_id"] for r in runs]}


_KNOWN_RUN_KEYS = {"run_id", "role", "control_run", "depends_on", "stage", "priority"}


def _expected_for(design: dict, run_id: str):
    for e in (design.get("handoff") or {}).get("expected_registry") or []:
        if isinstance(e, dict) and e.get("run_id") == run_id:
            return e.get("expected")
    return None


def _registry_line(design: dict, run: dict) -> dict:
    ev = design.get("evaluation") or {}
    pm = ev.get("primary_metric") or {}
    readout = ev.get("readout") or {}
    fr = design.get("freeze") or {}
    return {
        "design_id": design["design_id"],
        "run_id": run.get("run_id"),
        "role": run.get("role"),
        "control_run": run.get("control_run"),
        "stage": run.get("stage"),
        "primary_metric": {"name": pm.get("name"),
                           "direction": pm.get("direction")},
        "readout": {side: readout.get(side) for side in ("positive", "negative", "null")},
        "expected": _expected_for(design, run.get("run_id")),
        "seeds": (ev.get("seeds") or {}).get("count"),
        "repetitions": ev.get("repetitions"),
        "content_hash": current_frozen_hash(design),
    }


def _render_brief(design: dict, runs: list[dict], date: str) -> str:
    reg = design.get("registration") or {}
    plan = design.get("plan") or {}
    contract = design.get("contract") or {}
    ev = design.get("evaluation") or {}
    res = design.get("resources") or {}
    fr = design.get("freeze") or {}
    claims = design.get("claims") or {}
    pm = ev.get("primary_metric") or {}
    readout = ev.get("readout") or {}

    L: list[str] = []
    L.append(f"# 实验运行清单 — {design.get('title')}")
    L.append("")
    L.append(f"> 交接自 light-design 定版设计书 `{design['design_id']}`"
             f"（承接 idea `{design.get('idea_id')}`），导出于 {date}。")
    L.append(f"> 🔒 冻结哈希 `{current_frozen_hash(design)}`"
             f"｜结果可见性声明：**{reg.get('visibility')}**"
             "｜本清单按依赖拓扑序排列（对照先行），Experiment 照单执行、"
             "逐 run 回填；偏离设计走偏离登记回 Design，不许执行端私自改设计。")
    L.append("")
    L.append("## 主张与判读（对账基准）")
    L.append("")
    for c in claims.get("primary_claims") or []:
        kind = "确认性" if c.get("confirmatory") else "探索性"
        L.append(f"- **[{c.get('id')}]** {c.get('statement')}（{kind}）"
                 f"｜最低可信证据：{c.get('minimum_convincing_evidence')}")
    L.append(f"- 主指标：**{pm.get('name')}**（方向 {pm.get('direction')}，"
             f"惯例出处 {pm.get('convention_source')}）")
    for side, label in (("positive", "正"), ("negative", "负"), ("null", "零")):
        s = readout.get(side) or {}
        L.append(f"- 判读·{label}：{s.get('meaning')}"
                 + (f" → {s['action']}" if s.get("action") else ""))
    L.append("")
    L.append("## 变量表（取值全枚举，run 级取值不得超出此域）")
    L.append("")
    L.append("| 变量 | 组 | 取值域 |")
    L.append("|---|---|---|")
    for v in plan.get("variables") or []:
        dom = json.dumps(v.get("domain") or {}, ensure_ascii=False)
        L.append(f"| {v.get('name')} | {v.get('group')} | {dom} |")
    L.append(f"- 独立重复层级：**{plan.get('replication_level')}**"
             f"｜种子数：{(ev.get('seeds') or {}).get('count')}"
             f"｜重复数：{ev.get('repetitions')}")
    cps = plan.get("intervention_checkpoints") or []
    if cps:
        L.append("- 干预生效核查点（每 run 后留证）："
                 + "；".join(str(c) for c in cps))
    L.append("")
    L.append("## 对照与消融")
    L.append("")
    for c in contract.get("controls") or []:
        sq = "（status quo 一等对照，每批必跑）" if c.get("status_quo") else ""
        L.append(f"- 对照 **{c.get('name')}**{sq}")
    for a in contract.get("ablations") or []:
        L.append(f"- 消融 **{a.get('id')}**：测 {a.get('what_it_tests')}"
                 f"；组件重要则预期 {a.get('expected_if_component_matters')}")
    for u in contract.get("unnecessary_ablations") or []:
        L.append(f"- 显式不做：{u.get('what')}（{u.get('reason')}）")
    L.append("")
    L.append(f"## 运行清单（拓扑序，共 {len(runs)} 个 run）")
    L.append("")
    for i, r in enumerate(runs, 1):
        deps = "、".join(r.get("depends_on") or []) or "—"
        L.append(f"### {i}. {r.get('run_id')}（{r.get('role')}）")
        L.append(f"- 阶段：{r.get('stage') or '—'}｜优先级：{r.get('priority') or '—'}"
                 f"｜对照 run：{r.get('control_run') or '—'}｜前置依赖：{deps}")
        exp = _expected_for(design, r.get("run_id"))
        L.append(f"- 预期登记：{exp if exp is not None else '（无单列预期，按判读三向对账）'}")
        L.append("- 判读标准：见文首判读三向（正/负/零的 meaning 与 action 对全部 run 生效）")
        extras = {k: v for k, v in r.items() if k not in _KNOWN_RUN_KEYS}
        if extras:
            L.append(f"- 附加字段：{json.dumps(extras, ensure_ascii=False, default=str)}")
        L.append("")
    breakers = res.get("circuit_breakers") or []
    if breakers:
        L.append("## 熔断线（触发即停机审查，不许自行放宽）")
        L.append("")
        for b in breakers:
            L.append(f"- {b.get('metric')} @ {b.get('threshold')} → {b.get('action')}")
        L.append("")
    stages = res.get("stages") or []
    if stages:
        L.append("## 阶段转移条件")
        L.append("")
        for s in stages:
            L.append(f"- **{s.get('name')}**：进入 = {s.get('entry_condition')}"
                     f"；退出 = {s.get('exit_condition')}")
        L.append("")
    return "\n".join(L)


def _render_repro(design: dict, date: str) -> str:
    reg = design.get("registration") or {}
    plan = design.get("plan") or {}
    ev = design.get("evaluation") or {}
    ho = design.get("handoff") or {}
    fr = design.get("freeze") or {}
    intake = design.get("intake") or {}
    seeds = ev.get("seeds") or {}
    tp = ev.get("tuning_parity") or {}

    L: list[str] = []
    L.append(f"# 复现字段清单 — {design.get('title')}")
    L.append("")
    L.append(f"> 设计书 `{design['design_id']}`（导出于 {date}）。"
             "复现时逐项核对；任一项不一致，结果不可与冻结版对账。")
    L.append("")
    L.append("## 冻结锚点")
    L.append(f"- 内容哈希：`{current_frozen_hash(design)}`（冻结于 {fr.get('frozen_at')}，"
             f"原始冻结哈希 `{fr.get('content_hash')}`，"
             f"amendment {len(fr.get('amendments') or [])} 条）")
    L.append(f"- 结果可见性声明：{reg.get('visibility')}")
    L.append("")
    L.append("## 随机性")
    L.append(f"- 种子数：{seeds.get('count')}｜种子政策：{seeds.get('policy') or '（未填）'}")
    L.append(f"- 重复数：{ev.get('repetitions')}｜独立重复层级：{plan.get('replication_level')}"
             f"｜重复计数：{plan.get('replication_counts') or {}}")
    rnd = plan.get("randomization") or {}
    if rnd:
        L.append(f"- 随机化：{rnd.get('method') or '—'}｜种子政策：{rnd.get('seed_policy') or '—'}")
    rf = ho.get("repro_fields")
    if rf is not None:
        L.append(f"- 复现字段（handoff 登记）："
                 f"`{json.dumps(rf, ensure_ascii=False, default=str)}`")
    L.append("")
    L.append("## 环境与资产")
    L.append(f"- 软件环境：{reg.get('software_env') or '（未登记）'}")
    assets = reg.get("existing_assets") or []
    L.append(f"- 定版时已有资产：{assets if assets else '（无）'}")
    L.append("")
    L.append("## 数据版本（承接登记）")
    for s in intake.get("spec_intake") or []:
        if s.get("item") in ("datasets", "strongest_baseline"):
            L.append(f"- {s.get('item')}：{s.get('handoff_value') or '（缺）'}")
    dp = ev.get("data_protocol")
    if dp is not None:
        L.append(f"- 数据协议：`{json.dumps(dp, ensure_ascii=False, default=str)}`")
    L.append("")
    L.append("## 调参对等条款（约束 7：比较公平性）")
    L.append(f"- 条款：{tp.get('statement') or '（未声明）'}")
    if tp.get("details"):
        L.append(f"- 细节：{tp['details']}")
    L.append("")
    cps = ho.get("checkpoints") or []
    if cps:
        L.append("## 人类检查点")
        for c in cps:
            L.append(f"- {c.get('node')}（人工确认：{c.get('human_confirm')}）")
        L.append("")
    return "\n".join(L)


# ---------- 项目级报告 ----------

def _extract_manual(text: str) -> str:
    """取旧报告里的手工区内容（标记之间）；无标记时为空。"""
    if MANUAL_START in text and MANUAL_END in text:
        inner = text.split(MANUAL_START, 1)[1].split(MANUAL_END, 1)[0]
        return inner.strip("\n")
    return ""


def build_report(root: Path, *, date: str | None = None) -> dict:
    """生成/刷新 design-stage/DESIGN_REPORT.md，返回汇总 dict。
    手工区（MANUAL 标记之间）逐字保留，不被刷新覆盖。"""
    date = date or today()
    p = project_paths(root)
    meta = {}
    if p["project_yaml"].exists():
        from .util import read_yaml
        meta = read_yaml(p["project_yaml"])
    designs = list_designs(root)
    counts = Counter(d.get("status") for d in designs)
    frozen = [d for d in designs if d.get("status") == "frozen"]
    total_amds = sum(len((d.get("freeze") or {}).get("amendments") or [])
                     for d in designs)

    # 打回记录摘要：returned_items 逐条 + 状态机往返次数
    returned_rows: list[tuple[str, dict]] = []
    return_trips = 0
    for d in designs:
        for r in (d.get("intake") or {}).get("returned_items") or []:
            if isinstance(r, dict):
                returned_rows.append((d["design_id"], r))
        return_trips += sum(1 for h in d.get("status_history") or []
                            if isinstance(h, dict) and h.get("to") == "returned")

    old = p["design_report"].read_text(encoding="utf-8") \
        if p["design_report"].exists() else ""
    manual = _extract_manual(old)

    L: list[str] = []
    L.append(f"# DESIGN_REPORT — {meta.get('project', root.name)}")
    L.append("")
    L.append(f"> 本方向唯一权威文档（report 命令生成/刷新于 {date}）："
             "设计总数 / 状态分布 / 定版清单 / amendment 与打回汇总。"
             "手工区在文末标记之间，刷新不覆盖。")
    L.append("")
    L.append("## 总览")
    L.append("")
    L.append(f"- 设计总数：{len(designs)}")
    for s in ALL_STATES:
        if counts.get(s):
            L.append(f"- {s}：{counts[s]}")
    L.append(f"- 已冻结（frozen）：{len(frozen)}")
    L.append(f"- amendment 总数：{total_amds}")
    L.append(f"- 打回条目总数：{len(returned_rows)}"
             f"（状态机打回往返 {return_trips} 次）")
    L.append("")
    L.append("## 设计清单")
    L.append("")
    if not designs:
        L.append("（暂无设计书）")
    else:
        L.append("| design_id | 状态 | 级别 | amendment | 题名 |")
        L.append("|---|---|---|---|---|")
        for d in sorted(designs, key=lambda x: x["design_id"]):
            n = len((d.get("freeze") or {}).get("amendments") or [])
            L.append(f"| {d['design_id']} | {d.get('status')} | {d.get('tier')} "
                     f"| {n} | {d.get('title')} |")
    L.append("")
    L.append("## 定版清单")
    L.append("")
    if not frozen:
        L.append("（暂无冻结设计）")
    for d in sorted(frozen, key=lambda x: x["design_id"]):
        fr = d.get("freeze") or {}
        rev = fr.get("review") or {}
        rid = rev.get("review_id") or "—"
        L.append(f"- `{d['design_id']}`：{d.get('title')}｜冻结于 {fr.get('frozen_at')}"
                 f"｜哈希 `{str(fr.get('content_hash'))[:12]}…`"
                 f"｜评审收据 {rid}（{rev.get('reviewer')} / {rev.get('family')}）"
                 f"｜交接件 exports/{d['design_id']}/")
    L.append("")
    L.append("## 打回记录摘要")
    L.append("")
    if not returned_rows:
        L.append("（暂无打回条目）")
    for did, r in returned_rows:
        state = "已回补" if r.get("resolved") else "**未清**"
        L.append(f"- `{did}` 打回 **{r.get('item')}**（{r.get('date')}，{state}）"
                 f"：{r.get('reason')}｜需要：{r.get('needed')}")
    for d in designs:
        if d.get("status") == "returned":
            rr = d.get("return_record") or {}
            L.append(f"- `{d['design_id']}` 当前处于 returned："
                     f"缺项 {rr.get('missing_items')}（{rr.get('reason')}）")
    L.append("")
    L.append("## 手工区（人工维护，report 刷新不覆盖）")
    L.append("")
    L.append(MANUAL_START)
    if manual:
        L.append(manual)
    L.append(MANUAL_END)
    L.append("")
    p["design_report"].write_text("\n".join(L), encoding="utf-8")
    return {
        "date": date,
        "total": len(designs),
        "status_counts": {s: counts[s] for s in ALL_STATES if counts.get(s)},
        "frozen": [d["design_id"] for d in frozen],
        "amendments": total_amds,
        "returned_items": len(returned_rows),
        "report_path": str(p["design_report"]),
    }
