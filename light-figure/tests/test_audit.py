"""审计引擎七门：全链正例 + 逐门负例 + STALE 纪律。"""

import shutil
import zipfile

import pymupdf
import pytest

from light_figure.audit import (
    AuditError, audit_status, run_audit, set_review_disposition,
)
from light_figure.gates import advance
from light_figure.util import dump_json, load_structured, sha256_file
from conftest import FIG_DATA, FIG_METHOD


def _gates(root, fig_id):
    record = load_structured(root / "audit" / f"{fig_id}.audit.json")
    return record["gates"]


def test_full_chain_advances_to_audited(produced_pkg):
    root = produced_pkg["root"]
    result = advance(root)  # contracted → produced
    assert result["advanced"], result["gaps"]
    outcome = run_audit(root)
    overalls = {f["overall"] for f in outcome["figures"].values()}
    assert overalls <= {"PASS", "REVIEW_REQUIRED"}, outcome
    data_gates = _gates(root, FIG_DATA)
    assert data_gates["alignment"]["verdict"] == "PASS"
    assert data_gates["glyph"]["verdict"] == "PASS"
    assert data_gates["honesty"]["verdict"] == "PASS"
    assert data_gates["contract"]["verdict"] == "PASS"
    method_gates = _gates(root, FIG_METHOD)
    assert method_gates["native"]["verdict"] == "PASS"
    assert method_gates["policy_block"]["verdict"] == "PASS"
    # REVIEW 门逐门落处置理由后才许过 audited 门
    for fig_id, gates in ((FIG_DATA, data_gates),
                          (FIG_METHOD, method_gates)):
        for name, gate in gates.items():
            if gate.get("applicable") and gate["verdict"] == \
                    "REVIEW_REQUIRED":
                set_review_disposition(root, fig_id, name,
                                       "已人工复核：容差内可接受")
    result = advance(root)  # produced → audited
    assert result["advanced"], result["gaps"]
    # delivered 段（Phase 3 已接入）：未生成 delivery.yaml 前如实停住
    result = advance(root)
    assert result["advanced"] is False
    assert any("delivery.yaml" in g for g in result["gaps"])


def test_audit_status_stale_after_artifact_change(produced_pkg):
    root = produced_pkg["root"]
    advance(root)
    run_audit(root)
    status = audit_status(root)
    assert status["figures"][FIG_DATA]["state"] == "FRESH"
    pdf = root / "exports" / "fig-data.pdf"
    with pdf.open("ab") as fh:
        fh.write(b"% tampered\n")
    status = audit_status(root)
    assert status["figures"][FIG_DATA]["state"] == "STALE"
    result = advance(root)  # produced → audited 应被 STALE 拦住
    assert result["advanced"] is False
    assert any("STALE" in g for g in result["gaps"])


def test_note_rejected_when_stale(produced_pkg):
    root = produced_pkg["root"]
    advance(root)
    run_audit(root)
    pdf = root / "exports" / "fig-data.pdf"
    with pdf.open("ab") as fh:
        fh.write(b"% changed\n")
    with pytest.raises(AuditError):
        set_review_disposition(root, FIG_DATA, "collisions", "理由")


def _fake_pdf(path, width_pt=612, height_pt=200, fontsize=9,
              boxes=((72, 72, "Panel label"),)):
    doc = pymupdf.open()
    page = doc.new_page(width=width_pt, height=height_pt)
    for x, y, text in boxes:
        page.insert_text((x, y), text, fontsize=fontsize)
    doc.save(path)
    doc.close()


def test_glyph_gate_blocks_tiny_text(pkg):
    root = pkg["root"]
    _fake_pdf(root / "exports" / "fig-data.pdf", fontsize=3)
    run_audit(root, fig_id=FIG_DATA)
    glyph = _gates(root, FIG_DATA)["glyph"]
    assert glyph["verdict"] == "FIX_BEFORE_DELIVERY"


def test_collisions_gate_blocks_overlapping_text(pkg):
    root = pkg["root"]
    _fake_pdf(root / "exports" / "fig-data.pdf", boxes=(
        (72, 100, "Overlapping label text"),
        (74, 101, "Overlapping label text"),
    ))
    run_audit(root, fig_id=FIG_DATA)
    assert _gates(root, FIG_DATA)["collisions"]["verdict"] == \
        "FIX_BEFORE_DELIVERY"


def test_contract_gate_blocks_wrong_width(pkg):
    root = pkg["root"]
    _fake_pdf(root / "exports" / "fig-data.pdf", width_pt=500)
    run_audit(root, fig_id=FIG_DATA)
    contract = _gates(root, FIG_DATA)["contract"]
    assert contract["verdict"] == "FIX_BEFORE_DELIVERY"


def test_alignment_gate_blocks_misaligned_panels(produced_pkg):
    root = produced_pkg["root"]
    manifest_path = root / "audit" / "fig-data.alignment-input.json"
    manifest = load_structured(manifest_path)
    manifest["panels"][1]["bbox_pt"][1] += 6.0  # 第二面板顶边下移 6pt
    dump_json(manifest_path, manifest)
    run_audit(root, fig_id=FIG_DATA)
    assert _gates(root, FIG_DATA)["alignment"]["verdict"] == \
        "FIX_BEFORE_DELIVERY"


def test_honesty_gate_blocks_reversed_axis(produced_pkg):
    root = produced_pkg["root"]
    script = root / "data" / "scripts" / "fig-data.py"
    text = script.read_text(encoding="utf-8").replace(
        "direction: increasing, limits: [0, 100]",
        "direction: decreasing, limits: [0, 100]")
    script.write_text(text, encoding="utf-8")
    run_audit(root, fig_id=FIG_DATA)
    assert _gates(root, FIG_DATA)["honesty"]["verdict"] == \
        "FIX_BEFORE_DELIVERY"


def test_honesty_gate_blocks_undeclared_truncation(produced_pkg):
    root = produced_pkg["root"]
    script = root / "data" / "scripts" / "fig-data.py"
    # 轴上限压到 75：数据最大值 78.8 被裁掉且未声明截断 → 阻断
    text = script.read_text(encoding="utf-8").replace(
        "limits: [0, 100]", "limits: [0, 75]")
    script.write_text(text, encoding="utf-8")
    run_audit(root, fig_id=FIG_DATA)
    honesty = _gates(root, FIG_DATA)["honesty"]
    assert honesty["verdict"] == "FIX_BEFORE_DELIVERY"


def _fake_vsdx(path, media: dict, shape_count: int):
    shapes = "".join(
        f'<Shape ID="{i + 1}" NameU="s{i + 1}" Type="Shape">'
        '<Cell N="PinX" V="1"/><Cell N="PinY" V="1"/>'
        '<Cell N="Width" V="1"/><Cell N="Height" V="1"/></Shape>'
        for i in range(shape_count))
    page = ('<?xml version="1.0" encoding="UTF-8"?>'
            '<PageContents xmlns="http://schemas.microsoft.com/office/'
            'visio/2012/main"><Shapes>' + shapes +
            "</Shapes></PageContents>")
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("visio/pages/page1.xml", page)
        for name, data in media.items():
            zf.writestr(name, data)


def test_native_gate_blocks_whole_image_embedding(pkg):
    root = pkg["root"]
    ref = root / "schematic" / "reference" / "fig-method.png"
    ref.parent.mkdir(parents=True, exist_ok=True)
    from conftest import make_reference_png
    make_reference_png(ref)
    vsdx = root / "schematic" / "redraw" / "fig-method.vsdx"
    vsdx.parent.mkdir(parents=True, exist_ok=True)
    _fake_vsdx(vsdx, {"visio/media/full.png": ref.read_bytes()},
               shape_count=1)
    run_audit(root, fig_id=FIG_METHOD)
    native = _gates(root, FIG_METHOD)["native"]
    assert native["verdict"] == "FIX_BEFORE_DELIVERY"


def test_policy_block_gate_blocks_reference_in_exports(produced_pkg):
    root = produced_pkg["root"]
    ref = root / "schematic" / "reference" / "fig-method.png"
    shutil.copy(ref, root / "exports" / "leaked-reference.png")
    run_audit(root, fig_id=FIG_METHOD)
    policy = _gates(root, FIG_METHOD)["policy_block"]
    assert policy["verdict"] == "FIX_BEFORE_DELIVERY"
    assert any("leaked-reference.png" in f["message"]
               for f in policy["findings"])


def test_redrawn_artifact_passes_policy_block(produced_pkg):
    root = produced_pkg["root"]
    run_audit(root, fig_id=FIG_METHOD)
    gates = _gates(root, FIG_METHOD)
    assert gates["policy_block"]["verdict"] == "PASS"
    assert gates["native"]["verdict"] == "PASS"


def test_native_gate_blocks_declared_full_page_residue(produced_pkg):
    """回归（Phase 3 演示变体抓出）：登记为合法残留、但尺寸≈参考图
    全幅的整幅嵌入必须被 full_page_bitmap 拦下。旧实现用 pymupdf
    打开图像文档的 page rect（按 96 dpi 换算的点数）冒充像素尺寸，
    400×300 的图被量成 300×225 而漏检。"""
    from light_figure.redraw import build_vsdx

    root = produced_pkg["root"]
    manifest_path = root / "schematic" / "redraw" / \
        f"{FIG_METHOD}.manifest.json"
    manifest = load_structured(manifest_path)
    ref_rel = f"schematic/reference/{FIG_METHOD}.png"
    manifest["bitmap_residue"] = [{
        "residue_id": "full-ref", "class": "photo", "panel_id": "a",
        "box_local": [0.0, 0.0, 1.0, 1.0],
        "media_name": "full_reference.png",
        "source": {"path": ref_rel,
                   "sha256": sha256_file(root / ref_rel)},
    }]
    dump_json(manifest_path, manifest)
    build_vsdx(root, FIG_METHOD)
    run_audit(root, fig_id=FIG_METHOD)
    native = _gates(root, FIG_METHOD)["native"]
    assert native["verdict"] == "FIX_BEFORE_DELIVERY"
    assert any(f["code"] == "native.full_page_bitmap"
               for f in native["findings"])
