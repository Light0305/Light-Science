"""校验器：合同五点 / 后端排他 / 期刊数值与容差 / provenance / 快照。"""

from light_figure.project import (
    load_package, save_backend, save_contract, save_head,
    save_journal_contract, save_provenance,
)
from light_figure.util import today
from light_figure.validate import validate_package
from conftest import (
    FAKE_HASH, FIG_DATA, FIG_METHOD, data_contract,
    fill_provenance_data, fill_provenance_schematic, make_journal_contract,
    schematic_contract, set_figure_stage,
)


def codes(root):
    return [e["code"] for e in validate_package(root)["errors"]]


def mutate_journal(pkg, fn):
    jc = load_package(pkg["root"])["journal_contract"]
    fn(jc)
    save_journal_contract(pkg["root"], jc)


def mutate_backend(pkg, reg):
    save_backend(pkg["root"], reg)


def base_backend(**kw):
    reg = {"backend": "python", "decided_via": "explicit",
           "decided_at": today(), "scope": "package", "overrides": []}
    reg.update(kw)
    return reg


# ------------------------------------------------------------ 基线

def test_filled_package_validates_clean(filled_pkg):
    report = validate_package(filled_pkg["root"])
    assert report["ok"], report["errors"]


def test_fresh_intake_names_every_five_point_gap(pkg):
    found = codes(pkg["root"])
    assert found.count("contract.five_point_missing") >= 6  # 两图合计
    assert "contract.panel_role_vocab" not in found  # 空 panel_map 只报缺项


# ------------------------------------------------------------ 图合同

def test_archetype_vocab_enforced(filled_pkg):
    contract = data_contract()
    contract["archetype"] = "pie_chart"
    save_contract(filled_pkg["root"], contract)
    assert "contract.archetype_vocab" in codes(filled_pkg["root"])


def test_panel_role_and_tier_vocab_enforced(filled_pkg):
    contract = data_contract()
    contract["panel_map"][0]["role"] = "pretty_picture"
    contract["panel_map"][1]["evidence_tier"] = "main"
    save_contract(filled_pkg["root"], contract)
    found = codes(filled_pkg["root"])
    assert "contract.panel_role_vocab" in found
    assert "contract.panel_tier_vocab" in found


def test_evidence_none_string_is_explicit_and_legal(filled_pkg):
    contract = data_contract()
    contract["evidence_requirements"] = {
        "statistics": "none", "source_data": "none",
        "image_integrity_notes": "none"}
    save_contract(filled_pkg["root"], contract)
    assert validate_package(filled_pkg["root"])["ok"]


def test_evidence_null_is_a_gap(filled_pkg):
    contract = data_contract()
    contract["evidence_requirements"]["statistics"] = None
    save_contract(filled_pkg["root"], contract)
    assert "contract.evidence_missing" in codes(filled_pkg["root"])


def test_density_stance_needs_reason(filled_pkg):
    contract = data_contract()
    contract["density_stance"] = {"stance": "density_first", "reason": None}
    save_contract(filled_pkg["root"], contract)
    assert "contract.density_no_reason" in codes(filled_pkg["root"])


def test_exclusion_entries_need_counts_rule_reason(filled_pkg):
    contract = data_contract()
    contract["data_integrity"] = {"exclusions": [
        {"before_count": 10, "after_count": 9, "reason": "损坏帧"}]}
    save_contract(filled_pkg["root"], contract)
    assert "contract.exclusion_malformed" in codes(filled_pkg["root"])


def test_export_override_needs_reason(filled_pkg):
    contract = data_contract()
    contract["export_contract_ref"]["overrides"] = [
        {"key": "aspect_ratio", "value": 1.4}]
    save_contract(filled_pkg["root"], contract)
    assert "contract.override_no_reason" in codes(filled_pkg["root"])


def test_policy_block_self_check_false_is_error(filled_pkg):
    contract = schematic_contract()
    contract["policy_check"]["reference_not_in_delivery"] = False
    save_contract(filled_pkg["root"], contract)
    assert "contract.policy_block_failed" in codes(filled_pkg["root"])


def test_gallery_triplet_must_be_complete(filled_pkg):
    contract = schematic_contract()
    del contract["sister_library_refs"]["method_gallery"]["style_anchor"]
    save_contract(filled_pkg["root"], contract)
    assert "library.triplet_incomplete" in codes(filled_pkg["root"])


def test_library_ref_needs_id_and_version(filled_pkg):
    contract = data_contract()
    contract["sister_library_refs"]["data_gallery"] = {"entry_id": "DG-1"}
    save_contract(filled_pkg["root"], contract)
    assert "library.ref_incomplete" in codes(filled_pkg["root"])


# ------------------------------------------------------------ 后端排他

def test_same_figure_two_backends_conflict(filled_pkg):
    mutate_backend(filled_pkg, base_backend(overrides=[
        {"fig_id": FIG_DATA, "backend": "r",
         "reason_code": "pipeline_in_r", "reason": "管线在 R"},
        {"fig_id": FIG_DATA, "backend": "python"},
    ]))
    assert "backend.conflict" in codes(filled_pkg["root"])


def test_figure_row_backend_mismatch_is_conflict(filled_pkg):
    data = load_package(filled_pkg["root"])
    for row in data["head"]["figures"]:
        if row["fig_id"] == FIG_DATA:
            row["backend"] = "r"  # 登记头行与 backend.json 解析（python）冲突
    save_head(filled_pkg["root"], data["head"])
    assert "backend.conflict" in codes(filled_pkg["root"])


def test_r_override_without_basis_rejected(filled_pkg):
    mutate_backend(filled_pkg, base_backend(overrides=[
        {"fig_id": FIG_DATA, "backend": "r", "reason": "想用 ggplot"}]))
    assert "backend.r_without_basis" in codes(filled_pkg["root"])


def test_r_override_with_basis_but_no_reason_rejected(filled_pkg):
    mutate_backend(filled_pkg, base_backend(overrides=[
        {"fig_id": FIG_DATA, "backend": "r",
         "reason_code": "r_decisive_advantage"}]))
    assert "backend.r_without_reason" in codes(filled_pkg["root"])


def test_r_override_with_full_basis_passes(filled_pkg):
    mutate_backend(filled_pkg, base_backend(overrides=[
        {"fig_id": FIG_DATA, "backend": "r",
         "reason_code": "r_decisive_advantage",
         "reason": "patchwork collect 收敛是该图组图的决定性能力"}]))
    assert validate_package(filled_pkg["root"])["ok"]


def test_package_level_r_needs_basis(filled_pkg):
    mutate_backend(filled_pkg, base_backend(backend="r"))
    assert "backend.r_without_basis" in codes(filled_pkg["root"])
    mutate_backend(filled_pkg, base_backend(
        backend="r", reason_code="pipeline_in_r"))
    assert validate_package(filled_pkg["root"])["ok"]


def test_schematic_figure_cannot_have_backend_override(filled_pkg):
    mutate_backend(filled_pkg, base_backend(overrides=[
        {"fig_id": FIG_METHOD, "backend": "python"}]))
    assert "backend.schematic_override" in codes(filled_pkg["root"])


def test_backend_undecided_is_warning_not_error(pkg):
    report = validate_package(pkg["root"])
    warning_codes = [w["code"] for w in report["warnings"]]
    assert "backend.undecided" in warning_codes


# ------------------------------------------------------------ 期刊与容差

def test_journal_numeric_legality(filled_pkg):
    def break_it(jc):
        jc["columns_mm"]["single"] = -5
        jc["font"]["min_pt"] = 9
        jc["font"]["max_pt"] = 7
        jc["formats_main"] = ["pdf", "bmp"]
    mutate_journal(filled_pkg, break_it)
    found = codes(filled_pkg["root"])
    assert "journal.column_illegal" in found
    assert "journal.font_order" in found
    assert "journal.format_unknown" in found


def test_palette_ref_needs_version(filled_pkg):
    def break_it(jc):
        jc["palettes"]["categorical"] = {"entry_id": "PAL-OI-8"}
    mutate_journal(filled_pkg, break_it)
    assert "palette.ref_incomplete" in codes(filled_pkg["root"])


def test_tolerance_relaxed_without_exemption_rejected(filled_pkg):
    def relax(jc):
        jc["tolerances"]["alignment_pt"] = 2.5
    mutate_journal(filled_pkg, relax)
    assert "tolerance.relaxed_without_exemption" in codes(filled_pkg["root"])


def test_tolerance_relaxed_with_exemption_passes(filled_pkg):
    def relax(jc):
        jc["tolerances"]["alignment_pt"] = 2.5
        jc["tolerance_exemptions"] = [{
            "param": "alignment_pt", "value": 2.5,
            "reason": "目标刊双栏大幅面图，编辑部确认可接受"}]
    mutate_journal(filled_pkg, relax)
    assert validate_package(filled_pkg["root"])["ok"]


def test_tolerance_exemption_needs_reason(filled_pkg):
    def relax(jc):
        jc["tolerances"]["alignment_pt"] = 2.5
        jc["tolerance_exemptions"] = [{"param": "alignment_pt", "value": 2.5}]
    mutate_journal(filled_pkg, relax)
    found = codes(filled_pkg["root"])
    assert "tolerance.exemption_no_reason" in found
    # 无理由的豁免不算数：放宽仍被判无登记
    assert "tolerance.relaxed_without_exemption" not in found  # 值已对位
    # ↑ 豁免按 param+value 对位即视为已登记，理由缺失另行报错（两层分开）


def test_glyph_floor_lowered_is_relaxation(filled_pkg):
    def relax(jc):
        jc["tolerances"]["glyph_floor_pt"] = 4.0
        jc["font"]["glyph_floor_pt"] = 4.0
    mutate_journal(filled_pkg, relax)
    assert "tolerance.relaxed_without_exemption" in codes(filled_pkg["root"])


def test_stricter_tolerances_need_no_exemption(filled_pkg):
    def tighten(jc):
        jc["tolerances"]["alignment_pt"] = 1.0
        jc["tolerances"]["glyph_floor_pt"] = 6.0
        jc["font"]["glyph_floor_pt"] = 6.0
    mutate_journal(filled_pkg, tighten)
    assert validate_package(filled_pkg["root"])["ok"]


def test_unknown_tolerance_param_rejected(filled_pkg):
    def add(jc):
        jc["tolerances"]["magic_pt"] = 1.0
    mutate_journal(filled_pkg, add)
    assert "tolerance.unknown_param" in codes(filled_pkg["root"])


# ------------------------------------------------------------ provenance

def test_provenance_not_required_before_produced(filled_pkg):
    # intake/contracted 段账行字段为空合法（账随产物落实）
    assert validate_package(filled_pkg["root"])["ok"]


def test_schematic_provenance_required_at_produced(filled_pkg):
    set_figure_stage(filled_pkg["root"], FIG_METHOD, "produced")
    found = codes(filled_pkg["root"])
    assert "provenance.reference_missing" in found
    assert "provenance.redraw_missing" in found
    fill_provenance_schematic(filled_pkg["root"])
    assert validate_package(filled_pkg["root"])["ok"]


def test_data_provenance_required_at_produced(filled_pkg):
    set_figure_stage(filled_pkg["root"], FIG_DATA, "produced")
    found = codes(filled_pkg["root"])
    assert "provenance.script_missing" in found
    assert "provenance.source_data_missing" in found
    fill_provenance_data(filled_pkg["root"])
    assert validate_package(filled_pkg["root"])["ok"]


def test_provenance_hash_format_enforced(filled_pkg):
    set_figure_stage(filled_pkg["root"], FIG_METHOD, "produced")
    fill_provenance_schematic(filled_pkg["root"])
    data = load_package(filled_pkg["root"])
    for entry in data["provenance"]["entries"]:
        if entry["fig_id"] == FIG_METHOD:
            entry["reference_image_hash"] = "not-a-hash"
    save_provenance(filled_pkg["root"], data["provenance"])
    assert "provenance.hash_format" in codes(filled_pkg["root"])


def test_provenance_row_missing_is_error(pkg):
    data = load_package(pkg["root"])
    data["provenance"]["entries"] = []
    save_provenance(pkg["root"], data["provenance"])
    assert "provenance.row_missing" in codes(pkg["root"])


# ------------------------------------------------------------ 承接快照

def test_snapshot_drift_detected(pkg):
    pkg["standalone"].write_text(
        pkg["standalone"].read_text(encoding="utf-8") + "\n# upstream edit\n",
        encoding="utf-8")
    assert "intake.snapshot_drift" in codes(pkg["root"])


def test_registered_journal_requires_metadata(tmp_path):
    from light_figure.project import init_package

    root = tmp_path / "figs"
    init_package(root, "Skeleton Journal")
    # 骨架未登记只警告；人为置 registered=true 而元数据为空则报错
    jc = make_journal_contract()
    jc["journal"] = None
    save_journal_contract(root, jc)
    assert "journal.field_missing" in codes(root)
