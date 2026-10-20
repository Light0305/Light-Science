"""Visio 重绘（F5，约束 11/12，拍板 D4）：重绘 manifest 单一真相源 +
文件级从零构建 .vsdx（手写 OPC）+ 成品反抽对账。

路线三格（本模块的执行边界如实落字）：
- COM 原生重建（主路线）：须 Windows + Visio 环境经脚手架 helper
  执行，本模块只登记规程与 manifest 契约——本环境调用 build 时
  route=com 如实落 gap 停住，不许冒充已执行；
- 文件级从零构建（正式第二路线）：本模块实现——按 manifest 拼 OPC
  包直写 .vsdx，几何用多段线近似弧线（跨渲染器一致优先，学
  vsdx-trace）；产物正式交付但 visio_verified 恒为 false；
- 文件级后处理（vsdx 库）：不承担重建，不在本模块范围。

manifest 纪律：面板四角标定动手前落字、对象清单足以不读其他文件
重建本图、局部坐标越界即契约违规（校验与构建双断言，学
pengjunchi0 的运行期抛错）、位图残留预先声明（未登记者不许以
位图形态出现）、状态只经本模块命令推进（registered → built →
verified），不许手写。
"""

from __future__ import annotations

import io
import json
import re
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

from . import schema
from .project import load_package, provenance_row
from .provenance import update_provenance_row
from .style import role_hex
from .util import component_hash, dump_json, load_structured, sha256_file

REDRAW_DIR = "schematic/redraw"
SHAPE_TYPES = ["rect", "rounded_rect", "ellipse", "diamond",
               "parallelogram", "line", "text", "image_residue"]
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_ZIP_EPOCH = (1980, 1, 1, 0, 0, 0)  # 确定性打包（vsdx-trace 口径）

NS_MAIN = "http://schemas.microsoft.com/office/visio/2012/main"
NS_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


_ATTR_ESC = {'"': "&quot;"}  # saxutils.escape 的属性值转义实体集


class RedrawError(Exception):
    def __init__(self, gaps):
        self.gaps = list(gaps)
        super().__init__("；".join(self.gaps))


def manifest_path(root, fig_id) -> Path:
    return Path(root) / REDRAW_DIR / f"{fig_id}.manifest.json"


def vsdx_relpath(fig_id) -> str:
    return f"{REDRAW_DIR}/{fig_id}.vsdx"


# ---------------------------------------------------------------- manifest 校验

def _box_ok(box) -> bool:
    return isinstance(box, (list, tuple)) and len(box) == 4 \
        and all(isinstance(v, (int, float)) and not isinstance(v, bool)
                for v in box)


def validate_manifest(manifest, root=None) -> list:
    """manifest 契约校验，返回 gaps（空 = 合法）。root 给定时同时验
    引用文件存在与哈希相符。"""
    gaps = []
    if not isinstance(manifest, dict):
        return ["重绘 manifest 须为对象"]
    fig_id = manifest.get("fig_id") or "?"
    reference = manifest.get("reference") or {}
    if not reference.get("path"):
        gaps.append(f"图 {fig_id} manifest 缺参考图指针 reference.path")
    if not _HEX64.match(str(reference.get("sha256") or "")):
        gaps.append(f"图 {fig_id} manifest 的 reference.sha256 不是 SHA-256")
    canvas = manifest.get("canvas") or {}
    size_px = canvas.get("reference_size_px")
    if not (isinstance(size_px, (list, tuple)) and len(size_px) == 2
            and all(isinstance(v, (int, float)) and v > 0 for v in size_px)):
        gaps.append(f"图 {fig_id} manifest 缺画布标定 "
                    "canvas.reference_size_px（参考图像素尺寸）")
    page_in = canvas.get("page_size_in")
    if not (isinstance(page_in, (list, tuple)) and len(page_in) == 2
            and all(isinstance(v, (int, float)) and v > 0 for v in page_in)):
        gaps.append(f"图 {fig_id} manifest 缺 canvas.page_size_in"
                    "（目标页尺寸，英寸）")
    if manifest.get("route") not in schema.VISIO_ROUTES:
        gaps.append(f"图 {fig_id} manifest 的 route "
                    f"{manifest.get('route')!r} 不在 {schema.VISIO_ROUTES}")
    panels = {}
    for panel in manifest.get("panels") or []:
        pid = panel.get("panel_id")
        if not pid:
            gaps.append(f"图 {fig_id} manifest 面板缺 panel_id")
            continue
        if pid in panels:
            gaps.append(f"图 {fig_id} manifest 面板 id 重复：{pid}")
        panels[pid] = panel
        box = panel.get("pixel_box")
        if not _box_ok(box):
            gaps.append(f"图 {fig_id} 面板 {pid} 缺四角标定 pixel_box"
                        "（全局像素框 [x, y, w, h]，动手前落字）")
        elif box[2] <= 0 or box[3] <= 0:
            gaps.append(f"图 {fig_id} 面板 {pid} 的 pixel_box 宽高须为正")
    if not panels:
        gaps.append(f"图 {fig_id} manifest 无面板清单（四角标定先行）")

    seen_ids = set()
    for shape in manifest.get("shapes") or []:
        sid = shape.get("shape_id")
        if not sid:
            gaps.append(f"图 {fig_id} manifest 形状缺稳定语义 ID shape_id")
            continue
        if sid in seen_ids:
            gaps.append(f"图 {fig_id} manifest 形状 ID 重复：{sid}")
        seen_ids.add(sid)
        if shape.get("type") not in SHAPE_TYPES:
            gaps.append(f"图 {fig_id} 形状 {sid} 的 type "
                        f"{shape.get('type')!r} 不在词表 {SHAPE_TYPES}")
        pid = shape.get("panel_id")
        if pid is not None and pid not in panels:
            gaps.append(f"图 {fig_id} 形状 {sid} 指向未标定面板 {pid}")
        box = shape.get("box_local")
        if not _box_ok(box):
            gaps.append(f"图 {fig_id} 形状 {sid} 缺局部坐标框 box_local"
                        "（[x, y, w, h]，面板局部 0–1；缺坐标即契约违规）")
        else:
            x, y, w, h = box
            if x < 0 or y < 0 or w <= 0 or h <= 0 \
                    or x + w > 1 + 1e-9 or y + h > 1 + 1e-9:
                gaps.append(f"图 {fig_id} 形状 {sid} 局部坐标越界："
                            f"box_local={box}（局部坐标出界即断言，"
                            "不许漂移/串区）")
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

    media_names = set()
    for residue in manifest.get("bitmap_residue") or []:
        rid = residue.get("residue_id") or "?"
        if residue.get("class") not in schema.BITMAP_RESIDUE_CLASSES:
            gaps.append(f"图 {fig_id} 位图残留 {rid} 的类别 "
                        f"{residue.get('class')!r} 不在合法类别 "
                        f"{schema.BITMAP_RESIDUE_CLASSES}（约束 12："
                        "未登记者不许以位图形态出现在成品中）")
        if not _box_ok(residue.get("box_local")):
            gaps.append(f"图 {fig_id} 位图残留 {rid} 缺精确裁剪框 box_local")
        source = residue.get("source") or {}
        if not source.get("path") \
                or not _HEX64.match(str(source.get("sha256") or "")):
            gaps.append(f"图 {fig_id} 位图残留 {rid} 缺源文件指针/哈希")
        media = residue.get("media_name")
        if not media:
            gaps.append(f"图 {fig_id} 位图残留 {rid} 缺 media_name"
                        "（包内 media 条目名，native 门对账锚）")
        elif media in media_names:
            gaps.append(f"图 {fig_id} 位图残留 media_name 重复：{media}")
        media_names.add(media)
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
            gaps.append("manifest 登记的参考图哈希与包内文件不符")
        for residue in manifest.get("bitmap_residue") or []:
            src = root / str((residue.get("source") or {}).get("path") or "")
            if not src.exists():
                gaps.append(f"位图残留 {residue.get('residue_id')} 的"
                            f"源文件不存在：{src}")
            elif sha256_file(src) != residue["source"]["sha256"]:
                gaps.append(f"位图残留 {residue.get('residue_id')} 的"
                            "源文件哈希与登记不符")
    return gaps


def init_manifest(root, fig_id: str) -> dict:
    """按合同面板 + 已登记参考图生成 manifest 骨架（状态 draft）。

    骨架的 pixel_box 留空待标定——标定与对象清单由绘图人补齐后经
    install 登记（install 走全量契约校验），骨架本身不许直接 build。
    """
    root = Path(root)
    pkg = load_package(root)
    contract = pkg["contracts"].get(fig_id)
    if contract is None:
        raise RedrawError([f"图 {fig_id} 无图合同（先 intake）"])
    entry = provenance_row(pkg["provenance"], fig_id) or {}
    if not entry.get("reference_image_hash"):
        raise RedrawError([f"图 {fig_id} 参考图尚未入包登记"
                            "（先 reference add，manifest 须钉参考图哈希）"])
    from .reference import reference_relpath
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
        "version": "1.0",
        "status": "draft",
        "route": "file_build",
        "reference": {"path": ref_rel,
                      "sha256": entry.get("reference_image_hash")},
        "canvas": {"reference_size_px": ref_size,
                   "page_size_in": [11.0, 8.5]},
        "role_palette": contract.get("role_palette_ref"),
        "panels": [
            {"panel_id": p.get("panel_id"), "pixel_box": None,
             "contract_panel_id": p.get("panel_id")}
            for p in contract.get("panel_map") or []
        ],
        "shapes": [],
        "bitmap_residue": [],
        "trace_layer": {"used": False, "opacity": 0.25,
                        "removed_before_delivery": True},
        "label_check": {"done": False, "by": None, "at": None},
        "build": None,
        "extracted_shapes_hash": None,
        "reconciliation": None,
    }
    path = manifest_path(root, fig_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    dump_json(path, manifest)
    return manifest


def install_manifest(root, fig_id: str, source) -> dict:
    """把外部编成的 manifest 登记入包（全量契约校验 + 与 provenance
    参考图哈希对表），状态置 registered。"""
    root = Path(root)
    manifest = load_structured(Path(source))
    if not isinstance(manifest, dict):
        raise RedrawError(["manifest 文件不是对象"])
    if manifest.get("fig_id") != fig_id:
        raise RedrawError([f"manifest 的 fig_id "
                            f"{manifest.get('fig_id')!r} 与目标图 "
                            f"{fig_id} 不一致"])
    gaps = validate_manifest(manifest, root=root)
    pkg = load_package(root)
    entry = provenance_row(pkg["provenance"], fig_id) or {}
    if entry.get("reference_image_hash") \
            and manifest["reference"]["sha256"] \
            != entry["reference_image_hash"]:
        gaps.append("manifest 参考图哈希与 provenance 账登记不一致")
    if gaps:
        raise RedrawError(gaps)
    manifest["status"] = "registered"
    path = manifest_path(root, fig_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    dump_json(path, manifest)
    return manifest


def load_manifest(root, fig_id: str) -> dict | None:
    path = manifest_path(root, fig_id)
    if not path.exists():
        return None
    return load_structured(path)


def save_manifest(root, manifest) -> None:
    dump_json(manifest_path(root, manifest["fig_id"]), manifest)


# ---------------------------------------------------------------- 几何变换

def shape_geometry(manifest, shape) -> dict:
    """manifest 局部坐标 → Visio 页坐标（英寸）：两级标定（全局
    像素→英寸 + 面板局部 0–1），Y 轴翻转在此一处解决。"""
    canvas = manifest["canvas"]
    ref_w, ref_h = canvas["reference_size_px"]
    page_w, page_h = canvas["page_size_in"]
    panels = {p["panel_id"]: p for p in manifest.get("panels") or []}
    pid = shape.get("panel_id")
    if pid is not None:
        px, py, pw, ph = panels[pid]["pixel_box"]
    else:
        px, py, pw, ph = 0, 0, ref_w, ref_h
    lx, ly, lw, lh = shape["box_local"]
    gx, gy = px + lx * pw, py + ly * ph
    gw, gh = lw * pw, lh * ph
    sx, sy = page_w / ref_w, page_h / ref_h
    x_in, y_top = gx * sx, gy * sy
    w_in, h_in = gw * sx, gh * sy
    return {
        "pin_x": x_in + w_in / 2,
        "pin_y": page_h - (y_top + h_in / 2),
        "width": w_in, "height": h_in,
    }


def _geometry_points(shape_type, w, h):
    """局部几何（原点在形状左下角）：多段线近似弧线（vsdx-trace
    口径，跨渲染器一致优先）。返回 (points, closed)。"""
    import math

    if shape_type == "ellipse":
        pts = [(w / 2 + w / 2 * math.cos(2 * math.pi * i / 24),
                h / 2 + h / 2 * math.sin(2 * math.pi * i / 24))
               for i in range(24)]
        pts.append(pts[0])
        return pts, True
    if shape_type == "rounded_rect":
        r = min(w, h) * 0.18
        pts = [(r, 0), (w - r, 0)]
        for cx, cy, a0 in ((w - r, r, -90), (w - r, h - r, 0),
                           (r, h - r, 90), (r, r, 180)):
            for step in (45, 90):
                ang = math.radians(a0 + step)
                pts.append((cx + r * math.cos(ang),
                            cy + r * math.sin(ang)))
        pts.append(pts[0])
        return pts, True
    if shape_type == "diamond":
        return [(w / 2, 0), (w, h / 2), (w / 2, h), (0, h / 2),
                (w / 2, 0)], True
    if shape_type == "parallelogram":
        off = w * 0.2
        return [(off, 0), (w, 0), (w - off, h), (0, h), (off, 0)], True
    if shape_type == "line":
        return [(0, 0), (w, h)], False
    # rect / text / image_residue
    return [(0, 0), (w, 0), (w, h), (0, h), (0, 0)], True


# ---------------------------------------------------------------- OPC 构建

def _cells_xml(cells: dict) -> str:
    return "".join(f'<Cell N="{name}" V="{escape(str(value), _ATTR_ESC)}"/>'
                   for name, value in cells.items())


def _shape_xml(shape, geom, shape_pk_id, media_rel_id=None,
               role_entry_id=None) -> str:
    style = shape.get("style") or {}
    w, h = geom["width"], geom["height"]
    cells = {
        "PinX": f"{geom['pin_x']:.5f}", "PinY": f"{geom['pin_y']:.5f}",
        "Width": f"{w:.5f}", "Height": f"{h:.5f}",
        "LocPinX": f"{w / 2:.5f}", "LocPinY": f"{h / 2:.5f}",
        "Angle": "0",
    }
    shape_type = shape["type"]
    if shape_type == "image_residue":
        cells["ImgWidth"] = f"{w:.5f}"
        cells["ImgHeight"] = f"{h:.5f}"
    if shape_type == "text":
        cells["FillPattern"] = "0"
        cells["LinePattern"] = "0"
    else:
        fill = style.get("fill") or (
            role_hex(role_entry_id, style["fill_role"])
            if style.get("fill_role") else None)
        line = style.get("line") or (
            role_hex(role_entry_id, style["line_role"])
            if style.get("line_role") else "#000000")
        if fill:
            cells["FillForegnd"] = fill
            cells["FillPattern"] = "1"
        if shape_type != "image_residue":
            cells["LineColor"] = line
            cells["LineWeight"] = \
                f"{float(style.get('line_width_pt', 0.75)) / 72:.6f}"
            cells["LinePattern"] = "1"
    font_pt = float(style.get("font_pt", 8))
    points, _closed = _geometry_points(shape_type, w, h)
    rows = []
    for i, (x, y) in enumerate(points):
        row_type = "MoveTo" if i == 0 else "LineTo"
        rows.append(f'<Row T="{row_type}" IX="{i + 1}">'
                    f'<Cell N="X" V="{x:.5f}"/><Cell N="Y" V="{y:.5f}"/>'
                    "</Row>")
    geometry = (f'<Section N="Geometry" IX="0">'
                f'<Cell N="NoFill" V="0"/><Cell N="NoLine" V="0"/>'
                + "".join(rows) + "</Section>")
    character = (f'<Section N="Character"><Row IX="0">'
                 f'<Cell N="Size" V="{font_pt / 72:.6f}"/></Row></Section>')
    text = shape.get("text") or ""
    text_xml = f"<Text>{escape(str(text))}</Text>" if text else ""
    foreign = ""
    shape_attr_type = "Shape"
    if shape_type == "image_residue" and media_rel_id:
        shape_attr_type = "Foreign"
        foreign = (f'<ForeignData ForeignType="Bitmap" '
                   f'CompressionType="PNG"><Rel r:id="{media_rel_id}"/>'
                   "</ForeignData>")
    # 顺序纪律（pengjunchi0）：Shape 级 Cell 必须在 Section/Text/子元素之前
    name_esc = escape(str(shape["shape_id"]), {'"': "&quot;"})
    return (f'<Shape ID="{shape_pk_id}" NameU="{name_esc}" '
            f'Name="{name_esc}" Type="{shape_attr_type}">'
            + _cells_xml(cells) + character + geometry + foreign
            + text_xml + "</Shape>")


def build_vsdx(root, fig_id: str, by: str | None = None) -> dict:
    root = Path(root)
    manifest = load_manifest(root, fig_id)
    if manifest is None:
        raise RedrawError([f"图 {fig_id} 无重绘 manifest"
                            "（先 redraw init / install 登记）"])
    gaps = validate_manifest(manifest, root=root)
    if gaps:
        raise RedrawError(gaps)
    if manifest["route"] == "com":
        raise RedrawError([
            "manifest 路线为 COM 原生重建：须在 Windows + Visio 环境"
            "经脚手架 helper 执行（两级标定 + 越界断言 + 描图层交付前"
            "移除）；本环境无 Visio，不许冒充已执行——改登记为 "
            "file_build 走文件级路线，或在 Visio 环境执行 COM 路线"])
    if manifest["status"] == "draft":
        raise RedrawError(["manifest 仍为 draft 骨架（标定未落字）："
                            "补齐后经 redraw install 登记再构建"])

    role_entry = (manifest.get("role_palette") or {}).get("entry_id")
    shapes = list(manifest.get("shapes") or [])
    residue_by_media = {}
    media_parts = {}
    page_rels = []
    for residue in manifest.get("bitmap_residue") or []:
        src = root / residue["source"]["path"]
        media_name = residue["media_name"]
        media_parts[f"visio/media/{media_name}"] = src.read_bytes()
        residue_by_media[media_name] = residue
        page_rels.append((f"rId{len(page_rels) + 1}", media_name,
                          residue["residue_id"]))
    rel_by_residue = {rid: rid_ for rid_, _name, rid in page_rels}

    shape_xml_parts = []
    pk = 0
    for shape in shapes:
        pk += 1
        geom = shape_geometry(manifest, shape)
        media_rel = None
        if shape["type"] == "image_residue":
            rid = shape.get("residue_id")
            media_rel = rel_by_residue.get(rid)
            if media_rel is None:
                raise RedrawError([
                    f"形状 {shape['shape_id']} 是 image_residue 但未绑定"
                    f"已登记的位图残留（residue_id={rid!r}）：未登记的"
                    "位图不许出现在成品中"])
        shape_xml_parts.append(
            _shape_xml(shape, geom, pk, media_rel, role_entry))
    for residue in manifest.get("bitmap_residue") or []:
        bound = [s for s in shapes
                 if s.get("type") == "image_residue"
                 and s.get("residue_id") == residue["residue_id"]]
        if not bound:
            pk += 1
            geom = shape_geometry(manifest, {
                "panel_id": residue.get("panel_id"),
                "box_local": residue["box_local"]})
            shape_xml_parts.append(_shape_xml(
                {"shape_id": f"residue-{residue['residue_id']}",
                 "type": "image_residue", "text": ""},
                geom, pk, rel_by_residue[residue["residue_id"]],
                role_entry))

    page_w, page_h = manifest["canvas"]["page_size_in"]
    page1_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        f'<PageContents xmlns="{NS_MAIN}" xmlns:r="{NS_R}" '
        'xml:space="preserve"><Shapes>'
        + "".join(shape_xml_parts) + "</Shapes></PageContents>")
    pages_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        f'<Pages xmlns="{NS_MAIN}" xmlns:r="{NS_R}">'
        f'<Page ID="0" NameU="Page-1" Name="Page-1" ViewScale="1" '
        f'ViewCenterX="{page_w / 2:.4f}" ViewCenterY="{page_h / 2:.4f}">'
        f'<PageSheet><Cell N="PageWidth" V="{page_w}"/>'
        f'<Cell N="PageHeight" V="{page_h}"/></PageSheet>'
        '<Rel r:id="rId1"/></Page></Pages>')
    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        f'<VisioDocument xmlns="{NS_MAIN}" xmlns:r="{NS_R}">'
        "<DocumentSettings/><Colors/>"
        '<FaceNames><FaceName NameU="Calibri"/></FaceNames>'
        "<StyleSheets/></VisioDocument>")
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/'
        'content-types">'
        '<Default Extension="rels" ContentType="application/vnd.'
        'openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Default Extension="png" ContentType="image/png"/>'
        '<Default Extension="jpg" ContentType="image/jpeg"/>'
        '<Default Extension="jpeg" ContentType="image/jpeg"/>'
        '<Override PartName="/visio/document.xml" ContentType='
        '"application/vnd.ms-visio.drawing.main+xml"/>'
        '<Override PartName="/visio/pages/pages.xml" ContentType='
        '"application/vnd.ms-visio.pages+xml"/>'
        '<Override PartName="/visio/pages/page1.xml" ContentType='
        '"application/vnd.ms-visio.page+xml"/>'
        '<Override PartName="/docProps/core.xml" ContentType='
        '"application/vnd.openxmlformats-package.core-properties+xml"/>'
        '<Override PartName="/docProps/app.xml" ContentType='
        '"application/vnd.openxmlformats-officedocument.'
        'extended-properties+xml"/></Types>')
    root_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<Relationships xmlns="http://schemas.openxmlformats.org/'
        'package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.microsoft.com/'
        'visio/2010/relationships/document" Target="visio/document.xml"/>'
        "</Relationships>")
    doc_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<Relationships xmlns="http://schemas.openxmlformats.org/'
        'package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.microsoft.com/'
        'visio/2010/relationships/pages" Target="pages/pages.xml"/>'
        "</Relationships>")
    pages_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<Relationships xmlns="http://schemas.openxmlformats.org/'
        'package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.microsoft.com/'
        'visio/2010/relationships/page" Target="page1.xml"/>'
        "</Relationships>")
    page1_rels = None
    if page_rels:
        rels = "".join(
            f'<Relationship Id="{rid}" Type="http://schemas.openxmlformats'
            f'.org/officeDocument/2006/relationships/image" '
            f'Target="../media/{escape(name, _ATTR_ESC)}"/>'
            for rid, name, _res in page_rels)
        page1_rels = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            '<Relationships xmlns="http://schemas.openxmlformats.org/'
            f'package/2006/relationships">{rels}</Relationships>')
    core_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/'
        'package/2006/metadata/core-properties">'
        f"<dc:title xmlns:dc=\"http://purl.org/dc/elements/1.1/\">"
        f"light-figure redraw {escape(fig_id, _ATTR_ESC)}</dc:title>"
        "</cp:coreProperties>")
    app_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<Properties xmlns="http://schemas.openxmlformats.org/'
        'officeDocument/2006/extended-properties">'
        "<Application>light-figure</Application></Properties>")

    parts = {
        "[Content_Types].xml": content_types,
        "_rels/.rels": root_rels,
        "docProps/app.xml": app_xml,
        "docProps/core.xml": core_xml,
        "visio/document.xml": document_xml,
        "visio/_rels/document.xml.rels": doc_rels,
        "visio/pages/pages.xml": pages_xml,
        "visio/pages/_rels/pages.xml.rels": pages_rels,
        "visio/pages/page1.xml": page1_xml,
    }
    if page1_rels:
        parts["visio/pages/_rels/page1.xml.rels"] = page1_rels
    for name, data in media_parts.items():
        parts[name] = data

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in sorted(parts):
            info = zipfile.ZipInfo(name, date_time=_ZIP_EPOCH)
            info.compress_type = zipfile.ZIP_DEFLATED
            data = parts[name]
            zf.writestr(info, data.encode("utf-8")
                        if isinstance(data, str) else data)
    out_path = root / vsdx_relpath(fig_id)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(buffer.getvalue())
    digest = sha256_file(out_path)

    manifest["status"] = "built"
    manifest["build"] = {
        "builder": "light-figure redraw build (file_build)",
        "route": "file_build",
        "visio_verified": False,  # 文件级路线恒未过 Visio 实机验证（D4）
        "artifact": vsdx_relpath(fig_id),
        "artifact_sha256": digest,
        "shapes_built": pk,
    }
    trace = manifest.setdefault("trace_layer", {})
    trace["removed_before_delivery"] = True  # 文件级构建从不嵌入描图层
    save_manifest(root, manifest)
    update_provenance_row(root, fig_id, {
        "redraw_source": {"path": vsdx_relpath(fig_id), "hash": digest},
    }, by=by or "light-figure redraw build")
    return {
        "fig_id": fig_id, "artifact": vsdx_relpath(fig_id),
        "artifact_sha256": digest, "shapes_built": pk,
        "visio_verified": False,
    }


# ---------------------------------------------------------------- 反抽对账

def extract_shapes(vsdx_path) -> list:
    """从成品 .vsdx 反抽形状清单（形状名/类型/页坐标/文本）。"""
    import xml.etree.ElementTree as ET

    def local(tag):
        return tag.rsplit("}", 1)[-1]

    with zipfile.ZipFile(vsdx_path) as zf:
        names = zf.namelist()
        page_names = sorted(
            n for n in names
            if re.match(r"visio/pages/page\d+\.xml$", n))
        if not page_names:
            raise RedrawError([f"{vsdx_path} 内无 visio/pages/pageN.xml"])
        xml_bytes = zf.read(page_names[0])
    tree = ET.fromstring(xml_bytes)
    shapes = []
    for el in tree.iter():
        if local(el.tag) != "Shape":
            continue
        cells = {}
        text = ""
        for child in el:
            if local(child.tag) == "Cell":
                cells[child.get("N")] = child.get("V")
            elif local(child.tag) == "Text":
                text = "".join(child.itertext()).strip()
        shapes.append({
            "shape_id": el.get("NameU"),
            "pin_x": float(cells.get("PinX", 0)),
            "pin_y": float(cells.get("PinY", 0)),
            "width": float(cells.get("Width", 0)),
            "height": float(cells.get("Height", 0)),
            "text": text,
        })
    return sorted(shapes, key=lambda s: str(s["shape_id"]))


def extract_and_reconcile(root, fig_id: str) -> dict:
    root = Path(root)
    manifest = load_manifest(root, fig_id)
    if manifest is None:
        raise RedrawError([f"图 {fig_id} 无重绘 manifest"])
    vsdx = root / vsdx_relpath(fig_id)
    if not vsdx.exists():
        raise RedrawError([f"图 {fig_id} 的成品 .vsdx 不存在（先 build）"])
    extracted = extract_shapes(vsdx)
    extracted_hash = component_hash(extracted)
    expected = {}
    for shape in manifest.get("shapes") or []:
        geom = shape_geometry(manifest, shape)
        expected[shape["shape_id"]] = {
            **geom, "text": str(shape.get("text") or "").strip()}
    for residue in manifest.get("bitmap_residue") or []:
        bound = [s for s in manifest.get("shapes") or []
                 if s.get("type") == "image_residue"
                 and s.get("residue_id") == residue["residue_id"]]
        if not bound:
            geom = shape_geometry(manifest, {
                "panel_id": residue.get("panel_id"),
                "box_local": residue["box_local"]})
            expected[f"residue-{residue['residue_id']}"] = {
                **geom, "text": ""}
    diffs = []
    got = {s["shape_id"]: s for s in extracted}
    for sid, exp in expected.items():
        if sid not in got:
            diffs.append(f"成品缺清单形状 {sid}（漏画）")
            continue
        act = got[sid]
        for key in ("pin_x", "pin_y", "width", "height"):
            if abs(act[key] - exp[key]) > 0.02:
                diffs.append(f"形状 {sid} 的 {key} 与清单不符："
                             f"成品 {act[key]:.3f} vs 清单 {exp[key]:.3f}")
        if act["text"] != exp["text"]:
            diffs.append(f"形状 {sid} 文本与清单不符："
                         f"成品 {act['text']!r} vs 清单 {exp['text']!r}")
    for sid in got:
        if sid not in expected:
            diffs.append(f"成品含未登记形状 {sid}（清单外形状不许出现）")
    ok = not diffs
    from .util import utcnow
    manifest["extracted_shapes_hash"] = extracted_hash
    manifest["reconciliation"] = {"ok": ok, "diffs": diffs, "at": utcnow()}
    if ok:
        manifest["status"] = "verified"
    save_manifest(root, manifest)
    return {"fig_id": fig_id, "ok": ok, "diffs": diffs,
            "extracted_shapes_hash": extracted_hash,
            "shapes_extracted": len(extracted)}
