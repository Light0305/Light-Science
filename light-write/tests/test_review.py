"""复核门：同族拒、收据、UNAVAILABLE 拦 ready、回填 schema、STALE。"""

import pytest

from light_write.gates import advance
from light_write.project import load_package
from light_write.review import (
    ReviewError, import_review, prepare_review, record_review,
    record_unavailable,
)
from light_write.util import dump_json


def test_prepare_packet_scopes_boundary_claims(audited_pkg):
    root = audited_pkg["root"]
    info = prepare_review(root)
    # C2（suggestive 且在正文）为边界主张；C1（strong/full）不在范围
    assert info["scope_claim_ids"] == ["C2"]
    packet = (root / "review_packet.md").read_text(encoding="utf-8")
    assert "成稿口径宪法" in packet


def test_record_same_family_rejected(audited_pkg):
    root = audited_pkg["root"]
    prepare_review(root)
    with pytest.raises(ReviewError) as exc:
        record_review(root, "Other Reviewer", "executor-family")
    assert any("同族" in g for g in exc.value.gaps)


def test_record_cross_family_receipt_then_ready(audited_pkg):
    root = audited_pkg["root"]
    prepare_review(root)
    review = record_review(root, "GPT Reviewer", "openai-family")
    assert review["receipt_id"].startswith("RV-")
    assert review["review_status"] == "approved"
    result = advance(root)
    assert result["advanced"] is True, result
    assert result["to"] == "submission_ready"
    assert load_package(root)["manuscript"]["status"] == "submission_ready"


def test_unavailable_blocks_ready_and_records_reason(audited_pkg):
    root = audited_pkg["root"]
    prepare_review(root)
    record_unavailable(root, reason="本环境无异家族模型")
    result = advance(root)
    assert result["advanced"] is False
    assert any("REVIEW_UNAVAILABLE" in g for g in result["gaps"])
    ms = load_package(root)["manuscript"]
    assert ms["status"] == "audited"
    assert "REVIEW_UNAVAILABLE" in ms["submission_blocked_reason"]


def test_import_review_schema_and_agree(audited_pkg, tmp_path):
    root = audited_pkg["root"]
    prepare_review(root)
    payload = {"reviewer": "Gemini Reviewer", "family": "google-family",
               "decisions": [{"claim_id": "C2", "agree": True,
                              "comment": "措辞与 suggestive 档贴合"}],
               "notes": None}
    path = tmp_path / "verdict.json"
    dump_json(path, payload)
    review = import_review(root, path)
    assert review["via"] == "import"
    assert review["receipt_id"].startswith("RV-")


def test_import_review_disagree_rejected(audited_pkg, tmp_path):
    root = audited_pkg["root"]
    prepare_review(root)
    payload = {"reviewer": "Gemini Reviewer", "family": "google-family",
               "decisions": [{"claim_id": "C2", "agree": False,
                              "comment": "措辞仍偏强"}]}
    path = tmp_path / "verdict-disagree.json"
    dump_json(path, payload)
    with pytest.raises(ReviewError) as exc:
        import_review(root, path)
    assert any("disagree" in g or "异议" in g for g in exc.value.gaps)


def test_import_review_missing_decision_rejected(audited_pkg, tmp_path):
    root = audited_pkg["root"]
    prepare_review(root)
    payload = {"reviewer": "Gemini Reviewer", "family": "google-family",
               "decisions": []}
    path = tmp_path / "verdict-empty.json"
    dump_json(path, payload)
    with pytest.raises(ReviewError):
        import_review(root, path)


def test_review_stale_after_manuscript_edit(audited_pkg):
    root = audited_pkg["root"]
    prepare_review(root)
    record_review(root, "GPT Reviewer", "openai-family")
    path = root / "sections" / "04-discussion.md"
    path.write_text(path.read_text(encoding="utf-8") + "An added sentence.\n",
                    encoding="utf-8")
    result = advance(root)
    assert result["advanced"] is False
    assert any("STALE" in g for g in result["gaps"])
