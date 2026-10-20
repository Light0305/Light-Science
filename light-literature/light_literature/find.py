"""Find 线：多源检索 → 三层去重对账 → 身份核实（含独立撤稿检查）→ 粗筛 → 证据矩阵。

管线出处与取舍见 ../01-literature/deep-read-B.md 综合拼图 [2][3][4][5] 与
REDESIGN-DRAFT.md §3.1。本模块把其中四步落成代码：

- [2] 多源检索：OpenAlex / Crossref / Semantic Scholar / arXiv / Europe PMC
  全部免 Key。单源失败（网络、限流、坏响应）只记入检索报告，不拖垮全程
  （nature academic-search 的源故障独立降级）。
- [3] 三层对账：records（各源原始条目）→ reports（同一书目实体的多源重复）
  → studies（同一研究的多版本，如预印本 + 正式版）。合并全程留痕
  merged_from，study 的主记录（primary）正式版优先。
- [4] 身份核实门 + 撤稿检查（独立一步，在核实门内、粗筛之前）：
  核实失败不删条、只打标（候选层规则，ARIS）；撤稿状态由 Crossref
  updates 关系 + Europe PMC 出版类型/评论更正列表双源判定。
- [5] 粗筛表：判定先行格式（decision 列在 reason 列之前）；
  matrix 生成时执行成稿层硬规则——只有 identity_status=verified 且
  未撤稿的 study 才能进矩阵主体，其余一律进排除清单并注明原因，
  禁止静默丢弃。

真实信号形态说明（2026-10-20 实测，fixture 见 tests/fixtures/）：
- Crossref 的 update-to 挂在「通知」记录（如撤稿声明）上、指向原文 DOI，
  原文记录本身通常没有 update-to；查某 DOI 是否被撤稿/更正要反查
  GET /works?filter=updates:{doi}，读命中记录 update-to[].type。
- Crossref 还会给被撤稿原文的 title 加 "RETRACTED:" 前缀，作为辅助信号。
- Europe PMC 的撤稿信号在 pubTypeList.pubType 含 "Retracted Publication"，
  以及 commentCorrectionList 中 type 为 "Retraction in" /
  "Expression of concern in" / "Correction in" 的条目；个别记录另有
  isRetracted 字段（本模块防御性读取，实测样本中该字段缺失）。
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import unicodedata
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path

import requests

from . import project as project_mod
from .util import literature_dir

# ---------------------------------------------------------------------------
# 常量（阈值集中在此，改动须同步测试与 SKILL.md 说明）

#: 题名 token Jaccard 近似合并阈值（deep-read-B 取舍 5：nature Dedup Engine
#: 用 0.90；我们只在第一作者姓氏相容时才允许它触发 study 层合并，
#: 且靠它合并的 study 一律标 needs_review 进复核队列）。
TITLE_JACCARD_THRESHOLD = 0.9

#: 身份核实时题名相似度阈值：对规范化题名做 difflib 序列比对。
#: 0.85 的取舍：出版方常给题名加副标题/标点差异（比值多在 0.9 以上），
#: 而不同论文题名比值鲜少超过 0.8；0.85 留在两者之间。误判风险见 README。
TITLE_SIM_THRESHOLD = 0.85

#: 年份相容窗口：同一作品跨源年份差 ≤1 视为相容（在线优先 vs 期号年）。
YEAR_TOLERANCE = 1

DEFAULT_SOURCES = ("openalex", "crossref", "semanticscholar", "arxiv",
                   "europepmc")

SCREEN_DECISIONS = ("include", "exclude", "maybe")
SCREEN_COLUMNS = [
    "study_id", "title", "year", "venue", "version", "identity_status",
    "retraction_status", "decision", "reason", "dim_relevance",
    "dim_method", "dim_data", "dim_quality", "dim_access", "dim_risk",
]

_POOL_FILENAME = "候选池.jsonl"
_REPORT_FILENAME = "检索报告.md"
_SCREEN_FILENAME = "粗筛表.csv"
_SCREEN_NOTE_FILENAME = "粗筛说明.md"
_MATRIX_FILENAME = "研究证据矩阵.md"
_CACHE_DIRNAME = ".find-cache"

_HTTP_TIMEOUT = 30


class FetchError(Exception):
    """单源请求失败（网络错误 / 非预期状态码 / 响应不可解析）。"""


# ---------------------------------------------------------------------------
# HTTP 层（测试通过 monkeypatch 本函数实现 mock，禁止测试真联网）

def _get(url: str, params: dict | None = None,
         headers: dict | None = None) -> tuple[int, bytes]:
    """发 GET 请求，返回 (status, body)。网络异常抛 FetchError。

    4xx 不抛（404 对身份核实有语义：DOI 在 Crossref 查无）；5xx 抛
    FetchError（视为该源本次不可用）。
    """
    try:
        resp = requests.get(url, params=params, headers=headers,
                            timeout=_HTTP_TIMEOUT)
    except requests.RequestException as exc:
        raise FetchError(f"网络错误：{exc}") from exc
    if resp.status_code >= 500:
        raise FetchError(f"HTTP {resp.status_code}：{url}")
    return resp.status_code, resp.content


def _get_json(url: str, params: dict | None = None,
              headers: dict | None = None) -> tuple[object, bytes]:
    """GET 并解析 JSON；非 200 或解析失败抛 FetchError。返回 (data, raw)。"""
    status, body = _get(url, params=params, headers=headers)
    if status != 200:
        raise FetchError(f"HTTP {status}：{url}")
    try:
        return json.loads(body.decode("utf-8")), body
    except (ValueError, UnicodeDecodeError) as exc:
        raise FetchError(f"响应不是合法 JSON：{url}（{exc}）") from exc


def _ua(mailto: str | None) -> dict:
    ua = "Light-Literature/0.1 (Find; https://example.invalid/light-literature)"
    if mailto:
        ua += f" (mailto:{mailto})"
    return {"User-Agent": ua}


# ---------------------------------------------------------------------------
# 文本规范化与相似度

def normalize_doi(doi: str | None) -> str | None:
    """DOI 规范化：去 https://doi.org/ 等前缀、转小写、去空白。"""
    if not doi:
        return None
    text = str(doi).strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if text.startswith(prefix):
            text = text[len(prefix):]
    return text.strip() or None


def normalize_title(title: str | None) -> str:
    """题名规范化：NFKD 折叠、转小写、去全部标点、压缩空白。"""
    text = unicodedata.normalize("NFKD", title or "")
    text = text.encode("ascii", "ignore").decode("ascii").lower()
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def title_tokens(title: str | None) -> set[str]:
    return set(normalize_title(title).split())


def jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def title_similarity(t1: str | None, t2: str | None) -> float:
    """规范化题名的 difflib 序列相似度（0–1）。"""
    n1, n2 = normalize_title(t1), normalize_title(t2)
    if not n1 or not n2:
        return 0.0
    return SequenceMatcher(None, n1, n2).ratio()


def surname_of(author: str | None) -> str | None:
    """从作者显示名提取姓氏（规范化小写）。

    兼容三种写法："Family, Given"（逗号前为姓）、"Given Family"（末词
    为姓）、Europe PMC 的 "Family XY"（姓 + 缩写名，末词为 1–2 个字母
    的缩写时取首词为姓）。单名作者返回该名单词。
    """
    if not author:
        return None
    text = str(author).strip()
    if not text:
        return None
    if "," in text:
        surname = text.split(",", 1)[0]
    else:
        tokens = text.split()
        last = tokens[-1].strip(".")
        if len(tokens) >= 2 and len(last) <= 2 and last.isalpha():
            surname = tokens[0]  # "Zhang Y" 式：末词是缩写名，首词为姓
        else:
            surname = tokens[-1]
    surname = unicodedata.normalize("NFKD", surname)
    surname = surname.encode("ascii", "ignore").decode("ascii").lower()
    surname = re.sub(r"[^a-z-]", "", surname)
    return surname or None


def _surnames_compatible(a: str | None, b: str | None) -> bool:
    """姓氏相容：任一侧缺失视为相容（缺信息不作否决证据）。"""
    sa, sb = surname_of(a), surname_of(b)
    if sa is None or sb is None:
        return True
    return sa == sb


def _years_compatible(y1, y2) -> bool:
    if y1 is None or y2 is None:
        return True
    return abs(int(y1) - int(y2)) <= YEAR_TOLERANCE


def _first_author(record: dict) -> str | None:
    authors = record.get("authors") or []
    return authors[0] if authors else None


# ---------------------------------------------------------------------------
# 统一记录 schema 与各源适配器
#
# 记录字段：source / source_id / doi / title / authors / year / venue /
# type / version_hint(preprint|version_of_record|unknown) / abstract /
# url / retracted_hint（源内已知的撤稿线索字符串或 None）。

def _record(source: str, source_id: str, **kw) -> dict:
    rec = {
        "source": source,
        "source_id": str(source_id),
        "doi": normalize_doi(kw.get("doi")),
        "title": (kw.get("title") or "").strip(),
        "authors": [a for a in (kw.get("authors") or []) if a],
        "year": kw.get("year"),
        "venue": (kw.get("venue") or "").strip(),
        "type": kw.get("type") or "",
        "version_hint": kw.get("version_hint") or "unknown",
        "abstract": (kw.get("abstract") or "").strip(),
        "url": kw.get("url") or "",
        "retracted_hint": kw.get("retracted_hint"),
        "queries": list(kw.get("queries") or []),
    }
    return rec


_JATS_TAG_RE = re.compile(r"<[^>]+>")


def _strip_jats(text: str | None) -> str:
    """Crossref 摘要常带 JATS XML 标签，粗暴去标签只留文本。"""
    if not text:
        return ""
    return re.sub(r"\s+", " ", _JATS_TAG_RE.sub(" ", text)).strip()

def _openalex_abstract(inverted: dict | None) -> str:
    """OpenAlex 摘要倒排索引 {词: [位置,...]} 还原为文本。"""
    if not inverted:
        return ""
    positions: dict[int, str] = {}
    for word, idxs in inverted.items():
        for i in idxs:
            positions[i] = word
    return " ".join(positions[i] for i in sorted(positions))


_OPENALEX_VERSION = {
    "publishedVersion": "version_of_record",
    "acceptedVersion": "preprint",
    "submittedVersion": "preprint",
}


def _search_openalex(query: str, n: int, mailto: str | None):
    params = {"search": query, "per-page": n}
    if mailto:
        params["mailto"] = mailto
    data, raw = _get_json("https://api.openalex.org/works", params=params,
                          headers=_ua(mailto))
    records = []
    for w in data.get("results", []):
        loc = w.get("primary_location") or {}
        src = loc.get("source") or {}
        hint = _OPENALEX_VERSION.get(loc.get("version") or "", "unknown")
        if (src.get("display_name") or "").lower() == "arxiv":
            hint = "preprint"
        records.append(_record(
            "openalex", w.get("id", ""),
            doi=w.get("doi"), title=w.get("display_name") or w.get("title"),
            authors=[(a.get("author") or {}).get("display_name")
                     for a in w.get("authorships", [])],
            year=w.get("publication_year"),
            venue=src.get("display_name"),
            type=w.get("type") or "",
            version_hint=hint,
            abstract=_openalex_abstract(w.get("abstract_inverted_index")),
            url=(w.get("doi") and f"https://doi.org/{normalize_doi(w['doi'])}")
                or w.get("id"),
            queries=[query],
        ))
    return records, raw


def _crossref_year(item: dict) -> int | None:
    for key in ("published-print", "published-online", "published",
                "issued", "created"):
        parts = ((item.get(key) or {}).get("date-parts") or [[]])[0]
        if parts and isinstance(parts[0], int):
            return parts[0]
    return None


def _crossref_authors(item: dict) -> list[str]:
    out = []
    for a in item.get("author", []) or []:
        name = " ".join(x for x in (a.get("given"), a.get("family")) if x)
        out.append(name or a.get("name") or "")
    return out


def _crossref_retraction_hint(item: dict) -> str | None:
    """从 Crossref 记录本体提取撤稿线索（update-to 指向他人不算自身被撤，
    只认 title 的 RETRACTED 前缀——真正的被撤判定在撤稿检查步反查）。"""
    title = (item.get("title") or [""])[0]
    if title.strip().lower().startswith("retracted"):
        return "crossref:title-retracted-prefix"
    return None


def _search_crossref(query: str, n: int, mailto: str | None):
    params = {"query.bibliographic": query, "rows": n}
    if mailto:
        params["mailto"] = mailto
    data, raw = _get_json("https://api.crossref.org/works", params=params,
                          headers=_ua(mailto))
    records = []
    for item in (data.get("message") or {}).get("items", []):
        records.append(_record(
            "crossref", item.get("DOI", ""),
            doi=item.get("DOI"),
            title=(item.get("title") or [""])[0],
            authors=_crossref_authors(item),
            year=_crossref_year(item),
            venue=(item.get("container-title") or [""])[0],
            type=item.get("type") or "",
            version_hint="version_of_record"
            if item.get("type") in ("journal-article", "proceedings-article",
                                    "book-chapter")
            else "unknown",
            abstract=_strip_jats(item.get("abstract")),
            url=item.get("URL"),
            retracted_hint=_crossref_retraction_hint(item),
            queries=[query],
        ))
    return records, raw


def _search_semanticscholar(query: str, n: int, mailto: str | None):
    params = {
        "query": query, "limit": n,
        "fields": "title,authors,year,venue,externalIds,abstract,url,"
                  "publicationTypes",
    }
    data, raw = _get_json(
        "https://api.semanticscholar.org/graph/v1/paper/search",
        params=params, headers=_ua(mailto))
    records = []
    for p in data.get("data", []) or []:
        ext = p.get("externalIds") or {}
        venue = p.get("venue") or ""
        hint = "preprint" if venue.lower().startswith("arxiv") else "unknown"
        records.append(_record(
            "semanticscholar", p.get("paperId", ""),
            doi=ext.get("DOI"),
            title=p.get("title"),
            authors=[a.get("name") for a in p.get("authors", []) or []],
            year=p.get("year"), venue=venue,
            type=",".join(p.get("publicationTypes") or []),
            version_hint=hint,
            abstract=p.get("abstract"),
            url=p.get("url"),
            queries=[query],
        ))
    return records, raw


_ARXIV_NS = {"atom": "http://www.w3.org/2005/Atom",
             "arxiv": "http://arxiv.org/schemas/atom"}


def _search_arxiv(query: str, n: int, mailto: str | None):
    params = {"search_query": f"all:{query}", "start": 0, "max_results": n}
    status, body = _get("https://export.arxiv.org/api/query", params=params,
                        headers=_ua(mailto))
    if status != 200:
        raise FetchError(f"HTTP {status}：arXiv API")
    try:
        root = ET.fromstring(body.decode("utf-8"))
    except (ET.ParseError, UnicodeDecodeError) as exc:
        raise FetchError(f"arXiv 响应不是合法 XML（{exc}）") from exc
    records = []
    for entry in root.findall("atom:entry", _ARXIV_NS):
        def _text(tag):
            el = entry.find(tag, _ARXIV_NS)
            return (el.text or "").strip() if el is not None else ""
        full_id = _text("atom:id")
        arxiv_id = full_id.rsplit("/", 1)[-1] if full_id else ""
        published = _text("atom:published")
        doi = _text("arxiv:doi") or None
        records.append(_record(
            "arxiv", arxiv_id,
            doi=doi,
            title=re.sub(r"\s+", " ", _text("atom:title")),
            authors=[(a.findtext("atom:name", "", _ARXIV_NS) or "").strip()
                     for a in entry.findall("atom:author", _ARXIV_NS)],
            year=int(published[:4]) if published[:4].isdigit() else None,
            venue="arXiv",
            type="preprint",
            version_hint="preprint",
            abstract=re.sub(r"\s+", " ", _text("atom:summary")),
            url=full_id,
            queries=[query],
        ))
    return records, body


def _epmc_retraction_hints(res: dict) -> tuple[str | None, list[str]]:
    """从 Europe PMC 单条结果提取撤稿信号，返回 (retracted_hint, signals)。

    signals 是撤稿检查步用的分类信号（retracted/concern/corrected 前缀）。
    """
    signals: list[str] = []
    pub_types = (res.get("pubTypeList") or {}).get("pubType") or []
    if any("retract" in str(t).lower() for t in pub_types):
        signals.append("retracted:europepmc:pubtype-retracted-publication")
    if str(res.get("isRetracted") or "").upper() == "Y":
        signals.append("retracted:europepmc:isRetracted=Y")
    corrections = (res.get("commentCorrectionList") or {}).get(
        "commentCorrection") or []
    for c in corrections:
        ctype = str(c.get("type") or "").lower()
        if "retraction" in ctype or "withdrawal" in ctype:
            signals.append("retracted:europepmc:commentCorrection:retraction-in")
        elif "expression of concern" in ctype:
            signals.append(
                "concern:europepmc:commentCorrection:expression-of-concern-in")
        elif "correction" in ctype or "erratum" in ctype:
            signals.append("corrected:europepmc:commentCorrection:correction-in")
    hint = ("europepmc:" + ";".join(s.split(":", 1)[1] for s in signals)
            if signals else None)
    return hint, signals


def _epmc_record(res: dict, query: str | None = None) -> dict:
    hint, _signals = _epmc_retraction_hints(res)
    authors = []
    for a in (res.get("authorList") or {}).get("author", []) or []:
        authors.append(a.get("fullName") or "")
    journal = ((res.get("journalInfo") or {}).get("journal") or {}).get(
        "title") or ""
    year = res.get("pubYear")
    return _record(
        "europepmc", f"{res.get('source', '')}:{res.get('id', '')}",
        doi=res.get("doi"),
        title=res.get("title"),
        authors=authors,
        year=int(year) if str(year).isdigit() else None,
        venue=journal,
        type=",".join((res.get("pubTypeList") or {}).get("pubType") or []),
        version_hint="unknown",
        abstract=res.get("abstractText"),
        url=(res.get("doi")
             and f"https://doi.org/{normalize_doi(res['doi'])}")
            or f"https://europepmc.org/article/{res.get('source')}/{res.get('id')}",
        retracted_hint=hint,
        queries=[query] if query else [],
    )


def _search_europepmc(query: str, n: int, mailto: str | None):
    params = {"query": query, "format": "json", "resultType": "core",
              "pageSize": n}
    data, raw = _get_json(
        "https://www.ebi.ac.uk/europepmc/webservices/rest/search",
        params=params, headers=_ua(mailto))
    records = [_epmc_record(r, query)
               for r in (data.get("resultList") or {}).get("result", [])]
    return records, raw


_SEARCHERS = {
    "openalex": _search_openalex,
    "crossref": _search_crossref,
    "semanticscholar": _search_semanticscholar,
    "arxiv": _search_arxiv,
    "europepmc": _search_europepmc,
}


# ---------------------------------------------------------------------------
# 三层对账：records → reports → studies

class _UnionFind:
    def __init__(self, n: int):
        self.parent = list(range(n))

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


def _same_report(a: dict, b: dict) -> bool:
    """reports 层合并规则：同一书目实体的多源重复。

    L1：DOI 规范化后相同 → 合并。
    L2a：无 DOI 路径——题名规范化精确相同 + 第一作者姓氏相容 + 年份相容。
    （有 DOI 但 DOI 不同绝不在本层合并：那是两个版本，留给 studies 层。）
    """
    da, db = a.get("doi"), b.get("doi")
    if da and db:
        return da == db
    if normalize_title(a.get("title")) != normalize_title(b.get("title")):
        return False
    if not normalize_title(a.get("title")):
        return False
    # 预印本与正式版是同一 study 的两个 reports，绝不是同一 report——
    # 否则 arXiv 记录会被误并进期刊版的 report 里，版本关系就丢了。
    if {a.get("version_hint"), b.get("version_hint")} == {
            "preprint", "version_of_record"}:
        return False
    return (_surnames_compatible(_first_author(a), _first_author(b))
            and _years_compatible(a.get("year"), b.get("year")))


def _same_study(a: dict, b: dict, fuzzy_marks: set) -> bool:
    """studies 层合并规则：同一研究的不同版本（预印本/正式版等）。

    题名规范化精确相同，或 token Jaccard ≥ 阈值（TITLE_JACCARD_THRESHOLD）；
    两种情况都要求第一作者姓氏相容。靠 Jaccard 近似命中的合并把 pair
    记入 fuzzy_marks，study 标 needs_review（deep-read-B 取舍 5：
    模糊题名匹配进复核队列，不静默自动判重）。
    """
    if not _surnames_compatible(_first_author(a), _first_author(b)):
        return False
    na, nb = normalize_title(a.get("title")), normalize_title(b.get("title"))
    if na and na == nb:
        return True
    if jaccard(title_tokens(a.get("title")),
               title_tokens(b.get("title"))) >= TITLE_JACCARD_THRESHOLD:
        fuzzy_marks.add((id(a), id(b)))
        return True
    return False


_PRIMARY_SOURCE_RANK = {"crossref": 0, "openalex": 1, "europepmc": 2,
                        "semanticscholar": 3, "arxiv": 4}


def _primary_score(rec: dict) -> tuple:
    """主记录择优（越小越优先）：正式版 > 有 DOI > 有摘要 > 源权威序。"""
    return (
        0 if rec.get("version_hint") == "version_of_record" else 1,
        0 if rec.get("doi") else 1,
        0 if rec.get("abstract") else 1,
        _PRIMARY_SOURCE_RANK.get(rec.get("source"), 9),
    )


def dedup_records(records: list[dict]) -> list[dict]:
    """三层对账主函数：返回 studies 列表（结构见模块 docstring）。

    每个 study 保留全部 records 并给出 reports 分组（record key 列表）、
    merged_from（全部 "source:source_id"）、主记录标记与非主记录的
    version_of 指向。合并依据（exact/fuzzy）与 needs_review 一并落痕。
    """
    n = len(records)
    if n == 0:
        return []
    # 入口先统一规范化 DOI（不信任调用方已规范化，保证 L1 比较可靠）
    records = [{**r, "doi": normalize_doi(r.get("doi"))} for r in records]
    # 第一层：records → reports
    uf = _UnionFind(n)
    for i in range(n):
        for j in range(i + 1, n):
            if _same_report(records[i], records[j]):
                uf.union(i, j)
    report_groups: dict[int, list[int]] = {}
    for i in range(n):
        report_groups.setdefault(uf.find(i), []).append(i)
    reports = list(report_groups.values())

    # 第二层：reports → studies（以每组第一条记录为代表做两两判定）
    fuzzy_marks: set = set()
    uf2 = _UnionFind(len(reports))
    for i in range(len(reports)):
        for j in range(i + 1, len(reports)):
            if _same_study(records[reports[i][0]], records[reports[j][0]],
                           fuzzy_marks):
                uf2.union(i, j)
    study_groups: dict[int, list[int]] = {}
    for i in range(len(reports)):
        study_groups.setdefault(uf2.find(i), []).append(i)

    studies = []
    for s_idx, (_, report_idx_list) in enumerate(
            sorted(study_groups.items(), key=lambda kv: min(kv[1])), start=1):
        member_reports = [reports[i] for i in sorted(report_idx_list)]
        members = [records[i] for grp in member_reports for i in grp]
        primary = min(members, key=_primary_score)
        primary_key = f"{primary['source']}:{primary['source_id']}"
        fuzzy = any(id(r) in {x for pair in fuzzy_marks for x in pair}
                    for r in members) and len(member_reports) > 1
        out_records = []
        for rec in members:
            rec = dict(rec)
            key = f"{rec['source']}:{rec['source_id']}"
            rec["is_primary"] = rec is primary or key == primary_key
            # version_of：非主记录指向主记录，表示「同一 study 的另一版本」
            rec["version_of"] = None if key == primary_key else primary_key
            out_records.append(rec)
        out_records.sort(key=lambda r: (not r["is_primary"],
                                        _primary_score(r)))
        studies.append({
            "study_id": f"ST{s_idx:03d}",
            "title": primary.get("title") or "",
            "authors": primary.get("authors") or [],
            "year": primary.get("year"),
            "venue": primary.get("venue") or "",
            "doi": primary.get("doi"),
            "type": primary.get("type") or "",
            "version": primary.get("version_hint") or "unknown",
            "preprint_only": all(
                r.get("version_hint") == "preprint" for r in members),
            "needs_review": bool(fuzzy),
            "match_basis": ("fuzzy-title" if fuzzy else
                            "multi-record" if len(members) > 1 else "single"),
            "report_count": len(member_reports),
            "reports": [[f"{records[i]['source']}:{records[i]['source_id']}"
                         for i in grp] for grp in member_reports],
            "merged_from": [f"{r['source']}:{r['source_id']}"
                            for r in out_records],
            "found_by": {
                "sources": sorted({r["source"] for r in members}),
                "queries": sorted({q for r in members
                                   for q in r.get("queries", [])}),
            },
            "primary_record": primary_key,
            "records": out_records,
            "verification": None,
        })
    return studies


# ---------------------------------------------------------------------------
# 候选池读写

def _pool_path(project_dir: Path) -> Path:
    return literature_dir(project_dir) / _POOL_FILENAME


def _read_pool(project_dir: Path) -> list[dict]:
    path = _pool_path(project_dir)
    if not path.exists():
        raise FileNotFoundError(
            f"候选池不存在：{path}（先运行 find）")
    studies = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            studies.append(json.loads(line))
    return studies


def _write_pool(project_dir: Path, studies: list[dict]) -> Path:
    path = _pool_path(project_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for s in studies:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")
    return path


# ---------------------------------------------------------------------------
# find：多源检索 + 对账 + 报告

def find(project_dir: Path, queries: list[str],
         sources: tuple[str, ...] = DEFAULT_SOURCES,
         per_source: int = 10, mailto: str | None = None) -> dict:
    """执行多源检索并落盘候选池与检索报告，返回统计 dict。

    单源失败不中断：失败源与原因写入报告「失败源」一节并体现在返回的
    failures 里。各源原始响应写入 Literature/.find-cache/ 以便复现。
    """
    project_dir = Path(project_dir)
    if not queries:
        raise ValueError("至少需要一个 --query")
    unknown = [s for s in sources if s not in _SEARCHERS]
    if unknown:
        raise ValueError(f"未知检索源：{unknown}（可选：{list(_SEARCHERS)}）")
    project_mod.init_project(project_dir)
    lit = literature_dir(project_dir)
    cache_dir = lit / _CACHE_DIRNAME
    cache_dir.mkdir(parents=True, exist_ok=True)

    all_records: list[dict] = []
    per_source_stats: dict[str, dict] = {}
    failures: list[dict] = []
    for source in sources:
        stat = {"hits": 0, "ok": True, "error": None}
        for query in queries:
            try:
                records, raw = _SEARCHERS[source](query, per_source, mailto)
            except FetchError as exc:
                stat["ok"] = False
                stat["error"] = str(exc)
                failures.append({"source": source, "query": query,
                                 "error": str(exc)})
                continue
            stat["hits"] += len(records)
            all_records.extend(records)
            digest = hashlib.sha1(
                f"{source}|{query}|{per_source}".encode("utf-8")).hexdigest()[:10]
            ext = "xml" if source == "arxiv" else "json"
            (cache_dir / f"{source}__{digest}.{ext}").write_bytes(raw)
        per_source_stats[source] = stat

    studies = dedup_records(all_records)
    report_total = sum(s["report_count"] for s in studies)
    _write_pool(project_dir, studies)

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    lines = [
        "# 检索报告",
        "",
        f"- 生成时间（UTC）：{now}",
        f"- 查询式：{'；'.join(queries)}",
        f"- 每源上限：{per_source}",
        "",
        "## 各源命中",
        "",
        "| 源 | 状态 | 命中条数 |",
        "|---|---|---|",
    ]
    for source in sources:
        st = per_source_stats[source]
        status = "ok" if st["ok"] else f"失败：{st['error']}"
        lines.append(f"| {source} | {status} | {st['hits']} |")
    lines += [
        "",
        "## 去重对账（三层）",
        "",
        f"- records（各源原始条目）：{len(all_records)}",
        f"- reports（同一书目实体的多源重复合并后）：{report_total}",
        f"- studies（同一研究多版本合并后）：{len(studies)}",
        "",
        "## 合并样例（多记录 study，最多 10 个）",
        "",
    ]
    merged = [s for s in studies if len(s["records"]) > 1]
    if merged:
        for s in merged[:10]:
            lines.append(
                f"- {s['study_id']} 《{s['title']}》："
                f"{len(s['records'])} 条 records / {s['report_count']} 个 "
                f"reports，来源 {'、'.join(s['merged_from'])}，"
                f"主记录 {s['primary_record']}，合并依据 {s['match_basis']}")
    else:
        lines.append("- （无多记录合并）")
    review = [s for s in studies if s.get("needs_review")]
    lines += ["", "## 模糊合并复核队列（题名 Jaccard 近似合并）", ""]
    if review:
        for s in review:
            lines.append(f"- {s['study_id']} 《{s['title']}》")
    else:
        lines.append("- （无）")
    lines += ["", "## 失败源", ""]
    if failures:
        for f_ in failures:
            lines.append(f"- {f_['source']}（查询：{f_['query']}）：{f_['error']}")
    else:
        lines.append("- （无）")
    lines.append("")
    (lit / _REPORT_FILENAME).write_text("\n".join(lines), encoding="utf-8")

    return {
        "queries": queries,
        "sources": list(sources),
        "per_source_hits": {s: per_source_stats[s]["hits"] for s in sources},
        "failures": failures,
        "records": len(all_records),
        "reports": report_total,
        "studies": len(studies),
        "needs_review": len(review),
        "pool": str(_pool_path(project_dir)),
        "report": str(lit / _REPORT_FILENAME),
    }


# ---------------------------------------------------------------------------
# 身份核实 + 撤稿检查（独立一步）
#
# 与 nature ref-verifier 的一处有意偏离：Crossref 对 DOI 返回 404 不直接
# 判 mismatch——DataCite 注册的 DOI（如 arXiv 的 10.48550/...）本就不在
# Crossref 里。404 时先用 Europe PMC 兜底查 DOI；两边都查无才判
# unverifiable（查无 ≠ 张冠李戴）。mismatch 只用于「该 DOI/题名能查到
# 权威记录，但记录与候选条目对不上」。

def _crossref_work(doi: str, mailto: str | None) -> tuple[int, dict | None]:
    """按 DOI 取 Crossref 记录；返回 (status, message|None)。"""
    status, body = _get(f"https://api.crossref.org/works/{doi}",
                        headers=_ua(mailto))
    if status == 404:
        return 404, None
    if status != 200:
        raise FetchError(f"Crossref 按 DOI 查询返回 HTTP {status}")
    try:
        return 200, json.loads(body.decode("utf-8")).get("message") or {}
    except (ValueError, UnicodeDecodeError) as exc:
        raise FetchError(f"Crossref 响应解析失败（{exc}）") from exc


def _crossref_best_bibliographic(title: str, mailto: str | None) -> dict | None:
    """无 DOI 时用题名查 Crossref，返回题名相似度最高的一条（或 None）。"""
    params = {"query.bibliographic": title, "rows": 5}
    if mailto:
        params["mailto"] = mailto
    data, _raw = _get_json("https://api.crossref.org/works", params=params,
                           headers=_ua(mailto))
    items = (data.get("message") or {}).get("items", [])
    if not items:
        return None
    return max(items, key=lambda it: title_similarity(
        title, (it.get("title") or [""])[0]))


def _epmc_search(query: str, mailto: str | None,
                 page_size: int = 5) -> list[dict]:
    """Europe PMC 原始结果列表（resultType=core）。"""
    params = {"query": query, "format": "json", "resultType": "core",
              "pageSize": page_size}
    data, _raw = _get_json(
        "https://www.ebi.ac.uk/europepmc/webservices/rest/search",
        params=params, headers=_ua(mailto))
    return (data.get("resultList") or {}).get("result", []) or []


def _epmc_by_doi(doi: str, mailto: str | None) -> dict | None:
    results = _epmc_search(f'DOI:"{doi}"', mailto, page_size=3)
    for r in results:
        if normalize_doi(r.get("doi")) == doi:
            return r
    return results[0] if results else None


def _epmc_by_title(title: str, mailto: str | None) -> dict | None:
    """按题名查 Europe PMC，返回相似度最高的转换记录。

    命中记录额外带 `_epmc_raw`（原始结果 dict），供撤稿检查步直接读
    pubTypeList / commentCorrectionList，不必为撤稿再查一次。
    """
    safe = title.replace('"', " ")
    results = _epmc_search(f'TITLE:"{safe}"', mailto, page_size=5)
    if not results:
        return None
    pairs = [(r, _epmc_record(r)) for r in results]
    raw_best, best = max(
        pairs, key=lambda p: title_similarity(title, p[1]["title"]))
    if title_similarity(title, best["title"]) <= 0:
        return None
    best["_epmc_raw"] = raw_best
    return best


def _compare_identity(candidate: dict, authoritative: dict) -> dict:
    """字段级比对：题名相似度 / 第一作者姓氏 / 年份±容差。

    返回 {title_sim, author_ok, year_ok}，无法比对的字段为 None
    （缺字段不作否决证据——K-Dense 三态精神：查无与不符要分开）。
    """
    cand_title = candidate.get("title") or ""
    auth_title = authoritative.get("title") or ""
    if isinstance(auth_title, list):
        auth_title = auth_title[0] if auth_title else ""
    sim = title_similarity(cand_title, auth_title)
    cand_authors = candidate.get("authors") or []
    auth_authors = authoritative.get("authors")
    if auth_authors is None and "author" in authoritative:
        auth_authors = _crossref_authors(authoritative)
    author_ok = None
    if cand_authors and auth_authors:
        author_ok = _surnames_compatible(cand_authors[0], auth_authors[0])
    cand_year = candidate.get("year")
    auth_year = authoritative.get("year")
    if auth_year is None and isinstance(authoritative, dict):
        auth_year = _crossref_year(authoritative)
    year_ok = None
    if cand_year is not None and auth_year is not None:
        year_ok = abs(int(cand_year) - int(auth_year)) <= YEAR_TOLERANCE
    return {"title_sim": round(sim, 3), "author_ok": author_ok,
            "year_ok": year_ok}


def _judge_identity(cmp: dict) -> str:
    """比对结果 → identity_status。规则见本节头注。"""
    if cmp["title_sim"] < 0.5:
        return "mismatch"
    if cmp["title_sim"] >= TITLE_SIM_THRESHOLD:
        if cmp["author_ok"] is False and cmp["year_ok"] is False:
            return "mismatch"
        if cmp["author_ok"] is False or cmp["year_ok"] is False:
            return "mismatch"
        return "verified"
    # 题名相似度在 0.5–阈值之间：信息不足以确认同一性
    return "unverifiable"


_RETRACTION_TYPE_MAP = (
    ("retract", "retracted"), ("withdraw", "retracted"),
    ("concern", "concern"),
    ("correct", "corrected"), ("erratum", "corrected"),
    ("addendum", "corrected"), ("clarification", "corrected"),
)


def _classify_update_type(type_text: str) -> str | None:
    text = (type_text or "").lower()
    for needle, status in _RETRACTION_TYPE_MAP:
        if needle in text:
            return status
    return None


def check_retraction(doi: str | None, epmc_raw: dict | None,
                     mailto: str | None) -> dict:
    """撤稿/更正检查（独立一步）：返回 status/signals/sources/lookups_ok。

    双源：① Crossref 反查 filter=updates:{doi}，读通知记录 update-to 中
    指向本 DOI 的 type；② Europe PMC 记录的 pubTypeList /
    commentCorrectionList / isRetracted。优先级
    retracted > concern > corrected > clear；两源都查不成 → unknown。
    """
    signals: list[str] = []
    sources: list[str] = []
    lookups_ok = 0
    if doi:
        url = (f"https://api.crossref.org/works?"
               f"filter=updates:{doi}")
        try:
            params = {"rows": 20}
            if mailto:
                params["mailto"] = mailto
            data, _raw = _get_json("https://api.crossref.org/works",
                                   params={**params,
                                           "filter": f"updates:{doi}"},
                                   headers=_ua(mailto))
            lookups_ok += 1
            sources.append(url)
            for item in (data.get("message") or {}).get("items", []):
                for upd in item.get("update-to", []) or []:
                    if normalize_doi(upd.get("DOI")) == doi:
                        status = _classify_update_type(upd.get("type", ""))
                        if status:
                            signals.append(
                                f"{status}:crossref:update-to:"
                                f"{upd.get('type')}")
        except FetchError:
            pass  # 该源查不成不抛，靠另一源与 lookups_ok 计数兜底
    if epmc_raw is not None:
        lookups_ok += 1
        sources.append("https://www.ebi.ac.uk/europepmc/webservices/rest/search")
        _hint, epmc_signals = _epmc_retraction_hints(epmc_raw)
        signals.extend(epmc_signals)
    for status in ("retracted", "concern", "corrected"):
        if any(s.startswith(status + ":") for s in signals):
            return {"status": status, "signals": signals,
                    "sources": sources, "lookups_ok": lookups_ok}
    return {"status": "clear" if lookups_ok else "unknown",
            "signals": signals, "sources": sources,
            "lookups_ok": lookups_ok}


def _verify_one(study: dict, mailto: str | None) -> dict:
    """核实单个 study（以其主记录为准），返回 verification dict。"""
    primary = next((r for r in study["records"] if r.get("is_primary")),
                   study["records"][0])
    candidate = {
        "title": study.get("title") or primary.get("title"),
        "authors": study.get("authors") or primary.get("authors"),
        "year": study.get("year") or primary.get("year"),
    }
    doi = normalize_doi(study.get("doi") or primary.get("doi"))
    sources: list[str] = []
    details: list[str] = []
    identity = "unverifiable"
    epmc_raw: dict | None = None

    if doi:
        sources.append(f"https://api.crossref.org/works/{doi}")
        cr_status, cr_msg = (None, None)
        try:
            cr_status, cr_msg = _crossref_work(doi, mailto)
        except FetchError as exc:
            details.append(f"crossref_lookup_failed:{exc}")
        try:
            epmc_raw = _epmc_by_doi(doi, mailto)
            if epmc_raw is not None:
                sources.append(
                    "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
                    f'?query=DOI:"{doi}"')
        except FetchError as exc:
            details.append(f"europepmc_lookup_failed:{exc}")

        judged = False
        if cr_status == 200 and cr_msg is not None:
            cmp = _compare_identity(candidate, cr_msg)
            identity = _judge_identity(cmp)
            details.append(f"crossref:title_sim={cmp['title_sim']},"
                           f"author_ok={cmp['author_ok']},"
                           f"year_ok={cmp['year_ok']}")
            judged = True
        elif cr_status == 404:
            details.append("crossref:404（DOI 不在 Crossref，"
                           "可能是 DataCite 注册，转 Europe PMC 兜底）")
        if not judged or identity == "unverifiable":
            if epmc_raw is not None:
                epmc_rec = _epmc_record(epmc_raw)
                cmp = _compare_identity(candidate, epmc_rec)
                epmc_identity = _judge_identity(cmp)
                details.append(f"europepmc:title_sim={cmp['title_sim']},"
                               f"author_ok={cmp['author_ok']},"
                               f"year_ok={cmp['year_ok']}")
                if identity != "verified":
                    identity = epmc_identity
            elif cr_status == 404:
                details.append("europepmc:该 DOI 无记录")
                identity = "unverifiable"
    else:
        details.append("no_doi：走题名检索核实")
        best: dict | None = None
        try:
            best = _epmc_by_title(candidate["title"], mailto)
            if best is not None:
                sources.append(
                    "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
                    " (TITLE 查询)")
        except FetchError as exc:
            details.append(f"europepmc_lookup_failed:{exc}")
        if best is None:
            try:
                cr_best = _crossref_best_bibliographic(
                    candidate["title"], mailto)
                if cr_best is not None:
                    best = {
                        "title": (cr_best.get("title") or [""])[0],
                        "authors": _crossref_authors(cr_best),
                        "year": _crossref_year(cr_best),
                    }
                    sources.append(
                        "https://api.crossref.org/works (题名查询)")
            except FetchError as exc:
                details.append(f"crossref_lookup_failed:{exc}")
        best_sim = 0.0
        if best is not None:
            cmp = _compare_identity(candidate, best)
            identity = _judge_identity(cmp)
            best_sim = cmp["title_sim"]
            details.append(f"title_search:title_sim={cmp['title_sim']},"
                           f"author_ok={cmp['author_ok']},"
                           f"year_ok={cmp['year_ok']}")
        else:
            details.append("title_search:无候选记录")
        # 无 DOI 时撤稿检查靠 Europe PMC 题名命中的原始记录；若命中来自
        # Crossref 题名查询（无 EPMC 原始记录），退而用记录自带的
        # retracted_hint（_hint_only 分支）。注意：题名相似度没过阈值的
        # 命中很可能是另一篇论文，其撤稿信号不许张冠李戴到本条上。
        if best_sim >= TITLE_SIM_THRESHOLD and best is not None:
            if best.get("_epmc_raw") is not None:
                epmc_raw = best["_epmc_raw"]
            elif best.get("retracted_hint"):
                epmc_raw = {"_hint_only": best["retracted_hint"]}

    # 撤稿检查独立执行（不依赖身份判定结果）
    if epmc_raw is not None and epmc_raw.get("_hint_only"):
        hint = epmc_raw["_hint_only"]
        rstatus = ("retracted" if "retracted" in hint else
                   "concern" if "concern" in hint else
                   "corrected" if "corrected" in hint else "unknown")
        retraction = {"status": rstatus, "signals": [hint],
                      "sources": sources, "lookups_ok": 1}
    else:
        retraction = check_retraction(doi, epmc_raw, mailto)
    if primary.get("retracted_hint"):
        details.append(f"record_hint:{primary['retracted_hint']}")
        if (primary["retracted_hint"].startswith("crossref:title-retracted")
                and retraction["status"] in ("clear", "unknown")):
            retraction = {**retraction, "status": "retracted",
                          "signals": retraction["signals"] + [
                              "retracted:crossref:title-prefix"]}

    return {
        "identity_status": identity,
        "retraction_status": retraction["status"],
        "retraction_signals": retraction["signals"],
        "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sources": sorted(set(sources + retraction["sources"])),
        "detail": "；".join(details),
    }


def verify_identity(project_dir: Path, limit: int | None = None,
                    mailto: str | None = None) -> dict:
    """对候选池逐条核实并回写 verification 字段（只打标、不删条）。

    limit 给出时只核实前 limit 条（联网冒烟/分批核实用）。
    单条核实中未预期的网络失败记为 unverifiable + unknown，不中断全程。
    """
    project_dir = Path(project_dir)
    studies = _read_pool(project_dir)
    targets = studies if limit is None else studies[:limit]
    counts = {"verified": 0, "mismatch": 0, "unverifiable": 0,
              "retracted": 0, "corrected": 0, "concern": 0}
    for study in targets:
        try:
            study["verification"] = _verify_one(study, mailto)
        except FetchError as exc:
            study["verification"] = {
                "identity_status": "unverifiable",
                "retraction_status": "unknown",
                "retraction_signals": [],
                "checked_at": datetime.now(timezone.utc).isoformat(
                    timespec="seconds"),
                "sources": [],
                "detail": f"lookup_failed:{exc}",
            }
        v = study["verification"]
        counts[v["identity_status"]] = counts.get(v["identity_status"], 0) + 1
        if v["retraction_status"] in ("retracted", "corrected", "concern"):
            counts[v["retraction_status"]] += 1
    _write_pool(project_dir, studies)
    return {"checked": len(targets), "total": len(studies), **counts}


# ---------------------------------------------------------------------------
# 粗筛表（判定先行）与校验

_SCREEN_NOTE = """# 粗筛说明

填写纪律（判定先行，PaSa Selector 格式）：

1. **先写 decision，再写 reason**：decision 只能是 include / exclude /
   maybe，reason 必须紧随其后说明依据（引用冻结 RQ 或纳排标准），
   不许只给判定不给理由，也不许把理由写在判定之前另起文档。
2. **六维评分**（各 1–5 分，nature pipeline 六维门控）：dim_relevance
   主题相关是门控维——填 0 表示主题不相关，该条必须 exclude；
   dim_method 方法适配、dim_data 数据可得、dim_quality 证据质量、
   dim_access 全文可得性、dim_risk 风险（如仅预印本、已更正）。
3. **硬规则**：retraction_status=retracted 的条目 decision 必须是
   exclude（`screen check` 会报错拦截）；identity_status 不是 verified
   的条目即使在此处 include，也**不能**进入研究证据矩阵成稿层
   （matrix 生成时执行，见 SKILL.md 硬规则 1），此处 include 只表示
   候选层保留跟进。
4. 填完运行 `screen check <project_dir>` 校验，再运行 `matrix`。
"""


def generate_screen(project_dir: Path) -> dict:
    """从候选池生成 粗筛表.csv（decision 与六维留空）与 粗筛说明.md。

    已存在的 粗筛表.csv 不覆盖（里面可能有人工填写结果），直接报错。
    """
    project_dir = Path(project_dir)
    studies = _read_pool(project_dir)
    lit = literature_dir(project_dir)
    csv_path = lit / _SCREEN_FILENAME
    if csv_path.exists():
        raise ValueError(f"粗筛表已存在，不覆盖（内含人工填写结果）：{csv_path}")
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=SCREEN_COLUMNS)
        writer.writeheader()
        for s in studies:
            v = s.get("verification") or {}
            writer.writerow({
                "study_id": s["study_id"],
                "title": s.get("title") or "",
                "year": s.get("year") or "",
                "venue": s.get("venue") or "",
                "version": s.get("version") or "",
                "identity_status": v.get("identity_status", "not_checked"),
                "retraction_status": v.get("retraction_status", ""),
                "decision": "", "reason": "",
                "dim_relevance": "", "dim_method": "", "dim_data": "",
                "dim_quality": "", "dim_access": "", "dim_risk": "",
            })
    note_path = lit / _SCREEN_NOTE_FILENAME
    if not note_path.exists():
        note_path.write_text(_SCREEN_NOTE, encoding="utf-8")
    return {"screen": str(csv_path), "note": str(note_path),
            "rows": len(studies)}


def check_screen(project_dir: Path) -> dict:
    """校验 粗筛表.csv，返回 {ok, errors, warnings, rows}。

    硬规则错误：decision 为空或不在枚举内；retracted 条目 decision
    不是 exclude。警告（留痕但不拦截）：unverifiable/not_checked 条目
    decision=include；decision 已填但 reason 为空。
    """
    project_dir = Path(project_dir)
    csv_path = literature_dir(project_dir) / _SCREEN_FILENAME
    if not csv_path.exists():
        raise FileNotFoundError(f"粗筛表不存在：{csv_path}（先运行 screen）")
    errors: list[str] = []
    warnings: list[str] = []
    with open(csv_path, "r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        sid = row.get("study_id", "?")
        decision = (row.get("decision") or "").strip()
        reason = (row.get("reason") or "").strip()
        if decision not in SCREEN_DECISIONS:
            errors.append(
                f"{sid}：decision 必须填 {'/'.join(SCREEN_DECISIONS)}，"
                f"当前为 {decision!r}")
            continue
        if row.get("retraction_status") == "retracted" and decision != "exclude":
            errors.append(
                f"{sid}：已撤稿条目 decision 必须是 exclude，当前为 "
                f"{decision}（硬规则，用户显式覆写须改走人工记录并说明理由）")
        if decision == "include" and row.get("identity_status") not in (
                "verified",):
            warnings.append(
                f"{sid}：identity_status={row.get('identity_status')} 的条目"
                f"被 include——候选层允许，但成稿层（matrix）仍会排除，"
                f"此警告已留痕")
        if not reason:
            warnings.append(f"{sid}：decision 已填但 reason 为空"
                            f"（判定先行格式要求判定后紧跟理由）")
    return {"ok": not errors, "errors": errors, "warnings": warnings,
            "rows": len(rows)}


# ---------------------------------------------------------------------------
# 研究证据矩阵（成稿层硬规则在此执行）

def _load_index(project_dir: Path) -> dict:
    """文献索引.csv → {paper_id: {doi, norm_title}}，供证据行关联 study。"""
    index_path = literature_dir(project_dir) / "文献索引.csv"
    out: dict[str, dict] = {}
    if not index_path.exists():
        return out
    with open(index_path, "r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            out[row["paper_id"]] = {
                "doi": normalize_doi(row.get("doi")),
                "norm_title": normalize_title(row.get("title")),
            }
    return out


def _load_evidence(project_dir: Path) -> list[dict]:
    """读 证据表.jsonl 并消解纠错链：被 corrects 指向的原行视为已被
    纠错行取代（审计链留在证据表本身，矩阵只呈现现行有效行）。"""
    path = literature_dir(project_dir) / "证据表.jsonl"
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    superseded = {r["corrects"] for r in rows if r.get("corrects")}
    return [r for r in rows if r.get("evidence_id") not in superseded]


def _study_evidence(study: dict, index: dict,
                    evidence_rows: list[dict]) -> list[dict]:
    """按 DOI 或规范化题名把 study 关联到已入库论文的证据行。"""
    study_dois = {normalize_doi(r.get("doi"))
                  for r in study["records"]} - {None}
    study_title = normalize_title(study.get("title"))
    paper_ids = set()
    for pid, meta in index.items():
        if (meta["doi"] and meta["doi"] in study_dois) or (
                meta["norm_title"] and meta["norm_title"] == study_title):
            paper_ids.add(pid)
    return [r for r in evidence_rows if r.get("paper_id") in paper_ids]


def generate_matrix(project_dir: Path) -> dict:
    """从候选池 + 证据表.jsonl 生成 研究证据矩阵.md（覆盖生成节）。

    硬规则（REDESIGN-DRAFT §3.1，写死）：只有 identity_status=verified
    且 retraction_status != retracted 的 study 进矩阵主体；其余全部进
    文末「排除清单」并注明原因，禁止静默丢弃。corrected/concern 进
    主体但带 ⚠ 标记；仅预印本的 study 标「仅预印本」；撤稿状态
    unknown 的进主体但备注明示。
    """
    project_dir = Path(project_dir)
    studies = _read_pool(project_dir)
    index = _load_index(project_dir)
    evidence_rows = _load_evidence(project_dir)

    body: list[dict] = []
    excluded: list[tuple[dict, str]] = []
    for s in studies:
        v = s.get("verification")
        if v is None:
            excluded.append((s, "尚未核实（未运行 verify-identity）"))
        elif v.get("retraction_status") == "retracted":
            excluded.append((s, "已撤稿（retracted）"))
        elif v.get("identity_status") == "mismatch":
            excluded.append((s, "身份不符（mismatch）：权威记录与候选条目对不上"))
        elif v.get("identity_status") != "verified":
            excluded.append(
                (s, f"身份未核实（{v.get('identity_status')}）："
                    f"成稿层一律不用未核实文献"))
        else:
            body.append(s)

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    lines = [
        "# 研究证据矩阵",
        "",
        f"<!-- 由 `matrix` 命令生成于 {now}（UTC）；主体准入硬规则："
        f"identity_status=verified 且未撤稿，其余一律进排除清单 -->",
        "",
        "多篇论文按共同研究问题对齐：方法 / 数据 / 结论 / 局限，冲突显式记录，不静默选一。",
        "",
        "| 论文 | 版本 | 关键证据（证据表） | 备注 |",
        "|---|---|---|---|",
    ]
    pending = 0
    for s in sorted(body, key=lambda x: (-(x.get("year") or 0),
                                         x.get("title") or "")):
        v = s.get("verification") or {}
        title = s.get("title") or ""
        marks = []
        if v.get("retraction_status") == "corrected":
            marks.append("⚠ 已更正（corrected）")
        elif v.get("retraction_status") == "concern":
            marks.append("⚠ 编辑关注（expression of concern）")
        label = ((" ".join(marks) + " ") if marks else "") + title
        if s.get("year"):
            label += f"（{s['year']}）"
        version = s.get("version") or "unknown"
        if s.get("preprint_only"):
            version += "（仅预印本）"
        rows = _study_evidence(s, index, evidence_rows)
        notes = []
        if rows:
            cell = "；".join(
                f"{r.get('finding', '')}（p.{r.get('page')}，"
                f"{r.get('claim_strength') or '未标强度'}）" for r in rows)
        else:
            cell = "待精读"
            pending += 1
        if v.get("retraction_status") == "unknown":
            notes.append("撤稿状态未知（unknown）：双源均未查成，引用前复核")
        if s.get("needs_review"):
            notes.append("题名模糊合并，待人工复核")
        lines.append(f"| {label} | {version} | {cell} | "
                     f"{'；'.join(notes)} |")
    if not body:
        lines.append("| （暂无通过硬规则的 study） | | | |")
    lines += ["", "## 排除清单（未进成稿层，禁止静默丢弃）", "",
              "| study | 论文 | 排除原因 |", "|---|---|---|"]
    if excluded:
        for s, reason in excluded:
            lines.append(
                f"| {s['study_id']} | {s.get('title') or ''} | {reason} |")
    else:
        lines.append("| | （无） | |")
    lines.append("")
    matrix_path = literature_dir(project_dir) / _MATRIX_FILENAME
    matrix_path.write_text("\n".join(lines), encoding="utf-8")
    return {"matrix": str(matrix_path), "body": len(body),
            "excluded": len(excluded), "pending_evidence": pending}
