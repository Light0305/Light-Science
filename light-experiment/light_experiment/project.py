"""项目骨架、执行包文件操作与 E0 承接（intake）。

目录形态：

    <project>/
    ├── project.yaml
    ├── index.yaml / index.md
    ├── experiment-stage/
    │   └── intake_log.md          # 每次承接的结论与打回清单（只增留痕）
    └── executions/<exec_id>/
        ├── execution.yaml         # 登记头（权威）
        ├── runs/<run_id>/run.yaml # 逐 run 记录（权威）
        ├── events.jsonl           # 轨迹事件日志（只增）
        ├── reconciliation.yaml    # 对账表占位（一期）
        ├── artifacts/             # 内容寻址产物池（产物登记见 run.yaml）
        └── EXECUTION_REPORT.md    # 渲染报告（render 生成）

exec_id = <design_id>-b<批次号>（同设计第 n 次承接建第 n 个执行包，
历史批次不覆盖）。run_id = <brief 条目 id>-a<attempt 号>（草案 §2.1）。

承接纪律（草案 §4）：只消费 frozen 设计；四件套哈希/行对应不上 →
逐条列缺口打回（执行包停在 intake、缺口落 intake_report + intake_log），
不许执行端临场补设计。打回不删往返记录。
"""

from __future__ import annotations

import copy
import hashlib
import json
from collections import Counter
from pathlib import Path

from .events import append_event, read_events
from .gates import BUDGET_KEYS, GateError
from .schema import (
    EXIT_STATUSES,
    build_birth_certificate,
    compute_identity_hash,
    compute_params_hash,
    derive_seed,
    empty_execution,
    empty_run,
    identity_minimum_errors,
)
from .util import load_structured, read_yaml, slugify, today, utcnow, write_yaml

EXECUTIONS_DIRNAME = "executions"
STAGE_DIRNAME = "experiment-stage"
RECONCILIATION_FILENAME = "reconciliation.yaml"

EXPORT_FILES = ("experiment_brief.md", "design_card.json",
                "expected_registry.jsonl", "reproducibility.md")


class IntakeError(Exception):
    """承接根本无法进行（交接件缺失到无法识别设计）。gaps 逐条列明。"""

    def __init__(self, gaps: list[str]):
        self.gaps = gaps
        super().__init__("；".join(gaps))


def project_paths(root: Path) -> dict[str, Path]:
    return {
        "root": root,
        "project_yaml": root / "project.yaml",
        "index_yaml": root / "index.yaml",
        "index_md": root / "index.md",
        "stage": root / STAGE_DIRNAME,
        "intake_log": root / STAGE_DIRNAME / "intake_log.md",
        "executions": root / EXECUTIONS_DIRNAME,
    }


def init_project(root: Path, direction: str) -> Path:
    """建项目骨架。已存在 project.yaml 时拒绝覆盖。"""
    p = project_paths(root)
    if p["project_yaml"].exists():
        raise FileExistsError(f"项目已存在：{p['project_yaml']}")
    p["stage"].mkdir(parents=True, exist_ok=True)
    p["executions"].mkdir(parents=True, exist_ok=True)
    write_yaml(p["project_yaml"], {
        "project": direction,
        "project_id": f"{slugify(direction, fallback='experiment')}_"
                      f"{hashlib.sha256(direction.strip().lower().encode()).hexdigest()[:6]}",
        "created": today(),
        "tool": "light-experiment",
        "version": "1.0.0",
    })
    p["intake_log"].write_text(
        f"# 承接与打回记录 — {direction}\n\n"
        "每次消费 Design 交接四件套的结论逐条留痕（齐全/打回缺口），不许删除。\n",
        encoding="utf-8")
    refresh_index(root)
    return root


# ---------- 路径与读写 ----------

def exec_dir(root: Path, exec_id: str) -> Path:
    return project_paths(root)["executions"] / exec_id


def load_execution(root: Path, exec_id: str) -> dict:
    path = exec_dir(root, exec_id) / "execution.yaml"
    if not path.exists():
        raise FileNotFoundError(f"执行包不存在：{exec_id}（找 {path}）")
    return read_yaml(path)


def save_execution(root: Path, execution: dict) -> Path:
    d = exec_dir(root, execution["exec_id"])
    d.mkdir(parents=True, exist_ok=True)
    write_yaml(d / "execution.yaml", execution)
    return d


def run_dir(root: Path, exec_id: str, run_id: str) -> Path:
    return exec_dir(root, exec_id) / "runs" / run_id


def load_run(root: Path, exec_id: str, run_id: str) -> dict:
    path = run_dir(root, exec_id, run_id) / "run.yaml"
    if not path.exists():
        raise FileNotFoundError(f"run 不存在：{run_id}（找 {path}）")
    return read_yaml(path)


def save_run(root: Path, exec_id: str, run: dict) -> Path:
    d = run_dir(root, exec_id, run["run_id"])
    d.mkdir(parents=True, exist_ok=True)
    write_yaml(d / "run.yaml", run)
    return d


def list_executions(root: Path) -> list[dict]:
    base = project_paths(root)["executions"]
    out = []
    if base.exists():
        for d in sorted(base.iterdir()):
            y = d / "execution.yaml"
            if d.is_dir() and y.exists():
                out.append(read_yaml(y))
    return out


def list_runs(root: Path, exec_id: str) -> list[dict]:
    base = exec_dir(root, exec_id) / "runs"
    out = []
    if base.exists():
        for d in sorted(base.iterdir()):
            y = d / "run.yaml"
            if d.is_dir() and y.exists():
                out.append(read_yaml(y))
    return out


def load_reconciliation(root: Path, exec_id: str) -> dict | None:
    path = exec_dir(root, exec_id) / RECONCILIATION_FILENAME
    if not path.exists():
        return None
    return read_yaml(path)


def save_reconciliation(root: Path, exec_id: str, recon: dict) -> None:
    write_yaml(exec_dir(root, exec_id) / RECONCILIATION_FILENAME, recon)


ACCEPTANCE_FILENAME = "baseline_acceptance.yaml"
DEVIATIONS_FILENAME = "deviations.jsonl"
FAILURES_FILENAME = "failures.jsonl"
REFLUX_DIRNAME = "reflux"


def load_acceptance(root: Path, exec_id: str) -> dict | None:
    path = exec_dir(root, exec_id) / ACCEPTANCE_FILENAME
    if not path.exists():
        return None
    return read_yaml(path)


def save_acceptance(root: Path, exec_id: str, acc: dict) -> None:
    write_yaml(exec_dir(root, exec_id) / ACCEPTANCE_FILENAME, acc)


def load_jsonl_entries(root: Path, exec_id: str, filename: str) -> list[dict]:
    """读只增 JSONL 登记（偏离/失败/回流）。文件不存在 → 空表；
    坏行抛 ValueError（只增账损坏不许静默吞）。"""
    path = exec_dir(root, exec_id) / filename
    if not path.exists():
        return []
    from .util import read_jsonl
    return read_jsonl(path)


def append_jsonl_entry(root: Path, exec_id: str, filename: str,
                       entry: dict) -> dict:
    """向只增 JSONL 登记追加一条（本模块只提供 append，没有改写入口）。"""
    path = exec_dir(root, exec_id) / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
    return entry


def reflux_dir(root: Path, exec_id: str) -> Path:
    return exec_dir(root, exec_id) / REFLUX_DIRNAME


def load_reflux(root: Path, exec_id: str) -> dict:
    """回流条目（reflux/ 目录）：retry_queue / design_inbox 两本只增账
    + idea dossier 草稿文件清单。目录不存在 → 全空。"""
    d = reflux_dir(root, exec_id)
    out = {"retry_queue": [], "design_inbox": [], "idea_dossiers": []}
    if not d.exists():
        return out
    from .util import read_jsonl
    for key, name in (("retry_queue", "retry_queue.jsonl"),
                      ("design_inbox", "design_inbox.jsonl")):
        p = d / name
        if p.exists():
            out[key] = read_jsonl(p)
    dossiers = d / "idea_dossiers"
    if dossiers.exists():
        out["idea_dossiers"] = sorted(p.name for p in dossiers.iterdir()
                                      if p.is_file())
    return out


def load_package(root: Path, exec_id: str) -> dict:
    """组装整包 dict 供校验器/状态机消费（见 schema.validate_package）。
    二期产物（验收表 / 偏离 / 失败 / 回流）折叠后一并入包；文件不在场
    时给空值——「尚未进入该子流程」与「进入了但不合法」分开表达。"""
    from .deviations import fold_deviations
    from .failures import fold_failures
    execution = load_execution(root, exec_id)
    runs = {r["run_id"]: r for r in list_runs(root, exec_id)}
    events, event_errors = read_events(exec_dir(root, exec_id))
    d = exec_dir(root, exec_id)
    return {
        "execution": execution,
        "runs": runs,
        "events": events,
        "event_errors": event_errors,
        "reconciliation": load_reconciliation(root, exec_id),
        "acceptance": load_acceptance(root, exec_id),
        "deviations": fold_deviations(load_jsonl_entries(root, exec_id,
                                                         DEVIATIONS_FILENAME)),
        "deviations_present": (d / DEVIATIONS_FILENAME).exists(),
        "failures": fold_failures(load_jsonl_entries(root, exec_id,
                                                     FAILURES_FILENAME)),
        "failures_present": (d / FAILURES_FILENAME).exists(),
        "reflux": load_reflux(root, exec_id),
    }


def _transition(obj: dict, to: str, by: str, date: str, note: str = "") -> None:
    obj.setdefault("status_history", []).append(
        {"from": obj.get("status"), "to": to, "date": date,
         "by": by or "light-experiment", "note": note})
    obj["status"] = to
    obj["updated"] = date


# ---------- E0 承接（intake） ----------

def current_design_hash(card: dict) -> str | None:
    """交接件的现行内容哈希：有 amendment 取链尾 new_hash，否则冻结哈希
    （与 Light-Design current_frozen_hash 同口径）。"""
    fr = card.get("freeze") or {}
    amds = fr.get("amendments") or []
    if amds:
        return amds[-1].get("new_hash")
    return fr.get("content_hash")


def _next_batch(root: Path, design_id: str) -> int:
    n = sum(1 for e in list_executions(root)
            if (e.get("design_ref") or {}).get("design_id") == design_id)
    return n + 1


def intake(root: Path, export_dir: Path, *, date: str | None = None) -> tuple[dict, list[str]]:
    """消费 Design 交接四件套建执行包。返回 (execution, gaps)。

    校验顺序（草案 §4 的一期子集）：四件套齐全 → 设计 frozen →
    brief/reproducibility 所钉哈希与 design_card 现行哈希一致 →
    registry 逐行 design_id/content_hash 对齐 → registry 行与运行
    清单一对应 → 每行判读三向与主指标在场。
    有缺口：执行包照样落盘（status=intake、缺口进 intake_report 与
    intake_log），但不建 run、不生成对账表，advance 到 sanity 被门拦。
    design_card 缺失/不可解析到无法识别设计时抛 IntakeError（无从打回）。
    """
    date = date or today()
    gaps: list[str] = []
    paths = {name: export_dir / name for name in EXPORT_FILES}
    for name, p in paths.items():
        if not p.exists():
            gaps.append(f"交接件缺失：{name} 不存在于 {export_dir}")

    card: dict | None = None
    if paths["design_card.json"].exists():
        try:
            card = json.loads(paths["design_card.json"].read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise IntakeError(gaps + [f"design_card.json 不是合法 JSON：{e}"]) from e
    if card is None:
        raise IntakeError(gaps or ["design_card.json 缺失，无法识别设计"])
    design_id = card.get("design_id")
    if not design_id:
        raise IntakeError(gaps + ["design_card.json 缺 design_id，无法识别设计"])

    if card.get("status") != "frozen":
        gaps.append(f"设计未冻结（status={card.get('status')}）："
                    "只消费 frozen 设计，reviewed/draft 不许开跑")
    cur_hash = current_design_hash(card)
    frozen_hash = (card.get("freeze") or {}).get("content_hash")
    if not cur_hash:
        gaps.append("design_card 缺冻结哈希（freeze.content_hash），无从核对版本")

    for name in ("experiment_brief.md", "reproducibility.md"):
        if paths[name].exists() and cur_hash and \
                cur_hash not in paths[name].read_text(encoding="utf-8"):
            gaps.append(f"{name} 未钉住现行内容哈希（与 design_card 不一致，"
                        "疑似不同批次的交接件混装）")

    registry_lines: list[dict] = []
    if paths["expected_registry.jsonl"].exists():
        for i, line in enumerate(
                paths["expected_registry.jsonl"].read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                registry_lines.append(json.loads(line))
            except json.JSONDecodeError as e:
                gaps.append(f"expected_registry.jsonl 第 {i} 行不是合法 JSON：{e}")
    for line in registry_lines:
        lid = line.get("run_id")
        if line.get("design_id") != design_id:
            gaps.append(f"登记行 {lid} 的 design_id 与 design_card 不一致")
        if cur_hash and line.get("content_hash") != cur_hash:
            gaps.append(f"登记行 {lid} 的 content_hash 与现行冻结哈希不一致")
        readout = line.get("readout") or {}
        if not all(k in readout for k in ("positive", "negative", "null")):
            gaps.append(f"登记行 {lid} 判读三向不齐（positive/negative/null）")
        if not (line.get("primary_metric") or {}).get("name"):
            gaps.append(f"登记行 {lid} 缺主指标名")

    brief_runs = [r for r in (card.get("contract") or {}).get("runs") or []
                  if isinstance(r, dict)]
    brief_ids = [r.get("run_id") for r in brief_runs]
    reg_ids = [line.get("run_id") for line in registry_lines]
    if paths["expected_registry.jsonl"].exists() and sorted(reg_ids) != sorted(brief_ids):
        gaps.append(f"预期登记行与 brief 运行清单不一一对应："
                    f"登记 {sorted(reg_ids)} ≠ 清单 {sorted(brief_ids)}")

    exec_id = f"{design_id}-b{_next_batch(root, design_id)}"
    execution = empty_execution(exec_id, date)
    execution["design_ref"] = {
        "design_id": design_id,
        "content_hash": cur_hash or "",
        "frozen_content_hash": frozen_hash or "",
        "amendments": len((card.get("freeze") or {}).get("amendments") or []),
        "export_dir": str(export_dir),
    }
    res = card.get("resources") or {}
    execution["budget_ledger"]["design_budget"] = res.get("budget") or {}
    execution["budget_ledger"]["circuit_breakers"] = res.get("circuit_breakers") or []
    execution["intake_report"] = {
        "checked_at": date,
        "source_dir": str(export_dir),
        "gaps": gaps,
        "registry_run_ids": reg_ids,
    }
    execution["brief_runs"] = brief_runs
    execution["registry_lines"] = registry_lines

    d = exec_dir(root, exec_id)
    (d / "runs").mkdir(parents=True, exist_ok=True)
    (d / "artifacts").mkdir(parents=True, exist_ok=True)
    (d / "events.jsonl").write_text("", encoding="utf-8")
    save_execution(root, execution)
    append_event(d, "intake_done" if not gaps else "intake_rejected",
                 payload={"design_id": design_id, "content_hash": cur_hash,
                          "gaps": gaps})

    log = project_paths(root)["intake_log"]
    verdict = "承接齐全" if not gaps else f"打回 {len(gaps)} 项"
    with open(log, "a", encoding="utf-8") as f:
        f.write(f"\n## {date} — {exec_id}（design: {design_id}）\n\n"
                f"- 来源：{export_dir}\n- 结论：{verdict}\n")
        for g in gaps:
            f.write(f"  - 缺口：{g}\n")

    if not gaps:
        line_by_id = {line.get("run_id"): line for line in registry_lines}
        run_ids_by_design: dict[str, list[str]] = {}
        for brow in brief_runs:
            run = _create_run(root, execution, brow,
                              line_by_id.get(brow.get("run_id"), {}), date)
            run_ids_by_design.setdefault(brow.get("run_id"), []).append(run["run_id"])
        save_reconciliation(root, exec_id, {
            "design_id": design_id,
            "content_hash": cur_hash,
            "generated_at": date,
            "note": "一期占位对账表：只做行数与登记对齐，实质回填在二期",
            "rows": [{"registry_run_id": line.get("run_id"),
                      "run_ids": run_ids_by_design.get(line.get("run_id"), []),
                      "status": "pending",
                      "readout_actual": None, "layers": None,
                      "deviations": [], "evidence": []}
                     for line in registry_lines],
        })
    refresh_index(root)
    return execution, gaps


# ---------- run 生命周期 ----------

def _apply_spec(run: dict, spec: dict) -> None:
    """把 run 规格（--spec 文件内容）填进身份区（开跑前可改，开跑即冻结）。"""
    ident = run["identity"]
    for key in ("config", "params", "data_version", "environment"):
        if key in spec:
            ident[key] = spec[key]
    if isinstance(spec.get("code_snapshot"), dict):
        ident["code_snapshot"].update(spec["code_snapshot"])
    if spec.get("root_seed") is not None:
        ident["seeds"]["root_seed"] = spec["root_seed"]
    if spec.get("intervention_checks") is not None:
        ident["intervention_checks"] = spec["intervention_checks"]
    if spec.get("cold_start") is not None:
        # 冷启动重跑标记（E1 验收证据的真伪锚）：声明本 run 是在干净
        # 环境只凭提交物 + 单一入口冷启动跑的——开跑时钉进 run_started
        # 事件，事后回填冒充会被校验器以锚不一致检出（拍板 ③）
        ident["cold_start"] = bool(spec["cold_start"])


def _create_run(root: Path, execution: dict, brief_row: dict,
                registry_line: dict, date: str, *, spec: dict | None = None,
                retry_of: str | None = None,
                origin: dict | None = None) -> dict:
    design_run_id = brief_row.get("run_id")
    existing = [r for r in list_runs(root, execution["exec_id"])
                if r.get("design_run_id") == design_run_id]
    attempt = len(existing) + 1
    run_id = f"{design_run_id}-a{attempt}"
    run = empty_run(run_id, design_run_id, attempt, execution["design_ref"],
                    copy.deepcopy(brief_row), copy.deepcopy(registry_line), date)
    if origin is not None:
        oident = origin.get("identity") or {}
        for key in ("config", "params", "code_snapshot", "data_version", "environment"):
            run["identity"][key] = copy.deepcopy(oident.get(key))
        run["identity"]["seeds"]["root_seed"] = \
            (oident.get("seeds") or {}).get("root_seed")
        lineage = run["identity"]["lineage"]
        lineage["origin_run"] = retry_of
        lineage["retry_of"] = retry_of
        if spec is None and oident.get("identity_hash"):
            lineage["reused_segments"] = [{
                "segment": "identity_components",
                "from_run": retry_of,
                "identity_hash": oident["identity_hash"],
            }]
    if spec is not None:
        _apply_spec(run, spec)
    save_run(root, execution["exec_id"], run)
    append_event(exec_dir(root, execution["exec_id"]), "run_created",
                 run_id=run_id,
                 payload={"design_run_id": design_run_id, "attempt": attempt,
                          "retry_of": retry_of})
    return run


def new_run(root: Path, exec_id: str, design_run_id: str, *,
            spec: dict | None = None, retry_of: str | None = None,
            date: str | None = None) -> dict:
    """为 brief 条目新建一次尝试（attempt 自增）。--retry-of 指向已终止
    的旧尝试：新 run 独立成号、血缘指回（拍板 ②），身份成分默认继承
    旧 run（spec 给了则以 spec 为准）。"""
    date = date or today()
    execution = load_execution(root, exec_id)
    gaps = (execution.get("intake_report") or {}).get("gaps") or []
    if gaps:
        raise ValueError(f"承接未清零（{len(gaps)} 项缺口），不许建 run——先打回解决")
    brow = next((r for r in execution.get("brief_runs") or []
                 if r.get("run_id") == design_run_id), None)
    if brow is None:
        raise ValueError(f"brief 运行清单里没有条目 {design_run_id!r}"
                         "（执行端只照单建 run，不许清单外自创）")
    line = next((l for l in execution.get("registry_lines") or []
                 if l.get("run_id") == design_run_id), {})
    origin = None
    if retry_of is not None:
        origin = load_run(root, exec_id, retry_of)
        if origin.get("design_run_id") != design_run_id:
            raise ValueError(f"retry 来源 {retry_of} 不是条目 {design_run_id} 的尝试")
        if origin.get("status") not in ("completed", "failed", "deviated"):
            raise ValueError(f"retry 来源 {retry_of} 尚未终止"
                             f"（status={origin.get('status')}）："
                             "恢复=新尝试成 run，只许接已终止的尝试")
    run = _create_run(root, execution, brow, line, date,
                      spec=spec, retry_of=retry_of, origin=origin)
    recon = load_reconciliation(root, exec_id)
    if recon is not None:
        for row in recon.get("rows") or []:
            if row.get("registry_run_id") == design_run_id:
                row.setdefault("run_ids", []).append(run["run_id"])
        save_reconciliation(root, exec_id, recon)
    return run


def start_run(root: Path, exec_id: str, run_id: str, *,
              spec: dict | None = None, by: str = "",
              date: str | None = None) -> dict:
    """planned → running：身份下限全过才许开跑；开跑即冻结身份哈希、
    params 哈希与出生证明，并把哈希钉进 run_started 事件作锚。"""
    date = date or today()
    run = load_run(root, exec_id, run_id)
    if run.get("status") != "planned":
        raise GateError([f"run {run_id} 状态为 {run.get('status')}，只有 planned 可开跑"])
    if spec is not None:
        _apply_spec(run, spec)
    errs = identity_minimum_errors(run)
    if errs:
        raise GateError(errs)
    ident = run["identity"]
    ident["identity_hash"] = compute_identity_hash(ident)
    ident["params_hash"] = compute_params_hash(ident.get("params"))
    ident["birth_certificate"] = build_birth_certificate(ident, utcnow())
    seeds = ident["seeds"]
    seeds["derived_seed"] = derive_seed(seeds["root_seed"], run_id)
    run["observation"]["timeline"]["started_at"] = utcnow()
    run["observation"]["attempts_budget"]["attempts_used"] += 1
    _transition(run, "running", by, date, "开跑（身份哈希与出生证明已冻结）")
    save_run(root, exec_id, run)
    d = exec_dir(root, exec_id)
    append_event(d, "attempt_started", run_id=run_id,
                 payload={"attempt": run.get("attempt")})
    append_event(d, "run_started", run_id=run_id,
                 payload={"identity_hash": ident["identity_hash"],
                          "params_hash": ident["params_hash"],
                          "cold_start": bool(ident.get("cold_start"))})
    return run


def _file_fingerprint(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"登记文件不存在：{path}")
    return {"name": path.name, "path": str(path),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def finish_run(root: Path, exec_id: str, run_id: str, *, exit_status: str,
               metrics_file: Path | None = None,
               salvage_files: tuple[Path, ...] = (),
               salvage_note: str = "", no_salvage: bool = False,
               failure_ref: str | None = None, mark_deviated: bool = False,
               wall_clock_s: float = 0, gpu_hours: float = 0,
               api_cost: float = 0, by: str = "",
               date: str | None = None) -> dict:
    """running → completed / failed / deviated：落 exit_status（终止分类
    词表）、指标文件登记、抢救产物登记、预算入账。失败终止必须有抢救
    产物或显式「无可抢救」声明（约束 4）。"""
    date = date or today()
    if exit_status not in EXIT_STATUSES:
        raise ValueError(f"exit_status={exit_status!r} 不在终止分类词表内"
                         f"（须属 {list(EXIT_STATUSES)}；自由文本不许落字，约束 4）")
    run = load_run(root, exec_id, run_id)
    if run.get("status") != "running":
        raise GateError([f"run {run_id} 状态为 {run.get('status')}，只有 running 可终止"])
    target = "deviated" if mark_deviated else (
        "completed" if exit_status == "completed" else "failed")
    conc = run["conclusion"]
    salvage = [_file_fingerprint(p) for p in salvage_files]
    if target == "failed" and not salvage and not salvage_note and not no_salvage:
        raise GateError(["失败终止必须登记抢救产物（--salvage）或显式声明"
                         "无可抢救（--no-salvage / --salvage-note）——"
                         "失败先抢救留产物，只留一句报错不合格（约束 4）"])
    if no_salvage and not salvage_note:
        salvage_note = "无可抢救产物（--no-salvage 显式声明）"
    conc["exit_status"] = exit_status
    conc["failure_ref"] = failure_ref
    conc["salvage"] = salvage
    conc["salvage_note"] = salvage_note
    for entry in salvage:
        run["observation"]["artifacts"].append({**entry, "kind": "salvage"})
    if metrics_file is not None:
        run["observation"]["metrics_ref"] = _file_fingerprint(metrics_file)
    obs = run["observation"]
    obs["timeline"]["ended_at"] = utcnow()
    spent = {"wall_clock_s": wall_clock_s, "gpu_hours": gpu_hours, "api_cost": api_cost}
    for k in BUDGET_KEYS:
        obs["attempts_budget"][k] = (obs["attempts_budget"].get(k) or 0) + spent[k]
    _transition(run, target, by, date, f"终止：{exit_status}")
    save_run(root, exec_id, run)
    execution = load_execution(root, exec_id)
    ledger_spent = execution["budget_ledger"]["spent"]
    for k in BUDGET_KEYS:
        ledger_spent[k] = (ledger_spent.get(k) or 0) + spent[k]
    execution["updated"] = date
    save_execution(root, execution)
    append_event(exec_dir(root, exec_id), "run_finished", run_id=run_id,
                 payload={"exit_status": exit_status, "status": target,
                          "budget": spent})
    return run


# ---------- 索引 ----------

def refresh_index(root: Path) -> None:
    p = project_paths(root)
    executions = list_executions(root)
    counts = Counter(e.get("status") for e in executions)
    entries = [{
        "exec_id": e["exec_id"],
        "design_id": (e.get("design_ref") or {}).get("design_id"),
        "status": e.get("status"),
        "path": f"{EXECUTIONS_DIRNAME}/{e['exec_id']}/",
        "updated": e.get("updated"),
    } for e in executions]
    write_yaml(p["index_yaml"], {
        "generated": today(),
        "total": len(executions),
        "status_counts": dict(counts),
        "executions": entries,
    })
    lines = ["# 项目索引（自动生成，勿手改）", ""]
    lines.append(f"总执行包数：{len(executions)}")
    if counts:
        lines.append("状态分布：" + "、".join(f"{s} × {n}" for s, n in counts.items()))
    lines.append("")
    lines.append("| exec_id | 状态 | 承接 design_id |")
    lines.append("|---|---|---|")
    for e in entries:
        lines.append(f"| {e['exec_id']} | {e['status']} | {e['design_id']} |")
    lines.append("")
    p["index_md"].write_text("\n".join(lines), encoding="utf-8")
