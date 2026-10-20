"""LIT-D05 共享检索适配层测试：统一模型、缓存、失败隔离、S2 Key。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from light_literature import searchlayer as sl

FIXTURES = Path(__file__).parent / "fixtures"


def _fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def test_paper_record_roundtrip():
    rec = {
        "source": "crossref", "source_id": "10.1/abc", "doi": "10.1/ABC",
        "title": "  A Title ", "authors": ["Doe J", ""], "year": 2021,
        "venue": "J Test", "type": "journal-article",
        "version_hint": "version_of_record", "abstract": " abs ",
        "url": "https://doi.org/10.1/abc", "retracted_hint": None,
        "queries": ["q1"],
    }
    paper = sl.Paper.from_record(rec)
    out = paper.to_record()
    assert out["doi"] == "10.1/abc"          # DOI 规范化
    assert out["title"] == "A Title"          # 去空白
    assert out["authors"] == ["Doe J"]        # 去空作者
    assert out["abstract"] == "abs"
    assert sl.Paper.from_record(out).to_record() == out


def test_adapters_parse_real_fixtures():
    cr = sl.get_adapter("crossref").parse(
        _fixture("crossref_search_attention.json"), "attention")
    assert cr and all(p.source == "crossref" for p in cr)
    ep = sl.get_adapter("europepmc").parse(
        _fixture("europepmc_search_attention.json"), "attention")
    assert ep and all(p.source == "europepmc" for p in ep)
    ax = sl.get_adapter("arxiv").parse(
        _fixture("arxiv_search_attention.xml"), "attention")
    assert ax and all(p.version_hint == "preprint" for p in ax)


def test_search_all_cache_hit_avoids_network(tmp_path):
    calls = {"n": 0}

    def fake_get(url, params=None, headers=None):
        calls["n"] += 1
        return 200, _fixture("crossref_search_attention.json")

    cache = tmp_path / "cache"
    r1 = sl.search_all(["attention"], sources=("crossref",), per_source=3,
                       cache_dir=cache, get=fake_get)
    assert r1["records"] and calls["n"] == 1 and r1["cache_hits"] == 0

    def dead_get(url, params=None, headers=None):
        raise AssertionError("缓存命中时不许联网")

    r2 = sl.search_all(["attention"], sources=("crossref",), per_source=3,
                       cache_dir=cache, get=dead_get)
    assert r2["cache_hits"] == 1
    assert [r["source_id"] for r in r2["records"]] == \
        [r["source_id"] for r in r1["records"]]


def test_search_all_failure_isolation():
    def fake_get(url, params=None, headers=None):
        if "openalex" in url:
            raise sl.FetchError("模拟 OpenAlex 限流")
        return 200, _fixture("crossref_search_attention.json")

    r = sl.search_all(["attention"], sources=("crossref", "openalex"),
                      per_source=3, get=fake_get)
    assert r["records"], "好源的结果不应被坏源拖掉"
    assert r["per_source"]["crossref"]["ok"] is True
    assert r["per_source"]["openalex"]["ok"] is False
    assert [f["source"] for f in r["failures"]] == ["openalex"]


def test_search_all_unknown_source_rejected():
    with pytest.raises(ValueError):
        sl.search_all(["q"], sources=("nosuch",), get=lambda *a, **k: (200, b""))


def test_s2_key_header_injected_only_when_configured(monkeypatch):
    seen = {}

    def fake_get(url, params=None, headers=None):
        seen.update(headers or {})
        return 200, json.dumps({"data": []}).encode()

    adapter = sl.get_adapter("semanticscholar")
    monkeypatch.delenv(sl.S2_API_KEY_ENV, raising=False)
    adapter.search("q", 1, get=fake_get)
    assert "x-api-key" not in seen

    monkeypatch.setenv(sl.S2_API_KEY_ENV, "test-key-not-real")
    adapter.search("q", 1, get=fake_get)
    assert seen.get("x-api-key") == "test-key-not-real"
    assert sl.s2_api_key_configured() is True
