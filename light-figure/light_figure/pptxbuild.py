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


# ---------------------------------------------------------------- COM 实现形态
# 第二轮时 COM 路线只有规程（15-tools 深读 sbroenne）；本批升为实现
# 形态：manifest 生成 PowerShell + COM 构建脚本（构建单 B1–B3）。
# 证据等级纪律与 Illustrator 路同构（构建单 J3）：脚本生成只给
# script 级证据；com-verify 登记（枚举回读 + 导出物对账）无差、
# 带应用名/版本、执行者落字三件齐，才许 com_route.powerpoint_
# verified 置真。合同/顶层 powerpoint_verified 仍只由文件级
# extract 对 COM 产物 .pptx 落（同一产物同一核验路，不开第二口）。

def com_script_relpath(fig_id: str) -> str:
    return f"schematic/redraw/{fig_id}.com-build.ps1"


def com_verify_json_relpath(fig_id: str) -> str:
    return f"schematic/redraw/{fig_id}.com-verify.json"


def com_export_relpaths(fig_id: str) -> dict:
    return {
        "png": f"schematic/redraw/{fig_id}.com-export.png",
        "pdf": f"schematic/redraw/{fig_id}.com-export.pdf",
    }


def _ps_str(value) -> str:
    """PowerShell 单引号字符串字面量（' 以 '' 转义）。"""
    return "'" + str(value).replace("'", "''") + "'"


def _shape_colors(shape, role_entry):
    """填充/描边解析（与文件级 _add_shape 同口径：缺省皆 None）。"""
    style = shape.get("style") or {}
    fill = style.get("fill") or (
        role_hex(role_entry, style["fill_role"])
        if style.get("fill_role") else None)
    line = style.get("line") or (
        role_hex(role_entry, style["line_role"])
        if style.get("line_role") else None)
    return fill, line


def _com_rgb(hex_color: str) -> int:
    """#rrggbb → COM 的 RGB 长整型（R + G*256 + B*65536）。"""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return r + g * 256 + b * 65536


_MSO_SHAPE = {"rect": 1, "parallelogram": 2, "diamond": 4,
              "rounded_rect": 5, "ellipse": 9}


def _generate_com_ps(manifest) -> str:
    """manifest → PowerShell COM 构建脚本（文本产物）。

    坐标在 Python 侧经 shape_geometry 算成磅值（PowerPoint 原生
    单位、左上原点、Y 向下）后以字面量写入；脚本用 COM 对象模型
    直建形状（.Name + .AlternativeText 双写语义 ID，与文件级
    descr 同标记）、真连接器绑定两端形状、导出 PNG/PDF
    （export-to-verify）并把枚举结果写成 JSON 供 com-verify 登记。
    """
    import json as _json
    fig_id = manifest["fig_id"]
    page_w, page_h = manifest["canvas"]["page_size_in"]
    role_entry = (manifest.get("role_palette") or {}).get("entry_id")
    shapes = list(manifest.get("shapes") or [])
    geoms = {s["shape_id"]: shape_geometry(manifest, s)
             for s in shapes}

    def box_pt(geom):
        left = (geom["pin_x"] - geom["width"] / 2) * 72
        top = (page_h - (geom["pin_y"] + geom["height"] / 2)) * 72
        return left, top, geom["width"] * 72, geom["height"] * 72

    def var_of(sid):
        return "$S_" + "".join(
            ch if ch.isalnum() else "_" for ch in sid)

    out = []
    out.append("# light-figure PowerPoint COM route: build script "
               "(generated, do not edit by hand; regenerate via "
               "`light-figure pptx com-script`).")
    out.append(f"# figure: {fig_id}  backend: powerpoint_com")
    out.append("# Run on a Windows machine with Microsoft "
               "PowerPoint installed: set $PkgRoot to this figure "
               "package's absolute path, then run this script in "
               "PowerShell. It builds the deck via the COM object "
               "model, exports PNG/PDF for verification, and writes "
               "a shape enumeration JSON for `light-figure pptx "
               "com-verify`. Coordinates are PowerPoint points "
               "(72 pt = 1 in), origin top-left, Y down; they were "
               "computed from the redraw manifest by light-figure's "
               "single transform.")
    out.append('$ErrorActionPreference = "Stop"')
    out.append('$PkgRoot = ""  # <-- set to the figure package root '
               '(absolute path)')
    embedded = _json.dumps(
        manifest_projection(manifest), ensure_ascii=False, indent=1)
    out.append("$ManifestJson = @'")
    out.append(embedded)
    out.append("'@")
    out.append("$Manifest = $ManifestJson | ConvertFrom-Json")
    out.append("$App = New-Object -ComObject PowerPoint.Application")
    out.append("$App.Visible = $true")
    out.append("$Pres = $App.Presentations.Add()")
    out.append(f"$Pres.PageSetup.SlideWidth = {_n_pt(page_w * 72)}")
    out.append(f"$Pres.PageSetup.SlideHeight = {_n_pt(page_h * 72)}")
    out.append("$Slide = $Pres.Slides.Add(1, 12)  # ppLayoutBlank")
    for shape in shapes:
        if shape["type"] == "image_residue":
            continue
        geom = geoms[shape["shape_id"]]
        left, top, width, height = box_pt(geom)
        sid = shape["shape_id"]
        var = var_of(sid)
        fill, line = _shape_colors(shape, role_entry)
        stype = shape["type"]
        out.append(f"# shape {sid} ({stype})")
        if stype == "text":
            out.append(f"{var} = $Slide.Shapes.AddTextbox(1, "
                       f"{_n_pt(left)}, {_n_pt(top)}, {_n_pt(width)}, "
                       f"{_n_pt(height)})")
            out.append(f"{var}.TextFrame.TextRange.Text = "
                       f"{_ps_str(shape.get('text') or '')}")
            font_pt = float((shape.get("style") or {}).get(
                "font_pt", 8))
            out.append(f"{var}.TextFrame.TextRange.Font.Size = "
                       f"{_n_pt(font_pt)}")
        elif stype == "line":
            out.append(f"{var} = $Slide.Shapes.AddLine("
                       f"{_n_pt(left)}, {_n_pt(top + height)}, "
                       f"{_n_pt(left + width)}, {_n_pt(top)})")
            if line:
                out.append(f"{var}.Line.ForeColor.RGB = "
                           f"{_com_rgb(line)}")
        else:
            mso = _MSO_SHAPE[stype]
            out.append(f"{var} = $Slide.Shapes.AddShape({mso}, "
                       f"{_n_pt(left)}, {_n_pt(top)}, {_n_pt(width)}, "
                       f"{_n_pt(height)})")
            if shape.get("text"):
                out.append(f"{var}.TextFrame.TextRange.Text = "
                           f"{_ps_str(shape['text'])}")
                font_pt = float((shape.get("style") or {}).get(
                    "font_pt", 8))
                out.append(f"{var}.TextFrame.TextRange.Font.Size = "
                           f"{_n_pt(font_pt)}")
            if fill:
                out.append(f"{var}.Fill.ForeColor.RGB = "
                           f"{_com_rgb(fill)}")
            else:
                out.append(f"{var}.Fill.Visible = 0")
            if line:
                out.append(f"{var}.Line.ForeColor.RGB = "
                           f"{_com_rgb(line)}")
                lw = float((shape.get("style") or {}).get(
                    "line_width_pt", 0.75))
                out.append(f"{var}.Line.Weight = {_n_pt(lw)}")
            else:
                out.append(f"{var}.Line.Visible = 0")
        out.append(f"{var}.Name = {_ps_str(sid)}")
        out.append(f"{var}.AlternativeText = "
                   f"{_ps_str(_DESCR_USER + sid)}")
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
            raise PptxError([f"arrow_plan {pid} 的端点形状未登记，"
                             "连接线无从落（清单与计划脱节）"])
        x1, y1 = src["pin_x"] * 72, (page_h - src["pin_y"]) * 72
        x2, y2 = dst["pin_x"] * 72, (page_h - dst["pin_y"]) * 72
        var = "$C_" + "".join(
            ch if ch.isalnum() else "_" for ch in pid)
        out.append(f"# connector {pid}: {entry.get('from')} -> "
                   f"{entry.get('to')} (real COM connection + "
                   "AlternativeText binding)")
        out.append(f"{var} = $Slide.Shapes.AddConnector(1, "
                   f"{_n_pt(x1)}, {_n_pt(y1)}, {_n_pt(x2)}, "
                   f"{_n_pt(y2)})")
        out.append(f"try {{ {var}.ConnectorFormat.BeginConnect("
                   f"{var_of(entry.get('from'))}, 1) }} catch {{}}")
        out.append(f"try {{ {var}.ConnectorFormat.EndConnect("
                   f"{var_of(entry.get('to'))}, 1) }} catch {{}}")
        out.append(f"{var}.Line.EndArrowheadStyle = 3  "
                   "# msoArrowheadTriangle")
        out.append(f"{var}.Name = {_ps_str('arrow-' + pid)}")
        out.append(f"{var}.AlternativeText = {_ps_str(_DESCR_ARROW + pid + ';from=' + str(entry.get('from')) + ';to=' + str(entry.get('to')))}")
        drawn.add(pid)
    for residue in manifest.get("bitmap_residue") or []:
        bound = [s for s in shapes
                 if s.get("type") == "image_residue"
                 and s.get("residue_id") == residue["residue_id"]]
        geom_src = bound[0] if bound else {
            "panel_id": residue.get("panel_id"),
            "box_local": residue["box_local"]}
        geom = shape_geometry(manifest, geom_src)
        left, top, width, height = box_pt(geom)
        name = f"residue-{residue['residue_id']}"
        var = "$R_" + "".join(
            ch if ch.isalnum() else "_" for ch in name)
        out.append(f"# placed residue {residue['residue_id']} "
                   f"({residue.get('class')})")
        out.append(f"{var} = $Slide.Shapes.AddPicture("
                   f"\"$PkgRoot/{residue['source']['path']}\", 0, -1, "
                   f"{_n_pt(left)}, {_n_pt(top)}, {_n_pt(width)}, "
                   f"{_n_pt(height)})")
        out.append(f"{var}.Name = {_ps_str(name)}")
        out.append(f"{var}.AlternativeText = "
                   f"{_ps_str(_DESCR_USER + name)}")
    exports = com_export_relpaths(fig_id)
    out.append("# export-to-verify: rendered outputs reconciled "
               "against the manifest at com-verify registration")
    out.append(f"$Slide.Export(\"$PkgRoot/{exports['png']}\", "
               "\"PNG\", 1600, 1200)")
    out.append(f"$Pres.SaveAs(\"$PkgRoot/{exports['pdf']}\", 32)  "
               "# ppSaveAsPDF")
    out.append(f"$Pres.SaveAs(\"$PkgRoot/{pptx_relpath(fig_id)}\", "
               "24)  # ppSaveAsOpenXMLPresentation: the COM-built "
               "deck lands at the standard artifact path; run "
               "`light-figure pptx extract` on it as usual")
    out.append("$items = @()")
    out.append("foreach ($s in $Slide.Shapes) {")
    out.append("  $txt = $null")
    out.append("  if ($s.HasTextFrame -and $s.TextFrame.HasText) "
               "{ $txt = $s.TextFrame.TextRange.Text }")
    out.append("  $begin = $null; $end = $null")
    out.append("  try { $begin = $s.ConnectorFormat."
               "BeginConnectedShape.Name } catch {}")
    out.append("  try { $end = $s.ConnectorFormat."
               "EndConnectedShape.Name } catch {}")
    out.append("  $items += [PSCustomObject]@{ name = $s.Name; "
               "alternative_text = $s.AlternativeText; shape_type = "
               "$s.Type; left_pt = $s.Left; top_pt = $s.Top; "
               "width_pt = $s.Width; height_pt = $s.Height; text = "
               "$txt; begin_connected_shape = $begin; "
               "end_connected_shape = $end }")
    out.append("}")
    out.append("$record = [PSCustomObject]@{ app = "
               "[PSCustomObject]@{ name = \"Microsoft PowerPoint\"; "
               "version = $App.Version }; slide_size_pt = "
               "@($Pres.PageSetup.SlideWidth, "
               "$Pres.PageSetup.SlideHeight); items = $items; "
               f"exports = @(\"{Path(exports['png']).name}\", "
               f"\"{Path(exports['pdf']).name}\") }}")
    out.append("$record | ConvertTo-Json -Depth 6 | Out-File "
               f"-Encoding utf8 \"$PkgRoot/"
               f"{com_verify_json_relpath(fig_id)}\"")
    out.append("$Pres.Close()")
    out.append("$App.Quit()")
    return "\n".join(out) + "\n"


def _n_pt(value) -> str:
    return f"{float(value):.2f}"


def generate_com_script(root, fig_id: str, by: str | None = None,
                        ) -> dict:
    """由 pptx manifest 生成 COM 构建脚本并登记 com_route 段。

    生成不置任何 verified（构建单 J3）；同内容重复生成拒绝
    （round_noop 同构：脚本不会有任何实质变化）。
    """
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
                         "补齐后经 pptx install 登记再生成 COM 脚本"])
    projection = component_hash(manifest_projection(manifest))
    existing = manifest.get("com_route") or {}
    if existing.get("manifest_projection") == projection \
            and existing.get("script"):
        raise PptxError([
            "round_noop：pptx manifest 内容投影与已生成的 COM 脚本"
            "一致，重复生成不会有任何实质变化——先实质修改清单再"
            "生成（FIG-D06 口径，三路同构）"])
    text = _generate_com_ps(manifest)
    path = root / com_script_relpath(fig_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    # .ps1 以 BOM UTF-8 落盘（Windows PowerShell 5.1 无 BOM 按 ANSI
    # 读，中文文本会乱码——与 ExtendScript 同口径处理）
    path.write_bytes(b"\xef\xbb\xbf" + text.encode("utf-8"))
    digest = sha256_file(path)
    from .util import utcnow
    manifest["com_route"] = {
        "form": "com_script",
        "backend": "powerpoint_com",
        "script": com_script_relpath(fig_id),
        "script_sha256": digest,
        "manifest_projection": projection,
        "status": "script_generated",
        "powerpoint_verified": False,
        "verify": None,
        "exports": com_export_relpaths(fig_id),
        "generated_at": utcnow(),
        "gap": "COM 构建脚本须在装有 PowerPoint 的 Windows 机器上"
               "执行（生成 .pptx + 导出 PNG/PDF + 枚举 JSON），再经 "
               "pptx com-verify 登记对账；本环境无 Office，实机部分"
               "未执行、未验证（powerpoint_verified 恒 false 至登记"
               "对账通过）",
    }
    save_pptx_manifest(root, manifest)
    return {
        "fig_id": fig_id,
        "com_script": com_script_relpath(fig_id),
        "com_script_sha256": digest,
        "powerpoint_verified": False,
        "status": "script_generated",
    }


def register_com_verify(root, fig_id: str, record_file,
                        by: str | None = None) -> dict:
    """登记 COM 运行的枚举回读 + 导出物，对 pptx manifest 对账。

    枚举坐标为磅值、左上原点（COM 口径），登记时换算回包口径再
    比（容差与文件级 extract 同为 0.02 in）。powerpoint_verified
    （com_route 段内）置真三件套见文件头纪律（构建单 J3）。
    """
    from .aibuild import _parse_note
    root = Path(root)
    manifest = load_pptx_manifest(root, fig_id)
    if manifest is None:
        raise PptxError([f"图 {fig_id} 无 pptx manifest"])
    com_route = manifest.get("com_route") or {}
    if not com_route:
        raise PptxError([f"图 {fig_id} 尚无 COM 路线登记（先 pptx "
                         "com-script 生成构建脚本）"])
    data = load_structured(Path(record_file))
    if not isinstance(data, dict):
        raise PptxError(["com-verify 记录须为 JSON 对象"
                         "（构建脚本枚举段产出）"])
    app = data.get("app") or {}
    if "PowerPoint" not in str(app.get("name") or ""):
        raise PptxError(["com-verify 记录缺 PowerPoint 应用名"
                         "（证据须带来源）"])
    items = data.get("items")
    if not isinstance(items, list):
        raise PptxError(["com-verify 记录缺 items 枚举列表"])
    page_w, page_h = manifest["canvas"]["page_size_in"]
    shapes, placed = [], []
    for item in items:
        if not isinstance(item, dict) or not item.get("name"):
            raise PptxError(["com-verify items 条目须为带 name 的"
                             "对象"])
        user_id, arrow = _parse_note(
            str(item.get("alternative_text") or ""))
        left = float(item.get("left_pt") or 0) / 72
        top = float(item.get("top_pt") or 0) / 72
        width = float(item.get("width_pt") or 0) / 72
        height = float(item.get("height_pt") or 0) / 72
        entry = {
            "shape_id": item.get("name"),
            "user_semantic_id": user_id,
            "pin_x": round(left + width / 2, 4),
            "pin_y": round(page_h - (top + height / 2), 4),
            "width": round(width, 4),
            "height": round(height, 4),
            "text": str(item.get("text") or "").strip(),
            "arrow": arrow,
            "begin_connected_shape": item.get(
                "begin_connected_shape"),
            "end_connected_shape": item.get("end_connected_shape"),
        }
        if str(item.get("name")).startswith("residue-"):
            placed.append(entry)
        else:
            shapes.append(entry)
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
    got = {s["shape_id"]: s for s in shapes}
    for sid, exp in expected.items():
        if sid not in got:
            diffs.append(f"COM 枚举缺清单形状 {sid}（漏建）")
            continue
        act = got[sid]
        for key in ("pin_x", "pin_y", "width", "height"):
            if abs(act[key] - exp[key]) > 0.02:
                diffs.append(f"形状 {sid} 的 {key} 与清单不符：枚举 "
                             f"{act[key]} vs 清单 {exp[key]:.3f}")
        if act["text"] != exp["text"]:
            diffs.append(f"形状 {sid} 文本与清单不符：枚举 "
                         f"{act['text']!r} vs 清单 {exp['text']!r}")
        if act.get("user_semantic_id") != sid:
            diffs.append(f"形状 {sid} 的 AlternativeText User ID 为 "
                         f"{act.get('user_semantic_id')!r}，与清单"
                         "语义 ID 不一致")
    for pid, entry in plan.items():
        conn = got.get(f"arrow-{pid}")
        if conn is None:
            diffs.append(f"COM 枚举缺 arrow_plan {pid} 的连接器对象")
            continue
        arrow = conn.get("arrow") or {}
        if arrow.get("from") != entry.get("from") \
                or arrow.get("to") != entry.get("to"):
            diffs.append(f"连接器 arrow-{pid} 的 AlternativeText "
                         f"端点与 arrow_plan 不一致：{arrow}")
        if conn.get("begin_connected_shape") \
                and conn["begin_connected_shape"] != entry.get("from"):
            diffs.append(f"连接器 arrow-{pid} 的 COM 实连起点为 "
                         f"{conn['begin_connected_shape']}，与计划 "
                         f"{entry.get('from')} 不符")
        if conn.get("end_connected_shape") \
                and conn["end_connected_shape"] != entry.get("to"):
            diffs.append(f"连接器 arrow-{pid} 的 COM 实连终点为 "
                         f"{conn['end_connected_shape']}，与计划 "
                         f"{entry.get('to')} 不符")
    residue_names = {f"residue-{r.get('residue_id')}"
                     for r in manifest.get("bitmap_residue") or []}
    placed_names = {p["shape_id"] for p in placed}
    for name in sorted(residue_names - placed_names):
        diffs.append(f"COM 枚举缺登记位图残留的置入图 {name}")
    for name in sorted(placed_names - residue_names):
        diffs.append(f"COM 枚举含未登记置入图 {name}")
    known = set(expected) | {f"arrow-{pid}" for pid in plan}
    for sid in got:
        if sid not in known:
            diffs.append(f"COM 枚举含未登记对象 {sid}")
    export_hashes = {}
    for name in data.get("exports") or []:
        candidate = root / "schematic" / "redraw" / str(name)
        if candidate.exists():
            export_hashes[str(name)] = sha256_file(candidate)
        else:
            diffs.append(f"export-to-verify 导出物 {name} 未存回本包"
                         "（导出对账缺件）")
    ok = not diffs
    from .util import utcnow
    verify = {
        "at": utcnow(),
        "source_file": Path(record_file).name,
        "app": {"name": app.get("name"),
                "version": app.get("version")},
        "ok": ok,
        "diffs": diffs,
        "export_sha256": export_hashes,
    }
    com_route["verify"] = verify
    # 每次登记先复位：新回读推翻旧结论时不许留旧真值（三路同纪律）
    com_route["powerpoint_verified"] = False
    com_route.pop("verified_by", None)
    com_route.pop("verified_at", None)
    if ok and app.get("version") and by:
        com_route["powerpoint_verified"] = True
        com_route["status"] = "verified"
        com_route["verified_by"] = by
        com_route["verified_at"] = utcnow()
        com_route.pop("gap", None)
    elif not ok:
        com_route["status"] = "verify_failed"
    manifest["com_route"] = com_route
    save_pptx_manifest(root, manifest)
    return {
        "fig_id": fig_id, "ok": ok, "diffs": diffs,
        "powerpoint_verified": bool(
            com_route.get("powerpoint_verified")),
        "status": com_route["status"],
        "exports": export_hashes,
    }
