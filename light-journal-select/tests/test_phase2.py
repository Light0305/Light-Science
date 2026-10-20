"""Phase 2：decide 定刊门 + handoff 交接（manifest 诚实、
check-record 自检闭环、语言一致、状态机全序、指南修订并存）。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from light_journal_select.checkrecord import (
    build_check_record, check_record_structure, run_write_selfcheck,
)
from light_journal_select.decide import apply_decide
from light_journal_select.gate import apply_gate
from light_journal_select.gates import GateError
from light_journal_select.handoff import run_handoff
from light_journal_select.project import FILES, load_selection
from light_journal_select.util import dump_json, load_structured, sha256_file
from light_journal_select.validate import validate_package

CEA = "Computers and Electronics in Agriculture"
ANIMALS = "Animals"
POULTRY = "Poultry Science"
WRITE_ROOT = Path(__file__).resolve().parents[2] / "light-write"


def _check(condition, hit=True, source="official-page"):
    return {"condition": condition, "hit": hit, "source": source,
            "source_ref": "checked 2026-10-20", "checked_at": "2026-10-20",
            "note": None}


def _clear():
    return [_check("warning_list_hit", hit=False),
            _check("predatory_list_hit", hit=False)]


def _gate_all(pkg, extra=None, overrides=None):
    checks = {CEA: _clear(), ANIMALS: _clear(), POULTRY: _clear()}
    checks.update(extra or {})
    return apply_gate(pkg, checks, overrides=overrides,
                      today_str="2026-10-20")


@pytest.fixture()
def gated_pkg(verified_pkg):
    _gate_all(verified_pkg)
    return verified_pkg


@pytest.fixture()
def decided_pkg(gated_pkg):
    apply_decide(gated_pkg, CEA, decided_by="用户本人",
                 reason="先例最密、scope 对口", date_str="2026-10-20")
    return gated_pkg


GUIDE_FIELDS = {
    "A": {"template_version": "elsarticle-2026",
          "applicable_years": [2026]},
    "B": {"format_track": "latex", "latex_class": "elsarticle",
          "class_version": "3.4", "options_axis": ["preprint", "review"],
          "word_template": None, "citation_package": "natbib"},
    "C": {"section_sequence": ["Abstract", "Introduction", "Methods",
                               "Results", "Discussion", "Conclusions"],
          "abstract_form": "unstructured", "keyword_limit": 6,
          "special_sections": ["CRediT authorship statement"]},
    "D": {"word_limit_total": 8000, "word_limit_abstract": 250,
          "page_limit": None, "figure_limit": None, "table_limit": None,
          "reference_limit": None, "title_char_limit": 120,
          "short_title_char_limit": 45},
    "E": {"style_name": "Elsevier Harvard", "csl_id": "elsevier-harvard",
          "bst_name": "elsarticle-harv",
          "citation_style_kind": "author-year"},
    "F": {"figure_submission_mode": "separate_files",
          "figure_formats": ["pdf", "eps", "tiff"],
          "figure_resolution": "300 dpi", "caption_position": "below"},
    "G": {"declarations": [
              {"type": "data_availability", "required": True,
               "position": "end", "field_name": "data_availability"},
              {"type": "conflict_of_interest", "required": True,
               "position": "end", "field_name": "conflict"}],
          "ai_policy": {
              "has_guideline": True, "ai_authorship_banned": True,
              "disclosure_required": True,
              "disclosure_content_standard": "tool name and purpose",
              "disclosure_title": "Declaration of generative AI use",
              "disclosure_wording_template": None,
              "disclosure_positions": ["Methods", "Acknowledgments"],
              "language_editing_stance": "allowed with disclosure",
              "publisher_conflict": {"conflict": False,
                                     "resolution_note": None},
              "output_validity_evaluation": None}},
    "I": {"redistribution": "channel_only",
          "terms_pointer": "https://example.org/terms",
          "purpose_restriction": "submission use only"},
}


def _file_specs(tmp_path):
    incoming = tmp_path / "incoming"
    incoming.mkdir(exist_ok=True)
    guide = incoming / "guide.pdf"
    guide.write_bytes(b"%PDF-fake-author-guide")
    return [
        {"kind": "guideline", "filename": "author-guide.pdf",
         "source_url": "https://example.org/author-guide",
         "local_path": str(guide)},
        {"kind": "template", "filename": "elsarticle.zip",
         "source_url": "https://example.org/elsarticle.zip"},
    ]


# ------------------------------------------------------------- decide

def test_decide_happy_path(decided_pkg):
    selection = load_selection(decided_pkg)
    assert selection["status"] == "decided"
    decision = selection["decision"]
    assert decision["journal"] == CEA
    assert decision["decided_at"] == "2026-10-20"
    assert decision["decided_by"] == "用户本人"
    assert decision["reason"]


def test_decide_requires_decider_and_reason(gated_pkg):
    with pytest.raises(GateError) as exc:
        apply_decide(gated_pkg, CEA)
    text = "；".join(exc.value.gaps)
    assert "定刊人未填" in text and "定刊理由未填" in text
    assert load_selection(gated_pkg)["status"] == "gated"  # 半落盘不许


def test_decide_before_gate_rejected(verified_pkg):
    with pytest.raises(GateError) as exc:
        apply_decide(verified_pkg, CEA, decided_by="用户", reason="x")
    assert "不许定刊" in "；".join(exc.value.gaps)


def test_decide_hard_excluded_rejected(verified_pkg):
    _gate_all(verified_pkg, extra={
        POULTRY: [_check("warning_list_hit", source="中科院预警名单官方页")]})
    with pytest.raises(GateError) as exc:
        apply_decide(verified_pkg, POULTRY, decided_by="用户", reason="x")
    text = "；".join(exc.value.gaps)
    assert "已被风险门排除" in text and "hard_exclude" in text


def test_decide_quasi_unreleased_rejected(verified_pkg):
    _gate_all(verified_pkg, extra={
        ANIMALS: [_check("predatory_list_hit",
                         source="stop-predatory-journals")]})
    with pytest.raises(GateError) as exc:
        apply_decide(verified_pkg, ANIMALS, decided_by="用户", reason="x")
    assert "已被风险门排除" in "；".join(exc.value.gaps)


def test_decide_quasi_released_allowed(verified_pkg):
    override = {"confirmed_by": "用户本人",
                "confirmation_text": "已知情，仍决定投",
                "date": "2026-10-20"}
    _gate_all(verified_pkg,
              extra={ANIMALS: [_check("predatory_list_hit",
                                      source="stop-predatory-journals")]},
              overrides={ANIMALS: override})
    result = apply_decide(verified_pkg, ANIMALS, decided_by="用户本人",
                          reason="知情后仍选", date_str="2026-10-20")
    assert result["status"] == "decided"
    assert result["decision"]["risk_level"] == "quasi_hard"


def test_decide_unknown_candidate_rejected(gated_pkg):
    with pytest.raises(GateError) as exc:
        apply_decide(gated_pkg, "No Such Journal",
                     decided_by="用户", reason="x")
    assert "不在候选池中" in "；".join(exc.value.gaps)


# ------------------------------------------------------------- handoff

def test_handoff_full_flow(decided_pkg, tmp_path):
    result = run_handoff(decided_pkg, fields=GUIDE_FIELDS,
                         file_specs=_file_specs(tmp_path),
                         today_str="2026-10-20")
    assert result["status"] == "handed_off"
    root = Path(decided_pkg)
    target = root / FILES["target_dir"]
    assert (target / "guideline" / "2026-10-20" / "author-guide.pdf") \
        .read_bytes() == b"%PDF-fake-author-guide"
    assert (target / "templates").is_dir()
    manifest = load_structured(root / FILES["manifest"])
    by_name = {e["filename"]: e for e in manifest["entries"]}
    guide = by_name["author-guide.pdf"]
    assert guide["status"] == "downloaded"
    assert guide["downloaded_at"] == "2026-10-20"
    assert guide["sha256"] == sha256_file(
        target / "guideline" / "2026-10-20" / "author-guide.pdf")
    tpl = by_name["elsarticle.zip"]
    assert tpl["status"] == "pending_download"      # 没真下载如实 pending
    assert tpl["sha256"] is None and tpl["stored_path"] is None
    record = load_structured(root / FILES["check_record"])
    assert record["A"]["journal_name"] == CEA
    assert record["A"]["journal_language"] == "en"
    assert record["A"]["record_id"].startswith("TR-2026-")
    assert record["H"]["verified_at"] == "2026-10-20"
    md = (root / FILES["handoff_md"]).read_text(encoding="utf-8")
    assert "register-template" in md and CEA in md
    assert "本地结构校验 pass" in md
    selection = load_selection(decided_pkg)
    assert selection["status"] == "handed_off"
    assert selection["handoff"]["record_id"] == record["A"]["record_id"]
    assert validate_package(decided_pkg)["ok"]


def test_handoff_full_state_sequence(decided_pkg, tmp_path):
    run_handoff(decided_pkg, fields=GUIDE_FIELDS,
                file_specs=_file_specs(tmp_path), today_str="2026-10-20")
    history = [h["state"]
               for h in load_selection(decided_pkg)["status_history"]]
    assert history == ["draft", "candidates_ready", "verified", "gated",
                       "decided", "handed_off"]


def test_handoff_requires_fields(decided_pkg):
    with pytest.raises(GateError) as exc:
        run_handoff(decided_pkg, fields=None, today_str="2026-10-20")
    assert "缺指南字段文件" in "；".join(exc.value.gaps)
    assert load_selection(decided_pkg)["status"] == "decided"


def test_handoff_broken_record_blocked(decided_pkg, tmp_path):
    fields = json.loads(json.dumps(GUIDE_FIELDS))
    fields["D"] = {}                       # 限额组全空 → Write 必 error
    with pytest.raises(GateError) as exc:
        run_handoff(decided_pkg, fields=fields,
                    file_specs=_file_specs(tmp_path), today_str="2026-10-20")
    assert "template.limits_empty" in "；".join(exc.value.gaps)
    assert load_selection(decided_pkg)["status"] == "decided"
    assert not (Path(decided_pkg) / FILES["check_record"]).exists()


def test_handoff_ai_disclosure_positions_blocked(decided_pkg, tmp_path):
    fields = json.loads(json.dumps(GUIDE_FIELDS))
    fields["G"]["ai_policy"]["disclosure_positions"] = []
    with pytest.raises(GateError) as exc:
        run_handoff(decided_pkg, fields=fields,
                    file_specs=_file_specs(tmp_path), today_str="2026-10-20")
    assert "template.ai_disclosure_positions" in "；".join(exc.value.gaps)
    assert load_selection(decided_pkg)["status"] == "decided"


def test_handoff_language_conflict_blocked(decided_pkg, tmp_path):
    fields = json.loads(json.dumps(GUIDE_FIELDS))
    fields["A"]["journal_language"] = "zh"   # 稿件是 en：拿错指南
    with pytest.raises(GateError) as exc:
        run_handoff(decided_pkg, fields=fields,
                    file_specs=_file_specs(tmp_path), today_str="2026-10-20")
    assert "不一致" in "；".join(exc.value.gaps)
    assert load_selection(decided_pkg)["status"] == "decided"


def test_record_language_follows_manuscript():
    selection = {"selection_id": "sel_x",
                 "manuscript": {"language": "zh"}}
    candidate = {"candidate_id": "J-zh", "name": "农业工程学报",
                 "issn": "1002-6819", "publisher": "中国农业工程学会",
                 "guide_url": None, "homepage_url": "https://example.org/zh"}
    record, gaps = build_check_record(selection, candidate, GUIDE_FIELDS,
                                      "2026-10-20")
    assert gaps == []
    assert record["A"]["journal_language"] == "zh"


def test_handoff_missing_local_file_stays_pending(decided_pkg, tmp_path):
    specs = [{"kind": "guideline", "filename": "guide.pdf",
              "source_url": "https://example.org/guide.pdf",
              "local_path": str(tmp_path / "not-there.pdf")}]
    run_handoff(decided_pkg, fields=GUIDE_FIELDS, file_specs=specs,
                today_str="2026-10-20")
    manifest = load_structured(Path(decided_pkg) / FILES["manifest"])
    entry = manifest["entries"][0]
    assert entry["status"] == "pending_download"
    assert entry["sha256"] is None
    assert "不存在" in entry["note"]


def test_handoff_auto_pending_guide_entry(decided_pkg):
    run_handoff(decided_pkg, fields=GUIDE_FIELDS, file_specs=None,
                today_str="2026-10-20")
    manifest = load_structured(Path(decided_pkg) / FILES["manifest"])
    assert len(manifest["entries"]) == 1
    entry = manifest["entries"][0]
    assert entry["kind"] == "guideline"
    assert entry["status"] == "pending_download"
    assert entry["source_url"] == "https://example.org/journal"


def test_guideline_refresh_supersedes(decided_pkg, tmp_path):
    run_handoff(decided_pkg, fields=GUIDE_FIELDS,
                file_specs=_file_specs(tmp_path), today_str="2026-10-20")
    incoming = tmp_path / "incoming2"
    incoming.mkdir()
    new_guide = incoming / "guide-v2.pdf"
    new_guide.write_bytes(b"%PDF-guide-v2")
    result = run_handoff(
        decided_pkg, fields=GUIDE_FIELDS,
        file_specs=[{"kind": "guideline", "filename": "author-guide.pdf",
                     "source_url": "https://example.org/author-guide",
                     "local_path": str(new_guide)}],
        guideline_version="2027-01", today_str="2027-01-15")
    assert result["refresh"] is True
    root = Path(decided_pkg)
    assert (root / FILES["target_dir"] / "guideline" / "2027-01"
            / "author-guide.pdf").exists()
    assert (root / FILES["target_dir"] / "guideline" / "2026-10-20"
            / "author-guide.pdf").exists()      # 旧版并存不删
    manifest = load_structured(root / FILES["manifest"])
    guides = [e for e in manifest["entries"] if e["kind"] == "guideline"]
    assert len(guides) == 2
    assert guides[1]["supersedes"] == guides[0]["entry_id"]
    assert guides[0]["superseded_by"] == guides[1]["entry_id"]
    selection = load_selection(decided_pkg)
    assert selection["status"] == "handed_off"
    kinds = [h["kind"] for h in selection["handoff_history"]]
    assert kinds == ["initial", "guideline_refresh"]
    assert validate_package(decided_pkg)["ok"]


def test_manifest_tamper_detected(decided_pkg, tmp_path):
    run_handoff(decided_pkg, fields=GUIDE_FIELDS,
                file_specs=_file_specs(tmp_path), today_str="2026-10-20")
    root = Path(decided_pkg)
    manifest_path = root / FILES["manifest"]
    manifest = load_structured(manifest_path)
    pending = next(e for e in manifest["entries"]
                   if e["status"] == "pending_download")
    pending["sha256"] = "0" * 64               # 给未下载条目伪造哈希
    dump_json(manifest_path, manifest)
    rep = validate_package(decided_pkg)
    assert any(i["code"] == "manifest.pending_with_hash"
               for i in rep["errors"])


def test_stored_file_swap_detected(decided_pkg, tmp_path):
    run_handoff(decided_pkg, fields=GUIDE_FIELDS,
                file_specs=_file_specs(tmp_path), today_str="2026-10-20")
    stored = (Path(decided_pkg) / FILES["target_dir"] / "guideline"
              / "2026-10-20" / "author-guide.pdf")
    stored.write_bytes(b"tampered")
    rep = validate_package(decided_pkg)
    assert any(i["code"] == "manifest.hash_mismatch" for i in rep["errors"])


# ------------------------------------------------- 与 Write 的自检闭环

@pytest.mark.skipif(not (WRITE_ROOT / "light_write").exists(),
                    reason="light-write 姊妹包不在场")
def test_generated_record_passes_real_write_validator(decided_pkg,
                                                      tmp_path):
    run_handoff(decided_pkg, fields=GUIDE_FIELDS,
                file_specs=_file_specs(tmp_path), today_str="2026-10-20")
    record_path = Path(decided_pkg) / FILES["check_record"]
    result = run_write_selfcheck(record_path, WRITE_ROOT)
    assert result["status"] == "pass", result
    assert result["errors"] == []


@pytest.mark.skipif(not (WRITE_ROOT / "light_write").exists(),
                    reason="light-write 姊妹包不在场")
def test_write_selfcheck_hook_records_pass(decided_pkg, tmp_path):
    result = run_handoff(decided_pkg, fields=GUIDE_FIELDS,
                         file_specs=_file_specs(tmp_path),
                         write_root=str(WRITE_ROOT), today_str="2026-10-20")
    assert result["self_check"]["write_check"] == "pass"
    md = (Path(decided_pkg) / FILES["handoff_md"]).read_text(
        encoding="utf-8")
    assert "Write 校验器自检 pass" in md


@pytest.mark.skipif(not (WRITE_ROOT / "light_write").exists(),
                    reason="light-write 姊妹包不在场")
def test_write_selfcheck_bites_broken_record(tmp_path):
    record, _ = build_check_record(
        {"selection_id": "s", "manuscript": {"language": "en"}},
        {"candidate_id": "J-x", "name": "X", "publisher": "P",
         "issn": None, "eissn": None, "guide_url": None,
         "homepage_url": None},
        GUIDE_FIELDS, "2026-10-20")
    del record["H"]["verified_at"]            # 构造 Write 必 error 的记录
    rep = check_record_structure(record)       # 本地镜像先咬住
    assert any(i["code"] == "template.field_missing" for i in rep.errors)
    path = tmp_path / "broken.json"
    dump_json(path, record)
    result = run_write_selfcheck(path, WRITE_ROOT)   # 真 Write 校验器也咬
    assert result["status"] == "fail"
    assert any(i["code"] == "template.field_missing"
               for i in result["errors"])


def test_write_selfcheck_unavailable_root(tmp_path):
    result = run_write_selfcheck(tmp_path / "x.json", tmp_path / "nope")
    assert result["status"] == "unavailable"


# ---------------------------------------------------------------- CLI

def test_cli_decide_and_handoff(decided_pkg, tmp_path):
    from light_journal_select.cli import main

    root = str(decided_pkg)  # 已 decided 的包直接走 CLI handoff
    fields_path = tmp_path / "fields.json"
    fields_path.write_text(json.dumps(GUIDE_FIELDS), encoding="utf-8")
    files_path = tmp_path / "files.json"
    files_path.write_text(json.dumps(_file_specs(tmp_path)),
                          encoding="utf-8")
    assert main(["handoff", root, "--fields", str(fields_path),
                 "--files", str(files_path),
                 "--date", "2026-10-20"]) == 0
    assert main(["status", root]) == 0
    assert main(["validate", root]) == 0
    # 已 handed_off 后 decide 不许再跑
    assert main(["decide", root, "--candidate", CEA,
                 "--by", "用户", "--reason", "改主意"]) == 1
