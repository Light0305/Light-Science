"""导出渲染链测试（PLAN §5.3 P0）：组装变换、模板变量映射、
渲染后复核、工具缺失如实落字。

纪律：pandoc / LaTeX 引擎 / SVG 转换器缺席时相关用例 skip，
不许假渲染充数（与被测模块同一口径）。
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from light_write import export as exp
from light_write.project import load_package, manuscript_hash
from light_write.util import dump_json

from conftest import make_record

DEMO_PKG = (Path(__file__).resolve().parent.parent
            / "examples" / "demo-fullrun" / "manuscript-pkg")

pandoc_missing = exp.find_pandoc() is None
engine_missing = exp.find_latex_engine() is None
svg_missing = exp.find_svg_converter() is None


# ---------------------------------------------------------------- 配置映射

def test_profile_from_record_mapping():
    prof = exp.profile_from_record(make_record())
    assert prof["documentclass"] == "exart"
    assert prof["classoptions"] == ["onecolumn"]
    assert prof["citation_mode"] == "natbib"
    assert prof["bst_name"] == "exnum"
    assert prof["csl_id"] == "example-numeric"
    assert prof["journal_name"] == "Journal of Examples"


def test_profile_default_generic():
    prof = exp.profile_from_record(None)
    assert prof["documentclass"] == "article"
    assert prof["citation_mode"] == "citeproc"


# ---------------------------------------------------------------- 组装变换

def test_assemble_transforms(drafted_pkg):
    root = drafted_pkg["root"]
    pkg = load_package(root)
    combined, log, gaps = exp.assemble_markdown(pkg)
    assert gaps == []
    assert "[num:" not in combined and "[claim:" not in combined
    assert "[@" + drafted_pkg["cite_key"] + "]" in combined
    assert log["cited_keys"] == [drafted_pkg["cite_key"]]
    nums = {n["num_id"]: n for n in log["numbers"]}
    assert nums["N001"]["printed_in_text"] == "5.2"
    assert nums["N001"]["ledger_value"] == "5.2"
    # 摘要节被提升为元数据、不再以正文节出现
    assert log["abstract_hoisted"] == "00-abstract.md"
    assert "This study evaluates threshold adaptation" in combined


def test_assemble_value_mismatch_gap(drafted_pkg):
    root = drafted_pkg["root"]
    section = root / "sections" / "01-introduction.md"
    section.write_text(
        section.read_text(encoding="utf-8").replace("5.2", "9.9"),
        encoding="utf-8")
    pkg = load_package(root)
    _combined, _log, gaps = exp.assemble_markdown(pkg)
    assert any("N001" in g and "不符" in g for g in gaps)


def test_assemble_placeholder_gap(drafted_pkg):
    root = drafted_pkg["root"]
    section = root / "sections" / "02-methods.md"
    section.write_text(
        section.read_text(encoding="utf-8") + "\nAUTHOR_INPUT_NEEDED\n",
        encoding="utf-8")
    pkg = load_package(root)
    _combined, _log, gaps = exp.assemble_markdown(pkg)
    assert any("AUTHOR_INPUT_NEEDED" in g for g in gaps)


def test_assemble_unknown_citation_gap(drafted_pkg):
    root = drafted_pkg["root"]
    section = root / "sections" / "02-methods.md"
    section.write_text(
        section.read_text(encoding="utf-8") + "\nSee [@ghost2099-nope].\n",
        encoding="utf-8")
    pkg = load_package(root)
    _combined, _log, gaps = exp.assemble_markdown(pkg)
    assert any("不在 lock" in g for g in gaps)


def test_frontiers_metadata_numbering():
    structured = [
        {"name": "Ada Lovelace", "affiliation": "Lab A",
         "corresponding": True},
        {"name": "Alan Turing", "affiliation": "Lab B",
         "corresponding": False},
        {"name": "Grace Hopper", "affiliation": "Lab A",
         "corresponding": False},
    ]
    meta = exp._frontiers_metadata(structured)
    assert meta["frontiers_first_author_last"] == "Lovelace {et~al.}"
    assert "Ada Lovelace\\,$^{1,*}$" in meta["frontiers_authors"]
    assert "Alan Turing\\,$^{2}$" in meta["frontiers_authors"]
    assert "Grace Hopper\\,$^{1}$" in meta["frontiers_authors"]
    assert "$^{1}$Lab A" in meta["frontiers_address"]
    assert "$^{2}$Lab B" in meta["frontiers_address"]
    assert meta["frontiers_corr_author"] == "Ada Lovelace"
    assert meta["frontiers_corr_email"] == ""


# ---------------------------------------------------------------- 渲染

@pytest.mark.skipif(pandoc_missing, reason="本机无 pandoc")
def test_run_export_docx_tex(drafted_pkg):
    root = drafted_pkg["root"]
    record = exp.run_export(root, formats=("docx", "tex"),
                            profile=exp.default_profile())
    assert record["overall"] is True
    out = root / "export" / "generic"
    assert (out / "manuscript.docx").stat().st_size > 0
    assert (out / "manuscript.tex").stat().st_size > 0
    assert record["manuscript_hash"] == manuscript_hash(root)
    checks = {c["name"]: c["ok"] for c in record["checks"]}
    assert checks["numbers_in_render"] and checks["citations_in_render"]
    assert checks["wording_rescan"] and checks["placeholders_absent"]


@pytest.mark.skipif(pandoc_missing, reason="本机无 pandoc")
def test_export_check_stale(drafted_pkg):
    root = drafted_pkg["root"]
    exp.run_export(root, formats=("docx",), profile=exp.default_profile())
    fresh = exp.check_export(root)
    assert fresh["exports"] and fresh["exports"][0]["stale"] is False
    section = root / "sections" / "02-methods.md"
    section.write_text(
        section.read_text(encoding="utf-8") + "\nOne more sentence.\n",
        encoding="utf-8")
    stale = exp.check_export(root)
    assert stale["exports"][0]["stale"] is True


def test_export_check_empty(pkg):
    assert exp.check_export(pkg["root"])["exports"] == []


def test_pandoc_missing_named(monkeypatch, drafted_pkg):
    monkeypatch.setattr(exp, "find_pandoc", lambda: None)
    with pytest.raises(exp.ExportError) as exc:
        exp.run_export(drafted_pkg["root"], formats=("docx",))
    assert any("PANDOC_MISSING" in g for g in exc.value.gaps)


# ---------------------------------------------------------------- demo 全链

@pytest.fixture()
def demo_copy(tmp_path):
    dst = tmp_path / "demo-pkg"
    shutil.copytree(DEMO_PKG, dst)
    return dst


@pytest.mark.skipif(pandoc_missing or engine_missing or svg_missing,
                    reason="全链冒烟需 pandoc + LaTeX 引擎 + SVG 转换器")
def test_demo_full_chain(demo_copy):
    record = exp.run_export(demo_copy, formats=("docx", "tex", "pdf"),
                            profile=exp.default_profile())
    assert record["overall"] is True, record["checks"]
    out = demo_copy / "export" / "generic"
    for name in ("manuscript.docx", "manuscript.tex", "manuscript.pdf"):
        assert (out / name).stat().st_size > 0
    checks = {c["name"]: c for c in record["checks"]}
    assert checks["figures_in_render"]["ok"] is True
    assert record["transform_log"]["figures_placed"][0]["figure_id"] \
        == "F001"
    result = exp.check_export(demo_copy)
    assert result["exports"][0]["stale"] is False
    assert result["exports"][0]["ok"] is True


# ---------------------------------------------------------------- 模板库

def _fake_library(tmp_path, redistribution="packageable"):
    lib = tmp_path / "journal-templates"
    lib.mkdir()
    (lib / "artifacts").mkdir()
    (lib / "artifacts" / "fakeart.cls").write_text(
        "% fake class\n", encoding="utf-8")
    rows = [{
        "template_id": "fake-art", "publisher": "Fake Press",
        "redistribution": redistribution,
        "export_profile": {
            "label": "fakeart", "documentclass": "fakeart",
            "citation_mode": "natbib", "bst_name": "fakeart-num",
            "class_files": ["artifacts/fakeart.cls",
                            "artifacts/fakeart-num.bst"],
        },
    }, {
        "template_id": "reg-only", "publisher": "Reg Press",
        "redistribution": "channel_only",
    }]
    (lib / "registry.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    (lib / "artifacts" / "fakeart-num.bst").write_text(
        "% fake bst\n", encoding="utf-8")
    return lib


def test_library_profile_loads(tmp_path):
    lib = _fake_library(tmp_path)
    prof = exp.load_library_profile("fake-art", lib)
    assert prof["documentclass"] == "fakeart"
    assert prof["class_files"][0].endswith("fakeart.cls")
    assert Path(prof["class_files"][0]).is_absolute()


def test_library_profile_prohibited_blocked(tmp_path):
    lib = _fake_library(tmp_path, redistribution="prohibited")
    with pytest.raises(exp.ExportError):
        exp.load_library_profile("fake-art", lib)


def test_library_profile_without_mapping_blocked(tmp_path):
    lib = _fake_library(tmp_path)
    with pytest.raises(exp.ExportError):
        exp.load_library_profile("reg-only", lib)
    with pytest.raises(exp.ExportError):
        exp.load_library_profile("no-such-id", lib)


def test_library_profile_requires_library_root(drafted_pkg):
    with pytest.raises(exp.ExportError):
        exp.run_export(drafted_pkg["root"], formats=("docx",),
                       template_id="fake-art")
