"""逐页分诊：四项体检判定每页走文本层还是视觉通道。

规格见 deep-read-C.md 第二节第 1 小节。分诊结果连同原始数值写入
paper.yaml 的 triage 字段——分诊错了后面全错，所以必须可审计。
"""

from __future__ import annotations

import unicodedata
from pathlib import Path

import pymupdf

from .util import load_paper_yaml, save_paper_yaml

CHAR_THRESHOLD = 150       # 正文页文本层字符数下限
SCANNED_CHAR_MAX = 20      # 低于此视为无文本层
GARBLED_MAX = 0.01         # 乱码率上限 1%
GRAPHICS_DRAWINGS = 50     # 矢量对象数达到此量级视为图形密集页（豁免）

# ---- mixed 页可用性细分阈值（第六增量）----
# mixed 只是「没过 born-digital 严门槛」的统称，其中一部分页的文本层
# 其实基本可用。实测依据（ResNet arXiv:1512.03385 p5）：3890 字符、
# span 可解码率正常（font_ok）、覆盖不 suspicious，仅因 Table 3 里数学
# 字体的大括号分片字形（私有区 U+F8EE–F8FB 与控制位字形，共 64 字）
# 把乱码率顶到 1.64%，越过 1% 严门槛——这类页整页丢弃的代价是整页
# 正文 + 图（Figure 4）+ 表（Table 3）全失。故 mixed 单设可用通道，
# 三关同过才放行（放行 ≠ 免检：extract 侧降置信、provenance 打标、
# 原文.md 页首加注，无文本层的区域仍不解析）：
MIXED_USABLE_MIN_CHARS = 300     # born-digital 门槛（150）的 2 倍：低于此
                                 # 文本层信息量不足，多为零星水印/残字
MIXED_USABLE_GARBLED_MAX = 0.05  # 乱码率放宽到 5% 的前提是 font_ok（span
                                 # 可解码率 ≥0.95）同时通过：乱码须是字体
                                 # 编码怪癖（括号分片等），不是整层坏死


def _garbled_ratio(text: str) -> float:
    """乱码率 = (替换符 + 私有区字符 + 控制字符) / 总字符数。"""
    if not text:
        return 0.0
    bad = 0
    for ch in text:
        o = ord(ch)
        if o == 0xFFFD or 0xE000 <= o <= 0xF8FF:
            bad += 1
        elif unicodedata.category(ch) == "Cc" and ch not in "\n\t\r":
            bad += 1
    return bad / len(text)


def _font_check(doc: pymupdf.Document, page: pymupdf.Page) -> dict:
    """字体完整性：所用字体是否有 ToUnicode 映射 + span 文本可解码抽查。"""
    fonts = page.get_fonts(full=True)
    with_tounicode, total = 0, 0
    for font in fonts:
        xref = font[0]
        try:
            kind, _ = doc.xref_get_key(xref, "ToUnicode")
        except Exception:
            kind = ""
        total += 1
        if kind == "xref":
            with_tounicode += 1
    # span 可解码抽查：可打印/常见字符占比。
    # font_ok 以可解码率为主判据（ToUnicode 缺失但标准编码的 Base-14 字体同样
    # 可解码，不应误判）；ToUnicode 计数只作审计信息保留。
    spans = [s for b in page.get_text("dict")["blocks"]
             for ln in b.get("lines", []) for s in ln["spans"]]
    sample = "".join(s["text"] for s in spans)[:2000]
    if sample:
        ok_chars = sum(1 for ch in sample
                       if ch.isprintable() or ch in "\n\t")
        decodable = ok_chars / len(sample)
    else:
        decodable = 0.0
    font_ok = (total == 0) or decodable >= 0.95
    return {"fonts_total": total, "fonts_with_tounicode": with_tounicode,
            "span_decodable_ratio": round(decodable, 4), "font_ok": font_ok}


def _coverage(page: pymupdf.Page) -> dict:
    """图文覆盖粗估：文本块面积占比 vs 低分辨率渲染的墨迹占比。"""
    rect = page.rect
    page_area = rect.width * rect.height or 1.0
    text_area = 0.0
    for block in page.get_text("blocks"):
        x0, y0, x1, y1 = block[:4]
        text_area += max(0.0, (x1 - x0) * (y1 - y0))
    text_ratio = min(text_area / page_area, 1.0)
    # 36 dpi 灰度渲染，二值化统计墨迹（像素灰度 < 200 计为墨迹）
    pix = page.get_pixmap(dpi=36, colorspace=pymupdf.csGRAY)
    samples = pix.samples
    ink = sum(1 for v in samples if v < 200) / max(len(samples), 1)
    # 文本很多但墨迹远超文本覆盖 → 页面主要内容不在文本层里（如扫描图）
    suspicious = text_ratio > 0.02 and ink > 0.25 and text_ratio < 0.35 * ink
    return {"text_area_ratio": round(text_ratio, 4),
            "ink_ratio": round(ink, 4), "suspicious": bool(suspicious)}


def triage_page(doc: pymupdf.Document, page: pymupdf.Page) -> dict:
    """对单页做四项体检并分类。"""
    text = page.get_text()
    chars = len(text.strip())
    garbled = _garbled_ratio(text)
    fonts = _font_check(doc, page)
    coverage = _coverage(page)
    drawings = len(page.get_drawings())
    full_bleed_image = False
    for img in page.get_images(full=True):
        for r in page.get_image_rects(img[0]):
            if (r.width * r.height) >= 0.9 * (page.rect.width * page.rect.height):
                full_bleed_image = True

    graphics_page = drawings >= GRAPHICS_DRAWINGS and chars < CHAR_THRESHOLD
    if chars < SCANNED_CHAR_MAX and not graphics_page:
        kind, conf = "scanned", 0.9
    elif (chars >= CHAR_THRESHOLD and garbled < GARBLED_MAX
          and fonts["font_ok"] and not coverage["suspicious"]):
        kind, conf = "born_digital", 0.95
    elif graphics_page:
        # 图形密集页：字符少是版式所致，不判扫描页；仍走文本层 + 图形单独处理
        kind, conf = "born_digital", 0.6
    else:
        kind, conf = "mixed", 0.7
    # mixed 可用性细分（仅对 mixed 页判定，其余页为 None）：
    # 字符量、乱码率（放宽阈值）、字体可解码三关同过 + 覆盖不 suspicious
    # + 非整页大图（整页图 + 薄文本层多为扫描页的 OCR 残层，不放行）。
    mixed_usable = None
    if kind == "mixed":
        mixed_usable = bool(
            chars >= MIXED_USABLE_MIN_CHARS
            and garbled <= MIXED_USABLE_GARBLED_MAX
            and fonts["font_ok"]
            and not coverage["suspicious"]
            and not full_bleed_image)
    return {
        "page": page.number + 1,
        "page_kind": kind,
        "confidence": conf,
        "mixed_usable": mixed_usable,
        "chars": chars,
        "garbled_ratio": round(garbled, 4),
        "fonts": fonts,
        "coverage": coverage,
        "drawings": drawings,
        "full_bleed_image": full_bleed_image,
        "graphics_page": graphics_page,
    }


def triage(project_dir: Path, paper_id: str) -> dict:
    """对整篇论文逐页分诊，结果写入 paper.yaml 并返回汇总。"""
    pdir, paper = load_paper_yaml(project_dir, paper_id)
    doc = pymupdf.open(pdir / "原文.pdf")
    pages = [triage_page(doc, doc[i]) for i in range(len(doc))]
    doc.close()
    summary = {"born_digital": 0, "mixed": 0, "scanned": 0,
               "mixed_usable": 0, "mixed_unusable": 0}
    for p in pages:
        summary[p["page_kind"]] += 1
        if p["page_kind"] == "mixed":
            summary["mixed_usable" if p["mixed_usable"]
                    else "mixed_unusable"] += 1
    result = {"pages": pages, "summary": summary, "total_pages": len(pages)}
    paper["triage"] = result
    paper.setdefault("status", {})["triage"] = "done"
    save_paper_yaml(pdir, paper)
    return result
