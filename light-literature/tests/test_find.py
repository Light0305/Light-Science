"""Find 线测试：多源检索（mock 网络，fixture 为真实 API 响应样本）、
三层去重对账、身份核实状态机、独立撤稿检查、粗筛校验、矩阵硬规则。

网络层 mock 方式：monkeypatch find_mod._get，按 URL/params 路由到
tests/fixtures/ 下的真实响应样本。OpenAlex 与 Semantic Scholar 的成功
响应在本机抓取时被共享 IP 限流（真实错误体存为 *_error_*.json），
其成功路径的字段映射用本文件内构造的小型合成响应覆盖，并在用例名与
注释里标明 synthetic，不冒充真实样本。
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from light_literature import find as find_mod
from light_literature import project as project_mod

FIXTURES = Path(__file__).parent / "fixtures"


def _body(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


class Router:
    """按 (url, params) 路由的 mock _get。未命中的 URL 直接断言失败。"""

    def __init__(self):
        self.crossref_search = (200, _body("crossref_search_attention.json"))
        self.crossref_works: dict[str, tuple[int, bytes]] = {}
        self.crossref_updates: dict[str, bytes] = {}
        self.epmc_doi: dict[str, bytes] = {}
        self.epmc_title = (200, _body("europepmc_search_attention.json"))
        self.epmc_search = (200, _body("europepmc_search_attention.json"))
        self.arxiv = (200, _body("arxiv_search_attention.xml"))
        self.openalex = (429, _body("openalex_error_ratelimit.json"))
        self.s2 = (429, _body("semanticscholar_error_429.json"))
        self.raise_all = False

    def __call__(self, url, params=None, headers=None):
        if self.raise_all:
            raise find_mod.FetchError("模拟网络全断")
        params = params or {}
        if "api.openalex.org" in url:
            return self.openalex
        if "semanticscholar.org" in url:
            return self.s2
        if "export.arxiv.org" in url:
            return self.arxiv
        if "ebi.ac.uk" in url:
            query = params.get("query", "")
            if query.startswith('DOI:"'):
                doi = query[5:-1].lower()
                if doi in self.epmc_doi:
                    return 200, self.epmc_doi[doi]
                return 200, b'{"resultList": {"result": []}}'
            if query.startswith('TITLE:"'):
                return self.epmc_title
            return self.epmc_search
        if "api.crossref.org/works/" in url:
            doi = url.split("/works/", 1)[1].lower()
            if doi in self.crossref_works:
                return self.crossref_works[doi]
            return 404, b"{}"
        if "api.crossref.org/works" in url:
            filt = params.get("filter", "")
            if filt.startswith("updates:"):
                doi = filt[len("updates:"):].lower()
                if doi in self.crossref_updates:
                    return 200, self.crossref_updates[doi]
                return 200, _body("crossref_updates_alphafold2.json")
            return self.crossref_search
        raise AssertionError(f"未预期的 URL：{url}")


@pytest.fixture()
def router(monkeypatch):
    r = Router()
    monkeypatch.setattr(find_mod, "_get", r)
    return r


def _rec(source, source_id, **kw):
    base = {"source": source, "source_id": source_id, "doi": None,
            "title": "", "authors": [], "year": None, "venue": "",
            "type": "", "version_hint": "unknown", "abstract": "",
            "url": "", "retracted_hint": None, "queries": ["q"]}
    base.update(kw)
    return base


def _study(study_id, title, doi, version="version_of_record",
           preprint_only=False, verification=None, authors=None,
           year=2023):
    rec = _rec("crossref", doi or study_id, doi=doi, title=title,
               authors=authors or ["Ann Author"], year=year,
               version_hint=version)
    rec["is_primary"] = True
    rec["version_of"] = None
    return {
        "study_id": study_id, "title": title,
        "authors": authors or ["Ann Author"], "year": year, "venue": "J",
        "doi": doi, "type": "journal-article", "version": version,
        "preprint_only": preprint_only, "needs_review": False,
        "match_basis": "single", "report_count": 1,
        "reports": [[f"crossref:{doi or study_id}"]],
        "merged_from": [f"crossref:{doi or study_id}"],
        "found_by": {"sources": ["crossref"], "queries": ["q"]},
        "primary_record": f"crossref:{doi or study_id}",
        "records": [rec], "verification": verification,
    }


def _verification(identity, retraction):
    return {"identity_status": identity, "retraction_status": retraction,
            "retraction_signals": [], "checked_at": "2026-10-20T00:00:00+00:00",
            "sources": [], "detail": "test"}


# ---------------------------------------------------------------------------
# 解析器（真实 fixture）

def test_parsers_on_real_fixtures(router):
    recs, _ = find_mod._search_crossref("attention is all you need", 3, None)
    assert len(recs) == 3 and all(r["source"] == "crossref" for r in recs)
    recs, _ = find_mod._search_europepmc("attention is all you need", 3, None)
    assert len(recs) == 3 and recs[2]["year"] == 2023
    assert find_mod.surname_of(recs[2]["authors"][0]) == "zhang"
    recs, _ = find_mod._search_arxiv("attention is all you need", 3, None)
    assert len(recs) == 3 and all(
        r["version_hint"] == "preprint" for r in recs)


def test_parsers_openalex_and_s2_synthetic(monkeypatch):
    """OpenAlex / S2 成功响应在本机构建时被限流无法抓样，此处用合成
    响应只验字段映射（含 OpenAlex 倒排摘要还原），不冒充真实样本。"""
    openalex_body = json.dumps({"results": [{
        "id": "https://openalex.org/W1", "doi": "https://doi.org/10.1/abc",
        "display_name": "Synthetic Work", "publication_year": 2020,
        "type": "article",
        "authorships": [{"author": {"display_name": "Ann Author"}}],
        "primary_location": {"version": "publishedVersion",
                             "source": {"display_name": "Journal X"}},
        "abstract_inverted_index": {"Hello": [0], "world": [1]},
    }]}).encode()
    s2_body = json.dumps({"data": [{
        "paperId": "S2ID", "title": "Synthetic Paper",
        "authors": [{"name": "Bob Baker"}], "year": 2021,
        "venue": "Conf Y", "externalIds": {"DOI": "10.2/def"},
        "abstract": "abs", "url": "https://example.invalid/p",
        "publicationTypes": ["JournalArticle"],
    }]}).encode()

    def fake_get(url, params=None, headers=None):
        if "openalex" in url:
            return 200, openalex_body
        return 200, s2_body

    monkeypatch.setattr(find_mod, "_get", fake_get)
    recs, _ = find_mod._search_openalex("q", 1, None)
    assert recs[0]["doi"] == "10.1/abc"
    assert recs[0]["version_hint"] == "version_of_record"
    assert recs[0]["abstract"] == "Hello world"
    recs, _ = find_mod._search_semanticscholar("q", 1, None)
    assert recs[0]["doi"] == "10.2/def" and recs[0]["year"] == 2021


def test_source_failure_raises_fetcherror(router):
    # OpenAlex / S2 在 Router 里返回真实 429 错误体
    with pytest.raises(find_mod.FetchError):
        find_mod._search_openalex("q", 1, None)
    with pytest.raises(find_mod.FetchError):
        find_mod._search_semanticscholar("q", 1, None)


# ---------------------------------------------------------------------------
# 三层去重对账

def test_dedup_preprint_and_vor_become_one_study():
    records = [
        _rec("arxiv", "1706.03762v5", title="Attention Is All You Need",
             authors=["Ashish Vaswani", "Noam Shazeer"], year=2017,
             venue="arXiv", version_hint="preprint"),
        _rec("crossref", "10.1234/nips.2017.7181",
             doi="10.1234/nips.2017.7181",
             title="Attention Is All You Need",
             authors=["Ashish Vaswani", "Noam Shazeer"], year=2017,
             venue="NeurIPS", version_hint="version_of_record",
             abstract="The dominant sequence transduction models..."),
        _rec("openalex", "W2963403868", doi="10.1234/nips.2017.7181",
             title="Attention Is All You Need",
             authors=["Ashish Vaswani"], year=2017, venue="NeurIPS",
             version_hint="version_of_record"),
    ]
    studies = find_mod.dedup_records(records)
    assert len(studies) == 1
    s = studies[0]
    assert s["report_count"] == 2  # arXiv 预印本 + 正式版两个 reports
    assert len(s["records"]) == 3 and len(s["merged_from"]) == 3
    assert s["preprint_only"] is False
    assert s["primary_record"] == "crossref:10.1234/nips.2017.7181"
    by_source = {r["source"]: r for r in s["records"]}
    assert by_source["arxiv"]["version_of"] == "crossref:10.1234/nips.2017.7181"
    assert by_source["crossref"]["is_primary"] is True


def test_dedup_fuzzy_title_merges_with_review_flag():
    common = dict(authors=["Ann Author"], abstract="x")
    records = [
        _rec("arxiv", "1901.00001", title=(
            "A comprehensive survey of deep neural network architectures "
            "for natural language processing tasks"),
            year=2019, version_hint="preprint", **common),
        _rec("crossref", "10.9/survey", doi="10.9/survey", title=(
            "A survey of deep neural network architectures for natural "
            "language processing tasks"),
            year=2021, version_hint="version_of_record", **common),
    ]
    studies = find_mod.dedup_records(records)
    assert len(studies) == 1
    assert studies[0]["needs_review"] is True
    assert studies[0]["match_basis"] == "fuzzy-title"
    assert studies[0]["report_count"] == 2


def test_dedup_distinct_papers_stay_separate():
    records = [
        _rec("crossref", "10.1/a", doi="10.1/a",
             title="Quantum Error Correction with Surface Codes",
             authors=["Ann Author"], year=2020),
        _rec("crossref", "10.1/b", doi="10.1/b",
             title="Photosynthesis Efficiency in Desert Plants",
             authors=["Bob Baker"], year=2021),
    ]
    assert len(find_mod.dedup_records(records)) == 2


def test_dedup_same_doi_same_report():
    records = [
        _rec("crossref", "10.1/a", doi="10.1/a", title="Some Paper",
             authors=["Ann Author"], year=2020),
        _rec("openalex", "W1", doi="https://doi.org/10.1/A",
             title="Some Paper", authors=["Ann Author"], year=2020),
    ]
    studies = find_mod.dedup_records(records)
    assert len(studies) == 1 and studies[0]["report_count"] == 1

# ---------------------------------------------------------------------------
# find 端到端（mock 网络）+ 单源失败不拖垮全程

def test_find_end_to_end_and_source_failures(tmp_path, router):
    proj = tmp_path / "proj"
    stats = find_mod.find(proj, ["attention is all you need"],
                          per_source=3)
    # crossref 3 + europepmc 3 + arxiv 3；openalex 与 s2 限流失败
    assert stats["records"] == 9
    failed_sources = {f["source"] for f in stats["failures"]}
    assert failed_sources == {"openalex", "semanticscholar"}
    assert stats["studies"] >= 1
    pool = find_mod._read_pool(proj)
    assert len(pool) == stats["studies"]
    report = (proj / "Literature" / "检索报告.md").read_text(
        encoding="utf-8")
    assert "失败源" in report and "openalex" in report
    cache = list((proj / "Literature" / ".find-cache").glob("*"))
    assert len(cache) == 3  # 三个成功源各一份原始响应


# ---------------------------------------------------------------------------
# 身份核实状态机 + 撤稿检查

def _route_verified_sources(router):
    router.crossref_works["10.1038/s41586-021-03819-2"] = (
        200, _body("crossref_work_alphafold2.json"))
    router.crossref_updates["10.1038/s41586-021-03819-2"] = _body(
        "crossref_updates_alphafold2.json")
    router.epmc_doi["10.1038/s41586-021-03819-2"] = _body(
        "europepmc_doi_alphafold2.json")


def test_verify_identity_verified_and_clear(tmp_path, router):
    _route_verified_sources(router)
    proj = tmp_path / "proj"
    project_mod.init_project(proj)
    study = _study(
        "ST001", "Highly accurate protein structure prediction with "
        "AlphaFold", "10.1038/s41586-021-03819-2",
        authors=["John Jumper", "Richard Evans"], year=2021)
    find_mod._write_pool(proj, [study])
    stats = find_mod.verify_identity(proj)
    assert stats["verified"] == 1
    v = find_mod._read_pool(proj)[0]["verification"]
    assert v["identity_status"] == "verified"
    assert v["retraction_status"] == "clear"
    assert v["sources"] and v["checked_at"]


def test_verify_identity_retracted_paper(tmp_path, router):
    router.crossref_works["10.1038/nature12968"] = (
        200, _body("crossref_work_nature12968.json"))
    router.crossref_updates["10.1038/nature12968"] = _body(
        "crossref_updates_nature12968.json")
    router.epmc_doi["10.1038/nature12968"] = _body(
        "europepmc_doi_nature12968.json")
    proj = tmp_path / "proj"
    project_mod.init_project(proj)
    study = _study(
        "ST001", "Stimulus-triggered fate conversion of somatic cells "
        "into pluripotency", "10.1038/nature12968",
        authors=["Haruko Obokata", "Teruhiko Wakayama"], year=2014)
    find_mod._write_pool(proj, [study])
    find_mod.verify_identity(proj)
    v = find_mod._read_pool(proj)[0]["verification"]
    assert v["retraction_status"] == "retracted"
    assert any("crossref:update-to:retraction" in s
               for s in v["retraction_signals"])
    assert any("europepmc" in s for s in v["retraction_signals"])
    # 核实失败/撤稿都不删条：候选池仍有这条
    assert len(find_mod._read_pool(proj)) == 1


def test_verify_identity_mismatch(tmp_path, router):
    _route_verified_sources(router)
    proj = tmp_path / "proj"
    project_mod.init_project(proj)
    study = _study(
        "ST001", "Completely unrelated study of soil microbes in "
        "volcanic ash", "10.1038/s41586-021-03819-2",
        authors=["Jane Doe"], year=1999)
    find_mod._write_pool(proj, [study])
    find_mod.verify_identity(proj)
    v = find_mod._read_pool(proj)[0]["verification"]
    assert v["identity_status"] == "mismatch"


def test_verify_identity_unverifiable_when_network_down(tmp_path, router):
    router.raise_all = True
    proj = tmp_path / "proj"
    project_mod.init_project(proj)
    find_mod._write_pool(proj, [_study("ST001", "Anything",
                                       "10.1038/s41586-021-03819-2")])
    stats = find_mod.verify_identity(proj)
    assert stats["unverifiable"] == 1
    v = find_mod._read_pool(proj)[0]["verification"]
    assert v["retraction_status"] == "unknown"


def test_verify_identity_no_doi_via_epmc_title(tmp_path, router):
    proj = tmp_path / "proj"
    project_mod.init_project(proj)
    study = _study(
        "ST001", "Attention is all you need: utilizing attention in "
        "AI-enabled drug discovery.", None,
        authors=["Zhang Y", "Liu C"], year=2023)
    find_mod._write_pool(proj, [study])
    find_mod.verify_identity(proj)
    v = find_mod._read_pool(proj)[0]["verification"]
    assert v["identity_status"] == "verified"


def test_check_retraction_priority_and_clear():
    wakefield = json.loads(_body("europepmc_doi_wakefield.json"))[
        "resultList"]["result"][0]
    out = find_mod.check_retraction(None, wakefield, None)
    # 同时有 retraction 与 expression of concern 信号 → retracted 优先
    assert out["status"] == "retracted"
    alphafold = json.loads(_body("europepmc_doi_alphafold2.json"))[
        "resultList"]["result"][0]
    out = find_mod.check_retraction(None, alphafold, None)
    assert out["status"] == "clear"
    out = find_mod.check_retraction(None, None, None)
    assert out["status"] == "unknown"


# ---------------------------------------------------------------------------
# 粗筛校验

def _fill_screen(proj, decisions: dict[str, str]):
    path = proj / "Literature" / "粗筛表.csv"
    with open(path, "r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
        fields = list(rows[0].keys())
    for row in rows:
        if row["study_id"] in decisions:
            row["decision"] = decisions[row["study_id"]]
            row["reason"] = "按冻结 RQ 判定"
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def test_screen_check_retracted_include_is_error(tmp_path):
    proj = tmp_path / "proj"
    project_mod.init_project(proj)
    studies = [
        _study("ST001", "Retracted Work", "10.1/r",
               verification=_verification("verified", "retracted")),
        _study("ST002", "Clean Work", "10.1/c",
               verification=_verification("verified", "clear")),
        _study("ST003", "Shaky Work", "10.1/s",
               verification=_verification("unverifiable", "unknown")),
    ]
    find_mod._write_pool(proj, studies)
    find_mod.generate_screen(proj)
    assert (proj / "Literature" / "粗筛说明.md").exists()

    _fill_screen(proj, {"ST001": "include", "ST002": "include",
                        "ST003": "include"})
    report = find_mod.check_screen(proj)
    assert report["ok"] is False
    assert any("ST001" in e and "exclude" in e for e in report["errors"])
    assert any("ST003" in w for w in report["warnings"])

    _fill_screen(proj, {"ST001": "exclude"})
    report = find_mod.check_screen(proj)
    assert report["ok"] is True
    assert any("ST003" in w for w in report["warnings"])


def test_screen_check_empty_decision_is_error(tmp_path):
    proj = tmp_path / "proj"
    project_mod.init_project(proj)
    find_mod._write_pool(proj, [
        _study("ST001", "Clean Work", "10.1/c",
               verification=_verification("verified", "clear"))])
    find_mod.generate_screen(proj)
    report = find_mod.check_screen(proj)
    assert report["ok"] is False and report["errors"]


# ---------------------------------------------------------------------------
# 证据矩阵硬规则

def test_matrix_excludes_retracted_and_unverified(tmp_path):
    proj = tmp_path / "proj"
    project_mod.init_project(proj)
    lit = proj / "Literature"
    studies = [
        _study("ST001", "Clean Verified Paper", "10.1/clean",
               verification=_verification("verified", "clear")),
        _study("ST002", "Retracted Paper", "10.1/retracted",
               verification=_verification("verified", "retracted")),
        _study("ST003", "Unverifiable Paper", "10.1/shaky",
               verification=_verification("unverifiable", "unknown")),
        _study("ST004", "Corrected Preprint Only", "10.1/corr",
               version="preprint", preprint_only=True,
               verification=_verification("verified", "corrected")),
        _study("ST005", "Never Checked Paper", "10.1/new",
               verification=None),
    ]
    find_mod._write_pool(proj, studies)
    # 给 ST001 关联一篇已入库论文 + 一条证据行（按 DOI 关联）
    with open(lit / "文献索引.csv", "a", encoding="utf-8",
              newline="") as f:
        csv.writer(f).writerow([
            "clean-paper_abc123", "Clean Verified Paper", "10.1/clean",
            "version_of_record", "0" * 64, 10, "ingested", "2026-10-20"])
    with open(lit / "证据表.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({
            "evidence_id": "E001", "paper_id": "clean-paper_abc123",
            "finding": "主结果显著", "statistic": "p<0.01", "page": 3,
            "quote": "", "supports_claim": "C1",
            "claim_strength": "direct", "limitations": "",
            "note_path": "", "note_anchor": "",
            "created_at": "2026-10-20"}, ensure_ascii=False) + "\n")

    stats = find_mod.generate_matrix(proj)
    text = (lit / "研究证据矩阵.md").read_text(encoding="utf-8")
    body, _, excluded = text.partition("## 排除清单")
    assert stats["body"] == 2 and stats["excluded"] == 3
    assert "主结果显著" in body and "Clean Verified Paper" in body
    assert "Retracted Paper" not in body
    assert "Unverifiable Paper" not in body
    assert "Never Checked Paper" not in body
    # 排除清单三条都在且原因明确（禁止静默丢弃）
    for sid, reason in (("ST002", "已撤稿"), ("ST003", "身份未核实"),
                        ("ST005", "尚未核实")):
        assert sid in excluded and reason in excluded
    # corrected + 仅预印本标记
    assert "⚠ 已更正" in body and "仅预印本" in body
    assert "待精读" in body  # ST004 无证据行


# ---------------------------------------------------------------------------
# CLI 冒烟

def test_cli_find_screen_matrix(tmp_path, router, monkeypatch):
    from light_literature import cli

    proj = tmp_path / "proj"
    assert cli.main(["init", str(proj)]) == 0
    assert cli.main(["find", str(proj), "--query",
                     "attention is all you need", "--per-source",
                     "3"]) == 0
    assert cli.main(["verify-identity", str(proj), "--limit", "2"]) == 0
    assert cli.main(["screen", str(proj)]) == 0
    # 未填 decision 时 check 报错退出 1
    assert cli.main(["screen", "check", str(proj)]) == 1
    assert cli.main(["matrix", str(proj)]) == 0
