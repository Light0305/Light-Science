"""v1.1 交付增件（REV-D09 对应件清单）：delivery.yaml 逐图
correspondence 的源资产映射与内容级哈希可按实物复算。"""

from light_figure.audit import run_audit, set_review_disposition
from light_figure.delivery import generate_delivery
from light_figure.gates import advance
from light_figure.util import component_hash, load_structured, sha256_file
from conftest import FIG_DATA, FIG_METHOD


def _to_audited(root):
    result = advance(root)
    assert result["advanced"], result["gaps"]
    run_audit(root)
    for fig_id in (FIG_DATA, FIG_METHOD):
        record = load_structured(root / "audit" / f"{fig_id}.audit.json")
        for name, gate in record["gates"].items():
            if gate.get("applicable") and gate["verdict"] == \
                    "REVIEW_REQUIRED":
                set_review_disposition(root, fig_id, name,
                                       "已人工复核：容差内可接受")
    result = advance(root)
    assert result["advanced"], result["gaps"]


def test_correspondence_listed_and_recomputable(produced_pkg):
    root = produced_pkg["root"]
    _to_audited(root)
    generate_delivery(root)
    doc = load_structured(root / "exports" / "delivery.yaml")
    rows = {r["fig_id"]: r for r in doc["figures"]}

    data_corr = rows[FIG_DATA]["correspondence"]
    roles = {s["role"] for s in data_corr["source_assets"]}
    assert roles == {"plotting_script", "source_data", "style_bundle"}
    for asset in data_corr["source_assets"]:
        assert asset["sha256"] == sha256_file(root / asset["path"])
    align = load_structured(root / "audit" / "fig-data.alignment-input.json")
    assert data_corr["content_hashes"]["alignment_panels"] == \
        component_hash(align["panels"])

    method_corr = rows[FIG_METHOD]["correspondence"]
    roles = {s["role"] for s in method_corr["source_assets"]}
    assert roles == {"redraw_manifest", "reference_image"}
    manifest = load_structured(
        root / "schematic" / "redraw" / "fig-method.manifest.json")
    assert method_corr["content_hashes"]["extracted_shapes"] == \
        manifest["extracted_shapes_hash"]
    ref_asset = next(s for s in method_corr["source_assets"]
                     if s["role"] == "reference_image")
    assert ref_asset["path"] is None  # 参考图本体不进交付集，只给哈希
