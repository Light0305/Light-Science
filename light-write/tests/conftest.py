"""共享夹具：结论卡 / Literature 导出 / 模板记录 / 成品稿件包的构造器。"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from light_write.gates import freeze_contract
from light_write.intake import run_intake
from light_write.project import init_package, load_package, save_manuscript
from light_write.template_reg import register_template
from light_write.util import dump_json, dump_yaml


# ---------------------------------------------------------------- 结论卡

def make_card(status="delivered", review_status=None, claims=None):
    return {
        "kind": "light-analysis/conclusion-card",
        "version": "1.0",
        "analysis_id": "demo-analysis",
        "exported_at": "2026-10-20",
        "status": status,
        "review": {
            "reviewer": None,
            "family": None,
            "review_status": review_status,
            "receipt_id": None,
            "reason": "演示口径" if review_status else None,
        },
        "claims": claims if claims is not None else [
            {"claim_id": "C1", "support": "supported", "grade": "strong",
             "cap_reason": None,
             "text": "Method A outperforms the fixed-threshold baseline.",
             "line_verdicts": {"R-PRED": "positive"}},
            {"claim_id": "C2", "support": "partial", "grade": "suggestive",
             "cap_reason": "仅一行支撑",
             "line_verdicts": {"R-ORA": "positive"}},
        ],
        "number_provenance": [
            {"value": 5.2, "quantity": "effect_size", "verdict_line": "R-PRED#v1",
             "registry_line_id": "R-PRED", "spec_id": "S001",
             "calc_provenance": "welch_effect_and_ci"},
        ],
    }


def make_blocked_card():
    return make_card(
        status="blocked", review_status="REVIEW_UNAVAILABLE",
        claims=[{"claim_id": "C1", "support": "untested", "grade": "insufficient",
                 "cap_reason": "主张含未检验行，强度封顶 insufficient",
                 "line_verdicts": {"R-FIX": "undetermined", "R-NEG": "untested"}}])


# ---------------------------------------------------------------- 文献导出

def make_literature_rows():
    def row(study_id, doi, verification):
        return {
            "study_id": study_id,
            "title": f"Title of {study_id}",
            "authors": ["Ada Lovelace", "Alan Turing"],
            "year": 2024,
            "venue": "Journal of Examples",
            "doi": doi,
            "type": "journal-article",
            "verification": verification,
        }

    return [
        row("ST001", "10.1000/clean.1",
            {"identity_status": "verified", "retraction_status": "clear",
             "checked_at": "2026-10-19T00:00:00+00:00"}),
        row("ST002", "10.1000/retracted.2",
            {"identity_status": "verified", "retraction_status": "retracted",
             "checked_at": "2026-10-19T00:00:00+00:00"}),
        row("ST003", None,
            {"identity_status": "verified", "retraction_status": "clear",
             "checked_at": "2026-10-19T00:00:00+00:00"}),
        row("ST004", "10.1000/unverified.4",
            {"identity_status": "unverifiable", "retraction_status": "unknown",
             "checked_at": "2026-10-19T00:00:00+00:00"}),
        row("ST005", "10.1000/unknown.5",
            {"identity_status": "verified", "retraction_status": "pending",
             "checked_at": "2026-10-19T00:00:00+00:00"}),
    ]


# ---------------------------------------------------------------- 模板记录

def make_record(language="en", verified_at="2026-10-01"):
    return {
        "A": {"record_id": "TPL-DEMO-001", "journal_name": "Journal of Examples",
              "issn": "1234-5678", "eissn": "1234-5679", "publisher": "Example Press",
              "journal_group": None, "template_version": "2026.1",
              "applicable_years": "2026", "journal_language": language},
        "B": {"format_track": "latex", "latex_class": "exart", "class_version": "3.1",
              "options_axis": {"layout": "onecolumn"}, "word_template": None,
              "citation_package": "natbib"},
        "C": {"section_sequence": ["title", "abstract", "introduction", "methods",
                                   "results", "discussion", "declarations",
                                   "references"],
              "abstract_form": "single_paragraph", "keyword_limit": 6,
              "special_sections": []},
        "D": {"word_limit_total": 8000, "word_limit_abstract": 250,
              "page_limit": None, "figure_limit": 8, "table_limit": None,
              "reference_limit": None, "title_char_limit": 120,
              "short_title_char_limit": 50},
        "E": {"style_name": "Example Numeric", "csl_id": "example-numeric",
              "bst_name": "exnum", "citation_style_kind": "numeric"},
        "F": {"figure_submission_mode": "separate_files",
              "figure_formats": ["pdf", "png"], "figure_resolution": "300dpi",
              "caption_position": "below"},
        "G": {"declarations": [
                  {"type": "data_availability", "required": True,
                   "position": "declarations", "field_name": "data_availability"},
                  {"type": "conflict", "required": True,
                   "position": "declarations", "field_name": "conflict"}],
              "ai_policy": {
                  "has_guideline": True, "ai_authorship_banned": True,
                  "disclosure_required": True,
                  "disclosure_content_standard": "工具/版本/用途/节逐项",
                  "disclosure_title": "Declaration of AI Use",
                  "disclosure_wording_template": "The authors used {tool} ({version}) for {purpose}.",
                  "disclosure_positions": ["declarations"],
                  "language_editing_stance": "allowed_with_disclosure",
                  "publisher_conflict": {"conflict": False, "resolution_note": None},
                  "output_validity_evaluation": None}},
        "H": {"source_url": "https://example.org/author-guide",
              "official_channel": "publisher_page", "verified_at": verified_at,
              "review_cycle_days": 180, "verified_by": "light-write census",
              "bundled": "official"},
        "I": {"redistribution": "channel_only",
              "terms_pointer": "https://example.org/terms",
              "purpose_restriction": "submission_only"},
    }


# ---------------------------------------------------------------- 包构造

def write_jsonl(path: Path, rows):
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
                    encoding="utf-8")
    return path


@pytest.fixture()
def upstreams(tmp_path):
    card_path = tmp_path / "conclusion_card.json"
    dump_json(card_path, make_card())
    lit_path = write_jsonl(tmp_path / "candidate_pool.jsonl", make_literature_rows())
    return {"card": card_path, "literature": lit_path, "dir": tmp_path}


@pytest.fixture()
def pkg(tmp_path, upstreams):
    """已 init + intake 的稿件包（英文，delivered 卡）。"""
    root = tmp_path / "ms"
    init_package(root, "Demo Manuscript on Thresholds", "en")
    result = run_intake(root, upstreams["card"], upstreams["literature"])
    return {"root": root, "intake": result, "upstreams": upstreams}


@pytest.fixture()
def record_path(tmp_path):
    path = tmp_path / "template_record.json"
    dump_json(path, make_record())
    return path


def add_assertions(root, n=10, contested_ids=()):
    pkg_data = load_package(root)
    contract = pkg_data["contract"]
    contract["assertions"] = [
        {"assertion_id": f"A{i + 1:02d}",
         "text": f"断言 {i + 1}：终稿满足条件 {i + 1}",
         "checkable_via": "validate + 人工读终稿",
         "status": "contested" if f"A{i + 1:02d}" in contested_ids else "agreed"}
        for i in range(n)
    ]
    dump_yaml(Path(root) / "acceptance_contract.yaml", contract)


def full_pkg(pkg, record_path, contested_ids=()):
    """intake + 模板登记 + 贡献签认 + 合同冻结齐备的包（outlined 门前一步）。"""
    from light_write.intake import confirm_contribution

    register_template(pkg["root"], record_path)
    confirm_contribution(pkg["root"], by="demo author")
    add_assertions(pkg["root"], contested_ids=contested_ids)
    freeze_contract(pkg["root"])
    return pkg


def add_section(root, filename="01-introduction.md", text="Body text.\n",
                section_id="S-intro"):
    root = Path(root)
    (root / "sections" / filename).write_text(text, encoding="utf-8")
    pkg_data = load_package(root)
    manuscript = pkg_data["manuscript"]
    manuscript["sections"] = [
        {"section_id": section_id, "file": filename, "role": "introduction",
         "goal": "确立研究空白", "required_info": ["空白", "主张"], "claim_ids": []},
    ]
    save_manuscript(root, manuscript)
    return filename


# ================================================================ Phase 2

SECTION_TEXTS = {
    "abstract": "This study evaluates threshold adaptation for behaviour "
                "detection in recorded video segments.\n",
    "introduction": None,  # 含主张/数字/引用标记，write_full_sections 拼
    "methods": "We applied the preregistered analysis plan to all recorded "
               "segments and frozen configurations.\n",
    "results": "The oracle variant suggests a possible gain under matched "
               "conditions [claim:C2].\n",
    "discussion": "Limitations include the single-site setting of the study "
                  "and the modest number of segments.\n",
    "declarations": "Data availability: all data are available from the "
                    "authors on request.\n",
}
SECTION_FILES = {
    "abstract": "00-abstract.md", "introduction": "01-introduction.md",
    "methods": "02-methods.md", "results": "03-results.md",
    "discussion": "04-discussion.md", "declarations": "05-declarations.md",
}


def lock_key_for(root, entry_id="ST001"):
    pkg_data = load_package(root)
    for e in (pkg_data["lock"] or {}).get("entries") or []:
        if e.get("entry_id") == entry_id:
            return e["key"]
    raise KeyError(entry_id)


def write_full_sections(root):
    """按模板栏目序列写齐六节并登记；intro 锚 C1+N001+引用，results 锚 C2。"""
    root = Path(root)
    key = lock_key_for(root)
    texts = dict(SECTION_TEXTS)
    texts["introduction"] = (
        "Method A shows a clear improvement over the fixed-threshold "
        f"baseline [claim:C1] with an effect of [num:N001] 5.2 in the "
        f"primary metric [@{key}].\n")
    sections = []
    for role, fname in SECTION_FILES.items():
        (root / "sections" / fname).write_text(texts[role], encoding="utf-8")
        sections.append({"section_id": f"S-{role}", "file": fname,
                         "role": role, "goal": f"{role} 的功能目标",
                         "required_info": ["必备信息"], "claim_ids": []})
    pkg_data = load_package(root)
    pkg_data["manuscript"]["sections"] = sections
    save_manuscript(root, pkg_data["manuscript"])
    return key


def add_numbers(root):
    dump_yaml(Path(root) / "numbers_ledger.yaml", {"numbers": [
        {"num_id": "N001", "value_as_printed": "5.2",
         "trace_ref": "R-PRED#v1", "verdict_ref": "R-PRED",
         "spec_ref": "S001", "calc_provenance": "welch_effect_and_ci",
         "locations": [{"section": "01-introduction.md"}],
         "rounding": "呈现 1 位小数，标准舍入"},
    ]})


def add_checklist(root):
    dump_yaml(Path(root) / "submission_checklist.yaml", {"items": [
        {"item_id": "CHK-01", "source": "journal_requirement",
         "requirement": "引言须报告主要结果", "status": "addressed",
         "tier": "baseline",
         "location": {"kind": "section", "file": "01-introduction.md",
                      "anchor": "Method A shows"}},
        {"item_id": "CHK-02", "source": "reporting_guideline:preregistration",
         "requirement": "方法节须述预注册分析计划", "status": "addressed",
         "tier": "full",
         "location": {"kind": "section", "file": "02-methods.md",
                      "anchor": "preregistered analysis plan"}},
        {"item_id": "CHK-03", "source": "declaration",
         "requirement": "数据可用性声明在场", "status": "addressed",
         "tier": "baseline",
         "location": {"kind": "declarations", "key": "data_availability"}},
    ]})


def set_declarations(root, state="present"):
    pkg_data = load_package(root)
    for key in pkg_data["manuscript"]["declarations"]:
        pkg_data["manuscript"]["declarations"][key] = {"state": state,
                                                       "note": None}
    save_manuscript(root, pkg_data["manuscript"])


def add_use_log(root):
    pkg_data = load_package(root)
    pkg_data["manuscript"]["use_log"] = [
        {"tool": "Claude", "model": "Claude", "model_version": "opus-4.5",
         "purpose": "language editing", "section": "introduction",
         "date": "2026-10-20"},
    ]
    save_manuscript(root, pkg_data["manuscript"])


def set_executor(root, name="Claude Executor", family="executor-family"):
    pkg_data = load_package(root)
    pkg_data["manuscript"]["executor"] = {"name": name, "family": family}
    save_manuscript(root, pkg_data["manuscript"])


def online_records_for(root, entry_id="ST001"):
    """与 lock 条目逐字段一致的在线权威记录（模拟复核接口注入）。"""
    pkg_data = load_package(root)
    for e in (pkg_data["lock"] or {}).get("entries") or []:
        if e.get("entry_id") == entry_id:
            return {entry_id: {
                "exists": True, "title": e["title"],
                "authors": list(e["authors"]), "year": e["year"],
                "venue": e["venue"], "doi": e["doi"], "doi_resolves": True,
                "retraction_state": "clean"}}
    raise KeyError(entry_id)


@pytest.fixture()
def drafted_pkg(pkg, record_path):
    """完整走到 drafted 的包：六节齐 + 数字账 + 清单 + 声明 + use_log。"""
    from light_write.gates import advance

    full_pkg(pkg, record_path)
    root = pkg["root"]
    set_declarations(root)
    add_use_log(root)
    key = write_full_sections(root)
    add_numbers(root)
    add_checklist(root)
    r1 = advance(root)
    assert r1["advanced"] and r1["to"] == "outlined", r1
    r2 = advance(root)
    assert r2["advanced"] and r2["to"] == "drafted", r2
    return {"root": root, "cite_key": key, "intake": pkg["intake"],
            "narrowing": r2.get("lock_narrowing")}


@pytest.fixture()
def audited_pkg(drafted_pkg):
    """drafted + 披露（先于审计，披露文本同为稿件内容）+ 审计全过 → audited。"""
    from light_write.disclose import generate_disclosures
    from light_write.gates import advance
    from light_write.audit import run_audit

    root = drafted_pkg["root"]
    set_executor(root)
    generate_disclosures(root)
    report = run_audit(root, online_records=online_records_for(root))
    assert report["overall"] == "pass", report
    r = advance(root)
    assert r["advanced"] and r["to"] == "audited", r
    drafted_pkg["audit"] = report
    return drafted_pkg
