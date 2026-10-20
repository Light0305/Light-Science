"""本地复核环（FIG-D11）：交付前与修订后对最终产物做纯本地机械
复核，不依赖外部服务，也不替代七门审计——复核只报 findings，
结论落 audit/<fig_id>.recheck.json 并声明复检范围（scope）。

复检纪律（与 STALE 全量重跑的关系）：修订后可只复检受影响的图与
面板——scope 记 {figures, panels, whole_file_checks}；面板级范围
只对能按面板归属的检查生效（方法图形状/用色），文件级检查（页
尺寸、字体嵌入）不可分，恒全文件并在记录中如实声明。改动区域外
的七门结论可沿用，但沿用须以本记录的范围声明为据，不许口头沿用。

量测口径如实落字：本环全部量测为**文件层结构量测**（PyMuPDF /
OPC / python-pptx 反读），不是渲染量测；无渲染器回验（FIG-D12
可缓未做），结论不冒充像素级一致性。
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path

from . import schema
from .audit import artifact_for
from .project import (
    load_package, schematic_artifact_relpath, schematic_backend,
)
from .util import dump_json, load_structured, utcnow

_TF_RE = re.compile(rb"/[A-Za-z0-9_.\-+]+\s+([0-9]+(?:\.[0-9]+)?)\s+Tf")


class RecheckError(Exception):
    def __init__(self, gaps):
        self.gaps = list(gaps)
        super().__init__("；".join(self.gaps))


def _finding(check, level, message):
    return {"check": check, "level": level, "message": message}


def _rgb_hex(value) -> str | None:
    """PyMuPDF drawings 的 color/fill 是 (r, g, b) 浮点元组；也兼容
    sRGB 整数形态。"""
    if value is None:
        return None
    if isinstance(value, (tuple, list)) and len(value) == 3:
        r, g, b = (float(v) for v in value)
    elif isinstance(value, (int, float)):
        rgb = int(value)
        r = (rgb >> 16 & 255) / 255.0
        g = (rgb >> 8 & 255) / 255.0
        b = (rgb & 255) / 255.0
    else:
        return None
    return "#%02x%02x%02x" % (round(r * 255), round(g * 255),
                              round(b * 255))


def _is_neutral(hex_color: str) -> bool:
    h = hex_color.lstrip("#")
    return h[0:2] == h[2:4] == h[4:6]


def _palette_colors(root, pkg) -> set | None:
    """合同允许色集：样式 bundle 的分类 + 连续色板（中性色另行豁免）。"""
    bundle_path = Path(root) / "data" / "styles" / "bundle.json"
    if not bundle_path.exists():
        return None
    bundle = load_structured(bundle_path)
    colors = set()
    for slot in ("categorical", "continuous"):
        entry = (bundle.get("palettes") or {}).get(slot) or {}
        for c in entry.get("colors") or []:
            colors.add(str(c).lower())
    return colors


def _role_colors(contract) -> set:
    from .style import ROLE_PALETTE_REGISTRY
    ref = (contract or {}).get("role_palette_ref") or {}
    reg = ROLE_PALETTE_REGISTRY.get(ref.get("entry_id")) or {}
    colors = {str(r["hex"]).lower() for r in reg.get("roles") or []}
    colors.add("#000000")
    return colors


# ---------------------------------------------------------------- 数据图

def _recheck_data(root, pkg, fig_id, contract, record) -> None:
    findings = record["findings"]
    artifact = Path(root) / "exports" / f"{fig_id}.pdf"
    try:
        import pymupdf
    except ImportError:
        findings.append(_finding(
            "environment", "fail",
            "PyMuPDF 未安装：本地复核无从执行（缺依赖如实落字）"))
        return
    doc = pymupdf.open(artifact)
    page = doc[0]
    w_mm = page.rect.width / 72 * 25.4
    h_mm = page.rect.height / 72 * 25.4
    journal = pkg["journal_contract"] or {}
    columns = journal.get("columns_mm") or {}
    candidates = [v for v in (columns.get("single"), columns.get("double"))
                  if isinstance(v, (int, float))]
    if candidates and min(abs(w_mm - c) for c in candidates) > 1.0:
        findings.append(_finding(
            "page_size", "fail",
            f"页宽 {w_mm:.1f} mm 与期刊栏宽 {candidates} 均不符"
            "（差 > 1 mm）"))
    else:
        findings.append(_finding(
            "page_size", "pass",
            f"页尺寸 {w_mm:.1f} × {h_mm:.1f} mm 与期刊栏宽相符"))
    max_h = journal.get("max_height_mm")
    if isinstance(max_h, (int, float)) and h_mm > max_h + 1.0:
        findings.append(_finding(
            "page_size", "fail", f"页高 {h_mm:.1f} mm 超期刊最大高 "
                                   f"{max_h} mm"))
    # 字体嵌入：查 FontDescriptor 的 FontFile/2/3 键（不许用
    # extract_font——它对 Base-14 内置字体也返回缓冲，会误报已嵌入）
    def _font_embedded(xref):
        def descriptor_of(x):
            kind, value = doc.xref_get_key(x, "FontDescriptor")
            if kind == "xref":
                return int(str(value).split()[0])
            kind2, value2 = doc.xref_get_key(x, "DescendantFonts")
            if kind2 == "array":
                m = re.search(r"(\d+)\s+0\s+R", str(value2))
                if m:
                    return descriptor_of(int(m.group(1)))
            return None

        fd = descriptor_of(xref)
        if fd is None:
            return False
        for key in ("FontFile", "FontFile2", "FontFile3"):
            kind, _value = doc.xref_get_key(fd, key)
            if kind == "xref":
                return True
        return False

    seen_fonts = {}
    for page_ in doc:
        for font in page_.get_fonts(full=True):
            seen_fonts[font[0]] = font[3]
    unembedded = [basefont for xref, basefont in seen_fonts.items()
                  if not _font_embedded(xref)]
    if unembedded:
        findings.append(_finding(
            "fonts_embedded", "fail",
            "未嵌入字体：" + "、".join(sorted(set(unembedded)))
            + "（投稿 PDF 须字体全嵌入）"))
    elif seen_fonts:
        findings.append(_finding(
            "fonts_embedded", "pass",
            f"{len(seen_fonts)} 个字体全部嵌入"))
    else:
        findings.append(_finding(
            "fonts_embedded", "warn", "PDF 无字体可查（无文本？）"))
    sizes = []
    for page_ in doc:
        for xref in page_.get_contents():
            stream = doc.xref_stream(xref) or b""
            sizes.extend(float(m) for m in _TF_RE.findall(stream))
    floor = float((journal.get("tolerances") or {}).get(
        "glyph_floor_pt", schema.TOLERANCE_PARAMS["glyph_floor_pt"]
        ["default"]))
    if sizes and min(sizes) < floor - 1e-9:
        findings.append(_finding(
            "min_font_size", "fail",
            f"实测最小字号 {min(sizes):.2f} pt < 地板 {floor} pt"))
    elif sizes:
        findings.append(_finding(
            "min_font_size", "pass",
            f"实测最小字号 {min(sizes):.2f} pt ≥ 地板 {floor} pt"))
    # 实际用色 vs 合同色板（填充/描边色采样，中性色豁免）
    allowed = _palette_colors(root, pkg)
    if allowed is None:
        findings.append(_finding(
            "colors_vs_palette", "warn",
            "样式 bundle 缺失：用色对色板检查跳过（未验，如实落字）"))
    else:
        used = set()
        for page_ in doc:
            for drawing in page_.get_drawings():
                for key in ("color", "fill"):
                    hx = _rgb_hex(drawing.get(key))
                    if hx:
                        used.add(hx)
        off = sorted(c for c in used
                     if c not in allowed and not _is_neutral(c))
        if off:
            findings.append(_finding(
                "colors_vs_palette", "fail",
                "实际用色越出合同色板（中性色除外）：" + "、".join(off)))
        else:
            findings.append(_finding(
                "colors_vs_palette", "pass",
                f"采样用色 {len(used)} 个均在合同色板或中性色内"))
    # 嵌入位图有效分辨率
    low_res = []
    n_images = 0
    for page_ in doc:
        for img in page_.get_images(full=True):
            n_images += 1
            xref = img[0]
            pix = pymupdf.Pixmap(doc, xref)
            for rect in page_.get_image_rects(xref):
                if rect.width > 0:
                    dpi = pix.width / (rect.width / 72.0)
                    if dpi < 200:
                        low_res.append(
                            f"xref {xref}：{dpi:.0f} dpi（显示 "
                            f"{rect.width:.0f} pt）")
    if low_res:
        findings.append(_finding(
            "raster_resolution", "fail",
            "嵌入位图有效分辨率 < 200 dpi：" + "；".join(low_res)))
    elif n_images:
        findings.append(_finding(
            "raster_resolution", "pass",
            f"{n_images} 个嵌入位图有效分辨率均 ≥ 200 dpi"))
    else:
        findings.append(_finding(
            "raster_resolution", "pass", "无嵌入位图（纯矢量）"))


# ---------------------------------------------------------------- 方法图

def _recheck_schematic(root, pkg, fig_id, contract, record,
                       panels_scope) -> None:
    findings = record["findings"]
    backend = schematic_backend(contract)
    artifact = artifact_for(root, pkg, fig_id)
    allowed = _role_colors(contract)
    if backend == "powerpoint":
        from .pptxbuild import extract_pptx_shapes, load_pptx_manifest
        manifest = load_pptx_manifest(root, fig_id) or {}
        shapes = extract_pptx_shapes(artifact)
        page_in = (manifest.get("canvas") or {}).get("page_size_in") \
            or [0, 0]
        from pptx import Presentation
        from pptx.util import Emu
        prs = Presentation(str(artifact))
        actual = [Emu(prs.slide_width).inches,
                  Emu(prs.slide_height).inches]
        if abs(actual[0] - page_in[0]) > 0.02 \
                or abs(actual[1] - page_in[1]) > 0.02:
            findings.append(_finding(
                "slide_size", "fail",
                f"幻灯片尺寸 {actual} 与 manifest 标定 {page_in} 不符"))
        else:
            findings.append(_finding(
                "slide_size", "pass",
                f"幻灯片尺寸 {actual} 与标定一致（= 图尺寸）"))
        missing = [s["shape_id"] for s in shapes
                   if not str(s["shape_id"]).startswith("arrow-")
                   and s.get("user_semantic_id") != s["shape_id"]
                   and not str(s["shape_id"]).startswith("residue-")]
        residue_missing = [
            s["shape_id"] for s in shapes
            if str(s["shape_id"]).startswith("residue-")
            and s.get("user_semantic_id") != s["shape_id"]]
        if missing or residue_missing:
            findings.append(_finding(
                "semantic_ids", "fail",
                "对象 User 语义 ID 缺失/不符："
                + "、".join(missing + residue_missing)))
        else:
            findings.append(_finding(
                "semantic_ids", "pass",
                f"{len(shapes)} 个对象的 User 语义 ID 齐备"))
        declared = {r.get("residue_id")
                    for r in manifest.get("bitmap_residue") or []}
        pics = [s for s in shapes
                if str(s["shape_id"]).startswith("residue-")]
        stray = [s["shape_id"] for s in pics
                 if s["shape_id"][len("residue-"):] not in declared]
        if stray:
            findings.append(_finding(
                "media_vs_residue", "fail",
                "未登记的图片对象：" + "、".join(stray)))
        else:
            findings.append(_finding(
                "media_vs_residue", "pass",
                f"图片对象 {len(pics)} 个均有残留登记"))
        return
    # visio 线
    from .redraw import extract_shapes, load_manifest
    manifest = load_manifest(root, fig_id) or {}
    shapes = extract_shapes(artifact)
    page_in = (manifest.get("canvas") or {}).get("page_size_in") or [0, 0]
    import xml.etree.ElementTree as ET
    with zipfile.ZipFile(artifact) as zf:
        names = zf.namelist()
        pages_xml = zf.read("visio/pages/pages.xml").decode("utf-8")
        media = [n for n in names if n.startswith("visio/media/")]
    m = re.search(r'N="PageWidth" V="([0-9.]+)"', pages_xml)
    w_actual = float(m.group(1)) if m else None
    m = re.search(r'N="PageHeight" V="([0-9.]+)"', pages_xml)
    h_actual = float(m.group(1)) if m else None
    if w_actual is None or abs(w_actual - page_in[0]) > 0.02 \
            or abs(h_actual - page_in[1]) > 0.02:
        findings.append(_finding(
            "page_size", "fail",
            f"成品页尺寸 {w_actual} × {h_actual} in 与 manifest 标定 "
            f"{page_in} 不符"))
    else:
        findings.append(_finding(
            "page_size", "pass",
            f"成品页尺寸 {w_actual} × {h_actual} in 与标定一致"))
    missing = [s["shape_id"] for s in shapes
               if s.get("user_semantic_id") != s["shape_id"]]
    if missing:
        findings.append(_finding(
            "semantic_ids", "fail",
            "形状 User.SemanticId 缺失/不符：" + "、".join(missing)))
    else:
        findings.append(_finding(
            "semantic_ids", "pass",
            f"{len(shapes)} 个形状的 User.SemanticId 齐备"))
    declared_media = {r.get("media_name")
                      for r in manifest.get("bitmap_residue") or []}
    stray = [n for n in media
             if n.rsplit("/", 1)[-1] not in declared_media]
    if stray:
        findings.append(_finding(
            "media_vs_residue", "fail",
            "未登记的包内 media：" + "、".join(stray)))
    else:
        findings.append(_finding(
            "media_vs_residue", "pass",
            f"包内 media {len(media)} 个均有残留登记"))
    # 实际用色 vs 角色色板（Cell FillForegnd/LineColor 采样）
    with zipfile.ZipFile(artifact) as zf:
        page1 = zf.read("visio/pages/page1.xml").decode("utf-8")
    used = {c.lower() for c in re.findall(
        r'N="(?:FillForegnd|LineColor)" V="(#[0-9a-fA-F]{6})"', page1)}
    off = sorted(c for c in used
                 if c not in allowed and not _is_neutral(c))
    if panels_scope:
        record["scope"]["panels_note"] = (
            "visio 线用色采样为整页 Cell 采样：面板范围只限定义务"
            "范围声明，颜色检查恒全页（如实落字）")
    if off:
        findings.append(_finding(
            "colors_vs_palette", "fail",
            "成品用色越出角色色板（中性色除外）：" + "、".join(off)))
    else:
        findings.append(_finding(
            "colors_vs_palette", "pass",
            f"采样用色 {len(used)} 个均在角色色板或中性色内"))


# ---------------------------------------------------------------- 入口

def run_recheck(root, fig_id: str | None = None,
                panels: list | None = None) -> dict:
    """对一图（或全包）跑本地复核，逐图落 audit/<fig>.recheck.json。

    panels 给定 = 局部复检（FIG-D11）：范围声明落记录，文件级检查
    恒全文件并注明不可分。返回 {figures: {fig_id: record 摘要}}。
    """
    root = Path(root)
    pkg = load_package(root)
    if pkg["head"] is None:
        raise RecheckError(["图包不存在（先 init）"])
    rows = pkg["head"].get("figures") or []
    targets = [r for r in rows
               if fig_id is None or r.get("fig_id") == fig_id]
    if not targets:
        raise RecheckError([f"图 {fig_id} 不在逐图状态表中"])
    out = {}
    for row in targets:
        fid = row["fig_id"]
        artifact = artifact_for(root, pkg, fid)
        record = {
            "kind": "light-figure/recheck",
            "fig_id": fid,
            "line": row.get("line"),
            "checked_at": utcnow(),
            "measurement_basis": "file_layer（文件层结构量测，"
                                 "非渲染量测）",
            "scope": {
                "figures": [fid],
                "panels": panels,
                "whole_file_checks": [
                    "page_size", "fonts_embedded", "min_font_size"],
                "note": ("局部复检：面板范围外的七门结论可沿用，"
                         "沿用以本范围声明为据（FIG-D11）"
                         if panels else "全图复检"),
            },
            "artifact": None,
            "findings": [],
        }
        if artifact is None:
            record["findings"].append(_finding(
                "artifact", "fail",
                "最终产物不存在：复核无从执行（先完成生产）"))
        else:
            record["artifact"] = str(artifact.relative_to(root))
            contract = pkg["contracts"].get(fid) or {}
            if row.get("line") == "data":
                _recheck_data(root, pkg, fid, contract, record)
            else:
                _recheck_schematic(root, pkg, fid, contract, record,
                                   panels)
        record["overall"] = "FINDINGS" if any(
            f["level"] == "fail" for f in record["findings"]) else "PASS"
        path = root / "audit" / f"{fid}.recheck.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        dump_json(path, record)
        out[fid] = {"overall": record["overall"],
                    "record": f"audit/{fid}.recheck.json",
                    "findings": record["findings"]}
    return {"figures": out}
