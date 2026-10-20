"""共享检索适配层（LIT-D05）：统一结果模型 + 逐源适配器 + 缓存 + 失败隔离。

三包共用的检索底座（literature 先行落地，idea 查新与 journal-select
先例检索按 SKILL.md 接口契约消费本层）：

- 统一结果模型 Paper：字段与 Find 线的 record schema 完全一致
  (source / source_id / doi / title / authors / year / venue / type /
  version_hint / abstract / url / retracted_hint / queries)，to_record()
  与 from_record() 互转，保证既有候选池/对账代码无感切换。
- 逐源适配器：Crossref / OpenAlex / Semantic Scholar / Europe PMC /
  arXiv。每个适配器把该源的端点、参数、响应形状、版本提示与撤稿线索
  提取全部封装在内部 (fetch_raw 取原始响应字节、parse 解析为 Paper)，
  来源差异不外泄到调用方。
- 单一入口 search_all：多源多查询统一调度；(源+查询式+上限) 为键的
  磁盘缓存 (存原始响应，命中不联网)；单源单查询失败只记入 failures，
  不中断其余源 (失败隔离)。
- 传输注入：所有适配器收 get 可调用 (签名同 _get)，默认本层 http_get。
  light_literature.find 注入自己的 _get 以保留既有打桩与口径；独立消费
  方 (idea / journal-select) 直接用默认传输即可。

Semantic Scholar 适配器支持可选 Key (LIT-D07)：环境变量
SEMANTIC_SCHOLAR_API_KEY 存在时以 x-api-key 头注入；Key 绝不落盘、
不进日志与缓存键。无 Key 时维持免 Key 口径 (限流盲区见 SKILL 失败
模式附录第 13 条)。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import unicodedata
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

import requests

_HTTP_TIMEOUT = 30

#: 默认源清单 (与 Find 线 DEFAULT_SOURCES 一致；arXiv 为 literature
#: 既有第五源，一并纳入适配层，来源差异同样封装在适配器内)。
DEFAULT_SOURCES = ("openalex", "crossref", "semanticscholar", "arxiv",
                   "europepmc")


class FetchError(Exception):
    """单源请求失败 (网络错误 / 非预期状态码 / 响应不可解析)。"""


# ---------------------------------------------------------------------------
# 传输层 (默认实现；调用方可注入同签名函数替换，如 find 注入自身 _get)

def http_get(url: str, params: dict | None = None,
             headers: dict | None = None) -> tuple[int, bytes]:
    """发 GET 请求，返回 (status, body)。网络异常抛 FetchError。

    4xx 不抛 (404 对身份核实有语义)；5xx 抛 FetchError (该源本次不可用)。
    """
    try:
        resp = requests.get(url, params=params, headers=headers,
                            timeout=_HTTP_TIMEOUT)
    except requests.RequestException as exc:
        raise FetchError(f"网络错误：{exc}") from exc
    if resp.status_code >= 500:
        raise FetchError(f"HTTP {resp.status_code}：{url}")
    return resp.status_code, resp.content


def _get_json(get, url: str, params: dict | None = None,
              headers: dict | None = None) -> tuple[object, bytes]:
    """用注入的 get 取 JSON；非 200 或解析失败抛 FetchError。"""
    status, body = get(url, params=params, headers=headers)
    if status != 200:
        raise FetchError(f"HTTP {status}：{url}")
    try:
        return json.loads(body.decode("utf-8")), body
    except (ValueError, UnicodeDecodeError) as exc:
        raise FetchError(f"响应不是合法 JSON：{url}（{exc}）") from exc


def ua_headers(mailto: str | None) -> dict:
    ua = "light-literature/0.1 (Find; https://example.invalid/light-literature)"
    if mailto:
        ua += f" (mailto:{mailto})"
    return {"User-Agent": ua}


# ---------------------------------------------------------------------------
# DOI 规范化 (find 等模块共用同一实现，避免口径漂移)

def normalize_doi(doi: str | None) -> str | None:
    """DOI 规范化：去 https://doi.org/ 等前缀、转小写、去空白。"""
    if not doi:
        return None
    text = str(doi).strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if text.startswith(prefix):
            text = text[len(prefix):]
    return text.strip() or None


# ---------------------------------------------------------------------------
# 统一结果模型 Paper

@dataclass
class Paper:
    """统一检索结果模型 (字段与 Find 线 record schema 一一对应)。"""

    source: str
    source_id: str
    doi: str | None = None
    title: str = ""
    authors: list = field(default_factory=list)
    year: int | None = None
    venue: str = ""
    type: str = ""
    version_hint: str = "unknown"  # preprint | version_of_record | unknown
    abstract: str = ""
    url: str = ""
    retracted_hint: str | None = None
    queries: list = field(default_factory=list)

    def to_record(self) -> dict:
        return {
            "source": self.source,
            "source_id": self.source_id,
            "doi": self.doi,
            "title": self.title,
            "authors": list(self.authors),
            "year": self.year,
            "venue": self.venue,
            "type": self.type,
            "version_hint": self.version_hint,
            "abstract": self.abstract,
            "url": self.url,
            "retracted_hint": self.retracted_hint,
            "queries": list(self.queries),
        }

    @classmethod
    def from_record(cls, rec: dict) -> "Paper":
        return cls(
            source=rec.get("source", ""), source_id=str(rec.get("source_id", "")),
            doi=normalize_doi(rec.get("doi")),
            title=(rec.get("title") or "").strip(),
            authors=[a for a in (rec.get("authors") or []) if a],
            year=rec.get("year"), venue=(rec.get("venue") or "").strip(),
            type=rec.get("type") or "",
            version_hint=rec.get("version_hint") or "unknown",
            abstract=(rec.get("abstract") or "").strip(),
            url=rec.get("url") or "",
            retracted_hint=rec.get("retracted_hint"),
            queries=list(rec.get("queries") or []),
        )


def _paper(source: str, source_id: str, **kw) -> Paper:
    """规范化构造 Paper (与历史 _record 行为一致：DOI 规范化、去空作者)。"""
    return Paper(
        source=source, source_id=str(source_id),
        doi=normalize_doi(kw.get("doi")),
        title=(kw.get("title") or "").strip(),
        authors=[a for a in (kw.get("authors") or []) if a],
        year=kw.get("year"), venue=(kw.get("venue") or "").strip(),
        type=kw.get("type") or "",
        version_hint=kw.get("version_hint") or "unknown",
        abstract=(kw.get("abstract") or "").strip(),
        url=kw.get("url") or "",
        retracted_hint=kw.get("retracted_hint"),
        queries=list(kw.get("queries") or []),
    )


# ---------------------------------------------------------------------------
# Crossref 适配器

_JATS_TAG_RE = re.compile(r"<[^>]+>")


def _strip_jats(text: str | None) -> str:
    """Crossref 摘要常带 JATS XML 标签，粗暴去标签只留文本。"""
    if not text:
        return ""
    return re.sub(r"\s+", " ", _JATS_TAG_RE.sub(" ", text)).strip()


def crossref_year(item: dict) -> int | None:
    for key in ("published-print", "published-online", "published",
                "issued", "created"):
        parts = ((item.get(key) or {}).get("date-parts") or [[]])[0]
        if parts and isinstance(parts[0], int):
            return parts[0]
    return None


def crossref_authors(item: dict) -> list[str]:
    out = []
    for a in item.get("author", []) or []:
        name = " ".join(x for x in (a.get("given"), a.get("family")) if x)
        out.append(name or a.get("name") or "")
    return out


def _crossref_retraction_hint(item: dict) -> str | None:
    """从 Crossref 记录本体提取撤稿线索 (只认 title 的 RETRACTED 前缀；
    update-to 挂在通知记录上指向原文，不算自身被撤，真判定在撤稿检查步)。"""
    title = (item.get("title") or [""])[0]
    if title.strip().lower().startswith("retracted"):
        return "crossref:title-retracted-prefix"
    return None


class CrossrefAdapter:
    """Crossref：检索 + 按 DOI 取权威记录 (身份核实/元数据回填共用)。"""

    name = "crossref"
    base = "https://api.crossref.org/works"

    def fetch_raw(self, query: str, limit: int, mailto: str | None = None,
                  get=None) -> bytes:
        get = get or http_get
        params = {"query.bibliographic": query, "rows": limit}
        if mailto:
            params["mailto"] = mailto
        _data, raw = _get_json(get, self.base, params=params,
                               headers=ua_headers(mailto))
        return raw

    def parse(self, raw: bytes, query: str | None = None) -> list[Paper]:
        try:
            data = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise FetchError(f"Crossref 响应不是合法 JSON（{exc}）") from exc
        records = []
        for item in (data.get("message") or {}).get("items", []):
            records.append(_paper(
                "crossref", item.get("DOI", ""),
                doi=item.get("DOI"),
                title=(item.get("title") or [""])[0],
                authors=crossref_authors(item),
                year=crossref_year(item),
                venue=(item.get("container-title") or [""])[0],
                type=item.get("type") or "",
                version_hint="version_of_record"
                if item.get("type") in ("journal-article",
                                        "proceedings-article",
                                        "book-chapter")
                else "unknown",
                abstract=_strip_jats(item.get("abstract")),
                url=item.get("URL"),
                retracted_hint=_crossref_retraction_hint(item),
                queries=[query] if query else [],
            ))
        return records

    def search(self, query: str, limit: int, mailto: str | None = None,
               get=None) -> tuple[list[Paper], bytes]:
        raw = self.fetch_raw(query, limit, mailto=mailto, get=get)
        return self.parse(raw, query), raw

    def fetch_work(self, doi: str, mailto: str | None = None,
                   get=None) -> tuple[int, dict | None]:
        """按 DOI 取 Crossref 权威记录，返回 (status, message|None)。

        404 返回 (404, None) 不抛 (DOI 可能注册在 DataCite)；其他非 200
        抛 FetchError。
        """
        get = get or http_get
        status, body = get(f"{self.base}/{doi}", headers=ua_headers(mailto))
        if status == 404:
            return 404, None
        if status != 200:
            raise FetchError(f"Crossref 按 DOI 查询返回 HTTP {status}")
        try:
            return 200, json.loads(body.decode("utf-8")).get("message") or {}
        except (ValueError, UnicodeDecodeError) as exc:
            raise FetchError(f"Crossref 响应解析失败（{exc}）") from exc


# ---------------------------------------------------------------------------
# OpenAlex 适配器

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


class OpenAlexAdapter:
    name = "openalex"
    base = "https://api.openalex.org/works"

    def fetch_raw(self, query: str, limit: int, mailto: str | None = None,
                  get=None) -> bytes:
        get = get or http_get
        params = {"search": query, "per-page": limit}
        if mailto:
            params["mailto"] = mailto
        _data, raw = _get_json(get, self.base, params=params,
                               headers=ua_headers(mailto))
        return raw

    def parse(self, raw: bytes, query: str | None = None) -> list[Paper]:
        try:
            data = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise FetchError(f"OpenAlex 响应不是合法 JSON（{exc}）") from exc
        records = []
        for w in data.get("results", []):
            loc = w.get("primary_location") or {}
            src = loc.get("source") or {}
            hint = _OPENALEX_VERSION.get(loc.get("version") or "", "unknown")
            if (src.get("display_name") or "").lower() == "arxiv":
                hint = "preprint"
            records.append(_paper(
                "openalex", w.get("id", ""),
                doi=w.get("doi"), title=w.get("display_name") or w.get("title"),
                authors=[(a.get("author") or {}).get("display_name")
                         for a in w.get("authorships", [])],
                year=w.get("publication_year"),
                venue=src.get("display_name"),
                type=w.get("type") or "",
                version_hint=hint,
                abstract=_openalex_abstract(w.get("abstract_inverted_index")),
                url=(w.get("doi")
                     and f"https://doi.org/{normalize_doi(w['doi'])}")
                    or w.get("id"),
                queries=[query] if query else [],
            ))
        return records

    def search(self, query: str, limit: int, mailto: str | None = None,
               get=None) -> tuple[list[Paper], bytes]:
        raw = self.fetch_raw(query, limit, mailto=mailto, get=get)
        return self.parse(raw, query), raw


# ---------------------------------------------------------------------------
# Semantic Scholar 适配器 (可选 Key：环境变量注入，绝不落盘)

#: Key 的环境变量名 (连接器/用户环境注入；代码与日志中永不出现其值)。
S2_API_KEY_ENV = "SEMANTIC_SCHOLAR_API_KEY"


def s2_api_key_configured() -> bool:
    return bool(os.environ.get(S2_API_KEY_ENV))


class SemanticScholarAdapter:
    name = "semanticscholar"
    base = "https://api.semanticscholar.org/graph/v1/paper/search"

    def _headers(self, mailto: str | None) -> dict:
        headers = ua_headers(mailto)
        key = os.environ.get(S2_API_KEY_ENV)
        if key:
            headers["x-api-key"] = key
        return headers

    def fetch_raw(self, query: str, limit: int, mailto: str | None = None,
                  get=None) -> bytes:
        get = get or http_get
        params = {
            "query": query, "limit": limit,
            "fields": "title,authors,year,venue,externalIds,abstract,url,"
                      "publicationTypes",
        }
        _data, raw = _get_json(get, self.base, params=params,
                               headers=self._headers(mailto))
        return raw

    def parse(self, raw: bytes, query: str | None = None) -> list[Paper]:
        try:
            data = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise FetchError(
                f"Semantic Scholar 响应不是合法 JSON（{exc}）") from exc
        records = []
        for p in data.get("data", []) or []:
            ext = p.get("externalIds") or {}
            venue = p.get("venue") or ""
            hint = "preprint" if venue.lower().startswith("arxiv") else "unknown"
            records.append(_paper(
                "semanticscholar", p.get("paperId", ""),
                doi=ext.get("DOI"),
                title=p.get("title"),
                authors=[a.get("name") for a in p.get("authors", []) or []],
                year=p.get("year"), venue=venue,
                type=",".join(p.get("publicationTypes") or []),
                version_hint=hint,
                abstract=p.get("abstract"),
                url=p.get("url"),
                queries=[query] if query else [],
            ))
        return records

    def search(self, query: str, limit: int, mailto: str | None = None,
               get=None) -> tuple[list[Paper], bytes]:
        raw = self.fetch_raw(query, limit, mailto=mailto, get=get)
        return self.parse(raw, query), raw


# ---------------------------------------------------------------------------
# Europe PMC 适配器 (含撤稿信号提取：pubTypeList / commentCorrectionList)

def epmc_retraction_hints(res: dict) -> tuple[str | None, list[str]]:
    """从 Europe PMC 单条结果提取撤稿信号，返回 (retracted_hint, signals)。

    signals 是撤稿检查步用的分类信号 (retracted/concern/corrected 前缀)。
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


class EuropePMCAdapter:
    name = "europepmc"
    base = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"

    def record_from_raw(self, res: dict, query: str | None = None) -> Paper:
        hint, _signals = epmc_retraction_hints(res)
        authors = []
        for a in (res.get("authorList") or {}).get("author", []) or []:
            authors.append(a.get("fullName") or "")
        journal = ((res.get("journalInfo") or {}).get("journal") or {}).get(
            "title") or ""
        year = res.get("pubYear")
        return _paper(
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

    def search_raw(self, query: str, mailto: str | None = None,
                   page_size: int = 5, get=None) -> list[dict]:
        """原始结果 dict 列表 (resultType=core)；身份核实/撤稿检查共用。"""
        get = get or http_get
        params = {"query": query, "format": "json", "resultType": "core",
                  "pageSize": page_size}
        data, _raw = _get_json(get, self.base, params=params,
                               headers=ua_headers(mailto))
        return (data.get("resultList") or {}).get("result", []) or []

    def fetch_raw(self, query: str, limit: int, mailto: str | None = None,
                  get=None) -> bytes:
        get = get or http_get
        params = {"query": query, "format": "json", "resultType": "core",
                  "pageSize": limit}
        _data, raw = _get_json(get, self.base, params=params,
                               headers=ua_headers(mailto))
        return raw

    def parse(self, raw: bytes, query: str | None = None) -> list[Paper]:
        try:
            data = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise FetchError(f"Europe PMC 响应不是合法 JSON（{exc}）") from exc
        return [self.record_from_raw(r, query)
                for r in (data.get("resultList") or {}).get("result", [])]

    def search(self, query: str, limit: int, mailto: str | None = None,
               get=None) -> tuple[list[Paper], bytes]:
        raw = self.fetch_raw(query, limit, mailto=mailto, get=get)
        return self.parse(raw, query), raw


# ---------------------------------------------------------------------------
# arXiv 适配器 (Atom XML)

_ARXIV_NS = {"atom": "http://www.w3.org/2005/Atom",
             "arxiv": "http://arxiv.org/schemas/atom"}


class ArxivAdapter:
    name = "arxiv"
    base = "https://export.arxiv.org/api/query"

    def fetch_raw(self, query: str, limit: int, mailto: str | None = None,
                  get=None) -> bytes:
        get = get or http_get
        params = {"search_query": f"all:{query}", "start": 0,
                  "max_results": limit}
        status, body = get(self.base, params=params,
                           headers=ua_headers(mailto))
        if status != 200:
            raise FetchError(f"HTTP {status}：arXiv API")
        return body

    def parse(self, raw: bytes, query: str | None = None) -> list[Paper]:
        try:
            root = ET.fromstring(raw.decode("utf-8"))
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
            records.append(_paper(
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
                queries=[query] if query else [],
            ))
        return records

    def search(self, query: str, limit: int, mailto: str | None = None,
               get=None) -> tuple[list[Paper], bytes]:
        raw = self.fetch_raw(query, limit, mailto=mailto, get=get)
        return self.parse(raw, query), raw


# ---------------------------------------------------------------------------
# 适配器注册表与统一入口 (缓存 + 失败隔离)

_ADAPTERS = {
    "crossref": CrossrefAdapter(),
    "openalex": OpenAlexAdapter(),
    "semanticscholar": SemanticScholarAdapter(),
    "europepmc": EuropePMCAdapter(),
    "arxiv": ArxivAdapter(),
}


def get_adapter(name: str):
    try:
        return _ADAPTERS[name]
    except KeyError:
        raise ValueError(
            f"未知检索源：{name}（可选：{sorted(_ADAPTERS)}）") from None


def adapter_names() -> list[str]:
    return list(_ADAPTERS)


def cache_key(source: str, query: str, per_source: int) -> str:
    """缓存文件名 (不含扩展名)；与 Find 线 .find-cache 历史命名一致。"""
    digest = hashlib.sha1(
        f"{source}|{query}|{per_source}".encode("utf-8")).hexdigest()[:10]
    return f"{source}__{digest}"


def cache_ext(source: str) -> str:
    return "xml" if source == "arxiv" else "json"


def search_all(queries: list[str], sources=DEFAULT_SOURCES,
               per_source: int = 10, mailto: str | None = None,
               cache_dir: Path | None = None, get=None) -> dict:
    """多源多查询统一检索：返回 records (record dict 列表) 与运行统计。

    - 缓存：cache_dir 给出时，(源+查询式+上限) 命中的原始响应直接解析、
      不联网；未命中取回后落盘原始响应 (可复现)。
    - 失败隔离：单源单查询抛 FetchError 只记入 failures 并把该源 stat
      标 ok=False，其余源/查询照常执行。
    - 留痕：每条 record 带 source 与 queries；统计含 per_source
      {hits, ok, error}、failures、cache_hits。
    """
    if not queries:
        raise ValueError("至少需要一个查询式")
    unknown = [s for s in sources if s not in _ADAPTERS]
    if unknown:
        raise ValueError(f"未知检索源：{unknown}（可选：{adapter_names()}）")
    if cache_dir is not None:
        cache_dir = Path(cache_dir)
        cache_dir.mkdir(parents=True, exist_ok=True)

    records: list[dict] = []
    per_source_stats: dict[str, dict] = {}
    failures: list[dict] = []
    cache_hits = 0
    for source in sources:
        adapter = _ADAPTERS[source]
        stat = {"hits": 0, "ok": True, "error": None}
        for query in queries:
            cache_path = None
            if cache_dir is not None:
                cache_path = cache_dir / (
                    cache_key(source, query, per_source)
                    + "." + cache_ext(source))
            try:
                if cache_path is not None and cache_path.exists():
                    raw = cache_path.read_bytes()
                    cache_hits += 1
                    papers = adapter.parse(raw, query)
                else:
                    papers, raw = adapter.search(
                        query, per_source, mailto=mailto, get=get)
                    if cache_path is not None:
                        cache_path.write_bytes(raw)
            except FetchError as exc:
                stat["ok"] = False
                stat["error"] = str(exc)
                failures.append({"source": source, "query": query,
                                 "error": str(exc)})
                continue
            stat["hits"] += len(papers)
            records.extend(p.to_record() for p in papers)
        per_source_stats[source] = stat
    return {
        "records": records,
        "per_source": per_source_stats,
        "failures": failures,
        "cache_hits": cache_hits,
    }
