"""选材排除（SC3）与分页构造（SC4）。"""

from __future__ import annotations

from light_copyright import render, schema, select as select_mod
from light_copyright.util import wrap_line
from conftest import drive_to_frozen, write_source


def test_selection_excludes_third_party_and_tests(tmp_path, case_dir,
                                                  facts_file):
    src = write_source(tmp_path)
    drive_to_frozen(case_dir, facts_file, src)
    sel = select_mod.scan_candidates(case_dir)
    included = {e["path"] for e in sel["included"]}
    excluded = {e["path"]: e["reasons"] for e in sel["exclusions"]}
    assert included == {"app/core.py", "app/main.py"}
    assert any("版权" in r for r in excluded["app/borrowed.py"])
    assert any("测试" in r for r in excluded["tests/test_core.py"])


def test_secret_file_excluded(tmp_path, case_dir, facts_file):
    src = write_source(tmp_path)
    (src / "app" / "config.py").write_text(
        'API_KEY = "sk-fake-0000000000"\n', encoding="utf-8")
    drive_to_frozen(case_dir, facts_file, src)
    sel = select_mod.scan_candidates(case_dir)
    excluded = {e["path"] for e in sel["exclusions"]}
    assert "app/config.py" in excluded


def test_appeal_moves_with_trace(tmp_path, case_dir, facts_file):
    src = write_source(tmp_path)
    drive_to_frozen(case_dir, facts_file, src)
    select_mod.scan_candidates(case_dir)
    sel = select_mod.appeal(case_dir, "app/borrowed.py",
                            "归属自证：该文件为本项目自有，头为模板残留")
    paths = {e["path"] for e in sel["included"]}
    assert "app/borrowed.py" in paths
    assert sel["appealed"][0]["reason"].startswith("归属自证")
    # 无理由申诉被拒
    import pytest
    from light_copyright.case import CaseError
    with pytest.raises(CaseError):
        select_mod.appeal(case_dir, "tests/test_core.py", "  ")


def _stream(n):
    return [{"text": f"line-{i}", "file": "a.py", "line": i}
            for i in range(n)]


def test_paginate_exact_pages():
    pages = render.paginate(_stream(150), 50)
    assert [len(p) for p in pages] == [50, 50, 50]


def test_paginate_last_page_partial():
    pages = render.paginate(_stream(151), 50)
    assert [len(p) for p in pages] == [50, 50, 50, 1]


def test_front_back_at_boundary_60():
    pages = render.paginate(_stream(60 * 50), 50)
    kept, omitted = render.front_back(pages)
    assert omitted is None and len(kept) == 60


def test_front_back_over_limit_records_omission():
    pages = render.paginate(_stream(61 * 50), 50)
    kept, omitted = render.front_back(pages)
    assert len(kept) == 60
    assert omitted["omitted_pages"] == 1
    assert omitted["omitted_from_page"] == 31
    assert omitted["omitted_to_page"] == 31
    assert omitted["omitted_lines"] == 50


def test_wrap_wide_chars_count_two_columns():
    line = "汉" * 60  # 120 列，须折为两行
    pieces = wrap_line(line, schema.WRAP_COLUMNS)
    assert len(pieces) == 2
    assert "".join(pieces) == line  # 只切分不改字（HC-1）


def test_wrap_short_line_untouched():
    assert wrap_line("abc", 100) == ["abc"]
