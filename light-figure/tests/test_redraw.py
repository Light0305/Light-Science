"""重绘 manifest 契约、文件级 .vsdx 构建、反抽对账、位图残留登记。"""

import zipfile

import pytest

from light_figure.redraw import (
    RedrawError, build_vsdx, extract_and_reconcile, extract_shapes,
    install_manifest, shape_geometry, validate_manifest,
)
from light_figure.util import dump_json, load_structured, sha256_file
from conftest import FIG_METHOD, method_manifest


def test_shape_geometry_roundtrip():
    manifest = method_manifest()
    shape = manifest["shapes"][0]
    geo = shape_geometry(manifest, shape)
    # 面板 a: 像素 [20,30]-[180,210]，刻度 0.025 in/px，Y 翻转（页高 7.5）
    assert geo["pin_x"] == pytest.approx((20 + 180) / 2 * 0.025)
    assert geo["width"] == pytest.approx(160 * 0.025)
    assert geo["pin_y"] == pytest.approx(7.5 - (30 + 210) / 2 * 0.025)


def test_validate_rejects_out_of_bounds_shape():
    manifest = method_manifest()
    manifest["shapes"][0]["box_local"] = [0.5, 0.5, 0.9, 0.9]
    gaps = validate_manifest(manifest)
    assert any("出界" in g for g in gaps)


def test_validate_rejects_bad_connect_target():
    manifest = method_manifest()
    manifest["shapes"][2]["connect"]["to"] = "missing-shape"
    gaps = validate_manifest(manifest)
    assert any("指向不存在的形状" in g for g in gaps)


def test_validate_rejects_unknown_residue_class():
    manifest = method_manifest()
    manifest["bitmap_residue"] = [{
        "residue_id": "r1", "class": "decoration", "panel_id": "a",
        "media_name": "visio/media/r1.png",
        "box_local": [0.0, 0.0, 0.25, 0.25],
        "source": {"path": "schematic/reference/fig-method.png",
                   "sha256": "a" * 64},
        "reason": "x"}]
    gaps = validate_manifest(manifest)
    assert any("不在合法类别" in g for g in gaps)


def _install(produced_pkg_fixture):
    return produced_pkg_fixture


def test_built_vsdx_is_opc_and_reconciles(produced_pkg):
    root = produced_pkg["root"]
    vsdx = root / "schematic" / "redraw" / "fig-method.vsdx"
    assert vsdx.exists()
    with zipfile.ZipFile(vsdx) as zf:
        names = set(zf.namelist())
    assert "[Content_Types].xml" in names
    assert "visio/pages/page1.xml" in names
    shapes = extract_shapes(vsdx)
    assert {s["shape_id"] for s in shapes} == {
        "input-frame", "input-label", "predictor"}
    manifest = load_structured(
        root / "schematic" / "redraw" / "fig-method.manifest.json")
    assert manifest["build"]["visio_verified"] is False
    assert manifest["reconciliation"]["ok"] is True
    assert manifest["status"] == "verified"
    prov_hash = sha256_file(vsdx)
    assert manifest["build"]["artifact_sha256"] == prov_hash


def test_extract_detects_unregistered_shape(produced_pkg, tmp_path):
    root = produced_pkg["root"]
    # 在成品里塞一个未登记形状 → 反抽对账必须点名
    vsdx = root / "schematic" / "redraw" / "fig-method.vsdx"
    with zipfile.ZipFile(vsdx) as zf:
        parts = {n: zf.read(n) for n in zf.namelist()}
    page = parts["visio/pages/page1.xml"].decode("utf-8")
    rogue = ('<Shape ID="99" NameU="rogue" Type="Shape">'
             '<Cell N="PinX" V="1"/><Cell N="PinY" V="1"/>'
             '<Cell N="Width" V="1"/><Cell N="Height" V="1"/></Shape>')
    page = page.replace("</Shapes>", rogue + "</Shapes>")
    parts["visio/pages/page1.xml"] = page.encode("utf-8")
    with zipfile.ZipFile(vsdx, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in parts.items():
            zf.writestr(name, data)
    outcome = extract_and_reconcile(root, FIG_METHOD)
    assert outcome["ok"] is False
    assert any("rogue" in d for d in outcome["diffs"])


def test_install_rejects_reference_hash_mismatch(pkg, tmp_path):
    manifest = method_manifest()
    manifest["reference"]["sha256"] = "b" * 64
    path = tmp_path / "bad.json"
    dump_json(path, manifest)
    with pytest.raises(RedrawError):
        install_manifest(pkg["root"], FIG_METHOD, path)
