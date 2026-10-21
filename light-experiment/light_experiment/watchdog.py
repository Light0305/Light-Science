"""无进展巡检（总纲三第四批 P1，PLAN §3.3）。

形态定版（PLAN 给二选一：包内轻量巡检 / 外部看门狗契约）——取
**包内轻量巡检**：`watchdog scan` 按需扫描，不起守护进程。理由：
本包「规程执行、不托管子进程」口径不变（拍板 ① = C），守护进程
与工具形态冲突；扫描式巡检与 budget check（触发落事件 + 候选
名单）同构，可被规程/定时任务周期调用。

判定口径（机械、无模型判断）：
- 对象：status == running 的 run；
- 进展信号 = 该 run 的进展类事件（PROGRESS_EVENT_TYPES：开跑 /
  step / observation / heartbeat / 干预核验 / 人工检查点）；
- 闲置时长 = 扫描时刻 − 最近一条进展事件时间戳；≥ 阈值
  （DEFAULT_NO_PROGRESS_THRESHOLD_S = 3600 秒，scan 可配）
  → 判 no_progress。
- 判定只落 `no_progress_verdict` 事件 + 列入候选名单，**工具不
  代杀**：正式终止仍由执行者走 run-finish --exit-status
  killed_no_progress 留痕（与 budget 的 killed_budget 候选同
  纪律）。同一进展状态（最近进展事件 event_id 相同）只落一条
  判定事件，重复扫描不刷事件账。
- 心跳纪律：长 run 靠 `event --type heartbeat`（或 step /
  observation）周期落痕证明在进展；无心跳的静默长跑会被判
  无进展——这是口径不是误报（判定是候选留痕而非终止，执行者
  收到判定后或补心跳续跑、或正规终止）。正常长运行只要按规程
  发心跳，最近进展事件恒新鲜，永不误判（测试钉住此反例）。

残留边界：本巡检是「超时未进展」的机械判定，不做 OpenHands
StuckDetector 式的动作重复/打转语义检测（重复 step 的语义判读
归执行者与评审）；实时性取决于扫描调用频率，工具本身不常驻。
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from .events import append_event
from .util import utcnow

# 进展类事件：出现即证明该 run 在此时刻仍有活动。note / note 类
# 泛记事不算进展（防拿记事刷活），run_finished 等终止事件不出现
# 在 running 的 run 上。
PROGRESS_EVENT_TYPES = (
    "attempt_started",
    "run_started",
    "step",
    "observation",
    "heartbeat",
    "intervention_check",
    "human_checkpoint",
)

DEFAULT_NO_PROGRESS_THRESHOLD_S = 3600.0

VERDICT_EVENT_TYPE = "no_progress_verdict"


def _parse_ts(raw) -> datetime | None:
    try:
        ts = datetime.fromisoformat(str(raw))
    except (TypeError, ValueError):
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts


def evaluate_no_progress(events: list[dict], runs: dict, *,
                         now: datetime, threshold_s: float) -> list[dict]:
    """纯判定：对每个 running 的 run 算闲置时长并给出判定列表。
    返回 [{run_id, last_event_id, last_event_type, last_progress_at,
    idle_seconds, threshold_seconds}]（仅命中的 run）。"""
    verdicts: list[dict] = []
    for rid, run in sorted((runs or {}).items()):
        if not isinstance(run, dict) or run.get("status") != "running":
            continue
        progress = [e for e in events
                    if e.get("run_id") == rid
                    and e.get("type") in PROGRESS_EVENT_TYPES]
        if not progress:
            continue  # 无任何进展事件（异常形态）：无从计时，不判
        last = progress[-1]
        last_ts = _parse_ts(last.get("ts"))
        if last_ts is None:
            continue
        idle = (now - last_ts).total_seconds()
        if idle >= threshold_s:
            verdicts.append({
                "run_id": rid,
                "verdict": "no_progress",
                "last_event_id": last.get("event_id"),
                "last_event_type": last.get("type"),
                "last_progress_at": last.get("ts"),
                "idle_seconds": round(idle, 3),
                "threshold_seconds": threshold_s,
            })
    return verdicts


def scan_no_progress(root: Path, exec_id: str, *,
                     threshold_s: float = DEFAULT_NO_PROGRESS_THRESHOLD_S,
                     now: datetime | None = None,
                     by: str = "") -> dict:
    """扫描执行包并落判定事件。返回 {scanned_at, threshold_seconds,
    running: [...], verdicts: [...], newly_recorded: [...],
    already_recorded: [...]}。已就同一进展状态落过判定的不重复落。"""
    from .project import exec_dir, load_package
    pkg = load_package(root, exec_id)
    events = pkg["events"]
    runs = pkg["runs"]
    now = now or datetime.now(timezone.utc)
    verdicts = evaluate_no_progress(events, runs, now=now,
                                    threshold_s=threshold_s)
    recorded: dict[str, set] = {}
    for e in events:
        if e.get("type") == VERDICT_EVENT_TYPE and e.get("run_id"):
            payload = e.get("payload") or {}
            recorded.setdefault(e["run_id"], set()).add(
                payload.get("last_event_id"))
    d = exec_dir(root, exec_id)
    newly: list[dict] = []
    already: list[dict] = []
    for v in verdicts:
        if v["last_event_id"] in recorded.get(v["run_id"], set()):
            already.append(v)
            continue
        ev = append_event(d, VERDICT_EVENT_TYPE, run_id=v["run_id"],
                          payload={**v, "scanned_at": utcnow(),
                                   "by": by or "light-experiment watchdog scan",
                                   "note": "巡检判定（候选留痕，工具不代杀）："
                                           "正式终止走 run-finish "
                                           "--exit-status killed_no_progress"})
        newly.append({**v, "event_id": ev["event_id"]})
    running = sorted(rid for rid, r in runs.items()
                     if isinstance(r, dict) and r.get("status") == "running")
    return {"scanned_at": utcnow(), "threshold_seconds": threshold_s,
            "running": running, "verdicts": verdicts,
            "newly_recorded": newly, "already_recorded": already}
