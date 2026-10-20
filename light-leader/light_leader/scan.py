"""status：只读扫描项目目录，逐阶段报告各包登记文件的状态。

扫描口径（与 SKILL.md §7 同源）：
- 在项目树内按登记头文件名定位各包产物（深度上限内递归，跳过隐藏
  目录与 __pycache__）；状态一律读登记头顶层 status 字段，硬门标记
  按字段名深搜。读不到、解析失败、字段缺失都逐项落字，不猜。
- literature 无状态机：读 文献索引.csv 的逐篇 status 列计数，并数
  同目录 证据表.jsonl 行数。
- memory：读 memory.yaml 是否存在 + 四账行数 + registry-view.json
  是否已导出。
- 本模块只读，绝不写任何文件。
"""

from __future__ import annotations

import csv
from pathlib import Path

from .layout import GATE_FIELDS, PIPELINE, STAGES
from .util import count_jsonl, deep_find, load_yaml

MAX_DEPTH = 7
_SKIP_DIRS = {"__pycache__", ".git", ".index", "node_modules"}


def _walk_files(root: Path):
    """递归产出 (相对深度, 路径)；跳过隐藏目录与缓存目录。"""
    root = Path(root)
    stack = [(root, 0)]
    while stack:
        d, depth = stack.pop()
        if depth > MAX_DEPTH:
            continue
        try:
            entries = sorted(d.iterdir())
        except OSError:
            continue
        for e in entries:
            if e.is_dir():
                if e.name.startswith(".") or e.name in _SKIP_DIRS:
                    continue
                stack.append((e, depth + 1))
            elif e.is_file():
                yield e


def find_files(root, filename: str) -> list:
    return [p for p in _walk_files(root) if p.name == filename]


def _gate_markers(stage: str, data: dict) -> list:
    """按 GATE_FIELDS 深搜硬门标记；命中 REVIEW_UNAVAILABLE 才登记。"""
    hits = []
    for field in GATE_FIELDS.get(stage, ()):
        val = deep_find(data, field)
        if isinstance(val, str) and "REVIEW_UNAVAILABLE" in val:
            hits.append({"field": field, "value": val})
    return hits


def _scan_yaml_stage(root, stage: str) -> dict:
    spec = STAGES[stage]
    headers = find_files(root, spec["header"])
    items = []
    for h in headers:
        data = load_yaml(h)
        item = {"path": str(h.relative_to(root)), "status": None}
        if data is None:
            item["error"] = "登记头存在但解析失败或顶层非映射"
        else:
            item["status"] = data.get("status")
            if item["status"] is None:
                item["error"] = "登记头缺顶层 status 字段"
            gates = _gate_markers(stage, data)
            if gates:
                item["gates"] = gates
            if stage == "analysis":
                blocked = data.get("blocked")
                if isinstance(blocked, dict) and blocked.get("reason"):
                    item["blocked_reason"] = blocked["reason"]
        items.append(item)
    return {"stage": stage, "skill": spec["skill"], "found": bool(items),
            "items": items}


def _scan_literature(root) -> dict:
    indexes = find_files(root, "文献索引.csv")
    items = []
    for idx in indexes:
        item = {"path": str(idx.relative_to(root)), "papers": 0,
                "status_counts": {}, "evidence_rows": None}
        try:
            with idx.open(encoding="utf-8", newline="") as f:
                for row in csv.DictReader(f):
                    item["papers"] += 1
                    st = (row.get("status") or "").strip() or "(空)"
                    item["status_counts"][st] = \
                        item["status_counts"].get(st, 0) + 1
        except Exception as exc:  # 索引不可读：落字不猜
            item["error"] = f"文献索引读取失败：{exc}"
        ev = idx.parent / "证据表.jsonl"
        if ev.is_file():
            item["evidence_rows"] = count_jsonl(ev)
        items.append(item)
    return {"stage": "literature", "skill": STAGES["literature"]["skill"],
            "found": bool(items), "items": items}


def _scan_memory(root) -> dict:
    heads = find_files(root, "memory.yaml")
    items = []
    for h in heads:
        base = h.parent
        item = {"path": str(h.relative_to(root)),
                "counts": {name: count_jsonl(base / f"{name}.jsonl")
                           for name in ("objects", "events", "facts",
                                        "relations")},
                "registry_view": (base / "registry-view.json").is_file()}
        items.append(item)
    return {"stage": "memory", "skill": STAGES["memory"]["skill"],
            "found": bool(items), "items": items}


def scan_project(root) -> dict:
    """全量扫描，返回 {root, stages: {stage: {...}}}（顺序按流水线）。"""
    root = Path(root)
    stages = {}
    for sid in PIPELINE:
        if sid == "literature":
            stages[sid] = _scan_literature(root)
        else:
            stages[sid] = _scan_yaml_stage(root, sid)
    stages["memory"] = _scan_memory(root)
    return {"root": str(root), "stages": stages}


def stage_statuses(stage_scan: dict) -> list:
    """某阶段全部登记头的 status 值列表（缺失/坏头不入列）。"""
    return [it["status"] for it in stage_scan.get("items", [])
            if it.get("status")]


def any_gate(stage_scan: dict) -> list:
    """某阶段全部硬门标记（跨登记头汇总）。"""
    out = []
    for it in stage_scan.get("items", []):
        out.extend(it.get("gates", []))
    return out
