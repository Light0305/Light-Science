"""入库元数据自动回填 (LIT-D03)。

paper.yaml 新增 metadata 区，authors / venue / year 三字段逐字段记
{value, source, verified}：

- 来源优先级：Crossref 按 DOI 的权威记录 (须显式联网) > PDF 首页
  文本层与 PDF 元数据 > source_map 首页块。先命中先用，逐字段独立。
- 诚实纪律：自动回填的 verified 恒为 False——回填值是「有出处的候选」，
  不是已核实事实；只有用户显式 --confirm (已逐字核对原文首页) 才置
  True。抽不到就留空 (value=None) 并在 attempted_sources 记下试过
  哪些源，不许猜、不许凭记忆补 (与 SKILL §3/§5 的既有纪律一致)。
- ingest 只自动跑本地源 (不联网，失败不阻断入库)；联网回填走
  metadata-backfill 命令或 ingest --backfill-online。
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import pymupdf

from . import searchlayer as _sl
from .util import load_paper_yaml, read_json, save_paper_yaml

FIELDS = ("authors", "venue", "year")

_YEAR_RE = re.compile(r"(?<!\d)(?:19|20)\d{2}(?!\d)")
_YEAR_CONTEXT_KEYS = ("©", "copyright", "published", "available online",
                      "received", "accepted")


def _year_from_text(text: str) -> int | None:
    """从首页文本保守抽年份：优先版权/出版行；无上下文且全页只有一个
    不同年份时才取；多个候选无上下文一律留空 (抽错宁可空)。"""
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    contextual: list[int] = []
    all_years: list[int] = []
    for ln in lines:
        years = [int(m.group(0)) for m in _YEAR_RE.finditer(ln)]
        all_years.extend(years)
        low = ln.lower()
        if any(k in low for k in _YEAR_CONTEXT_KEYS):
            contextual.extend(years)
    if contextual:
        return contextual[0]
    distinct = sorted(set(all_years))
    if len(distinct) == 1:
        return distinct[0]
    return None


def _from_crossref(paper: dict, get=None, mailto: str | None = None) -> dict:
    """Crossref 按 DOI 取权威记录 → {字段: (值, 'crossref')}。"""
    doi = _sl.normalize_doi(paper.get("doi"))
    if not doi:
        return {}
    status, msg = _sl.get_adapter("crossref").fetch_work(
        doi, mailto=mailto, get=get)
    if status != 200 or not msg:
        return {}
    out: dict = {}
    authors = [a for a in _sl.crossref_authors(msg) if a]
    if authors:
        out["authors"] = (authors, "crossref")
    venue = (msg.get("container-title") or [""])[0]
    if venue:
        out["venue"] = (venue, "crossref")
    year = _sl.crossref_year(msg)
    if year:
        out["year"] = (year, "crossref")
    return out


def _from_pdf(pdir: Path) -> dict:
    """PDF 本地源：元数据作者 + 首页文本层年份。venue 不从文本层猜。"""
    pdf = pdir / "原文.pdf"
    if not pdf.exists():
        return {}
    out: dict = {}
    doc = pymupdf.open(pdf)
    try:
        author = ((doc.metadata or {}).get("author") or "").strip()
        if author:
            out["authors"] = ([author], "pdf_metadata")
        if len(doc) > 0:
            year = _year_from_text(doc[0].get_text())
            if year:
                out["year"] = (year, "pdf_first_page")
    finally:
        doc.close()
    return out


def _from_source_map(pdir: Path) -> dict:
    """source_map 首页 (page=1) 块文本抽年份 (双轨解析后可用的兜底源)。"""
    smap_path = pdir / "source_map.json"
    if not smap_path.exists():
        return {}
    smap = read_json(smap_path)
    text = "\n".join(
        (b.get("text") or "") for b in smap.get("blocks", [])
        if b.get("page") == 1 and b.get("text"))
    year = _year_from_text(text)
    if year:
        return {"year": (year, "source_map_first_page")}
    return {}


def backfill_metadata(project_dir: Path, paper_id: str,
                      online: bool = False, confirm: bool = False,
                      get=None, mailto: str | None = None) -> dict:
    """回填 paper.yaml 的 metadata 区，返回回填摘要。

    online=True 才查 Crossref (联网)；confirm=True 表示用户已逐字
    核对原文首页，把已填字段 verified 置 True。已存在的 metadata
    区整体重写 (回填是可重跑的确定性动作，旧值不保留——来源链以
    attempted_sources 与 backfilled_at 为据)。
    """
    pdir, paper = load_paper_yaml(Path(project_dir), paper_id)
    attempted: list[str] = []
    found: dict[str, tuple] = {}

    if online and paper.get("doi"):
        attempted.append("crossref")
        try:
            for k, v in _from_crossref(paper, get=get, mailto=mailto).items():
                found.setdefault(k, v)
        except _sl.FetchError:
            pass  # 联网失败不阻断回填，其余源照常；attempted 已留痕
    attempted.append("pdf")
    for k, v in _from_pdf(pdir).items():
        found.setdefault(k, v)
    attempted.append("source_map")
    for k, v in _from_source_map(pdir).items():
        found.setdefault(k, v)

    metadata: dict = {}
    for f in FIELDS:
        if f in found:
            value, source = found[f]
            metadata[f] = {"value": value, "source": source,
                           "verified": bool(confirm)}
        else:
            metadata[f] = {"value": None, "source": None, "verified": False}
    metadata["backfilled_at"] = date.today().isoformat()
    metadata["attempted_sources"] = attempted
    if confirm:
        metadata["confirmed_by"] = "user"
    paper["metadata"] = metadata
    save_paper_yaml(pdir, paper)
    return {
        "paper_id": paper_id,
        "metadata": metadata,
        "filled": [f for f in FIELDS if metadata[f]["value"] is not None],
        "empty": [f for f in FIELDS if metadata[f]["value"] is None],
    }
