"""I1 演进链算子的素材工具（三期）：按种子 DOI 拉引文邻居落盘成链素材。

设计依据：02-idea/LEARNING.md §2（演进链算子：双向生长、逐节相关性门、
高被引源头停止）+ REDESIGN-DRAFT §3 I1。

本模块只做「取材」一件确定性的事：给定种子论文 DOI，从公开 API 拉它
的参考文献（backward）与施引文献（forward）邻居清单，落盘成链素材
（chains/<chain_id>/）。**不做自动生成**——建链（逐节点抽 {想法一句话,
实验, 实体, 参考文献} 四元组、相关性门每步保留 3–5、链尾外推生成候选）
是智能体按 SKILL.md 第 9 节规程执行的工作，工具不许代劳、更不许假装。

生长方式：一张演进链由一个根种子定义（chain_id 由根种子 DOI 确定性
生成）；对链上选定节点再跑本命令并以 --chain-id 指回同一链，即把该
节点的邻居作为新一跳素材并入同一链目录（每条邻居的 hop_of 字段
恒记为「被展开的那个节点的 DOI」，由工具自动决定、不许人工指定，
防归因错位），节点取舍仍归智能体的相关性门。

源与失败口径（与 novelty.prepare 一致）：OpenAlex / Semantic Scholar /
Crossref 三源免 Key 实查；单源失败只记状态，不中断其余源，不假装查全；
三源全灭时抛 ChainError，CLI 返回 1。HTTP 只用标准库 urllib；测试通过
monkeypatch 本模块的 `_http_get_json` 实现 mock，禁止真联网。
"""

from __future__ import annotations

import hashlib
import json
import re
import urllib.parse
from pathlib import Path

from .novelty import SourceError, _http_get_json, normalize_doi, normalize_title
from .util import today

SOURCES = ("openalex", "semanticscholar", "crossref")
SOURCE_LABELS = {
    "openalex": "OpenAlex",
    "semanticscholar": "Semantic Scholar",
    "crossref": "Crossref",
}
DIRECTIONS = ("references", "cited_by")  # backward（种子引用的）/ forward（引用种子的）
DIRECTION_LABELS = {"references": "参考文献（向后）", "cited_by": "施引文献（向前）"}

DEFAULT_PER_DIRECTION = 25
_ABSTRACT_SNIPPET_CHARS = 400


class ChainError(Exception):
    """链素材抓取失败。errors 为逐条人读原因。"""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("；".join(errors))


def make_chain_id(seed_doi: str) -> str:
    """chain_id = CH-<sha256(规范化种子 DOI)[:8]>，确定性可复现。"""
    norm = normalize_doi(seed_doi) or (seed_doi or "").strip().lower()
    return "CH-" + hashlib.sha256(norm.encode("utf-8")).hexdigest()[:8]


def chain_dir(root: Path, chain_id: str) -> Path:
    return root / "chains" / chain_id


# ---------------------------------------------------------------------------
# 统一邻居记录：{direction, title, authors, year, doi, venue,
#               cited_by_count, abstract, source, source_id}

def _record(source: str, direction: str, **kw) -> dict:
    return {
        "direction": direction,
        "source": source,
        "source_id": str(kw.get("source_id") or ""),
        "title": (kw.get("title") or "").strip(),
        "authors": [a for a in (kw.get("authors") or []) if a],
        "year": kw.get("year"),
        "doi": normalize_doi(kw.get("doi")),
        "venue": (kw.get("venue") or "").strip(),
        "cited_by_count": kw.get("cited_by_count"),
        "abstract": (kw.get("abstract") or "").strip(),
    }


def _openalex_abstract(inverted) -> str:
    if not inverted:
        return ""
    positions: dict[int, str] = {}
    for word, idxs in inverted.items():
        for i in idxs:
            positions[i] = word
    return " ".join(positions[i] for i in sorted(positions))


def _openalex_record(w: dict, direction: str) -> dict:
    loc = w.get("primary_location") or {}
    src = loc.get("source") or {}
    return _record(
        "openalex", direction,
        source_id=w.get("id", ""),
        doi=w.get("doi"), title=w.get("display_name") or w.get("title"),
        authors=[(a.get("author") or {}).get("display_name")
                 for a in w.get("authorships", []) or []],
        year=w.get("publication_year"),
        venue=src.get("display_name"),
        cited_by_count=w.get("cited_by_count"),
        abstract=_openalex_abstract(w.get("abstract_inverted_index")),
    )


def _fetch_openalex(doi: str, per_direction: int) -> dict:
    """OpenAlex：先取种子本体（拿到 work id 与 referenced_works），
    再分别拉参考文献详情与施引列表。返回 {seed, neighbors}。"""
    work = _http_get_json(
        f"https://api.openalex.org/works/https://doi.org/{doi}")
    if not isinstance(work, dict) or not work.get("id"):
        raise SourceError("openalex", f"OpenAlex 未找到种子：{doi}")
    seed = _openalex_record(work, "seed")
    neighbors: list[dict] = []
    ref_ids = [r for r in (work.get("referenced_works") or []) if r]
    if ref_ids:
        short = [r.rsplit("/", 1)[-1] for r in ref_ids[:per_direction]]
        data = _http_get_json(
            "https://api.openalex.org/works",
            {"filter": "openalex_id:" + "|".join(short),
             "per-page": len(short)})
        for w in (data or {}).get("results", []) or []:
            neighbors.append(_openalex_record(w, "references"))
    wid = work["id"].rsplit("/", 1)[-1]
    data = _http_get_json(
        "https://api.openalex.org/works",
        {"filter": f"cites:{wid}", "per-page": per_direction,
         "sort": "cited_by_count:desc"})
    for w in (data or {}).get("results", []) or []:
        neighbors.append(_openalex_record(w, "cited_by"))
    return {"seed": seed, "neighbors": neighbors}


_S2_FIELDS = "title,year,venue,externalIds,abstract,authors,citationCount"


def _s2_record(paper: dict, direction: str) -> dict:
    ext = paper.get("externalIds") or {}
    return _record(
        "semanticscholar", direction,
        source_id=paper.get("paperId", ""),
        doi=ext.get("DOI"), title=paper.get("title"),
        authors=[a.get("name") for a in paper.get("authors", []) or []],
        year=paper.get("year"), venue=paper.get("venue"),
        cited_by_count=paper.get("citationCount"),
        abstract=paper.get("abstract"),
    )


def _fetch_semanticscholar(doi: str, per_direction: int) -> dict:
    """Semantic Scholar：/references 给 citedPaper、/citations 给 citingPaper；
    种子本体从 references 端点的上下文不可得时以 DOI 记录占位（title 留空，
    合并时由其他源补全）。"""
    base = ("https://api.semanticscholar.org/graph/v1/paper/"
            f"DOI:{urllib.parse.quote(doi, safe='')}")
    neighbors: list[dict] = []
    data = _http_get_json(base + "/references",
                          {"fields": _S2_FIELDS, "limit": per_direction})
    for item in (data or {}).get("data", []) or []:
        paper = item.get("citedPaper") or {}
        if paper:
            neighbors.append(_s2_record(paper, "references"))
    data = _http_get_json(base + "/citations",
                          {"fields": _S2_FIELDS, "limit": per_direction})
    for item in (data or {}).get("data", []) or []:
        paper = item.get("citingPaper") or {}
        if paper:
            neighbors.append(_s2_record(paper, "cited_by"))
    seed = _record("semanticscholar", "seed", doi=doi)
    return {"seed": seed, "neighbors": neighbors}


def _fetch_crossref(doi: str, per_direction: int) -> dict:
    """Crossref：种子本体带 reference[]（只有参考文献方向；施引方向
    Crossref 不给明细，只有 is-referenced-by-count 计数，记入 seed）。"""
    data = _http_get_json(
        f"https://api.crossref.org/works/{urllib.parse.quote(doi, safe='')}")
    msg = (data or {}).get("message") or {}
    year = None
    for key in ("published-print", "published-online", "published", "issued"):
        parts = ((msg.get(key) or {}).get("date-parts") or [[]])[0]
        if parts and isinstance(parts[0], int):
            year = parts[0]
            break
    seed = _record(
        "crossref", "seed", source_id=msg.get("DOI", ""), doi=msg.get("DOI"),
        title=(msg.get("title") or [""])[0],
        authors=[" ".join(x for x in (a.get("given"), a.get("family")) if x)
                 or a.get("name") or "" for a in msg.get("author", []) or []],
        year=year, venue=(msg.get("container-title") or [""])[0],
        cited_by_count=msg.get("is-referenced-by-count"),
        abstract=re.sub(r"<[^>]+>", " ", msg.get("abstract") or "").strip(),
    )
    neighbors: list[dict] = []
    for ref in (msg.get("reference") or [])[:per_direction]:
        y = ref.get("year")
        neighbors.append(_record(
            "crossref", "references",
            source_id=ref.get("DOI", ""), doi=ref.get("DOI"),
            title=ref.get("article-title") or ref.get("volume-title") or "",
            authors=[ref.get("author") or ""],
            year=int(y) if str(y).isdigit() else None,
        ))
    return {"seed": seed, "neighbors": neighbors}


_FETCHERS = {
    "openalex": _fetch_openalex,
    "semanticscholar": _fetch_semanticscholar,
    "crossref": _fetch_crossref,
}


# ---------------------------------------------------------------------------
# 归并：同 DOI（或同规范化题名）+ 同方向合并，字段互补

def _merge_key(rec: dict) -> str:
    if rec.get("doi"):
        return f"{rec['direction']}|doi:{rec['doi']}"
    return f"{rec['direction']}|title:{normalize_title(rec.get('title'))}"


def merge_neighbors(records: list[dict]) -> list[dict]:
    merged: dict[str, dict] = {}
    for rec in records:
        if not rec.get("title") and not rec.get("doi"):
            continue  # 无题名无 DOI 的残条目不入素材（多为 Crossref 无题参考文献）
        key = _merge_key(rec)
        cur = merged.get(key)
        if cur is None:
            cur = dict(rec)
            cur["sources"] = [rec["source"]]
            merged[key] = cur
            continue
        if rec["source"] not in cur["sources"]:
            cur["sources"].append(rec["source"])
        for field in ("title", "venue", "abstract", "source_id"):
            if not cur.get(field) and rec.get(field):
                cur[field] = rec[field]
        if not cur.get("authors") and rec.get("authors"):
            cur["authors"] = rec["authors"]
        if cur.get("year") is None and rec.get("year") is not None:
            cur["year"] = rec["year"]
        if cur.get("cited_by_count") is None and rec.get("cited_by_count") is not None:
            cur["cited_by_count"] = rec["cited_by_count"]
    out = list(merged.values())
    out.sort(key=lambda r: (r["direction"],
                            -(r.get("cited_by_count") or 0),
                            normalize_title(r.get("title"))))
    return out


# ---------------------------------------------------------------------------
# fetch：抓一跳邻居并落盘（可重复调用以多跳生长）

def fetch_chain(root: Path, seed_doi: str, *,
                chain_id: str | None = None,
                hop_of: str | None = None,
                per_direction: int = DEFAULT_PER_DIRECTION,
                sources: tuple[str, ...] = SOURCES,
                date: str | None = None) -> dict:
    """抓 seed_doi 的一跳邻居并并入 chains/<chain_id>/ 落盘。

    - 首次调用（chain_id 缺省）：chain_id 由 seed_doi 生成，seed_doi 即根种子；
    - 生长调用：传 chain_id 指回既有链，seed_doi 为被展开的节点
      DOI；邻居并入同一 neighbors.jsonl（按 key+hop_of 去重保留
      先到版本），hop_of 自动记为该节点 DOI。hop_of 参数仅为旧
      调用兼容保留，已忽略。
    返回汇总 dict（源状态、方向计数、落盘路径）。三源全灭抛 ChainError。
    """
    date = date or today()
    doi = normalize_doi(seed_doi)
    if not doi:
        raise ChainError([f"种子 DOI 为空或非法：{seed_doi!r}"])
    chain_id = chain_id or make_chain_id(doi)

    all_records: list[dict] = []
    seed_best: dict | None = None
    source_status: dict[str, dict] = {}
    for source in sources:
        st = {"ok": False, "neighbors": 0, "error": None}
        try:
            got = _FETCHERS[source](doi, per_direction)
        except SourceError as exc:
            st["error"] = str(exc)
            source_status[source] = st
            continue
        except Exception as exc:  # 解析异常也如实记为该源失败，不中断其余源
            st["error"] = f"{type(exc).__name__}：{exc}"
            source_status[source] = st
            continue
        st["ok"] = True
        st["neighbors"] = len(got["neighbors"])
        source_status[source] = st
        all_records.extend(got["neighbors"])
        cand = got.get("seed") or {}
        if cand.get("title") and (seed_best is None
                                  or not seed_best.get("title")):
            seed_best = cand
        elif seed_best is None:
            seed_best = cand
    if not any(s["ok"] for s in source_status.values()):
        errs = [f"{SOURCE_LABELS[s]} 失败：{source_status[s]['error']}"
                for s in sources]
        raise ChainError(["三源全部不可用，链素材未成立——不许凭印象建链；"
                          "待源恢复后重跑。" ] + errs)

    fresh = merge_neighbors(all_records)
    for rec in fresh:
        rec["hop_of"] = doi  # 恒为被展开节点，归因不许人工指定

    cdir = chain_dir(root, chain_id)
    cdir.mkdir(parents=True, exist_ok=True)

    # 种子文件：根种子只在首次写；生长调用不覆盖根种子，只追加 hop 记录
    seed_path = cdir / "seed.json"
    hops: list[dict] = []
    if seed_path.exists():
        prev = json.loads(seed_path.read_text(encoding="utf-8"))
        hops = prev.get("hops", [])
        root_seed = prev.get("seed") or {}
    else:
        root_seed = {
            "doi": doi,
            "title": (seed_best or {}).get("title") or "",
            "authors": (seed_best or {}).get("authors") or [],
            "year": (seed_best or {}).get("year"),
            "venue": (seed_best or {}).get("venue") or "",
            "cited_by_count": (seed_best or {}).get("cited_by_count"),
        }
    hop_entry = {"doi": doi, "date": date,
                 "title": (seed_best or {}).get("title") or "",
                 "is_root": not seed_path.exists(),
                 "source_status": source_status}
    hops = [h for h in hops if normalize_doi(h.get("doi")) != doi] + [hop_entry]
    seed_path.write_text(json.dumps({
        "chain_id": chain_id, "seed": root_seed, "hops": hops,
        "updated": date,
    }, ensure_ascii=False, indent=1), encoding="utf-8")

    # 邻居并入：键 = hop_of + 方向 + DOI/题名；已有条目保留，补来源
    nb_path = cdir / "neighbors.jsonl"
    existing: dict[str, dict] = {}
    if nb_path.exists():
        for line in nb_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                rec = json.loads(line)
                existing[f"{rec.get('hop_of')}|{_merge_key(rec)}"] = rec
    for rec in fresh:
        key = f"{rec['hop_of']}|{_merge_key(rec)}"
        if key in existing:
            cur = existing[key]
            for s in rec["sources"]:
                if s not in cur["sources"]:
                    cur["sources"].append(s)
        else:
            existing[key] = rec
    all_neighbors = sorted(
        existing.values(),
        key=lambda r: (r.get("hop_of") or "", r["direction"],
                       -(r.get("cited_by_count") or 0),
                       normalize_title(r.get("title"))))
    with open(nb_path, "w", encoding="utf-8") as f:
        for rec in all_neighbors:
            f.write(json.dumps({
                "direction": rec["direction"],
                "hop_of": rec.get("hop_of"),
                "sources": rec["sources"],
                "source_id": rec["source_id"],
                "title": rec["title"],
                "authors": rec["authors"],
                "year": rec["year"],
                "doi": rec["doi"],
                "venue": rec["venue"],
                "cited_by_count": rec["cited_by_count"],
                "abstract_snippet": (rec.get("abstract") or "")[
                    :_ABSTRACT_SNIPPET_CHARS],
            }, ensure_ascii=False) + "\n")

    report_path = cdir / "chain_report.md"
    report_path.write_text(_render_report(
        chain_id, root_seed, hops, all_neighbors), encoding="utf-8")
    counts = {d: sum(1 for r in fresh if r["direction"] == d)
              for d in DIRECTIONS}
    return {
        "chain_id": chain_id,
        "seed_doi": doi,
        "date": date,
        "new_neighbors": len(fresh),
        "counts": counts,
        "total_neighbors_on_disk": len(all_neighbors),
        "source_status": source_status,
        "any_source_ok": True,
        "chain_dir": str(cdir),
        "seed_path": str(seed_path),
        "neighbors_path": str(nb_path),
        "report_path": str(report_path),
    }


def _render_report(chain_id: str, root_seed: dict, hops: list[dict],
                   neighbors: list[dict]) -> str:
    L: list[str] = []
    L.append(f"# 演进链素材报告 — {chain_id}")
    L.append("")
    L.append(f"> 根种子：{root_seed.get('title') or '（题名未取到）'}"
             f"（DOI: {root_seed.get('doi')}，{root_seed.get('year') or '年份缺'}）")
    L.append("> 本文件只是**链素材**：邻居清单是公开 API 实查结果；建链"
             "（抽节点四元组、相关性门、链尾外推）由智能体按 SKILL.md "
             "第 9 节规程执行，本工具不自动生成想法。")
    L.append("")
    L.append("## 已展开的跳（hops）")
    L.append("")
    L.append("| 节点 DOI | 是否根种子 | 日期 | 各源状态 |")
    L.append("|---|---|---|---|")
    for h in hops:
        bits = []
        for source in SOURCES:
            st = (h.get("source_status") or {}).get(source) or {}
            bits.append(f"{SOURCE_LABELS[source]}："
                        f"{'可用（邻居 ' + str(st.get('neighbors', 0)) + '）' if st.get('ok') else '失败（' + str(st.get('error')) + '）'}")
        L.append(f"| {h.get('doi')} | {'是' if h.get('is_root') else '否'} "
                 f"| {h.get('date')} | {'；'.join(bits)} |")
    L.append("")
    for direction in DIRECTIONS:
        rows = [r for r in neighbors if r["direction"] == direction]
        L.append(f"## {DIRECTION_LABELS[direction]}（落盘 {len(rows)} 条，"
                 f"按被引数降序）")
        L.append("")
        if not rows:
            L.append("（无）")
        for r in rows:
            doi = f" DOI:{r['doi']}" if r.get("doi") else ""
            cited = (f"，被引 {r['cited_by_count']}"
                     if r.get("cited_by_count") is not None else "")
            L.append(f"- [{r.get('year') or '年份缺'}] {r['title']}"
                     f"（展开自 {r.get('hop_of')}）{doi}{cited}")
        L.append("")
    L.append("## 下一步（规程提示）")
    L.append("")
    L.append("1. 按相关性门从邻居中逐跳选 3–5 个节点（与方向问题不相关的"
             "不许凑数），逐节点抽 {想法一句话, 实验, 实体, 参考文献} 四元组；")
    L.append("2. 高被引（>1000）源头节点只作链的起点背景，不在其上继续外推；")
    L.append("3. 先写趋势层小结（相邻代际之间变了什么），再在链尾/断点处"
             "生成候选，落卡时 provenance.chain_id 与 path_string 必填；")
    L.append("4. 查新撞车证据以 bad_case 回流时轮次上限 ≤3（SKILL 第 9 节）。")
    L.append("")
    return "\n".join(L)


def load_neighbors(root: Path, chain_id: str) -> list[dict]:
    """读回已落盘的邻居清单（供报告/测试核对）。"""
    path = chain_dir(root, chain_id) / "neighbors.jsonl"
    if not path.exists():
        raise ChainError([f"链素材不存在：{path}——先跑 chain 命令取材"])
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out
