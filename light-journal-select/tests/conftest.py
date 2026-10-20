"""共享夹具：OpenAlex 假响应 / 假 fetcher / 驱动到各状态的选刊包。

先例路离线测试口径：fetcher 注入 fixture，不碰真实网络；
网络失败路径用抛异常的 fetcher 如实验证 failed 落痕。
"""

from __future__ import annotations

import urllib.parse

import pytest

from light_journal_select.cli import _apply_fingerprint
from light_journal_select.project import init_package
from light_journal_select.verify import apply_verification

Q0 = "turkey behaviour detection"
Q1 = "poultry welfare vision"

CEA = ("https://openalex.org/S1", "Computers and Electronics in Agriculture")
ANIMALS = ("https://openalex.org/S2", "Animals")
POULTRY = ("https://openalex.org/S4", "Poultry Science")
SMALL = ("https://openalex.org/S5", "Small Venue Journal")
OBSCURE = ("https://openalex.org/S3", "Journal of Obscure Results")

VOLUMES = {"S1": 20000, "S2": 8000, "S4": 12000, "S5": 1000, "S3": 500}


def make_work(wid, title, year, doi, source, wtype="article",
              retracted=False):
    sid, sname = source
    return {
        "id": f"https://openalex.org/{wid}",
        "display_name": title,
        "publication_year": year,
        "type": wtype,
        "is_retracted": retracted,
        "doi": f"https://doi.org/{doi}" if doi else None,
        "primary_location": {
            "source": {
                "id": sid,
                "display_name": sname,
                "issn_l": "0000-0001",
                "issn": ["0000-0001"],
                "host_organization_name": "Test Publisher",
                "homepage_url": "https://example.org/journal",
            }
        },
    }


def works_payload(query):
    if query == Q0:
        return {"meta": {"count": 6}, "results": [
            make_work("W1", "Abnormal turkey behaviour detection", 2024,
                      "10.1016/j.compag.2024.001", CEA),
            make_work("W2", "Welfare monitoring in turkeys", 2023,
                      "10.3390/ani13010001", ANIMALS),
            make_work("W3", "Tracking turkeys in barns", 2025,
                      "10.1016/j.compag.2025.002", CEA),
            make_work("W4", "Retracted turkey study", 2024,
                      "10.0000/retracted.1", OBSCURE, retracted=True),
            make_work("W5", "One-off small venue paper", 2022,
                      "10.0000/small.1", SMALL),
            make_work("W6", "Editorial on poultry", 2024,
                      None, OBSCURE, wtype="editorial"),
        ]}
    if query == Q1:
        return {"meta": {"count": 2}, "results": [
            make_work("W7", "Vision for poultry welfare", 2024,
                      "10.3390/ani14010002", ANIMALS),
            make_work("W8", "Poultry vision systems", 2024,
                      "10.3382/ps.2024.001", POULTRY),
        ]}
    return {"meta": {"count": 0}, "results": []}


class FakeFetcher:
    """按 URL 形态分发 fixture：works 检索 / 刊发文量计数。"""

    def __init__(self, fail_queries=(), fail_all=False):
        self.fail_queries = set(fail_queries)
        self.fail_all = fail_all
        self.urls = []

    def __call__(self, url):
        self.urls.append(url)
        if self.fail_all:
            raise ConnectionError("network down (fixture)")
        params = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        if "search" in params:
            query = params["search"][0]
            if query in self.fail_queries:
                raise TimeoutError("timeout (fixture)")
            return works_payload(query)
        filt = params.get("filter", [""])[0]
        for sid, count in VOLUMES.items():
            if f"source.id:{sid}" in filt:
                return {"meta": {"count": count}, "results": []}
        return {"meta": {"count": 0}, "results": []}


FINGERPRINT_PAYLOAD = {
    "manuscript": {
        "abstract": "We detect abnormal behaviour in turkeys from video.",
        "keywords": ["turkey", "behaviour detection", "tracking"],
        "source_ref": None,
    },
    "fingerprint": {
        "field": "agricultural engineering",
        "subfield": "animal behaviour monitoring",
        "study_object": "turkeys",
        "core_problem": "abnormal behaviour detection",
        "contribution_type": "method",
        "audience": "precision livestock farming researchers",
        "methods_role": "core_method_contribution",
    },
    "queries": [Q0, Q1],
    "constraints": {"apc_budget": 2000, "review_cycle_limit": 6},
    "constraints_confirmed": True,
}


@pytest.fixture()
def pkg(tmp_path):
    root = tmp_path / "sel"
    init_package(root, "Abnormal turkey behaviour detection",
                 "en", manuscript_type="research")
    _apply_fingerprint(root, FINGERPRINT_PAYLOAD)
    return root


@pytest.fixture()
def candidates_pkg(pkg):
    from light_journal_select.precedent import run_precedent
    run_precedent(pkg, fetcher=FakeFetcher(), today_str="2026-10-20")
    return pkg


def verified_entry(value, **kw):
    entry = {"value": value,
             "source_url": "https://example.org/metrics",
             "source_year": "2025",
             "queried_at": "2026-10-20",
             "status": "verified",
             "provenance": "official"}
    entry.update(kw)
    return entry


def unconfirmed_entry(source_status="attempted"):
    return {"value": None, "status": "unconfirmed",
            "source_status": source_status}


@pytest.fixture()
def verified_pkg(candidates_pkg):
    records = [
        {"candidate": "Computers and Electronics in Agriculture",
         "source_status": "succeeded",
         "metrics": {
             "quartile_jcr": verified_entry("Q1"),
             "impact_factor": verified_entry(7.9, source_year="2024 JCR"),
             "apc": verified_entry(1500),
             "review_cycle": verified_entry(5),
             "scope_fit": verified_entry("strong",
                                         source_url="https://example.org/aims"),
         }},
        {"candidate": "Animals",
         "source_status": "succeeded",
         "metrics": {
             "quartile_jcr": verified_entry("Q2"),
             "apc": verified_entry(1800),
             "review_cycle": {
                 "value": 9, "status": "verified", "provenance": "crowd",
                 "source_url": "https://example.org/crowd",
                 "source_year": "2026", "queried_at": "2026-10-20",
                 "annotations": {"basis": "LetPub 众包投稿经验",
                                 "sample_size": "未披露",
                                 "queried_at": "2026-10-20"}},
         }},
        {"candidate": "Poultry Science",
         "source_status": "partial",
         "metrics": {"impact_factor": unconfirmed_entry("attempted")}},
    ]
    apply_verification(candidates_pkg, records, today_str="2026-10-20")
    return candidates_pkg
