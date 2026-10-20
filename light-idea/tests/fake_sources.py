"""七源假响应（fixture）：形状对齐各源真实 API，供 test_novelty 离线 mock。

用法：monkeypatch.setattr(novelty, "_http_get_json", make_fake(fail={...}))
fail 集合里的源名会抛 SourceError（模拟 429/不可达）。

v1.1（IDEA-D02）：新增 dblp / CORE / OpenAIRE 三源。三源默认回空结果
（保 v1.0 既有池规模断言不变）；rich_new=True 时回带数据的载荷：
dblp 与 Crossref 同 DOI（测跨源合并）、CORE 与 S2 同 DOI（测合并）、
OpenAIRE 一条独立新记录（测池增长）。
"""

from __future__ import annotations

from light_idea.novelty import SourceError

# 同一篇工作在 Crossref 与 OpenAlex 以不同 DOI 写法出现（测去重合并）
SHARED_DOI = "10.1000/mae-plant.2024"
S2_DOI = "10.2000/ssleaf.2023"
EPMC_DOI = "10.3000/fewshot.2025"


def crossref_payload():
    return {"message": {"items": [
        {
            "DOI": SHARED_DOI,
            "title": ["Masked autoencoders for plant phenotyping"],
            "author": [{"given": "Jane", "family": "Doe"},
                       {"given": "Wei", "family": "Chen"}],
            "issued": {"date-parts": [[2024]]},
            "container-title": ["Computers and Electronics in Agriculture"],
            "abstract": "<jats:p>Masked autoencoder pretraining on "
                        "greenhouse plant images.</jats:p>",
            "URL": f"https://doi.org/{SHARED_DOI}",
            "type": "journal-article",
        },
        {
            "DOI": "10.1000/unrelated.2020",
            "title": ["Soil moisture sensor calibration"],
            "author": [{"given": "Bob", "family": "Smith"}],
            "issued": {"date-parts": [[2020]]},
            "container-title": ["Sensors"],
            "URL": "https://doi.org/10.1000/unrelated.2020",
            "type": "journal-article",
        },
    ]}}


def openalex_payload():
    return {"results": [
        {
            "id": "https://openalex.org/W123",
            "doi": f"https://doi.org/{SHARED_DOI.upper()}",
            "display_name": "Masked autoencoders for plant phenotyping",
            "authorships": [{"author": {"display_name": "Jane Doe"}},
                            {"author": {"display_name": "Wei Chen"}}],
            "publication_year": 2024,
            "primary_location": {
                "source": {"display_name":
                           "Computers and Electronics in Agriculture"},
                "version": "publishedVersion"},
            "abstract_inverted_index": {
                "Masked": [0], "autoencoder": [1], "pretraining": [2],
                "greenhouse": [3]},
        },
    ]}


def semanticscholar_payload():
    return {"data": [
        {
            "paperId": "s2paper123",
            "title": "Self-supervised learning for leaf disease classification",
            "authors": [{"name": "Ann Lee"}, {"name": "Tom Ray"}],
            "year": 2023,
            "venue": "Plant Methods",
            "externalIds": {"DOI": S2_DOI},
            "abstract": "Self-supervised pretraining reduces label needs "
                        "for leaf disease classification.",
            "url": "https://www.semanticscholar.org/paper/s2paper123",
        },
    ]}


def europepmc_payload():
    return {"resultList": {"result": [
        {
            "source": "MED", "id": "998877",
            "doi": EPMC_DOI,
            "title": "Few-shot tomato disease recognition in the field",
            "authorList": {"author": [{"fullName": "Garcia M"},
                                      {"fullName": "Patel R"}]},
            "pubYear": "2025",
            "journalInfo": {"journal": {"title": "Biosystems Engineering"}},
            "abstractText": "Few-shot recognition of tomato diseases "
                            "under field conditions.",
        },
    ]}}


OPENAIRE_DOI = "10.4000/openaire.graph.2024"


def dblp_payload(rich: bool):
    if not rich:
        return {"result": {"hits": {"@total": "0", "hit": []}}}
    return {"result": {"hits": {"@total": "1", "hit": [{
        "@id": "1",
        "info": {
            "key": "journals/cea/DoeC24",
            "title": "Masked Autoencoders for Plant Phenotyping.",
            "authors": {"author": [{"text": "Jane Doe"},
                                   {"text": "Wei Chen"}]},
            "venue": "Computers and Electronics in Agriculture",
            "year": "2024",
            "doi": SHARED_DOI,
            "ee": f"https://doi.org/{SHARED_DOI}",
            "url": "https://dblp.org/rec/journals/cea/DoeC24",
        },
    }]}}}


def core_payload(rich: bool):
    if not rich:
        return {"totalHits": 0, "results": []}
    return {"totalHits": 1, "results": [{
        "id": 987654,
        "doi": S2_DOI,
        "title": "Self-supervised learning for leaf disease "
                 "classification",
        "authors": [{"name": "Ann Lee"}, {"name": "Tom Ray"}],
        "yearPublished": 2023,
        "abstract": "Self-supervised pretraining reduces label needs "
                    "for leaf disease classification.",
        "publisher": "Springer",
        "downloadUrl": "https://core.ac.uk/works/987654",
    }]}


def openaire_payload(rich: bool):
    if not rich:
        return {"response": {"results": {"result": []}}}
    return {"response": {"results": {"result": [{
        "header": {"dri:objIdentifier": {"$": "openaire____::abc123"}},
        "metadata": {"oaf:entity": {"oaf:result": {
            "title": [{"$": "Graph-based analysis of social "
                            "interactions in laying hen flocks"}],
            "creator": [{"$": "Maria Garcia", "@rank": "1"},
                        {"$": "Ken Watanabe", "@rank": "2"}],
            "dateofacceptance": {"$": "2024-06-01"},
            "description": [{"$": "Interaction graphs reveal social "
                                   "structure in poultry flocks."}],
            "pid": [{"$": OPENAIRE_DOI, "@classid": "doi"}],
            "journal": {"$": "Poultry Science"},
        }}},
    }]}}}


_PAYLOADS = {
    "crossref": crossref_payload,
    "openalex": openalex_payload,
    "semanticscholar": semanticscholar_payload,
    "europepmc": europepmc_payload,
}

_NEW_PAYLOADS = {
    "dblp": dblp_payload,
    "core": core_payload,
    "openaire": openaire_payload,
}

_HOST_TO_SOURCE = {
    "api.crossref.org": "crossref",
    "api.openalex.org": "openalex",
    "api.semanticscholar.org": "semanticscholar",
    "ebi.ac.uk": "europepmc",
    "dblp.org": "dblp",
    "api.core.ac.uk": "core",
    "api.openaire.eu": "openaire",
}


def make_fake(fail: frozenset | set = frozenset(), status: int = 429,
              rich_new: bool = False):
    """返回可替换 novelty._http_get_json 的假函数。

    fail 中的源名每次请求都抛 SourceError(status=status)；
    rich_new=True 时三新源回带数据的载荷（见文件头）。
    """
    def fake(url, params=None, headers=None):
        for host, source in _HOST_TO_SOURCE.items():
            if host in url:
                if source in fail:
                    raise SourceError(source, f"HTTP {status}：模拟限流/不可达",
                                      status=status)
                if source in _PAYLOADS:
                    return _PAYLOADS[source]()
                return _NEW_PAYLOADS[source](rich_new)
        raise AssertionError(f"未预期的 URL：{url}")
    return fake
