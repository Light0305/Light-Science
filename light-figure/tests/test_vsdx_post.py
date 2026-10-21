"""Visio 文件级后处理格（工具规划 T2：vsdx vendored 化）回归覆盖。

vendored 本体 = dave-howard/vsdx 0.6.1（BSD-3），逐字节收编于
light_figure/vendor/vsdx/，vsdxpost 是唯一加载口。覆盖：版本
钉死断言、抽取、改字（与清单对齐放行 / 与清单分叉如实报
diff）、改色（语义 ID 与文本双定位、歧义点名）、未命中点名、
diff（与备份比对）。后处理成品的 extract 对账与 provenance
哈希刷新是纪律的一部分，一并断言。
"""
from pathlib import Path

import pytest

from light_figure.provenance import update_provenance_row  # noqa: F401
from light_figure.project import load_package, provenance_row
from light_figure.redraw import (
    load_manifest, save_manifest, vsdx_relpath,
)
from light_figure.util import sha256_file
from light_figure.vsdxpost import (
    PostError, VSDX_PINNED_VERSION, load_vendored_vsdx, post_diff,
    post_extract, post_replace_text, post_set_fill,
)

from conftest import FIG_METHOD


def _rows_by_id(result):
    return {row["shape_id"]: row for row in result["shapes"]}


def test_vendored_vsdx_is_pinned_and_licensed():
    module = load_vendored_vsdx()
    assert module.__version__ == VSDX_PINNED_VERSION == "0.6.1"
    assert getattr(module, "__light_figure_vendored__", False) is True
    vendor_dir = Path(module.__file__).parent
    assert (vendor_dir / "VENDOR.md").exists()
    license_text = (vendor_dir / "LICENSE").read_text(encoding="utf-8")
    assert "BSD 3-Clause License" in license_text
    assert "Dave Howard" in license_text


def test_post_extract_lists_built_shapes(produced_pkg):
    root = produced_pkg["root"]
    result = post_extract(root, FIG_METHOD)
    assert result["tool"].startswith("vsdx 0.6.1")
    rows = _rows_by_id(result)
    assert set(rows) == {"input-frame", "input-label", "predictor"}
    assert rows["input-label"]["text"] == "Input video"
    assert rows["predictor"]["text"] == "Threshold predictor"
    assert rows["predictor"]["fill"]  # 角色色已落 Cell


def test_post_extract_requires_build(filled_pkg):
    with pytest.raises(PostError):
        post_extract(filled_pkg["root"], FIG_METHOD)


def test_post_replace_text_aligned_with_manifest(produced_pkg):
    """先改清单再后处理对齐：改字写回 → 强制 extract 对账 ok，
    manifest 账与 provenance 哈希同步刷新，备份留痕。"""
    root = produced_pkg["root"]
    manifest = load_manifest(root, FIG_METHOD)
    for shape in manifest["shapes"]:
        if shape["shape_id"] == "input-label":
            shape["text"] = "Input stream"
    save_manifest(root, manifest)

    result = post_replace_text(root, FIG_METHOD, "Input video",
                               "Input stream", by="tester")
    assert result["replacements"] == 1
    assert result["reconciliation"]["ok"] is True
    artifact_hash = sha256_file(root / vsdx_relpath(FIG_METHOD))
    assert result["artifact_sha256"] == artifact_hash
    backup = root / result["backup"]
    assert backup.exists()  # 写前备份（同目录时间戳副本）

    after = load_manifest(root, FIG_METHOD)
    assert len(after["post_processing"]) == 1
    entry = after["post_processing"][0]
    assert entry["op"] == "replace_text"
    assert entry["by"] == "tester"
    assert entry["hits"][0]["shape_id"] == "input-label"
    prov = load_package(root)["provenance"]
    row = provenance_row(prov, FIG_METHOD)
    assert row["redraw_source"]["hash"] == artifact_hash
    assert row["manual_corrections_log"] == \
        "schematic/redraw/fig-method.manifest.json#post_processing"
    rows = _rows_by_id(post_extract(root, FIG_METHOD))
    assert rows["input-label"]["text"] == "Input stream"


def test_post_replace_text_divergence_is_reported(produced_pkg):
    """只改成品不改清单：对账如实报文本 diff，不许静默放行。"""
    root = produced_pkg["root"]
    result = post_replace_text(root, FIG_METHOD, "Input video",
                               "Renamed off-manifest")
    assert result["reconciliation"]["ok"] is False
    assert any("input-label" in d
               for d in result["reconciliation"]["diffs"])
    rows = _rows_by_id(post_extract(root, FIG_METHOD))
    assert rows["input-label"]["text"] == "Renamed off-manifest"


def test_post_replace_text_no_match_names_gap(produced_pkg):
    root = produced_pkg["root"]
    before = sha256_file(root / vsdx_relpath(FIG_METHOD))
    with pytest.raises(PostError):
        post_replace_text(root, FIG_METHOD, "不存在的文本", "x")
    assert sha256_file(root / vsdx_relpath(FIG_METHOD)) == before


def test_post_set_fill_by_semantic_id(produced_pkg):
    root = produced_pkg["root"]
    result = post_set_fill(root, FIG_METHOD, shape_id="predictor",
                           fill="#FF0000", by="tester")
    assert result["after"]["fill"] == "#ff0000"
    assert result["reconciliation"]["ok"] is True
    rows = _rows_by_id(post_extract(root, FIG_METHOD))
    assert rows["predictor"]["fill"] == "#ff0000"


def test_post_set_fill_by_text_and_guards(produced_pkg):
    root = produced_pkg["root"]
    result = post_set_fill(root, FIG_METHOD,
                           text="Threshold predictor", line="#00FF00")
    assert result["shape_id"] == "predictor"
    assert result["after"]["line"] == "#00ff00"
    with pytest.raises(PostError):  # 定位不到点名
        post_set_fill(root, FIG_METHOD, shape_id="no-such-shape",
                      fill="#000000")
    with pytest.raises(PostError):  # 定位方式二选一
        post_set_fill(root, FIG_METHOD, shape_id="predictor",
                      text="Threshold predictor", fill="#000000")
    with pytest.raises(PostError):  # 色值形态
        post_set_fill(root, FIG_METHOD, shape_id="predictor",
                      fill="red")


def test_post_diff_against_pre_post_backup(produced_pkg):
    root = produced_pkg["root"]
    artifact = root / vsdx_relpath(FIG_METHOD)
    pristine = produced_pkg["tmp"] / "pristine.vsdx"
    pristine.write_bytes(artifact.read_bytes())
    same = post_diff(root, FIG_METHOD, pristine)
    assert same["identical"] is True

    manifest = load_manifest(root, FIG_METHOD)
    for shape in manifest["shapes"]:
        if shape["shape_id"] == "input-label":
            shape["text"] = "Input stream"
    save_manifest(root, manifest)
    post_replace_text(root, FIG_METHOD, "Input video", "Input stream")
    changed = post_diff(root, FIG_METHOD, pristine)
    assert changed["identical"] is False
    assert "visio/pages/page1.xml" in changed["changed_members"]
