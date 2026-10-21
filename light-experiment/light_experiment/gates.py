"""双层状态机（草案 §2.6）。

run 级：planned → running → completed / failed / deviated → reconciled
    - reconciled 是终态、不可逆：要改只能新开 run 并以 lineage 指回
      （拍板 ②：恢复/重试 = 新尝试成 run + 血缘指针）；
    - 作废不是删除：作废走 deviated → reconciled（以作废身份对账），
      本期只立状态与门，闭包计算在二期。
包级：intake → sanity → executing → reconciling → delivered
    - 旁路 blocked：必须写明阻塞原因与解阻条件，解阻只许回到受阻前状态；
    - delivered 门（约束 13：未清零不交付）：全部 run 已 reconciled、
      对账表行数与预期登记逐行对齐、无 run 停在 deviated 待处置。

门只验确定性事实；「跑得对不对」归规程与 Analysis，不在此假装能验。
"""

from __future__ import annotations

from .schema import PKG_MAIN_STATES, PKG_NEXT, RUN_NEXT, _nonempty_str

BUDGET_KEYS = ("wall_clock_s", "gpu_hours", "api_cost")


class GateError(Exception):
    """门校验失败。errors 为逐条人读原因。"""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("；".join(errors))


def _append_history(obj: dict, to: str, by: str, date: str, note: str) -> None:
    hist = obj.setdefault("status_history", [])
    hist.append({"from": obj.get("status"), "to": to, "date": date,
                 "by": by or "light-experiment", "note": note})
    obj["status"] = to
    obj["updated"] = date


# ---------- run 级 ----------

def advance_run(run: dict, to: str, *, by: str = "", date: str,
                note: str = "") -> dict:
    """run 级通用推进（run-start / run-finish 走各自专用通道，此处管
    reconciled 与 deviated 的收尾跃迁）。非法跃迁/门不过抛 GateError。"""
    cur = run.get("status")
    if to not in RUN_NEXT.get(cur, ()):
        raise GateError([f"非法跃迁：run {run.get('run_id')} {cur} → {to}"
                         f"（{cur} 只许去 {RUN_NEXT.get(cur, ()) or '终态，无出边'}）"])
    errs: list[str] = []
    if to == "reconciled":
        conc = run.get("conclusion") or {}
        if not conc.get("exit_status"):
            errs.append("进 reconciled 须先落 exit_status（终止分类未落字不许对账）")
        if cur == "failed":
            salvage = conc.get("salvage") or []
            if not salvage and not _nonempty_str(conc.get("salvage_note")):
                errs.append("失败 run 进 reconciled 须先登记抢救产物或写明无可抢救")
        if cur == "deviated":
            recon = conc.get("reconciliation") or {}
            if not (recon.get("voided_by") or _nonempty_str(note)):
                errs.append("deviated run 进 reconciled 须有处置依据："
                            "对账指针 voided_by（作废身份对账）或本次推进附注记说明处置")
    if errs:
        raise GateError(errs)
    _append_history(run, to, by, date, note)
    return run


# ---------- 包级 ----------

def _acceptance_errors(pkg: dict) -> list[str]:
    """基线复现验收门（sanity → executing，草案 §5）：brief 有基线
    条目（role=baseline）或验收表已生成时，验收结论必须 passed 才许
    开主清单——复现不达标不开主实验，不许带病开跑后在结论里解释。"""
    from .schema import BASELINE_ROLE
    execution = pkg["execution"]
    has_baseline = any(isinstance(b, dict) and b.get("role") == BASELINE_ROLE
                       for b in execution.get("brief_runs") or [])
    acc = pkg.get("acceptance")
    if acc is None:
        if has_baseline:
            return ["brief 含基线条目但基线复现验收表未生成：先 acceptance "
                    "init 冻结验收表并逐叶判定，验收未过不许开主清单（草案 §5）"]
        return []
    if acc.get("verdict") != "passed":
        return [f"基线复现验收未通过（verdict={acc.get('verdict')!r}）："
                "复现分未达阈值不开主清单——先走 E5 诊断归因（种子/数据版本/"
                "未报告技巧三项清单），或回 Design 报告基线不可复现（草案 §5）"]
    # D-EXP-1：verdict 落字 passed 不够——advance 前复跑叶级容差校验
    # （与 validate 同口径），防落盘状态里藏着超容差冒判 pass 的结果叶
    from .schema import result_leaf_tolerance_problem
    tol_errs = []
    for leaf in acc.get("leaves") or []:
        if not isinstance(leaf, dict):
            continue
        prob = result_leaf_tolerance_problem(leaf, acc.get("tolerance_pct"))
        if prob:
            tol_errs.append(f"验收叶 {leaf.get('leaf_id')} 判 pass 但{prob}："
                            "该叶 pass 不成立，验收结论 passed 不作数，"
                            "不许开主清单")
    return tol_errs


def _delivered_errors(pkg: dict) -> list[str]:
    errs: list[str] = []
    execution = pkg["execution"]
    runs = pkg["runs"]
    if not runs:
        errs.append("无任何 run，不许交付空执行包")
    for run in runs.values():
        if run.get("status") != "reconciled":
            errs.append(f"run {run.get('run_id')} 尚未对账清零"
                        f"（status={run.get('status')}）：未清零不交付（约束 13）")
    recon = pkg.get("reconciliation")
    registry_ids = (execution.get("intake_report") or {}).get("registry_run_ids") or []
    if not isinstance(recon, dict):
        errs.append("对账表缺失（reconciliation.yaml），不许交付")
    else:
        row_ids = [r.get("registry_run_id") for r in recon.get("rows") or []
                   if isinstance(r, dict)]
        if sorted(row_ids) != sorted(registry_ids):
            errs.append("对账表行数与预期登记不对齐（缺行），不许交付")
        # 二期：对账清零检查（与 reconcile check 同口径的门控子集）：
        # 缺行 / blocked / 作废未替代恒拦；pending 行仅当包已进入实质
        # 对账（reconcile fill 用过，substantive=true）才拦——一期只做
        # 行对齐的包沿用一期口径，进入实质对账就必须逐行清零到底。
        from .schema import reconciliation_problems
        errs.extend(reconciliation_problems(
            pkg, pending_blocks=bool(recon.get("substantive"))))
    # 二期：偏离全处置、失败全分类——仅当对应子流程已被启用
    # （登记文件在场）时才成门，未启用的包沿用一期口径。
    if pkg.get("deviations_present"):
        for dev in pkg.get("deviations") or []:
            if not dev.get("applied"):
                errs.append(f"偏离 {dev.get('deviation_id')} 尚未处置生效"
                            "（apply）：偏离全处置才许交付（草案 §2.6）")
    if pkg.get("failures_present"):
        classified = {f.get("run_id") for f in pkg.get("failures") or []}
        for run in runs.values():
            es = (run.get("conclusion") or {}).get("exit_status")
            if run.get("status") in ("failed", "reconciled") and es and \
                    es != "completed" and run["run_id"] not in classified:
                errs.append(f"run {run['run_id']} 失败终止（{es}）但未分类："
                            "失败全分类（MAST × IVE）才许交付（草案 §2.6）")
    return errs


def advance_package(pkg: dict, to: str, *, by: str = "", date: str,
                    note: str = "", block_reason: str = "",
                    unblock_condition: str = "") -> dict:
    """包级推进。pkg 为 load_package 组装的整包 dict；成功就地修改
    pkg['execution'] 并返回它。门不过抛 GateError 逐条点名。"""
    execution = pkg["execution"]
    cur = execution.get("status")

    if to == "blocked":
        if cur == "delivered":
            raise GateError(["delivered 是终态，不许再转 blocked"])
        if cur == "blocked":
            raise GateError(["执行包已处于 blocked"])
        if not _nonempty_str(block_reason) or not _nonempty_str(unblock_condition):
            raise GateError(["转 blocked 须写明阻塞原因与解阻条件"
                             "（--reason / --unblock）"])
        execution["block_record"] = {
            "reason": block_reason, "unblock_condition": unblock_condition,
            "from_state": cur, "date": date,
        }
        _append_history(execution, "blocked", by, date, note or block_reason)
        return execution

    if cur == "blocked":
        br = execution.get("block_record") or {}
        home = br.get("from_state")
        if to != home:
            raise GateError([f"blocked 只许解阻回到受阻前状态 {home}，不许去 {to}"])
        execution["block_record"] = None
        _append_history(execution, to, by, date, note or "解阻")
        return execution

    if to not in PKG_NEXT.get(cur, ()):
        raise GateError([f"非法跃迁：执行包 {cur} → {to}"
                         f"（{cur} 只许去 {PKG_NEXT.get(cur, ()) or '终态，无出边'}）"])

    errs: list[str] = []
    if to == "sanity":
        gaps = (execution.get("intake_report") or {}).get("gaps") or []
        if gaps:
            errs.append(f"承接校验未清零（{len(gaps)} 项缺口未打回解决）："
                        "对不齐不开跑，缺口见 intake_report.gaps")
    elif to == "executing":
        if not pkg["runs"]:
            errs.append("尚无任何 run：先 run-new 承接 brief 条目再进执行")
        errs.extend(_acceptance_errors(pkg))
    elif to == "reconciling":
        for run in pkg["runs"].values():
            if run.get("status") in ("planned", "running"):
                errs.append(f"run {run.get('run_id')} 仍在 {run.get('status')}，"
                            "未终止不许进对账阶段")
    elif to == "delivered":
        errs.extend(_delivered_errors(pkg))
    if errs:
        raise GateError(errs)
    _append_history(execution, to, by, date, note)
    return execution
