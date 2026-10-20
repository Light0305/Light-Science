"""校验器纪律：主张/占位符/撤稿/哈希漂移/声明/use_log/账本逐条正反例。"""

from pathlib import Path

import pytest

from light_write.project import load_package, save_claims, save_manuscript
from light_write.util import dump_yaml
from light_write.validate import validate_package
from conftest import add_section


def codes(report, level="error"):
    return {i["code"] for i in report[f"{level}s"]}


def mutate_claims(root, fn):
    data = load_package(root)
    fn(data["claims"]["claims"])
    save_claims(root, data["claims"])


def test_baseline_pkg_has_no_errors(pkg):
    report = validate_package(pkg["root"])
    assert report["ok"], report["errors"]


def test_untested_form_full_rejected(tmp_path, upstreams):
    from light_write.intake import run_intake
    from light_write.project import init_package
    from conftest import make_blocked_card
    from light_write.util import dump_json

    card_path = tmp_path / "card.json"
    dump_json(card_path, make_blocked_card())
    root = tmp_path / "ms"
    init_package(root, "Blocked Demo", "en")
    run_intake(root, card_path, upstreams["literature"])
    mutate_claims(root, lambda rows: rows[0].update(writable_form="full"))
    report = validate_package(root)
    assert "claims.form_exceeds_ceiling" in codes(report)


def test_wording_language_mismatch_rejected(pkg):
    def fn(rows):
        rows[0]["wording_ceiling"] = dict(rows[0]["wording_ceiling"], language="zh")
    mutate_claims(pkg["root"], fn)
    assert "claims.wording_language" in codes(validate_package(pkg["root"]))


def test_text_hash_drift_detected(pkg):
    mutate_claims(pkg["root"], lambda rows: rows[0].update(
        claim_text="Method A vastly outperforms everything."))
    assert "claims.text_hash_drift" in codes(validate_package(pkg["root"]))


def test_claims_coverage_missing_and_extra(pkg):
    mutate_claims(pkg["root"], lambda rows: rows.pop(0))
    assert "claims.coverage_missing" in codes(validate_package(pkg["root"]))
    mutate_claims(pkg["root"], lambda rows: rows.append(
        {"claim_id": "C9", "analysis_claim_ref": "C9",
         "upstream_status": "supported", "strength_grade": "strong",
         "writable_ceiling": "full", "writable_form": "full",
         "wording_ceiling": {"language": "en"}, "claim_text": None,
         "text_hash": None}))
    assert "claims.coverage_extra" in codes(validate_package(pkg["root"]))


def test_section_unknown_cite_key_and_lit_id(pkg):
    add_section(pkg["root"], text="Text [@nosuchkey] and [@lit:ST999].\n")
    found = codes(validate_package(pkg["root"]))
    assert "cite.unknown_key" in found and "cite.unknown_entry" in found


def test_section_cites_locked_key_ok(pkg):
    lock = load_package(pkg["root"])["lock"]
    key = lock["entries"][0]["key"]
    add_section(pkg["root"], text=f"Prior work [@{key}] motivates this.\n")
    report = validate_package(pkg["root"])
    assert "cite.unknown_key" not in codes(report)


def test_section_bare_doi_is_error_etal_is_warning(pkg):
    add_section(pkg["root"],
                text="As shown by Lovelace et al. (2024), see 10.1000/clean.1 for details.\n")
    report = validate_package(pkg["root"])
    assert "section.bare_doi" in codes(report)
    assert "section.handwritten_cite" in codes(report, "warning")


def test_section_unknown_claim_and_num_markers(pkg):
    add_section(pkg["root"], text="Claim here [claim:C9] and value [num:N9].\n")
    found = codes(validate_package(pkg["root"]))
    assert "section.unknown_claim_mark" in found
    assert "section.unknown_num_mark" in found


def _cite_entry(pkg, entry_id):
    lock = load_package(pkg["root"])["lock"]
    entry = next(e for e in lock["entries"] if e["entry_id"] == entry_id)
    add_section(pkg["root"], text=f"Cited [@{entry['key']}].\n")
    return entry


def test_cited_retracted_entry_rejected(pkg):
    _cite_entry(pkg, "ST002")
    assert "cite.retracted" in codes(validate_package(pkg["root"]))


def test_cited_unknown_retraction_needs_note(pkg):
    entry = _cite_entry(pkg, "ST005")
    assert "cite.retraction_unknown_no_note" in codes(validate_package(pkg["root"]))
    # 落字说明后放行
    data = load_package(pkg["root"])
    for e in data["lock"]["entries"]:
        if e["entry_id"] == "ST005":
            e["retraction_note"] = "2026-10-20 复核 Crossref/Europe PMC：无撤稿信号，状态待成稿时点再核"
    from light_write.project import save_lock
    from light_write.render import render_bib
    save_lock(pkg["root"], data["lock"])
    (pkg["root"] / "references.bib").write_text(
        render_bib(data["lock"]["entries"]), encoding="utf-8")
    assert "cite.retraction_unknown_no_note" not in codes(validate_package(pkg["root"]))


def test_bib_hand_edit_detected(pkg):
    bib = pkg["root"] / "references.bib"
    bib.write_text(bib.read_text(encoding="utf-8") + "% sneaky manual edit\n",
                   encoding="utf-8")
    assert "bib.hand_edited" in codes(validate_package(pkg["root"]))


def test_literature_snapshot_stale_detected(pkg):
    lit = pkg["upstreams"]["literature"]
    text = lit.read_text(encoding="utf-8")
    lit.write_text(text.replace("Title of ST001", "Changed Title of ST001"),
                   encoding="utf-8")
    assert "intake.literature_stale" in codes(validate_package(pkg["root"]))


def test_declarations_missing_na_and_absent(pkg):
    data = load_package(pkg["root"])
    ms = data["manuscript"]
    del ms["declarations"]["ethics"]
    ms["declarations"]["funding"] = {"state": "na", "note": None}
    save_manuscript(pkg["root"], ms)
    report = validate_package(pkg["root"])
    found = codes(report)
    assert "declarations.missing" in found
    assert "declarations.na_no_reason" in found
    assert "declarations.absent" in codes(report, "warning")


def test_use_log_missing_model_version_rejected(pkg):
    data = load_package(pkg["root"])
    data["manuscript"]["use_log"] = [
        {"tool": "SomeLLM", "model": "x", "purpose": "语言润色",
         "section": "introduction", "date": "2026-10-20"}]
    save_manuscript(pkg["root"], data["manuscript"])
    assert "use_log.no_model_version" in codes(validate_package(pkg["root"]))


def test_numbers_without_trace_and_figure_backfill(pkg):
    root = pkg["root"]
    dump_yaml(root / "numbers_ledger.yaml",
              {"numbers": [{"num_id": "N001", "trace_ref": None}]})
    dump_yaml(root / "figures_manifest.yaml",
              {"figures": [{"figure_id": "F001", "status": "backfilled",
                            "source_ref": "fig.pdf"}]})
    found = codes(validate_package(root))
    assert "numbers.no_trace" in found
    assert "figures.backfill_no_source" in found


def test_checklist_na_requires_reason(pkg):
    dump_yaml(pkg["root"] / "submission_checklist.yaml",
              {"items": [{"item_id": "CHK1", "source": "journal",
                          "requirement": "结构化摘要", "status": "not_applicable",
                          "note": None}]})
    assert "checklist.na_no_reason" in codes(validate_package(pkg["root"]))
