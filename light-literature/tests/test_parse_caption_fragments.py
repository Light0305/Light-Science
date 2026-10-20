"""回归测试：Doc2X 图注碎片合并 + 附录编号分序列。

实测来源（CEA 110856, Doc2X 轨首跑）：Doc2X layout 把每条表注拆成
「标签块 + 正文块」（caption_of 同指一表），未合并时正文块成孤儿、
正文数字（2.5-minute 等）被编号兜底误当图号；附录 Table A.1–A.6 与
正文 Table 1–6 混在一条序列里撞号。本测试以手造 middle blocks 复现
该形态，断言 build_source_map 合并碎片、附录编号进 appendix series，
且 verify 编号序列检查分序列通过。
"""

from __future__ import annotations

from pathlib import Path

import yaml

from light_literature import parse as parse_mod
from light_literature import verify as verify_mod
from light_literature.util import write_json

_TABLE_HTML = ("<table><tr><th>a</th></tr><tr><td>1</td></tr></table>")


def _blocks():
    """raw 顺序即 caption_of 下标基准：表在 1/4，碎片图注紧随其后。"""
    return [
        {"type": "text", "page": 1, "order_in_page": 1,
         "bbox": [0, 0, 100, 10], "text": "Intro text.", "text_level": 0},
        {"type": "table", "page": 5, "order_in_page": 2,
         "bbox": [0, 20, 100, 60], "table_body": _TABLE_HTML},
        {"type": "caption", "page": 5, "order_in_page": 3,
         "bbox": [0, 62, 30, 70], "text": "Table 1", "caption_of": 1},
        {"type": "caption", "page": 5, "order_in_page": 4,
         "bbox": [0, 72, 100, 80], "caption_of": 1,
         "text": "Video lengths for each of the 2.5-minute test videos."},
        {"type": "table", "page": 10, "order_in_page": 5,
         "bbox": [0, 20, 100, 60], "table_body": _TABLE_HTML},
        {"type": "caption", "page": 10, "order_in_page": 6,
         "bbox": [0, 62, 30, 70], "text": "Table", "caption_of": 4},
        {"type": "caption", "page": 10, "order_in_page": 7,
         "bbox": [0, 72, 100, 80], "caption_of": 4,
         "text": "A.1 Measured performances in a 5-minute video."},
    ]


def test_split_table_captions_merged_with_trace():
    smap, _md, stats = parse_mod.build_source_map(
        _blocks(), {"paper_id": "p", "title": "t", "sha256": "x"})
    caps = [b for b in smap["blocks"] if b.get("type") == "caption"]
    assert len(caps) == 2, caps
    main, appendix = caps
    assert main["text"].startswith("Table 1 Video lengths")
    assert main["caption_kind"] == "table"
    assert main["caption_number"] == 1  # 不是正文里的 2.5
    assert "caption_series" not in main
    assert main["merged_from"] == [2, 3]
    assert appendix["text"].startswith("Table A.1 Measured")
    assert appendix["caption_number"] == 1
    assert appendix["caption_series"] == "appendix"
    tables = [b for b in smap["blocks"] if b.get("type") == "table"]
    assert [t["caption_id"] for t in tables] == [main["id"], appendix["id"]]
    assert stats["anchors"]["C"] == 2


def test_verify_passes_with_main_and_appendix_series(tmp_path: Path):
    smap, md_text, _stats = parse_mod.build_source_map(
        _blocks(), {"paper_id": "paper_x", "title": "t", "sha256": "x"})
    pdir = tmp_path / "Literature" / "paper_x"
    pdir.mkdir(parents=True)
    (pdir / "paper.yaml").write_text(
        yaml.safe_dump({"paper_id": "paper_x", "title": "t"}),
        encoding="utf-8")
    write_json(pdir / "source_map.json", smap)
    (pdir / "原文.md").write_text(md_text, encoding="utf-8")
    report = verify_mod.verify(tmp_path, "paper_x")
    assert report["ok"], report
    assert report["orphan_captions"] == []
    assert report["errors"] == []
