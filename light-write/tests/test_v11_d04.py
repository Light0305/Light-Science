"""WRT-D04 贡献确认回执：未签拦 outlined、签认漂移点名、防篡改检出。"""

import pytest

from light_write.gates import advance
from light_write.intake import ContributionError, confirm_contribution
from light_write.project import load_package, save_claims, save_manuscript
from light_write.util import dump_yaml
from light_write.validate import validate_package
from conftest import add_assertions
from light_write.gates import freeze_contract
from light_write.template_reg import register_template


def _codes(report):
    return {e["code"] for e in report["errors"]}


def test_unsigned_contribution_blocks_outlined(pkg, record_path):
    register_template(pkg["root"], record_path)
    add_assertions(pkg["root"])
    freeze_contract(pkg["root"])
    result = advance(pkg["root"])
    assert result["advanced"] is False
    assert any("贡献确认回执未签认" in g for g in result["gaps"])


def test_signed_contribution_unblocks(pkg, record_path):
    register_template(pkg["root"], record_path)
    receipt = confirm_contribution(pkg["root"], by="the author")
    assert receipt["drift_from_draft"] is False
    assert receipt["statement"]  # 草案由上游主张 C1 文本组装，非空
    add_assertions(pkg["root"])
    freeze_contract(pkg["root"])
    result = advance(pkg["root"])
    assert result["advanced"] is True and result["to"] == "outlined"


def test_drift_without_note_rejected(pkg):
    with pytest.raises(ContributionError):
        confirm_contribution(pkg["root"], by="the author",
                             statement="A completely different claim.")


def test_drift_with_note_recorded(pkg):
    receipt = confirm_contribution(
        pkg["root"], by="the author",
        statement="Method A outperforms the fixed-threshold baseline "
                  "on held-out segments.",
        drift_note="补入留出段限定（草案只含 C1 原文，签认时按 C2 证据收窄）")
    assert receipt["drift_from_draft"] is True
    assert receipt["drift_note"]


def test_statement_tamper_detected(pkg):
    confirm_contribution(pkg["root"], by="the author")
    pkg_data = load_package(pkg["root"])
    pkg_data["manuscript"]["contribution"]["receipt"]["statement"] = \
        "Tampered statement."
    save_manuscript(pkg["root"], pkg_data["manuscript"])
    report = validate_package(pkg["root"])
    assert "contribution.receipt_hash_drift" in _codes(report)


def test_upstream_claim_change_requires_resign(pkg):
    confirm_contribution(pkg["root"], by="the author")
    pkg_data = load_package(pkg["root"])
    claims = pkg_data["claims"]
    claims["claims"][0]["claim_text"] = "Rewritten upstream claim text."
    claims["claims"][0]["text_hash"] = None
    dump_yaml(pkg["root"] / "claims_register.yaml", claims)
    report = validate_package(pkg["root"])
    assert "contribution.source_drift" in _codes(report)
