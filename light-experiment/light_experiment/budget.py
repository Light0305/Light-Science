"""预算闸（E2 补，拍板 ⑤：熔断只许停不许改）。

熔断线在承接时从 Design 交接件落进 budget_ledger.circuit_breakers
快照（design 侧冻结值，执行端无任何命令可以改它——本模块通篇没有
写 limits 的入口，放宽只能回 Design 走 amendment）。

`budget check`：把 run 账与包总账对照熔断线——
- 包级：spent[metric] ≥ 线 → 该线触发；
- run 级：单个 run 的 attempts_budget[metric] ≥ 线 → 该 run 单独点名。
触发即落 budget_event（+ action=stop 时另落 breaker_tripped），
并把当时仍在 running 的 run 登记为 killed_budget 候选
（budget_ledger.candidates）——候选只是名单，真正终止仍走
run-finish --exit-status killed_budget 留痕，不许工具代杀无痕。
"""

from __future__ import annotations

from pathlib import Path

from .events import append_event
from .gates import BUDGET_KEYS
from .project import exec_dir, load_package, save_execution
from .util import today


def budget_lines(execution: dict) -> list[dict]:
    """现行熔断线 = 承接快照 circuit_breakers 中落在预算维度上的条目。"""
    ledger = execution.get("budget_ledger") or {}
    return [cb for cb in ledger.get("circuit_breakers") or []
            if isinstance(cb, dict) and cb.get("metric") in BUDGET_KEYS
            and isinstance(cb.get("threshold"), (int, float))]


def check_budget(root: Path, exec_id: str, *, by: str = "",
                 date: str | None = None) -> dict:
    """对照熔断线检查预算账。返回 {tripped: [...], candidates: [...],
    lines: [...]}；触发时落事件 + 候选名单（只停报，不改线）。"""
    date = date or today()
    pkg = load_package(root, exec_id)
    execution = pkg["execution"]
    ledger = execution.setdefault("budget_ledger", {})
    spent = ledger.get("spent") or {}
    lines = budget_lines(execution)
    tripped: list[dict] = []
    for cb in lines:
        metric, threshold = cb["metric"], cb["threshold"]
        total = spent.get(metric) or 0
        offenders = sorted(
            r["run_id"] for r in pkg["runs"].values()
            if ((r.get("observation") or {}).get("attempts_budget") or {})
            .get(metric, 0) >= threshold)
        if total >= threshold or offenders:
            tripped.append({"metric": metric, "threshold": threshold,
                            "spent": total, "action": cb.get("action"),
                            "offending_runs": offenders})
    candidates: list[str] = []
    if tripped:
        candidates = sorted(r["run_id"] for r in pkg["runs"].values()
                            if r.get("status") == "running")
        ledger["candidates"] = candidates
        d = exec_dir(root, exec_id)
        for t in tripped:
            append_event(d, "budget_event",
                         payload={"kind": "circuit_breaker_check",
                                  "metric": t["metric"],
                                  "threshold": t["threshold"],
                                  "spent": t["spent"],
                                  "candidates": candidates,
                                  "by": by or "light-experiment budget check"})
            if t.get("action") == "stop":
                append_event(d, "breaker_tripped",
                             payload={"metric": t["metric"],
                                      "threshold": t["threshold"],
                                      "spent": t["spent"],
                                      "candidates": candidates})
    ledger["last_check"] = {"date": date, "tripped": [t["metric"] for t in tripped],
                            "candidates": candidates}
    execution["updated"] = date
    save_execution(root, execution)
    return {"tripped": tripped, "candidates": candidates, "lines": lines}
