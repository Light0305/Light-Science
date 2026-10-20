"""承接：快照落盘、合同/账行开立、登记前校验、错误点名。"""

import pytest

from light_figure.intake import IntakeError, run_intake
from light_figure.project import init_package, load_package
from light_figure.util import dump_yaml, sha256_file, sha256_text
from conftest import (
    FIG_DATA, FIG_METHOD, make_ai_policy, make_journal_contract,
    make_manifest, make_standalone,
)


def test_standalone_intake_opens_contracts_and_ledger(pkg):
    root = pkg["root"]
    data = load_package(root)
    head = data["head"]
    assert head["intake"]["source_kind"] == "standalone"
    assert head["intake"]["source_hash"] == sha256_file(pkg["standalone"])
    rows = {r["fig_id"]: r for r in head["figures"]}
    assert rows[FIG_DATA]["line"] == "data"
    assert rows[FIG_METHOD]["line"] == "schematic"
    # 合同骨架与账行随承接开立
    assert set(data["contracts"]) == {FIG_DATA, FIG_METHOD}
    assert "policy_check" in data["contracts"][FIG_METHOD]
    assert "policy_check" not in data["contracts"][FIG_DATA]
    entries = {e["fig_id"]: e for e in data["provenance"]["entries"]}
    assert entries[FIG_METHOD]["reference_image_hash"] is None
    assert entries[FIG_DATA]["script_hash"] is None
    # 期刊与政策已登记
    assert data["journal_contract"]["registered"] is True
    assert head["target_journal"]["template_record_id"] == "TPL-DEMO-001"
    assert pkg["intake"]["journal_registered"] is True
    assert pkg["intake"]["ai_policy_snapshot"] is True


def test_manifest_intake_snapshots_caption_hash(tmp_path):
    root = tmp_path / "figs"
    init_package(root, "Manifest Intake")
    manifest = tmp_path / "figures_manifest.yaml"
    dump_yaml(manifest, make_manifest())
    result = run_intake(root, manifest=str(manifest))
    assert result["source_kind"] == "write_manifest"
    snapshot = load_package(root)["head"]["intake"]["entries_snapshot"]
    by_id = {e["figure_id"]: e for e in snapshot}
    assert by_id[FIG_DATA]["caption_draft_hash"] == sha256_text(
        "Accuracy of the three threshold arms.")
    assert by_id[FIG_DATA]["intext_anchor"] == "results:p2"
    assert by_id[FIG_METHOD]["kind"] == "schematic"


def test_intake_rejects_unknown_kind(tmp_path):
    root = tmp_path / "figs"
    init_package(root, "Bad Kind")
    bad = tmp_path / "bad.yaml"
    dump_yaml(bad, {"figures": [{"fig_id": "x", "kind": "figure"}]})
    with pytest.raises(IntakeError) as exc:
        run_intake(root, standalone=str(bad))
    assert any("kind" in g for g in exc.value.gaps)


def test_intake_requires_exactly_one_source(pkg):
    with pytest.raises(IntakeError):
        run_intake(pkg["root"], manifest="a.yaml", standalone="b.yaml")
    with pytest.raises(IntakeError):
        run_intake(pkg["root"])


def test_intake_rejects_illegal_journal_contract(tmp_path):
    root = tmp_path / "figs"
    init_package(root, "Bad Journal")
    standalone = tmp_path / "s.yaml"
    dump_yaml(standalone, make_standalone())
    jc = make_journal_contract()
    jc["columns_mm"]["single"] = -5
    journal = tmp_path / "j.yaml"
    dump_yaml(journal, jc)
    with pytest.raises(IntakeError) as exc:
        run_intake(root, standalone=str(standalone),
                   journal_contract_file=str(journal))
    assert any("journal.column_illegal" in g for g in exc.value.gaps)
    # 非法合同不许入包：包内仍为未登记骨架
    assert load_package(root)["journal_contract"]["registered"] is False


def test_intake_rejects_incomplete_ai_policy(tmp_path):
    root = tmp_path / "figs"
    init_package(root, "Bad Policy")
    standalone = tmp_path / "s.yaml"
    dump_yaml(standalone, make_standalone())
    policy = make_ai_policy()
    del policy["verified_at"]
    policy_path = tmp_path / "p.yaml"
    dump_yaml(policy_path, policy)
    with pytest.raises(IntakeError) as exc:
        run_intake(root, standalone=str(standalone),
                   ai_policy_file=str(policy_path))
    assert any("verified_at" in g for g in exc.value.gaps)


def test_intake_policy_exhibit_exemption_key_required(tmp_path):
    root = tmp_path / "figs"
    init_package(root, "Exemption Key")
    standalone = tmp_path / "s.yaml"
    dump_yaml(standalone, make_standalone())
    policy = make_ai_policy()
    del policy["exhibit_exemption"]  # 键缺失与显式 null 不同：须点名
    policy_path = tmp_path / "p.yaml"
    dump_yaml(policy_path, policy)
    with pytest.raises(IntakeError) as exc:
        run_intake(root, standalone=str(standalone),
                   ai_policy_file=str(policy_path))
    assert any("exhibit_exemption" in g for g in exc.value.gaps)
