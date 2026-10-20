"""工作区与登记管理（C0）+ 事件账 + 目标运行状态 + 运行锁。

工作区 = 项目根 data-sources/ 目录（LD-02 目录规范落点）：
  crawler.yaml      登记头（含顶层 status 与合规档位锁 lock 段）
  targets/<id>/target.yaml   目标登记（用户撰写，代码校验）
  targets/<id>/state.yaml    目标运行状态（代码维护：熔断/连续被拒）
  prechecks/<id>.jsonl       预检记录与确认事件（只增不改）
  events.jsonl               全工作区事件账（只增不改）
  seen.jsonl                 已见集（请求指纹 + 条件请求凭据）
  provenance.jsonl           全工作区 provenance 总账（只增不改）
  store/<xx>/<sha256>        原始响应内容寻址留存（S3 轻量档）
  runs/<run_id>/             每次采集的 run 记录、清洗件、run 内账
  locks/                     目标运行锁
"""

from __future__ import annotations

import uuid
from pathlib import Path

from . import schema
from .util import append_jsonl, dump_yaml, load_yaml, read_jsonl, utcnow

HEADER_NAME = "crawler.yaml"


class WorkspaceError(Exception):
    def __init__(self, problems):
        self.problems = list(problems)
        super().__init__("；".join(self.problems))


def header_path(root) -> Path:
    return Path(root) / HEADER_NAME


def load_header(root) -> dict:
    header = load_yaml(header_path(root))
    if header is None:
        raise WorkspaceError([f"工作区登记头缺失或不可解析：{header_path(root)}"
                              "（先 init）"])
    return header


def save_header(root, header) -> None:
    dump_yaml(header_path(root), header)


def default_lock() -> dict:
    """项目级合规档位锁的出厂形态：单目标只能收紧、不能放松（见 precheck）。"""
    return {
        "min_interval_sec": None,        # 项目可设下限；None 表示不另加锁值
        "allow_browser": True,           # 项目可整锁关掉浏览器通道
        "max_personal_data_risk": "low",  # 锁内最高可登记风险（high 本就拒收）
    }


def init_workspace(root, project: str) -> dict:
    root = Path(root)
    if header_path(root).exists():
        raise WorkspaceError([f"登记头已存在，拒绝覆盖：{header_path(root)}"])
    root.mkdir(parents=True, exist_ok=True)
    for sub in ("targets", "prechecks", "runs", "store", "locks"):
        (root / sub).mkdir(exist_ok=True)
    header = {
        "kind": "light-crawler/workspace",
        "version": 1,
        "workspace_id": f"ws-{uuid.uuid4().hex[:8]}",
        "project": project,
        "status": "active",
        "created_at": utcnow(),
        "lock": default_lock(),
    }
    save_header(root, header)
    append_event(root, "workspace_initialized",
                 detail=f"项目 {project} 的采集工作区已建（data-sources 口径）")
    return header


# ---------------------------------------------------------------- 事件账

def append_event(root, event_type: str, target_id=None, detail=None,
                 data=None) -> dict:
    if event_type not in schema.EVENT_TYPES:
        raise WorkspaceError([f"事件类型 {event_type!r} 不在词表内"])
    row = {
        "event_id": f"ev-{uuid.uuid4().hex[:12]}",
        "at": utcnow(),
        "type": event_type,
        "target_id": target_id,
        "detail": detail,
        "data": data or {},
    }
    append_jsonl(Path(root) / "events.jsonl", row)
    return row


def read_events(root) -> list:
    return read_jsonl(Path(root) / "events.jsonl")


# ---------------------------------------------------------------- 目标登记

def target_dir(root, target_id) -> Path:
    return Path(root) / "targets" / target_id


def register_target(root, reg: dict, update: bool = False) -> dict:
    """登记（或更新）一个目标。先过 schema 校验，不合格逐项点名拒绝。"""
    problems = schema.validate_target(reg)
    if problems:
        raise WorkspaceError(problems)
    tdir = target_dir(root, reg["target_id"])
    exists = (tdir / "target.yaml").exists()
    if exists and not update:
        raise WorkspaceError(
            [f"目标 {reg['target_id']} 已登记；更新请显式 --update"])
    tdir.mkdir(parents=True, exist_ok=True)
    dump_yaml(tdir / "target.yaml", reg)
    if not (tdir / "state.yaml").exists():
        dump_yaml(tdir / "state.yaml", {
            "target_id": reg["target_id"],
            "consecutive_refusals": 0,
            "circuit_broken": False,
            "circuit_reason": None,
            "updated_at": utcnow(),
        })
    append_event(root, "target_updated" if exists else "target_registered",
                 target_id=reg["target_id"],
                 detail=f"通道 {reg['channel']}，用途 {reg['purpose_kind']}")
    refresh_status(root)
    return reg


def load_target(root, target_id) -> dict:
    reg = load_yaml(target_dir(root, target_id) / "target.yaml")
    if reg is None:
        raise WorkspaceError([f"目标未登记：{target_id}（无登记不抓取，HC-1）"])
    return reg


def list_targets(root) -> list:
    tdir = Path(root) / "targets"
    if not tdir.is_dir():
        return []
    out = []
    for d in sorted(tdir.iterdir()):
        reg = load_yaml(d / "target.yaml")
        if reg is not None:
            out.append(reg)
    return out


def load_state(root, target_id) -> dict:
    state = load_yaml(target_dir(root, target_id) / "state.yaml")
    if state is None:
        state = {"target_id": target_id, "consecutive_refusals": 0,
                 "circuit_broken": False, "circuit_reason": None}
    return state


def save_state(root, state) -> None:
    state["updated_at"] = utcnow()
    dump_yaml(target_dir(root, state["target_id"]) / "state.yaml", state)


def refresh_status(root) -> None:
    """登记头顶层 status 由代码维护：任一目标熔断即 attention。"""
    header = load_yaml(header_path(root))
    if header is None:
        return
    broken = [t["target_id"] for t in list_targets(root)
              if load_state(root, t["target_id"]).get("circuit_broken")]
    header["status"] = "attention" if broken else "active"
    header["circuit_broken_targets"] = broken
    save_header(root, header)


# ---------------------------------------------------------------- 运行锁（项目锁之二）

def acquire_run_lock(root, target_id, run_id, stale_after_sec=3600) -> dict:
    """同一目标同时只许一个在飞 run。残锁超时只点名不自动夺锁。"""
    lock_path = Path(root) / "locks" / f"{target_id}.json"
    if lock_path.exists():
        import json as _json
        try:
            held = _json.loads(lock_path.read_text(encoding="utf-8"))
        except Exception:
            held = {"run_id": "?", "acquired_at": "?"}
        raise WorkspaceError([
            f"目标 {target_id} 已有在飞 run（{held.get('run_id')}，"
            f"起于 {held.get('acquired_at')}）：项目锁拒绝并发 run；"
            "若确为残锁，人工核对后删除 locks/"
            f"{target_id}.json 再继续（删锁动作本身应留痕于项目记录）"])
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    import json as _json
    lock = {"target_id": target_id, "run_id": run_id, "acquired_at": utcnow()}
    lock_path.write_text(_json.dumps(lock, ensure_ascii=False), encoding="utf-8")
    return lock


def release_run_lock(root, target_id) -> None:
    lock_path = Path(root) / "locks" / f"{target_id}.json"
    if lock_path.exists():
        lock_path.unlink()


def new_run_id(target_id: str) -> str:
    return f"run-{target_id}-{uuid.uuid4().hex[:6]}"
