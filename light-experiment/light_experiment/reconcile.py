"""对账实质化（E6，草案 §2.5）与 execution_card.json 投影导出。

一期对账表只做行对齐占位；二期逐行回填事实层材料：
- readout_actual 只收分布摘要 {mean, spread, n, replication_level}，
  单点值（数字本身 / 含 value 等单点键 / n<2 的伪分布）在登记时
  即被拒绝——「跑了一次的读数」不许冒充分布（约束 12）；
- random_sources 逐行落字：哪些随机源被重新随机化、哪些被冻结；
  「只换种子 + 冻结其余」自动标有偏估计警告（bias_warnings）；
- layers 三层事实判定：implementation / execution 二值，
  result_fact 三态（within / outside / incomparable，不可比须写原因）。
本表只做事实层：readout 三向的正式判定（positive/negative/null）
由 Analysis 回写，本技能不下「改进成立」结论（草案 §2.5 注）。

`reconcile check` = reconciliation_problems 的 CLI 面（逐行清零，
缺行 / 未填 / 作废未替代逐个点名）；delivered 门消费同一口径。
"""

from __future__ import annotations

import json
from pathlib import Path

from .events import append_event
from .gates import GateError
from .project import exec_dir, load_package, load_reconciliation, save_reconciliation
from .schema import (
    RESULT_FACT_VERDICTS,
    bias_warnings,
    readout_distribution_errors,
    reconciliation_problems,
    run_voided_by,
    _nonempty_str,
)
from .util import today


def fill_row(root: Path, exec_id: str, registry_run_id: str, *,
             readout: dict, random_sources: dict, layers: dict,
             evidence: tuple[str, ...] = (), by: str = "",
             date: str | None = None) -> dict:
    """逐行回填一条对账行。形状不过（单点/缺层/不可比无原因）在
    登记时即拒绝，不许先落字再由校验器事后发现。"""
    date = date or today()
    errs = readout_distribution_errors(readout, f"对账行 {registry_run_id}")
    if errs:
        raise GateError(errs)
    if not isinstance(random_sources, dict) or \
            "rerandomized" not in random_sources or \
            "frozen" not in random_sources:
        raise GateError([f"对账行 {registry_run_id} random_sources 须含 "
                         "rerandomized 与 frozen 两份清单"
                         "（哪些被重新随机化、哪些被冻结，逐行落字）"])
    if not isinstance(layers, dict):
        raise GateError([f"对账行 {registry_run_id} layers 须为对象"])
    for layer in ("implementation", "execution"):
        if not isinstance(layers.get(layer), bool):
            raise GateError([f"对账行 {registry_run_id} layers.{layer} 须为"
                             "二值判定（实现/执行层照 PaperBench 三层记账）"])
    rf = layers.get("result_fact") or {}
    if rf.get("verdict") not in RESULT_FACT_VERDICTS:
        raise GateError([f"对账行 {registry_run_id} layers.result_fact.verdict "
                         f"非法：{rf.get('verdict')!r}（须属 "
                         f"{list(RESULT_FACT_VERDICTS)}）"])
    if rf.get("verdict") == "incomparable" and not _nonempty_str(rf.get("reason")):
        raise GateError([f"对账行 {registry_run_id} result_fact 判 incomparable "
                         "必须写明不可比原因（如真值未过低方差门）"])
    recon = load_reconciliation(root, exec_id)
    if recon is None:
        raise ValueError("对账表不存在（承接未清零时不生成对账表）")
    row = next((r for r in recon.get("rows") or []
                if r.get("registry_run_id") == registry_run_id), None)
    if row is None:
        raise ValueError(f"对账行不存在：{registry_run_id}（逐行对账不许缺行，"
                         "也不许清单外自创行）")
    pkg = load_package(root, exec_id)
    runs = pkg["runs"]
    if row.get("status") == "voided":
        live = [u for u in row.get("run_ids") or []
                if u in runs and not run_voided_by(runs[u])]
        if not live:
            raise GateError([f"对账行 {registry_run_id} 已作废且无替代 run："
                             "先新开替代 run 再回填（作废未替代不清零）"])
    rs = dict(random_sources)
    rs["bias_warnings"] = bias_warnings(random_sources)
    row["readout_actual"] = readout
    row["random_sources"] = rs
    row["layers"] = layers
    if evidence:
        row["evidence"] = list(evidence)
    row["status"] = "filled"
    row["filled_at"] = date
    row["filled_by"] = by or "light-experiment reconcile fill"
    recon["substantive"] = True  # 进入实质对账：delivered 门转逐行清零口径
    save_reconciliation(root, exec_id, recon)
    append_event(exec_dir(root, exec_id), "reconciliation_filled",
                 payload={"registry_run_id": registry_run_id,
                          "bias_warnings": len(rs["bias_warnings"])})
    return row


def check_reconciliation(root: Path, exec_id: str) -> list[str]:
    """逐行清零检查：以「全部清零」为标准逐个点名（pending 也算未清零）。
    delivered 门消费的是同一函数的门控子集（见 gates 口径）。"""
    pkg = load_package(root, exec_id)
    return reconciliation_problems(pkg, pending_blocks=True)


def export_card(root: Path, exec_id: str, *,
                out: Path | None = None, date: str | None = None) -> dict:
    """execution_card.json：给 Analysis 的结构化投影（草案 §2）。
    投影只汇总事实层材料与指针，不含 readout 三向判定。"""
    date = date or today()
    pkg = load_package(root, exec_id)
    execution = pkg["execution"]
    dref = execution.get("design_ref") or {}
    recon = pkg.get("reconciliation") or {}
    card = {
        "exec_id": exec_id,
        "exported_at": date,
        "design_ref": dref,
        "status": execution.get("status"),
        "budget_ledger": execution.get("budget_ledger"),
        "acceptance": ({"verdict": pkg["acceptance"].get("verdict"),
                        "targets": pkg["acceptance"].get("targets")}
                       if pkg.get("acceptance") else None),
        "runs": [{
            "run_id": r["run_id"],
            "design_run_id": r.get("design_run_id"),
            "attempt": r.get("attempt"),
            "status": r.get("status"),
            "exit_status": (r.get("conclusion") or {}).get("exit_status"),
            "identity_hash": (r.get("identity") or {}).get("identity_hash"),
            "voided_by": run_voided_by(r),
            "failure_ref": (r.get("conclusion") or {}).get("failure_ref"),
            "attempts_budget": (r.get("observation") or {}).get("attempts_budget"),
        } for r in sorted(pkg["runs"].values(), key=lambda x: x["run_id"])],
        "reconciliation": {
            "content_hash": recon.get("content_hash"),
            "rows": recon.get("rows") or [],
        },
        "deviations": [{
            "deviation_id": d.get("deviation_id"), "type": d.get("type"),
            "disposition": d.get("disposition"),
            "invalidated": (d.get("applied") or {}).get("invalidated"),
        } for d in pkg.get("deviations") or []],
        "failures": [{
            "failure_id": f.get("failure_id"), "run_id": f.get("run_id"),
            "mast_code": f.get("mast_code"),
            "failure_class": f.get("failure_class"),
            "reflux_target": f.get("reflux_target"),
            "reflux_status": f.get("reflux_status"),
        } for f in pkg.get("failures") or []],
    }
    out = out or (exec_dir(root, exec_id) / "execution_card.json")
    out.write_text(json.dumps(card, ensure_ascii=False, indent=2), encoding="utf-8")
    return card
