"""复刻三路平权（用户 2026-10-21 推翻 FIG-D03）回归覆盖。

三后端合同接受 / Illustrator 生产路线（ExtendScript 生成冒烟、
DOM 回读解析与对账、produced 门分流、全链交付角色）/ PowerPoint
COM 实现形态（脚本生成冒烟、com-verify 登记对账）。实机不在场：
. ai 以 PDF 兼容占位件模拟（.ai 本为 PDF 载体），DOM 回读与 COM
枚举均以夹具 JSON 模拟——验的是契约与对账逻辑，不冒充实机证据。
"""
from pathlib import Path

import pytest

from light_figure.aibuild import (
    AiError, ai_manifest_path, ai_relpath, build_jsx_relpath,
    extract_ai, generate_build_scripts, install_ai_manifest,
    load_ai_manifest, readback_jsx_relpath,
)
from light_figure.audit import record_path, run_audit
from light_figure.delivery import generate_delivery
from light_figure.gates import advance
from light_figure.pptxbuild import (
    PptxError, com_script_relpath, generate_com_script,
    install_pptx_manifest, load_pptx_manifest, register_com_verify,
)
from light_figure.project import save_contract
from light_figure.redraw import shape_geometry
from light_figure.util import dump_json, load_structured, sha256_file
from light_figure.validate import validate_package

from conftest import (
    FIG_DATA, FIG_METHOD, data_contract, method_manifest,
    schematic_contract,
)

REDRAW_DIR = Path("schematic") / "redraw"


def _codes(root):
    report = validate_package(root)
    return [e["code"] for e in report["errors"]]


def _ai_manifest(root) -> dict:
    manifest = method_manifest()
    manifest["version"] = "1.1"
    manifest["backend"] = "illustrator_extendscript"
    manifest["reference"]["sha256"] = sha256_file(
        root / "schematic" / "reference" / "fig-method.png")
    manifest["arrow_plan"] = [{
        "arrow_plan_id": "AP-1", "from": "input-frame",
        "to": "predictor", "fact": "帧流进入预测器",
    }]
    manifest["shapes"][2]["connect"]["arrow_plan_id"] = "AP-1"
    return manifest


def _install_ai(root) -> dict:
    source = root / "tmp-ai-manifest.json"
    dump_json(source, _ai_manifest(root))
    return install_ai_manifest(root, FIG_METHOD, source)


def _readback_record(manifest, *, tamper_text=None) -> dict:
    items = []
    for shape in manifest["shapes"]:
        if shape["type"] == "image_residue":
            continue
        geom = shape_geometry(manifest, shape)
        text = shape.get("text")
        if tamper_text and shape["shape_id"] == tamper_text[0]:
            text = tamper_text[1]
        items.append({
            "name": shape["shape_id"],
            "note": f"light-figure:user-id={shape['shape_id']}",
            "typename": "TextFrame" if shape["type"] == "text"
                        else "PathItem",
            "pin_x": geom["pin_x"], "pin_y": geom["pin_y"],
            "width": geom["width"], "height": geom["height"],
            "text": text,
        })
    for entry in manifest.get("arrow_plan") or []:
        pid = entry["arrow_plan_id"]
        items.append({
            "name": f"arrow-{pid}",
            "note": f"light-figure:arrow={pid};from={entry['from']}"
                    f";to={entry['to']}",
            "typename": "PathItem", "pin_x": 5.0, "pin_y": 3.75,
            "width": 1.0, "height": 0.1, "text": None,
        })
        items.append({
            "name": f"arrow-{pid}-head",
            "note": f"light-figure:user-id=arrow-{pid}-head",
            "typename": "PathItem", "pin_x": 7.4, "pin_y": 3.75,
            "width": 0.16, "height": 0.11, "text": None,
        })
    return {
        "app": {"name": "Adobe Illustrator", "version": "28.0"},
        "document": {"page_size_in": [10.0, 7.5],
                     "color_space": "DocumentColorSpace.RGB"},
        "items": items,
        "preflight_facts": {
            "mixed_color_spaces": False,
            "white_overprint_detected": False,
            "white_overprint_probe": True,
            "pdfx_preset_available": True,
        },
    }


def _write_fake_ai(root) -> Path:
    """PDF 兼容的 .ai 占位件（正确页尺寸）：模拟实机存回的成品。"""
    import pymupdf
    path = root / ai_relpath(FIG_METHOD)
    doc = pymupdf.open()
    page = doc.new_page(width=720, height=540)
    page.draw_rect(pymupdf.Rect(36, 54, 324, 378))
    page.insert_text((40, 420), "Input video")
    page.insert_text((400, 200), "Threshold predictor")
    doc.save(str(path))
    doc.close()
    return path


def _ai_ready(produced_pkg) -> Path:
    """合同切 illustrator + ai manifest 登记 + 脚本生成的包。"""
    root = produced_pkg["root"]
    contract = schematic_contract()
    contract["schematic_backend"] = "illustrator"
    save_contract(root, contract)
    _install_ai(root)
    return root


@pytest.fixture()
def ai_pkg(produced_pkg):
    """Illustrator 路线全链走通（脚本→模拟实机→回读对账→交付）。"""
    root = _ai_ready(produced_pkg)
    generate_build_scripts(root, FIG_METHOD)
    _write_fake_ai(root)
    readback = root / REDRAW_DIR / "fig-method.dom-readback.json"
    manifest = load_ai_manifest(root, FIG_METHOD)
    dump_json(readback, _readback_record(manifest))
    result = extract_ai(root, FIG_METHOD, readback, by="tester")
    assert result["ok"], result["diffs"]
    assert advance(root)["advanced"]          # → produced
    run_audit(root)
    assert advance(root)["advanced"]          # → audited
    generate_delivery(root)
    assert advance(root)["advanced"]          # → delivered
    return produced_pkg


# ---------------------------------------------------------------- 合同层

def test_contract_accepts_illustrator_backend(filled_pkg):
    contract = schematic_contract()
    contract["schematic_backend"] = "illustrator"
    save_contract(filled_pkg["root"], contract)
    codes = _codes(filled_pkg["root"])
    assert "contract.schematic_backend_vocab" not in codes
    assert "contract.schematic_backend_on_data" not in codes


def test_data_figure_cannot_claim_illustrator_backend(filled_pkg):
    contract = data_contract()
    contract["schematic_backend"] = "illustrator"
    save_contract(filled_pkg["root"], contract)
    assert "contract.schematic_backend_on_data" in _codes(
        filled_pkg["root"])


def test_ai_manifest_install_rejects_out_of_page_geometry(produced_pkg):
    root = produced_pkg["root"]
    manifest = _ai_manifest(root)
    manifest["shapes"][2]["box_local"] = [0.9, 0.1, 0.5, 0.5]
    source = root / "tmp-ai-bad.json"
    dump_json(source, manifest)
    with pytest.raises(AiError):
        install_ai_manifest(root, FIG_METHOD, source)


# ---------------------------------------------------------------- Illustrator 路线

def test_ai_build_generates_jsx_scripts(produced_pkg):
    root = _ai_ready(produced_pkg)
    out = generate_build_scripts(root, FIG_METHOD)
    assert out["illustrator_verified"] is False
    assert out["evidence_level"] == "script"
    build_text = (root / build_jsx_relpath(FIG_METHOD)).read_text(
        encoding="utf-8-sig")
    for needle in ("input-frame", "predictor",
                   "light-figure:user-id=input-frame",
                   "Threshold predictor", "arrow-AP-1",
                   "light-figure:arrow=AP-1;from=input-frame",
                   "documents.add", "saveAs"):
        assert needle in build_text, needle
    readback_text = (root / readback_jsx_relpath(FIG_METHOD)).read_text(
        encoding="utf-8-sig")
    for needle in ("pageItems", "geometricBounds", "preflight_facts",
                   "dom-readback.json"):
        assert needle in readback_text, needle
    manifest = load_ai_manifest(root, FIG_METHOD)
    build = manifest["build"]
    assert build["illustrator_verified"] is False
    assert build["evidence_level"] == "script"
    assert build["gap"]                       # 实机 gap 如实登记
    assert manifest["status"] == "built"
    with pytest.raises(AiError):              # 同内容重复生成拒绝
        generate_build_scripts(root, FIG_METHOD)


def test_ai_extract_reconciles_dom_readback(produced_pkg):
    root = _ai_ready(produced_pkg)
    generate_build_scripts(root, FIG_METHOD)
    _write_fake_ai(root)
    readback = root / REDRAW_DIR / "fig-method.dom-readback.json"
    manifest = load_ai_manifest(root, FIG_METHOD)
    dump_json(readback, _readback_record(manifest))
    result = extract_ai(root, FIG_METHOD, readback, by="tester")
    assert result["ok"], result["diffs"]
    assert result["illustrator_verified"] is True
    assert result["evidence_level"] == "dom_readback"
    assert result["shapes_extracted"] == 5    # 3 形状 + 线 + 箭头头
    manifest = load_ai_manifest(root, FIG_METHOD)
    assert manifest["status"] == "verified"
    assert manifest["preflight"] == {
        "rgb_mixed": False, "broken_links": False,
        "low_res_images": False, "white_overprint": False,
        "pdfx": False}
    from light_figure.project import load_package, provenance_row
    entry = provenance_row(load_package(root)["provenance"], FIG_METHOD)
    assert entry["redraw_source"]["path"].endswith(".ai")


def test_ai_extract_without_by_keeps_unverified(produced_pkg):
    root = _ai_ready(produced_pkg)
    generate_build_scripts(root, FIG_METHOD)
    _write_fake_ai(root)
    readback = root / REDRAW_DIR / "fig-method.dom-readback.json"
    manifest = load_ai_manifest(root, FIG_METHOD)
    dump_json(readback, _readback_record(manifest))
    result = extract_ai(root, FIG_METHOD, readback)   # 无 --by 落字
    assert result["ok"]
    assert result["illustrator_verified"] is False


def test_ai_extract_tampered_text_blocks(produced_pkg):
    root = _ai_ready(produced_pkg)
    generate_build_scripts(root, FIG_METHOD)
    _write_fake_ai(root)
    readback = root / REDRAW_DIR / "fig-method.dom-readback.json"
    manifest = load_ai_manifest(root, FIG_METHOD)
    dump_json(readback, _readback_record(
        manifest, tamper_text=("predictor", "Threshold predict0r")))
    result = extract_ai(root, FIG_METHOD, readback, by="tester")
    assert result["ok"] is False
    assert any("predictor" in d and "文本" in d
               for d in result["diffs"])
    assert result["illustrator_verified"] is False
    manifest = load_ai_manifest(root, FIG_METHOD)
    assert manifest["status"] == "built"      # 未过对账不许 verified


def test_produced_gate_blocks_illustrator_without_readback(produced_pkg):
    root = _ai_ready(produced_pkg)
    generate_build_scripts(root, FIG_METHOD)  # 只生成脚本，未回读
    result = advance(root)
    assert result["advanced"] is False
    gaps = result["gaps"]
    assert any("DOM 回读对账未过" in g for g in gaps)
    assert any(".ai" in g for g in gaps)


def test_ai_full_chain_delivery_role(ai_pkg):
    root = ai_pkg["root"]
    delivery = load_structured(root / "exports" / "delivery.yaml")
    row = next(r for r in delivery["figures"]
               if r["fig_id"] == FIG_METHOD)
    roles = {f["role"] for f in row["files"]}
    assert "illustrator_source" in roles
    assert row["illustrator_verified"] is True


def test_native_gate_ai_not_auditable_without_readback(produced_pkg):
    root = _ai_ready(produced_pkg)
    generate_build_scripts(root, FIG_METHOD)
    _write_fake_ai(root)                      # 有成品、无回读登记
    run_audit(root)
    record = load_structured(record_path(root, FIG_METHOD))
    native = record["gates"]["native"]
    assert native["verdict"] == "NOT_AUDITABLE"


def test_native_gate_ai_unregistered_placed_bitmap_fails(ai_pkg):
    root = ai_pkg["root"]
    manifest = load_ai_manifest(root, FIG_METHOD)
    manifest["dom_readback"]["placed_items"] = [{
        "shape_id": "residue-stray", "file": "reference.png",
        "linked_file_ok": True, "effective_ppi": 300,
        "pin_x": 5.0, "pin_y": 3.75, "width": 2.0, "height": 1.5,
        "typename": "PlacedItem", "user_semantic_id": "residue-stray",
        "text": "", "arrow": None,
    }]
    dump_json(ai_manifest_path(root, FIG_METHOD), manifest)
    run_audit(root)
    record = load_structured(record_path(root, FIG_METHOD))
    native = record["gates"]["native"]
    assert native["verdict"] == "FIX_BEFORE_DELIVERY"
    codes = [f["code"] for f in native["findings"]]
    assert "native.unregistered_bitmap" in codes


# ---------------------------------------------------------------- PowerPoint COM 路线

def _pptx_manifest(root) -> dict:
    manifest = method_manifest()
    manifest["version"] = "1.1"
    manifest["backend"] = "python-pptx"
    manifest["reference"]["sha256"] = sha256_file(
        root / "schematic" / "reference" / "fig-method.png")
    manifest["arrow_plan"] = [{
        "arrow_plan_id": "AP-1", "from": "input-frame",
        "to": "predictor", "fact": "帧流进入预测器",
    }]
    manifest["shapes"][2]["connect"]["arrow_plan_id"] = "AP-1"
    return manifest


def _com_ready(produced_pkg) -> Path:
    root = produced_pkg["root"]
    source = root / "tmp-pptx-manifest.json"
    dump_json(source, _pptx_manifest(root))
    install_pptx_manifest(root, FIG_METHOD, source)
    return root


def _com_verify_record(manifest, *, shift_sid=None) -> dict:
    page_h = manifest["canvas"]["page_size_in"][1]
    items = []
    for shape in manifest["shapes"]:
        if shape["type"] == "image_residue":
            continue
        geom = shape_geometry(manifest, shape)
        left_pt = (geom["pin_x"] - geom["width"] / 2) * 72
        if shift_sid == shape["shape_id"]:
            left_pt += 72                     # 故意偏移 1 in
        items.append({
            "name": shape["shape_id"],
            "alternative_text":
                f"light-figure:user-id={shape['shape_id']}",
            "shape_type": 1,
            "left_pt": left_pt,
            "top_pt": (page_h - (geom["pin_y"] + geom["height"] / 2))
                      * 72,
            "width_pt": geom["width"] * 72,
            "height_pt": geom["height"] * 72,
            "text": shape.get("text"),
            "begin_connected_shape": None,
            "end_connected_shape": None,
        })
    for entry in manifest.get("arrow_plan") or []:
        items.append({
            "name": f"arrow-{entry['arrow_plan_id']}",
            "alternative_text":
                f"light-figure:arrow={entry['arrow_plan_id']}"
                f";from={entry['from']};to={entry['to']}",
            "shape_type": 1, "left_pt": 180, "top_pt": 200,
            "width_pt": 180, "height_pt": 1,
            "text": None,
            "begin_connected_shape": entry["from"],
            "end_connected_shape": entry["to"],
        })
    return {
        "app": {"name": "Microsoft PowerPoint", "version": "16.0"},
        "slide_size_pt": [720.0, 540.0],
        "items": items,
        "exports": ["fig-method.com-export.png",
                    "fig-method.com-export.pdf"],
    }


def test_pptx_com_script_generation(produced_pkg):
    root = _com_ready(produced_pkg)
    out = generate_com_script(root, FIG_METHOD)
    assert out["powerpoint_verified"] is False
    assert out["status"] == "script_generated"
    text = (root / com_script_relpath(FIG_METHOD)).read_text(
        encoding="utf-8-sig")
    for needle in ("PowerPoint.Application", "input-frame",
                   "light-figure:user-id=input-frame",
                   "AlternativeText", "AddConnector", "Export",
                   "SaveAs", "com-verify.json"):
        assert needle in text, needle
    manifest = load_pptx_manifest(root, FIG_METHOD)
    com_route = manifest["com_route"]
    assert com_route["powerpoint_verified"] is False
    assert com_route["gap"]                   # 实机 gap 如实登记
    with pytest.raises(PptxError):            # 同内容重复生成拒绝
        generate_com_script(root, FIG_METHOD)


def test_pptx_com_verify_registration(produced_pkg):
    root = _com_ready(produced_pkg)
    generate_com_script(root, FIG_METHOD)
    for name in ("fig-method.com-export.png",
                 "fig-method.com-export.pdf"):
        (root / REDRAW_DIR / name).write_bytes(b"export-bytes")
    manifest = load_pptx_manifest(root, FIG_METHOD)
    record = root / REDRAW_DIR / "fig-method.com-verify.json"
    dump_json(record, _com_verify_record(manifest))
    result = register_com_verify(root, FIG_METHOD, record, by="tester")
    assert result["ok"], result["diffs"]
    assert result["powerpoint_verified"] is True
    assert len(result["exports"]) == 2        # 导出物哈希已对账登记


def test_pptx_com_verify_tampered_blocks(produced_pkg):
    root = _com_ready(produced_pkg)
    generate_com_script(root, FIG_METHOD)
    for name in ("fig-method.com-export.png",
                 "fig-method.com-export.pdf"):
        (root / REDRAW_DIR / name).write_bytes(b"export-bytes")
    manifest = load_pptx_manifest(root, FIG_METHOD)
    record = root / REDRAW_DIR / "fig-method.com-verify.json"
    dump_json(record, _com_verify_record(manifest,
                                         shift_sid="predictor"))
    result = register_com_verify(root, FIG_METHOD, record, by="tester")
    assert result["ok"] is False
    assert any("predictor" in d for d in result["diffs"])
    assert result["powerpoint_verified"] is False
