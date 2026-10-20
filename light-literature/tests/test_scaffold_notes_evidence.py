"""产品行为测试：translate-scaffold / verify 译文校验 / notes /
evidence / glossary。

setup 说明：开发期本文件的 source_map 由本地文本层抽取生成；
发布版无本地抽取，setup 改走产品路径——用 parse.build_source_map
把手工构造的 Doc2X 形态 middle_json 块锚点化，产物契约与 parse
命令一致。被测对象（translate / verify / notes / evidence /
glossary）不变。
"""

from __future__ import annotations

import json
import re

import pytest

from light_literature import evidence, glossary, notes, translate, verify
from light_literature import parse as parse_mod
from light_literature.cli import main as cli_main
from light_literature.util import (literature_dir, read_json,
                                   read_yaml, write_json)

_ANCHOR_RE = re.compile(r'<a id="([SCFTE]\d+)"></a>')


def _parsed(ingested):
    """ingest 后用产品路径造 source_map：手工 middle_json 块（标题 /
    正文 / 图 / 图注，形态与 conftest 合成 PDF 第一页对应）经
    parse.build_source_map 锚点化，并落盘 原文.md 与图资产占位文件。"""
    proj, pid = ingested
    pdir = literature_dir(proj) / pid
    paper = read_yaml(pdir / "paper.yaml")
    blocks = [
        {"type": "text", "page": 1, "bbox": [72, 60, 520, 95],
         "provenance": "engine:doc2x",
         "text": "A Study of Testable Pipelines", "text_level": 1},
        {"type": "text", "page": 1, "bbox": [72, 110, 520, 260],
         "provenance": "engine:doc2x",
         "text": ("This is a test paragraph for the literature pipeline. "
                  "It contains enough characters to pass the triage "
                  "threshold for a born digital page, with ordinary words "
                  "and numbers like 42 and 3.14 included for realism.")},
        {"type": "figure", "page": 1, "bbox": [150, 300, 430, 480],
         "provenance": "engine:doc2x", "asset": "assets/figures/fig1.png"},
        {"type": "caption", "page": 1, "bbox": [150, 490, 430, 520],
         "provenance": "engine:doc2x",
         "text": "Figure 1: A red rectangle used as a test figure.",
         "caption_of": 2},
    ]
    smap, md_text, _stats = parse_mod.build_source_map(blocks, paper)
    write_json(pdir / "source_map.json", smap)
    (pdir / "原文.md").write_text(md_text, encoding="utf-8")
    fig = pdir / "assets" / "figures" / "fig1.png"
    fig.parent.mkdir(parents=True, exist_ok=True)
    fig.write_bytes(b"\x89PNG fake test asset")
    return proj, pid, pdir


def _inject_table_and_equation(pdir):
    """往 source_map 注入一个 T 块和一个 E 块（translate/notes 只读 source_map）。"""
    smap = read_json(pdir / "source_map.json")
    max_order = max(b.get("order") or 0 for b in smap["blocks"])
    smap["blocks"] += [
        {"id": "T001", "page": 1, "type": "table", "order": max_order + 1,
         "bbox": [72, 540, 520, 640], "confidence": 0.5,
         "provenance": "test-injected", "caption_id": None, "no_caption": True,
         "table_md": "| Method | Score |\n|---|---|\n| SECRET_DATA_CELL | 99 |",
         "rows": 2, "cols": 2},
        {"id": "E001", "page": 1, "type": "equation", "order": max_order + 2,
         "bbox": [72, 660, 300, 690], "confidence": 0.55,
         "provenance": "test-injected", "text": "SECRET_FORMULA a+b=c"},
    ]
    write_json(pdir / "source_map.json", smap)
    return smap


# ---------- translate-scaffold ----------

def test_translate_scaffold_aligns_anchor_ids(ingested):
    proj, pid, pdir = _parsed(ingested)
    smap = _inject_table_and_equation(pdir)
    stats = translate.translate_scaffold(proj, pid)
    zh = (pdir / "原文_中文翻译.md").read_text(encoding="utf-8")
    smap_ids = [b["id"] for b in sorted(
        (b for b in smap["blocks"] if b.get("id")),
        key=lambda b: b.get("order") or 0)]
    assert _ANCHOR_RE.findall(zh) == smap_ids  # 集合与顺序都一致
    assert stats["blocks"] == len(smap_ids)
    for b in smap["blocks"]:
        if b.get("id"):
            expect = f"**原文:** 原文.md#{b['id']}（p.{b['page']}）"
            assert expect in zh, expect  # 每块回指行格式与页码正确


def test_translate_scaffold_does_not_copy_table_or_formula(ingested):
    proj, pid, pdir = _parsed(ingested)
    _inject_table_and_equation(pdir)
    translate.translate_scaffold(proj, pid)
    zh = (pdir / "原文_中文翻译.md").read_text(encoding="utf-8")
    assert "SECRET_DATA_CELL" not in zh   # 表格数据不复制
    assert "SECRET_FORMULA" not in zh     # 公式本体不重复渲染
    assert "表头（待译）" in zh
    assert "译注（待填）" in zh
    fig_block = [b for b in read_json(pdir / "source_map.json")["blocks"]
                 if b["type"] == "figure"][0]
    assert fig_block["asset"] in zh       # 图块只给资产引用


# ---------- verify 的译文校验 ----------

def test_verify_translation_skipped_without_zh_file(ingested):
    proj, pid, pdir = _parsed(ingested)
    report = verify.verify(proj, pid)
    assert report["ok"]
    assert report["translation"]["status"] == "skipped"


def test_verify_translation_passes_on_scaffold(ingested):
    proj, pid, pdir = _parsed(ingested)
    translate.translate_scaffold(proj, pid)
    report = verify.verify(proj, pid)
    assert report["ok"], report["errors"]
    assert report["translation"]["status"] == "checked"
    assert report["translation"]["errors"] == []
    assert report["translation"]["anchors_in_translation"] == \
        report["anchors_in_source_map"]


def test_verify_translation_detects_missing_anchor(ingested):
    proj, pid, pdir = _parsed(ingested)
    translate.translate_scaffold(proj, pid)
    zh_path = pdir / "原文_中文翻译.md"
    zh = zh_path.read_text(encoding="utf-8")
    zh_path.write_text(zh.replace('<a id="S001"></a>', ""), encoding="utf-8")
    report = verify.verify(proj, pid)
    assert not report["ok"]
    assert any("译文缺失锚点" in e and "S001" in e for e in report["errors"])


def test_verify_translation_detects_wrong_backref_page(ingested):
    proj, pid, pdir = _parsed(ingested)
    translate.translate_scaffold(proj, pid)
    zh_path = pdir / "原文_中文翻译.md"
    zh = zh_path.read_text(encoding="utf-8")
    zh_path.write_text(
        zh.replace("**原文:** 原文.md#S001（p.1）", "**原文:** 原文.md#S001（p.99）"),
        encoding="utf-8")
    report = verify.verify(proj, pid)
    assert not report["ok"]
    assert any("回指行" in e and "S001" in e for e in report["errors"])


# ---------- notes ----------

def test_notes_generates_full_card(ingested):
    proj, pid, pdir = _parsed(ingested)
    _inject_table_and_equation(pdir)
    stats = notes.generate_notes(proj, pid)
    text = (pdir / "阅读笔记.md").read_text(encoding="utf-8")
    # 文件头与证据状态头
    assert "A Study of Testable Pipelines" in text
    assert "10.0000/test.1" in text
    for key in ("Source coverage", "Extraction confidence",
                "Locator mode", "Context verification"):
        assert key in text
    # 精读 16 节齐全
    for i in range(1, 17):
        assert f"## {i:02d} " in text, f"缺第 {i} 节"
    assert stats["sections_16"] == 16
    # S4 自动清单条数与 source_map 的 F/T/E 块数一致
    smap = read_json(pdir / "source_map.json")
    expect_s4 = sum(1 for b in smap["blocks"]
                    if b.get("id") and b["type"] in ("figure", "table", "equation"))
    s4_section = text.split("## S4 图表清单")[1].split("## S5")[0]
    s4_rows = [ln for ln in s4_section.splitlines()
               if re.match(r"\| [FTE]\d{3} \|", ln)]
    assert len(s4_rows) == expect_s4 == stats["s4_items"]
    # 速读段是中间检查点的口径 + 关键纪律在位
    assert "中间检查点" in text
    assert "不支持的更强结论（必填）" in text
    assert "只许作者" in text or "只许作者自述" in text
    # 原子卡附录五类齐全，微结构三段齐全
    for card in ("金句卡", "概念卡", "反直觉卡", "方法卡", "结构卡"):
        assert f"## {card}" in text
    assert text.count("**复述**") >= 5 and text.count("**启发**") >= 5


# ---------- evidence ----------

def test_evidence_add_assigns_sequential_ids(tmp_path):
    proj = tmp_path / "p"
    r1 = evidence.add_evidence(proj, "paper_x", "发现一", 3,
                               statistic="42", claim_strength="direct")
    r2 = evidence.add_evidence(proj, "paper_x", "发现二", 5)
    assert (r1["evidence_id"], r2["evidence_id"]) == ("E001", "E002")
    lines = (literature_dir(proj) / "证据表.jsonl").read_text(
        encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["statistic"] == "42"


def test_evidence_correct_appends_without_touching_original(tmp_path):
    proj = tmp_path / "p"
    evidence.add_evidence(proj, "paper_x", "原始发现", 3)
    fixed = evidence.correct_evidence(proj, "E001", page=4,
                                      finding="修正后的发现")
    assert fixed["evidence_id"] == "E002"
    assert fixed["corrects"] == "E001"
    assert fixed["page"] == 4
    rows = [json.loads(ln) for ln in (literature_dir(proj) / "证据表.jsonl")
            .read_text(encoding="utf-8").strip().splitlines()]
    assert rows[0]["page"] == 3 and "corrects" not in rows[0]  # 原行不动
    with pytest.raises(ValueError):
        evidence.correct_evidence(proj, "E999", page=1)       # 目标不存在
    with pytest.raises(ValueError):
        evidence.correct_evidence(proj, "E001")               # 无修正字段


def test_evidence_validation_rejections(tmp_path):
    proj = tmp_path / "p"
    with pytest.raises(ValueError):
        evidence.add_evidence(proj, "paper_x", "  ", 1)       # finding 空
    with pytest.raises(ValueError):
        evidence.add_evidence(proj, "paper_x", "发现", None)  # page 必填
    with pytest.raises(ValueError):
        evidence.add_evidence(proj, "paper_x", "发现", 1,
                              quote="第一句。第二句。")          # 引文两句（中文）
    with pytest.raises(ValueError):
        evidence.add_evidence(proj, "paper_x", "发现", 1,
                              quote="First sentence. Second one!")  # 英文两句
    with pytest.raises(ValueError):
        evidence.add_evidence(proj, "paper_x", "发现", 1,
                              claim_strength="strong")       # 枚举外
    # 一句引文 + 小数不误判
    row = evidence.add_evidence(proj, "paper_x", "发现", 1,
                                quote="Accuracy reached 3.14 points overall.")
    assert row["evidence_id"] == "E001"


# ---------- glossary ----------

def test_glossary_add_and_duplicates(tmp_path):
    proj = tmp_path / "p"
    out = glossary.add_term(proj, "attention mechanism", "注意力机制",
                            note="核心概念")
    assert "注意力机制" in out["row"]
    with pytest.raises(ValueError) as ei:
        glossary.add_term(proj, "Attention Mechanism", "注意力")  # 英文重复（大小写不敏感）
    assert "已有行" in str(ei.value)
    with pytest.raises(ValueError):
        glossary.add_term(proj, "self-attention", "注意力机制")   # 译名重复
    glossary.add_term(proj, "self-attention", "自注意力")
    text = (literature_dir(proj) / "术语账本.md").read_text(encoding="utf-8")
    assert text.count("注意力机制") == 1
    assert "| self-attention | 自注意力 |" in text


# ---------- CLI 冒烟 ----------

def test_cli_new_commands_smoke(ingested, tmp_path):
    proj, pid, pdir = _parsed(ingested)
    assert cli_main(["translate-scaffold", str(pdir)]) == 0
    assert cli_main(["notes", str(pdir)]) == 0
    assert cli_main(["evidence", "add", str(proj), "--paper", pid,
                     "--finding", "CLI 证据", "--page", "1",
                     "--claim-strength", "direct"]) == 0
    assert cli_main(["glossary", "add", str(proj), "--term", "token",
                     "--zh", "词元"]) == 0
    assert cli_main(["glossary", "add", str(proj), "--term", "token",
                     "--zh", "令牌"]) == 2  # 重复 → 错误退出码
    assert cli_main(["verify", str(proj), pid]) == 0
