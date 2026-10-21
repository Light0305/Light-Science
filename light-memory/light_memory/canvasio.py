"""JSON Canvas 1.0 读写与坐标保全（工具层 T1，TOOLING-PLAN §5.1）。

坐标保全纪律（DR-O 建议 3 从笔记机器区推广到画布）：重生成
.canvas 时，存续节点（file 节点按 file 路径认、text 节点按 id
认）沿用旧坐标与全部既有属性，只给新节点排位、只删已撤节点；
用户在 Obsidian 里拖动过的布局不被重生成冲掉。保全做不到的
产物不进本模块（宁可降为快照件，见规划原文裁决）。
"""

from __future__ import annotations

import json
from pathlib import Path

from .util import component_hash

NODE_TYPES = ("text", "file", "link", "group")
DEFAULT_W, DEFAULT_H = 250, 120
STEP_X, STEP_Y = 370, 200
PER_COLUMN = 6


class CanvasError(Exception):
    def __init__(self, gaps):
        self.gaps = list(gaps)
        super().__init__("；".join(self.gaps))


def validate_canvas(data) -> list:
    """JSON Canvas 1.0 结构校验：返回逐项缺口（空列表为合格）。"""
    gaps = []
    if not isinstance(data, dict):
        return ["canvas 顶层须为对象"]
    nodes = data.get("nodes")
    edges = data.get("edges")
    if not isinstance(nodes, list):
        gaps.append("canvas 缺 nodes 数组")
        nodes = []
    if not isinstance(edges, list):
        gaps.append("canvas 缺 edges 数组")
        edges = []
    ids = set()
    for node in nodes:
        nid = node.get("id")
        if not nid:
            gaps.append("节点缺 id")
            continue
        if nid in ids:
            gaps.append(f"节点 id 重复：{nid}")
        ids.add(nid)
        ntype = node.get("type")
        if ntype not in NODE_TYPES:
            gaps.append(f"节点 {nid} 类型非法：{ntype}")
        if ntype == "file" and not node.get("file"):
            gaps.append(f"file 节点 {nid} 缺 file 路径")
        if ntype == "text" and "text" not in node:
            gaps.append(f"text 节点 {nid} 缺 text")
        if ntype == "link" and not node.get("url"):
            gaps.append(f"link 节点 {nid} 缺 url")
        for axis in ("x", "y", "width", "height"):
            if not isinstance(node.get(axis), (int, float)):
                gaps.append(f"节点 {nid} 缺数值字段 {axis}")
    eids = set()
    for edge in edges:
        eid = edge.get("id")
        if not eid:
            gaps.append("边缺 id")
            continue
        if eid in eids:
            gaps.append(f"边 id 重复：{eid}")
        eids.add(eid)
        for end in ("fromNode", "toNode"):
            if edge.get(end) not in ids:
                gaps.append(f"边 {eid} 的 {end} 指向不存在的节点："
                            f"{edge.get(end)}")
    return gaps


def load_canvas(path) -> dict:
    p = Path(path)
    if not p.exists():
        raise CanvasError([f"canvas 不存在：{p}"])
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise CanvasError([f"canvas JSON 解析失败：{p}（{exc}）"])
    gaps = validate_canvas(data)
    if gaps:
        raise CanvasError(gaps)
    return data


def save_canvas(path, data) -> None:
    gaps = validate_canvas(data)
    if gaps:
        raise CanvasError(gaps)
    Path(path).write_text(
        json.dumps(data, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8")


def _node_key(node: dict):
    if node.get("type") == "file":
        return ("file", node.get("file"))
    return ("id", node.get("id"))


def _edge_key(edge: dict):
    return (edge.get("fromNode"), edge.get("toNode"),
            edge.get("label"))


def merge_canvas(existing: dict, want_nodes: list,
                 want_edges: list) -> tuple:
    """把期望节点/边并入既有 canvas 数据（坐标保全）。

    want_nodes: [{type, file|text|url, id?}]——存续节点保留旧
    条目原样（含坐标与附加属性），新节点按网格排位（接在既有
    包围盒右侧分列）；want_edges: [{from_key, to_key, label?}]
    其中 from_key/to_key 是 _node_key 形（("file", 路径) 或
    ("id", 节点id)）。返回 (新数据, 报告)。
    """
    old_nodes = (existing or {}).get("nodes") or []
    old_edges = (existing or {}).get("edges") or []
    old_by_key = {_node_key(n): n for n in old_nodes}
    used_ids = {n.get("id") for n in old_nodes}

    def fresh_id(seed) -> str:
        base = "n-" + component_hash(seed)[:12]
        cand, i = base, 1
        while cand in used_ids:
            i += 1
            cand = f"{base}-{i}"
        used_ids.add(cand)
        return cand

    max_x = max((n.get("x", 0) for n in old_nodes), default=None)
    base_x = 0 if max_x is None else max_x + STEP_X
    nodes, kept, added = [], 0, 0
    key_to_id: dict = {}
    new_slots = []
    for want in want_nodes:
        key = _node_key(want)
        if key in old_by_key:
            node = dict(old_by_key[key])
            kept += 1
        else:
            node = dict(want)
            if not node.get("id"):
                node["id"] = fresh_id(key)
            else:
                used_ids.add(node["id"])
            new_slots.append(node)
            added += 1
        key_to_id[key] = node["id"]
        nodes.append(node)
    for i, node in enumerate(new_slots):
        node.setdefault("x", base_x + (i // PER_COLUMN) * STEP_X)
        node.setdefault("y", (i % PER_COLUMN) * STEP_Y)
        node.setdefault("width", DEFAULT_W)
        node.setdefault("height", DEFAULT_H)
    removed = len(old_nodes) - kept

    old_edge_by_key = {_edge_key(e): e for e in old_edges}
    edges, e_kept, e_added = [], 0, 0
    for want in want_edges:
        from_id = key_to_id.get(want["from_key"])
        to_id = key_to_id.get(want["to_key"])
        if from_id is None or to_id is None:
            continue
        probe = (from_id, to_id, want.get("label"))
        if probe in old_edge_by_key:
            edges.append(dict(old_edge_by_key[probe]))
            e_kept += 1
        else:
            edge = {"id": "e-" + component_hash(probe)[:12],
                    "fromNode": from_id, "toNode": to_id}
            if want.get("label"):
                edge["label"] = want["label"]
            for side in ("fromSide", "toSide", "color"):
                if want.get(side):
                    edge[side] = want[side]
            edges.append(edge)
            e_added += 1
    e_removed = len(old_edges) - e_kept
    data = dict(existing or {})  # 未知顶层键原样保留
    data["nodes"] = nodes
    data["edges"] = edges
    gaps = validate_canvas(data)
    if gaps:
        raise CanvasError(gaps)
    report = {"nodes_kept": kept, "nodes_added": added,
              "nodes_removed": removed, "edges_kept": e_kept,
              "edges_added": e_added, "edges_removed": e_removed}
    return data, report


def build_canvas_file(path, want_nodes: list,
                      want_edges: list) -> dict:
    """在 path 处生成/保坐标更新 .canvas，返回合并报告。

    path 已存在则先读旧数据做保全合并；不存在则全新排位。
    """
    p = Path(path)
    existing = None
    if p.exists():
        existing = load_canvas(p)
    data, report = merge_canvas(existing, want_nodes, want_edges)
    p.parent.mkdir(parents=True, exist_ok=True)
    save_canvas(p, data)
    report["path"] = str(p)
    report["nodes"] = len(data["nodes"])
    report["edges"] = len(data["edges"])
    return report
