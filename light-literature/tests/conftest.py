"""测试共用工具：用 PyMuPDF 现场合成测试 PDF（不依赖外部文件）。"""

from __future__ import annotations

from pathlib import Path

import pymupdf
import pytest


def make_pdf(path: Path, kind: str = "text") -> Path:
    """合成测试 PDF。

    kind="text"：第 1 页含标题、长段落、图片与图注；第 2 页只有图片（扫描页形态）。
    kind="blank"：单页空白（无文本无图）。
    """
    doc = pymupdf.open()
    if kind == "blank":
        doc.new_page(width=595, height=842)
    else:
        page = doc.new_page(width=595, height=842)
        page.insert_text((72, 80), "A Study of Testable Pipelines",
                         fontsize=17, fontname="helv")
        body = ("This is a test paragraph for the literature pipeline. "
                "It contains enough characters to pass the triage threshold "
                "for a born digital page, with ordinary words and numbers "
                "like 42 and 3.14 included for realism in extraction.")
        page.insert_textbox(pymupdf.Rect(72, 110, 520, 260),
                            body * 2, fontsize=11, fontname="helv")
        pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 60, 40))
        pix.set_rect(pymupdf.IRect(0, 0, 60, 40), (200, 60, 60))
        page.insert_image(pymupdf.Rect(150, 300, 430, 480),
                          stream=pix.tobytes("png"))
        page.insert_text((150, 505),
                         "Figure 1: A red rectangle used as a test figure.",
                         fontsize=10, fontname="helv")
        page2 = doc.new_page(width=595, height=842)
        pix2 = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 120, 160))
        pix2.set_rect(pymupdf.IRect(0, 0, 120, 160), (80, 80, 160))
        page2.insert_image(pymupdf.Rect(60, 60, 540, 780),
                           stream=pix2.tobytes("png"))
    doc.save(path)
    doc.close()
    return path


@pytest.fixture()
def demo_pdf(tmp_path) -> Path:
    return make_pdf(tmp_path / "test-paper.pdf")


@pytest.fixture()
def ingested(tmp_path, demo_pdf):
    """init + ingest 后的 (项目目录, paper_id)。"""
    from light_literature import project

    proj = tmp_path / "proj"
    info = project.ingest(proj, demo_pdf, doi="10.0000/test.1",
                          title="A Study of Testable Pipelines")
    return proj, info["paper_id"]
