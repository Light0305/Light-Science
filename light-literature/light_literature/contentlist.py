"""content_list 导出：source_map.json → content_list.json。

格式与 MinerU Content List V1 对齐（type / text / text_level / img_path /
image_caption / table_body / page_idx / bbox），作为与 Doc2X / MinerU
等外部引擎对照评测的统一交换格式：同一套打分器可以吃任何一方的
content_list，不必为每个引擎写一份解析。

对齐规则：
- type 映射：text→text、figure→image、table→table、equation→equation；
  图注（caption 块）不单独成条，而是按宿主附到 image 的 image_caption /
  table 的 table_caption（MinerU 原生形态）；无宿主的孤儿图注退化为
  text 条目并标 is_caption=True，不静默丢弃。
- bbox：由 PDF 点坐标换算为 0–1000 相对坐标（整数），page_idx 为 0 起。
- table_body：由 source_map 的 table_md（Markdown 管道表）转 HTML。
- 扩展字段（不与 V1 冲突）：anchor_id（本管线锚点，溯源用）、
  provenance、confidence、verify（纠错层检查状态，原样带出）；
  图组（第六增量）：figure 块带 group_id/group_role 标明所属图组，
  同组分片的 image_caption 相同（图注按 host_ids 折入整组每个分片，
  而非只折入宿主代表块）。
"""

from __future__ import annotations

import html
import re
from pathlib import Path

import pymupdf

from .util import load_paper_yaml, read_json

_TYPE_MAP = {"text": "text", "figure": "image",
             "table": "table", "equation": "equation"}


def table_md_to_html(table_md: str) -> str:
    """Markdown 管道表 → HTML 表格（首行为表头，网格自洽由 checks 另行校验）。"""
    rows: list[list[str]] = []
    for line in (table_md or "").splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if all(re.fullmatch(r":?-{3,}:?", c) for c in cells if c):
            continue  # |---|---| 分隔行
        rows.append(cells)
    if not rows:
        return ""
    out = ["<table>"]
    head, *body = rows
    out.append("<thead><tr>" + "".join(
        f"<th>{html.escape(c)}</th>" for c in head) + "</tr></thead>")
    out.append("<tbody>")
    for r in body:
        out.append("<tr>" + "".join(
            f"<td>{html.escape(c)}</td>" for c in r) + "</tr>")
    out.append("</tbody></table>")
    return "".join(out)


def _to_per_mille(bbox: list[float], width: float, height: float) -> list[int]:
    return [round(bbox[0] / width * 1000), round(bbox[1] / height * 1000),
            round(bbox[2] / width * 1000), round(bbox[3] / height * 1000)]


def build_content_list(smap: dict,
                       page_sizes: dict[int, tuple[float, float]]) -> list[dict]:
    """纯函数：source_map + 页尺寸（{1 起页码: (宽, 高)}）→ content_list。"""
    anchored = [b for b in smap["blocks"] if b.get("id")]
    anchored.sort(key=lambda b: b.get("order") or 0)
    by_id = {b["id"]: b for b in anchored}
    items: list[dict] = []
    item_by_anchor: dict[str, dict] = {}

    def base(block: dict) -> dict:
        w, h = page_sizes[block["page"]]
        item = {
            "page_idx": block["page"] - 1,
            "bbox": _to_per_mille(block["bbox"], w, h),
            "anchor_id": block["id"],
            "provenance": block.get("provenance"),
            "confidence": block.get("confidence"),
            "verify": block.get("verify") or {"exported_from": "source_map"},
        }
        if block.get("group_id"):
            item["group_id"] = block["group_id"]
            item["group_role"] = block.get("group_role")
        return item

    for block in anchored:
        btype = block["type"]
        if btype == "caption":
            continue  # 第二遍附到宿主；孤儿在第三遍处理
        if btype not in _TYPE_MAP:
            continue
        item = base(block)
        item["type"] = _TYPE_MAP[btype]
        if btype == "text":
            item["text"] = block.get("text", "")
            if block.get("text_level"):
                item["text_level"] = block["text_level"]
        elif btype == "figure":
            item["img_path"] = block.get("asset", "")
            item["image_caption"] = []
        elif btype == "table":
            item["table_body"] = table_md_to_html(block.get("table_md", ""))
            item["table_caption"] = []
        elif btype == "equation":
            item["text"] = block.get("text", "")
        items.append(item)
        item_by_anchor[block["id"]] = item

    # 图注附到宿主（image_caption / table_caption），保留 caption 锚点；
    # 图组图注按 host_ids 折入整组每个分片（同组 image_caption 相同）
    orphans = []
    for block in anchored:
        if block["type"] != "caption":
            continue
        host = by_id.get(block.get("host_id") or "")
        host_ids = block.get("host_ids") or (
            [block["host_id"]] if block.get("host_id") else [])
        host_items = [item_by_anchor[h] for h in host_ids
                      if h in item_by_anchor]
        if host is not None and host_items:
            key = ("image_caption" if host["type"] == "figure"
                   else "table_caption")
            for host_item in host_items:
                host_item.setdefault(key, []).append(block.get("text", ""))
                host_item["caption_anchor_id"] = block["id"]
        else:
            orphans.append(block)

    # 孤儿图注：退化为 text 条目并显式标记（不静默丢弃，与 verify 口径一致）
    for block in orphans:
        item = base(block)
        item["type"] = "text"
        item["text"] = block.get("text", "")
        item["is_caption"] = True
        items.append(item)
        item_by_anchor[block["id"]] = item

    order_of = {b["id"]: b.get("order") or 0 for b in anchored}
    items.sort(key=lambda it: (it["page_idx"],
                               order_of.get(it.get("anchor_id"), 0)))
    return items


def export_content_list(project_dir: Path, paper_id: str) -> dict:
    """生成 <paper_dir>/content_list.json，返回统计。"""
    pdir, paper = load_paper_yaml(project_dir, paper_id)
    smap_path = pdir / "source_map.json"
    if not smap_path.exists():
        raise FileNotFoundError(
            "source_map.json 不存在，先运行 parse（Doc2X 轨）"
            "或按 SKILL.md §5 模型直读轨生成")
    smap = read_json(smap_path)
    doc = pymupdf.open(pdir / "原文.pdf")
    try:
        page_sizes = {i + 1: (p.rect.width, p.rect.height)
                      for i, p in enumerate(doc)}
    finally:
        doc.close()
    items = build_content_list(smap, page_sizes)
    from .util import write_json
    write_json(pdir / "content_list.json", items)
    from collections import Counter
    counts = Counter(it["type"] for it in items)
    return {"paper_id": paper_id, "items": len(items),
            "by_type": dict(counts),
            "path": str(pdir / "content_list.json")}
