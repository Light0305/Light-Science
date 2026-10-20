"""共享夹具：期刊合同 / AI 政策快照 / 承接源 / 完整图包的构造器。"""

from __future__ import annotations

from pathlib import Path

import pytest

from light_figure.intake import run_intake
from light_figure.project import (
    init_package, load_package, new_journal_contract, save_backend,
    save_contract, save_head,
)
from light_figure.util import dump_yaml, sha256_text, today

FIG_DATA = "fig-data"
FIG_METHOD = "fig-method"
FAKE_HASH = "a" * 64


# ---------------------------------------------------------------- 构造器

def make_journal_contract():
    """完整合法的已登记期刊合同（Nature 锚 + 示例刊元数据）。"""
    jc = new_journal_contract()
    jc.update({
        "registered": True,
        "journal": "Journal of Examples",
        "version": "2026",
        "checked_at": today(),
        "source_url": "https://example.org/figure-guide",
    })
    jc["font"]["family"] = "Arial"
    jc["palettes"] = {
        "categorical": {"entry_id": "PAL-OI-8", "version": "2002.1"},
        "continuous": {"entry_id": "PAL-BATLOW", "version": "8.0"},
    }
    return jc


def make_ai_policy():
    return {
        "ai_images_prohibited": True,
        "exhibit_exemption": None,
        "disclosure_required": True,
        "source_url": "https://example.org/ai-policy",
        "verified_at": today(),
    }


def make_standalone():
    return {"figures": [
        {"fig_id": FIG_DATA, "kind": "data"},
        {"fig_id": FIG_METHOD, "kind": "schematic"},
    ]}


def make_manifest():
    """Write 侧 figures_manifest 形态（承接口径 data/schematic/table）。"""
    return {"figures": [
        {"figure_id": FIG_DATA, "kind": "data",
         "caption": "Accuracy of the three threshold arms.",
         "intext_refs": ["results:p2"]},
        {"figure_id": FIG_METHOD, "kind": "schematic",
         "caption": "Pipeline overview.",
         "intext_refs": ["methods:p1"]},
    ]}


def data_contract():
    return {
        "fig_id": FIG_DATA,
        "line": "data",
        "core_conclusion": "预测阈值臂达到与 oracle 相当的精度。",
        "results_question": "预测阈值是否消除了逐视频手工调参的需求？",
        "archetype": "quantitative_grid",
        "panel_map": [
            {"panel_id": "a", "role": "primary_quantitative_evidence",
             "content": "三臂精度对比（均值 ± 95% CI）",
             "evidence_tier": "hero"},
            {"panel_id": "b", "role": "baseline_or_control",
             "content": "固定阈值对照臂", "evidence_tier": "controls_robustness"},
        ],
        "evidence_requirements": {
            "statistics": "6 段视频均值 ± 95% CI",
            "source_data": "data/source-data/fig-data.csv",
            "image_integrity_notes": "none",
        },
        "density_stance": {"stance": "simplicity_first",
                           "reason": "单图单主张，主效应优先"},
        "export_contract_ref": {"journal_contract": "journal_contract.yaml",
                                "overrides": []},
        "reviewer_risk": [
            {"risk": "误差棒定义不清",
             "disposition": "图注写明 95% CI 与 n=6"}],
        "data_integrity": {"exclusions": "none"},
        "sister_library_refs": {
            "method_gallery": None,
            "visio_components": [],
            "data_gallery": {"entry_id": "DG-PLOT-001", "version": "1.0"},
        },
    }


def schematic_contract():
    contract = data_contract()
    contract.update({
        "fig_id": FIG_METHOD,
        "line": "schematic",
        "core_conclusion": "流水线以视频级统计量预测逐轨迹阈值。",
        "results_question": "方法结构是否可被读者一段内复述？",
        "archetype": "schematic_led_composite",
        "panel_map": [
            {"panel_id": "a", "role": "setup_schematic",
             "content": "输入视频与跟踪轨迹", "evidence_tier": "hero"},
            {"panel_id": "b", "role": "mechanistic_evidence",
             "content": "统计量 → 阈值预测 → 逐轨迹应用",
             "evidence_tier": "validation"},
        ],
        "evidence_requirements": {
            "statistics": "none",
            "source_data": "none",
            "image_integrity_notes": "示意图无实验图像，代表性不适用",
        },
        "density_stance": {"stance": "density_first",
                           "reason": "方法图须自包含复述全部模块与数据流"},
        "sister_library_refs": {
            "method_gallery": {
                "entry_id": "MG-FLOW-014", "version": "2.1",
                "style_anchor": "anchor-compact-flow",
                "prompt_version": "3",
            },
            "visio_components": [
                {"component_id": "VC-ARROW-FLOW", "version": "1.0"}],
            "data_gallery": None,
        },
        "policy_check": {
            "policy_snapshot_ref": "figure.yaml#ai_policy_snapshot",
            "reference_not_in_delivery": True,
            "degradation_path": "normal",
        },
        "role_palette_ref": {"entry_id": "PAL-ROLE-METHOD", "version": "1.2"},
        "palette_confirmation": {"confirmed_by": "author",
                                 "confirmed_at": today()},
    })
    return contract


# ---------------------------------------------------------------- 夹具

def _write(path: Path, obj):
    dump_yaml(path, obj)
    return path


@pytest.fixture()
def pkg(tmp_path):
    """已 init + intake（standalone 两图 + 期刊登记 + 政策快照）的图包。"""
    root = tmp_path / "figs"
    init_package(root, "Demo Paper Figures")
    standalone = _write(tmp_path / "standalone.yaml", make_standalone())
    journal = _write(tmp_path / "journal.yaml", make_journal_contract())
    policy = _write(tmp_path / "policy.yaml", make_ai_policy())
    result = run_intake(root, standalone=str(standalone),
                        journal_contract_file=str(journal),
                        template_record_id="TPL-DEMO-001",
                        ai_policy_file=str(policy))
    return {"root": root, "intake": result, "tmp": tmp_path,
            "standalone": standalone, "journal": journal, "policy": policy}


@pytest.fixture()
def filled_pkg(pkg):
    """合同五点齐 + 后端已决定的包（contracted 门前一步）。"""
    root = pkg["root"]
    save_contract(root, data_contract())
    save_contract(root, schematic_contract())
    save_backend(root, {
        "backend": "python", "decided_via": "explicit",
        "decided_at": today(), "scope": "package", "overrides": [],
    })
    return pkg


def set_figure_stage(root, fig_id, stage):
    data = load_package(root)
    head = data["head"]
    for row in head["figures"]:
        if row["fig_id"] == fig_id:
            row["stage"] = stage
    save_head(root, head)


def fill_provenance_schematic(root):
    from light_figure.project import save_provenance

    data = load_package(root)
    prov = data["provenance"]
    for entry in prov["entries"]:
        if entry["fig_id"] == FIG_METHOD:
            entry["prompt_version"] = "3"
            entry["generation_model"] = {"name": "GPT Image", "version": "1"}
            entry["reference_image_hash"] = FAKE_HASH
            entry["redraw_source"] = {
                "path": "schematic/redraw/fig-method.vsdx", "hash": FAKE_HASH}
            entry["label_check"] = {"done": True, "by": "author",
                                    "at": today()}
    save_provenance(root, prov)


def fill_provenance_data(root):
    from light_figure.project import save_provenance

    data = load_package(root)
    prov = data["provenance"]
    for entry in prov["entries"]:
        if entry["fig_id"] == FIG_DATA:
            entry["backend"] = "python"
            entry["runtime_version"] = "3.12"
            entry["script_hash"] = FAKE_HASH
            entry["source_data_hash"] = FAKE_HASH
    save_provenance(root, prov)


# ---------------------------------------------------------------- Phase 2

DATA_SCRIPT = '''# --- light-figure-script ---
# fig_id: fig-data
# style_build_hash: {bundle_hash}
# column: double
# panels: {{rows: 1, cols: 2}}
# axes:
#   y: {{direction: increasing, limits: [0, 100], data_min: 71.5,
#       data_max: 78.8, truncated: false, truncation_declared: false}}
#   x: {{direction: increasing, limits: [0, 2], data_min: 0, data_max: 2,
#       truncated: false, truncation_declared: false}}
# aspect: {{ratio: 0.75, declared: true}}
# area_encoding: none
# palette: {{categorical: PAL-OI-8, continuous: PAL-BATLOW}}
# --- end light-figure-script ---
"""三臂精度对比（数据图演示脚本）。"""
import csv
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "source-data" / "fig-data.csv"


def draw(fig, axes):
    rows = list(csv.DictReader(DATA.open(encoding="utf-8")))
    arms = [r["arm"] for r in rows]
    means = [float(r["mean"]) for r in rows]
    sds = [float(r["sd"]) for r in rows]
    ax = axes[0]
    ax.bar(arms, means, yerr=sds, capsize=3)
    ax.set_ylim(0, 100)
    ax.set_ylabel("Accuracy")
    ax.set_title("a")
    ax2 = axes[1]
    ax2.plot(arms, means, marker="o")
    ax2.set_ylim(0, 100)
    ax2.set_title("b")
'''


def write_source_data(root):
    path = Path(root) / "data" / "source-data" / "fig-data.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("arm,mean,sd\nfixed,72.6,1.1\noracle,77.9,0.9\n"
                    "predicted,77.8,1.0\n", encoding="utf-8")
    return path


def write_data_script(root, bundle_hash, script=DATA_SCRIPT):
    path = Path(root) / "data" / "scripts" / "fig-data.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(script.format(bundle_hash=bundle_hash),
                    encoding="utf-8")
    return path


def make_reference_png(path, size=(400, 300)):
    from PIL import Image, ImageDraw

    img = Image.new("RGB", size, "#dfe9f2")
    draw = ImageDraw.Draw(img)
    draw.rectangle([40, 40, 180, 180], outline="#0072b2", width=4)
    draw.rectangle([220, 60, 360, 160], outline="#d55e00", width=4)
    draw.line([180, 110, 220, 110], fill="#000000", width=3)
    img.save(path)
    return path


def method_manifest():
    return {
        "fig_id": FIG_METHOD,
        "version": "1.0",
        "status": "draft",
        "route": "file_build",
        "reference": {"path": f"schematic/reference/{FIG_METHOD}.png",
                      "sha256": None},  # 登记时回填
        "canvas": {"reference_size_px": [400, 300],
                   "page_size_in": [10.0, 7.5]},
        "role_palette": {"entry_id": "PAL-ROLE-METHOD", "version": "1.2"},
        "panels": [
            {"panel_id": "a", "pixel_box": [0, 0, 200, 300],
             "contract_panel_id": "a"},
            {"panel_id": "b", "pixel_box": [200, 0, 200, 300],
             "contract_panel_id": "b"},
        ],
        "shapes": [
            {"shape_id": "input-frame", "type": "rect", "panel_id": "a",
             "box_local": [0.1, 0.1, 0.8, 0.6],
             "style": {"fill_role": "input_data", "line_role": "neutral"}},
            {"shape_id": "input-label", "type": "text", "panel_id": "a",
             "box_local": [0.1, 0.75, 0.8, 0.15], "text": "Input video",
             "style": {"font_pt": 9}},
            {"shape_id": "predictor", "type": "rounded_rect",
             "panel_id": "b", "box_local": [0.1, 0.2, 0.8, 0.4],
             "style": {"fill_role": "model_core", "line_role": "neutral"},
             "text": "Threshold predictor",
             "connect": {"from": "input-frame", "to": "predictor",
                         "arrow": True, "semantics": "data flow"}},
        ],
        "bitmap_residue": [],
        "trace_layer": {"used": True, "opacity": 0.25,
                        "removed_before_delivery": True},
        "label_check": {"done": False, "by": None, "at": None},
    }


@pytest.fixture()
def produced_pkg(filled_pkg):
    """contracted → 双线产物齐备（produced 门前一步）的完整图包。"""
    from light_figure.audit import run_audit  # noqa: F401  (确保可导入)
    from light_figure.gates import advance
    from light_figure.prompt import build_prompt
    from light_figure.produce import produce_data_figure
    from light_figure.provenance import update_provenance_row
    from light_figure.redraw import (
        build_vsdx, extract_and_reconcile, install_manifest,
    )
    from light_figure.reference import accept_reference, register_reference
    from light_figure.style import build_style
    from light_figure.util import dump_json, sha256_file

    root = filled_pkg["root"]
    result = advance(root)
    assert result["advanced"], result["gaps"]

    bundle = build_style(root)
    write_source_data(root)
    write_data_script(root, bundle["style_build_hash"])
    produce_data_figure(root, FIG_DATA)

    build_prompt(root, FIG_METHOD)
    ref_src = make_reference_png(filled_pkg["tmp"] / "reference.png")
    register_reference(root, FIG_METHOD, ref_src,
                       model_name="GPT Image", model_version="1")
    accept_reference(root, FIG_METHOD, by="author", checks={
        "labels_verbatim": True, "structures_factual": True,
        "formulas_values_checked": True})
    manifest = method_manifest()
    manifest["reference"]["sha256"] = sha256_file(
        root / "schematic" / "reference" / f"{FIG_METHOD}.png")
    manifest_file = filled_pkg["tmp"] / "manifest.json"
    dump_json(manifest_file, manifest)
    install_manifest(root, FIG_METHOD, manifest_file)
    build_vsdx(root, FIG_METHOD)
    outcome = extract_and_reconcile(root, FIG_METHOD)
    assert outcome["ok"], outcome["diffs"]
    update_provenance_row(root, FIG_METHOD, {
        "label_check": {"done": True, "by": "author", "at": today()},
    }, by="test")
    filled_pkg["bundle"] = bundle
    return filled_pkg
