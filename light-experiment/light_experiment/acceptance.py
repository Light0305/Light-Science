"""基线复现验收子流程（E1，草案 §5，拍板 ③）。

- 验收表先行冻结：`init_acceptance` 从 brief 的基线条目（role ==
  baseline，或 --runs 显式指定）生成 baseline_acceptance.yaml——每
  个被复现的结论拆三层叶子（实现 / 执行 / 结果），二值判定、按对
  结论的重要性加权；叶子定义落 leaves_hash，生成后改表即被校验器
  以哈希不符检出（要改走偏离登记，不许原地改表）。
- 验收证据只认冷启动重跑：`record_leaf` 的每条判定必须带
  --evidence-run 指向一条冷启动重跑 run（run_started 事件锚
  cold_start=true、干净环境只凭提交物 + 单一入口重跑的产物登记）；
  执行期产物（无冷启动锚）冒充验收证据，在登记时即被拒绝。
- 闸门：加权通过分达阈值（brief/--threshold 声明，默认全叶通过）
  且全部叶子已判，verdict 才落 passed；包级 sanity → executing
  门消费此结论（见 gates）——验收未过不许开主清单。
- baseline_acceptance.md 为验收表的渲染视图（权威源为 .yaml）。
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from .events import append_event
from .gates import GateError
from .project import (
    exec_dir,
    load_acceptance,
    load_package,
    save_acceptance,
)
from .schema import (
    ACCEPTANCE_LAYERS,
    ACCEPTANCE_LAYER_WEIGHTS,
    ACCEPTANCE_VERDICTS,
    BASELINE_ROLE,
    DEFAULT_ACCEPTANCE_THRESHOLD,
    DEFAULT_RESULT_TOLERANCE_PCT,
    cold_start_ok,
)
from .util import component_hash, today

ACCEPTANCE_MD = "baseline_acceptance.md"


def baseline_targets(pkg: dict) -> list[str]:
    """brief 中的基线条目（role == baseline 的 design_run_id）。"""
    return [b.get("run_id") for b in pkg["execution"].get("brief_runs") or []
            if isinstance(b, dict) and b.get("role") == BASELINE_ROLE]


def _leaf_definitions(pkg: dict, targets: list[str]) -> list[dict]:
    lines = {l.get("run_id"): l for l in pkg["execution"].get("registry_lines") or []
             if isinstance(l, dict)}
    leaves: list[dict] = []
    for run_id in targets:
        line = lines.get(run_id) or {}
        metric = (line.get("primary_metric") or {}).get("name") or "主指标"
        readout = line.get("readout") or {}
        claims = {
            "implementation": f"条目 {run_id} 的实现按设计书落地"
                              "（代码/配置与冻结规格一致）",
            "execution": f"条目 {run_id} 照复现入口真实跑完（非自报、非跳步）",
            "result": f"条目 {run_id} 的{metric}读数与登记预期比对："
                      f"{(readout.get('positive') or {}).get('meaning', '达登记口径')}",
        }
        expected = line.get("expected")
        for layer in ACCEPTANCE_LAYERS:
            leaves.append({
                "leaf_id": f"{run_id}:{layer}",
                "run_id": run_id,
                "layer": layer,
                "claim": claims[layer],
                "weight": ACCEPTANCE_LAYER_WEIGHTS[layer],
                "verdict": None,
                "evidence_run": None,
                "evidence": [],
                "observed_value": None,
                "expected_value": expected if layer == "result" else None,
                "reported_variance": None,
                "deviation_pct": None,
                "deviation_abs": None,
                "note": "",
            })
    return leaves


def _definitions_hash(leaves: list[dict]) -> str:
    defs = [{k: leaf.get(k) for k in ("leaf_id", "run_id", "layer", "claim", "weight")}
            for leaf in leaves]
    return component_hash(defs)


def compute_verdict(acc: dict) -> str:
    leaves = acc.get("leaves") or []
    if any(leaf.get("verdict") is None for leaf in leaves):
        return "incomplete"
    total = sum(leaf.get("weight") or 0 for leaf in leaves)
    passed = sum(leaf.get("weight") or 0 for leaf in leaves
                 if leaf.get("verdict") == "pass")
    threshold = acc.get("threshold")
    threshold = threshold if isinstance(threshold, (int, float)) \
        else DEFAULT_ACCEPTANCE_THRESHOLD
    return "passed" if total and (passed / total) >= threshold else "failed"


def init_acceptance(root: Path, exec_id: str, *,
                    targets: tuple[str, ...] = (),
                    threshold: float = DEFAULT_ACCEPTANCE_THRESHOLD,
                    tolerance_pct: float = DEFAULT_RESULT_TOLERANCE_PCT,
                    by: str = "", date: str | None = None) -> dict:
    """生成并冻结验收表。targets 为空时取 brief 的 baseline 条目；
    两者皆空 → 无基线条目可验收，报错点名（不许生成空表冒充验收）。"""
    date = date or today()
    if load_acceptance(root, exec_id) is not None:
        raise GateError(["验收表已存在：验收表生成后冻结，改表走偏离登记"
                         "（deviation raise），不许重新生成覆盖"])
    pkg = load_package(root, exec_id)
    execution = pkg["execution"]
    if execution.get("status") == "delivered":
        raise GateError(["执行包已 delivered：验收表必须在开主清单前生成"])
    chosen = list(targets) or baseline_targets(pkg)
    if not chosen:
        raise ValueError("brief 中没有 role=baseline 的基线条目，也未用 "
                         "--runs 显式指定验收对象：无基线可验收")
    brief_ids = {b.get("run_id") for b in execution.get("brief_runs") or []
                 if isinstance(b, dict)}
    for t in chosen:
        if t not in brief_ids:
            raise ValueError(f"验收对象 {t} 不在 brief 运行清单内")
    leaves = _leaf_definitions(pkg, chosen)
    dref = execution.get("design_ref") or {}
    acc = {
        "exec_id": exec_id,
        "design_id": dref.get("design_id"),
        "content_hash": dref.get("content_hash"),
        "created": date,
        "created_by": by or "light-experiment acceptance init",
        "targets": chosen,
        "threshold": threshold,
        "tolerance_pct": tolerance_pct,
        "leaves_hash": _definitions_hash(leaves),
        "leaves": leaves,
        "verdict": "incomplete",
        "note": "验收表生成后冻结（leaves_hash 钉住叶子定义）；判定逐叶 "
                "record，证据只认冷启动重跑（拍板 ③）。",
    }
    save_acceptance(root, exec_id, acc)
    render_acceptance_md(root, exec_id)
    append_event(exec_dir(root, exec_id), "acceptance_initialized",
                 payload={"targets": chosen, "leaves": len(leaves),
                          "threshold": threshold})
    return acc


def _file_fingerprint(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"证据文件不存在：{path}")
    return {"name": path.name, "path": str(path),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def record_leaf(root: Path, exec_id: str, leaf_id: str, *, verdict: str,
                evidence_run: str, evidence_files: tuple[Path, ...] = (),
                observed_value: float | None = None,
                expected_value: float | None = None,
                reported_variance: float | None = None,
                note: str = "", by: str = "",
                date: str | None = None) -> dict:
    """逐叶登记判定 + 证据指针。证据 run 必须真实存在、属于该叶的
    条目、已终止，且带冷启动锚——执行期产物冒充验收证据在此被拒。"""
    date = date or today()
    if verdict not in ACCEPTANCE_VERDICTS:
        raise ValueError(f"叶判定非法：{verdict!r}（二值判定，须属 "
                         f"{list(ACCEPTANCE_VERDICTS)}）")
    acc = load_acceptance(root, exec_id)
    if acc is None:
        raise ValueError("验收表不存在：先 acceptance init 生成并冻结验收表")
    leaf = next((l for l in acc.get("leaves") or []
                 if l.get("leaf_id") == leaf_id), None)
    if leaf is None:
        raise ValueError(f"验收叶不存在：{leaf_id}")
    pkg = load_package(root, exec_id)
    run = pkg["runs"].get(evidence_run)
    if run is None:
        raise ValueError(f"证据 run 不存在：{evidence_run}"
                         "（验收证据必须指向冷启动重跑产物登记）")
    if run.get("design_run_id") != leaf.get("run_id"):
        raise ValueError(f"证据 run {evidence_run} 是条目 "
                         f"{run.get('design_run_id')} 的尝试，不是本叶条目 "
                         f"{leaf.get('run_id')}（张冠李戴不作数）")
    if run.get("status") not in ("completed", "failed", "deviated", "reconciled"):
        raise ValueError(f"证据 run {evidence_run} 尚未终止"
                         f"（status={run.get('status')}）：跑完的重跑才算产物")
    if not cold_start_ok(pkg, evidence_run):
        raise ValueError(f"证据 run {evidence_run} 无冷启动标记：执行期产物"
                         "不作验收证据——验收只认干净环境只凭提交物 + "
                         "单一入口的冷启动重跑（拍板 ③ 硬要求）")
    leaf["verdict"] = verdict
    leaf["evidence_run"] = evidence_run
    leaf["evidence"] = [_file_fingerprint(p) for p in evidence_files]
    if observed_value is not None:
        leaf["observed_value"] = observed_value
    if expected_value is not None:
        leaf["expected_value"] = expected_value
    if reported_variance is not None:
        leaf["reported_variance"] = reported_variance
    if leaf.get("observed_value") is not None and leaf.get("expected_value"):
        obs, exp = leaf["observed_value"], leaf["expected_value"]
        leaf["deviation_abs"] = abs(obs - exp)
        leaf["deviation_pct"] = round(abs(obs - exp) / abs(exp) * 100, 4)
    if note:
        leaf["note"] = note
    leaf["recorded_by"] = by or "light-experiment acceptance record"
    leaf["recorded_at"] = date
    acc["verdict"] = compute_verdict(acc)
    save_acceptance(root, exec_id, acc)
    render_acceptance_md(root, exec_id)
    append_event(exec_dir(root, exec_id), "acceptance_recorded",
                 run_id=evidence_run,
                 payload={"leaf_id": leaf_id, "verdict": verdict,
                          "package_verdict": acc["verdict"]})
    return acc


def render_acceptance_md(root: Path, exec_id: str) -> Path:
    """把验收表渲染成 baseline_acceptance.md（视图；权威源为 .yaml）。"""
    acc = load_acceptance(root, exec_id)
    if acc is None:
        raise FileNotFoundError("验收表不存在（baseline_acceptance.yaml）")
    L = [f"# 基线复现验收表 — {exec_id}", "",
         f"> 权威源为 baseline_acceptance.yaml（本文件是渲染视图）。"
         f"结论：**{acc.get('verdict')}**（阈值 {acc.get('threshold')}，"
         f"结果层容差 {acc.get('tolerance_pct')}%）；叶子定义哈希 "
         f"`{(acc.get('leaves_hash') or '')[:16]}…`（表已冻结）。", "",
         "| 叶子 | 层 | 权重 | 判定 | 证据 run（冷启动） | 偏差 |",
         "|---|---|---|---|---|---|"]
    for leaf in acc.get("leaves") or []:
        dev = leaf.get("deviation_pct")
        L.append(f"| {leaf.get('leaf_id')} | {leaf.get('layer')} "
                 f"| {leaf.get('weight')} | {leaf.get('verdict') or '（未判）'} "
                 f"| {leaf.get('evidence_run') or '—'} "
                 f"| {dev if dev is not None else '—'} |")
    L.append("")
    out = exec_dir(root, exec_id) / ACCEPTANCE_MD
    out.write_text("\n".join(L), encoding="utf-8")
    return out
