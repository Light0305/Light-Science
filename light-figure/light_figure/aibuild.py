"""Illustrator 生产路线（第三条原生后端，用户 2026-10-21 裁决）。

定位（裁决原文）：Illustrator 与 Visio / PowerPoint 平权——对用户
给出的参考图做原生复刻，第二轮 FIG-D03 的「只做精修/印前」定位
已被推翻（SKILL §16.6 留痕）。技术地基（第二轮工具层深读实证）：
ExtendScript DOM 是 Illustrator 唯一完整控制面（路径锚点 + 双侧
手柄、文本框、图层、画板、颜色、导出全可数值设定并回读）；
scientific-illustrator-agent 证明「结构化规格 → .jsx 构建 → 原生
对象 → 回读 registry 对账」形态可跑；ie3jp 服务器证明 DOM 全量
枚举回读（对象/文本/锚点/置入图）是现成能力。

本模块的执行边界（如实落字）：.ai 格式不开放、无文件级从零构建
路——本模块生成 ExtendScript 构建脚本与回读脚本（文本产物），
实机执行在装有 Illustrator 的机器上完成；本环境（无 Adobe 软件）
只做到脚本生成 + 回读 JSON 登记对账，illustrator_verified 恒
false 至登记纪律满足（schema.AI_EVIDENCE_LEVELS 与构建单 J3）。

语义 ID 钉扎（构建单 J1）：对象 name = 语义 ID + PageItem.note
写 `light-figure:user-id=<id>` 双写，DOM 枚举回读按 note 对账。

坐标口径（构建单 J2）：manifest 几何沿用 redraw.shape_geometry
单一变换（英寸、pin 中心、Y 自页面底部量起）；.jsx 在脚本内以
place 换算为 ExtendScript 文档坐标（pt、Y 向上），回读脚本按
同一口径反算回英寸落 JSON，Python 侧只消费英寸口径。
"""

from __future__ import annotations

import re
from pathlib import Path

from . import schema
from .project import load_package, provenance_row
from .provenance import update_provenance_row
from .redraw import (
    check_arrow_plan, check_effective_fields, manifest_projection,
    shape_geometry,
)
from .style import role_hex
from .util import component_hash, dump_json, load_structured, sha256_file

AI_DIR = "schematic/redraw"
AI_SHAPE_KINDS = ["rect", "rounded_rect", "ellipse", "diamond",
                  "parallelogram", "line", "text", "image_residue"]
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


class AiError(Exception):
    def __init__(self, gaps):
        self.gaps = list(gaps)
        super().__init__("；".join(self.gaps))


def ai_manifest_path(root, fig_id) -> Path:
    return Path(root) / AI_DIR / f"{fig_id}.ai-manifest.json"


def ai_relpath(fig_id) -> str:
    return f"{AI_DIR}/{fig_id}.ai"


def build_jsx_relpath(fig_id) -> str:
    return f"{AI_DIR}/{fig_id}.build.jsx"


def readback_jsx_relpath(fig_id) -> str:
    return f"{AI_DIR}/{fig_id}.readback.jsx"


def readback_json_relpath(fig_id) -> str:
    return f"{AI_DIR}/{fig_id}.dom-readback.json"


# ---------------------------------------------------------------- 契约校验

def _box_ok(box) -> bool:
    return isinstance(box, (list, tuple)) and len(box) == 4 \
        and all(isinstance(v, (int, float)) and not isinstance(v, bool)
                for v in box)


def validate_ai_manifest(manifest, root=None) -> list:
    """ai manifest 契约校验（与 redraw/pptx manifest 同契约），
    返回 gaps（空 = 合法）。"""
    gaps = []
    if not isinstance(manifest, dict):
        return ["AI manifest 须为对象"]
    fig_id = manifest.get("fig_id") or "?"
    backend = manifest.get("backend")
    if backend is not None and backend != "illustrator_extendscript":
        gaps.append(f"图 {fig_id} ai manifest 的 backend "
                    f"{backend!r} 不是 illustrator_extendscript")
    reference = manifest.get("reference") or {}
    if not reference.get("path"):
        gaps.append(f"图 {fig_id} ai manifest 缺参考图指针 reference.path")
    if not _HEX64.match(str(reference.get("sha256") or "")):
        gaps.append(f"图 {fig_id} ai manifest 的 reference.sha256 "
                    "不是 SHA-256")
    canvas = manifest.get("canvas") or {}
    size_px = canvas.get("reference_size_px")
    if not (isinstance(size_px, (list, tuple)) and len(size_px) == 2
            and all(isinstance(v, (int, float)) and v > 0
                    for v in size_px)):
        gaps.append(f"图 {fig_id} ai manifest 缺画布标定 "
                    "canvas.reference_size_px")
    page_in = canvas.get("page_size_in")
    if not (isinstance(page_in, (list, tuple)) and len(page_in) == 2
            and all(isinstance(v, (int, float)) and v > 0
                    for v in page_in)):
        gaps.append(f"图 {fig_id} ai manifest 缺 canvas.page_size_in"
                    "（画板尺寸 = 图尺寸）")
    panels = {}
    for panel in manifest.get("panels") or []:
        pid = panel.get("panel_id")
        if not pid:
            gaps.append(f"图 {fig_id} ai manifest 面板缺 panel_id")
            continue
        if pid in panels:
            gaps.append(f"图 {fig_id} ai manifest 面板 id 重复：{pid}")
        panels[pid] = panel
        box = panel.get("pixel_box")
        if not _box_ok(box):
            gaps.append(f"图 {fig_id} 面板 {pid} 缺四角标定 pixel_box")
        elif box[2] <= 0 or box[3] <= 0:
            gaps.append(f"图 {fig_id} 面板 {pid} 的 pixel_box 宽高须为正")
    if not panels:
        gaps.append(f"图 {fig_id} ai manifest 无面板清单（四角标定先行）")

    seen_ids = set()
    for shape in manifest.get("shapes") or []:
        sid = shape.get("shape_id")
        if not sid:
            gaps.append(f"图 {fig_id} ai manifest 形状缺稳定语义 ID "
                        "shape_id")
            continue
        if sid in seen_ids:
            gaps.append(f"图 {fig_id} ai manifest 形状 ID 重复：{sid}")
        seen_ids.add(sid)
        if shape.get("type") not in AI_SHAPE_KINDS:
            gaps.append(f"图 {fig_id} 形状 {sid} 的 type "
                        f"{shape.get('type')!r} 不在词表 {AI_SHAPE_KINDS}")
        pid = shape.get("panel_id")
        if pid is not None and pid not in panels:
            gaps.append(f"图 {fig_id} 形状 {sid} 指向未标定面板 {pid}")
        box = shape.get("box_local")
        if not _box_ok(box):
            gaps.append(f"图 {fig_id} 形状 {sid} 缺局部坐标框 box_local")
        else:
            x, y, w, h = box
            if x < 0 or y < 0 or w <= 0 or h <= 0 \
                    or x + w > 1 + 1e-9 or y + h > 1 + 1e-9:
                gaps.append(f"图 {fig_id} 形状 {sid} 局部坐标越界："
                            f"box_local={box}")
        if shape.get("type") == "text" \
                and not str(shape.get("text") or "").strip():
            gaps.append(f"图 {fig_id} 文本形状 {sid} 无逐字文本")
    for shape in manifest.get("shapes") or []:
        connect = shape.get("connect") or {}
        for endpoint in ("from", "to"):
            target = connect.get(endpoint)
            if target is not None and target not in seen_ids:
                gaps.append(f"图 {fig_id} 形状 {shape.get('shape_id')} 的"
                            f"连接 {endpoint} 指向不存在的形状 {target}")
    gaps.extend(check_effective_fields(manifest, fig_id,
                                       label="ai manifest"))
    gaps.extend(check_arrow_plan(manifest, fig_id, seen_ids,
                                 label="ai manifest"))
    for residue in manifest.get("bitmap_residue") or []:
        rid = residue.get("residue_id") or "?"
        if residue.get("class") not in schema.BITMAP_RESIDUE_CLASSES:
            gaps.append(f"图 {fig_id} 位图残留 {rid} 的类别 "
                        f"{residue.get('class')!r} 不在合法类别 "
                        f"{schema.BITMAP_RESIDUE_CLASSES}")
        if not _box_ok(residue.get("box_local")):
            gaps.append(f"图 {fig_id} 位图残留 {rid} 缺精确裁剪框 "
                        "box_local")
        source = residue.get("source") or {}
        if not source.get("path") \
                or not _HEX64.match(str(source.get("sha256") or "")):
            gaps.append(f"图 {fig_id} 位图残留 {rid} 缺源文件指针/哈希")
        if residue.get("panel_id") is not None \
                and residue.get("panel_id") not in panels:
            gaps.append(f"图 {fig_id} 位图残留 {rid} 指向未标定面板 "
                        f"{residue.get('panel_id')}")
    if root is not None:
        root = Path(root)
        ref_path = root / str(reference.get("path") or "")
        if reference.get("path") and not ref_path.exists():
            gaps.append(f"参考图文件不存在：{reference.get('path')}")
        elif reference.get("path") \
                and sha256_file(ref_path) != reference.get("sha256"):
            gaps.append("ai manifest 登记的参考图哈希与包内文件不符")
        for residue in manifest.get("bitmap_residue") or []:
            src = root / str((residue.get("source") or {}).get("path")
                             or "")
            if not src.exists():
                gaps.append(f"位图残留 {residue.get('residue_id')} 的"
                            f"源文件不存在：{src}")
            elif sha256_file(src) != residue["source"]["sha256"]:
                gaps.append(f"位图残留 {residue.get('residue_id')} 的"
                            "源文件哈希与登记不符")
    return gaps


# ---------------------------------------------------------------- 登记

def init_ai_manifest(root, fig_id: str) -> dict:
    """按合同面板 + 已登记参考图生成 ai manifest 骨架（draft）。"""
    root = Path(root)
    pkg = load_package(root)
    contract = pkg["contracts"].get(fig_id)
    if contract is None:
        raise AiError([f"图 {fig_id} 无图合同（先 intake）"])
    entry = provenance_row(pkg["provenance"], fig_id) or {}
    if not entry.get("reference_image_hash"):
        raise AiError([f"图 {fig_id} 参考图尚未入包登记"
                        "（先 reference add）"])
    from .reference import reference_relpath
    from .redraw import default_effective_fields
    ref_rel = reference_relpath(root, fig_id)
    ref_size = None
    if ref_rel:
        try:
            import pymupdf
            doc = pymupdf.open(root / ref_rel)
            ref_size = [int(doc[0].rect.width), int(doc[0].rect.height)]
            doc.close()
        except Exception:
            ref_size = None
    manifest = {
        "fig_id": fig_id,
        "version": schema.MANIFEST_STRICT_VERSION,
        "status": "draft",
        "backend": "illustrator_extendscript",
        "reference": {"path": ref_rel,
                      "sha256": entry.get("reference_image_hash")},
        "canvas": {"reference_size_px": ref_size,
                   "page_size_in": [10.0, 7.5]},
        "role_palette": contract.get("role_palette_ref"),
        "panels": [
            {"panel_id": p.get("panel_id"), "pixel_box": None,
             "contract_panel_id": p.get("panel_id")}
            for p in contract.get("panel_map") or []
        ],
        "shapes": [],
        "bitmap_residue": [],
        "arrow_plan": [],
        "renderer_effective_fields": default_effective_fields(),
        "rounds": [],
        "build": None,
        "dom_readback": None,
        "preflight": None,
        "extracted_shapes_hash": None,
        "reconciliation": None,
    }
    path = ai_manifest_path(root, fig_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    dump_json(path, manifest)
    return manifest


def install_ai_manifest(root, fig_id: str, source) -> dict:
    root = Path(root)
    manifest = load_structured(Path(source))
    if not isinstance(manifest, dict):
        raise AiError(["ai manifest 文件不是对象"])
    if manifest.get("fig_id") != fig_id:
        raise AiError([f"ai manifest 的 fig_id "
                       f"{manifest.get('fig_id')!r} 与目标图 {fig_id} "
                       "不一致"])
    gaps = validate_ai_manifest(manifest, root=root)
    pkg = load_package(root)
    entry = provenance_row(pkg["provenance"], fig_id) or {}
    if entry.get("reference_image_hash") \
            and manifest["reference"]["sha256"] \
            != entry["reference_image_hash"]:
        gaps.append("ai manifest 参考图哈希与 provenance 账登记不一致")
    if gaps:
        raise AiError(gaps)
    manifest["status"] = "registered"
    path = ai_manifest_path(root, fig_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    dump_json(path, manifest)
    return manifest


def load_ai_manifest(root, fig_id: str) -> dict | None:
    path = ai_manifest_path(root, fig_id)
    if not path.exists():
        return None
    return load_structured(path)


def save_ai_manifest(root, manifest) -> None:
    dump_json(ai_manifest_path(root, manifest["fig_id"]), manifest)


# ---------------------------------------------------------------- ExtendScript 生成

def _jsx_str(value) -> str:
    """转义为 JS 双引号字符串字面量（生成脚本内的文本/名称）。"""
    out = []
    for ch in str(value):
        if ch == '"':
            out.append('\\"')
        elif ch == "\\":
            out.append("\\\\")
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\r":
            out.append("\\r")
        elif ord(ch) < 0x20:
            out.append(f"\\u{ord(ch):04x}")
        else:
            out.append(ch)
    return '"' + "".join(out) + '"'


def _n(value) -> str:
    return f"{float(value):.4f}"


def _shape_colors(shape, role_entry):
    """填充/描边解析（与 pptxbuild 文件级构建同口径：缺省皆 None）。"""
    style = shape.get("style") or {}
    fill = style.get("fill") or (
        role_hex(role_entry, style["fill_role"])
        if style.get("fill_role") else None)
    line = style.get("line") or (
        role_hex(role_entry, style["line_role"])
        if style.get("line_role") else None)
    return fill, line


def _style_js(shape, role_entry, var) -> list:
    """填充/描边落字（与文件级构建同口径：text 形状无填充无描边，
    line 形状不填充）。"""
    fill, line = _shape_colors(shape, role_entry)
    lines = []
    if shape["type"] == "text":
        lines.append(f"{var}.filled = false;")
        lines.append(f"{var}.stroked = false;")
        return lines
    if fill and shape["type"] != "line":
        lines.append(f"{var}.filled = true;")
        lines.append(f"{var}.fillColor = rgbColor({_jsx_str(fill)});")
    else:
        lines.append(f"{var}.filled = false;")
    if line:
        width = float((shape.get("style") or {}).get(
            "line_width_pt", 0.75))
        lines.append(f"{var}.stroked = true;")
        lines.append(f"{var}.strokeColor = rgbColor({_jsx_str(line)});")
        lines.append(f"{var}.strokeWidth = {_n(width)};")
    else:
        lines.append(f"{var}.stroked = false;")
    return lines


def _generate_build_jsx(manifest) -> str:
    """manifest → ExtendScript 从零重建脚本（文本产物）。

    几何在 Python 侧经 shape_geometry 单一变换算成文档坐标
    （pt、Y 向上、原点为画板左下）后以字面量写入脚本（构建单
    J2）；脚本只负责按字面量在 DOM 里落对象，不做二次变换。
    """
    fig_id = manifest["fig_id"]
    page_w, page_h = manifest["canvas"]["page_size_in"]
    role_entry = (manifest.get("role_palette") or {}).get("entry_id")
    shapes = list(manifest.get("shapes") or [])
    geoms = {}
    for shape in shapes:
        geoms[shape["shape_id"]] = shape_geometry(manifest, shape)
    out = []
    out.append("// light-figure Illustrator production route: "
               "ExtendScript rebuild script (generated, do not edit "
               "by hand; regenerate via `light-figure ai build`).")
    out.append(f"// figure: {fig_id}  backend: "
               "illustrator_extendscript")
    out.append("// Run inside Adobe Illustrator (File > Scripts > "
               "Other Script). Set PKG_ROOT to this figure "
               "package's absolute path on your machine first "
               "(forward slashes). The script creates a NEW "
               "document; it never touches an open document.")
    out.append("// Geometry literals below are document points "
               "(72 pt = 1 in), Y axis up, origin at the artboard "
               "bottom-left; they were computed from the redraw "
               "manifest by light-figure's single transform.")
    out.append("#target illustrator")
    out.append("app.userInteractionLevel = "
               "UserInteractionLevels.DONTDISPLAYALERTS;")
    out.append('var PKG_ROOT = ""; '
               "// <-- set to the figure package root (absolute, "
               "forward slashes)")
    out.append("function rgbColor(hex) {")
    out.append("  var c = new RGBColor();")
    out.append('  c.red = parseInt(hex.substring(1, 3), 16);')
    out.append('  c.green = parseInt(hex.substring(3, 5), 16);')
    out.append('  c.blue = parseInt(hex.substring(5, 7), 16);')
    out.append("  return c;")
    out.append("}")
    out.append(f"var doc = app.documents.add(DocumentColorSpace.RGB, "
               f"{_n(page_w * 72)}, {_n(page_h * 72)});")
    out.append('var layer = doc.activeLayer;')
    out.append('layer.name = "light-figure";')
    marker = schema.AI_USER_ID_MARKER
    arrow_marker = schema.AI_ARROW_MARKER

    count = 0
    for shape in shapes:
        if shape["type"] == "image_residue":
            continue  # 置入项统一在残留段落（与另两路同口径）
        geom = geoms[shape["shape_id"]]
        left = (geom["pin_x"] - geom["width"] / 2) * 72
        top = (geom["pin_y"] + geom["height"] / 2) * 72
        width = geom["width"] * 72
        height = geom["height"] * 72
        sid = shape["shape_id"]
        var = f"it{count}"
        stype = shape["type"]
        has_text = bool(shape.get("text"))
        if stype == "line" and has_text:
            raise AiError([f"形状 {sid} 是 line 且带文本：开放路径无 "
                           "Illustrator 原生文本承载形态——把文本拆为"
                           "独立 text 形状登记后再走本路线"])
        out.append(f"// shape {sid} ({stype})")
        # 先落路径并上样式；带文本的闭合形状再经 areaText 把路径转
        # 区域文本框（Illustrator 里形状承载文字的原生形态，填充/
        # 描边随路径保留），name/note 钉在最终对象上。
        if stype == "text":
            out.append(f"var {var}P = layer.pathItems.rectangle("
                       f"{_n(top)}, {_n(left)}, {_n(width)}, "
                       f"{_n(height)});")
            out.append(f"{var}P.filled = false; "
                       f"{var}P.stroked = false;")
        elif stype == "rect":
            out.append(f"var {var}P = layer.pathItems.rectangle("
                       f"{_n(top)}, {_n(left)}, {_n(width)}, "
                       f"{_n(height)});")
            out.extend(_style_js(shape, role_entry, f"{var}P"))
        elif stype == "rounded_rect":
            radius = min(width, height) * 0.18
            out.append(f"var {var}P = layer.pathItems.roundedRectangle("
                       f"{_n(top)}, {_n(left)}, {_n(width)}, "
                       f"{_n(height)}, {_n(radius)}, {_n(radius)});")
            out.extend(_style_js(shape, role_entry, f"{var}P"))
        elif stype == "ellipse":
            out.append(f"var {var}P = layer.pathItems.ellipse("
                       f"{_n(top)}, {_n(left)}, {_n(width)}, "
                       f"{_n(height)});")
            out.extend(_style_js(shape, role_entry, f"{var}P"))
        elif stype in ("diamond", "parallelogram", "line"):
            bottom = (geom["pin_y"] - geom["height"] / 2) * 72
            right = left + width
            cx, cy = geom["pin_x"] * 72, geom["pin_y"] * 72
            if stype == "diamond":
                pts = [(cx, bottom), (right, cy), (cx, top),
                       (left, cy)]
            elif stype == "parallelogram":
                off = width * 0.2
                pts = [(left + off, bottom), (right, bottom),
                       (right - off, top), (left, top)]
            else:
                pts = [(left, bottom), (right, top)]
            pts_js = ", ".join(f"[{_n(x)}, {_n(y)}]" for x, y in pts)
            out.append(f"var {var}P = layer.pathItems.add();")
            out.append(f"{var}P.setEntirePath([{pts_js}]);")
            if stype != "line":
                out.append(f"{var}P.closed = true;")
            out.extend(_style_js(shape, role_entry, f"{var}P"))
        else:  # pragma: no cover - 词表校验已拦
            raise AiError([f"形状 {sid} 的类型 {stype} 无 ExtendScript "
                           "落形形态"])
        if has_text or stype == "text":
            out.append(f"var {var} = layer.textFrames.areaText("
                       f"{var}P);")
            out.append(f"{var}.contents = "
                       f"{_jsx_str(shape.get('text') or '')};")
            font_pt = float((shape.get("style") or {}).get(
                "font_pt", 8))
            out.append(f"{var}.textRange.characterAttributes.size = "
                       f"{_n(font_pt)};")
            final_var = var
        else:
            final_var = f"{var}P"
        out.append(f"{final_var}.name = {_jsx_str(sid)};")
        out.append(f"{final_var}.note = {_jsx_str(marker + sid)};")
        count += 1

    # 连接线：每条 arrow_plan 绑定落一条线 + 三角箭头（端点取两形状
    # 中心；线对象以 arrow-<pid> 命名并在 note 里写绑定，与 PPTX
    # 连接器对象同口径）。
    import math
    plan = {e.get("arrow_plan_id"): e
            for e in manifest.get("arrow_plan") or []}
    drawn = set()
    for shape in shapes:
        connect = shape.get("connect") or {}
        pid = connect.get("arrow_plan_id")
        if not pid or pid in drawn:
            continue
        entry = plan.get(pid) or {}
        src = geoms.get(entry.get("from") or connect.get("from"))
        dst = geoms.get(entry.get("to") or connect.get("to"))
        if src is None or dst is None:
            raise AiError([f"arrow_plan {pid} 的端点形状未登记，"
                           "连接线无从落（清单与计划脱节）"])
        sx, sy = src["pin_x"] * 72, src["pin_y"] * 72
        tx, ty = dst["pin_x"] * 72, dst["pin_y"] * 72
        dx, dy = tx - sx, ty - sy
        norm = math.hypot(dx, dy) or 1.0
        ux, uy = dx / norm, dy / norm
        tipx, tipy = tx - ux * 4, ty - uy * 4
        basex, basey = tipx - ux * 11.5, tipy - uy * 11.5
        px, py = -uy, ux
        head_pts = [(tipx, tipy),
                    (basex + px * 4, basey + py * 4),
                    (basex - px * 4, basey - py * 4)]
        var = f"ar{len(drawn)}"
        out.append(f"// arrow {pid}: "
                   f"{entry.get('from')} -> {entry.get('to')}")
        out.append(f"var {var} = layer.pathItems.add();")
        out.append(f"{var}.setEntirePath([[{_n(sx)}, {_n(sy)}], "
                   f"[{_n(tipx)}, {_n(tipy)}]]);")
        out.append(f"{var}.stroked = true; {var}.filled = false;")
        out.append(f"{var}.strokeColor = rgbColor(\"#000000\");")
        out.append(f"{var}.strokeWidth = 0.75;")
        out.append(f"{var}.name = {_jsx_str('arrow-' + pid)};")
        out.append(f"{var}.note = {_jsx_str(arrow_marker + pid + ';from=' + str(entry.get('from')) + ';to=' + str(entry.get('to')))};")
        head_js = ", ".join(f"[{_n(x)}, {_n(y)}]" for x, y in head_pts)
        out.append(f"var {var}H = layer.pathItems.add();")
        out.append(f"{var}H.setEntirePath([{head_js}]);")
        out.append(f"{var}H.closed = true;")
        out.append(f"{var}H.filled = true; {var}H.stroked = false;")
        out.append(f"{var}H.fillColor = rgbColor(\"#000000\");")
        out.append(f"{var}H.name = {_jsx_str('arrow-' + pid + '-head')};")
        out.append(f"{var}H.note = "
                   f"{_jsx_str(marker + 'arrow-' + pid + '-head')};")
        drawn.add(pid)
        count += 2

    # 位图残留：置入项（只许登记过的六类残留；参考图本体永不置入）
    for residue in manifest.get("bitmap_residue") or []:
        bound = [s for s in shapes
                 if s.get("type") == "image_residue"
                 and s.get("residue_id") == residue["residue_id"]]
        geom_src = bound[0] if bound else {
            "panel_id": residue.get("panel_id"),
            "box_local": residue["box_local"]}
        geom = shape_geometry(manifest, geom_src)
        left = (geom["pin_x"] - geom["width"] / 2) * 72
        top = (geom["pin_y"] + geom["height"] / 2) * 72
        var = f"rs{count}"
        name = f"residue-{residue['residue_id']}"
        out.append(f"// placed residue {residue['residue_id']} "
                   f"({residue.get('class')})")
        out.append(f"var {var} = layer.placedItems.add();")
        out.append(f"{var}.file = new File(PKG_ROOT + "
                   f"{_jsx_str('/' + residue['source']['path'])});")
        out.append(f"{var}.width = {_n(geom['width'] * 72)};")
        out.append(f"{var}.height = {_n(geom['height'] * 72)};")
        out.append(f"{var}.position = [{_n(left)}, {_n(top)}];")
        out.append(f"{var}.name = {_jsx_str(name)};")
        out.append(f"{var}.note = {_jsx_str(marker + name)};")
        count += 1

    out.append("doc.saveAs(new File(PKG_ROOT + "
               + _jsx_str("/" + ai_relpath(fig_id)) + "));")
    out.append("// Done. Next: open the saved .ai, run the companion "
               "readback script, then register with "
               "`light-figure ai extract`.")
    return "\n".join(out) + "\n"


def _generate_readback_jsx(manifest) -> str:
    """DOM 枚举回读脚本：对象/文本/锚点/置入项 + preflight 事实。

    几何在脚本内由 geometricBounds 换算回包口径（英寸、pin 中心、
    Y 自画板底部量起）再落 JSON——SVG 导入静默丢字形的对账基准
    是文本逐字清单，不是对象计数（深读实证坑）。
    """
    fig_id = manifest["fig_id"]
    lines = [
        "// light-figure Illustrator route: DOM enumeration readback "
        "(generated).",
        f"// figure: {fig_id}",
        "// Open the target .ai in Illustrator, then run this "
        "script. It enumerates every page item (name / note / type / "
        "geometry / verbatim text), lists placed items, probes "
        "preflight facts, and writes a JSON record next to the "
        "manifest for `light-figure ai extract` to reconcile.",
        "// Geometry is converted back to the package convention "
        "in-script: inches, pin centre, Y measured from the "
        "artboard bottom.",
        "#target illustrator",
        'var PKG_ROOT = ""; '
        "// <-- set to the figure package root (absolute, forward "
        "slashes)",
        "function esc(s) { return String(s).replace(/\\\\/g, "
        '"\\\\\\\\").replace(/"/g, \'\\\\"\').replace(/\\n/g, '
        '"\\\\n").replace(/\\r/g, "\\\\r"); }',
        "function num(v) { return Math.round(v * 10000) / 10000; }",
        "var doc = app.activeDocument;",
        "var ab = doc.artboards[doc.artboardIndex].artboardRect;",
        "var items = [];",
        "var colorKinds = {};",
        "var whiteOverprint = false;",
        "var overprintProbe = true;",
        "for (var i = 0; i < doc.pageItems.length; i++) {",
        "  var it = doc.pageItems[i];",
        "  var b = it.geometricBounds;",
        "  var pinX = ((b[0] + b[2]) / 2 - ab[0]) / 72;",
        "  var pinY = ((b[1] + b[3]) / 2 - ab[3]) / 72;",
        "  var wIn = (b[2] - b[0]) / 72;",
        "  var hIn = (b[1] - b[3]) / 72;",
        "  var note = \"\";",
        "  try { note = it.note; } catch (e) {}",
        "  var text = null;",
        "  if (it.typename == \"TextFrame\") { text = it.contents; }",
        "  var entry = '{\"name\": \"' + esc(it.name) + '\", "
        "\"note\": \"' + esc(note) + '\", \"typename\": \"' + "
        "it.typename + '\", \"pin_x\": ' + num(pinX) + ', "
        "\"pin_y\": ' + num(pinY) + ', \"width\": ' + num(wIn) + "
        "', \"height\": ' + num(hIn) + ', \"text\": ' + "
        "(text === null ? \"null\" : '\"' + esc(text) + '\"') + '}';",
        "  if (it.typename == \"PlacedItem\") {",
        "    var fname = \"\"; var lok = false;",
        "    try { fname = it.file.name; lok = it.file.exists; } "
        "catch (e) {}",
        "    entry = entry.substring(0, entry.length - 1) + "
        "\", \"file\": \"' + esc(fname) + '\", \"linked_file_ok\": ' "
        "+ lok + '}';",
        "  }",
        "  items.push(entry);",
        "  try { if (it.fillColor) colorKinds[it.fillColor."
        "typename] = true; } catch (e) {}",
        "  try { if (it.strokeColor) colorKinds[it.strokeColor."
        "typename] = true; } catch (e) {}",
        "  try {",
        "    if (it.overprintFill && it.fillColor && "
        "it.fillColor.typename == \"RGBColor\" && "
        "it.fillColor.red == 255 && it.fillColor.green == 255 && "
        "it.fillColor.blue == 255) { whiteOverprint = true; }",
        "  } catch (e) { overprintProbe = false; }",
        "}",
        "var mixed = (colorKinds[\"RGBColor\"] && "
        "colorKinds[\"CMYKColor\"]) ? true : false;",
        "var pdfx = false;",
        "try {",
        "  var presets = app.PDFPresetsList;",
        "  for (var j = 0; j < presets.length; j++) {",
        "    if (String(presets[j]).indexOf(\"PDF/X\") >= 0 || "
        "String(presets[j]).indexOf(\"PDFX\") >= 0) { pdfx = true; }",
        "  }",
        "} catch (e) {}",
        "var space = String(doc.documentColorSpace);",
        "var json = '{\"app\": {\"name\": \"Adobe Illustrator\", "
        "\"version\": \"' + esc(app.version) + '\"}, ' +",
        "  '\"document\": {\"page_size_in\": [' + "
        "num((ab[2] - ab[0]) / 72) + ', ' + num((ab[1] - ab[3]) / "
        "72) + '], \"color_space\": \"' + esc(space) + '\"}, ' +",
        "  '\"items\": [' + items.join(\", \") + '], ' +",
        "  '\"preflight_facts\": {\"mixed_color_spaces\": ' + mixed "
        "+ ', \"white_overprint_detected\": ' + whiteOverprint + "
        "', \"white_overprint_probe\": ' + overprintProbe + ', "
        "\"pdfx_preset_available\": ' + pdfx + '}}';",
        "var outFile = new File(PKG_ROOT + "
        + _jsx_str("/" + readback_json_relpath(fig_id)) + ");",
        "outFile.open(\"w\");",
        "outFile.encoding = \"UTF-8\";",
        "outFile.write(json);",
        "outFile.close();",
    ]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- 构建（脚本生成）

def generate_build_scripts(root, fig_id: str, by: str | None = None) -> dict:
    """由 manifest 生成 ExtendScript 构建脚本 + 回读脚本（文本产物）。

    本环境无 Illustrator：生成即本命令的完成边界，实机执行与回读
    登记是后续步骤（extract），生成命令永不置 illustrator_verified。
    """
    root = Path(root)
    manifest = load_ai_manifest(root, fig_id)
    if manifest is None:
        raise AiError([f"图 {fig_id} 无 ai manifest"
                       "（先 ai init / install 登记）"])
    gaps = validate_ai_manifest(manifest, root=root)
    if gaps:
        raise AiError(gaps)
    if manifest["status"] == "draft":
        raise AiError(["ai manifest 仍为 draft 骨架（标定未落字）："
                       "补齐后经 ai install 登记再生成构建脚本"])
    projection_hash = component_hash(manifest_projection(manifest))
    rounds = manifest.get("rounds") or []
    if rounds and rounds[-1].get("projection_hash") == projection_hash:
        raise AiError([
            f"round_noop：本轮 ai manifest 内容投影与上一轮（round "
            f"{rounds[-1].get('round')}）完全相同，生成的脚本不会有"
            "任何实质变化——纯元数据轮次不许计为进展；先实质修改"
            "清单再 build（FIG-D06 口径，三路同构）"])
    build_text = _generate_build_jsx(manifest)
    readback_text = _generate_readback_jsx(manifest)
    build_path = root / build_jsx_relpath(fig_id)
    readback_path = root / readback_jsx_relpath(fig_id)
    build_path.parent.mkdir(parents=True, exist_ok=True)
    # ExtendScript 以 BOM UTF-8 落盘（ie3jp 文件传输形态同口径）
    build_path.write_bytes(b"\xef\xbb\xbf"
                           + build_text.encode("utf-8"))
    readback_path.write_bytes(b"\xef\xbb\xbf"
                              + readback_text.encode("utf-8"))
    build_digest = sha256_file(build_path)
    readback_digest = sha256_file(readback_path)

    from .util import utcnow
    manifest.setdefault("rounds", []).append({
        "round": len(manifest.get("rounds") or []) + 1,
        "at": utcnow(),
        "projection_hash": projection_hash,
        "artifact_sha256": build_digest,
    })
    manifest["status"] = "built"
    manifest["build"] = {
        "builder": "light-figure ai build (ExtendScript generation)",
        "backend": "illustrator_extendscript",
        # 脚本生成只给 script 级证据：未在 Illustrator 实机执行、
        # 未回读对账，不许声称已验证（与另两路 verified 纪律同构）
        "illustrator_verified": False,
        "evidence_level": "script",
        "scripts": {
            "build": {"path": build_jsx_relpath(fig_id),
                      "sha256": build_digest},
            "readback": {"path": readback_jsx_relpath(fig_id),
                         "sha256": readback_digest},
        },
        "artifact": ai_relpath(fig_id),
        "artifact_sha256": None,
        "gap": "构建脚本须在装有 Illustrator 的机器上执行（打开 "
               "Illustrator 运行 build.jsx 生成 .ai 后，再运行 "
               "readback.jsx 并经 ai extract 登记回读对账）；本环境"
               "无 Adobe 软件，实机部分未执行、未验证",
    }
    save_ai_manifest(root, manifest)
    return {
        "fig_id": fig_id,
        "build_script": build_jsx_relpath(fig_id),
        "readback_script": readback_jsx_relpath(fig_id),
        "build_script_sha256": build_digest,
        "illustrator_verified": False,
        "evidence_level": "script",
    }


# ---------------------------------------------------------------- DOM 回读对账

def _parse_note(note: str):
    """note → (user_semantic_id, arrow dict|None)：双写钉扎的读面。

    形态：user-id 记作 marker + <id>；箭头记作 arrow marker +
    <pid>;from=<a>;to=<b>（分号字段在 marker 之后整段解析，
    不许先按分号切碎再逐段认领——端点会丢）。
    """
    note = note or ""
    user_id = None
    arrow = None
    idx = note.find(schema.AI_USER_ID_MARKER)
    if idx >= 0:
        rest = note[idx + len(schema.AI_USER_ID_MARKER):]
        user_id = rest.split(";")[0].strip() or None
    idx = note.find(schema.AI_ARROW_MARKER)
    if idx >= 0:
        rest = note[idx + len(schema.AI_ARROW_MARKER):]
        segments = rest.split(";")
        arrow = {"arrow_plan_id": segments[0].strip()}
        for seg in segments[1:]:
            if "=" in seg:
                key, value = seg.split("=", 1)
                arrow[key.strip()] = value.strip()
    return user_id, arrow


def parse_dom_readback(data) -> dict:
    """回读 JSON 形态校验与规范化（readback.jsx 的产出契约）。

    入参为已解析的 JSON 对象；返回 {app, document, shapes,
    placed_items, preflight_facts}。shapes 的几何口径与
    extract_pptx_shapes 一致（英寸、pin 中心、Y 自画板底部量起）。
    """
    if not isinstance(data, dict):
        raise AiError(["DOM 回读文件须为 JSON 对象（readback.jsx 产出）"])
    app = data.get("app") or {}
    if not isinstance(app, dict) or not app.get("name"):
        raise AiError(["DOM 回读缺 app.name（回读须注明宿主应用，"
                       "证据须带来源）"])
    items = data.get("items")
    if not isinstance(items, list):
        raise AiError(["DOM 回读缺 items 列表（DOM 枚举结果）"])
    shapes = []
    placed = []
    for item in items:
        if not isinstance(item, dict) or not item.get("name"):
            raise AiError(["DOM 回读 items 条目须为带 name 的对象"])
        user_id, arrow = _parse_note(str(item.get("note") or ""))
        entry = {
            "shape_id": item.get("name"),
            "user_semantic_id": user_id,
            "typename": item.get("typename"),
            "pin_x": item.get("pin_x"),
            "pin_y": item.get("pin_y"),
            "width": item.get("width"),
            "height": item.get("height"),
            "text": str(item.get("text") or "").strip(),
            "arrow": arrow,
        }
        if item.get("typename") == "PlacedItem":
            entry["file"] = item.get("file")
            entry["linked_file_ok"] = item.get("linked_file_ok")
            entry["effective_ppi"] = None  # extract 按源图实测补算
            placed.append(entry)
        else:
            shapes.append(entry)
    return {
        "app": {"name": app.get("name"), "version": app.get("version")},
        "document": data.get("document") or {},
        "shapes": sorted(shapes, key=lambda s: str(s["shape_id"])),
        "placed_items": sorted(placed, key=lambda s: str(s["shape_id"])),
        "preflight_facts": data.get("preflight_facts") or {},
    }


def _image_dims(data: bytes):
    """嵌入/源位图的真实像素尺寸（与 audit 同口径：用 Pixmap 实测，
    不用假定 DPI 换算的点数冒充像素数）。"""
    try:
        import pymupdf
        pix = pymupdf.Pixmap(data)
        return int(pix.width), int(pix.height)
    except Exception:
        return None, None


def compute_preflight(manifest, readback) -> dict:
    """印前五项终检：由 DOM 回读事实机械计算（构建单 J4）。

    true = 检出问题须处置；事实缺失的项不落键（produced 门会以
    「终检未齐」点名，不许默认无问题）。
    """
    facts = readback.get("preflight_facts") or {}
    placed = readback.get("placed_items") or []
    result = {}
    if "mixed_color_spaces" in facts:
        result["rgb_mixed"] = bool(facts["mixed_color_spaces"])
    result["broken_links"] = any(
        p.get("linked_file_ok") is False for p in placed)
    result["low_res_images"] = any(
        isinstance(p.get("effective_ppi"), (int, float))
        and p["effective_ppi"] < schema.AI_PLACED_PPI_FLOOR
        for p in placed)
    if facts.get("white_overprint_probe") is not False \
            and "white_overprint_detected" in facts:
        result["white_overprint"] = bool(
            facts["white_overprint_detected"])
    if "pdfx_preset_available" in facts:
        result["pdfx"] = not bool(facts["pdfx_preset_available"])
    return result


def extract_ai(root, fig_id: str, readback_file, by: str | None = None,
               ) -> dict:
    """登记 DOM 回读并与 ai manifest 对账（Illustrator 路线的
    extract：实机回读是唯一对账材料，本机不解析 .ai 二进制）。

    illustrator_verified 置真纪律（构建单 J3）：对账无差 + 回读
    带应用名/版本 + .ai 已存回本包 + 执行者以 by 落字，四件齐
    才许置真；生成命令与本命令的其余情形恒 false。
    """
    root = Path(root)
    manifest = load_ai_manifest(root, fig_id)
    if manifest is None:
        raise AiError([f"图 {fig_id} 无 ai manifest"])
    if not manifest.get("build"):
        raise AiError([f"图 {fig_id} 尚未生成构建脚本（先 ai build）："
                       "无构建记录不许登记回读"])
    data = load_structured(Path(readback_file))
    readback = parse_dom_readback(data)
    # 置入项有效分辨率：按包内残留源图实测像素 / 回读落位宽算
    residue_by_name = {f"residue-{r.get('residue_id')}": r
                       for r in manifest.get("bitmap_residue") or []}
    for item in readback["placed_items"]:
        residue = residue_by_name.get(item["shape_id"])
        width = item.get("width")
        if residue is not None and isinstance(width, (int, float)) \
                and width > 0:
            src = root / str((residue.get("source") or {}).get("path")
                             or "")
            if src.exists():
                pixel_w, _ = _image_dims(src.read_bytes())
                if pixel_w:
                    item["effective_ppi"] = round(pixel_w / width, 1)
    extracted = readback["shapes"]
    extracted_hash = component_hash({
        "shapes": extracted,
        "placed_items": readback["placed_items"],
    })
    expected = {}
    for shape in manifest.get("shapes") or []:
        if shape["type"] == "image_residue":
            continue
        geom = shape_geometry(manifest, shape)
        expected[shape["shape_id"]] = {
            **geom, "text": str(shape.get("text") or "").strip()}
    plan = {e.get("arrow_plan_id"): e
            for e in manifest.get("arrow_plan") or []}
    diffs = []
    got = {s["shape_id"]: s for s in extracted}
    for sid, exp in expected.items():
        if sid not in got:
            diffs.append(f"DOM 回读缺清单形状 {sid}（漏建）")
            continue
        act = got[sid]
        for key in ("pin_x", "pin_y", "width", "height"):
            if not isinstance(act.get(key), (int, float)) \
                    or abs(act[key] - exp[key]) > 0.02:
                diffs.append(f"形状 {sid} 的 {key} 与清单不符："
                             f"回读 {act.get(key)} vs 清单 "
                             f"{exp[key]:.3f}")
        if act["text"] != exp["text"]:
            diffs.append(f"形状 {sid} 文本与清单不符：回读 "
                         f"{act['text']!r} vs 清单 {exp['text']!r}"
                         "（文本逐字对账：SVG/脚本导入丢字以此抓，"
                         "不许只核计数）")
        if act.get("user_semantic_id") != sid:
            diffs.append(f"形状 {sid} 的 note User ID 为 "
                         f"{act.get('user_semantic_id')!r}，与清单语义 "
                         "ID 不一致（ID 钉扎对账，构建单 J1）")
    for pid, entry in plan.items():
        conn = got.get(f"arrow-{pid}")
        if conn is None:
            diffs.append(f"DOM 回读缺 arrow_plan {pid} 的连接线对象"
                         "（边事实未落成品）")
            continue
        arrow = conn.get("arrow") or {}
        if arrow.get("from") != entry.get("from") \
                or arrow.get("to") != entry.get("to"):
            diffs.append(f"连接线 arrow-{pid} 的端点与 arrow_plan "
                         f"登记不一致：回读 {arrow} vs 计划 {entry}")
        head = got.get(f"arrow-{pid}-head")
        if head is None:
            diffs.append(f"DOM 回读缺 arrow-{pid} 的箭头头对象")
        elif head.get("user_semantic_id") != f"arrow-{pid}-head":
            diffs.append(f"箭头头 arrow-{pid}-head 的 note User ID "
                         "未钉扎")
    placed_got = {p["shape_id"]: p for p in readback["placed_items"]}
    for name in residue_by_name:
        if name not in placed_got:
            diffs.append(f"DOM 回读缺登记位图残留的置入项 {name}")
    known = set(expected) | {f"arrow-{pid}" for pid in plan} \
        | {f"arrow-{pid}-head" for pid in plan} | set(residue_by_name)
    for sid in got:
        if sid not in known:
            diffs.append(f"DOM 回读含未登记对象 {sid}"
                         "（清单外对象不许出现）")
    for name in placed_got:
        if name not in residue_by_name:
            diffs.append(f"DOM 回读含未登记置入项 {name}"
                         "（未登记者不许以位图形态出现在成品中）")
    ok = not diffs
    note = None
    preflight = compute_preflight(manifest, readback)

    from .util import utcnow
    manifest["dom_readback"] = {
        "at": utcnow(),
        "source_file": Path(readback_file).name,
        "app": readback["app"],
        "document": readback["document"],
        "shapes": extracted,
        "placed_items": readback["placed_items"],
        "preflight_facts": readback["preflight_facts"],
        "extracted_shapes_hash": extracted_hash,
    }
    manifest["preflight"] = preflight
    manifest["extracted_shapes_hash"] = extracted_hash
    manifest["reconciliation"] = {"ok": ok, "diffs": diffs,
                                  "at": utcnow()}
    build = manifest.setdefault("build", {})
    if not ok:
        # 新回读推翻旧结论时先复位，不许留旧真值（三路同纪律）
        build["illustrator_verified"] = False
        build.pop("verified_by", None)
        build.pop("verified_at", None)
        manifest["status"] = "built"
    artifact = root / ai_relpath(fig_id)
    artifact_present = artifact.exists()
    if artifact_present:
        build["artifact_sha256"] = sha256_file(artifact)
    if ok:
        manifest["status"] = "verified"
        build["evidence_level"] = "dom_readback"
        app = readback["app"]
        if artifact_present and app.get("name") \
                and app.get("version") and by:
            build["illustrator_verified"] = True
            build["verified_by"] = by
            build["verified_at"] = utcnow()
            build.pop("gap", None)
        if artifact_present:
            update_provenance_row(root, fig_id, {
                "redraw_source": {
                    "path": ai_relpath(fig_id),
                    "hash": sha256_file(artifact)},
            }, by=by or "light-figure ai extract")
        else:
            note = ("对账已过但成品 .ai 未存回本包：先把实机"
                    "保存的 .ai 放到 schematic/redraw/ 再重跑 "
                    "extract，provenance 与 produced 门等它")
    save_ai_manifest(root, manifest)
    result = {
        "fig_id": fig_id, "ok": ok, "diffs": diffs,
        "extracted_shapes_hash": extracted_hash,
        "shapes_extracted": len(extracted),
        "illustrator_verified": bool(build.get("illustrator_verified")),
        "evidence_level": build.get("evidence_level"),
        "preflight": preflight,
    }
    if note:
        result["note"] = note
    return result
