"""与 Light-Write 的接口合同（集成验收）：

Phase 2 handoff 将生成的 check-record.json 必须能过 Write 的
check_template_record 校验。本测试把目标记录形态钉在 Write 的
真实校验器上——以 sys.path 路径注入方式调用（跨包导入不做成
运行时依赖）；light-write 不在场时跳过。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

WRITE_ROOT = Path(__file__).resolve().parents[2] / "light-write"

pytestmark = pytest.mark.skipif(
    not (WRITE_ROOT / "light_write").exists(),
    reason="light-write 姊妹包不在场")


@pytest.fixture(scope="module")
def write_validate():
    sys.path.insert(0, str(WRITE_ROOT))
    try:
        from light_write.validate import Report, check_template_record
    finally:
        sys.path.remove(str(WRITE_ROOT))
    return Report, check_template_record


def target_record():
    """Phase 2 handoff 目标形态：九组齐全的目标刊核查记录。"""
    return {
        "A": {"record_id": "TR-2026-001",
              "journal_name": "Computers and Electronics in Agriculture",
              "issn": "0168-1699", "eissn": "1872-7107",
              "publisher": "Elsevier",
              "journal_group": None,
              "template_version": "elsarticle-2026",
              "applicable_years": [2026],
              "journal_language": "en"},
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
              "bst_name": "elsarticle-harv", "citation_style_kind": "author-year"},
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
        "H": {"source_url": "https://example.org/author-guide",
              "official_channel": "journal homepage",
              "verified_at": "2026-10-20", "review_cycle_days": 180,
              "verified_by": "light-journal-select handoff",
              "bundled": "official"},
        "I": {"redistribution": "channel_only",
              "terms_pointer": "https://example.org/terms",
              "purpose_restriction": "submission use only"},
    }


def test_check_record_passes_write_validator(write_validate):
    Report, check_template_record = write_validate
    rep = Report()
    check_template_record(target_record(), rep)
    assert rep.errors == []  # Phase 2 生成的记录必须零 error 过 Write 门


def test_write_validator_actually_bites(write_validate):
    Report, check_template_record = write_validate
    broken = target_record()
    del broken["H"]["verified_at"]          # 必填缺失
    broken["D"] = {}                        # 限额组全空
    broken["G"]["ai_policy"]["disclosure_positions"] = []
    rep = Report()
    check_template_record(broken, rep)
    codes = {i["code"] for i in rep.errors}
    assert "template.field_missing" in codes
    assert "template.limits_empty" in codes
    assert "template.ai_disclosure_positions" in codes
