"""v1.1 增补测试：JS-D01 复合排序 / JS-D02 官网回填 / JS-D03
来源类型过滤 / JS-D06 证据构成段 / JS-06 scope 三项核验 /
JS-08 名单版本年份 / JS-09 白名单证据 / JS-10 录用率与派生
周期 / JS-12 费用组与许可组 / JS-13 政策必查项。

离线口径与既有测试一致：fetcher 注入 fixture，不碰真实网络；
演示回放用 examples/demo-fullrun 的存档 selection 数据
（深拷贝内存回放，不改封版产物）。
"""

from __future__ import annotations

import copy
import urllib.parse
from pathlib import Path

import pytest

from conftest import FakeFetcher, Q0, Q1, make_work, works_payload
from light_journal_select.decide import apply_decide
from light_journal_select.gate import (
    apply_gate, checks_from_name_list, load_name_list,
)
from light_journal_select.gates import GateError
from light_journal_select.handoff import run_handoff
from light_journal_select.precedent import run_precedent
from light_journal_select.project import (
    load_selection, new_candidate, new_selection,
)
from light_journal_select.report import (
    _metric_rows, _ranking_key, assign_tiers, constraint_flags,
    evidence_composition, match_reasons, render_report,
)
from light_journal_select.validate import validate_selection
from light_journal_select.verify import (
    Report, apply_verification, check_metric_entry,
)

CEA = "Computers and Electronics in Agriculture"
ANIMALS = "Animals"
POULTRY = "Poultry Science"
WRITE_ROOT = Path(__file__).resolve().parents[2] / "light-write"
DEMO_PKG = (Path(__file__).resolve().parents[1]
            / "examples" / "demo-fullrun" / "selection-pkg")


def _verified(value, **kw):
    entry = {"value": value, "source_url": "https://example.org/src",
             "source_year": "2026", "queried_at": "2026-10-21",
             "status": "verified", "provenance": "official"}
    entry.update(kw)
    return entry


def _stats(n, cov, rank, rate):
    return {"similar_works_n": n, "rate_per_10k": rate,
            "journal_volume_window": 10000, "volume_status": "succeeded",
            "queries_covered": cov, "best_rank": rank,
            "window": {"from": "2022-01-01", "to": "2026-12-31"},
            "queried_at": "2026-10-21",
            "precedents": [{"title": "P", "year": 2025,
                            "doi": "https://doi.org/10.1/x",
                            "openalex_id": "https://openalex.org/W1"}]}


def _cand(name, stats=None, metrics=None):
    cand = new_candidate(name, "precedent")
    cand["precedent"] = stats
    cand["risk"] = {"level": "clear", "checks": [], "override": None,
                    "evaluated_at": "2026-10-21"}
    if metrics is not None:
        cand["verification"] = {"checked_at": "2026-10-21",
                                 "source_status": "succeeded",
                                 "metrics": metrics}
    return cand


# ------------------------------------------------------------ JS-D01

def test_card_gate_three_prongs():
    sel = {"constraints": {}, "candidates": [
        _cand("Weak One", stats=_stats(1, 1, 41, 270.27)),
        _cand("Rank Rescued", stats=_stats(1, 1, 2, 8.02)),
        _cand("Strong", stats=_stats(3, 1, 9, 0.5)),
    ]}
    assign_tiers(sel)
    by_name = {c["name"]: c for c in sel["candidates"]}
    assert by_name["Weak One"]["tier"] is None
    assert by_name["Weak One"]["ranking"]["card_gate"] is False
    assert by_name["Rank Rescued"]["tier"] is not None
    assert by_name["Strong"]["tier"] is not None


def test_composite_weight_deflates_small_denominator():
    micro = _cand("Micro", stats=_stats(1, 2, 5, 270.27))
    flag = _cand("Flagship", stats=_stats(7, 2, 5, 13.16))
    sel = {"constraints": {}, "candidates": [micro, flag]}
    assign_tiers(sel)
    assert flag["ranking"]["weight"] > micro["ranking"]["weight"]
    ordered = sorted([micro, flag], key=_ranking_key)
    assert ordered[0] is flag  # 覆盖同为 2 式时篇数加权压住率值膨胀


def test_demo_replay_flagship_in_micro_out():
    """演示存档数据回放（JS-D01 验收）：CEA 进卡居首、Gomal 出局。"""
    sel = copy.deepcopy(load_selection(DEMO_PKG))
    assign_tiers(sel)
    carded = [c for c in sel["candidates"] if c.get("tier")]
    names = {c["name"] for c in carded}
    assert CEA in names
    assert "Gomal Journal of Agriculture and Biology" not in names
    assert names == {CEA, "Smart Agricultural Technology", ANIMALS,
                     "Frontiers in Animal Science", "AgriEngineering"}
    ordered = sorted(carded, key=_ranking_key)
    assert ordered[0]["name"] == CEA  # 覆盖 3 式居首
    gomal = next(c for c in sel["candidates"]
                 if "Gomal" in c["name"])
    assert gomal["ranking"]["card_gate"] is False


# ------------------------------------------------------------ JS-D02 / D03 / JS-09 源事实

def _dehydrated_payloads():
    """works 响应去掉 homepage_url（真实脱水形态），Poultry
    改独立 ISSN 以便区分 DOAJ 通道结果。"""
    payloads = {}
    for query in (Q0, Q1):
        payload = copy.deepcopy(works_payload(query))
        for work in payload["results"]:
            src = work["primary_location"]["source"]
            src.pop("homepage_url", None)
            if src["id"].endswith("/S4"):
                src["issn_l"] = "2222-2222"
                src["issn"] = ["2222-2222"]
            if src["id"].endswith("/S1"):
                src["is_in_doaj"] = True
                src["listed_in"] = ["doaj"]
        payloads[query] = payload
    return payloads


class _BackfillFetcher(FakeFetcher):
    def __init__(self, payloads):
        super().__init__()
        self.payloads = payloads

    def __call__(self, url):
        if "/sources/" in url:
            short = url.rsplit("/", 1)[-1]
            if short == "S1":
                return {"homepage_url": "https://cea.example.org/"}
            if short == "S2":
                return {"id": "x"}  # 详情无 homepage → 走 DOAJ
            raise ConnectionError("source detail down (fixture)")
        if "doaj.org" in url:
            if "2222-2222" in url:
                return {"results": []}
            return {"results": [{"bibjson": {"link": [
                {"type": "homepage",
                 "url": "https://animals.example.org/"}]}}]}
        params = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        if "search" in params:
            return self.payloads[params["search"][0]]
        return super().__call__(url)


def test_homepage_backfill_channels(pkg):
    fetcher = _BackfillFetcher(_dehydrated_payloads())
    result = run_precedent(pkg, fetcher=fetcher, today_str="2026-10-21")
    sel = load_selection(pkg)
    by_name = {c["name"]: c for c in sel["candidates"]}
    cea = by_name[CEA]
    assert cea["homepage_url"] == "https://cea.example.org/"
    assert cea["homepage_backfill"]["status"] == "filled"
    assert cea["homepage_backfill"]["channel"] == "openalex_source_detail"
    assert "api_key=" not in cea["homepage_backfill"]["evidence_url"]
    # JS-09：源事实快照（白名单在册证据）随聚合落字
    assert cea["source_facts"]["is_in_doaj"] is True
    assert cea["source_facts"]["listed_in"] == ["doaj"]
    animals = by_name[ANIMALS]
    assert animals["homepage_url"] == "https://animals.example.org/"
    assert animals["homepage_backfill"]["channel"] == "doaj_registry"
    poultry = by_name[POULTRY]
    assert poultry["homepage_url"] is None
    bf = poultry["homepage_backfill"]
    assert bf["status"] == "unconfirmed"  # 全通道失败不猜
    assert [a["channel"] for a in bf["attempts"]] == [
        "openalex_source_detail", "doaj_registry"]
    assert result["homepage_backfill"][POULTRY] == "unconfirmed"
    rep = validate_selection(sel)
    assert not [i for i in rep.errors
                if i["code"].startswith("candidate.backfill")]


def test_repository_source_filtered_with_appendix_note(pkg):
    zenodo = ("https://openalex.org/S9", "Zenodo")
    payload = copy.deepcopy(works_payload(Q0))
    for i in range(3):
        work = make_work(f"WZ{i}", f"Dataset paper {i}", 2025,
                         f"10.5281/zenodo.{i}", zenodo)
        work["primary_location"]["source"]["type"] = "repository"
        payload["results"].append(work)

    class RepoFetcher(FakeFetcher):
        def __call__(self, url):
            params = urllib.parse.parse_qs(
                urllib.parse.urlparse(url).query)
            if params.get("search", [""])[0] == Q0:
                return payload
            return super().__call__(url)

    result = run_precedent(pkg, fetcher=RepoFetcher(),
                           today_str="2026-10-21")
    sel = load_selection(pkg)
    names = {c["name"] for c in sel["candidates"]}
    assert "Zenodo" not in names  # 仓库型来源不以期刊身份入池
    assert result["source_type_excluded"] == ["Zenodo"]
    rows = sel["source_type_exclusions"]
    assert len(rows) == 1 and rows[0]["source_type"] == "repository"
    assert rows[0]["similar_works_n"] == 3
    assign_tiers(sel)
    text = render_report(sel, "2026-10-21")
    assert "来源类型排除（不入期刊候选池，JS-D03）：Zenodo" in text


# ------------------------------------------------------------ JS-D06

def test_evidence_composition_section(verified_pkg):
    clear = [{"condition": "warning_list_hit", "hit": False,
              "source": "official-page", "source_ref": "2026-10-21",
              "checked_at": "2026-10-21", "note": None}]
    names = [c["name"] for c in load_selection(verified_pkg)["candidates"]]
    apply_gate(verified_pkg, {n: clear for n in names},
               today_str="2026-10-21")
    from light_journal_select.report import run_report
    run_report(verified_pkg, today_str="2026-10-21")
    sel = load_selection(verified_pkg)
    comp = sel["evidence_composition"]
    assert comp["tiers"]["challenge"]["journals"] == 1
    assert comp["tiers"]["challenge"]["precedent_works"] == 2
    assert comp["carded_total"] == 3
    text = (verified_pkg / "SELECTION_REPORT.md").read_text(
        encoding="utf-8")
    assert "本轮分档证据构成（JS-D06）" in text
    assert "verified 指标" in text


def test_composition_explains_empty_tier():
    sel = {"constraints": {}, "candidates": [
        _cand("Only Safety", stats=_stats(3, 2, 1, 1.0))]}
    assign_tiers(sel)
    text = render_report(sel, "2026-10-21")
    assert "证据构成不足以支撑" in text and "challenge" in text


# ------------------------------------------------------------ JS-08

def test_name_list_version_year_fields(tmp_path):
    path = tmp_path / "list.csv"
    path.write_text(
        "name,issn,condition,source,version,year\n"
        "Animals,,predatory_list_hit,community-list,v3,2024\n"
        "Poultry Science,,warning_list_hit,cas-warning,2026-01,\n",
        encoding="utf-8")
    name_list = load_name_list(path)
    cands = [{"candidate_id": "J-a", "name": ANIMALS,
              "issn": None, "eissn": None},
             {"candidate_id": "J-b", "name": POULTRY,
              "issn": None, "eissn": None}]
    checks = checks_from_name_list(cands, name_list, "2026-10-21")
    hit_a = next(c for c in checks["J-a"] if c["hit"])
    assert hit_a["list_version"] == "v3" and hit_a["list_year"] == 2024
    hit_b = next(c for c in checks["J-b"] if c["hit"])
    assert hit_b["list_year"] == 2026  # 无 year 列时从 version 解析


def test_name_list_hit_without_version_year_rejected():
    sel = new_selection("T", "en", "research")
    cand = new_candidate(ANIMALS, "precedent")
    cand["risk"] = {"level": "quasi_hard", "override": None,
                    "evaluated_at": "2026-10-21",
                    "checks": [{"condition": "predatory_list_hit",
                                "hit": True, "source": "community-list",
                                "origin": "name_list",
                                "list_version": None, "list_year": None,
                                "checked_at": "2026-10-21"}]}
    sel["candidates"] = [cand]
    rep = validate_selection(sel)
    assert any(i["code"] == "candidate.risk_hit_no_list_version"
               for i in rep.errors)


# ------------------------------------------------------------ JS-06 / JS-09 / JS-10 / JS-12

SCOPE_CHECKS_FULL = {
    item: {"status": "verified",
           "source_url": "https://example.org/journal",
           "queried_at": "2026-10-21"}
    for item in ("recent_publications", "recent_issues", "article_types")}

FEE_GROUP = {"list_price": 2400, "currency": "USD",
             "charge_timing": "after_acceptance",
             "extra_fees": [{"name": "color_figure_fee",
                             "amount": 300, "currency": "USD"}],
             "waiver_available": True, "agreement_coverage": "unknown"}


def test_scope_checks_distinguish_basis(candidates_pkg):
    records = [{"candidate": CEA, "source_status": "succeeded",
                "metrics": {"scope_fit": _verified("strong")},
                "scope_checks": SCOPE_CHECKS_FULL},
               {"candidate": ANIMALS, "source_status": "succeeded",
                "metrics": {"scope_fit": _verified("partial")}}]
    apply_verification(candidates_pkg, records, today_str="2026-10-21")
    sel = load_selection(candidates_pkg)
    by_name = {c["name"]: c for c in sel["candidates"]}
    reasons = " ".join(match_reasons(by_name[CEA]))
    assert "实发核验" in reasons
    reasons_a = " ".join(match_reasons(by_name[ANIMALS]))
    assert "文案核对" in reasons_a  # 只有文案不许冒充实发匹配


def test_scope_checks_verified_needs_triplet(candidates_pkg):
    bad = {"recent_publications": {"status": "verified"}}
    with pytest.raises(GateError):
        apply_verification(
            candidates_pkg,
            [{"candidate": CEA, "source_status": "succeeded",
              "metrics": {}, "scope_checks": bad}],
            today_str="2026-10-21")


def test_indexing_from_aggregator_warns(candidates_pkg):
    result = apply_verification(
        candidates_pkg,
        [{"candidate": CEA, "source_status": "succeeded",
          "metrics": {"indexing": _verified(
              "Scopus 收录", provenance="aggregator")}}],
        today_str="2026-10-21")
    assert any("源头核验" in w for w in result["warnings"])  # JS-09


def test_acceptance_rate_official_only(candidates_pkg):
    with pytest.raises(GateError):
        apply_verification(
            candidates_pkg,
            [{"candidate": CEA, "source_status": "succeeded",
              "metrics": {"acceptance_rate": _verified(
                  0.18, provenance="aggregator")}}],
            today_str="2026-10-21")
    result = apply_verification(
        candidates_pkg,
        [{"candidate": CEA, "source_status": "succeeded",
          "metrics": {"acceptance_rate": _verified(0.18)}}],
        today_str="2026-10-21")
    assert result["verified_candidates"] == [CEA]


def test_derived_cycle_marked_and_not_constraining():
    entry = _verified(12)
    entry["derived"] = True
    rep = Report()
    check_metric_entry("review_cycle", entry, rep, where="t")
    assert any(i["code"] == "metric.derived_no_method"
               for i in rep.errors)  # 派生必须落方法
    entry["derivation"] = "由近 2 年实发文章收稿/录用日期倒推"
    rep = Report()
    check_metric_entry("review_cycle", entry, rep, where="t")
    assert rep.ok
    cand = _cand("Derived Cycle", metrics={"review_cycle": entry})
    flags = constraint_flags(cand, {"review_cycle_limit": 6})
    assert "cycle_over_limit" not in flags  # 派生不与官方同权
    row = next(r for r in _metric_rows(cand) if "review_cycle" in r)
    assert "派生估计" in row


def test_apc_fee_group_full_cycle(candidates_pkg):
    result = apply_verification(
        candidates_pkg,
        [{"candidate": CEA, "source_status": "succeeded",
          "metrics": {"apc": _verified(FEE_GROUP)}}],
        today_str="2026-10-21")
    assert result["verified_candidates"] == [CEA]
    sel = load_selection(candidates_pkg)
    cea = next(c for c in sel["candidates"] if c["name"] == CEA)
    row = next(r for r in _metric_rows(cea) if "| apc |" in r)
    assert "收费时点 录用后" in row and "标价不等于实付" in row
    assert "附加费 color_figure_fee" in row
    flags = constraint_flags(cea, {"apc_budget": 2000})
    assert flags == ["apc_over_budget"]  # 约束读费用组 list_price


def test_apc_fee_group_shape_enforced(candidates_pkg):
    bad = dict(FEE_GROUP)
    del bad["currency"]
    with pytest.raises(GateError):
        apply_verification(
            candidates_pkg,
            [{"candidate": CEA, "source_status": "succeeded",
              "metrics": {"apc": _verified(bad)}}],
            today_str="2026-10-21")


def test_apc_scalar_legacy_warns_not_blocks(candidates_pkg):
    result = apply_verification(
        candidates_pkg,
        [{"candidate": CEA, "source_status": "succeeded",
          "metrics": {"apc": _verified(1500)}}],
        today_str="2026-10-21")
    assert any("费用组" in w for w in result["warnings"])
    sel = load_selection(candidates_pkg)
    cea = next(c for c in sel["candidates"] if c["name"] == CEA)
    row = next(r for r in _metric_rows(cea) if "| apc |" in r)
    assert "费用组未结构化" in row  # 兼容读但卡面显形（J2）


def test_oa_license_block(candidates_pkg):
    block = {"oa_model": "hybrid", "license_type": "CC BY",
             "author_rights_retained": True,
             "self_archiving": "accepted manuscript, 12-month embargo",
             "source_url": "https://example.org/oa-policy",
             "queried_at": "2026-10-21"}
    apply_verification(
        candidates_pkg,
        [{"candidate": CEA, "source_status": "succeeded",
          "metrics": {}, "oa_license": block}],
        today_str="2026-10-21")
    sel = load_selection(candidates_pkg)
    cea = next(c for c in sel["candidates"] if c["name"] == CEA)
    assert cea["oa_license"]["license_type"] == "CC BY"
    bad = dict(block)
    del bad["source_url"]
    with pytest.raises(GateError):
        apply_verification(
            candidates_pkg,
            [{"candidate": ANIMALS, "source_status": "succeeded",
              "metrics": {}, "oa_license": bad}],
            today_str="2026-10-21")


# ------------------------------------------------------------ JS-13 + 全链回放

GUIDE_FIELDS = {
    "A": {"template_version": "test-2026", "applicable_years": [2026]},
    "B": {"format_track": "latex", "latex_class": "elsarticle",
          "class_version": "3.4", "options_axis": ["preprint"],
          "word_template": None, "citation_package": "natbib"},
    "C": {"section_sequence": ["Abstract", "Introduction", "Methods",
                               "Results", "Discussion"],
          "abstract_form": "unstructured", "keyword_limit": 6,
          "special_sections": []},
    "D": {"word_limit_total": 8000, "word_limit_abstract": 250,
          "page_limit": None, "figure_limit": None, "table_limit": None,
          "reference_limit": None, "title_char_limit": 120,
          "short_title_char_limit": 45},
    "E": {"style_name": "Elsevier Harvard", "csl_id": "elsevier-harvard",
          "bst_name": "elsarticle-harv",
          "citation_style_kind": "author-year"},
    "F": {"figure_submission_mode": "separate_files",
          "figure_formats": ["pdf"], "figure_resolution": "300 dpi",
          "caption_position": "below"},
    "G": {"declarations": [
              {"type": "data_availability", "required": True,
               "position": "end", "field_name": "data_availability"}],
          "ai_policy": {
              "has_guideline": True, "ai_authorship_banned": True,
              "disclosure_required": True,
              "disclosure_content_standard": "tool name and purpose",
              "disclosure_title": "Declaration of AI use",
              "disclosure_wording_template": None,
              "disclosure_positions": ["Methods"],
              "language_editing_stance": "allowed with disclosure",
              "publisher_conflict": {"conflict": False,
                                     "resolution_note": None},
              "output_validity_evaluation": None}},
    "I": {"redistribution": "channel_only",
          "terms_pointer": "https://example.org/terms",
          "purpose_restriction": "submission use only"},
}

POLICIES_FULL = [
    {"topic": "ai_use_disclosure", "status": "checked",
     "finding": "要求在 Methods 与致谢披露生成式 AI 工具名与用途",
     "source_url": "https://example.org/ai-policy",
     "accessed_at": "2026-10-21"},
    {"topic": "data_code_availability", "status": "checked",
     "finding": "要求数据可用性声明，数据存公开仓或说明限制",
     "source_url": "https://example.org/data-policy",
     "accessed_at": "2026-10-21"},
]


def _clear():
    return [{"condition": "warning_list_hit", "hit": False,
             "source": "official-page", "source_ref": "checked",
             "checked_at": "2026-10-21", "note": None}]


@pytest.fixture()
def decided_v11(verified_pkg):
    names = [c["name"] for c in load_selection(verified_pkg)["candidates"]]
    apply_gate(verified_pkg, {n: _clear() for n in names},
               today_str="2026-10-21")
    from light_journal_select.report import run_report
    run_report(verified_pkg, today_str="2026-10-21")
    apply_decide(verified_pkg, CEA, decided_by="用户本人",
                 reason="先例最密、scope 对口", date_str="2026-10-21")
    return verified_pkg


def test_handoff_with_policies_full(decided_v11):
    fields = copy.deepcopy(GUIDE_FIELDS)
    fields["policies"] = POLICIES_FULL
    result = run_handoff(decided_v11, fields=fields,
                         write_root=str(WRITE_ROOT),
                         today_str="2026-10-21")
    assert result["self_check"]["write_check"] == "pass"
    sel = load_selection(decided_v11)
    assert sel["status"] == "handed_off"
    assert sel["handoff"]["policy_gaps"] == []
    assert len(sel["policy_checks"]) == 2
    md = (decided_v11 / "journal" / "target" / "handoff.md").read_text(
        encoding="utf-8")
    assert "政策核读（JS-13" in md and "ai_use_disclosure" in md
    rep = validate_selection(sel)
    assert rep.ok


def test_handoff_without_policies_gaps_visible(decided_v11):
    run_handoff(decided_v11, fields=copy.deepcopy(GUIDE_FIELDS),
                today_str="2026-10-21")
    sel = load_selection(decided_v11)
    assert sel["handoff"]["policy_gaps"] == [
        "ai_use_disclosure", "data_code_availability"]
    md = (decided_v11 / "journal" / "target" / "handoff.md").read_text(
        encoding="utf-8")
    assert "政策必查项未覆盖" in md  # 缺项显形，不静默
    rep = validate_selection(sel)
    assert rep.ok  # 警告级，不误伤交接
    assert any(i["code"] == "handoff.policy_gaps" for i in rep.warnings)


def test_handoff_policy_conflict_blocks(decided_v11):
    fields = copy.deepcopy(GUIDE_FIELDS)
    bad = copy.deepcopy(POLICIES_FULL)
    bad[0]["status"] = "conflict"
    bad[0]["finding"] = "该刊禁止 AI 参与写作，本稿情形与之冲突"
    fields["policies"] = bad
    with pytest.raises(GateError) as exc:
        run_handoff(decided_v11, fields=fields, today_str="2026-10-21")
    assert "阻断项" in "；".join(exc.value.gaps)
    assert load_selection(decided_v11)["status"] == "decided"


def test_handoff_policy_item_needs_triplet(decided_v11):
    fields = copy.deepcopy(GUIDE_FIELDS)
    bad = copy.deepcopy(POLICIES_FULL)
    del bad[0]["source_url"]
    fields["policies"] = bad
    with pytest.raises(GateError):
        run_handoff(decided_v11, fields=fields, today_str="2026-10-21")


def test_policy_conflict_counts_in_flags():
    cand = _cand("Conflicted", stats=_stats(3, 2, 1, 1.0), metrics={
        "quartile_jcr": _verified("Q1")})
    cand["policy_checks"] = [
        {"topic": "ai_use_disclosure", "status": "conflict",
         "finding": "冲突", "source_url": "https://example.org/p",
         "accessed_at": "2026-10-21"}]
    sel = {"constraints": {}, "candidates": [cand]}
    assign_tiers(sel)
    assert "policy_conflict" in cand["flags"]
    assert cand["tier"] == "target"  # 冲突封 challenge（JS-13）
    comp = evidence_composition(sel)
    assert comp["tiers"]["target"]["policy_conflicts"] == 1
