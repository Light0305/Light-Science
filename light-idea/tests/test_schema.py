"""schema 结构校验：正例 + 每类反例。"""

from conftest import full_card
from light_idea.schema import validate_card


def test_full_card_valid():
    assert validate_card(full_card()) == []


def test_missing_facet_flagged():
    c = full_card()
    del c["facets"]["mechanism"]
    errs = validate_card(c)
    assert any("facets.mechanism" in e for e in errs)


def test_facet_empty_phrase_flagged():
    c = full_card()
    c["facets"]["purpose"]["phrase"] = "  "
    assert any("facets.purpose.phrase" in e for e in validate_card(c))


def test_seed_ref_bare_text_rejected():
    c = full_card()
    c["seed_refs"] = ["He et al. 2022, Masked Autoencoders"]
    errs = validate_card(c)
    assert any("seed_refs[0]" in e and "paper_id" in e for e in errs)


def test_seed_ref_without_id_rejected():
    c = full_card()
    c["seed_refs"] = [{"title": "某篇论文", "year": 2023}]
    assert any("seed_refs[0]" in e for e in validate_card(c))


def test_seed_ref_with_doi_ok():
    c = full_card()
    c["seed_refs"] = [{"doi": "10.1000/xyz123"}]
    assert validate_card(c) == []


def test_facet_paper_source_needs_ref():
    c = full_card()
    c["facets"]["purpose"]["source"] = {"type": "paper", "title": "某论文"}
    assert any("facets.purpose.source" in e for e in validate_card(c))


def test_provenance_required():
    c = full_card()
    c["provenance"] = {"chain_id": None, "path_string": None, "combo": None, "note": None}
    assert any("provenance" in e for e in validate_card(c))


def test_aux_verdict_forbidden():
    c = full_card()
    c["aux"] = {"verdict": "PROCEED"}
    assert any("aux" in e and "verdict" in e for e in validate_card(c))


def test_aux_unknown_key_flagged():
    c = full_card()
    c["aux"] = {"magic_score": 9.9}
    assert any("aux" in e for e in validate_card(c))


def test_novelty_similarity_forbidden():
    """物理分离：相似度分不许混进判定区。"""
    c = full_card()
    c["novelty"]["neighbor_similarity"] = 0.9
    assert any("novelty" in e and "aux" in e for e in validate_card(c))


def test_bad_verdict_flagged():
    c = full_card()
    c["novelty"]["verdict"] = "MAYBE"
    assert any("verdict" in e for e in validate_card(c))


def test_bad_status_and_operator_flagged():
    c = full_card()
    c["status"] = "almost_done"
    c["operator"] = "vibes"
    errs = validate_card(c)
    assert any("status" in e for e in errs)
    assert any("operator" in e for e in errs)


def test_closest_work_needs_ref():
    c = full_card()
    c["novelty"]["closest_works"] = [{"title": "撞车论文", "verified": True}]
    assert any("closest_works[0]" in e for e in validate_card(c))
