"""偏离登记与闭包作废（E4，草案 §2.3 / §6，拍板 ④）。

流程写死：发现即登记（raise，先登记后处置）→ 工具算作废闭包（出生
证明逐维比对 + brief 依赖图传递闭包，与人工估计分开落字）→ 生效
清单公示（publish：哪一维变了、将作废哪些 run，落盘成文）→ 生效
（apply：作废标记只追加 voided_by，run 经 deviated → reconciled 以
作废身份对账）→ 覆写（override：显式登记覆写者与理由，覆写本身进
偏离登记，报告标红提示其溯源代价）。

deviations.jsonl 是只增账：raise / publish / apply / override 四种
条目按 deviation_id 折叠成一条偏离的现行状态，没有改写入口。
构成设计修订的偏离（disposition=stop_and_return_design）在登记时
自动生成 design_amendment_draft 回流条目（reflux/design_inbox）。
"""

from __future__ import annotations

from pathlib import Path

from .events import append_event
from .gates import GateError
from .project import (
    DEVIATIONS_FILENAME,
    append_jsonl_entry,
    exec_dir,
    load_package,
    load_reconciliation,
    reflux_dir,
    save_reconciliation,
    save_run,
)
from .schema import (
    DEVIATION_DISPOSITIONS,
    DEVIATION_TYPES,
    TRIGGER_DIMENSIONS,
    run_voided_by,
    trigger_anchor,
    _nonempty_str,
)
from .util import today, utcnow

ENTRY_KINDS = ("raise", "publish", "apply", "override")


# ---------- 折叠（只增账 → 现行状态） ----------

def fold_deviations(entries: list[dict]) -> list[dict]:
    """把 deviations.jsonl 条目按 deviation_id 折叠：raise 定型主体，
    publish/apply 各至多一条（重复即后者覆盖并在校验器侧无从区分——
    折叠保留首条，重复生效属流程违规，由 apply 函数在写入时拦截），
    override 可多条（豁免集取并集）。"""
    folded: dict[str, dict] = {}
    order: list[str] = []
    for e in entries:
        if not isinstance(e, dict):
            continue
        did = e.get("deviation_id")
        kind = e.get("kind")
        if not did or kind not in ENTRY_KINDS:
            continue
        if kind == "raise":
            if did not in folded:
                order.append(did)
                folded[did] = {**e, "published": None, "applied": None,
                               "overrides": []}
            continue
        dev = folded.get(did)
        if dev is None:
            continue  # 无 raise 的后续条目：孤儿，校验器在 validate 侧无据可依，忽略
        if kind == "publish" and dev["published"] is None:
            dev["published"] = e
        elif kind == "apply" and dev["applied"] is None:
            dev["applied"] = e
        elif kind == "override":
            dev["overrides"].append(e)
    out = []
    for did in order:
        dev = folded[did]
        pub = dev["published"]
        dev["closure_current"] = (pub or {}).get("closure") or \
            dev.get("affected_runs_closure") or []
        exempted: list[str] = []
        for ov in dev["overrides"]:
            for rid in ov.get("exempted_runs") or []:
                if rid not in exempted:
                    exempted.append(rid)
        dev["exempted_runs"] = exempted
        dev["effective_closure"] = [r for r in dev["closure_current"]
                                     if r not in exempted]
        out.append(dev)
    return out


def get_deviation(pkg: dict, deviation_id: str) -> dict:
    for dev in pkg.get("deviations") or []:
        if dev.get("deviation_id") == deviation_id:
            return dev
    raise ValueError(f"偏离不存在：{deviation_id}")


# ---------- 闭包计算（拍板 ④：作废靠算不靠点名） ----------

def compute_closure(pkg: dict, *, run_id: str | None,
                    dimension: str | None) -> list[str]:
    """作废闭包 = 直接受影响集 ∪ 依赖图传递闭包（展开到全部 attempt）。

    直接集两部分：
    1. 发现上下文 run 本身；
    2. 锚匹配：与上下文 run 在触发维上锚值相同的全部已开跑 run——
       偏离的本质是「这一维的实际取值不是声称的那个」，凡与它同锚
       的 run 用的都是同一个实际取值，同罪同罚（例：代码快照实际
       是 v2 而非声称的 v1，则全部以 v2 锚开跑的 run 都受影响）。
    传递闭包：brief 依赖图按条目（design_run_id）求上游污染的下游
    传递闭包——受影响条目的全部下游条目（含其全部 attempt）都进集，
    因为它们消费了受影响 run 的产物。
    """
    runs = pkg["runs"]
    execution = pkg["execution"]
    direct: set[str] = set()
    if run_id and run_id in runs:
        direct.add(run_id)
        if dimension:
            anchor = trigger_anchor(runs[run_id], dimension)
            if anchor:
                for rid, r in runs.items():
                    if trigger_anchor(r, dimension) == anchor:
                        direct.add(rid)
    affected_entries = {runs[r]["design_run_id"] for r in direct if r in runs}
    deps = {b.get("run_id"): list(b.get("depends_on") or [])
            for b in execution.get("brief_runs") or [] if isinstance(b, dict)}
    changed = True
    while changed:
        changed = False
        for entry, ups in deps.items():
            if entry not in affected_entries and \
                    any(u in affected_entries for u in ups):
                affected_entries.add(entry)
                changed = True
    closure = sorted(r["run_id"] for r in runs.values()
                     if r.get("design_run_id") in affected_entries)
    return closure


# ---------- raise / publish / apply / override ----------

def _next_deviation_id(pkg: dict) -> str:
    return f"DV-{len(pkg.get('deviations') or []) + 1:04d}"


def raise_deviation(root: Path, exec_id: str, *, run_id: str | None = None,
                    context: str = "", type: str, dimension: str | None = None,
                    description: str, claimed: str = "", actual: str = "",
                    declared: tuple[str, ...] = (),
                    disposition: str, declaration: str = "",
                    decided_by: str = "", by: str = "",
                    date: str | None = None) -> dict:
    """登记一条偏离（先登记后处置）。declared 是人工估计的影响集，
    与工具算出的 affected_runs_closure 分开落字——两者不一致正是
    「作废靠算不靠点名」的证据。构成设计修订的当场生成回流条目。"""
    date = date or today()
    if type not in DEVIATION_TYPES:
        raise ValueError(f"偏离 type 非法：{type!r}（须属 {list(DEVIATION_TYPES)}）")
    if disposition not in DEVIATION_DISPOSITIONS:
        raise ValueError(f"disposition 非法：{disposition!r}"
                         f"（须属 {list(DEVIATION_DISPOSITIONS)}）")
    if dimension is not None and dimension not in TRIGGER_DIMENSIONS:
        raise ValueError(f"trigger_dimension 非法：{dimension!r}"
                         f"（须属 {list(TRIGGER_DIMENSIONS)} 或不给）")
    if not _nonempty_str(description):
        raise ValueError("偏离必须写明 description（偏离了什么）")
    if disposition == "accept_with_declaration" and not _nonempty_str(declaration):
        raise ValueError("disposition=accept_with_declaration 必须带声明文本"
                         "（--declaration）：接受偏离的声明要进对账表对应行")
    pkg = load_package(root, exec_id)
    runs = pkg["runs"]
    if run_id is not None and run_id not in runs:
        raise ValueError(f"发现上下文 run 不存在：{run_id}")
    for rid in declared:
        if rid not in runs:
            raise ValueError(f"人工估计影响集含不存在的 run：{rid}")
    closure = compute_closure(pkg, run_id=run_id, dimension=dimension)
    dev_id = _next_deviation_id(pkg)
    d = exec_dir(root, exec_id)
    ev = append_event(d, "deviation_raised", run_id=run_id,
                      payload={"deviation_id": dev_id, "type": type,
                               "dimension": dimension,
                               "disposition": disposition})
    execution = pkg["execution"]
    entry = {
        "kind": "raise",
        "deviation_id": dev_id,
        "discovered_at": utcnow(),
        "date": date,
        "event_ref": ev["event_id"],
        "run_id": run_id,
        "context": context,
        "type": type,
        "trigger_dimension": dimension,
        "description": description,
        "claimed_vs_actual": {"claimed": claimed, "actual": actual},
        "affected_runs_declared": list(declared),
        "affected_runs_closure": closure,
        "disposition": disposition,
        "declaration": declaration,
        "decided_by": decided_by or by or "light-experiment deviation raise",
        "design_ref": {"design_id": (execution.get("design_ref") or {}).get("design_id"),
                       "content_hash": (execution.get("design_ref") or {}).get("content_hash")},
    }
    append_jsonl_entry(root, exec_id, DEVIATIONS_FILENAME, entry)
    if disposition == "stop_and_return_design":
        _emit_design_amendment_draft(root, exec_id, entry, date)
        append_event(d, "reflux_emitted",
                     payload={"deviation_id": dev_id,
                              "kind": "design_amendment_draft",
                              "target": "design"})
    return entry


def _emit_design_amendment_draft(root: Path, exec_id: str, dev_entry: dict,
                                 date: str) -> dict:
    """构成设计修订的偏离 → reflux/design_inbox 的 amendment 草稿条目
    （回 Design 侧待处理；本技能不直接改设计书）。"""
    rd = reflux_dir(root, exec_id)
    rd.mkdir(parents=True, exist_ok=True)
    inbox = rd / "design_inbox.jsonl"
    # RX 编号在两本回流账之间统一计数，避免同号条目跨账撞车
    from .util import read_jsonl
    total = 0
    for other in ("retry_queue.jsonl", "design_inbox.jsonl"):
        op = rd / other
        if op.exists():
            total += len(read_jsonl(op))
    entry = {
        "entry_id": f"RX-{total + 1:04d}",
        "kind": "design_amendment_draft",
        "source": "deviation",
        "source_id": dev_entry["deviation_id"],
        "run_id": dev_entry.get("run_id"),
        "summary": dev_entry.get("description"),
        "claimed_vs_actual": dev_entry.get("claimed_vs_actual"),
        "affected_runs_closure": dev_entry.get("affected_runs_closure"),
        "status": "pending",
        "created": date,
    }
    with open(inbox, "a", encoding="utf-8") as f:
        import json
        f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
    return entry


def publish_deviation(root: Path, exec_id: str, deviation_id: str, *,
                      by: str = "", date: str | None = None) -> dict:
    """生成生效清单并公示落盘：executions/<id>/deviation_notices/
    <deviation_id>.md——将作废哪些 run、各自哪一维变了、人工估计与
    工具闭包的差异，一并示人。公示后才许 apply（先公示后作废）。"""
    date = date or today()
    pkg = load_package(root, exec_id)
    dev = get_deviation(pkg, deviation_id)
    if dev.get("published"):
        raise GateError([f"{deviation_id} 已公示过（重复公示不许："
                         "清单变更走 override 留痕）"])
    if dev.get("applied"):
        raise GateError([f"{deviation_id} 已生效，不许事后补公示"])
    closure = compute_closure(pkg, run_id=dev.get("run_id"),
                              dimension=dev.get("trigger_dimension"))
    runs = pkg["runs"]
    dim = dev.get("trigger_dimension")
    lines = [
        f"# 生效清单（偏离公示）— {deviation_id}", "",
        f"> 公示于 {date}。偏离类型 {dev.get('type')}，触发维 "
        f"{dim or '（无：不作维度比对）'}，处置 {dev.get('disposition')}。",
        f"> 偏离内容：{dev.get('description')}",
        f"> 声称 vs 实际：{dev.get('claimed_vs_actual')}", "",
        "## 将受影响的 run（工具闭包，公示口径）", "",
        "| run_id | 条目 | 状态 | 该维锚（前 12 位） |",
        "|---|---|---|---|",
    ]
    for rid in closure:
        r = runs[rid]
        anchor = trigger_anchor(r, dim) if dim else None
        lines.append(f"| {rid} | {r.get('design_run_id')} | {r.get('status')} "
                     f"| `{anchor[:12]}…` |" if anchor else
                     f"| {rid} | {r.get('design_run_id')} | {r.get('status')} | — |")
    declared = dev.get("affected_runs_declared") or []
    lines += ["", f"人工估计影响集（登记时）：{declared or '（未给）'}",
              f"工具闭包：{closure}",
              "两者不一致时以闭包为准（作废靠算不靠点名）；认为闭包有误，"
              "用 deviation override 显式豁免并留理由，不许口头放行。", ""]
    d = exec_dir(root, exec_id)
    notices = d / "deviation_notices"
    notices.mkdir(parents=True, exist_ok=True)
    notice_path = notices / f"{deviation_id}.md"
    notice_path.write_text("\n".join(lines), encoding="utf-8")
    entry = {"kind": "publish", "deviation_id": deviation_id, "date": date,
             "by": by or "light-experiment deviation publish",
             "closure": closure, "notice": str(notice_path)}
    append_jsonl_entry(root, exec_id, DEVIATIONS_FILENAME, entry)
    append_event(d, "deviation_decided",
                 payload={"deviation_id": deviation_id, "action": "publish",
                          "closure": closure})
    return entry


def apply_deviation(root: Path, exec_id: str, deviation_id: str, *,
                    by: str = "", date: str | None = None) -> dict:
    """生效：按公示闭包（减去 override 豁免）处置。
    - void_and_rerun / stop_and_return_design：闭包内已终止的 run 打
      作废标记（voided_by 只追加）并转 deviated，之后 advance 以作废
      身份进 reconciled；planned 的记为下游待处置（不开跑即不受罚，
      但对账行登记该偏离）；running / reconciled 的不许直接作废——
      逐个点名拦下（先终止 / 先 override 豁免）。
    - accept_with_declaration：不作废，声明文本进对账表对应行。
    - continue_with_note：只落事件与登记，run 不动。"""
    date = date or today()
    pkg = load_package(root, exec_id)
    dev = get_deviation(pkg, deviation_id)
    if dev.get("applied"):
        raise GateError([f"{deviation_id} 已生效过（只增账不许重复生效）"])
    pub = dev.get("published")
    if not pub:
        raise GateError([f"{deviation_id} 尚未公示（publish）："
                         "生效清单先公示后作废，不许先斩后奏"])
    disposition = dev.get("disposition")
    closure = dev["effective_closure"]
    runs = pkg["runs"]
    d = exec_dir(root, exec_id)

    if disposition == "accept_with_declaration":
        recon = load_reconciliation(root, exec_id)
        touched = []
        if recon is not None:
            entries = {runs[r]["design_run_id"] for r in closure if r in runs}
            for row in recon.get("rows") or []:
                if row.get("registry_run_id") in entries:
                    row.setdefault("deviations", []).append(deviation_id)
                    row.setdefault("declarations", []).append(
                        {"deviation_id": deviation_id,
                         "text": dev.get("declaration")})
                    touched.append(row.get("registry_run_id"))
            save_reconciliation(root, exec_id, recon)
        entry = {"kind": "apply", "deviation_id": deviation_id, "date": date,
                 "by": by or "light-experiment deviation apply",
                 "invalidated": [], "declared_rows": touched,
                 "exempted": dev["exempted_runs"]}
        append_jsonl_entry(root, exec_id, DEVIATIONS_FILENAME, entry)
        append_event(d, "deviation_decided",
                     payload={"deviation_id": deviation_id, "action": "apply",
                              "disposition": disposition})
        return entry

    if disposition == "continue_with_note":
        entry = {"kind": "apply", "deviation_id": deviation_id, "date": date,
                 "by": by or "light-experiment deviation apply",
                 "invalidated": [], "downstream_planned": [],
                 "exempted": dev["exempted_runs"]}
        append_jsonl_entry(root, exec_id, DEVIATIONS_FILENAME, entry)
        append_event(d, "deviation_decided",
                     payload={"deviation_id": deviation_id, "action": "apply",
                              "disposition": disposition})
        return entry

    # void_and_rerun / stop_and_return_design
    blockers: list[str] = []
    for rid in closure:
        st = runs[rid].get("status")
        if st in ("running", "reconciled"):
            blockers.append(f"{rid} 处于 {st}：running 须先终止、reconciled "
                            "是终态不许回改作废——处置它只能先 deviation "
                            "override 显式豁免，或新开 run 替代")
    if blockers:
        raise GateError(blockers)
    invalidated: list[str] = []
    downstream_planned: list[str] = []
    for rid in closure:
        run = runs[rid]
        st = run.get("status")
        if st == "planned":
            downstream_planned.append(rid)
            continue
        recon_ptr = run["conclusion"].setdefault("reconciliation", {})
        cur = recon_ptr.get("voided_by")
        if cur is None:
            recon_ptr["voided_by"] = deviation_id
        elif isinstance(cur, list):
            if deviation_id not in cur:
                cur.append(deviation_id)
        elif cur != deviation_id:
            recon_ptr["voided_by"] = [cur, deviation_id]
        if st in ("completed", "failed"):
            run.setdefault("status_history", []).append(
                {"from": st, "to": "deviated", "date": date,
                 "by": by or "light-experiment deviation apply",
                 "note": f"被偏离 {deviation_id} 闭包作废（作废标记只追加，"
                         "以作废身份对账）"})
            run["status"] = "deviated"
            run["updated"] = date
        save_run(root, exec_id, run)
        invalidated.append(rid)
        append_event(d, "void_marked", run_id=rid,
                     payload={"deviation_id": deviation_id})
    # 对账行联动：受影响行登记偏离；行内 run 全作废 → 行 voided；
    # 已回填的行被作废污染 → blocked（须以替代 run 重新回填）
    recon = load_reconciliation(root, exec_id)
    if recon is not None:
        affected_entries = {runs[r]["design_run_id"] for r in closure
                            if r in runs}
        dirty = False
        for row in recon.get("rows") or []:
            if row.get("registry_run_id") not in affected_entries:
                continue
            row.setdefault("deviations", []).append(deviation_id)
            dirty = True
            row_runs = [runs[u] for u in row.get("run_ids") or [] if u in runs]
            if row_runs and all(run_voided_by(u) for u in row_runs):
                if row.get("status") in ("pending", "filled"):
                    row["status"] = "voided"
            elif row.get("status") == "filled":
                row["status"] = "blocked"
        if dirty:
            save_reconciliation(root, exec_id, recon)
    entry = {"kind": "apply", "deviation_id": deviation_id, "date": date,
             "by": by or "light-experiment deviation apply",
             "invalidated": invalidated,
             "downstream_planned": downstream_planned,
             "exempted": dev["exempted_runs"]}
    append_jsonl_entry(root, exec_id, DEVIATIONS_FILENAME, entry)
    append_event(d, "deviation_voided",
                 payload={"deviation_id": deviation_id,
                          "invalidated": invalidated})
    return entry


def override_deviation(root: Path, exec_id: str, deviation_id: str, *,
                       exempted_runs: tuple[str, ...], by: str, reason: str,
                       date: str | None = None) -> dict:
    """显式覆写：把闭包内的若干 run 豁免出作废集。必须登记覆写者与
    理由——覆写本身进偏离登记、报告标红：被豁免 run 的结果溯源链从
    此带上「人工担责」标记，审计时先查这里。已生效的作废不许覆写
    回滚（只增纪律：错了只能新开 run 替代）。"""
    date = date or today()
    if not _nonempty_str(by):
        raise ValueError("覆写必须登记覆写者（--by）：匿名覆写不许")
    if not _nonempty_str(reason):
        raise ValueError("覆写必须登记理由（--reason）：无理由的豁免即橡皮图章")
    pkg = load_package(root, exec_id)
    dev = get_deviation(pkg, deviation_id)
    if dev.get("applied"):
        raise GateError([f"{deviation_id} 已生效：作废只追加不回滚，"
                         "覆写只能在 apply 之前豁免；已作废的 run 须新开替代"])
    for rid in exempted_runs:
        if rid not in pkg["runs"]:
            raise ValueError(f"豁免集含不存在的 run：{rid}")
        if rid not in dev["closure_current"]:
            raise ValueError(f"{rid} 不在 {deviation_id} 的公示闭包内，无从豁免")
    entry = {"kind": "override", "deviation_id": deviation_id, "date": date,
             "by": by, "reason": reason,
             "exempted_runs": list(exempted_runs)}
    append_jsonl_entry(root, exec_id, DEVIATIONS_FILENAME, entry)
    append_event(exec_dir(root, exec_id), "human_checkpoint", source="user",
                 payload={"deviation_id": deviation_id, "action": "override",
                          "exempted_runs": list(exempted_runs),
                          "reason": reason, "by": by})
    return entry
