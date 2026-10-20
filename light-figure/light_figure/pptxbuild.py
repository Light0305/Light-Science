"""PowerPoint 文件层路线（FIG-D02，v1.1 裁决修订后的第二原生后端）。

定位（诊断 2.2 (C)）：PPT 不替代 Visio，占两个位置——一图两栖的
演示目的地（方法图同时进组会/答辩 slides 时以 PPTX 为原生源），与
无 Visio 团队（PowerPoint/WPS 环境）的原生源替代。本模块只落
**文件层**：pptx manifest 契约（与 redraw manifest 对称）+
python-pptx 构建 + python-pptx 反读对账 + OPC 审计接入（audit.py）。
COM 增强格（sbroenne 形态：会话工程 + export-to-verify）只在
SKILL §8 落规程——本机无 Windows + PowerPoint，真机验证如实落
gap；文件层产物恒标 powerpoint_verified: false（证据等级
file_layer），不许冒充 COM 原生验证（与 visio_verified 同构）。

User.* 语义 ID 的 PPTX 落点（构建单 J3）：PPTX 无 ShapeSheet，
取双写——shape.name = 稳定语义 ID（PowerPoint UI 与 python-pptx
的原生名字面），cNvPr descr 写 `light-figure:user-id=<id>` 作机器
可读落点；连接线以连接器对象承载，descr 写 arrow 绑定
（arrow_plan_id + from/to），extract 双读对账。
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

PPTX_DIR = "schematic/redraw"
PPTX_SHAPE_KINDS = ["rect", "rounded_rect", "ellipse", "diamond",
                    "parallelogram", "line", "text", "image_residue"]
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_DESCR_USER = "light-figure:user-id="
_DESCR_ARROW = "light-figure:arrow="


class PptxError(Exception):
    def __init__(self, gaps):
        self.gaps = list(gaps)
        super().__init__("；".join(self.gaps))


def pptx_manifest_path(root, fig_id) -> Path:
    return Path(root) / PPTX_DIR / f"{fig_id}.pptx-manifest.json"


def pptx_relpath(fig_id) -> str:
    return f"{PPTX_DIR}/{fig_id}.pptx"


def _require_pptx():
    try:
        import pptx  # noqa: F401
    except ImportError:
        raise PptxError([
            "python-pptx 未安装：pip install 'python-pptx>=1.0'"
            "（PPT 文件层路线的构建/反读依赖；缺依赖如实停住，"
            "不许降级到其他库冒充）"])


# ---------------------------------------------------------------- 契约校验

def _box_ok(box) -> bool:
    return isinstance(box, (list, tuple)) and len(box) == 4 \
        and all(isinstance(v, (int, float)) and not isinstance(v, bool)
                for v in box)


def validate_pptx_manifest(manifest, root=None) -> list:
    """pptx manifest 契约校验（与 redraw manifest 对称），返回 gaps。"""
    gaps = []
    if not isinstance(manifest, dict):
        return ["PPTX manifest 须为对象"]
    fig_id = manifest.get("fig_id") or "?"
    reference = manifest.get("reference") or {}
    if not reference.get("path"):
        gaps.append(f"图 {fig_id} pptx manifest 缺参考图指针 reference.path")
    if not _HEX64.match(str(reference.get("sha256") or "")):
        gaps.append(f"图 {fig_id} pptx manifest 的 reference.sha256 "
                    "不是 SHA-256")
    canvas = manifest.get("canvas") or {}
    size_px = canvas.get("reference_size_px")
    if not (isinstance(size_px, (list, tuple)) and len(size_px) == 2
            and all(isinstance(v, (int, float)) and v > 0 for v in size_px)):
        gaps.append(f"图 {fig_id} pptx manifest 缺画布标定 "
                    "canvas.reference_size_px")
    page_in = canvas.get("page_size_in")
    if not (isinstance(page_in, (list, tuple)) and len(page_in) == 2
            and all(isinstance(v, (int, float)) and v > 0 for v in page_in)):
        gaps.append(f"图 {fig_id} pptx manifest 缺 canvas.page_size_in"
                    "（幻灯片尺寸 = 图尺寸，合同约定先行）")
    panels = {}
    for panel in manifest.get("panels") or []:
        pid = panel.get("panel_id")
        if not pid:
            gaps.append(f"图 {fig_id} pptx manifest 面板缺 panel_id")
            continue
        if pid in panels:
            gaps.append(f"图 {fig_id} pptx manifest 面板 id 重复：{pid}")
        panels[pid] = panel
        box = panel.get("pixel_box")
        if not _box_ok(box):
            gaps.append(f"图 {fig_id} 面板 {pid} 缺四角标定 pixel_box")
        elif box[2] <= 0 or box[3] <= 0:
            gaps.append(f"图 {fig_id} 面板 {pid} 的 pixel_box 宽高须为正")
    if not panels:
        gaps.append(f"图 {fig_id} pptx manifest 无面板清单（四角标定先行）")

    seen_ids = set()
    for shape in manifest.get("shapes") or []:
        sid = shape.get("shape_id")
        if not sid:
            gaps.append(f"图 {fig_id} pptx manifest 形状缺稳定语义 ID "
                        "shape_id")
            continue
        if sid in seen_ids:
            gaps.append(f"图 {fig_id} pptx manifest 形状 ID 重复：{sid}")
        seen_ids.add(sid)
        if shape.get("type") not in PPTX_SHAPE_KINDS:
            gaps.append(f"图 {fig_id} 形状 {sid} 的 type "
                        f"{shape.get('type')!r} 不在词表 {PPTX_SHAPE_KINDS}")
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
                                       label="pptx manifest"))
    gaps.extend(check_arrow_plan(manifest, fig_id, seen_ids,
                                 label="pptx manifest"))
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
            gaps.append("pptx manifest 登记的参考图哈希与包内文件不符")
        for residue in manifest.get("bitmap_residue") or []:
            src = root / str((residue.get("source") or {}).get("path") or "")
            if not src.exists():
                gaps.append(f"位图残留 {residue.get('residue_id')} 的"
                            f"源文件不存在：{src}")
            elif sha256_file(src) != residue["source"]["sha256"]:
                gaps.append(f"位图残留 {residue.get('residue_id')} 的"
                            "源文件哈希与登记不符")
    return gaps


# ---------------------------------------------------------------- 登记

def init_pptx_manifest(root, fig_id: str) -> dict:
    """按合同面板 + 已登记参考图生成 pptx manifest 骨架（draft）。"""
    _require_pptx()
    root = Path(root)
    pkg = load_package(root)
    contract = pkg["contracts"].get(fig_id)
    if contract is None:
        raise PptxError([f"图 {fig_id} 无图合同（先 intake）"])
    entry = provenance_row(pkg["provenance"], fig_id) or {}
    if not entry.get("reference_image_hash"):
        raise PptxError([f"图 {fig_id} 参考图尚未入包登记"
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
        "backend": "powerpoint_file",
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
        "extracted_shapes_hash": None,
        "reconciliation": None,
    }
    path = pptx_manifest_path(root, fig_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    dump_json(path, manifest)
    return manifest


def install_pptx_manifest(root, fig_id: str, source) -> dict:
    root = Path(root)
    manifest = load_structured(Path(source))
    if not isinstance(manifest, dict):
        raise PptxError(["pptx manifest 文件不是对象"])
    if manifest.get("fig_id") != fig_id:
        raise PptxError([f"pptx manifest 的 fig_id "
                         f"{manifest.get('fig_id')!r} 与目标图 {fig_id} "
                         "不一致"])
    gaps = validate_pptx_manifest(manifest, root=root)
    pkg = load_package(root)
    entry = provenance_row(pkg["provenance"], fig_id) or {}
    if entry.get("reference_image_hash") \
            and manifest["reference"]["sha256"] \
            != entry["reference_image_hash"]:
        gaps.append("pptx manifest 参考图哈希与 provenance 账登记不一致")
    if gaps:
        raise PptxError(gaps)
    manifest["status"] = "registered"
    path = pptx_manifest_path(root, fig_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    dump_json(path, manifest)
    return manifest


def load_pptx_manifest(root, fig_id: str) -> dict | None:
    path = pptx_manifest_path(root, fig_id)
    if not path.exists():
        return None
    return load_structured(path)


def save_pptx_manifest(root, manifest) -> None:
    dump_json(pptx_manifest_path(root, manifest["fig_id"]), manifest)


# ---------------------------------------------------------------- 构建

def _set_descr(shape, value: str) -> None:
    """cNvPr descr 写入（User.* 的机器可读落点）。"""
    sp = shape._element
    nv = None
    for tag in ("p:nvPicPr", "p:nvSpPr", "p:nvCxnSpPr",
                "p:nvGraphicFramePr"):
        found = sp.find(f"{{{_NS_P}}}{tag.split(':', 1)[1]}")
        if found is not None:
            nv = found
            break
    if nv is None:
        return
    cnv = nv.find(f"{{{_NS_P}}}cNvPr")
    if cnv is not None:
        cnv.set("descr", value)


def _get_descr(shape) -> str:
    sp = shape._element
    for el in sp.iter():
        if el.tag.rsplit("}", 1)[-1] == "cNvPr":
            return el.get("descr") or ""
    return ""


_NS_P = "http://schemas.openxmlformats.org/presentationml/2006/main"
_NS_A = "http://schemas.openxmlformats.org/drawingml/2006/main"


def _apply_style(shape, style, role_entry_id):
    from pptx.dml.color import RGBColor
    from pptx.util import Pt

    fill_hex = style.get("fill") or (
        role_hex(role_entry_id, style["fill_role"])
        if style.get("fill_role") else None)
    line_hex = style.get("line") or (
        role_hex(role_entry_id, style["line_role"])
        if style.get("line_role") else "#000000")
    if fill_hex:
        shape.fill.solid()
        shape.fill.fore_color.rgb = RGBColor.from_string(
            fill_hex.lstrip("#").upper())
    else:
        shape.fill.background()
    if line_hex:
        shape.line.color.rgb = RGBColor.from_string(
            line_hex.lstrip("#").upper())
        shape.line.width = Pt(float(style.get("line_width_pt", 0.75)))


def _set_text(shape, text, font_pt):
    from pptx.util import Pt

    tf = shape.text_frame
    tf.word_wrap = True
    tf.text = str(text)
    for para in tf.paragraphs:
        for run in para.runs:
            run.font.size = Pt(float(font_pt))


def _add_arrowhead(connector) -> None:
    """连接器尾端箭头（DrawingML tailEnd；python-pptx 无原生 API，
    按 GVML 混合思想直接补 XML）。"""
    from lxml import etree

    ln = connector.line._get_or_add_ln()
    tail = ln.makeelement(f"{{{_NS_A}}}tailEnd", {"type": "arrow"})
    ln.append(tail)


def build_pptx(root, fig_id: str, by: str | None = None) -> dict:
    _require_pptx()
    from pptx import Presentation
    from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
    from pptx.util import Inches

    root = Path(root)
    manifest = load_pptx_manifest(root, fig_id)
    if manifest is None:
        raise PptxError([f"图 {fig_id} 无 pptx manifest"
                          "（先 pptx init / install 登记）"])
    gaps = validate_pptx_manifest(manifest, root=root)
    if gaps:
        raise PptxError(gaps)
    if manifest["status"] == "draft":
        raise PptxError(["pptx manifest 仍为 draft 骨架（标定未落字）："
                          "补齐后经 pptx install 登记再构建"])
    projection_hash = component_hash(manifest_projection(manifest))
    rounds = manifest.get("rounds") or []
    if rounds and rounds[-1].get("projection_hash") == projection_hash:
        raise PptxError([
            f"round_noop：本轮 pptx manifest 内容投影与上一轮（round "
            f"{rounds[-1].get('round')}）完全相同——纯元数据轮次不许"
            "计为进展；先实质修改清单再 build（FIG-D06）"])

    role_entry = (manifest.get("role_palette") or {}).get("entry_id")
    page_w, page_h = manifest["canvas"]["page_size_in"]
    prs = Presentation()
    prs.slide_width = Inches(float(page_w))
    prs.slide_height = Inches(float(page_h))
    slide = prs.slides.add_slide(prs.slide_layouts[6])  # 空白版式

    shape_types = {
        "rect": MSO_SHAPE.RECTANGLE,
        "rounded_rect": MSO_SHAPE.ROUNDED_RECTANGLE,
        "ellipse": MSO_SHAPE.OVAL,
        "diamond": MSO_SHAPE.DIAMOND,
        "parallelogram": MSO_SHAPE.PARALLELOGRAM,
    }
    shapes = list(manifest.get("shapes") or [])
    placed = {}
    count = 0
    for shape in shapes:
        if shape["type"] == "image_residue":
            continue  # 位图残留统一在残留段落盘（与 vsdx 同口径）
        geom = shape_geometry(manifest, shape)
        left = Inches(geom["pin_x"] - geom["width"] / 2)
        top = Inches(page_h - (geom["pin_y"] + geom["height"] / 2))
        width = Inches(geom["width"])
        height = Inches(geom["height"])
        style = shape.get("style") or {}
        if shape["type"] == "text":
            obj = slide.shapes.add_textbox(left, top, width, height)
        elif shape["type"] == "line":
            obj = slide.shapes.add_connector(
                MSO_CONNECTOR.STRAIGHT, left, top,
                left + width, top + height)
            from pptx.dml.color import RGBColor
            from pptx.util import Pt as _Pt
            line_hex = style.get("line") or (
                role_hex(role_entry, style["line_role"])
                if style.get("line_role") else "#000000")
            obj.line.color.rgb = RGBColor.from_string(
                line_hex.lstrip("#").upper())
            obj.line.width = _Pt(float(style.get("line_width_pt", 0.75)))
        else:
            obj = slide.shapes.add_shape(
                shape_types[shape["type"]], left, top, width, height)
            _apply_style(obj, style, role_entry)
        obj.name = shape["shape_id"]
        _set_descr(obj, _DESCR_USER + shape["shape_id"])
        if shape.get("text"):
            _set_text(obj, shape["text"],
                      style.get("font_pt", 8))
        placed[shape["shape_id"]] = (obj, geom)
        count += 1
    # 连接线：每条 arrow_plan 绑定落一条连接器对象（端点取两形状中心）
    plan = {e.get("arrow_plan_id"): e
            for e in manifest.get("arrow_plan") or []}
    drawn_arrows = set()
    for shape in shapes:
        connect = shape.get("connect") or {}
        pid = connect.get("arrow_plan_id")
        if not pid or pid in drawn_arrows:
            continue
        entry = plan.get(pid) or {}
        src = placed.get(entry.get("from") or connect.get("from"))
        dst = placed.get(entry.get("to") or connect.get("to"))
        if src is None or dst is None:
            raise PptxError([f"arrow_plan {pid} 的端点形状未构建，"
                              "连接线无从落（清单与计划脱节）"])
        sg, dg = src[1], dst[1]
        conn = slide.shapes.add_connector(
            MSO_CONNECTOR.STRAIGHT,
            Inches(sg["pin_x"]), Inches(page_h - sg["pin_y"]),
            Inches(dg["pin_x"]), Inches(page_h - dg["pin_y"]))
        conn.name = f"arrow-{pid}"
        _set_descr(conn, _DESCR_ARROW
                   + f"{pid};from={entry.get('from')};to={entry.get('to')}")
        _add_arrowhead(conn)
        drawn_arrows.add(pid)
        count += 1
    for residue in manifest.get("bitmap_residue") or []:
        bound = [s for s in shapes
                 if s.get("type") == "image_residue"
                 and s.get("residue_id") == residue["residue_id"]]
        geom_src = bound[0] if bound else {
            "panel_id": residue.get("panel_id"),
            "box_local": residue["box_local"]}
        geom = shape_geometry(manifest, geom_src)
        src = root / residue["source"]["path"]
        pic = slide.shapes.add_picture(
            str(src),
            Inches(geom["pin_x"] - geom["width"] / 2),
            Inches(page_h - (geom["pin_y"] + geom["height"] / 2)),
            Inches(geom["width"]), Inches(geom["height"]))
        pic.name = f"residue-{residue['residue_id']}"
        _set_descr(pic, _DESCR_USER + f"residue-{residue['residue_id']}")
        count += 1

    out_path = root / pptx_relpath(fig_id)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    prs.save(str(out_path))
    digest = sha256_file(out_path)

    from .util import utcnow
    manifest.setdefault("rounds", []).append({
        "round": len(manifest.get("rounds") or []) + 1,
        "at": utcnow(),
        "projection_hash": projection_hash,
        "artifact_sha256": digest,
    })
    manifest["status"] = "built"
    manifest["build"] = {
        "builder": "light-figure pptx build (python-pptx file layer)",
        "backend": "powerpoint_file",
        # 文件层证据：python-pptx 构建 + OPC 反读，不等于 PowerPoint
        # 实机原生验证（与 visio_verified: false 同构，如实落字）
        "powerpoint_verified": False,
        "evidence_level": "file_layer",
        "artifact": pptx_relpath(fig_id),
        "artifact_sha256": digest,
        "shapes_built": count,
    }
    save_pptx_manifest(root, manifest)
    update_provenance_row(root, fig_id, {
        "redraw_source": {"path": pptx_relpath(fig_id), "hash": digest},
    }, by=by or "light-figure pptx build")
    return {
        "fig_id": fig_id, "artifact": pptx_relpath(fig_id),
        "artifact_sha256": digest, "shapes_built": count,
        "powerpoint_verified": False, "evidence_level": "file_layer",
    }


# ---------------------------------------------------------------- 反读对账

def extract_pptx_shapes(pptx_path) -> list:
    """python-pptx 反读：形状名 / User ID（descr）/ 页坐标（英寸，
    左下原点，与 shape_geometry 同口径）/ 文本 / 类别。"""
    _require_pptx()
    from pptx import Presentation
    from pptx.util import Emu

    prs = Presentation(str(pptx_path))
    page_h_in = Emu(prs.slide_height).inches
    out = []
    for slide in prs.slides:
        for shape in slide.shapes:
            descr = _get_descr(shape)
            user_id = descr[len(_DESCR_USER):] \
                if descr.startswith(_DESCR_USER) else None
            arrow = None
            if descr.startswith(_DESCR_ARROW):
                body = descr[len(_DESCR_ARROW):]
                parts = dict(kv.split("=", 1)
                             for kv in body.split(";") if "=" in kv)
                first = body.split(";")[0]
                arrow = {"arrow_plan_id": first, **parts}
            out.append({
                "shape_id": shape.name,
                "user_semantic_id": user_id,
                "shape_type": str(shape.shape_type),
                "pin_x": round(Emu(shape.left).inches
                               + Emu(shape.width).inches / 2, 5)
                if shape.left is not None else None,
                "pin_y": round(page_h_in
                               - (Emu(shape.top).inches
                                  + Emu(shape.height).inches / 2), 5)
                if shape.top is not None else None,
                "width": round(Emu(shape.width).inches, 5)
                if shape.width is not None else None,
                "height": round(Emu(shape.height).inches, 5)
                if shape.height is not None else None,
                "text": (shape.text_frame.text.strip()
                         if shape.has_text_frame else ""),
                "arrow": arrow,
            })
    return sorted(out, key=lambda s: str(s["shape_id"]))


def extract_and_reconcile_pptx(root, fig_id: str) -> dict:
    root = Path(root)
    manifest = load_pptx_manifest(root, fig_id)
    if manifest is None:
        raise PptxError([f"图 {fig_id} 无 pptx manifest"])
    artifact = root / pptx_relpath(fig_id)
    if not artifact.exists():
        raise PptxError([f"图 {fig_id} 的成品 .pptx 不存在（先 build）"])
    extracted = extract_pptx_shapes(artifact)
    extracted_hash = component_hash(extracted)
    expected = {}
    for shape in manifest.get("shapes") or []:
        if shape["type"] == "image_residue":
            continue
        geom = shape_geometry(manifest, shape)
        expected[shape["shape_id"]] = {
            **geom, "text": str(shape.get("text") or "").strip()}
    for residue in manifest.get("bitmap_residue") or []:
        geom = shape_geometry(manifest, {
            "panel_id": residue.get("panel_id"),
            "box_local": residue["box_local"]})
        expected[f"residue-{residue['residue_id']}"] = {
            **geom, "text": ""}
    plan = {e.get("arrow_plan_id"): e
            for e in manifest.get("arrow_plan") or []}
    diffs = []
    got = {s["shape_id"]: s for s in extracted}
    for sid, exp in expected.items():
        if sid not in got:
            diffs.append(f"成品缺清单形状 {sid}（漏画）")
            continue
        act = got[sid]
        for key in ("pin_x", "pin_y", "width", "height"):
            if act[key] is None or abs(act[key] - exp[key]) > 0.02:
                diffs.append(f"形状 {sid} 的 {key} 与清单不符："
                             f"成品 {act[key]} vs 清单 {exp[key]:.3f}")
        if act["text"] != exp["text"]:
            diffs.append(f"形状 {sid} 文本与清单不符："
                         f"成品 {act['text']!r} vs 清单 {exp['text']!r}")
        if act.get("user_semantic_id") != sid:
            diffs.append(f"形状 {sid} 的 descr User ID 为 "
                         f"{act.get('user_semantic_id')!r}，与清单语义 "
                         "ID 不一致（ID 钉扎对账，FIG-D04）")
    for pid, entry in plan.items():
        conn = got.get(f"arrow-{pid}")
        if conn is None:
            diffs.append(f"成品缺 arrow_plan {pid} 的连接线对象（边事实"
                         "未落成品，FIG-D06）")
            continue
        arrow = conn.get("arrow") or {}
        if arrow.get("from") != entry.get("from") \
                or arrow.get("to") != entry.get("to"):
            diffs.append(f"连接线 arrow-{pid} 的端点与 arrow_plan 登记"
                         f"不一致：成品 {arrow} vs 计划 {entry}")
    known = set(expected) | {f"arrow-{pid}" for pid in plan}
    for sid in got:
        if sid not in known:
            diffs.append(f"成品含未登记对象 {sid}（清单外对象不许出现）")
    ok = not diffs
    from .util import utcnow
    manifest["extracted_shapes_hash"] = extracted_hash
    manifest["reconciliation"] = {"ok": ok, "diffs": diffs,
                                  "at": utcnow()}
    if ok:
        manifest["status"] = "verified"
    save_pptx_manifest(root, manifest)
    return {"fig_id": fig_id, "ok": ok, "diffs": diffs,
            "extracted_shapes_hash": extracted_hash,
            "shapes_extracted": len(extracted)}
