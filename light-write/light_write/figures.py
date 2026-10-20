"""W5 图表回填三方对账与编号冻结（Phase 2）。

三方 = figures_manifest 登记行 ↔ 正文 [fig:F###] 标记实位 ↔ 图注文本：
- intext_refs 账实一致：清单登记的引用位置 == 正文实际标记位置
  （sync 从正文回填账，check 只判不改）；
- backfilled 行：交付物指针/哈希在场（validate 已查）、图注在场且
  caption_text_hash 对齐、图注原文出现在其放置节文件中；
- 编号冻结（时点 = audited 段前，见 SKILL）：冻结后新增图表只许
  追加编号（append，落 numbering.changes 日志）或全量重编
  （freeze --renumber，同样落日志），不许静默插队改号。
display_number 按 kind 分别编号（F→Figure n、T→Table n），次序 =
 正文首次出现次序（按节登记顺序 × 行号）。
"""

from __future__ import annotations

import re
from pathlib import Path

from . import schema
from .project import (
    load_package, manuscript_hash, save_figures, section_files,
)
from .util import sha256_text, today

FIG_MARK_RE = re.compile(r"\[fig:([A-Za-z0-9_-]+)\]")


class FigureError(Exception):
    def __init__(self, gaps):
        self.gaps = list(gaps)
        super().__init__("；".join(self.gaps))


def scan_intext_refs(root) -> dict:
    """正文 [fig:] 标记实位：{figure_id: [{file, line}]}（节登记序 × 行号）。"""
    root = Path(root)
    pkg = load_package(root)
    manuscript = pkg["manuscript"] or {}
    order = {}
    for i, s in enumerate(manuscript.get("sections") or []):
        order[s.get("file")] = i
    files = section_files(root)
    refs = {}
    for fname in sorted(files, key=lambda f: (order.get(f, 999), f)):
        for lineno, line in enumerate(files[fname].splitlines(), 1):
            for m in FIG_MARK_RE.finditer(line):
                refs.setdefault(m.group(1), []).append(
                    {"file": fname, "line": lineno})
    return refs


def _ordered_ids(root, refs=None) -> list:
    """图表次序：按首次出现（节序 × 行号）；未入正文者按 figure_id 排尾。"""
    refs = refs if refs is not None else scan_intext_refs(root)
    pkg = load_package(root)
    manuscript = pkg["manuscript"] or {}
    order = {}
    for i, s in enumerate(manuscript.get("sections") or []):
        order[s.get("file")] = i

    def key(fid):
        occ = refs.get(fid)
        if occ:
            first = occ[0]
            return (0, order.get(first["file"], 999), first["line"], fid)
        return (1, 0, 0, fid)

    rows = (pkg["figures"] or {}).get("figures") or []
    return sorted([r.get("figure_id") for r in rows], key=key)


def _kind_of(row) -> str:
    kind = row.get("kind")
    if kind in schema.FIGURE_KINDS:
        return kind
    fid = row.get("figure_id") or ""
    return "table" if fid.startswith("T") else "figure"


def sync_intext_refs(root) -> dict:
    """从正文回填 intext_refs 账（check 只判不改，sync 是唯一回填口）。"""
    root = Path(root)
    pkg = load_package(root)
    refs = scan_intext_refs(root)
    figures = pkg["figures"]
    changed = []
    for row in figures.get("figures") or []:
        actual = refs.get(row.get("figure_id"), [])
        if row.get("intext_refs") != actual:
            row["intext_refs"] = actual
            changed.append(row.get("figure_id"))
    save_figures(root, figures)
    return {"synced": changed, "figures_with_refs": sorted(refs)}


def set_caption(root, figure_id, caption) -> dict:
    root = Path(root)
    pkg = load_package(root)
    for row in (pkg["figures"] or {}).get("figures") or []:
        if row.get("figure_id") == figure_id:
            row["caption"] = caption
            row["caption_text_hash"] = sha256_text(caption.strip())
            save_figures(root, pkg["figures"])
            return {"figure_id": figure_id,
                    "caption_text_hash": row["caption_text_hash"]}
    raise FigureError([f"图表 {figure_id} 不在 figures_manifest 中"])


def mark_delivered(root, figure_id, source_ref, source_hash,
                   backfill=False) -> dict:
    root = Path(root)
    pkg = load_package(root)
    for row in (pkg["figures"] or {}).get("figures") or []:
        if row.get("figure_id") == figure_id:
            row["source_ref"] = source_ref
            row["source_hash"] = source_hash
            if backfill:
                if not row.get("caption"):
                    raise FigureError([
                        f"图表 {figure_id} 无图注不许标 backfilled："
                        "先 set-caption"])
                row["status"] = "backfilled"
            else:
                row["status"] = "delivered"
            save_figures(root, pkg["figures"])
            return {"figure_id": figure_id, "status": row["status"]}
    raise FigureError([f"图表 {figure_id} 不在 figures_manifest 中"])


def add_figure(root, figure_id, kind="figure") -> dict:
    """登记新图表；编号已冻结时只许追加编号并落变更日志。"""
    root = Path(root)
    pkg = load_package(root)
    figures = pkg["figures"]
    rows = figures.setdefault("figures", [])
    if any(r.get("figure_id") == figure_id for r in rows):
        raise FigureError([f"图表 {figure_id} 已登记"])
    if kind not in schema.FIGURE_KINDS:
        raise FigureError([f"kind {kind!r} 不在 {schema.FIGURE_KINDS}"])
    row = {"figure_id": figure_id, "kind": kind, "status": "placeholder",
           "source_ref": None, "source_hash": None, "caption": None,
           "caption_text_hash": None, "intext_refs": [],
           "display_number": None}
    rows.append(row)
    numbering = figures.get("numbering") or {}
    if numbering.get("frozen"):
        same_kind = [r for r in rows
                     if _kind_of(r) == kind
                     and r.get("display_number") is not None]
        row["display_number"] = (max(r["display_number"] for r in same_kind)
                                  + 1) if same_kind else 1
        numbering.setdefault("order", []).append(figure_id)
        numbering.setdefault("changes", []).append({
            "at": today(), "action": "append_after_freeze",
            "figure_id": figure_id,
            "display_number": row["display_number"],
            "note": "编号冻结后新增：只许追加编号（或全量重编并落字）"})
        figures["numbering"] = numbering
    save_figures(root, figures)
    return row


def freeze_numbering(root, renumber=False) -> dict:
    """编号冻结：按正文首次出现次序分 kind 派号；重编须显式 renumber 并落日志。"""
    root = Path(root)
    pkg = load_package(root)
    figures = pkg["figures"]
    numbering = figures.get("numbering") or {}
    if numbering.get("frozen") and not renumber:
        return {"frozen": True, "already": True,
                "order": numbering.get("order")}
    ordered = _ordered_ids(root)
    rows = {r.get("figure_id"): r
            for r in figures.get("figures") or []}
    counters = {}
    for fid in ordered:
        kind = _kind_of(rows[fid])
        counters[kind] = counters.get(kind, 0) + 1
        rows[fid]["display_number"] = counters[kind]
        rows[fid]["display_label"] = (
            f"{'Figure' if kind == 'figure' else 'Table'} {counters[kind]}")
    changes = list(numbering.get("changes") or [])
    changes.append({"at": today(),
                    "action": "renumber_all" if numbering.get("frozen")
                    else "freeze",
                    "order": ordered,
                    "manuscript_hash": manuscript_hash(root)})
    figures["numbering"] = {"frozen": True, "frozen_at": today(),
                            "order": ordered, "changes": changes}
    save_figures(root, figures)
    return {"frozen": True, "already": False, "order": ordered}


def check_figures(root) -> dict:
    """三方对账：返回 {ok, findings}（只判不改）。"""
    root = Path(root)
    findings = []

    def err(code, msg):
        findings.append({"level": "error", "code": code, "message": msg})

    def warn(code, msg):
        findings.append({"level": "warning", "code": code, "message": msg})

    pkg = load_package(root)
    figures = pkg["figures"] or {}
    rows = figures.get("figures") or []
    by_id = {r.get("figure_id"): r for r in rows}
    refs = scan_intext_refs(root)
    files = section_files(root)
    for fid in refs:
        if fid not in by_id:
            err("figures.mark_without_row",
                f"正文标记 [fig:{fid}] 在 figures_manifest 中无登记行")
    for row in rows:
        fid = row.get("figure_id")
        actual = refs.get(fid, [])
        if row.get("intext_refs") != actual:
            err("figures.intext_refs_mismatch",
                f"图表 {fid} intext_refs 与正文实位不符（登记 "
                f"{row.get('intext_refs')} vs 实际 {actual}）：先跑 "
                "figures sync 回填账")
        if not actual and not row.get("placeholder_anchor"):
            warn("figures.unreferenced",
                 f"图表 {fid} 正文无引用且无 placeholder_anchor")
        if row.get("status") == "backfilled":
            caption = row.get("caption")
            if not caption:
                err("figures.backfilled_no_caption",
                    f"图表 {fid} 已回填但无图注")
            else:
                if row.get("caption_text_hash") != sha256_text(caption.strip()):
                    err("figures.caption_hash_drift",
                        f"图表 {fid} caption_text_hash 与图注文本不符")
                if actual:
                    place_file = actual[0]["file"]
                    if caption.strip() not in files.get(place_file, ""):
                        err("figures.caption_not_in_text",
                            f"图表 {fid} 图注原文未出现在放置节 "
                            f"sections/{place_file} 中（图注须与正文同位）")
    numbering = figures.get("numbering") or {}
    seen_numbers = {}
    for row in rows:
        n = row.get("display_number")
        if n is not None:
            key = (_kind_of(row), n)
            if key in seen_numbers:
                err("figures.display_number_dup",
                    f"{_kind_of(row)} 编号 {n} 重复：{seen_numbers[key]} 与 "
                    f"{row.get('figure_id')}")
            seen_numbers[key] = row.get("figure_id")
    if numbering.get("frozen"):
        expected = _ordered_ids(root, refs)
        if numbering.get("order") != expected:
            warn("figures.order_changed_after_freeze",
                 "编号冻结后图表次序已变（新增/移动）：现行 order 与冻结 "
                 "order 不一致，处置只能是追加编号或全量重编落字")
        counters = {}
        for fid in expected:
            row = by_id.get(fid)
            if row is None:
                continue
            kind = _kind_of(row)
            counters[kind] = counters.get(kind, 0) + 1
            if row.get("display_number") is not None and \
                    row["display_number"] != counters[kind]:
                err("figures.display_number_mismatch",
                    f"图表 {fid} display_number={row['display_number']} "
                    f"与冻结次序应得 {counters[kind]} 不符")
    return {"ok": not any(f["level"] == "error" for f in findings),
            "findings": findings}
