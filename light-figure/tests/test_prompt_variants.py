"""提示词多版变体（2026-10-21 补丁）：多版生成与纪律、合同/账面登记、
变体选定门、参考图所据变体门、produced 门落点、全链走通。"""

import re

import pytest

from light_figure.project import load_package, provenance_row, save_contract
from light_figure.prompt import (
    PromptError, build_prompt, parse_front_matter, select_variant,
)
from light_figure.reference import (
    ReferenceError, accept_reference, register_reference,
)
from light_figure.validate import validate_package
from conftest import FIG_METHOD, make_reference_png

ALL_VARIANTS = ["compact", "spacious", "layered"]
SIX_HEADINGS = ("## 1 全局", "## 2 分区", "## 3 全局标注",
                "## 4 风格规格", "## 5 负面约束", "## 6 政策段")
CHECKS = {"labels_verbatim": True, "structures_factual": True,
          "formulas_values_checked": True}


def _codes(root):
    return [e["code"] for e in validate_package(root)["errors"]]


def _variant_text(root, variant_id):
    path = root / "schematic" / "prompts" / f"fig-method.{variant_id}.md"
    return path.read_text(encoding="utf-8")


# ------------------------------------------------------------ 多版生成

def test_multi_variant_build_creates_disciplined_files(filled_pkg):
    root = filled_pkg["root"]
    outcome = build_prompt(root, FIG_METHOD, variants=ALL_VARIANTS)
    assert [b["variant_id"] for b in outcome["variants"]] == ALL_VARIANTS
    assert outcome["selected_variant"] is None
    bodies = set()
    for vid in ALL_VARIANTS:
        text = _variant_text(root, vid)
        meta, body = parse_front_matter(text)
        bodies.add(body)
        # front matter：变体登记 + 三元组/色板与单版同源
        assert meta["variant"]["id"] == vid
        assert meta["gallery"]["entry_id"] == "MG-FLOW-014"
        assert meta["gallery"]["bound_prompt_version"] == "3"
        assert meta["gallery"]["style_anchor"] == "anchor-compact-flow"
        assert meta["role_palette"]["entry_id"] == "PAL-ROLE-METHOD"
        assert meta["version"] == 3  # 首版取图库条目绑定的提示词版本
        # 六段齐 + 既有纪律（正文无 hex、只引角色名）
        for heading in SIX_HEADINGS:
            assert heading in body
        assert not re.search(r"#[0-9a-fA-F]{6}\b", body)
        assert "model_core" in body
        # 变体三维口径入正文：构图 / 布局流向 / 变体执行口径 / 变体红线
        assert meta["variant"]["composition"] in body
        assert meta["variant"]["layout_flow"] in body
        assert "变体执行口径（本版为准）" in body
        assert "变体红线" in body
    # 三版正文互不相同（变体真的区分了）
    assert len(bodies) == 3
    # 合同与账面登记变体集合
    data = load_package(root)
    pv = data["contracts"][FIG_METHOD]["prompt_variants"]
    assert [e["variant_id"] for e in pv["variants"]] == ALL_VARIANTS
    assert pv["variants"][0]["file"] == \
        "schematic/prompts/fig-method.compact.md"
    assert pv["selected_variant"] is None
    row = provenance_row(data["provenance"], FIG_METHOD)
    assert row["prompt_variants"] == ALL_VARIANTS
    assert row["selected_variant"] is None
    # 登记形态过 validate
    assert validate_package(root)["ok"]


def test_variant_unknown_rejected_and_nothing_registered(filled_pkg):
    root = filled_pkg["root"]
    with pytest.raises(PromptError) as exc:
        build_prompt(root, FIG_METHOD, variants=["compact", "weird"])
    assert any("未知提示词变体" in g for g in exc.value.gaps)
    assert not (root / "schematic" / "prompts"
                / "fig-method.compact.md").exists()
    contract = load_package(root)["contracts"][FIG_METHOD]
    assert "prompt_variants" not in contract


def test_variant_revision_archives_per_variant(filled_pkg):
    root = filled_pkg["root"]
    build_prompt(root, FIG_METHOD, variants=["compact"])
    outcome = build_prompt(root, FIG_METHOD, variants=["compact"])
    entry = outcome["variants"][0]
    assert entry["version"] == 4
    assert entry["archived"] == \
        "schematic/prompts/archive/fig-method.compact.v3.md"
    assert (root / "schematic" / "prompts" / "archive"
            / "fig-method.compact.v3.md").exists()


def test_variant_build_still_blocks_metric_literals(filled_pkg):
    from light_figure.project import load_package as lp, save_contract as sc

    data = lp(filled_pkg["root"])
    contract = data["contracts"][FIG_METHOD]
    contract["panel_map"][0]["labels"] = ["箭头宽 12 pt"]
    sc(filled_pkg["root"], contract)
    with pytest.raises(PromptError) as exc:
        build_prompt(filled_pkg["root"], FIG_METHOD, variants=["compact"])
    assert any("度量字面量" in g for g in exc.value.gaps)


def test_variant_build_still_blocks_unconfirmed_palette(pkg):
    # 只 intake 未补合同（无 palette_confirmation）：变体构建同样被门拦
    with pytest.raises(PromptError):
        build_prompt(pkg["root"], FIG_METHOD, variants=["compact"])


# ------------------------------------------------------------ 选定

def test_select_variant_registers_contract_and_provenance(filled_pkg):
    root = filled_pkg["root"]
    build_prompt(root, FIG_METHOD, variants=ALL_VARIANTS)
    outcome = select_variant(root, FIG_METHOD, "spacious")
    assert outcome["selected_variant"] == "spacious"
    data = load_package(root)
    pv = data["contracts"][FIG_METHOD]["prompt_variants"]
    assert pv["selected_variant"] == "spacious"
    row = provenance_row(data["provenance"], FIG_METHOD)
    assert row["selected_variant"] == "spacious"
    assert row["prompt_version"] == "3"  # 取所选变体的 version


def test_select_unbuilt_variant_rejected(filled_pkg):
    root = filled_pkg["root"]
    build_prompt(root, FIG_METHOD, variants=["compact"])
    with pytest.raises(PromptError) as exc:
        select_variant(root, FIG_METHOD, "layered")
    assert any("未构建登记" in g for g in exc.value.gaps)


def test_rebuild_without_selected_variant_clears_selection(filled_pkg):
    root = filled_pkg["root"]
    build_prompt(root, FIG_METHOD, variants=ALL_VARIANTS)
    select_variant(root, FIG_METHOD, "compact")
    build_prompt(root, FIG_METHOD, variants=["spacious"])
    data = load_package(root)
    pv = data["contracts"][FIG_METHOD]["prompt_variants"]
    assert pv["selected_variant"] is None
    row = provenance_row(data["provenance"], FIG_METHOD)
    assert row["selected_variant"] is None


def test_rebuild_keeping_selected_variant_preserves_selection(filled_pkg):
    root = filled_pkg["root"]
    build_prompt(root, FIG_METHOD, variants=ALL_VARIANTS)
    select_variant(root, FIG_METHOD, "compact")
    build_prompt(root, FIG_METHOD, variants=ALL_VARIANTS)
    data = load_package(root)
    pv = data["contracts"][FIG_METHOD]["prompt_variants"]
    assert pv["selected_variant"] == "compact"
    # 账面 prompt_version 同步到所选变体改版后的新 version（3 → 4）
    row = provenance_row(data["provenance"], FIG_METHOD)
    assert row["prompt_version"] == "4"


# ------------------------------------------------- 参考图所据变体门

def test_reference_add_blocked_until_variant_selected(filled_pkg, tmp_path):
    root = filled_pkg["root"]
    build_prompt(root, FIG_METHOD, variants=ALL_VARIANTS)
    src = make_reference_png(tmp_path / "ref.png")
    with pytest.raises(ReferenceError) as exc:
        register_reference(root, FIG_METHOD, src, variant="compact")
    assert any("未选定" in g for g in exc.value.gaps)


def test_reference_add_requires_named_variant_matching_selection(
        filled_pkg, tmp_path):
    root = filled_pkg["root"]
    build_prompt(root, FIG_METHOD, variants=ALL_VARIANTS)
    select_variant(root, FIG_METHOD, "compact")
    src = make_reference_png(tmp_path / "ref.png")
    # 未指明所据变体 → 拦
    with pytest.raises(ReferenceError) as exc:
        register_reference(root, FIG_METHOD, src,
                           model_name="GPT Image", model_version="1")
    assert any("指明所据变体" in g for g in exc.value.gaps)
    # 所据变体与选定不一致 → 拦
    with pytest.raises(ReferenceError) as exc:
        register_reference(root, FIG_METHOD, src,
                           model_name="GPT Image", model_version="1",
                           variant="spacious")
    assert any("不一致" in g for g in exc.value.gaps)
    # 所据 = 选定 → 通过且记账
    outcome = register_reference(root, FIG_METHOD, src,
                                 model_name="GPT Image", model_version="1",
                                 variant="compact")
    assert outcome["reference_variant"] == "compact"
    row = provenance_row(load_package(root)["provenance"], FIG_METHOD)
    assert row["reference_variant"] == "compact"


def test_accept_records_variant_and_rechecks_selection(filled_pkg, tmp_path):
    root = filled_pkg["root"]
    build_prompt(root, FIG_METHOD, variants=ALL_VARIANTS)
    select_variant(root, FIG_METHOD, "layered")
    src = make_reference_png(tmp_path / "ref.png")
    register_reference(root, FIG_METHOD, src,
                       model_name="GPT Image", model_version="1",
                       variant="layered")
    outcome = accept_reference(root, FIG_METHOD, by="author",
                               checks=dict(CHECKS))
    assert outcome["variant"] == "layered"
    row = provenance_row(load_package(root)["provenance"], FIG_METHOD)
    assert row["reference_acceptance"]["variant"] == "layered"
    assert row["reference_acceptance"]["done"] is True


def test_accept_blocked_if_selection_changed_after_registration(
        filled_pkg, tmp_path):
    root = filled_pkg["root"]
    build_prompt(root, FIG_METHOD, variants=ALL_VARIANTS)
    select_variant(root, FIG_METHOD, "compact")
    src = make_reference_png(tmp_path / "ref.png")
    register_reference(root, FIG_METHOD, src, variant="compact")
    select_variant(root, FIG_METHOD, "spacious")  # 登记后改选
    with pytest.raises(ReferenceError) as exc:
        accept_reference(root, FIG_METHOD, by="author",
                         checks=dict(CHECKS))
    assert any("不一致" in g for g in exc.value.gaps)


def test_legacy_reference_flow_untouched_by_variant_gate(pkg, tmp_path):
    # 无变体集的单版图：登记/验收不要求 variant（存量兼容）
    src = make_reference_png(tmp_path / "ref.png")
    register_reference(pkg["root"], FIG_METHOD, src)
    outcome = accept_reference(pkg["root"], FIG_METHOD, by="author",
                               checks=dict(CHECKS))
    assert outcome["variant"] is None
    row = provenance_row(load_package(pkg["root"])["provenance"],
                         FIG_METHOD)
    assert "variant" not in row["reference_acceptance"]


# ------------------------------------------------- validate 形态校验

def test_validate_variant_vocab_and_selection(filled_pkg):
    root = filled_pkg["root"]
    build_prompt(root, FIG_METHOD, variants=ALL_VARIANTS)
    contract = load_package(root)["contracts"][FIG_METHOD]
    contract["prompt_variants"]["variants"][0]["variant_id"] = "weird"
    save_contract(root, contract)
    assert "prompt.variant_vocab" in _codes(root)


def test_validate_variant_duplicate_and_file_mismatch(filled_pkg):
    root = filled_pkg["root"]
    build_prompt(root, FIG_METHOD, variants=ALL_VARIANTS)
    contract = load_package(root)["contracts"][FIG_METHOD]
    contract["prompt_variants"]["variants"][1]["variant_id"] = "compact"
    contract["prompt_variants"]["variants"][1]["file"] = \
        "schematic/prompts/fig-method.spacious.md"
    save_contract(root, contract)
    found = _codes(root)
    assert "prompt.variant_duplicate" in found
    assert "prompt.variant_file_mismatch" in found


def test_validate_selected_variant_must_be_in_set(filled_pkg):
    root = filled_pkg["root"]
    build_prompt(root, FIG_METHOD, variants=["compact"])
    contract = load_package(root)["contracts"][FIG_METHOD]
    contract["prompt_variants"]["selected_variant"] = "layered"
    save_contract(root, contract)
    assert "prompt.selected_variant_unknown" in _codes(root)


def test_validate_variants_on_data_line_rejected(filled_pkg):
    from conftest import FIG_DATA

    contract = load_package(filled_pkg["root"])["contracts"][FIG_DATA]
    contract["prompt_variants"] = {
        "variants": [{"variant_id": "compact",
                      "file": "schematic/prompts/fig-data.compact.md",
                      "version": 1}],
        "selected_variant": None}
    save_contract(filled_pkg["root"], contract)
    assert "prompt.variants_on_data" in _codes(filled_pkg["root"])


# ------------------------------------------------- produced 门与全链

def test_variant_chain_reaches_produced(filled_pkg):
    from light_figure.gates import _produced_gaps, advance
    from light_figure.produce import produce_data_figure
    from light_figure.provenance import update_provenance_row
    from light_figure.redraw import (
        build_vsdx, extract_and_reconcile, install_manifest,
    )
    from light_figure.style import build_style
    from light_figure.util import dump_json, sha256_file, today
    from conftest import (
        FIG_DATA, method_manifest, write_data_script, write_source_data,
    )

    root = filled_pkg["root"]
    result = advance(root)
    assert result["advanced"], result["gaps"]

    bundle = build_style(root)
    write_source_data(root)
    write_data_script(root, bundle["style_build_hash"])
    produce_data_figure(root, FIG_DATA)

    build_prompt(root, FIG_METHOD, variants=ALL_VARIANTS)
    # 未选定：produced 门点名变体未选定（而不是含糊的缺提示词）
    pkg_now = load_package(root)
    gaps = _produced_gaps(pkg_now)
    assert any("提示词变体未选定" in g for g in gaps), gaps

    select_variant(root, FIG_METHOD, "layered")
    ref_src = make_reference_png(filled_pkg["tmp"] / "reference.png")
    register_reference(root, FIG_METHOD, ref_src,
                       model_name="GPT Image", model_version="1",
                       variant="layered")
    accept_reference(root, FIG_METHOD, by="author", checks=dict(CHECKS))
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
    result = advance(root)
    assert result["advanced"], result["gaps"]
    assert result["to"] == "produced"


# ------------------------------------------------- CLI 冒烟

def test_cli_variants_select_and_reference(tmp_path, capsys):
    import json

    from light_figure.cli import main
    from conftest import data_contract, schematic_contract
    from light_figure.project import init_package, save_backend, \
        save_contract
    from light_figure.intake import run_intake
    from light_figure.util import dump_yaml, today
    from conftest import (make_ai_policy, make_journal_contract,
                          make_standalone)

    root = tmp_path / "figs"
    init_package(root, "CLI Variants")
    standalone = tmp_path / "s.yaml"
    dump_yaml(standalone, make_standalone())
    journal = tmp_path / "j.yaml"
    dump_yaml(journal, make_journal_contract())
    policy = tmp_path / "p.yaml"
    dump_yaml(policy, make_ai_policy())
    run_intake(root, standalone=str(standalone),
               journal_contract_file=str(journal),
               ai_policy_file=str(policy))
    save_contract(root, data_contract())
    save_contract(root, schematic_contract())
    save_backend(root, {"backend": "python", "decided_via": "explicit",
                        "decided_at": today(), "scope": "package",
                        "overrides": []})

    def run(argv):
        rc = main(argv)
        return rc, json.loads(capsys.readouterr().out)

    rc, out = run(["prompt", "build", str(root), FIG_METHOD,
                   "--variants", "compact,layered"])
    assert rc == 0 and len(out["variants"]) == 2
    rc, out = run(["prompt", "select", str(root), FIG_METHOD, "layered"])
    assert rc == 0 and out["selected_variant"] == "layered"
    src = make_reference_png(tmp_path / "ref.png")
    rc, out = run(["reference", "add", str(root), FIG_METHOD,
                   "--image", str(src), "--model-name", "GPT Image"])
    assert rc == 1 and any("指明所据变体" in g for g in out["gaps"])
    rc, out = run(["reference", "add", str(root), FIG_METHOD,
                   "--image", str(src), "--model-name", "GPT Image",
                   "--variant", "layered"])
    assert rc == 0 and out["reference_variant"] == "layered"
    rc, out = run(["reference", "accept", str(root), FIG_METHOD,
                   "--by", "author", "--labels-verbatim",
                   "--structures-factual", "--formulas-values-checked"])
    assert rc == 0 and out["variant"] == "layered"
