"""先例路引擎（JS-04 / JS-05，学 sci-select similar_works.py 工程形态）。

主路证据 = 「近 5 年同题论文实际发在哪」的去向统计：
指纹检索式 → OpenAlex works 检索 → 按 primary_location.source
聚合到期刊 → 按刊同期发文量归一化（rate_per_10k）→ 入门门槛
入池；每刊保留 ≤5 篇真实先例（题名+年份+DOI 可复核）。

纪律：
- 原始响应逐查询落 evidence/ 留痕，查询参数与日期登记进
  precedent_runs；网络失败如实落 failed，不编造、不静默跳过。
- Jane 局限的移植修正（JS-05）：语料换 OpenAlex 全学科（CC0）、
  窗口近 5 年、相似度按刊发文量归一化，不用相似度和裸排序。
- 可选 Key（JS-11）：环境变量 OPENALEX_API_KEY 在场时
  live_fetcher 以 api_key 查询参数带上（匿名走共享免费日
  预算，耗尽时 429 如实落 failed）；Key 只许存在于进程内存
  与请求线，**不许出现在任何落盘文件、日志与异常消息里**——
  落痕 URL 经 redact_url、异常文本经 redact_text 脱敏，
  测试钉死（tests/test_api_key.py）。
"""

from __future__ import annotations

import json
import os
import re
import urllib.parse
import urllib.request
from pathlib import Path

from . import schema
from .gates import GateError, require_selection
from .project import FILES, find_candidate, new_candidate, save_selection
from .util import dump_json, normalize_name, sha256_text, today


def window_for(today_str: str) -> dict:
    """近 WINDOW_YEARS 年窗口（含当年），由查询日期推。"""
    year = int(str(today_str)[:4])
    return {"from": f"{year - schema.WINDOW_YEARS + 1}-01-01",
            "to": f"{year}-12-31"}


def works_url(query: str, window: dict) -> str:
    params = {
        "search": query,
        "filter": (f"from_publication_date:{window['from']},"
                   f"to_publication_date:{window['to']},"
                   f"type:{'|'.join(schema.RESEARCH_TYPES)}"),
        "per-page": str(schema.PER_QUERY_LIMIT),
    }
    return f"{schema.OPENALEX_BASE}/works?{urllib.parse.urlencode(params)}"


def volume_url(source_id: str, window: dict) -> str:
    """刊同期发文量（归一化分母）：同刊同窗口 works 总数。"""
    short = source_id.rsplit("/", 1)[-1]
    params = {
        "filter": (f"primary_location.source.id:{short},"
                   f"from_publication_date:{window['from']},"
                   f"to_publication_date:{window['to']}"),
        "per-page": "1",
    }
    return f"{schema.OPENALEX_BASE}/works?{urllib.parse.urlencode(params)}"


REDACTED = "REDACTED"
_API_KEY_PARAM_RE = re.compile(r"(api_key=)[^&\s\"'\)\]]+")


def api_key_from_env() -> str | None:
    """读可选 OpenAlex API Key（JS-11：用户自备、只经环境注入）。

    返回值是凭据：只许在本进程内拼请求 URL，不许写进任何
    文件、日志或异常消息（落痕一律走 redact_url / redact_text）。
    """
    return os.environ.get("OPENALEX_API_KEY") or None


def with_api_key(url: str, key: str) -> str:
    """给 URL 追加 api_key 查询参数（其余参数逐字保留）。

    参数值不做百分号编码：Key 或为 OpenAlex 的简单令牌，
    或为运行时代理凭据（hsurr: 前缀），编码会破坏后者的
    原文形态；两种形态都不含 & / 空格等分隔符。
    """
    base, sep, query = str(url).partition("?")
    params = [p for p in query.split("&")
              if p and not p.startswith("api_key=")] if sep else []
    params.append(f"api_key={key}")
    return base + "?" + "&".join(params)


def redact_url(url: str) -> str:
    """落痕用 URL 脱敏：api_key 参数值替换为 REDACTED，
    其余部分逐字保留；无该参数时原样返回。"""
    text = str(url)
    if "api_key=" not in text:
        return text
    base, _, query = text.partition("?")
    params = [f"api_key={REDACTED}" if p.startswith("api_key=") else p
              for p in query.split("&")]
    return base + "?" + "&".join(params)


def redact_text(text, key: str | None = None) -> str:
    """文本脱敏（异常消息/日志落盘前必过）：api_key= 参数形态
    与 Key 原值（含 URL 编码形态）一律替换为 REDACTED。"""
    out = _API_KEY_PARAM_RE.sub(r"\g<1>" + REDACTED, str(text))
    key = key if key is not None else api_key_from_env()
    if key:
        out = out.replace(key, REDACTED)
        encoded = urllib.parse.quote(key, safe="")
        if encoded != key:
            out = out.replace(encoded, REDACTED)
    return out


def live_fetcher(url: str) -> dict:
    """实时取 OpenAlex JSON。OPENALEX_API_KEY 在场时以 api_key
    参数带上；匿名时走共享免费预算（429 等失败由调用方如实
    落痕）。本函数只许被喂 OpenAlex 的 URL——Key 不许随手
    漏给第三方站点。"""
    key = api_key_from_env()
    if key:
        url = with_api_key(url, key)
    req = urllib.request.Request(
        url, headers={"User-Agent": "light-journal-select/0.1"})
    with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
        return json.loads(resp.read().decode("utf-8"))


def aggregate(responses: list[dict]) -> dict:
    """按刊聚合多条检索式的 works 响应（只含期刊型来源）。

    responses[i] 对应第 i 条检索式（顺序即名次口径）。返回
    {source_key: 聚合块}；source_key 优先 OpenAlex source id，
    缺失时退化为归一刊名。来源类型过滤（JS-D03）的分流在
    _aggregate_all，本函数保持「只回期刊池」的既有口径。
    """
    journals, _ = _aggregate_all(responses)
    return journals


def _aggregate_all(responses: list[dict]):
    """聚合全实现：返回 (期刊聚合 dict, 来源类型排除列表)。

    来源 type 明确非 journal 者（repository 等）不入期刊池，
    逐个来源落一条排除附记素材（JS-D03：留痕不静默丢弃）；
    type 缺失者按 journal 处置。聚合块同时带 OpenAlex 源事实
    （type / is_in_doaj / is_oa / listed_in，JS-09 白名单证据）。
    """
    journals: dict[str, dict] = {}
    type_excluded: dict[str, dict] = {}
    for qi, payload in enumerate(responses):
        results = (payload or {}).get("results") or []
        for rank, work in enumerate(results, start=1):
            if work.get("is_retracted"):
                continue  # 撤稿不作先例
            if work.get("type") and \
                    work["type"] not in schema.RESEARCH_TYPES:
                continue
            location = work.get("primary_location") or {}
            source = location.get("source") or {}
            name = source.get("display_name")
            if not name:
                continue
            key = source.get("id") or f"name:{normalize_name(name)}"
            source_type = source.get("type")
            if source_type is not None and \
                    source_type != schema.JOURNAL_SOURCE_TYPE:
                bucket = type_excluded.setdefault(key, {
                    "source_id": source.get("id"),
                    "name": name,
                    "source_type": source_type,
                    "works": {},
                    "queries": set(),
                })
                work_id = work.get("id") or work.get("doi") or \
                    f"{work.get('title')}|{work.get('publication_year')}"
                bucket["works"].setdefault(work_id, True)
                bucket["queries"].add(qi)
                continue
            entry = journals.setdefault(key, {
                "source_id": source.get("id"),
                "name": name,
                "issn": source.get("issn_l"),
                "issn_list": source.get("issn") or [],
                "publisher": (source.get("host_organization_name")
                              or work.get("primary_location", {})
                              .get("source", {}).get("host_organization_name")),
                "homepage_url": source.get("homepage_url"),
                "source_type": source_type,
                "is_in_doaj": source.get("is_in_doaj"),
                "is_oa": source.get("is_oa"),
                "listed_in": source.get("listed_in") or [],
                "works": {},          # openalex work id -> 先例条目（去重）
                "queries": set(),
                "best_rank": None,
            })
            # 源事实以先到记录为准，后到响应只补空缺（同一源记录）
            for fact_key in ("is_in_doaj", "is_oa"):
                if entry[fact_key] is None:
                    entry[fact_key] = source.get(fact_key)
            if not entry["listed_in"] and source.get("listed_in"):
                entry["listed_in"] = source.get("listed_in")
            work_id = work.get("id") or work.get("doi") or \
                f"{work.get('title')}|{work.get('publication_year')}"
            if work_id not in entry["works"]:
                entry["works"][work_id] = {
                    "title": work.get("display_name") or work.get("title"),
                    "year": work.get("publication_year"),
                    "doi": work.get("doi"),
                    "openalex_id": work.get("id"),
                }
            entry["queries"].add(qi)
            if entry["best_rank"] is None or rank < entry["best_rank"]:
                entry["best_rank"] = rank
    exclusions = [{
        "name": b["name"],
        "source_id": b["source_id"],
        "source_type": b["source_type"],
        "similar_works_n": len(b["works"]),
        "queries_covered": len(b["queries"]),
        "reason": f"来源类型为 {b['source_type']}，非期刊"
                  "（JS-D03 来源类型过滤），不入期刊候选池",
    } for b in type_excluded.values()]
    return journals, exclusions


def passes_entry(stats: dict) -> bool:
    """入门门槛（JS-04）：防单篇偶合。"""
    return (stats["similar_works_n"] >= schema.ENTRY_MIN_SIMILAR
            or stats["queries_covered"] >= schema.ENTRY_MIN_QUERIES
            or (stats["best_rank"] is not None
                and stats["best_rank"] <= schema.ENTRY_TOP_RANK))


# ------------------------------------------------------------ 官网回填（JS-D02）

def source_detail_url(source_id: str) -> str:
    """OpenAlex 源记录详情 URL（全量记录含 homepage_url）。"""
    short = source_id.rsplit("/", 1)[-1]
    return f"{schema.OPENALEX_BASE}/sources/{short}"


def doaj_journal_url(issn: str) -> str:
    """DOAJ 按 ISSN 查登记记录 URL（bibjson.link 含 homepage）。"""
    return f"https://doaj.org/api/journals/issn/{issn}"


def _doaj_homepage(payload) -> str | None:
    """从 DOAJ 检索响应里取登记的期刊 homepage 链接。"""
    results = (payload or {}).get("results") or []
    for item in results:
        links = ((item or {}).get("bibjson") or {}).get("link") or []
        for link in links:
            if isinstance(link, dict) and link.get("type") == "homepage" \
                    and link.get("url"):
                return link["url"]
    return None


def backfill_homepages(selection: dict, fetcher,
                       today_str: str) -> dict:
    """官网 URL 回填（JS-D02）：给缺 homepage_url 的先例候选补链。

    OpenAlex works 的脱水源记录不含 homepage_url（v1.0 实测恒
    缺），官网 scope 核对与 check-record H 组都断在这一步。
    通道序：OpenAlex /sources/{id} 全量记录 → DOAJ 按 ISSN 查
    登记页链接（只认登记源，不跟随期刊自家「验证页」，JS-09）。
    逐通道尝试留痕；全失败落 unconfirmed 不猜。返回
    {刊名: filled|unconfirmed|skipped} 摘要。
    """
    summary: dict[str, str] = {}
    for cand in selection.get("candidates") or []:
        if cand.get("source") != "precedent" or cand.get("homepage_url"):
            continue
        attempts: list[dict] = []
        filled = None  # (value, channel, evidence_url)
        source_id = cand.get("openalex_source_id")
        if source_id:
            url = source_detail_url(source_id)
            try:
                payload = fetcher(url)
                hp = (payload or {}).get("homepage_url")
                attempts.append({
                    "channel": "openalex_source_detail",
                    "status": "succeeded" if hp else "attempted",
                    "evidence_url": redact_url(url),
                    "note": None if hp else "源记录详情无 homepage_url",
                })
                if hp:
                    filled = (hp, "openalex_source_detail", url)
            except Exception as exc:  # 取不到如实落痕，不猜
                attempts.append({
                    "channel": "openalex_source_detail",
                    "status": "attempted",
                    "evidence_url": redact_url(url),
                    "note": redact_text(
                        f"{type(exc).__name__}: {exc}")[:200],
                })
        issn = cand.get("issn")
        if filled is None and issn:
            url = doaj_journal_url(issn)
            try:
                payload = fetcher(url)
                hp = _doaj_homepage(payload)
                attempts.append({
                    "channel": "doaj_registry",
                    "status": "succeeded" if hp else "attempted",
                    "evidence_url": url,
                    "note": None if hp else "DOAJ 登记无 homepage 链接",
                })
                if hp:
                    filled = (hp, "doaj_registry", url)
            except Exception as exc:
                attempts.append({
                    "channel": "doaj_registry",
                    "status": "attempted",
                    "evidence_url": url,
                    "note": redact_text(
                        f"{type(exc).__name__}: {exc}")[:200],
                })
        if filled is not None:
            value, channel, ev_url = filled
            cand["homepage_url"] = value
            cand["homepage_backfill"] = {
                "status": "filled", "value": value, "channel": channel,
                "evidence_url": redact_url(ev_url),
                "queried_at": today_str, "attempts": attempts,
            }
            summary[cand.get("name")] = "filled"
        elif attempts:
            cand["homepage_backfill"] = {
                "status": "unconfirmed", "value": None, "channel": None,
                "evidence_url": None, "queried_at": today_str,
                "attempts": attempts,
            }
            summary[cand.get("name")] = "unconfirmed"
        else:
            summary[cand.get("name")] = "skipped"
    return summary


def run_precedent(root, fetcher=None, today_str: str | None = None) -> dict:
    """执行先例路：逐式查询、落痕、聚合、归一化、入池。

    fetcher(url) -> dict 可注入（离线测试用 fixture）；缺省走
    OpenAlex 实时 API。任一查询失败如实登记 failed 并继续其余
    查询；全部失败则报错且状态不动（不许拿空池冒充已生成）。
    """
    root = Path(root)
    selection = require_selection(root)
    queries = selection.get("queries") or []
    if not queries:
        raise GateError(["指纹检索式为空（先 fingerprint 落 2–3 条检索式）"])
    fetcher = fetcher or live_fetcher
    today_str = today_str or today()
    window = window_for(today_str)
    evidence_dir = root / FILES["evidence_dir"]
    evidence_dir.mkdir(exist_ok=True)

    responses: list[dict] = []
    run_rows = []
    ok_queries = 0
    for qi, query in enumerate(queries):
        url = works_url(query, window)
        row = {"query_index": qi, "query": query, "url": redact_url(url),
               "window": window, "queried_at": today_str,
               "status": "failed", "works_returned": 0,
               "evidence_file": None, "error": None}
        try:
            payload = fetcher(url)
        except Exception as exc:  # 网络失败如实落痕，不编造
            # 异常文本可能内嵌带 Key 的请求 URL：落盘前先脱敏
            row["error"] = redact_text(f"{type(exc).__name__}: {exc}")
            run_rows.append(row)
            responses.append({})
            continue
        fname = f"openalex-q{qi}-{today_str}-{sha256_text(url)[:8]}.json"
        dump_json(evidence_dir / fname, payload)
        row.update({"status": "succeeded",
                    "works_returned": len(payload.get("results") or []),
                    "evidence_file": f"{FILES['evidence_dir']}/{fname}"})
        run_rows.append(row)
        responses.append(payload)
        ok_queries += 1
    selection.setdefault("precedent_runs", []).extend(run_rows)
    if ok_queries == 0:
        save_selection(root, selection)
        raise GateError(["先例路全部查询失败（见 precedent_runs 留痕），"
                         "未生成任何候选；检查网络后重跑"])

    journals, type_exclusions = _aggregate_all(responses)
    for row in type_exclusions:
        row["queried_at"] = today_str
    selection.setdefault("source_type_exclusions", []).extend(
        type_exclusions)
    admitted, near_misses = [], []
    for key, entry in journals.items():
        similar_n = len(entry["works"])
        volume = None
        volume_status = "skipped"
        if entry["source_id"]:
            try:
                vpayload = fetcher(volume_url(entry["source_id"], window))
                volume = (vpayload.get("meta") or {}).get("count")
                volume_status = "succeeded" if volume is not None \
                    else "attempted"
            except Exception:
                volume_status = "attempted"  # 分母取不到：rate 留空，不猜
        rate = (similar_n / volume * 10000
                if volume else None)
        stats = {
            "similar_works_n": similar_n,
            "rate_per_10k": (round(rate, 2) if rate is not None else None),
            "journal_volume_window": volume,
            "volume_status": volume_status,
            "queries_covered": len(entry["queries"]),
            "best_rank": entry["best_rank"],
            "window": window,
            "queried_at": today_str,
            "precedents": sorted(
                entry["works"].values(),
                key=lambda w: (-(w["year"] or 0), w["title"] or ""),
            )[:schema.MAX_PRECEDENTS_PER_JOURNAL],
        }
        if passes_entry(stats):
            admitted.append((entry, stats))
        else:
            near_misses.append({"name": entry["name"],
                                "source_id": entry["source_id"],
                                "similar_works_n": similar_n,
                                "queries_covered": stats["queries_covered"],
                                "best_rank": entry["best_rank"],
                                "queried_at": today_str,
                                "reason": "未过入门门槛（相似数/多式覆盖/"
                                          "单式名次均不足）"})
    for entry, stats in admitted:
        cand = find_candidate(selection, entry["name"])
        if cand is None:
            cand = new_candidate(entry["name"], "precedent")
            selection.setdefault("candidates", []).append(cand)
        cand["openalex_source_id"] = entry["source_id"]
        cand["issn"] = cand["issn"] or entry["issn"]
        cand["publisher"] = cand["publisher"] or entry["publisher"]
        cand["homepage_url"] = cand["homepage_url"] or entry["homepage_url"]
        cand["source_facts"] = {
            "type": entry.get("source_type"),
            "is_in_doaj": entry.get("is_in_doaj"),
            "is_oa": entry.get("is_oa"),
            "listed_in": entry.get("listed_in") or [],
            "queried_at": today_str,
        }
        cand["precedent"] = stats
    selection.setdefault("precedent_near_misses", []).extend(near_misses)
    backfill_summary = backfill_homepages(selection, fetcher, today_str)
    save_selection(root, selection)

    advanced = None
    if selection.get("candidates") and selection.get("status") == "draft":
        from .gates import advance_to
        advance_to(root, "candidates_ready", by="light-journal-select precedent")
        advanced = "candidates_ready"
    return {"queries_ok": ok_queries, "queries_total": len(queries),
            "admitted": [e["name"] for e, _ in admitted],
            "near_misses": [m["name"] for m in near_misses],
            "source_type_excluded": [r["name"] for r in type_exclusions],
            "homepage_backfill": backfill_summary,
            "status": advanced or selection.get("status")}
