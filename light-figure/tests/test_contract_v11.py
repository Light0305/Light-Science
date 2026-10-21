"""v1.1 合同新字段（FIG-D08 配色决定 / FIG-D09 六维拆解 /
FIG-D02 后端词表 / FIG-D03 Illustrator 精修段）与提示词消费。"""

import pytest

from light_figure.gates import advance
from light_figure.project import load_package, provenance_row, save_contract
from light_figure.validate import validate_package
from conftest import FIG_DATA, FIG_METHOD, data_contract, schematic_contract


def _codes(root):
    return [e["code"] for e in validate_package(root)["errors"]]


def test_palette_decision_missing_blocks_contracted(filled_pkg):
    root = filled_pkg["root"]
    contract = data_contract()
    del contract["palette_decision"]
    save_contract(root, contract)
    result = advance(root)
    assert result["advanced"] is False
    assert any("配色决定" in g for g in result["gaps"])


def test_palette_decision_bad_source_is_error(filled_pkg):
    contract = data_contract()
    contract["palette_decision"]["source"] = "vibes"
    save_contract(filled_pkg["root"], contract)
    assert "contract.palette_decision_source" in _codes(filled_pkg["root"])


def test_palette_decision_without_basis_is_error(filled_pkg):
    contract = schematic_contract()
    contract["palette_decision"]["basis"] = None
    save_contract(filled_pkg["root"], contract)
    assert "contract.palette_decision_no_basis" in _codes(
        filled_pkg["root"])


def test_breakdown_missing_dimension_is_error(filled_pkg):
    contract = schematic_contract()
    del contract["sister_library_refs"]["method_gallery"][
        "reference_breakdown"]["layout_flow"]
    save_contract(filled_pkg["root"], contract)
    report = validate_package(filled_pkg["root"])
    hits = [e for e in report["errors"]
            if e["code"] == "library.breakdown_incomplete"]
    assert hits and "layout_flow" in hits[0]["message"]


def test_breakdown_palette_hex_must_be_hex(filled_pkg):
    contract = schematic_contract()
    contract["sister_library_refs"]["method_gallery"][
        "reference_breakdown"]["palette_hex"] = ["blue-ish"]
    save_contract(filled_pkg["root"], contract)
    assert "library.breakdown_palette_hex" in _codes(filled_pkg["root"])


def test_prompt_consumes_breakdown_without_hex(produced_pkg):
    root = produced_pkg["root"]
    text = (root / "schematic" / "prompts" / f"{FIG_METHOD}.md").read_text(
        encoding="utf-8")
    assert "布局流向" in text and "左入右出两段流" in text
    import re
    body = text.split("---", 2)[-1]
    assert not re.search(r"#[0-9a-fA-F]{6}\b", body)


def test_produce_records_palette_decision(produced_pkg):
    root = produced_pkg["root"]
    pkg = load_package(root)
    entry = provenance_row(pkg["provenance"], FIG_DATA)
    record = entry.get("palette_decision_record") or {}
    assert record.get("source") == "journal_contract"
    assert record.get("categorical") == "PAL-OI-8@2002.1"
    assert record.get("style_build_hash")


def test_schematic_backend_vocab(filled_pkg):
    # 三路平权后 illustrator 已是合法后端（用户 2026-10-21 推翻
    # FIG-D03）：词表外样本改用 photoshop，断言不变。
    contract = schematic_contract()
    contract["schematic_backend"] = "photoshop"
    save_contract(filled_pkg["root"], contract)
    assert "contract.schematic_backend_vocab" in _codes(
        filled_pkg["root"])


def test_data_figure_cannot_claim_schematic_backend(filled_pkg):
    contract = data_contract()
    contract["schematic_backend"] = "powerpoint"
    save_contract(filled_pkg["root"], contract)
    assert "contract.schematic_backend_on_data" in _codes(
        filled_pkg["root"])


def test_illustrator_refinement_planned_needs_entry(filled_pkg):
    contract = schematic_contract()
    contract["illustrator_refinement"] = {"planned": True,
                                          "status": "planned"}
    save_contract(filled_pkg["root"], contract)
    assert "contract.illustrator_no_entry" in _codes(filled_pkg["root"])


def test_illustrator_refinement_done_needs_clean_preflight(filled_pkg):
    contract = schematic_contract()
    contract["illustrator_refinement"] = {
        "planned": True, "entry_svg_ref": "schematic/refine/fig.svg",
        "status": "done",
        "readback": {
            "object_count": 12, "texts_verbatim_checked": True,
            "anchor_bbox_checked": True,
            "preflight": {"rgb_mixed": True, "broken_links": False,
                          "low_res_images": False,
                          "white_overprint": False, "pdfx": False},
        },
    }
    save_contract(filled_pkg["root"], contract)
    assert "contract.illustrator_preflight_open" in _codes(
        filled_pkg["root"])


def test_illustrator_refinement_complete_ok(filled_pkg):
    contract = schematic_contract()
    contract["illustrator_refinement"] = {
        "planned": True, "entry_svg_ref": "schematic/refine/fig.svg",
        "status": "done",
        "readback": {
            "object_count": 12, "texts_verbatim_checked": True,
            "anchor_bbox_checked": True,
            "preflight": {"rgb_mixed": False, "broken_links": False,
                          "low_res_images": False,
                          "white_overprint": False, "pdfx": False},
        },
    }
    save_contract(filled_pkg["root"], contract)
    codes = _codes(filled_pkg["root"])
    assert not any(c.startswith("contract.illustrator") for c in codes)
