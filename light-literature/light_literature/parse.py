"""parse 命令：产品解析路径（第八增量，解析双轨制）。

产品解析只有两轨（2026-10-20 用户裁决，见 SKILL.md §5 解析双轨制）：

- **Doc2X 轨（本模块）**：用户自配 Key 后，`parse <paper_dir>` 把整篇
  PDF 送 Doc2X（`engines/doc2x.py` 适配器），再把 Doc2X 的 layout /
  逐页 MD 转成符合 source_map 契约的 source_map.json 与
  原文.md——锚点 S/C/F/T/E 建在 Doc2X 输出之上，verify /
  translate-scaffold / notes / export-content-list 不感知来源差异。
- **模型直读轨（无代码）**：未配置 Doc2X 时由执行 agent 的模型直接
  读 原文.pdf 撰写四件套（步骤与纪律见 SKILL.md），provenance 标
  `model-direct`。

Doc2X 未配置或调用失败时，本模块**不回退任何本地抽取**：明确报错，
并把 paper.yaml 的 `parse.status` 置为 `awaiting_model_direct`，
提示走模型直读轨。本地抽取是研究/对照工具（对照基准、差距分析），
不是产品解析路径，也不包含在产品发布中——`--backend local`
在此明确拒绝。

锚点化转换规则（source_map 契约）：
- 块序：Doc2X 返回顺序（页升序、页内 reading_order）；boilerplate
  块（layout 的 is_boilerplate）作无锚点条目留痕。
- 图注配对与图组：优先用 layout 的 `caption_of`（引擎自身分组的
  归属结论）；图分组用本模块内置的 `_group_figures`（图注亲和 +
  几何相邻），组认领图注的规则为组内共享同一
  caption_id，图注 host 指向组内首块并以 host_ids 记全组）。
- 表格：Doc2X 的 table_body（HTML）用 checks 的网格解析展开为
  Markdown 管道表写入 table_md（verify/content_list 契约要求），
  HTML 原件保留在 table_html 字段（合并单元格语义在 MD 中丢失，
  以 HTML 为准）。
- 公式：text 取 Doc2X 转写的 LaTeX（另存 latex 字段），不再是
  「未转 LaTeX」占位状态。
- confidence：取 Doc2X 逐页 score/100（页级质量分，块级为代理值）；
  无 score 的页不写 confidence，不编造。
- 图资产：优先用 convert 导出 zip 里的裁切图（layout Figure 的 src
  URL 参数与导出文件名同构：`{page}_{x}_{y}_{w}_{h}_{r}.jpg`）；
  未命中的图块用 PDF 页 bbox 渲染裁片兜底（asset_source 逐块
  记录来源：doc2x_export / pdf_crop / page_render）。
"""

from __future__ import annotations

import re
import shutil
import time
import urllib.parse
from pathlib import Path
from typing import Optional

import pymupdf

from . import triage as triage_mod
from .checks import _TableParser, expand_grid
from .engines import EngineUnavailableError
from .engines.doc2x import Doc2XEngine, Doc2XError
from .util import (load_paper_yaml, read_json, read_yaml, save_paper_yaml,
                   write_json)

CROP_ZOOM = 3.0        # PDF 裁片兜底渲染倍率（与 extract 矢量图口径一致）
PAGE_RENDER_ZOOM = 2.0  # 无 bbox 时整页渲染兜底倍率

_PREFIX = {"text": "S", "caption": "C", "figure": "F",
           "table": "T", "equation": "E"}


# ---------- 图注识别 / 图组分组（自研规则，parse 内置） ----------
# 以下纯函数原属开发期的本地抽取管线，产品 parse 路径依赖它们完成
# 图注编号识别、图注-宿主距离度量与多分片图组分组；开源发布版将其
# 以最小方式迁入本模块，行为与标定口径保持不变。

_CAPTION_RE = re.compile(
    r"^\s*(Figure|Fig\.?|Table|图|表)\s*(\d+)\s*[:：\.]", re.IGNORECASE)

# 图组几何相邻规则的 bbox 膨胀半径（pt），标定依据见 _group_figures。
GROUP_GAP = 45.0


def _caption_dist(cap_bbox: list, host_bbox: list) -> float:
    """图注-宿主距离（图注配对与图组亲和共用同一口径）。

    取图注顶边与宿主底边的纵向距离；图注在宿主上方时 +50 惩罚——图注
    通常在图下方、表上方，同等距离优先下方候选。
    """
    dist = abs(cap_bbox[1] - host_bbox[3])
    if cap_bbox[1] < host_bbox[1]:
        dist += 50
    return dist


def _group_figures(figures: list[dict], all_captions: list[dict],
                   fig_captions: list[dict]) -> list[list[dict]]:
    """把同页的图块（栅格整图 + 矢量分片）分组成图组，返回图组列表。

    一幅图被拆成多个 F 分片时，分片共享一条图注；1:1 硬配对会让其余
    分片误标 no_caption（第四增量局限 1）。分组两条规则合用：
    - A 图注亲和：多个图块的「最近图注」（_caption_dist 口径）是同一条
      → 同组。依据：Attention Figure 2 双面板间隙 108pt，几何上挨不
      着，但两面板的最近图注同为 Figure 2 的图注；ResNet Figure 3 五
      分片的最近图注同为 Figure 3 的图注。
    - B 几何相邻：bbox 膨胀 GROUP_GAP 后相交，且两块之间无图注屏障
      （任一图注——图/表注都算——的 bbox 与两块并集相交，说明中间隔着
      别的单元），且两块最近图注相同或至少一块无图注。依据：ResNet p4
      Figure 3 五分片间隙 21–39pt 可链式合并；而 ResNet p8 的 Figure 6
      与 Figure 7 纵向间隙同样是 39pt，靠屏障（Figure 6 的图注夹在两图
      之间）+ 最近图注不同两道闸区分——间隙大小本身区分不了这两类。
    误并风险（如实记录）：某图的图注未被 _CAPTION_RE 检出时，该图可能
    被亲和规则并入邻图一组。分组结果在 source_map 全量留痕
    （group_id/group_role），verify 按组呈现，人工可复核、可推翻。
    """
    if not figures:
        return []
    n = len(figures)
    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[ri] = rj

    # 每块的最近图注（只认 figure 类图注）
    nearest: list[dict | None] = []
    for fig in figures:
        best, best_dist = None, None
        for capb in fig_captions:
            d = _caption_dist(capb["bbox"], fig["bbox"])
            if best_dist is None or d < best_dist:
                best, best_dist = capb, d
        nearest.append(best)

    # A 图注亲和：最近图注相同 → 同组
    by_caption: dict[int, int] = {}
    for i, capb in enumerate(nearest):
        if capb is None:
            continue
        key = id(capb)
        if key in by_caption:
            union(by_caption[key], i)
        else:
            by_caption[key] = i

    # B 几何相邻：膨胀相交 + 无图注屏障 + 最近图注相容
    rects = [pymupdf.Rect(f["bbox"]) for f in figures]
    cap_rects = [pymupdf.Rect(c["bbox"]) for c in all_captions]
    for i in range(n):
        for j in range(i + 1, n):
            ei = pymupdf.Rect(rects[i].x0 - GROUP_GAP,
                              rects[i].y0 - GROUP_GAP,
                              rects[i].x1 + GROUP_GAP,
                              rects[i].y1 + GROUP_GAP)
            if not ei.intersects(rects[j]):
                continue
            if (nearest[i] is not None and nearest[j] is not None
                    and nearest[i] is not nearest[j]):
                continue  # 各自已有明确归属，不许几何规则强行合并
            bridge = rects[i] | rects[j]
            if any(bridge.intersects(cr) for cr in cap_rects):
                continue  # 两块之间夹着图注 → 是两幅独立图
            union(i, j)

    groups: dict[int, list[dict]] = {}
    for i, fig in enumerate(figures):
        groups.setdefault(find(i), []).append(fig)
    return list(groups.values())


# ---------- 表格 HTML → Markdown ----------

def html_table_to_md(html_body: str) -> tuple[str, int, int]:
    """Doc2X 的 HTML 表格 → Markdown 管道表，返回 (table_md, rows, cols)。

    用 checks 的 span 感知解析器展开 rowspan/colspan 成完整网格
    （被纵向合并的单元格文本在展开网格中重复出现）；单元格内的
    竖线转义、换行压成空格。空表返回 ("", 0, 0)。
    """
    parser = _TableParser()
    parser.feed(html_body or "")
    if not parser.rows:
        return "", 0, 0
    grid = expand_grid(parser.rows)
    cols = max((len(r) for r in grid), default=0)
    if cols == 0:
        return "", 0, 0

    def cell(text: str) -> str:
        return (text or "").replace("\n", " ").replace("|", "\\|").strip()

    lines = []
    for i, row in enumerate(grid):
        padded = row + [""] * (cols - len(row))
        lines.append("| " + " | ".join(cell(c) for c in padded) + " |")
        if i == 0:
            lines.append("| " + " | ".join("---" for _ in range(cols)) + " |")
    return "\n".join(lines), len(grid), cols


# ---------- 图资产物化 ----------

def _export_image_name(src: str) -> Optional[str]:
    """由 layout Figure 的 src URL 推出 convert 导出图文件名。

    src 形如 ``https://img.doc2x.noedgeai.com/{uid}_{page}.jpg?x=..&y=..
    &w=..&h=..&r=..``，导出 zip 内文件名是 ``{page}_{x}_{y}_{w}_{h}_{r}.jpg``
    （2026-10-20 实测样本核对：ResNet 篇 layout 9 个图块、导出 7 张，
    命名同构成立；未命中的小分片走 PDF 裁片兜底）。
    """
    if not src or not src.startswith("http"):
        return None
    parsed = urllib.parse.urlparse(src)
    stem = Path(parsed.path).stem  # {uid}_{page}
    if "_" not in stem:
        return None
    page = stem.rsplit("_", 1)[-1]
    query = urllib.parse.parse_qs(parsed.query)
    try:
        vals = [query[k][0] for k in ("x", "y", "w", "h", "r")]
    except (KeyError, IndexError):
        return None
    if not page.isdigit() or not all(v.lstrip("-").isdigit() for v in vals):
        return None
    return f"{page}_{'_'.join(vals)}.jpg"


def _prepare_figure_assets(blocks: list[dict], pdir: Path,
                           doc2x_dir: Path, pdf_path: Path) -> None:
    """把 figure 块的 asset 落到 <paper_dir>/assets/figures/（原地改写）。

    来源优先级：convert 导出图（doc2x_export）→ PDF bbox 裁片
    （pdf_crop）→ 整页渲染（page_render，无可用 bbox 时）。逐块在
    asset_source 记录实际来源，不许假装是 Doc2X 原图。
    """
    fig_dir = pdir / "assets" / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open(pdf_path)
    try:
        for seq, block in enumerate(blocks):
            if block.get("type") != "figure":
                continue
            src = str(block.get("asset") or "")
            dest: Optional[Path] = None
            source_kind: Optional[str] = None
            candidates: list[Path] = []
            name = _export_image_name(src)
            if name:
                candidates += [doc2x_dir / "images" / name,
                               doc2x_dir / name]
            if src and not src.startswith("http"):
                candidates += [doc2x_dir / src,
                               doc2x_dir / "images" / Path(src).name]
            for cand in candidates:
                if cand.is_file():
                    target = fig_dir / cand.name
                    if not target.exists():
                        shutil.copyfile(cand, target)
                    dest, source_kind = target, "doc2x_export"
                    break
            page_no = int(block.get("page") or 1)
            if dest is None and 1 <= page_no <= len(doc):
                page = doc[page_no - 1]
                bbox = block.get("bbox") or [0, 0, 0, 0]
                rect = None
                if len(bbox) == 4 and bbox[2] > bbox[0] \
                        and bbox[3] > bbox[1]:
                    if block.get("bbox_space") == "per_mille":
                        w, h = page.rect.width, page.rect.height
                        rect = pymupdf.Rect(bbox[0] / 1000 * w,
                                            bbox[1] / 1000 * h,
                                            bbox[2] / 1000 * w,
                                            bbox[3] / 1000 * h)
                    elif block.get("bbox_space") != "missing":
                        rect = pymupdf.Rect(bbox)
                if rect is not None:
                    fname = f"doc2x_p{page_no}_{seq}.png"
                    pix = page.get_pixmap(
                        clip=rect,
                        matrix=pymupdf.Matrix(CROP_ZOOM, CROP_ZOOM))
                    pix.save(fig_dir / fname)
                    dest, source_kind = fig_dir / fname, "pdf_crop"
                else:
                    fname = f"doc2x_p{page_no}_full_{seq}.png"
                    pix = page.get_pixmap(
                        matrix=pymupdf.Matrix(PAGE_RENDER_ZOOM,
                                              PAGE_RENDER_ZOOM))
                    pix.save(fig_dir / fname)
                    dest, source_kind = fig_dir / fname, "page_render"
            if dest is not None:
                block["asset"] = f"assets/figures/{dest.name}"
                block["asset_source"] = source_kind
    finally:
        doc.close()


# ---------- middle_json → source_map + 原文.md ----------

_APPENDIX_CAPTION_RE = re.compile(
    r"^\s*(Figure|Fig\.?|Table|图|表)\s*([A-Z])\s*\.\s*(\d+)",
    re.IGNORECASE)


def _caption_kind_number(block: dict, host_type: Optional[str]):
    """解析图注的类别与编号：文本正则优先，其次 caption_of 宿主类型。

    返回 (kind, number, series)：kind ∈ figure/table/other；number 只在
    figure/table 且确有编号时给出（verify 的编号序列检查只查这两类，
    无编号的图注降为 other，避免拿假编号污染序列）。附录编号
    （Table A.1 型）单列 series="appendix"、number 取点后数字，与正文
    编号分序列检查，避免 A.1 与 Table 1 撞号（实测：CEA 110856 附录六表）。
    """
    text = str(block.get("text") or "")
    m = _APPENDIX_CAPTION_RE.match(text)
    if m:
        word = m.group(1).lower()
        kind = "table" if word.startswith(("table", "表")) else "figure"
        return kind, int(m.group(3)), "appendix"
    m = _CAPTION_RE.match(text)
    if m:
        word = m.group(1).lower()
        kind = "table" if word.startswith(("table", "表")) else "figure"
        return kind, int(m.group(2)), "main"
    if host_type in ("figure", "table"):
        num = re.search(r"\d+", text)
        if num:
            return host_type, int(num.group(0)), "main"
    return "other", None, "main"


def build_source_map(blocks: list[dict], paper: dict,
                     page_scores: Optional[dict] = None,
                     parse_meta: Optional[dict] = None) -> tuple[dict, str, dict]:
    """纯函数：Doc2X middle_json 块 → (source_map, 原文.md 文本, 统计)。

    产物契约见模块 docstring 的转换规则；
    blocks 的顺序即文档顺序（页升序、页内 reading_order），
    caption_of 的下标以 blocks 原列表为准（解析在重排前完成）。
    """
    page_scores = page_scores or {}
    parse_meta = parse_meta or {}
    raw = list(blocks)
    by_raw_index = {i: b for i, b in enumerate(raw)}

    # 工作集：复制一份，boilerplate 单独留痕（与 extract 同口径）
    work: list[dict] = []
    boilerplates: list[dict] = []
    for i, b in enumerate(raw):
        item = dict(b)
        item["_raw_index"] = i
        if item.get("is_boilerplate"):
            boilerplates.append(item)
        else:
            work.append(item)
    # 文档顺序：页升序 + 页内 reading_order（layout 块）；MD 兜底块
    # 无 order_in_page，靠稳定排序保持其原始相对顺序。
    work.sort(key=lambda b: (int(b.get("page") or 1),
                             int(b.get("order_in_page") or 0)))

    # 图注碎片合并：Doc2X layout 常把一条表注拆成「标签块 + 正文块」
    # （如 "Table 1" 与 "Video lengths ..." 两块 caption_of 同指一表）。
    # 不合并则正文块被宿主 caption_id 漏认领成孤儿，且正文里的数字
    # （如 2.5-minute）会被编号兜底误当图号（实测：CEA 110856 十二表
    # 全中，verify 报 12 孤儿 + 编号重复）。同 caption_of 的碎片按文档
    # 序合并为一条：文本拼接、bbox 取并集、merged_from 留痕（与
    # extract 段落合并同口径）。
    frags_by_host: dict[int, list[dict]] = {}
    for item in work:
        if item["type"] == "caption" and item.get("caption_of") is not None:
            frags_by_host.setdefault(item["caption_of"], []).append(item)
    merged_away: set[int] = set()
    for frags in frags_by_host.values():
        if len(frags) < 2:
            continue
        head = frags[0]
        head["text"] = " ".join(
            str(f.get("text") or "").strip() for f in frags).strip()
        boxes = [f.get("bbox") or [0, 0, 0, 0] for f in frags]
        head["bbox"] = [min(b[0] for b in boxes), min(b[1] for b in boxes),
                        max(b[2] for b in boxes), max(b[3] for b in boxes)]
        head["merged_from"] = [f["_raw_index"] for f in frags]
        merged_away.update(id(f) for f in frags[1:])
    if merged_away:
        work = [w for w in work if id(w) not in merged_away]

    # 图注类别/编号（caption_of 宿主类型作推断兜底）
    for item in work:
        if item["type"] != "caption":
            continue
        host = by_raw_index.get(item.get("caption_of"))
        host_type = host.get("type") if isinstance(host, dict) else None
        kind, number, series = _caption_kind_number(item, host_type)
        item["_caption_kind"] = kind
        item["_caption_number"] = number
        item["_caption_series"] = series
        item["_host_raw"] = item.get("caption_of")

    # 图组（复用 extract 的分组规则：图注亲和 + 几何相邻）
    groups_by_page: dict[int, list[list[dict]]] = {}
    for page_no in sorted({int(b.get("page") or 1) for b in work}):
        figs = [b for b in work if b["type"] == "figure"
                and int(b.get("page") or 1) == page_no]
        if not figs:
            continue
        caps = [b for b in work if b["type"] == "caption"
                and int(b.get("page") or 1) == page_no]
        for c in caps:
            c["caption_kind"] = c["_caption_kind"]  # _group_figures 读此键
        fig_caps = [c for c in caps if c["_caption_kind"] == "figure"]
        groups_by_page[page_no] = _group_figures(
            figs, caps, fig_caps)
    group_of: dict[int, list[dict]] = {}
    for groups in groups_by_page.values():
        for group in groups:
            for member in group:
                group_of[id(member)] = group

    # 锚点分配（文档顺序、五命名空间独立计数，与 extract 同规则）
    counters = {"S": 0, "C": 0, "F": 0, "T": 0, "E": 0}

    def next_id(prefix: str) -> str:
        counters[prefix] += 1
        return f"{prefix}{counters[prefix]:03d}"

    for item in work:
        item["_id"] = next_id(_PREFIX[item["type"]])

    # 图注认领：caption_of 预约优先，其次组级/表级最近距离（extract 口径）
    caption_host: dict[int, dict] = {}     # id(caption) -> 图组首块 或 表块
    figure_caption: dict[int, dict] = {}   # id(figure) -> caption
    table_caption: dict[int, dict] = {}    # id(table) -> caption
    claimed: set[int] = set()
    for item in work:
        if item["type"] != "caption" or item.get("_host_raw") is None:
            continue
        host = by_raw_index.get(item["_host_raw"])
        if not isinstance(host, dict):
            continue
        host_item = next((w for w in work if w["_raw_index"] == item["_host_raw"]),
                         None)
        if host_item is None:
            continue
        if host_item["type"] == "figure":
            for member in group_of.get(id(host_item), [host_item]):
                figure_caption[id(member)] = item
            caption_host[id(item)] = group_of.get(
                id(host_item), [host_item])[0]
            claimed.add(id(item))
        elif host_item["type"] == "table":
            table_caption[id(host_item)] = item
            caption_host[id(item)] = host_item
            claimed.add(id(item))
    for groups in groups_by_page.values():
        for group in groups:
            if any(id(m) in figure_caption for m in group):
                continue
            union = [min(m["bbox"][0] for m in group),
                     min(m["bbox"][1] for m in group),
                     max(m["bbox"][2] for m in group),
                     max(m["bbox"][3] for m in group)]
            best, best_dist = None, None
            for cap in work:
                if cap["type"] != "caption" or id(cap) in claimed \
                        or cap["_caption_kind"] != "figure" \
                        or int(cap.get("page") or 1) != int(group[0].get("page") or 1):
                    continue
                d = _caption_dist(cap["bbox"], union)
                if best_dist is None or d < best_dist:
                    best, best_dist = cap, d
            if best is not None:
                for member in group:
                    figure_caption[id(member)] = best
                caption_host[id(best)] = group[0]
                claimed.add(id(best))
    for item in work:
        if item["type"] != "table" or id(item) in table_caption:
            continue
        best, best_dist = None, None
        for cap in work:
            if cap["type"] != "caption" or id(cap) in claimed \
                    or cap["_caption_kind"] != "table" \
                    or int(cap.get("page") or 1) != int(item.get("page") or 1):
                continue
            d = _caption_dist(cap["bbox"], item["bbox"])
            if best_dist is None or d < best_dist:
                best, best_dist = cap, d
        if best is not None:
            table_caption[id(item)] = best
            caption_host[id(best)] = item
            claimed.add(id(best))

    # 条目构建（字段契约与 extract 一致）
    entries: list[dict] = []
    order = 0
    rendered: list[tuple[dict, dict]] = []
    for item in work:
        order += 1
        bid = item["_id"]
        page_no = int(item.get("page") or 1)
        entry: dict = {
            "id": bid, "page": page_no, "type": item["type"],
            "order": order,
            "bbox": [round(float(v), 1) for v in (item.get("bbox") or [0, 0, 0, 0])],
            "provenance": item.get("provenance") or "engine:doc2x",
            "order_method": "doc2x_reading_order",
            "order_uncertain": False,
        }
        if item.get("bbox_space"):
            entry["bbox_space"] = item["bbox_space"]
        conf = item.get("confidence")
        if conf is None and page_no in page_scores:
            conf = round(float(page_scores[page_no]) / 100.0, 3)
        if conf is not None:
            entry["confidence"] = float(conf)
        btype = item["type"]
        if btype == "text":
            entry["text"] = str(item.get("text") or "")
            entry["text_level"] = int(item.get("text_level") or 0)
            if item.get("inline_latex"):
                entry["inline_latex"] = item["inline_latex"]
        elif btype == "caption":
            entry["text"] = str(item.get("text") or "")
            entry["caption_kind"] = item["_caption_kind"]
            if item["_caption_number"] is not None:
                entry["caption_number"] = item["_caption_number"]
            if item.get("_caption_series") == "appendix":
                entry["caption_series"] = "appendix"
            if item.get("merged_from"):
                entry["merged_from"] = item["merged_from"]
            host = caption_host.get(id(item))
            entry["host_id"] = host["_id"] if host else None
            if host is not None and host["type"] == "figure":
                members = group_of.get(id(host), [host])
                if len(members) > 1:
                    entry["host_ids"] = [m["_id"] for m in members]
        elif btype == "figure":
            entry["asset"] = str(item.get("asset") or "")
            if item.get("asset_source"):
                entry["asset_source"] = item["asset_source"]
            members = group_of.get(id(item), [item])
            entry["group_id"] = f"G-{members[0]['_id']}"
            entry["group_role"] = "sole" if len(members) == 1 else "fragment"
            cap = figure_caption.get(id(item))
            entry["caption_id"] = cap["_id"] if cap else None
            entry["no_caption"] = cap is None
        elif btype == "table":
            table_md, rows, cols = html_table_to_md(
                str(item.get("table_body") or ""))
            if not table_md and item.get("table_md"):
                table_md = str(item["table_md"])
                rows = table_md.count("\n") + 1
                cols = 0
            if not table_md and item.get("text"):
                table_md = str(item["text"])
                rows, cols = 1, 0
            entry["table_md"] = table_md
            entry["rows"] = rows
            entry["cols"] = cols
            if item.get("table_body"):
                entry["table_html"] = str(item["table_body"])
            cap = table_caption.get(id(item))
            entry["caption_id"] = cap["_id"] if cap else None
            entry["no_caption"] = cap is None
        elif btype == "equation":
            latex = str(item.get("latex") or "").strip()
            entry["text"] = latex or str(item.get("text") or "")
            if latex:
                entry["latex"] = latex
                entry["verify"] = {
                    "formula": "engine_latex",
                    "note": "Doc2X 转写 LaTeX；可编译性可用 "
                            "checks.check_formula_compilable 复核",
                }
            if item.get("equation_number"):
                entry["equation_number"] = str(item["equation_number"])
        entries.append(entry)
        rendered.append((item, entry))
    for item in boilerplates:
        entries.append({
            "id": None, "page": int(item.get("page") or 1),
            "type": "boilerplate", "order": None,
            "bbox": [round(float(v), 1)
                     for v in (item.get("bbox") or [0, 0, 0, 0])],
            "confidence": 0.9,
            "provenance": item.get("provenance") or "engine:doc2x",
            "text": str(item.get("text") or ""),
        })

    # 原文.md 渲染（格式与 extract 对齐，文件头标明 Doc2X 轨与参数）
    params = parse_meta.get("engine_params") or {}
    md_parts: list[str] = [
        f"# {paper.get('title') or paper.get('paper_id')}\n",
        f"> paper_id: {paper.get('paper_id')}｜本文件由 Doc2X 解析生成"
        f"（backend=doc2x，model={params.get('model')}，"
        f"formula_mode={params.get('formula_mode')}，"
        f"formula_level={params.get('formula_level')}，"
        f"merge_cross_page_forms={params.get('merge_cross_page_forms')}），"
        "块首锚点与 source_map.json 对应。\n",
    ]
    by_anchor = {e["id"]: e for e in entries if e.get("id")}
    for item, entry in rendered:
        bid, page_no = entry["id"], entry["page"]
        src = f"**Source:** p.{page_no} {bid}"
        btype = entry["type"]
        if btype == "text":
            head = "## " if entry.get("text_level") == 1 else \
                "### " if entry.get("text_level") == 2 else ""
            md_parts.append(
                f'\n<a id="{bid}"></a>\n{src}\n\n{head}{entry["text"]}\n')
        elif btype == "caption":
            md_parts.append(
                f'\n<a id="{bid}"></a>\n{src}\n\n*Caption:* {entry["text"]}\n')
        elif btype == "figure":
            cap = by_anchor.get(entry.get("caption_id") or "")
            cap_txt = (f'{cap["id"]} — {cap["text"]}'
                       if cap else "no_caption（未检测到图注，待复核）")
            members = group_of.get(id(item), [item])
            group_txt = (
                f"**Figure group:** {entry['group_id']}"
                f"（本图共 {len(members)} 个分片，图注由整组共享）\n"
                if entry.get("group_role") == "fragment" else "")
            md_parts.append(
                f'\n<a id="{bid}"></a>\n{src}\n\n'
                f'![{bid}]({entry["asset"]})\n\n'
                f"**Placed near:** p.{page_no}\n{group_txt}"
                f"**Caption:** {cap_txt}\n")
        elif btype == "table":
            md_parts.append(
                f'\n<a id="{bid}"></a>\n{src}\n\n{entry["table_md"]}\n')
        elif btype == "equation":
            if entry.get("latex"):
                num = (f"\n公式编号：{entry['equation_number']}\n"
                       if entry.get("equation_number") else "")
                md_parts.append(
                    f'\n<a id="{bid}"></a>\n{src}\n\n'
                    f'$$\n{entry["latex"]}\n$$\n{num}')
            else:
                md_parts.append(
                    f'\n<a id="{bid}"></a>\n{src}\n\n'
                    f"> 公式（Doc2X 未给出 LaTeX 转写）：{entry['text']}\n")

    smap = {
        "paper_id": paper.get("paper_id"),
        "title": paper.get("title"),
        "sha256": paper.get("sha256"),
        "backend": "doc2x",
        "parse": parse_meta,
        "blocks": entries,
        "pending_pages": [],
    }
    if paper.get("triage"):
        smap["triage"] = {"summary": paper["triage"].get("summary"),
                          "pages": paper["triage"].get("pages")}
    stats = {
        "anchors": dict(counters),
        "total_blocks": len(entries),
        "assets": sum(1 for e in entries if e.get("asset")),
        "figure_groups": len({e["group_id"] for e in entries
                              if e["type"] == "figure"}),
        "multi_fragment_groups": len({
            e["group_id"] for e in entries
            if e["type"] == "figure" and e.get("group_role") == "fragment"}),
    }
    return smap, "".join(md_parts), stats


# ---------- 编排 ----------

def _record_awaiting(pdir: Path, paper: dict, params: dict,
                     reason: str, uid: Optional[str] = None) -> None:
    """把 parse 状态置为 awaiting_model_direct 并落盘（不覆盖既有产物）。"""
    record = {
        "backend": "doc2x",
        "status": "awaiting_model_direct",
        "engine_params": params,
        "error": reason,
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    if uid:
        record["uid"] = uid
    paper["parse"] = record
    save_paper_yaml(pdir, paper)


def parse(paper_dir: Path, backend: str = "doc2x",
          engine: Optional[Doc2XEngine] = None) -> dict:
    """产品解析（Doc2X 轨）：生成 source_map.json 与 原文.md。

    失败（未配置/额度/超时/服务错误）不回退本地管线：置
    paper.yaml `parse.status = awaiting_model_direct` 后抛错，
    由执行方改走模型直读轨（见 SKILL.md §5）。
    """
    pdir = Path(paper_dir)
    if not (pdir / "paper.yaml").exists():
        raise FileNotFoundError(f"不是有效的论文目录（缺 paper.yaml）：{pdir}")
    if backend != "doc2x":
        raise ValueError(
            f"parse 的产品路径只有 Doc2X（收到 --backend {backend}）；"
            "本地抽取属于研究/对照工具、不是产品解析路径，"
            "未包含在产品发布中（见 SKILL.md §5 解析双轨制）")
    project_dir, paper_id = pdir.parent.parent, pdir.name
    pdir, paper = load_paper_yaml(project_dir, paper_id)
    pdf = pdir / "原文.pdf"
    if not pdf.exists():
        raise FileNotFoundError(f"原文.pdf 不存在：{pdf}")
    # 分诊是本地管线保留的产品角色（审计数值进 source_map），缺失时先补
    if not paper.get("triage"):
        triage_mod.triage(project_dir, paper_id)
        paper = read_yaml(pdir / "paper.yaml")

    doc2x_dir = pdir / "doc2x"
    engine = engine or Doc2XEngine(output_dir=doc2x_dir)
    params = {
        "model": engine.model,
        "formula_mode": engine.formula_mode,
        "formula_level": engine.formula_level,
        "merge_cross_page_forms": engine.merge_cross_page_forms,
    }
    hint = ("请用户配置 Doc2X Key 后重跑 parse，或按 SKILL.md §5 "
            "模型直读轨由模型直接读 原文.pdf 撰写四件套"
            "（provenance=model-direct）")
    if not engine.available():
        reason = "Doc2X 凭据不可用（未配置 Key 或凭据通道不可用）"
        _record_awaiting(pdir, paper, params, reason)
        raise EngineUnavailableError(
            f"{reason}；paper.yaml 已置 awaiting_model_direct。{hint}")
    try:
        blocks = engine.parse(pdf)
    except (EngineUnavailableError, Doc2XError) as exc:
        uid = (engine.last_run or {}).get("uid")
        _record_awaiting(pdir, paper, params, str(exc), uid=uid)
        raise type(exc)(f"{exc}；paper.yaml 已置 awaiting_model_direct。"
                        f"{hint}") from exc
    if not blocks:
        reason = "Doc2X 解析返回空结果（0 块）"
        _record_awaiting(pdir, paper, params, reason,
                         uid=(engine.last_run or {}).get("uid"))
        raise Doc2XError(f"{reason}；paper.yaml 已置 awaiting_model_direct。"
                         f"{hint}")

    run = engine.last_run or {}
    result_path = doc2x_dir / "doc2x_result.json"
    page_scores: dict[int, float] = {}
    if result_path.exists():
        result = read_json(result_path)
        for entry in result.get("pages") or []:
            if isinstance(entry, dict) \
                    and isinstance(entry.get("score"), (int, float)):
                page_scores[int(entry.get("page_idx") or 0) + 1] = \
                    entry["score"]
    _prepare_figure_assets(blocks, pdir, doc2x_dir, pdf)
    parse_meta = {
        "backend": "doc2x",
        "engine_params": params,
        "uid": run.get("uid"),
        "parsed_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    smap, md_text, stats = build_source_map(
        blocks, paper, page_scores=page_scores, parse_meta=parse_meta)
    write_json(pdir / "source_map.json", smap)
    (pdir / "原文.md").write_text(md_text, encoding="utf-8")

    pages = int(paper.get("pages") or 0)
    paper["parse"] = {
        "backend": "doc2x",
        "status": "done",
        "engine_params": params,
        "uid": run.get("uid"),
        "parsed_at": parse_meta["parsed_at"],
        "anchors": stats["anchors"],
    }
    paper.setdefault("status", {})["extract"] = "done"
    save_paper_yaml(pdir, paper)
    return {
        "paper_id": paper_id,
        "backend": "doc2x",
        "pages": pages,
        "estimated_cost_cny": [round(pages * 0.01, 2),
                               round(pages * 0.02, 2)],
        "uid": run.get("uid"),
        **stats,
    }
