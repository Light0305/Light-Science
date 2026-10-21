"""链接图谱自算与改名重写器（工具层 T1，TOOLING-PLAN §5.1）。

为什么自研：社区 CLI 的 move 在规划期实测未跑通（§0 P7），改名
改链这种一致性操作不许依赖外部工具。图谱是派生物——由 vault
文件全量扫描确定性算出，可整删重算（与 .index 同律）。

解析口径与 Obsidian 对齐：
- wikilink 含别名（|）、标题（#）、块引用（#^）与嵌入（! 前缀）；
- 内联字段形（键:: 目标）落类型边，与投影的类型边双写同形；
- 目标解析：带路径按 vault 相对路径匹配；短链按 basename 匹配，
  basename 唯一才可解，同名多份记 ambiguous 不猜（Breadcrumbs
  的全路径标识教训，DR-O §一.3）；
- 代码围栏与行内代码中的链接不算边。

改名重写覆盖：wikilink（别名/标题/块后缀原样保留）、内联字段
目标、.canvas 的 file 节点与 text 节点内链、.base 过滤里的路径
字符串。先 dry-run 出 diff 清单，落字后重算图谱复验无新增未解。
投影笔记文件名由对象 ID 派生，改名拒（指引走四账/重投影）。
"""

from __future__ import annotations

import re
from pathlib import Path

from . import canvasio, vaultio

_WIKILINK_RE = re.compile(r"(!?)\[\[([^\]\n]+)\]\]")


class LinkGraphError(Exception):
    def __init__(self, gaps):
        self.gaps = list(gaps)
        super().__init__("；".join(self.gaps))


# ---------------------------------------------------------------- 解析

def _split_link_inner(inner: str) -> dict:
    """拆 wikilink 内部文本：目标 + 后缀（#标题/#^块/|别名原样）。"""
    target, sep, alias = inner.partition("|")
    suffix = ("|" + alias) if sep else ""
    head, frag = target, ""
    hash_at = target.find("#")
    if hash_at >= 0:
        head, frag = target[:hash_at], target[hash_at:]
    return {"target": head.strip(), "suffix": frag + suffix,
            "alias": alias if sep else None,
            "fragment": frag or None}


def _field_value_span(line: str):
    """行首内联字段（键:: 值）：返回 (key, value_start_index)。"""
    stripped = line.lstrip()
    lead = len(line) - len(stripped)
    if stripped.startswith(("- ", "* ", "+ ")):
        stripped = stripped[2:]
        lead += 2
    at = stripped.find("::")
    if at <= 0:
        return None
    key = stripped[:at].strip()
    if not key or len(key) > 64 or ":" in key:
        return None
    if any(c in key for c in "[]#"):
        return None
    return key, lead + at + 2


def parse_note_links(text: str) -> list:
    """抽一篇笔记的出边（代码块/行内代码剔除、字段边归类）。"""
    edges = []
    in_fence = False
    for lineno, line in enumerate((text or "").split("\n"), 1):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        field = _field_value_span(line)
        scan = re.sub(r"`[^`\n]*`", lambda m: " " * len(m.group(0)),
                      line)
        for m in _WIKILINK_RE.finditer(scan):
            parts = _split_link_inner(m.group(2))
            kind = "wikilink"
            field_key = None
            if m.group(1) == "!":
                kind = "embed"
            elif field and m.start() >= field[1]:
                kind, field_key = "inline_field", field[0]
            edges.append({
                "target_raw": m.group(2), "target": parts["target"],
                "suffix": parts["suffix"], "alias": parts["alias"],
                "fragment": parts["fragment"], "kind": kind,
                "field": field_key, "line": lineno,
                "start": m.start(), "end": m.end(),
                "embed": m.group(1) == "!",
            })
    return edges


# ---------------------------------------------------------------- 图谱

def _resolve(target: str, rel_set: set, by_stem: dict):
    """目标解析：返回 (rel 或 None, reason 或 None, candidates)。"""
    t = (target or "").strip()
    if t.endswith(".md"):
        t = t[:-3]
    if not t:
        return None, "empty", []
    if "/" in t:
        if t + ".md" in rel_set:
            return t + ".md", None, []
        return None, "missing", []
    hits = by_stem.get(t) or []
    if len(hits) == 1:
        return hits[0], None, []
    if len(hits) > 1:
        return None, "ambiguous", sorted(hits)
    return None, "missing", []


def _index(rels: list):
    by_stem: dict[str, list] = {}
    for rel in rels:
        by_stem.setdefault(Path(rel).stem, []).append(rel)
    return set(rels), by_stem


def build_graph(vault) -> dict:
    """全库扫描自算图谱：出边/入边/未解/孤儿四表 + 边全量。"""
    vault = Path(vault)
    rels = vaultio.list_notes(vault)
    rel_set, by_stem = _index(rels)
    edges, unresolved = [], []
    outlinks: dict[str, set] = {rel: set() for rel in rels}
    backlinks: dict[str, set] = {rel: set() for rel in rels}
    for rel in rels:
        text = (vault / rel).read_text(encoding="utf-8")
        for e in parse_note_links(text):
            to, reason, cands = _resolve(e["target"], rel_set,
                                          by_stem)
            edges.append({"from": rel, "to": to,
                          "target_raw": e["target_raw"],
                          "target": e["target"], "kind": e["kind"],
                          "field": e["field"], "line": e["line"],
                          "embed": e["embed"]})
            if to is None:
                unresolved.append({
                    "from": rel, "target_raw": e["target_raw"],
                    "reason": reason, "candidates": cands,
                    "line": e["line"]})
            else:
                outlinks[rel].add(to)
                backlinks[to].add(rel)
    orphans = sorted(rel for rel in rels
                     if not outlinks[rel] and not backlinks[rel])
    return {
        "vault": str(vault), "notes": rels, "edges": edges,
        "outlinks": {k: sorted(v) for k, v in outlinks.items()},
        "backlinks": {k: sorted(v) for k, v in backlinks.items()},
        "unresolved": unresolved, "orphans": orphans,
    }


# ---------------------------------------------------------------- 改名

def _new_link_target(written_target: str, new_rel: str,
                     new_stem_count: int) -> str:
    """按原写法定新目标：路径形换全路径；短链在新名仍唯一时
    保持短链、否则升全路径消歧；原带 .md 后缀者保留后缀。"""
    had_ext = written_target.endswith(".md")
    new_noext = new_rel[:-3] if new_rel.endswith(".md") else new_rel
    if "/" in written_target:
        base = new_noext
    elif new_stem_count == 1:
        base = Path(new_rel).stem
    else:
        base = new_noext
    return base + (".md" if had_ext else "")


def _hits_in_text(text: str, rel_set: set, by_stem: dict,
                  old_rel: str, new_rel: str,
                  new_stem_count: int) -> list:
    """一段文本内指向 old_rel 的链接改写点（绝对偏移，不落盘）。"""
    line_starts = [0]
    for line in text.split("\n"):
        line_starts.append(line_starts[-1] + len(line) + 1)
    hits = []
    for e in parse_note_links(text):
        to, _, _ = _resolve(e["target"], rel_set, by_stem)
        if to != old_rel:
            continue
        new_inner = _new_link_target(e["target"], new_rel,
                                     new_stem_count) + e["suffix"]
        base = line_starts[e["line"] - 1]
        hits.append({"offset": base + e["start"],
                     "end": base + e["end"], "old": e["target_raw"],
                     "new": new_inner, "line": e["line"]})
    return hits


def _apply_hits(text: str, hits: list) -> str:
    out = text
    for hit in sorted(hits, key=lambda h: h["offset"], reverse=True):
        bang = out[hit["offset"]] == "!"
        start = hit["offset"] + (1 if bang else 0)
        out = out[:start] + "[[" + hit["new"] + "]]" + \
            out[hit["end"]:]
    return out


def rename_note(vault, old_rel: str, new_rel: str,
                apply: bool = False) -> dict:
    """改名重写：dry-run 出 diff 清单；apply 落字并复验。

    执行序：先移文件、再按原偏移改写各文件（含被改名文件自身
    的自链）。复验口径：重算图谱后未解集合与改名前相比不得
    新增（ file 移动造成的 from 变化先映射回新名再比）。
    """
    vault = Path(vault)
    old_path = vaultio._note_path(vault, old_rel)
    new_path = vaultio._note_path(vault, new_rel)
    if not old_path.exists():
        raise LinkGraphError([f"待改名笔记不存在：{old_rel}"])
    if new_path.exists():
        raise LinkGraphError([f"目标路径已存在：{new_rel}"])
    if vaultio.is_projected(vault, old_rel,
                            old_path.read_text(encoding="utf-8")):
        raise LinkGraphError([
            f"投影笔记文件名由对象 ID 派生，拒改名：{old_rel}"
            "——如需改名请改四账/对象后重投影"])
    graph_before = build_graph(vault)
    rel_set, by_stem = _index(graph_before["notes"])
    rels_after = [new_rel if r == old_rel else r
                  for r in graph_before["notes"]]
    stem_count = sum(1 for r in rels_after
                     if Path(r).stem == Path(new_rel).stem)

    note_changes: dict[str, list] = {}
    for rel in graph_before["notes"]:
        hits = _hits_in_text(
            (vault / rel).read_text(encoding="utf-8"),
            rel_set, by_stem, old_rel, new_rel, stem_count)
        if hits:
            note_changes[rel] = hits

    old_noext = old_rel[:-3] if old_rel.endswith(".md") else old_rel
    new_noext = new_rel[:-3] if new_rel.endswith(".md") else new_rel
    canvas_plan, base_plan = [], []
    for path in sorted(vault.rglob("*.canvas")):
        if vaultio.TRASH_DIR in path.parts:
            continue
        try:
            data = canvasio.load_canvas(path)
        except canvasio.CanvasError:
            continue
        hits = []
        for node in data.get("nodes") or []:
            if node.get("type") == "file" and \
                    node.get("file") == old_rel:
                hits.append({"node": node.get("id"),
                             "field": "file", "old": old_rel,
                             "new": new_rel})
            elif node.get("type") == "text" and \
                    isinstance(node.get("text"), str):
                for h in _hits_in_text(node["text"], rel_set,
                                       by_stem, old_rel, new_rel,
                                       stem_count):
                    hits.append({"node": node.get("id"),
                                 "field": "text", "old": h["old"],
                                 "new": h["new"], "_hit": h})
        if hits:
            canvas_plan.append(
                {"file": path.relative_to(vault).as_posix(),
                 "hits": hits})
    for path in sorted(vault.rglob("*.base")):
        if vaultio.TRASH_DIR in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        count = text.count(old_rel) + text.count(f'"{old_noext}"') \
            + text.count(f"'{old_noext}'")
        if count:
            base_plan.append(
                {"file": path.relative_to(vault).as_posix(),
                 "count": count})

    plan = {
        "rename": {"from": old_rel, "to": new_rel},
        "applied": False,
        "note_changes": [
            {"file": rel,
             "replacements": [{"line": h["line"], "old": h["old"],
                               "new": h["new"]} for h in hits]}
            for rel, hits in sorted(note_changes.items())],
        "canvas_changes": [
            {"file": c["file"],
             "hits": [{"node": h["node"], "field": h["field"],
                       "old": h["old"], "new": h["new"]}
                      for h in c["hits"]]}
            for c in canvas_plan],
        "base_changes": base_plan,
        "unresolved_before": graph_before["unresolved"],
    }
    if not apply:
        return plan

    new_path.parent.mkdir(parents=True, exist_ok=True)
    old_path.rename(new_path)
    for rel, hits in note_changes.items():
        target = vault / (new_rel if rel == old_rel else rel)
        target.write_text(
            _apply_hits(target.read_text(encoding="utf-8"), hits),
            encoding="utf-8")
    for entry in canvas_plan:
        cpath = vault / entry["file"]
        data = canvasio.load_canvas(cpath)
        by_node = {n.get("id"): n for n in data.get("nodes") or []}
        text_hits: dict[str, list] = {}
        for h in entry["hits"]:
            node = by_node.get(h["node"])
            if node is None:
                continue
            if h["field"] == "file":
                node["file"] = new_rel
            else:
                text_hits.setdefault(h["node"], []).append(h["_hit"])
        for node_id, hits in text_hits.items():
            node = by_node[node_id]
            node["text"] = _apply_hits(node["text"], hits)
        canvasio.save_canvas(cpath, data)
    for entry in base_plan:
        bpath = vault / entry["file"]
        text = bpath.read_text(encoding="utf-8")
        text = text.replace(old_rel, new_rel)
        text = text.replace(f'"{old_noext}"', f'"{new_noext}"')
        text = text.replace(f"'{old_noext}'", f"'{new_noext}'")
        bpath.write_text(text, encoding="utf-8")

    graph_after = build_graph(vault)
    before_keys = {(u["from"], u["target_raw"])
                   for u in graph_before["unresolved"]}
    after_keys = {(new_rel if f == old_rel else f, t)
                  for f, t in ((u["from"], u["target_raw"])
                               for u in graph_after["unresolved"])}
    plan["applied"] = True
    plan["unresolved_after"] = graph_after["unresolved"]
    plan["new_unresolved"] = sorted(
        f"{f} -> {t}" for f, t in after_keys - before_keys)
    plan["graph_notes"] = graph_after["notes"]
    return plan
