"""失败分类与回流（E5，草案 §2.4 / §6，拍板 ⑥）。

双层分类：exit_status（怎么停的，一期已有）→ mast_code（根因，
MAST 14 模式执行域转译词表，见 schema.MAST_CODES）→ failure_class
（回流去向，IVE 二分类，规则与 Idea 杀卡同构：fundamental 须
root_cause + boundary_conditions，implementation 须 retry_guidance）。

分类落定自动生成回流条目（reflux/）：implementation → retry_queue
（留本技能重试队列）；fundamental → design_inbox（回 Design 待
处理）；指向想法本体的（--idea-bound）另附 idea_dossier_draft.md
草稿（经 Design 中转回 Idea，本技能不直连改卡）。回流条目状态
pending / sent / resolved 由 reflux update 跟踪，决策仍归下游与
用户——工具只生成条目，不替下游做决定（拍板 ⑥）。

失败预算制（草案 §6）：同签名（mast_code + root_cause）最多
2 次补丁 + 2 次干净重写；分类时若本次使计数超限，记录落
budget_exceeded 并发 budget_event 报警，校验器同步检出——停下
报告「计划或环境错了」，不许换个姿势继续烧。

failures.jsonl 只增：classify 落一条 kind=failure；人工抽验走
kind=failure_review 追加（classification_review 字段），折叠后呈现。
"""

from __future__ import annotations

import json
from pathlib import Path

from .events import append_event
from .gates import GateError
from .project import (
    FAILURES_FILENAME,
    append_jsonl_entry,
    exec_dir,
    load_package,
    load_run,
    reflux_dir,
    save_run,
)
from .schema import (
    ATTEMPT_KINDS,
    FAILURE_CLASSES,
    FAILURE_SIGNATURE_BUDGET,
    MAST_CODES,
    _nonempty_str,
)
from .util import read_jsonl, today, utcnow


def fold_failures(entries: list[dict]) -> list[dict]:
    """failures.jsonl 折叠：failure 定型主体；failure_review 追加
    更新 classification_review（抽验全量留痕于 reviews，现行值取
    最后一条）；reflux_status 追加更新回流状态呈现（取最后一条）。"""
    folded: dict[str, dict] = {}
    order: list[str] = []
    for e in entries:
        if not isinstance(e, dict):
            continue
        fid = e.get("failure_id")
        if not fid:
            continue
        if e.get("kind") == "failure":
            if fid not in folded:
                order.append(fid)
                folded[fid] = {**e, "reviews": []}
        elif e.get("kind") == "failure_review":
            rec = folded.get(fid)
            if rec is not None:
                review = {"reviewer": e.get("reviewer"),
                          "agrees": e.get("agrees"), "date": e.get("date"),
                          "note": e.get("note", "")}
                rec["reviews"].append(review)
                rec["classification_review"] = review
        elif e.get("kind") == "reflux_status":
            rec = folded.get(fid)
            if rec is not None:
                rec["reflux_status"] = e.get("reflux_status")
    return [folded[f] for f in order]


def _next_id(existing: list, prefix: str) -> str:
    return f"{prefix}-{len(existing) + 1:04d}"


def signature_of(mast_code: str, root_cause: str) -> str:
    return f"{mast_code}|{(root_cause or '').strip()}"


def classify_failure(root: Path, exec_id: str, *, run_id: str, mast_code: str,
                     failure_class: str, root_cause: str = "",
                     boundary_conditions: str = "", retry_guidance: str = "",
                     diagnosis: str = "", attempt_kind: str | None = None,
                     idea_bound: bool = False, reviewer: str = "",
                     review_agrees: bool | None = None, by: str = "",
                     date: str | None = None) -> dict:
    """给一条 failed run 落双层分类并自动生成回流条目。"""
    date = date or today()
    if mast_code not in MAST_CODES:
        raise ValueError(f"mast_code 不在 MAST 转译词表内：{mast_code!r}"
                         "（14 模式见 schema.MAST_CODES；只写「执行失败」视为未分类）")
    if failure_class not in FAILURE_CLASSES:
        raise ValueError(f"failure_class 非法：{failure_class!r}"
                         f"（须属 {list(FAILURE_CLASSES)}）")
    if failure_class == "fundamental":
        if not _nonempty_str(root_cause):
            raise ValueError("fundamental 必须附 root_cause（根因）——与 Idea 杀卡同规则")
        if not _nonempty_str(boundary_conditions):
            raise ValueError("fundamental 必须附 boundary_conditions"
                             "（该结论在什么边界内成立）——与 Idea 杀卡同规则")
    if failure_class == "implementation" and not _nonempty_str(retry_guidance):
        raise ValueError("implementation 必须附 retry_guidance（重试指引）"
                         "——与 Idea 杀卡同规则")
    if attempt_kind is not None and attempt_kind not in ATTEMPT_KINDS:
        raise ValueError(f"attempt_kind 非法：{attempt_kind!r}"
                         f"（须属 {list(ATTEMPT_KINDS)} 或不给）")
    pkg = load_package(root, exec_id)
    run = pkg["runs"].get(run_id)
    if run is None:
        raise ValueError(f"run 不存在：{run_id}")
    if run.get("status") == "reconciled":
        raise GateError([f"run {run_id} 已 reconciled（终态）：分类须在对账清零前落定"])
    conc = run.get("conclusion") or {}
    if run.get("status") != "failed" or conc.get("exit_status") in (None, "completed"):
        raise GateError([f"run {run_id} 不是失败终止（status={run.get('status')}，"
                         f"exit_status={conc.get('exit_status')!r}）：无失败可分类"])
    if conc.get("failure_ref"):
        raise GateError([f"run {run_id} 已有失败分类 {conc['failure_ref']}："
                         "重复分类不许（纠正走 failure review 留痕）"])
    failures = pkg["failures"]
    failure_id = _next_id(failures, "F")
    reflux_target = "experiment" if failure_class == "implementation" else \
        ("idea" if idea_bound else "design")

    # 失败预算制：同签名计数（含本次）超限 → 报警
    sig = signature_of(mast_code, root_cause)
    budget_exceeded = False
    if attempt_kind in ATTEMPT_KINDS:
        same = [f for f in failures
                if signature_of(f.get("mast_code", ""), f.get("root_cause", "")) == sig
                and f.get("attempt_kind") == attempt_kind]
        if len(same) + 1 > FAILURE_SIGNATURE_BUDGET[attempt_kind]:
            budget_exceeded = True

    record = {
        "kind": "failure",
        "failure_id": failure_id,
        "run_id": run_id,
        "date": date,
        "classified_at": utcnow(),
        "exit_status": conc.get("exit_status"),
        "mast_code": mast_code,
        "mast_name": MAST_CODES[mast_code]["name"],
        "failure_class": failure_class,
        "root_cause": root_cause,
        "boundary_conditions": boundary_conditions,
        "retry_guidance": retry_guidance,
        "diagnosis": diagnosis,
        "attempt_kind": attempt_kind,
        "signature": sig,
        "budget_exceeded": budget_exceeded,
        "reflux_target": reflux_target,
        "reflux_status": "pending",
        "classification_review": None,
        "by": by or "light-experiment failure classify",
    }
    if reviewer:
        record["classification_review"] = {
            "reviewer": reviewer, "agrees": review_agrees, "date": date,
            "note": "分类时同步抽验"}
    append_jsonl_entry(root, exec_id, FAILURES_FILENAME, record)
    # 回写 run 结论区指针（failure_ref 是结论区的指针字段，此时落字）
    run = load_run(root, exec_id, run_id)
    run["conclusion"]["failure_ref"] = failure_id
    run["updated"] = date
    save_run(root, exec_id, run)
    d = exec_dir(root, exec_id)
    append_event(d, "failure_classified", run_id=run_id,
                 payload={"failure_id": failure_id, "mast_code": mast_code,
                          "failure_class": failure_class,
                          "reflux_target": reflux_target})
    if budget_exceeded:
        append_event(d, "budget_event", run_id=run_id,
                     payload={"kind": "failure_signature_budget",
                              "signature": sig, "attempt_kind": attempt_kind,
                              "limit": FAILURE_SIGNATURE_BUDGET[attempt_kind],
                              "action": "alarm_stop_and_report"})
    _emit_reflux(root, exec_id, record, run, date)
    append_event(d, "reflux_emitted", run_id=run_id,
                 payload={"failure_id": failure_id, "target": reflux_target})
    return record


def _emit_reflux(root: Path, exec_id: str, record: dict, run: dict,
                 date: str) -> list[dict]:
    """按 reflux_target 生成回流条目（只生成、不决策，拍板 ⑥）。"""
    rd = reflux_dir(root, exec_id)
    rd.mkdir(parents=True, exist_ok=True)
    made: list[dict] = []

    def _append(name: str, entry: dict) -> dict:
        p = rd / name
        # RX 编号在两本回流账之间统一计数，避免同号条目跨账撞车
        total = 0
        for other in ("retry_queue.jsonl", "design_inbox.jsonl"):
            op = rd / other
            if op.exists():
                total += len(read_jsonl(op))
        entry = {"entry_id": f"RX-{total + 1:04d}", **entry}
        with open(p, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
        made.append(entry)
        return entry

    base = {
        "source": "failure",
        "source_id": record["failure_id"],
        "run_id": record["run_id"],
        "mast_code": record["mast_code"],
        "failure_class": record["failure_class"],
        "root_cause": record["root_cause"],
        "status": "pending",
        "created": date,
    }
    if record["failure_class"] == "implementation":
        _append("retry_queue.jsonl", {
            **base, "kind": "retry",
            "retry_guidance": record["retry_guidance"],
            "signature": record["signature"],
            "budget_exceeded": record["budget_exceeded"],
        })
    else:
        _append("design_inbox.jsonl", {
            **base, "kind": "design_failure",
            "boundary_conditions": record["boundary_conditions"],
            "note": "设计级失败：回 Design 汇总，构成修订的转 amendment",
        })
        if record["reflux_target"] == "idea":
            dossiers = rd / "idea_dossiers"
            dossiers.mkdir(parents=True, exist_ok=True)
            path = dossiers / f"{record['failure_id']}.md"
            path.write_text(
                f"# Idea 回流 dossier 草稿 — {record['failure_id']}\n\n"
                f"> 由 Light-Experiment 失败分类自动生成（{date}），经 Design "
                "中转回 Idea 的修订/杀卡流程；本草稿不直接改想法卡。\n\n"
                f"- 来源 run：{record['run_id']}（exit_status "
                f"{record['exit_status']}）\n"
                f"- MAST 根因类：{record['mast_code']} "
                f"{MAST_CODES[record['mast_code']]['name']}\n"
                f"- 根因：{record['root_cause']}\n"
                f"- 边界条件：{record['boundary_conditions']}\n"
                f"- 诊断：{record['diagnosis'] or '（未填）'}\n",
                encoding="utf-8")
    return made


def review_failure(root: Path, exec_id: str, failure_id: str, *,
                   reviewer: str, agrees: bool, note: str = "",
                   date: str | None = None) -> dict:
    """人工抽验落痕（约束 11：自动分类只作初筛，进回流决策前人工抽验）。"""
    date = date or today()
    if not _nonempty_str(reviewer):
        raise ValueError("抽验必须登记抽验人（--reviewer）")
    pkg = load_package(root, exec_id)
    if not any(f.get("failure_id") == failure_id for f in pkg["failures"]):
        raise ValueError(f"失败记录不存在：{failure_id}")
    entry = {"kind": "failure_review", "failure_id": failure_id,
             "reviewer": reviewer, "agrees": bool(agrees), "date": date,
             "note": note}
    append_jsonl_entry(root, exec_id, FAILURES_FILENAME, entry)
    return entry


# ---------- 回流条目跟踪 ----------

def list_reflux(root: Path, exec_id: str) -> dict:
    from .project import load_reflux
    return load_reflux(root, exec_id)


def reflux_status_of(entries: list[dict], entry_id: str) -> str:
    """一条回流条目的现行状态：其 status_update 追加条目的最后一条，
    无更新则为条目自带的 status。"""
    status = ""
    for e in entries:
        if e.get("entry_id") == entry_id and e.get("kind") != "status_update":
            status = e.get("status") or "pending"
    for e in entries:
        if e.get("kind") == "status_update" and e.get("entry_id") == entry_id:
            status = e.get("status") or status
    return status


def update_reflux_entry(root: Path, exec_id: str, entry_id: str, *,
                        status: str, by: str = "",
                        date: str | None = None) -> dict:
    """以追加条目方式更新回流状态，并同步 failures.jsonl 中对应失败
    记录的 reflux_status 呈现（以追加 kind=reflux_status 条目实现，
    fold_failures 会取最后一条）。"""
    from .schema import REFLUX_STATES
    date = date or today()
    if status not in REFLUX_STATES:
        raise ValueError(f"reflux 状态非法：{status!r}（须属 {list(REFLUX_STATES)}）")
    from .project import load_reflux
    reflux = load_reflux(root, exec_id)
    all_entries = reflux["retry_queue"] + reflux["design_inbox"]
    target = next((e for e in all_entries if e.get("entry_id") == entry_id), None)
    if target is None:
        raise ValueError(f"回流条目不存在：{entry_id}")
    rd = reflux_dir(root, exec_id)
    name = "retry_queue.jsonl" if target in reflux["retry_queue"] \
        else "design_inbox.jsonl"
    entry = {"kind": "status_update", "entry_id": entry_id, "status": status,
             "date": date, "by": by or "light-experiment reflux update"}
    with open(rd / name, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
    # 同步失败记录的 reflux_status 呈现（追加条目，折叠取最后一条）
    src = target.get("source_id")
    pkg = load_package(root, exec_id)
    if target.get("source") == "failure" and src:
        append_jsonl_entry(root, exec_id, FAILURES_FILENAME,
                           {"kind": "reflux_status", "failure_id": src,
                            "reflux_status": status, "date": date})
    return entry
