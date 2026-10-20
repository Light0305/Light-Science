"""审计引擎（F6，约束 12/13/14/15，拍板 D1/D3/D6）：七门在最终
产物上实测，产物落 audit/<fig_id>.audit.json 并绑定交付物哈希——
产物变更后 audit-status 报 STALE，旧审计不许冒充新鲜（约束 13：
改动必重跑）。

七门与线别适用性：
- alignment / collisions / glyph：最终 PDF 实测（PyMuPDF），数据图线；
  方法图在 Phase 2 无 PDF 交付物 → 不适用（applicable=false），
  不许以 NOT_AUDITABLE 冒充已审、也不许声称通过；
- contract：双线（数据图查 PDF 尺寸/格式/文本/色板；方法图查
  manifest 与路线口径）；
- native：方法图 .vsdx 包内 media 清单 + 形状数机械审计；
- honesty：数据图，判据来自脚本头登记（D6 分层硬度：反转轴阻断、
  截断未声明阻断、宽高比/面积编码登记 + 警告、缺登记落 REVIEW）；
- policy_block：方法图，交付集文件哈希与 provenance 参考图哈希
  比对（全线唯一政策硬拦，D1）。

判决四态（schema.AUDIT_VERDICTS）：PASS / REVIEW_REQUIRED /
FIX_BEFORE_DELIVERY / NOT_AUDITABLE。缺测对象（无量测清单、无
Tf 可测、账无哈希）一律 NOT_AUDITABLE，不许声称通过。PyMuPDF
缺失时 PDF 三门同态落 NOT_AUDITABLE 并点名依赖。
"""

from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path

from . import __version__, schema
from .produce import parse_script_header, script_path
from .project import load_package, provenance_row
from .redraw import load_manifest
from .util import dump_json, load_structured, sha256_file, utcnow

AUDIT_DIR = "audit"
_VERDICT_RANK = {"PASS": 0, "REVIEW_REQUIRED": 1,
                 "NOT_AUDITABLE": 2, "FIX_BEFORE_DELIVERY": 3}
_RASTER_EXTS = (".png", ".jpg", ".jpeg")


class AuditError(Exception):
    def __init__(self, gaps):
        self.gaps = list(gaps)
        super().__init__("；".join(self.gaps))


# ---------------------------------------------------------------- 上下文

class _Ctx:
    def __init__(self, root, pkg, fig_id):
        self.root = Path(root)
        self.pkg = pkg
        self.fig_id = fig_id
        self.row = next((r for r in pkg["head"].get("figures") or []
                         if r.get("fig_id") == fig_id), None)
        self.line = (self.row or {}).get("line")
        self.contract = pkg["contracts"].get(fig_id) or {}
        journal = pkg["journal_contract"] or {}
        self.journal = journal
        tolerances = dict(journal.get("tolerances") or {})
        for param, spec in schema.TOLERANCE_PARAMS.items():
            tolerances.setdefault(param, spec["default"])
        self.tolerances = tolerances
        self.artifact = artifact_for(self.root, pkg, fig_id)
        self.artifact_hash = sha256_file(self.artifact) \
            if self.artifact else None

    def tol(self, param):
        return float(self.tolerances[param])


def artifact_for(root, pkg, fig_id):
    """逐图最终产物（审计对象）：数据图 = exports/<fig>.pdf；
    方法图 = schematic/redraw/<fig>.vsdx。不存在返回 None。"""
    root = Path(root)
    row = next((r for r in (pkg["head"] or {}).get("figures") or []
                if r.get("fig_id") == fig_id), None)
    if row is None:
        return None
    if row.get("line") == "schematic":
        path = root / "schematic" / "redraw" / f"{fig_id}.vsdx"
    else:
        path = root / "exports" / f"{fig_id}.pdf"
    return path if path.exists() else None


def _gate(gate, verdict, findings=None, metrics=None, applicable=True):
    return {"gate": gate, "applicable": applicable, "verdict": verdict,
            "findings": findings or [], "metrics": metrics or {}}


def _na(gate, reason):
    return _gate(gate, "NOT_AUDITABLE",
                 [{"level": "fail", "code": f"{gate}.not_auditable",
                   "message": reason}])


def _skip(gate, reason):
    return _gate(gate, "PASS",
                 [{"level": "info", "code": f"{gate}.not_applicable",
                   "message": reason}], applicable=False)


def _compose(findings):
    if any(f["level"] == "fail" for f in findings):
        return "FIX_BEFORE_DELIVERY"
    if any(f["level"] == "warn" for f in findings):
        return "REVIEW_REQUIRED"
    return "PASS"


def _open_pdf(ctx):
    """(doc, None) 或 (None, reason)：依赖缺失/文件损坏如实落 NA。"""
    try:
        import pymupdf
    except ImportError:
        return None, ("PyMuPDF 未安装：pip install 'PyMuPDF>=1.24'"
                      "（缺测对象落 NOT_AUDITABLE，不许声称通过）")
    try:
        return pymupdf.open(ctx.artifact), None
    except Exception as e:
        return None, f"最终 PDF 无法打开：{e}"


# ---------------------------------------------------------------- 对齐门

def gate_alignment(ctx: _Ctx) -> dict:
    if ctx.line != "data":
        return _skip("alignment", "对齐门量测对象是数据图最终 PDF 的 "
                                  "plot-area 矩形")
    input_path = ctx.root / AUDIT_DIR / f"{ctx.fig_id}.alignment-input.json"
    if not input_path.exists():
        return _na("alignment", "缺 plot-area 量测清单 "
                                f"audit/{ctx.fig_id}.alignment-input.json"
                                "（量测由生产后端在最终布局上完成，"
                                "约束 13：无量测不许声称对齐通过）")
    data = load_structured(input_path)
    if data.get("artifact_sha256") != ctx.artifact_hash:
        return _na("alignment", "量测清单绑定旧产物哈希，与当前交付物"
                                "不一致：须重跑 produce 重新量测")
    findings = []
    tol = ctx.tol("alignment_pt")
    panels = data.get("panels") or []
    contract_ids = [p.get("panel_id")
                    for p in ctx.contract.get("panel_map") or []]
    measured_ids = [p["panel_id"] for p in panels]
    for pid in contract_ids:
        if pid not in measured_ids:
            findings.append({
                "level": "fail", "code": "alignment.panel_unmeasured",
                "message": f"合同面板 {pid} 无量测矩形（量测不完整）"})
    for pid in measured_ids:
        if contract_ids and pid not in contract_ids:
            findings.append({
                "level": "warn", "code": "alignment.panel_unknown",
                "message": f"量测面板 {pid} 不在图合同 panel_map 中"})
    exemptions = {}
    for ex in data.get("exemptions") or []:
        if not ex.get("reason"):
            findings.append({
                "level": "warn", "code": "alignment.exemption_no_reason",
                "message": f"对齐豁免 {ex.get('panel_id')} 缺理由"
                           "（豁免须登记理由，禁止调大容差掩盖例外）"})
        exemptions[ex.get("panel_id")] = ex
    active = [p for p in panels if p["panel_id"] not in exemptions]
    max_dev = 0.0

    def compare(group, edge_indexes, label):
        nonlocal max_dev
        if len(group) < 2:
            return
        for edge in edge_indexes:
            values = [p["bbox_pt"][edge] for p in group]
            dev = max(values) - min(values)
            max_dev = max(max_dev, dev)
            if dev > tol:
                ids = ", ".join(p["panel_id"] for p in group)
                findings.append({
                    "level": "fail", "code": "alignment.deviation",
                    "message": f"{label}（{ids}）边 {edge} 偏差 "
                               f"{dev:.2f} pt > 容差 {tol} pt"})

    rows, cols = {}, {}
    for p in active:
        rows.setdefault(p.get("row"), []).append(p)
        cols.setdefault(p.get("col"), []).append(p)
    for r, group in rows.items():
        compare(group, (1, 3), f"同行组 row={r}")
        ordered = sorted(group, key=lambda p: p["bbox_pt"][0])
        gaps = [ordered[i + 1]["bbox_pt"][0] - ordered[i]["bbox_pt"][2]
                for i in range(len(ordered) - 1)]
        if len(gaps) >= 2:
            spread = max(gaps) - min(gaps)
            max_dev = max(max_dev, spread)
            if spread > tol:
                findings.append({
                    "level": "fail", "code": "alignment.gutter",
                    "message": f"同行组 row={r} 的 gutter 不一致："
                               f"差 {spread:.2f} pt > 容差 {tol} pt"})
    for c, group in cols.items():
        compare(group, (0, 2), f"同列组 col={c}")
    if len(panels) <= 1:
        findings.append({
            "level": "info", "code": "alignment.single_panel",
            "message": "单面板图：无可比组，对齐门以量测清单在场为据"})
    if not any(f["level"] in ("fail", "warn") for f in findings) \
            and len(panels) > 1:
        findings.append({
            "level": "info", "code": "alignment.within_tolerance",
            "message": f"全部可比组边偏差 ≤ {tol} pt"})
    return _gate("alignment", _compose(findings), findings,
                 {"panels": len(panels), "max_deviation_pt": round(max_dev, 3),
                  "tolerance_pt": tol,
                  "exemptions": sorted(exemptions)})


# ---------------------------------------------------------------- 碰撞门

def gate_collisions(ctx: _Ctx) -> dict:
    if ctx.line != "data":
        return _skip("collisions", "碰撞门量测对象是最终 PDF 几何；"
                                   "方法图 Phase 2 无 PDF 交付物")
    doc, err = _open_pdf(ctx)
    if doc is None:
        return _na("collisions", err)
    inset = ctx.tol("collision_inset_pt")
    ratio = ctx.tol("collision_min_overlap_ratio")
    clip_tol = ctx.tol("collision_clip_pt")
    bg_ratio = ctx.tol("collision_background_exempt_ratio")
    findings = []
    counts = {"text_boxes": 0, "fail": 0, "warn": 0, "contained_info": 0}

    def overlap(a, b):
        x0 = max(a[0], b[0]); y0 = max(a[1], b[1])
        x1 = min(a[2], b[2]); y1 = min(a[3], b[3])
        if x1 <= x0 or y1 <= y0:
            return 0.0
        return (x1 - x0) * (y1 - y0)

    for page in doc:
        page_area = page.rect.width * page.rect.height
        texts = []
        for block in page.get_text("dict")["blocks"]:
            if block.get("type") != 0:
                continue
            for line in block.get("lines") or []:
                x0, y0, x1, y1 = line["bbox"]
                box = (x0 + inset, y0 + inset, x1 - inset, y1 - inset)
                if box[2] > box[0] and box[3] > box[1]:
                    texts.append(box)
        counts["text_boxes"] += len(texts)
        for box in texts:
            over = max(-box[0], -box[1],
                       box[2] - page.rect.width, box[3] - page.rect.height)
            if over > clip_tol:
                counts["fail"] += 1
                findings.append({
                    "level": "fail", "code": "collisions.text_clipped",
                    "message": f"文字框 {tuple(round(v, 1) for v in box)} "
                               f"出页 {over:.2f} pt > 裁剪容差 "
                               f"{clip_tol} pt"})
        for i in range(len(texts)):
            for j in range(i + 1, len(texts)):
                inter = overlap(texts[i], texts[j])
                smaller = min(
                    (texts[i][2] - texts[i][0]) * (texts[i][3] - texts[i][1]),
                    (texts[j][2] - texts[j][0]) * (texts[j][3] - texts[j][1]))
                if smaller > 0 and inter / smaller >= ratio:
                    counts["fail"] += 1
                    findings.append({
                        "level": "fail", "code": "collisions.text_text",
                        "message": f"文字-文字重叠：{tuple(round(v, 1) for v in texts[i])} 与 "
                                   f"{tuple(round(v, 1) for v in texts[j])} "
                                   f"重叠比 {inter / smaller:.2f} ≥ {ratio}"})
        strokes, areas = [], []
        for drawing in page.get_drawings():
            rect = (drawing["rect"].x0, drawing["rect"].y0,
                    drawing["rect"].x1, drawing["rect"].y1)
            if drawing.get("color") is not None \
                    and (rect[3] - rect[1] <= 3 or rect[2] - rect[0] <= 3):
                strokes.append(rect)
            if drawing.get("fill") is not None:
                areas.append(rect)
        for img in page.get_images(full=True):
            for rect in page.get_image_rects(img[0]):
                areas.append((rect.x0, rect.y0, rect.x1, rect.y1))
        for box in texts:
            box_area = (box[2] - box[0]) * (box[3] - box[1])
            if box_area <= 0:
                continue
            for stroke in strokes:
                if overlap(box, stroke) / box_area >= ratio:
                    counts["fail"] += 1
                    findings.append({
                        "level": "fail", "code": "collisions.text_stroke",
                        "message": f"文字被描边穿过：文字框 "
                                   f"{tuple(round(v, 1) for v in box)} 与线条 "
                                   f"{tuple(round(v, 1) for v in stroke)} 交叠"})
                    break
            for area in areas:
                area_size = (area[2] - area[0]) * (area[3] - area[1])
                if page_area > 0 and area_size / page_area >= bg_ratio:
                    continue  # 背景豁免（面积 ≥ 页面 20%）
                inter = overlap(box, area)
                frac = inter / box_area
                if frac >= 0.999:
                    counts["contained_info"] += 1
                elif frac > 0:
                    counts["warn"] += 1
                    findings.append({
                        "level": "warn", "code": "collisions.text_area_edge",
                        "message": f"文字与填充/图像边沿部分重叠 "
                                   f"（占文字框 {frac:.2f}）：须在最终"
                                   "尺寸下逐条看并记录处置理由"})
    return _gate("collisions", _compose(findings), findings, counts)


# ---------------------------------------------------------------- 字形门

_TF_RE = re.compile(rb"/[A-Za-z0-9_.\-+]+\s+([0-9]+(?:\.[0-9]+)?)\s+Tf")


def gate_glyph(ctx: _Ctx) -> dict:
    if ctx.line != "data":
        return _skip("glyph", "字形门量测对象是最终 PDF 内容流 Tf；"
                              "方法图 Phase 2 无 PDF 交付物")
    doc, err = _open_pdf(ctx)
    if doc is None:
        return _na("glyph", err)
    sizes = []
    for page in doc:
        for xref in page.get_contents():
            stream = doc.xref_stream(xref) or b""
            sizes.extend(float(m) for m in _TF_RE.findall(stream))
    floor = ctx.tol("glyph_floor_pt")
    if not sizes:
        return _na("glyph", "最终 PDF 内容流无 Tf 字号可测（文本可能"
                            "已转曲或为空）：缺测对象落 NOT_AUDITABLE")
    below = [s for s in sizes if s < floor - 1e-9]
    findings = []
    if below:
        findings.append({
            "level": "fail", "code": "glyph.below_floor",
            "message": f"实测最小字号 {min(sizes):.2f} pt < 地板 "
                       f"{floor} pt（{len(below)} 个 Tf 低于地板；"
                       "源级字号检查漏网的缩放字形在此拦截，约束 13）"})
    else:
        findings.append({
            "level": "info", "code": "glyph.above_floor",
            "message": f"实测最小字号 {min(sizes):.2f} pt ≥ 地板 "
                       f"{floor} pt"})
    return _gate("glyph", _compose(findings), findings,
                 {"min_pt": min(sizes), "samples": len(sizes),
                  "floor_pt": floor, "below_floor": len(below)})


# ---------------------------------------------------------------- 合同门

def gate_contract(ctx: _Ctx) -> dict:
    findings = []
    if ctx.line == "data":
        doc, err = _open_pdf(ctx)
        if doc is None:
            return _na("contract", err)
        formats = [str(f).lower()
                   for f in ctx.journal.get("formats_main") or []]
        if "pdf" not in formats:
            findings.append({
                "level": "fail", "code": "contract.format_not_whitelisted",
                "message": f"交付格式 pdf 不在期刊主图格式白名单 {formats}"})
        page = doc[0]
        w_mm = page.rect.width / 72 * 25.4
        h_mm = page.rect.height / 72 * 25.4
        columns = ctx.journal.get("columns_mm") or {}
        candidates = [v for v in (columns.get("single"),
                                  columns.get("double"))
                      if isinstance(v, (int, float))]
        if candidates and min(abs(w_mm - c) for c in candidates) > 1.0:
            findings.append({
                "level": "fail", "code": "contract.width_mismatch",
                "message": f"图宽 {w_mm:.1f} mm 与期刊栏宽 "
                           f"{candidates} 均不符（差 > 1 mm）"})
        max_h = ctx.journal.get("max_height_mm")
        if isinstance(max_h, (int, float)) and h_mm > max_h + 1.0:
            findings.append({
                "level": "fail", "code": "contract.height_exceeds",
                "message": f"图高 {h_mm:.1f} mm 超期刊最大高 {max_h} mm"})
        spans = sum(len(line.get("spans") or [])
                    for page_ in doc
                    for block in page_.get_text("dict")["blocks"]
                    if block.get("type") == 0
                    for line in block.get("lines") or [])
        if spans == 0:
            findings.append({
                "level": "warn", "code": "contract.no_editable_text",
                "message": "最终 PDF 无可抽取文本：文本可能已转曲"
                           "（期刊要求可编辑文本，约束 14）"})
        path = script_path(ctx.root, ctx.fig_id)
        if path.exists():
            text = path.read_text(encoding="utf-8")
            from .produce import _BANNED_CMAP_RE
            if _BANNED_CMAP_RE.search(text):
                findings.append({
                    "level": "fail", "code": "contract.banned_colormap",
                    "message": "绘图脚本使用禁用色标（rainbow/jet/hsv）"})
            try:
                header = parse_script_header(text)
            except ValueError:
                header = None
            palettes = (header or {}).get("palette") or {}
            for slot in ("categorical", "continuous"):
                declared = palettes.get(slot)
                registered = (ctx.journal.get("palettes") or {}).get(
                    slot) or {}
                if declared and registered.get("entry_id") \
                        and declared != registered["entry_id"]:
                    findings.append({
                        "level": "warn", "code": "contract.palette_mismatch",
                        "message": f"脚本声明色板 {slot}={declared} 与"
                                   f"期刊合同登记 {registered['entry_id']} "
                                   "不一致"})
        metrics = {"width_mm": round(w_mm, 2), "height_mm": round(h_mm, 2),
                   "text_spans": spans}
    else:
        manifest = load_manifest(ctx.root, ctx.fig_id)
        if manifest is None:
            findings.append({
                "level": "fail", "code": "contract.manifest_missing",
                "message": "方法图缺重绘 manifest（单一真相源）"})
            return _gate("contract", _compose(findings), findings)
        if manifest.get("route") not in schema.VISIO_ROUTES:
            findings.append({
                "level": "fail", "code": "contract.route_vocab",
                "message": f"重绘路线 {manifest.get('route')!r} 不在 "
                           f"{schema.VISIO_ROUTES}"})
        build = manifest.get("build") or {}
        if not build:
            findings.append({
                "level": "warn", "code": "contract.build_unrecorded",
                "message": "成品 .vsdx 无构建记录（非本工具构建或未登记）"})
        elif build.get("route") == "file_build" \
                and build.get("visio_verified") is not False:
            findings.append({
                "level": "fail", "code": "contract.visio_verified_false_claim",
                "message": "文件级路线产物被标 visio_verified≠false："
                           "未过 Visio 实机验证不许声称通过（拍板 D4）"})
        for residue in manifest.get("bitmap_residue") or []:
            if residue.get("class") not in schema.BITMAP_RESIDUE_CLASSES:
                findings.append({
                    "level": "fail", "code": "contract.residue_class",
                    "message": f"位图残留 {residue.get('residue_id')} 类别"
                               f" {residue.get('class')!r} 不在合法类别"})
        metrics = {"route": manifest.get("route"),
                   "build_recorded": bool(build)}
    if not findings:
        findings.append({"level": "info", "code": "contract.ok",
                         "message": "尺寸/格式/文本/色板与期刊合同相符"})
    return _gate("contract", _compose(findings), findings, metrics)


# ---------------------------------------------------------------- 原生性门

def _image_dims(data: bytes):
    """嵌入位图的真实像素尺寸（与 manifest 的 reference_size_px 同
    口径）。注意不许用 pymupdf 打开图像文档后的 page rect——那是按
    假定 DPI（无元数据时 96 dpi）换算的点数，不是像素数，用它比对
    会把整幅嵌入按 0.75 倍缩小漏检（Phase 3 演示变体实测抓出）。"""
    try:
        import pymupdf
        pix = pymupdf.Pixmap(data)
        return int(pix.width), int(pix.height)
    except Exception:
        pass
    try:
        import pymupdf
        doc = pymupdf.open(stream=data)
        rect = doc[0].rect
        return int(rect.width), int(rect.height)
    except Exception:
        return None


def gate_native(ctx: _Ctx) -> dict:
    if ctx.line != "schematic":
        return _skip("native", "原生性门只审方法图 .vsdx")
    try:
        zf = zipfile.ZipFile(ctx.artifact)
    except Exception as e:
        return _na("native", f".vsdx 无法按 OPC 包打开：{e}")
    names = zf.namelist()
    page_names = sorted(n for n in names
                        if re.match(r"visio/pages/page\d+\.xml$", n))
    if not page_names:
        return _na("native", ".vsdx 内无 visio/pages/pageN.xml，"
                             "形状数无从审计")
    import xml.etree.ElementTree as ET

    def count_shapes(name):
        tree = ET.fromstring(zf.read(name))
        return sum(1 for el in tree.iter()
                   if el.tag.rsplit("}", 1)[-1] == "Shape")

    page1_shapes = count_shapes(page_names[0])
    media = [n for n in names if n.startswith("visio/media/")]
    rasters = [n for n in media
               if n.lower().endswith(_RASTER_EXTS)]
    manifest = load_manifest(ctx.root, ctx.fig_id) or {}
    declared = {}
    for residue in manifest.get("bitmap_residue") or []:
        if residue.get("media_name"):
            declared[residue["media_name"]] = residue
    ref_size = (manifest.get("canvas") or {}).get("reference_size_px")
    findings = []
    for name in rasters:
        base = name.rsplit("/", 1)[-1]
        if base not in declared:
            findings.append({
                "level": "fail", "code": "native.undeclared_bitmap",
                "message": f"包内位图 {name} 未在重绘 manifest 登记"
                           "（未登记的位图不许出现在成品中，约束 12）"})
            continue
        dims = _image_dims(zf.read(name))
        if dims and ref_size and dims[0] >= 0.9 * ref_size[0] \
                and dims[1] >= 0.9 * ref_size[1]:
            findings.append({
                "level": "fail", "code": "native.full_page_bitmap",
                "message": f"位图 {name} 尺寸 {dims} ≈ 参考图全幅："
                           "登记的残留只许精确裁剪局部，整图嵌入即 FAIL"})
    if page1_shapes == 1 and rasters:
        findings.append({
            "level": "fail", "code": "native.one_shape_one_bitmap",
            "message": "首页恰好 1 个形状且含嵌入位图：不是真重建"
                       "（vsdx-trace 机械警告，约束 12）"})
    if page1_shapes == 0:
        findings.append({
            "level": "fail", "code": "native.no_shapes",
            "message": "首页形状数为 0：无原生对象"})
    for media_name in declared:
        if f"visio/media/{media_name}" not in names:
            findings.append({
                "level": "fail", "code": "native.residue_missing",
                "message": f"manifest 登记的位图残留 {media_name} "
                           "未在成品包内（登记与成品不符）"})
    trace = manifest.get("trace_layer") or {}
    if trace.get("used") and not trace.get("removed_before_delivery"):
        findings.append({
            "level": "fail", "code": "native.trace_layer_present",
            "message": "描图层用过但未确认交付前移除（参考图只许作"
                       "临时锁定描图层）"})
    metrics = {
        "page1_shapes": page1_shapes,
        "media": [{"name": n, "bytes": zf.getinfo(n).file_size}
                  for n in media],
        "raster_count": len(rasters),
        "declared_residues": sorted(declared),
    }
    if not findings:
        findings.append({
            "level": "info", "code": "native.ok",
            "message": f"首页 {page1_shapes} 个原生形状、位图 "
                       f"{len(rasters)} 个均有登记"})
    return _gate("native", _compose(findings), findings, metrics)


# ---------------------------------------------------------------- 诚实门

def gate_honesty(ctx: _Ctx) -> dict:
    if ctx.line != "data":
        return _skip("honesty", "诚实门只审数据图（拍板 D6）")
    path = script_path(ctx.root, ctx.fig_id)
    if not path.exists():
        return _na("honesty", "绘图脚本缺失，诚实判据无从落")
    text = path.read_text(encoding="utf-8")
    try:
        header = parse_script_header(text)
    except ValueError:
        header = None
    findings = []
    if header is None:
        findings.append({
            "level": "warn", "code": "honesty.unregistered",
            "message": "脚本无文件头登记块：坐标轴口径未登记，"
                       "诚实门落 REVIEW（缺登记不许默认诚实）"})
        return _gate("honesty", _compose(findings), findings)
    axes = header.get("axes")
    if not isinstance(axes, dict) or not axes:
        findings.append({
            "level": "warn", "code": "honesty.axes_unregistered",
            "message": "脚本头未登记 axes 坐标轴口径：落 REVIEW"})
    else:
        for name, axis in axes.items():
            if not isinstance(axis, dict):
                continue
            if axis.get("direction") == "decreasing":
                findings.append({
                    "level": "fail", "code": "honesty.reversed_axis",
                    "message": f"轴 {name} 为反转轴（direction="
                               "decreasing）：D6 分层硬度——反转轴阻断"
                               "（Pandey 2015：反转轴错误结论率 79%）"})
            declared = axis.get("truncation_declared") is True
            limits = axis.get("limits")
            dmin, dmax = axis.get("data_min"), axis.get("data_max")
            clipped = False
            if isinstance(limits, (list, tuple)) and len(limits) == 2 \
                    and isinstance(dmin, (int, float)) \
                    and isinstance(dmax, (int, float)):
                clipped = dmin < limits[0] - 1e-12 \
                    or dmax > limits[1] + 1e-12
            if axis.get("truncated") is True and not declared:
                findings.append({
                    "level": "fail", "code": "honesty.truncation_undeclared",
                    "message": f"轴 {name} 登记为截断（truncated）但无"
                               "截断声明：未声明阻断（D6）"})
            elif clipped and not declared:
                findings.append({
                    "level": "fail", "code": "honesty.data_clipped_undeclared",
                    "message": f"轴 {name} 范围 {limits} 裁掉数据 "
                               f"[{dmin}, {dmax}] 且未声明截断：阻断"})
            elif axis.get("truncated") is True and declared:
                findings.append({
                    "level": "info", "code": "honesty.truncation_declared",
                    "message": f"轴 {name} 截断已声明，放行留记录（D6）"})
    aspect = header.get("aspect")
    if not isinstance(aspect, dict) or aspect.get("declared") is not True:
        findings.append({
            "level": "warn", "code": "honesty.aspect_undeclared",
            "message": "宽高比未登记声明（aspect.declared）：登记 + "
                       "警告层（D6；宽高比失真感知夸张 ≈ +130%）"})
    area = header.get("area_encoding")
    if area is None:
        findings.append({
            "level": "warn", "code": "honesty.area_unregistered",
            "message": "面积编码未登记（area_encoding）：落 REVIEW"})
    elif area in ("area", "radius"):
        findings.append({
            "level": "warn", "code": "honesty.area_encoding",
            "message": f"面积编码已登记（area_encoding={area}）："
                       "登记 + 警告（D6；面积编码感知夸张 ≈ +59%）"})
    if not findings:
        findings.append({"level": "info", "code": "honesty.ok",
                         "message": "坐标轴口径登记齐全且无诚实红项"})
    return _gate("honesty", _compose(findings), findings,
                 {"axes_checked": len(axes) if isinstance(axes, dict)
                  else 0})


# ---------------------------------------------------------------- 政策硬拦

def gate_policy_block(ctx: _Ctx) -> dict:
    if ctx.line != "schematic":
        return _skip("policy_block", "政策硬拦对象是方法图的 AI "
                                     "参考图本体（数据图无参考图）")
    entry = provenance_row(ctx.pkg["provenance"], ctx.fig_id) or {}
    ref_hash = entry.get("reference_image_hash")
    if not ref_hash:
        return _na("policy_block", "provenance 账无参考图哈希："
                                   "硬拦无从比对（账为唯一事实源）")
    delivery = []
    exports_dir = ctx.root / "exports"
    if exports_dir.exists():
        delivery.extend(p for p in sorted(exports_dir.rglob("*"))
                        if p.is_file())
    if ctx.artifact and ctx.artifact not in delivery:
        delivery.append(ctx.artifact)
    findings = []
    for path in delivery:
        if sha256_file(path) == ref_hash:
            findings.append({
                "level": "fail", "code": "policy_block.reference_in_delivery",
                "message": f"交付集文件 {path.relative_to(ctx.root)} 的"
                           "哈希与参考图本体一致：AI 参考图本体不许"
                           "进入交付/投稿包（D1 全线唯一政策硬拦）"})
    if not findings:
        findings.append({
            "level": "info", "code": "policy_block.clear",
            "message": f"交付集 {len(delivery)} 个文件均与参考图哈希"
                       "不符（重绘成品不拦）"})
    return _gate("policy_block", _compose(findings), findings,
                 {"checked_files": len(delivery),
                  "reference_hash_prefix": str(ref_hash)[:12]})


GATE_FUNCS = {
    "alignment": gate_alignment,
    "collisions": gate_collisions,
    "glyph": gate_glyph,
    "contract": gate_contract,
    "native": gate_native,
    "honesty": gate_honesty,
    "policy_block": gate_policy_block,
}


# ---------------------------------------------------------------- 运行与状态

def record_path(root, fig_id) -> Path:
    return Path(root) / AUDIT_DIR / f"{fig_id}.audit.json"


def audit_figure(root, pkg, fig_id) -> dict:
    ctx = _Ctx(root, pkg, fig_id)
    old = None
    path = record_path(root, fig_id)
    if path.exists():
        try:
            old = load_structured(path)
        except Exception:
            old = None
    if ctx.artifact is None:
        record = {
            "kind": "light-figure/audit", "fig_id": fig_id,
            "line": ctx.line, "artifact": None, "artifact_sha256": None,
            "audited_at": utcnow(), "tool_version": __version__,
            "gates": {}, "overall": "NOT_AUDITABLE",
            "note": "无最终产物文件：审计无从执行（先 produce / redraw build）",
            "review_dispositions": {},
        }
    else:
        gates = {}
        for name in schema.AUDIT_GATES:
            gates[name] = GATE_FUNCS[name](ctx)
        applicable = [g for g in gates.values() if g["applicable"]]
        if applicable:
            overall = max((g["verdict"] for g in applicable),
                          key=lambda v: _VERDICT_RANK[v])
        else:
            overall = "NOT_AUDITABLE"
        dispositions = {}
        if old and old.get("artifact_sha256") == ctx.artifact_hash:
            dispositions = old.get("review_dispositions") or {}
        record = {
            "kind": "light-figure/audit", "fig_id": fig_id,
            "line": ctx.line,
            "artifact": str(ctx.artifact.relative_to(ctx.root)),
            "artifact_sha256": ctx.artifact_hash,
            "audited_at": utcnow(), "tool_version": __version__,
            "tolerances": ctx.tolerances,
            "gates": gates, "overall": overall,
            "review_dispositions": dispositions,
        }
    path.parent.mkdir(parents=True, exist_ok=True)
    dump_json(path, record)
    return record


def run_audit(root, fig_id: str | None = None) -> dict:
    root = Path(root)
    pkg = load_package(root)
    if pkg["head"] is None:
        raise AuditError(["图包不存在（先 init）"])
    ids = [fig_id] if fig_id else [
        r.get("fig_id") for r in pkg["head"].get("figures") or []]
    records = {}
    for fid in ids:
        records[fid] = audit_figure(root, pkg, fid)
    return {"figures": {
        fid: {"overall": rec["overall"],
              "artifact": rec.get("artifact"),
              "artifact_sha256": rec.get("artifact_sha256"),
              "gates": {name: g["verdict"]
                        for name, g in rec["gates"].items()
                        if g["applicable"]}}
        for fid, rec in records.items()}}


def audit_status(root) -> dict:
    """逐图审计新鲜度：FRESH / STALE / MISSING / NO_ARTIFACT。"""
    root = Path(root)
    pkg = load_package(root)
    if pkg["head"] is None:
        raise AuditError(["图包不存在（先 init）"])
    out = {}
    for row in pkg["head"].get("figures") or []:
        fig_id = row.get("fig_id")
        artifact = artifact_for(root, pkg, fig_id)
        path = record_path(root, fig_id)
        if artifact is None:
            out[fig_id] = {"state": "NO_ARTIFACT", "overall": None}
            continue
        if not path.exists():
            out[fig_id] = {"state": "MISSING", "overall": None,
                           "artifact_sha256": sha256_file(artifact)}
            continue
        record = load_structured(path)
        current = sha256_file(artifact)
        fresh = record.get("artifact_sha256") == current
        out[fig_id] = {
            "state": "FRESH" if fresh else "STALE",
            "overall": record.get("overall"),
            "artifact_sha256": current,
            "audited_at": record.get("audited_at"),
        }
    return {"figures": out}


def set_review_disposition(root, fig_id: str, gate: str,
                           reason: str) -> dict:
    """给 REVIEW_REQUIRED 门落处置理由（audited 门要求 WARN 逐条有
    处置落字）；审计已 STALE 时不许补记——先重跑。"""
    root = Path(root)
    status = audit_status(root)["figures"].get(fig_id)
    if status is None:
        raise AuditError([f"图 {fig_id} 不在逐图状态表中"])
    if status["state"] != "FRESH":
        raise AuditError([f"图 {fig_id} 审计状态为 {status['state']}："
                            "先重跑 audit run 使审计绑定当前产物，"
                            "再落处置理由"])
    if gate not in schema.AUDIT_GATES:
        raise AuditError([f"门 {gate!r} 不在审计门清单 {schema.AUDIT_GATES}"])
    if not reason:
        raise AuditError(["处置理由不许为空（WARN 逐条有处置理由落字）"])
    path = record_path(root, fig_id)
    record = load_structured(path)
    record.setdefault("review_dispositions", {})[gate] = reason
    dump_json(path, record)
    return {"fig_id": fig_id, "gate": gate, "reason": reason}
