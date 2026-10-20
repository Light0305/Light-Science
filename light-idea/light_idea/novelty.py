"""I3 facet 查新子流程（二期）：取证（prepare）与判定落卡（verdict）。

设计依据：02-idea/REDESIGN-DRAFT.md §4 + LEARNING.md 约束 1/2/3。
写死的纪律（校验器与流程共同把守）：

- **facet 主路线**（约束 3）：从想法卡 facet 区逐面构造检索式实查，
  整想法检索只作召回层（入池、标 facet=whole），不单独产生判定；
- **实查证据**（约束 1）：新颖性结论只能来自证据包里可审计的命中记录；
  相似度只是离线粗排信号，只许用于召回排序，**不作判定依据**，也不写进
  卡的 novelty 判定区（aux 区都不写——查新相似度不是卡的排序信号）；
- **判定宪法**（约束 2 / 拍板 9.1-A，ARIS 宽松口径）：ABANDON 只有一个
  资格——点名一篇已发表的在先论文且该论文必须真实存在于证据池中；
  「拥挤但有 delta」= PROCEED；CAUTION 必须说清 delta 薄在哪，
  说不出就是 PROCEED；拿不准取宽松；
- **跨模型硬门**（约束 1 / 拍板 9.4-B）：判定者与执行者必须不同模型
  家族，同家族自审判无效、拒绝落卡；外部判定确实不可得时允许显式
  降级（review_status=REVIEW_UNAVAILABLE 落盘，一期定版门保证其
  不能定版，本模块不放宽任何门）；
- **失败如实记录**：单源限流/不可达只记入该源状态与已知盲区，
  不中断其余源、不假装查全。

HTTP 只用标准库 urllib（本包依赖面保持 pyyaml 一项）。四个源均为
免 Key 公开 API：Crossref / OpenAlex / Semantic Scholar / Europe PMC。
测试通过 monkeypatch 本模块的 `_http_get_json` 实现 mock，禁止真联网。
"""

from __future__ import annotations

import hashlib
import json
import re
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from difflib import SequenceMatcher
from pathlib import Path

from .dedup import cosine, tfidf_vectors
from .schema import FACETS, VERDICTS, _nonempty_str, _ref_ok, model_family
from .util import today

# ---------------------------------------------------------------------------
# 常量

SOURCES = ("crossref", "openalex", "semanticscholar", "europepmc")
SOURCE_LABELS = {
    "crossref": "Crossref",
    "openalex": "OpenAlex",
    "semanticscholar": "Semantic Scholar",
    "europepmc": "Europe PMC",
}
WHOLE = "whole"  # 整想法召回层的伪 facet 名（只召回、不判定）
ALL_FACET_TAGS = FACETS + (WHOLE,)

DEFAULT_PER_QUERY = 10
_HTTP_TIMEOUT = 25
_ABSTRACT_SNIPPET_CHARS = 400

_UA = {"User-Agent": "Light-Idea/0.2 (novelty-check; stdlib-urllib)"}

# 关键词抽取停用词（英文功能词 + 学术套话；只影响关键词式查询的构成）
_STOPWORDS = {
    "the", "a", "an", "of", "for", "with", "and", "or", "to", "in", "on",
    "by", "via", "using", "use", "used", "based", "towards", "toward",
    "from", "into", "under", "over", "per", "et", "al", "we", "our",
    "this", "that", "these", "those", "is", "are", "be", "as", "at",
    "study", "studies", "paper", "approach", "method", "methods",
    "propose", "proposed", "novel", "new", "framework", "model", "models",
}


class SourceError(Exception):
    """单源请求失败。status 为 HTTP 状态码，网络错误时为 None。"""

    def __init__(self, source: str, message: str, status: int | None = None):
        self.source = source
        self.status = status
        super().__init__(message)


class NoveltyError(Exception):
    """查新流程/判定校验失败。errors 为逐条人读原因。"""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("；".join(errors))


# ---------------------------------------------------------------------------
# HTTP 层（测试 monkeypatch 本函数实现 mock，禁止测试真联网）

def _http_get_json(url: str, params: dict | None = None) -> object:
    """GET 并解析 JSON。失败抛 SourceError（源名由调用方补注时用 url 推断）。

    HTTP 错误（含 429）抛 SourceError(status=...)；网络错误 status=None。
    """
    full = url
    if params:
        full = url + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(full, headers=_UA)
    try:
        with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT) as resp:
            body = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        raise SourceError("http", f"HTTP {exc.code}：{url}", status=exc.code) from exc
    except (urllib.error.URLError, OSError) as exc:
        raise SourceError("http", f"网络错误：{exc}：{url}", status=None) from exc
    try:
        return json.loads(body)
    except ValueError as exc:
        raise SourceError("http", f"响应不是合法 JSON：{url}", status=None) from exc


def _fetch(source: str, url: str, params: dict) -> object:
    """带源名的请求封装：把 _http_get_json 的错误补上源名后原样抛出。"""
    try:
        return _http_get_json(url, params)
    except SourceError as exc:
        raise SourceError(source, str(exc), status=exc.status) from exc


# ---------------------------------------------------------------------------
# 文本工具（本模块独立实现，不跨项目 import；与卡内其他模块口径对齐）

def normalize_doi(doi) -> str | None:
    if not doi:
        return None
    text = str(doi).strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if text.startswith(prefix):
            text = text[len(prefix):]
    return text.strip() or None


def normalize_title(title) -> str:
    """题名规范化（去重/匹配键）：NFKD、小写、去标点、压缩空白。"""
    text = unicodedata.normalize("NFKD", title or "")
    text = text.encode("ascii", "ignore").decode("ascii").lower()
    text = re.sub(r"[^a-z0-9\u4e00-\u9fff ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _title_ratio(t1: str, t2: str) -> float:
    n1, n2 = normalize_title(t1), normalize_title(t2)
    if not n1 or not n2:
        return 0.0
    return SequenceMatcher(None, n1, n2).ratio()


def _keywords(text: str, limit: int = 10) -> list[str]:
    """从短语+展开里抽关键词：英文实词（去停用词）+ 中文二元组。"""
    text = (text or "").lower()
    words: list[str] = []
    for w in re.findall(r"[a-z][a-z0-9\-]{2,}", text):
        w = w.strip("-")
        if w and w not in _STOPWORDS and w not in words:
            words.append(w)
    cjk = "".join(re.findall(r"[\u4e00-\u9fff]", text))
    grams: list[str] = []
    for i in range(len(cjk) - 1):
        g = cjk[i:i + 2]
        if g not in grams:
            grams.append(g)
    out = words[:limit]
    for g in grams:
        if len(out) >= limit:
            break
        out.append(g)
    return out


# ---------------------------------------------------------------------------
# 1. 构式：逐面至少 2 条（短语式 + 关键词式）+ 整想法召回 1–2 条

def build_queries(card: dict) -> list[dict]:
    """从卡的 facet 区与题名构造检索式清单。

    每条：{facet, kind, text}；kind ∈ phrase / keywords / whole_idea。
    facet=whole 的整想法式只作召回层（约束 3），判定不许只凭它。
    """
    queries: list[dict] = []
    facets = card.get("facets") or {}
    for facet in FACETS:
        fd = facets.get(facet) or {}
        phrase = (fd.get("phrase") or "").strip()
        detail = (fd.get("detail") or "").strip()
        if phrase:
            queries.append({"facet": facet, "kind": "phrase", "text": phrase})
        kw = _keywords(f"{phrase} {detail}")
        if kw:
            queries.append({"facet": facet, "kind": "keywords",
                            "text": " ".join(kw)})
    title = (card.get("title") or "").strip()
    if title:
        queries.append({"facet": WHOLE, "kind": "whole_idea", "text": title})
    whole_kw = _keywords(" ".join([
        title,
        (facets.get("purpose") or {}).get("phrase") or "",
        (facets.get("mechanism") or {}).get("phrase") or "",
        card.get("one_liner") or "",
    ]))
    if whole_kw:
        queries.append({"facet": WHOLE, "kind": "whole_idea",
                        "text": " ".join(whole_kw)})
    return queries


def facet_texts(card: dict) -> dict[str, str]:
    """每面（+整想法）的比对文本：粗排时与池内记录算离线相似度。"""
    facets = card.get("facets") or {}
    texts = {}
    for facet in FACETS:
        fd = facets.get(facet) or {}
        texts[facet] = f"{fd.get('phrase') or ''} {fd.get('detail') or ''}".strip()
    texts[WHOLE] = " ".join([
        card.get("title") or "", card.get("one_liner") or "",
        texts["purpose"], texts["mechanism"],
    ]).strip()
    return texts


# ---------------------------------------------------------------------------
# 2. 四源适配器：统一记录 {source, source_id, title, authors, year, doi,
#    venue, abstract, url}

def _strip_jats(text) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", str(text))).strip()


def _record(source: str, source_id: str, **kw) -> dict:
    return {
        "source": source,
        "source_id": str(source_id or ""),
        "title": (kw.get("title") or "").strip(),
        "authors": [a for a in (kw.get("authors") or []) if a],
        "year": kw.get("year"),
        "doi": normalize_doi(kw.get("doi")),
        "venue": (kw.get("venue") or "").strip(),
        "abstract": (kw.get("abstract") or "").strip(),
        "url": kw.get("url") or "",
    }


def _search_crossref(query: str, n: int) -> list[dict]:
    data = _fetch("crossref", "https://api.crossref.org/works",
                  {"query.bibliographic": query, "rows": n})
    out = []
    for item in (data.get("message") or {}).get("items", []) or []:
        year = None
        for key in ("published-print", "published-online", "published",
                    "issued", "created"):
            parts = ((item.get(key) or {}).get("date-parts") or [[]])[0]
            if parts and isinstance(parts[0], int):
                year = parts[0]
                break
        authors = []
        for a in item.get("author", []) or []:
            name = " ".join(x for x in (a.get("given"), a.get("family")) if x)
            authors.append(name or a.get("name") or "")
        out.append(_record(
            "crossref", item.get("DOI", ""),
            doi=item.get("DOI"),
            title=(item.get("title") or [""])[0],
            authors=authors, year=year,
            venue=(item.get("container-title") or [""])[0],
            abstract=_strip_jats(item.get("abstract")),
            url=item.get("URL"),
        ))
    return out


def _openalex_abstract(inverted) -> str:
    if not inverted:
        return ""
    positions: dict[int, str] = {}
    for word, idxs in inverted.items():
        for i in idxs:
            positions[i] = word
    return " ".join(positions[i] for i in sorted(positions))


def _search_openalex(query: str, n: int) -> list[dict]:
    data = _fetch("openalex", "https://api.openalex.org/works",
                  {"search": query, "per-page": n})
    out = []
    for w in data.get("results", []) or []:
        loc = w.get("primary_location") or {}
        src = loc.get("source") or {}
        doi = normalize_doi(w.get("doi"))
        out.append(_record(
            "openalex", w.get("id", ""),
            doi=doi, title=w.get("display_name") or w.get("title"),
            authors=[(a.get("author") or {}).get("display_name")
                     for a in w.get("authorships", []) or []],
            year=w.get("publication_year"),
            venue=src.get("display_name"),
            abstract=_openalex_abstract(w.get("abstract_inverted_index")),
            url=(f"https://doi.org/{doi}" if doi else w.get("id")),
        ))
    return out


def _search_semanticscholar(query: str, n: int) -> list[dict]:
    data = _fetch(
        "semanticscholar", "https://api.semanticscholar.org/graph/v1/paper/search",
        {"query": query, "limit": n,
         "fields": "title,authors,year,venue,externalIds,abstract,url"})
    out = []
    for p in data.get("data", []) or []:
        ext = p.get("externalIds") or {}
        out.append(_record(
            "semanticscholar", p.get("paperId", ""),
            doi=ext.get("DOI"), title=p.get("title"),
            authors=[a.get("name") for a in p.get("authors", []) or []],
            year=p.get("year"), venue=p.get("venue"),
            abstract=p.get("abstract"), url=p.get("url"),
        ))
    return out


def _search_europepmc(query: str, n: int) -> list[dict]:
    data = _fetch(
        "europepmc", "https://www.ebi.ac.uk/europepmc/webservices/rest/search",
        {"query": query, "format": "json", "resultType": "core",
         "pageSize": n})
    out = []
    for res in (data.get("resultList") or {}).get("result", []) or []:
        authors = [a.get("fullName") or ""
                   for a in (res.get("authorList") or {}).get("author", []) or []]
        journal = ((res.get("journalInfo") or {}).get("journal") or {}).get("title") or ""
        year = res.get("pubYear")
        doi = normalize_doi(res.get("doi"))
        out.append(_record(
            "europepmc", f"{res.get('source', '')}:{res.get('id', '')}",
            doi=doi, title=res.get("title"), authors=authors,
            year=int(year) if str(year).isdigit() else None,
            venue=journal, abstract=res.get("abstractText"),
            url=(f"https://doi.org/{doi}" if doi
                 else f"https://europepmc.org/article/{res.get('source')}/{res.get('id')}"),
        ))
    return out


_SEARCHERS = {
    "crossref": _search_crossref,
    "openalex": _search_openalex,
    "semanticscholar": _search_semanticscholar,
    "europepmc": _search_europepmc,
}


# ---------------------------------------------------------------------------
# 3. 归池、去重、粗排

def _pool_key(rec: dict) -> str:
    """去重键：DOI 优先，无 DOI 时用规范化题名。"""
    if rec.get("doi"):
        return f"doi:{rec['doi']}"
    return f"title:{normalize_title(rec.get('title'))}"


def collect_pool(card: dict, queries: list[dict], *,
                 per_query: int = DEFAULT_PER_QUERY,
                 sources: tuple[str, ...] = SOURCES,
                 interleave_sleep: float = 0.0) -> dict:
    """逐式逐源实查，归池去重并离线粗排。

    返回 {pool, query_log, source_status}：
    - pool：去重后记录，每条带 sources[]、hit_facets[]、queries[]、
      similarity（对命中面的离线粗排分，只作排序）、best_facet；
    - query_log：每条 (query, source) 的命中数或错误（可审计）；
    - source_status：每源 {ok, hits, errors[]}——单源失败不中断。
    """
    ftexts = facet_texts(card)
    merged: dict[str, dict] = {}
    query_log: list[dict] = []
    source_status: dict[str, dict] = {
        s: {"ok": False, "responded": False, "hits": 0, "errors": []}
        for s in sources
    }
    for q in queries:
        for source in sources:
            entry = {"facet": q["facet"], "kind": q["kind"], "query": q["text"],
                     "source": source, "hits": None, "error": None}
            try:
                records = _SEARCHERS[source](q["text"], per_query)
            except SourceError as exc:
                # _http_get_json 的消息已自带「HTTP <码>：」或「网络错误：」
                # 前缀，此处不重复拼接，只原样记录以便审计。
                entry["error"] = str(exc)
                source_status[source]["errors"].append(
                    {"query": q["text"], "error": entry["error"]})
                query_log.append(entry)
                continue
            entry["hits"] = len(records)
            source_status[source]["hits"] += len(records)
            # ok = 源可达（至少一次成功响应），与「有无命中」分开记，
            # 零命中是查无、不是源坏；失败只看 errors。
            source_status[source]["responded"] = True
            source_status[source]["ok"] = True
            for rec in records:
                key = _pool_key(rec)
                cur = merged.get(key)
                if cur is None:
                    cur = dict(rec)
                    cur["sources"] = [rec["source"]]
                    cur["hit_facets"] = [q["facet"]]
                    cur["queries"] = [q["text"]]
                    cur["_abstract_full"] = rec.get("abstract") or ""
                    merged[key] = cur
                else:
                    if rec["source"] not in cur["sources"]:
                        cur["sources"].append(rec["source"])
                    if q["facet"] not in cur["hit_facets"]:
                        cur["hit_facets"].append(q["facet"])
                    if q["text"] not in cur["queries"]:
                        cur["queries"].append(q["text"])
                    # 字段补全：优先保留带摘要/年份/作者的版本
                    if not cur.get("abstract") and rec.get("abstract"):
                        cur["abstract"] = rec["abstract"]
                        cur["_abstract_full"] = rec["abstract"]
                    if not cur.get("year") and rec.get("year"):
                        cur["year"] = rec["year"]
                    if not cur.get("authors") and rec.get("authors"):
                        cur["authors"] = rec["authors"]
                    if not cur.get("doi") and rec.get("doi"):
                        cur["doi"] = rec["doi"]
            query_log.append(entry)
            if interleave_sleep:
                time.sleep(interleave_sleep)

    pool = list(merged.values())
    # 离线粗排：记录文本 vs 各面文本的 TF-IDF 余弦，取命中面中的最大者。
    # 只作召回排序（约束 3），不进判定。
    facet_names = list(ALL_FACET_TAGS)
    corpus = [ftexts[f] for f in facet_names] + [
        f"{r.get('title') or ''} {r.get('_abstract_full') or ''}" for r in pool
    ]
    vectors = tfidf_vectors(corpus)
    facet_vecs = {f: vectors[i] for i, f in enumerate(facet_names)}
    for j, rec in enumerate(pool):
        rvec = vectors[len(facet_names) + j]
        sims = {f: cosine(rvec, facet_vecs[f]) for f in rec["hit_facets"]}
        best = max(sims, key=sims.get) if sims else WHOLE
        rec["similarity"] = round(sims.get(best, 0.0), 4)
        rec["best_facet"] = best
        rec["facet_similarities"] = {f: round(s, 4) for f, s in sims.items()}
    pool.sort(key=lambda r: (-r["similarity"], normalize_title(r.get("title"))))
    return {"pool": pool, "query_log": query_log,
            "source_status": source_status}


def known_blind_spots(source_status: dict, pool: list[dict],
                      queries: list[dict]) -> list[str]:
    """已知盲区声明：源级失败 + 面级零命中 + 固定口径声明。"""
    spots: list[str] = []
    for source in SOURCES:
        st = source_status.get(source) or {}
        if st.get("errors") and not st.get("ok"):
            first = st["errors"][0]["error"]
            spots.append(
                f"{SOURCE_LABELS[source]} 本次全部查询失败（{first}）："
                f"该源独有覆盖可能漏检，本次结论须视为覆盖不全")
        elif st.get("errors"):
            spots.append(
                f"{SOURCE_LABELS[source]} 部分查询失败（{len(st['errors'])} 条，"
                f"如：{st['errors'][0]['error']}）：覆盖可能不完整")
    hit_facets = {f for rec in pool for f in rec.get("hit_facets", [])}
    for facet in FACETS:
        if facet not in hit_facets:
            spots.append(
                f"{facet} 面零命中：可能是真空，也可能是查询式未命中该面的"
                f"表述方式，判定者须知悉，不得据此单独下结论")
    spots.append("检索基于题名/摘要级元数据，未做全文比对：只在全文细节"
                 "处撞车的论文可能漏检")
    spots.append("相似度为离线文本粗排，仅作召回排序，不是判定依据（约束 3）")
    return spots


# ---------------------------------------------------------------------------
# 4. prepare：证据包落盘 + 卡的 search_scope 回填

def novelty_dir(root: Path, idea_id: str) -> Path:
    return root / "novelty" / idea_id


def prepare(root: Path, card: dict, *,
            per_query: int = DEFAULT_PER_QUERY,
            sources: tuple[str, ...] = SOURCES,
            interleave_sleep: float = 0.0,
            date: str | None = None) -> dict:
    """跑取证：构式 → 实查 → 证据包落盘 → 回填卡的 search_scope。

    就地修改 card 的 novelty.search_scope 与 evidence_package（调用方
    负责 save_card）。返回汇总 dict（池规模、源状态、盲区、落盘路径）。
    """
    date = date or today()
    queries = build_queries(card)
    if not queries:
        raise NoveltyError(["无法从卡的 facet 区构造任何检索式："
                            "facet 短语与题名均为空，先补齐想法卡"])
    result = collect_pool(card, queries, per_query=per_query,
                          sources=sources, interleave_sleep=interleave_sleep)
    pool, source_status = result["pool"], result["source_status"]
    spots = known_blind_spots(source_status, pool, queries)

    nd = novelty_dir(root, card["idea_id"])
    nd.mkdir(parents=True, exist_ok=True)
    evidence_path = nd / "evidence.jsonl"
    with open(evidence_path, "w", encoding="utf-8") as f:
        for rec in pool:
            f.write(json.dumps({
                "source": rec["sources"][0] if rec["sources"] else rec["source"],
                "sources": rec["sources"],
                "source_id": rec["source_id"],
                "title": rec["title"],
                "authors": rec["authors"],
                "year": rec["year"],
                "doi": rec["doi"],
                "venue": rec["venue"],
                "url": rec["url"],
                "hit_facets": rec["hit_facets"],
                "best_facet": rec["best_facet"],
                "similarity": rec["similarity"],
                "facet_similarities": rec["facet_similarities"],
                "abstract_snippet": (rec.get("_abstract_full") or "")[
                    :_ABSTRACT_SNIPPET_CHARS],
            }, ensure_ascii=False) + "\n")
    queries_path = nd / "queries.json"
    queries_path.write_text(json.dumps({
        "idea_id": card["idea_id"], "date": date, "per_query": per_query,
        "queries": queries, "log": result["query_log"],
    }, ensure_ascii=False, indent=1), encoding="utf-8")

    report_path = nd / "pool_report.md"
    report_path.write_text(_render_pool_report(
        card, date, queries, result, spots), encoding="utf-8")

    nov = card.setdefault("novelty", {})
    nov["search_scope"] = {
        "sources": list(sources),
        "pool_size": len(pool),
        "known_blind_spots": "；".join(spots),
    }
    nov["evidence_package"] = f"novelty/{card['idea_id']}/"
    card["updated"] = date
    return {
        "idea_id": card["idea_id"],
        "date": date,
        "pool_size": len(pool),
        "raw_source_hits": sum(s["hits"] for s in source_status.values()),
        "query_count": len(queries),
        "source_status": source_status,
        "blind_spots": spots,
        "evidence_path": str(evidence_path),
        "pool_report_path": str(report_path),
        "queries_path": str(queries_path),
        "any_source_ok": any(s["ok"] for s in source_status.values()),
    }


def _render_pool_report(card: dict, date: str, queries: list[dict],
                        result: dict, spots: list[str]) -> str:
    pool, status = result["pool"], result["source_status"]
    L: list[str] = []
    L.append(f"# 查新证据池报告 — {card['idea_id']}")
    L.append("")
    L.append(f"> 日期：{date} ｜ 想法：{card.get('title')}")
    L.append("> 本报告是查新判定的证据底稿：判定只能引用证据包"
             "（evidence.jsonl）中真实存在的论文；相似度只作召回排序。")
    L.append("")
    L.append("## 查询式（逐面构造）")
    L.append("")
    L.append("| 面 | 式型 | 查询式 |")
    L.append("|---|---|---|")
    for q in queries:
        L.append(f"| {q['facet']} | {q['kind']} | {q['text']} |")
    L.append("")
    L.append("## 各源状态（如实记录，单源失败不中断）")
    L.append("")
    L.append("| 源 | 状态 | 原始命中 | 失败条数 |")
    L.append("|---|---|---|---|")
    for source in SOURCES:
        st = status.get(source) or {}
        state = "可用" if st.get("ok") else "不可用"
        L.append(f"| {SOURCE_LABELS[source]} | {state} | {st.get('hits', 0)}"
                 f" | {len(st.get('errors', []))} |")
    for source in SOURCES:
        for e in (status.get(source) or {}).get("errors", []):
            L.append(f"- ⚠️ {SOURCE_LABELS[source]} 失败：查询「{e['query']}」"
                     f"→ {e['error']}")
    L.append("")
    raw = sum(s["hits"] for s in status.values())
    by_facet = {f: 0 for f in ALL_FACET_TAGS}
    for rec in pool:
        for f in rec["hit_facets"]:
            by_facet[f] += 1
    L.append("## 池规模")
    L.append("")
    L.append(f"- 原始命中合计（未去重）：{raw}")
    L.append(f"- 去重后证据池：{len(pool)} 条")
    for f in ALL_FACET_TAGS:
        L.append(f"- 命中 {f} 面的记录：{by_facet[f]} 条")
    L.append("")
    L.append("## 粗排 Top 15（相似度只作召回排序，不作判定依据）")
    L.append("")
    for rec in pool[:15]:
        doi = f" DOI:{rec['doi']}" if rec.get("doi") else ""
        L.append(f"- [{rec['similarity']}] ({', '.join(rec['hit_facets'])}) "
                 f"{rec['title']}（{rec.get('year') or '年份缺'}）{doi}")
    if not pool:
        L.append("（池为空）")
    L.append("")
    L.append("## 已知盲区声明")
    L.append("")
    for s in spots:
        L.append(f"- {s}")
    L.append("")
    return "\n".join(L)


def load_pool(root: Path, idea_id: str) -> list[dict]:
    """读回 evidence.jsonl（verdict 的池存在性核查以落盘证据为准）。"""
    path = novelty_dir(root, idea_id) / "evidence.jsonl"
    if not path.exists():
        raise NoveltyError([
            f"证据包不存在：{path}——先跑 novelty prepare 生成证据包，"
            f"不许无证据落判定"])
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def _in_pool(work: dict, pool: list[dict]) -> dict | None:
    """判定一篇被引工作是否真实存在于证据池：DOI 精确匹配优先，
    其次 source_id == paper_id，最后规范化题名精确匹配。"""
    doi = normalize_doi(work.get("doi"))
    pid = (work.get("paper_id") or "").strip()
    title_n = normalize_title(work.get("title"))
    for rec in pool:
        if doi and rec.get("doi") and normalize_doi(rec["doi"]) == doi:
            return rec
        if pid and rec.get("source_id") == pid:
            return rec
        if title_n and normalize_title(rec.get("title")) == title_n:
            return rec
    return None


# ---------------------------------------------------------------------------
# 5. verdict：判定落卡（判定纪律在代码中的落点）

def make_verdict_id(idea_id: str, date: str, judge_model: str | None,
                    verdict: str) -> str:
    """收据 verdict_id 生成规则：NV-<sha256(idea|日期|判定模型|结论)[:10]>。

    确定性可复现：同一判定事件（卡、日期、判定者、结论）恒得同一 id，
    换判定者/结论/日期即换 id；一期定版门只要求其非空且与收据一同落盘。
    """
    raw = f"{idea_id}|{date}|{judge_model or 'REVIEW_UNAVAILABLE'}|{verdict}"
    return "NV-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:10]


def apply_verdict(root: Path, card: dict, verdict_data: dict, *,
                  date: str | None = None) -> dict:
    """校验并把判定写入卡的查新证据区 + 收据落盘。失败抛 NoveltyError。

    verdict_data 字段：
      verdict（必填）、caution_reason、closest_works[]、named_paper、
      judge_model / judge_family / executor_model / executor_family、
      review_unavailable（bool）。
    就地修改 card（调用方 save_card）。返回落盘的收据 dict。
    """
    date = date or today()
    errs: list[str] = []
    verdict = verdict_data.get("verdict")
    if verdict not in VERDICTS:
        errs.append(f"verdict 非法：{verdict!r}（须为 {VERDICTS} 之一）")
    review_unavailable = bool(verdict_data.get("review_unavailable"))

    # —— 跨模型硬门：判定者与执行者必须不同家族（约束 1）
    judge_model = verdict_data.get("judge_model")
    executor_model = verdict_data.get("executor_model")
    judge_family = (verdict_data.get("judge_family") or "").strip().lower() \
        or model_family(judge_model or "")
    executor_family = (verdict_data.get("executor_family") or "").strip().lower() \
        or model_family(executor_model or "")
    if not review_unavailable:
        if not _nonempty_str(judge_model):
            errs.append("缺 judge_model：无判定者不许落判定（自评不当闸门，约束 1）")
        if not _nonempty_str(executor_model):
            errs.append("缺 executor_model：收据须同时登记执行者模型")
        if judge_family and executor_family and judge_family == executor_family:
            errs.append(
                f"判定者与执行者同属一个模型家族（{judge_family}）："
                f"自审判无效，拒绝落卡——须换另一家族模型判定，"
                f"或在确实不可得时用 --review-unavailable 显式降级")

    # —— CAUTION 必须说清 delta 薄在哪（拍板 9.1-A）
    caution_reason = (verdict_data.get("caution_reason") or "").strip()
    if verdict == "PROCEED_WITH_CAUTION" and not caution_reason:
        errs.append("PROCEED_WITH_CAUTION 须附 caution_reason：delta 薄在哪"
                    "必须说清，说不出就是 PROCEED（拍板 9.1-A）")

    # —— 证据池存在性：一切被引工作必须真实在池（无证据不许落判定）
    pool: list[dict] = []
    try:
        pool = load_pool(root, card["idea_id"])
    except NoveltyError as exc:
        errs.extend(exc.errors)

    closest_in = verdict_data.get("closest_works") or []
    closest_out: list[dict] = []
    if not isinstance(closest_in, list):
        errs.append("closest_works 必须是列表（结构化文件传入）")
        closest_in = []
    for i, w in enumerate(closest_in):
        if not isinstance(w, dict):
            errs.append(f"closest_works[{i}] 不是结构化记录")
            continue
        if not _ref_ok(w):
            errs.append(f"closest_works[{i}] 必须带 paper_id 或 doi（不许裸文本）")
        facets_hit = w.get("collided_facets")
        if not isinstance(facets_hit, list) or not facets_hit:
            errs.append(f"closest_works[{i}] 缺 collided_facets：判定必须逐面"
                        f"举证——撞了哪一面（{list(FACETS)}）须逐项列明")
        else:
            bad = [f for f in facets_hit if f not in FACETS]
            if bad:
                errs.append(f"closest_works[{i}] collided_facets 含非法面：{bad}"
                            f"（只许 {list(FACETS)}；whole 是召回层，不许作撞车面）")
        if not _nonempty_str(w.get("delta")):
            errs.append(f"closest_works[{i}] 缺 delta：与该在先工作的差异点"
                        f"必须逐条写明，没有 delta 的撞车陈述不成立")
        if pool and _ref_ok(w) and _in_pool(w, pool) is None:
            errs.append(f"closest_works[{i}]（{w.get('title') or w.get('doi') or w.get('paper_id')}）"
                        f"不在证据池中：判定只能引用 prepare 实查到的论文，"
                        f"池外论文不许进判定区（如确为漏检，先补查再落判定）")
        closest_out.append({
            "paper_id": w.get("paper_id"),
            "doi": normalize_doi(w.get("doi")) or w.get("doi"),
            "title": w.get("title") or "",
            "year": w.get("year"),
            "collided_facets": facets_hit,
            "delta": (w.get("delta") or "").strip(),
            "verified": bool(w.get("verified", False)),
        })

    # —— ABANDON 必须点名在先论文且在池中（判定宪法，拍板 9.1-A）
    named = verdict_data.get("named_paper")
    named_entry = None
    if verdict == "ABANDON":
        if not _ref_ok(named if isinstance(named, dict) else {}):
            errs.append("ABANDON 必须点名在先论文：named_paper 须带 paper_id "
                        "或 doi——点不出论文不许 ABANDON（拍板 9.1-A）")
        elif pool and _in_pool(named, pool) is None:
            errs.append("ABANDON 点名的论文不在证据池中：点名必须指向 prepare "
                        "实查到的论文，不许凭印象点名")
        else:
            named_entry = named
            in_closest = any(
                (normalize_doi(c.get("doi")) and normalize_doi(c.get("doi")) == normalize_doi(named.get("doi")))
                or (c.get("paper_id") and c.get("paper_id") == named.get("paper_id"))
                or (normalize_title(c.get("title")) and normalize_title(c.get("title")) == normalize_title(named.get("title")))
                for c in closest_out
            )
            if not in_closest:
                errs.append("ABANDON 点名论文必须同时列入 closest_works 并逐面"
                            "举证（collided_facets + delta），否则点名无据")

    if errs:
        raise NoveltyError(errs)

    verdict_id = make_verdict_id(card["idea_id"], date, judge_model, verdict)
    receipt = {
        "verdict_id": verdict_id,
        "judge_model": judge_model if not review_unavailable else None,
        "judge_family": judge_family if not review_unavailable else None,
        "executor_model": executor_model,
        "executor_family": executor_family or None,
    }
    nov = card.setdefault("novelty", {})
    nov["verdict"] = verdict
    nov["caution_reason"] = caution_reason if verdict == "PROCEED_WITH_CAUTION" else ""
    nov["closest_works"] = closest_out
    nov["receipt"] = receipt
    nov["review_status"] = "REVIEW_UNAVAILABLE" if review_unavailable else "ok"
    nov["checked_at"] = date
    if not nov.get("evidence_package"):
        nov["evidence_package"] = f"novelty/{card['idea_id']}/"
    if verdict == "ABANDON":
        nov["abandon_named_paper"] = {
            "paper_id": named_entry.get("paper_id"),
            "doi": normalize_doi(named_entry.get("doi")) or named_entry.get("doi"),
            "title": named_entry.get("title") or "",
            "year": named_entry.get("year"),
        }
    card["updated"] = date

    nd = novelty_dir(root, card["idea_id"])
    nd.mkdir(parents=True, exist_ok=True)
    record = {
        "idea_id": card["idea_id"],
        "date": date,
        "verdict": verdict,
        "caution_reason": nov["caution_reason"],
        "closest_works": closest_out,
        "named_paper": nov.get("abandon_named_paper"),
        "receipt": receipt,
        "review_status": nov["review_status"],
        "pool_size": (nov.get("search_scope") or {}).get("pool_size"),
    }
    (nd / "verdict.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8")
    return record
