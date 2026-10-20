"""三期 chain 命令测试：三源假响应（形状对齐真实 API），全程 monkeypatch
chain._http_get_json，禁止真联网。

覆盖：三源邻居按 DOI 合并、方向计数、seed/报告落盘、生长调用并入同一
链、单源失败如实记录、三源全灭报错、CLI 冒烟与项目不存在拦截。
"""

from __future__ import annotations

import json

import pytest

from light_idea import chain
from light_idea.cli import main
from light_idea.novelty import SourceError
from light_idea.project import init_project

SEED_DOI = "10.1000/seed.2025"
REF_A_DOI = "10.1000/ref-a"
CITING_A_DOI = "10.1000/citing-a"


def _openalex_work():
    return {
        "id": "https://openalex.org/W999",
        "doi": f"https://doi.org/{SEED_DOI}",
        "display_name": "Seed paper on poultry tracking",
        "publication_year": 2025,
        "cited_by_count": 42,
        "referenced_works": ["https://openalex.org/W111",
                             "https://openalex.org/W222"],
        "authorships": [{"author": {"display_name": "Jane Doe"}}],
        "primary_location": {"source": {"display_name":
                                        "Computers and Electronics in Agriculture"}},
        "abstract_inverted_index": {"Self-supervised": [0], "tracking": [1]},
    }


def _openalex_work_item(wid, doi, title, year, cited):
    return {
        "id": f"https://openalex.org/{wid}",
        "doi": f"https://doi.org/{doi}",
        "display_name": title,
        "publication_year": year,
        "cited_by_count": cited,
        "authorships": [{"author": {"display_name": "Ann Lee"}}],
        "primary_location": {"source": {"display_name": "Some Journal"}},
        "abstract_inverted_index": {"Abstract": [0], "words": [1]},
    }


def _s2_paper(pid, doi, title, year, cited=0):
    return {"paperId": pid, "title": title, "year": year,
            "venue": "Some Venue", "externalIds": {"DOI": doi},
            "abstract": f"Abstract of {title}",
            "authors": [{"name": "Tom Ray"}], "citationCount": cited}


def make_chain_fake(fail: frozenset | set = frozenset()):
    """按 URL/参数分发的假 _http_get_json。fail 中的源名抛 SourceError。"""
    def fake(url, params=None):
        if "api.openalex.org" in url:
            if "openalex" in fail:
                raise SourceError("openalex", "HTTP 429：模拟限流", status=429)
            if url.endswith("/works") or url == "https://api.openalex.org/works":
                filt = (params or {}).get("filter", "")
                if filt.startswith("openalex_id:"):
                    return {"results": [
                        _openalex_work_item("W111", REF_A_DOI,
                                            "Reference A tracking", 2022, 1500),
                        _openalex_work_item("W222", "10.1000/ref-b",
                                            "Reference B vision", 2021, 30),
                    ]}
                if filt.startswith("cites:"):
                    return {"results": [
                        _openalex_work_item("W333", CITING_A_DOI,
                                            "Citing A followup", 2026, 3)]}
                raise AssertionError(f"未预期的 OpenAlex filter：{filt}")
            return _openalex_work()
        if "api.semanticscholar.org" in url:
            if "semanticscholar" in fail:
                raise SourceError("semanticscholar", "HTTP 429：模拟限流",
                                  status=429)
            if url.endswith("/references"):
                return {"data": [
                    {"citedPaper": _s2_paper("s2a", REF_A_DOI,
                                             "Reference A tracking", 2022, 1500)},
                    {"citedPaper": _s2_paper("s2b", "10.1000/ref-s2",
                                             "S2 only reference", 2020, 5)},
                ]}
            if url.endswith("/citations"):
                return {"data": [
                    {"citingPaper": _s2_paper("s2c", CITING_A_DOI,
                                              "Citing A followup", 2026, 3)}]}
            raise AssertionError(f"未预期的 S2 URL：{url}")
        if "api.crossref.org" in url:
            if "crossref" in fail:
                raise SourceError("crossref", "网络错误：模拟不可达",
                                  status=None)
            return {"message": {
                "DOI": SEED_DOI,
                "title": ["Seed paper on poultry tracking"],
                "author": [{"given": "Jane", "family": "Doe"}],
                "issued": {"date-parts": [[2025]]},
                "container-title": ["Computers and Electronics in Agriculture"],
                "is-referenced-by-count": 42,
                "reference": [
                    {"DOI": REF_A_DOI, "article-title": "Reference A tracking",
                     "year": "2022", "author": "Lee A"},
                    {"DOI": "10.1000/ref-c", "article-title": "Crossref only ref",
                     "year": "2019", "author": "Kim J"},
                    {"article-title": "", "author": ""},  # 残条目应被丢弃
                ],
            }}
        raise AssertionError(f"未预期的 URL：{url}")
    return fake


@pytest.fixture()
def project(tmp_path):
    root = tmp_path / "proj"
    init_project(root, "链测试方向")
    return root


def test_fetch_merges_three_sources(project, monkeypatch):
    monkeypatch.setattr(chain, "_http_get_json", make_chain_fake())
    summary = chain.fetch_chain(project, SEED_DOI)
    assert summary["chain_id"] == chain.make_chain_id(SEED_DOI)
    assert summary["any_source_ok"]
    # 参考文献：ref-a（三源合并）+ ref-b（OpenAlex）+ ref-s2（S2）+ ref-c（Crossref）
    assert summary["counts"]["references"] == 4
    assert summary["counts"]["cited_by"] == 1
    neighbors = chain.load_neighbors(project, summary["chain_id"])
    by_doi = {n["doi"]: n for n in neighbors if n["doi"]}
    ref_a = by_doi[REF_A_DOI]
    assert ref_a["direction"] == "references"
    assert set(ref_a["sources"]) == {"openalex", "semanticscholar", "crossref"}
    assert ref_a["cited_by_count"] == 1500
    citing = by_doi[CITING_A_DOI]
    assert citing["direction"] == "cited_by"
    assert set(citing["sources"]) == {"openalex", "semanticscholar"}
    # 残条目（无题名无 DOI）不入素材
    assert all(n["title"] or n["doi"] for n in neighbors)


def test_fetch_writes_seed_and_report(project, monkeypatch):
    monkeypatch.setattr(chain, "_http_get_json", make_chain_fake())
    summary = chain.fetch_chain(project, SEED_DOI)
    cdir = project / "chains" / summary["chain_id"]
    seed = json.loads((cdir / "seed.json").read_text(encoding="utf-8"))
    assert seed["seed"]["doi"] == SEED_DOI
    assert seed["seed"]["title"] == "Seed paper on poultry tracking"
    assert seed["hops"][0]["is_root"] is True
    report = (cdir / "chain_report.md").read_text(encoding="utf-8")
    assert "链素材" in report and "相关性门" in report


def test_growth_appends_to_same_chain(project, monkeypatch):
    monkeypatch.setattr(chain, "_http_get_json", make_chain_fake())
    first = chain.fetch_chain(project, SEED_DOI)
    total1 = first["total_neighbors_on_disk"]
    # 生长：对某个节点 DOI 再展开，指回同一链（假源对任意 DOI 返回同形数据，
    # 题名/DOI 相同 → 按 hop_of 区分入盘，总数应增加）
    second = chain.fetch_chain(project, REF_A_DOI,
                               chain_id=first["chain_id"], hop_of=REF_A_DOI)
    assert second["chain_id"] == first["chain_id"]
    assert second["total_neighbors_on_disk"] > total1
    neighbors = chain.load_neighbors(project, first["chain_id"])
    assert {n["hop_of"] for n in neighbors} == {SEED_DOI, REF_A_DOI}
    seed = json.loads((project / "chains" / first["chain_id"]
                       / "seed.json").read_text(encoding="utf-8"))
    # 根种子不被生长调用覆盖
    assert seed["seed"]["doi"] == SEED_DOI
    assert len(seed["hops"]) == 2


def test_hop_of_attribution_not_overridable(project, monkeypatch):
    """hop_of 恒为被展开节点：传入错误 hop_of 也不许污染归因
    （三期演示实测教训：生长跳的邻居曾被误记到根种子名下）。"""
    monkeypatch.setattr(chain, "_http_get_json", make_chain_fake())
    chain.fetch_chain(project, SEED_DOI)
    chain.fetch_chain(project, REF_A_DOI,
                      chain_id=chain.make_chain_id(SEED_DOI),
                      hop_of="10.9999/wrong-attribution")
    neighbors = chain.load_neighbors(project, chain.make_chain_id(SEED_DOI))
    assert {n["hop_of"] for n in neighbors} == {SEED_DOI, REF_A_DOI}


def test_single_source_failure_recorded(project, monkeypatch):
    monkeypatch.setattr(chain, "_http_get_json",
                        make_chain_fake(fail={"openalex"}))
    summary = chain.fetch_chain(project, SEED_DOI)
    assert summary["source_status"]["openalex"]["ok"] is False
    assert "429" in summary["source_status"]["openalex"]["error"]
    assert summary["source_status"]["crossref"]["ok"] is True
    # 其余源的邻居仍在
    assert summary["counts"]["references"] >= 2


def test_all_sources_fail_raises(project, monkeypatch):
    monkeypatch.setattr(chain, "_http_get_json", make_chain_fake(
        fail={"openalex", "semanticscholar", "crossref"}))
    with pytest.raises(chain.ChainError):
        chain.fetch_chain(project, SEED_DOI)


def test_cli_chain_smoke_and_missing_project(tmp_path, monkeypatch):
    monkeypatch.setattr(chain, "_http_get_json", make_chain_fake())
    missing = tmp_path / "nope"
    assert main(["chain", str(missing), "--seed-doi", SEED_DOI]) == 1
    root = tmp_path / "proj"
    init_project(root, "CLI 链方向")
    assert main(["chain", str(root), "--seed-doi", SEED_DOI]) == 0
    cid = chain.make_chain_id(SEED_DOI)
    assert (root / "chains" / cid / "neighbors.jsonl").exists()
