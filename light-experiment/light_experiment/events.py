"""轨迹事件日志 events.jsonl（只增，约束 3）。

每行一个事件：{seq, event_id, ts, type, source, run_id, parent_event_id,
payload}。纪律：

- 只追加、永不回改：本模块只提供 append 与 read，没有改写入口；
  seq 自 1 起连续递增，event_id = EV-<seq:06d>，由 seq 派生不许自拟；
- 时间戳（UTC）不倒退：校验器逐行验 seq 连续 + ts 单调不减；
- 摘要视图（EXECUTION_REPORT）是事件的只读投影，不是本体；
  人工拒绝、被护栏拦下的动作同样成事件（payload 记理由）。

事件类型下限集（草案 §2.2）：run_queued / run_started / attempt_started /
step / observation / intervention_check / deviation_raised /
deviation_decided / deviation_voided / budget_event / breaker_tripped /
human_checkpoint / run_finished / failure_classified / reflux_emitted /
resume / void_marked / intake_done / intake_rejected / package_advanced /
note。一期实际产生的子集见各命令；词表外类型校验器直接报错——
词表修订须走留痕（改本常量 + SKILL 同步），不许静默扩词（约束 11）。
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .util import utcnow

EVENTS_FILENAME = "events.jsonl"

EVENT_TYPES = (
    "intake_done",
    "intake_rejected",
    "package_advanced",
    "run_created",
    "run_queued",
    "attempt_started",
    "run_started",
    "step",
    "observation",
    "intervention_check",
    "deviation_raised",
    "deviation_decided",
    "deviation_voided",
    "budget_event",
    "breaker_tripped",
    "human_checkpoint",
    "run_finished",
    "failure_classified",
    "reflux_emitted",
    "acceptance_initialized",
    "acceptance_recorded",
    "reconciliation_filled",
    "resume",
    "void_marked",
    "note",
)

EVENT_SOURCES = ("agent", "user", "tool", "environment")


def event_id_for(seq: int) -> str:
    return f"EV-{seq:06d}"


def events_path(exec_dir: Path) -> Path:
    return exec_dir / EVENTS_FILENAME


def read_events(exec_dir: Path) -> tuple[list[dict], list[str]]:
    """读事件日志。返回 (events, errors)：坏行不抛异常、逐条记进 errors，
    供校验器把「日志损坏」与「内容不合法」分开点名。"""
    path = events_path(exec_dir)
    events: list[dict] = []
    errors: list[str] = []
    if not path.exists():
        return events, [f"事件日志缺失：{EVENTS_FILENAME} 不存在（轨迹只增，本体不可缺）"]
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError as e:
            errors.append(f"events.jsonl 第 {i} 行不是合法 JSON：{e}")
    return events, errors


def append_event(exec_dir: Path, type: str, *, source: str = "tool",
                 run_id: str | None = None, parent_event_id: str | None = None,
                 payload: dict | None = None) -> dict:
    """追加一条事件并返回它。seq = 现有行数 + 1（只增语义下恒成立；
    文件被外部截断/改写时 seq 会与既有内容冲突，由校验器检出）。"""
    if type not in EVENT_TYPES:
        raise ValueError(f"事件类型不在词表内：{type!r}（词表见 events.EVENT_TYPES）")
    if source not in EVENT_SOURCES:
        raise ValueError(f"事件来源非法：{source!r}（须属 {EVENT_SOURCES}）")
    path = events_path(exec_dir)
    existing, errors = read_events(exec_dir)
    if errors:
        raise ValueError("事件日志已损坏，拒绝追加：" + "；".join(errors))
    seq = len(existing) + 1
    event = {
        "seq": seq,
        "event_id": event_id_for(seq),
        "ts": utcnow(),
        "type": type,
        "source": source,
        "run_id": run_id,
        "parent_event_id": parent_event_id,
        "payload": payload or {},
    }
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")
    return event


def validate_events(events: list[dict]) -> list[str]:
    """事件日志的确定性校验：schema 齐全、seq 连续、event_id 派生一致、
    ts 不倒退、类型在词表内。返回逐条错误（空 = 合法）。"""
    errs: list[str] = []
    prev_ts: datetime | None = None
    for i, ev in enumerate(events):
        want_seq = i + 1
        if not isinstance(ev, dict):
            errs.append(f"事件 #{want_seq} 不是对象")
            continue
        for key in ("seq", "event_id", "ts", "type", "source"):
            if key not in ev:
                errs.append(f"事件 #{want_seq} 缺字段 {key}（事件 schema 不全）")
        if ev.get("seq") != want_seq:
            errs.append(f"事件序号不连续：第 {i + 1} 行 seq={ev.get('seq')!r}，"
                        f"应为 {want_seq}（只增日志被删行/改写即在此暴露）")
        if ev.get("event_id") != event_id_for(want_seq):
            errs.append(f"事件 #{want_seq} 的 event_id={ev.get('event_id')!r} "
                        f"与派生值 {event_id_for(want_seq)} 不符（不许自拟）")
        if ev.get("type") not in EVENT_TYPES:
            errs.append(f"事件 #{want_seq} 类型不在词表内：{ev.get('type')!r}")
        if ev.get("source") not in EVENT_SOURCES:
            errs.append(f"事件 #{want_seq} 来源非法：{ev.get('source')!r}")
        ts_raw = ev.get("ts")
        try:
            ts = datetime.fromisoformat(str(ts_raw))
        except (TypeError, ValueError):
            errs.append(f"事件 #{want_seq} 时间戳不可解析：{ts_raw!r}")
            continue
        if prev_ts is not None and ts < prev_ts:
            errs.append(f"事件 #{want_seq} 时间戳倒退：{ts_raw} < 前一事件"
                        "（只增日志的时间序不许回改）")
        prev_ts = ts
    return errs
