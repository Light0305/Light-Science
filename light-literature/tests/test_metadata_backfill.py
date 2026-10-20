"""LIT-D03 元数据回填测试：逐字段来源、空值纪律、notes 文件头两路。"""

from __future__ import annotations

import json
from pathlib import Path

import pymupdf
import pytest

from light_literature import metadata as meta_mod
from light_literature import notes as notes_mod
from light_literature import project as project_mod
from light_literature.util import read_yaml

FIXTURES = Path(__file__).parent / "fixtures"


def _make_pdf(path: Path, *, author: str | None = None,
              header_line: str | None = None) -> Path:
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    y = 80
    if header_line:
        page.insert_text((72, y), header_line, fontsize=10, fontname="helv")
        y += 30
    page.insert_text((72, y), "A Study of Metadata Backfill",
                     fontsize=16, fontname="helv")
    page.insert_textbox(
        pymupdf.Rect(72, y + 30, 520, y + 160),
        "Body text with enough ordinary words to look like a first page "
        "of a paper, without any year-like numbers in the prose itself.",
        fontsize=11, fontname="helv")
    if author:
        doc.set_metadata({"author": author, "title": "A Study of Metadata"})
    doc.save(path)
    doc.close()
    return path


def _ingest(tmp_path, pdf, **kw):
    proj = tmp_path / "proj"
    info = project_mod.ingest(proj, pdf, **kw)
    return proj, info["paper_id"]


def test_local_backfill_year_and_author(tmp_path):
    pdf = _make_pdf(tmp_path / "p.pdf", author="Jane Doe",
                    header_line="Copyright © 2021 The Authors")
    proj, pid = _ingest(tmp_path, pdf)
    paper = read_yaml(proj / "Literature" / pid / "paper.yaml")
    md = paper["metadata"]
    assert md["year"] == {"value": 2021, "source": "pdf_first_page",
                          "verified": False}
    assert md["authors"]["value"] == ["Jane Doe"]
    assert md["authors"]["source"] == "pdf_metadata"
    assert md["venue"]["value"] is None  # 文本层不猜 venue


def test_empty_discipline_nothing_invented(tmp_path):
    pdf = _make_pdf(tmp_path / "p.pdf")  # 无作者、无年份线索
    proj, pid = _ingest(tmp_path, pdf)
    paper = read_yaml(proj / "Literature" / pid / "paper.yaml")
    md = paper["metadata"]
    assert md["authors"]["value"] is None
    assert md["year"]["value"] is None
    assert md["venue"]["value"] is None
    assert "pdf" in md["attempted_sources"]


def test_ambiguous_years_stay_empty(tmp_path):
    # 首页出现两个不同年份且都无版权/出版上下文 → 歧义，留空不许猜
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((72, 80), "A Study of Ambiguous Years",
                     fontsize=16, fontname="helv")
    page.insert_textbox(
        pymupdf.Rect(72, 120, 520, 260),
        "We compare the 2019 baseline against the 2021 variant and "
        "discuss both at length in this long ordinary prose paragraph.",
        fontsize=11, fontname="helv")
    pdf = tmp_path / "p.pdf"
    doc.save(pdf)
    doc.close()
    proj, pid = _ingest(tmp_path, pdf)
    summary = meta_mod.backfill_metadata(proj, pid)
    assert summary["metadata"]["year"]["value"] is None


def test_crossref_backfill_priority_and_unverified(tmp_path):
    pdf = _make_pdf(tmp_path / "p.pdf", author="Wrong Author")
    proj, pid = _ingest(tmp_path, pdf, doi="10.1038/s41586-021-03819-2")

    def fake_get(url, params=None, headers=None):
        if "api.crossref.org/works/" in url:
            return 200, (FIXTURES / "crossref_work_alphafold2.json").read_bytes()
        raise AssertionError(f"意外 URL：{url}")

    summary = meta_mod.backfill_metadata(proj, pid, online=True, get=fake_get)
    md = summary["metadata"]
    assert md["authors"]["source"] == "crossref"      # 权威源优先于 PDF 元数据
    assert "Jumper" in md["authors"]["value"][0]
    assert md["venue"] == {"value": "Nature", "source": "crossref",
                           "verified": False}          # 回填不冒充已核实
    assert md["year"]["value"] == 2021
    assert "crossref" in md["attempted_sources"]


def test_confirm_marks_verified(tmp_path):
    pdf = _make_pdf(tmp_path / "p.pdf", header_line="Copyright © 2021 X")
    proj, pid = _ingest(tmp_path, pdf)
    summary = meta_mod.backfill_metadata(proj, pid, confirm=True)
    assert summary["metadata"]["year"]["verified"] is True
    assert summary["metadata"]["confirmed_by"] == "user"


def _add_source_map(proj, pid):
    pdir = proj / "Literature" / pid
    (pdir / "source_map.json").write_text(json.dumps({
        "paper_id": pid, "blocks": [
            {"id": "S001", "page": 1, "type": "text", "order": 1,
             "text": "hello world"}],
        "pending_pages": []}), encoding="utf-8")


def test_notes_header_uses_backfill(tmp_path):
    pdf = _make_pdf(tmp_path / "p.pdf", author="Jane Doe",
                    header_line="Copyright © 2021 The Authors")
    proj, pid = _ingest(tmp_path, pdf)
    _add_source_map(proj, pid)
    notes_mod.generate_notes(proj, pid)
    text = (proj / "Literature" / pid / "阅读笔记.md").read_text(
        encoding="utf-8")
    assert "Jane Doe" in text and "未核实" in text
    assert "2021" in text


def test_notes_header_fallback_todo(tmp_path):
    pdf = _make_pdf(tmp_path / "p.pdf")
    proj, pid = _ingest(tmp_path, pdf)
    _add_source_map(proj, pid)
    notes_mod.generate_notes(proj, pid)
    text = (proj / "Literature" / pid / "阅读笔记.md").read_text(
        encoding="utf-8")
    assert "（待填）（paper.yaml 无作者字段" in text  # 原 待填 行一字不变
