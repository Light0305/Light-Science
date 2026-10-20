"""claim-support 检查 (LIT-D04)：核实成本三级的最高档落成命令面。

SKILL §3 规则 8 第三档：被写进我方稿件的主张级引用才跑上下文支持。
两件工具：

- locate_claim：给定主张文本，在已入库语料的 source_map 块级定位
  证据 (词项/数字机械匹配)，输出候选锚点与命中信号；全语料无命中
  如实回 status=not_mentioned——查无实据就报未提及，不许推断补齐。
- record_claim_check：执行 agent 读块后给出三值判定
  (supports / contradicts / not_mentioned)，本函数做机械校验后追加
  一行 Literature/claim_support.jsonl (只增不改，供 light-write
  交接时附带)。机械校验：锚点必须真实存在；supports 时主张中的
  每个数字必须逐字出现在所引块中 (防「引用存在但数字对不上」的
  假支持)；contradicts 须至少给一个锚点。

三值口径：诊断原文的 insufficient_context (锚点在但上下文不足判)
并入 not_mentioned，以 signals.reason 区分 no_block_mentions /
cited_blocks_do_not_mention (构建单自主判断留痕)。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from . import textmatch
from .util import corpus_paper_ids, literature_dir, paper_dir, read_json

VERDICTS = ("supports", "contradicts", "not_mentioned")
_LEDGER_FILENAME = "claim_support.jsonl"
_EXCERPT_CHARS = 200


def _blocks_by_id(project_dir: Path, paper_id: str) -> dict[str, dict]:
    pdir = paper_dir(Path(project_dir), paper_id)
    smap = read_json(pdir / "source_map.json")
    return {b["id"]: b for b in smap.get("blocks", []) if b.get("id")}


def _excerpt(text: str) -> str:
    flat = " ".join((text or "").split())
    return flat[:_EXCERPT_CHARS]


def locate_claim(project_dir: Path, claim: str,
                 paper_id: str | None = None, top: int = 10) -> dict:
    """在语料中为一条主张定位候选证据块 (纯读，不落盘)。

    返回 {claim, status: located|not_mentioned, candidates: [...]}，
    候选含 paper_id / anchor / page / score / matched_terms /
    matched_numbers / excerpt，按分数降序。
    """
    project_dir = Path(project_dir)
    if not (claim or "").strip():
        raise ValueError("主张文本不许为空")
    paper_ids = [paper_id] if paper_id else corpus_paper_ids(project_dir)
    q_tokens = textmatch.tokenize(claim)
    q_numbers = textmatch.extract_numbers(claim)
    candidates: list[dict] = []
    for pid in paper_ids:
        for anchor, block in _blocks_by_id(project_dir, pid).items():
            scored = textmatch.score_block(q_tokens, q_numbers, block)
            if textmatch.is_evidence(scored):
                candidates.append({
                    "paper_id": pid,
                    "anchor": anchor,
                    "page": block.get("page"),
                    "score": scored["score"],
                    "matched_terms": scored["matched_terms"],
                    "matched_numbers": scored["matched_numbers"],
                    "excerpt": _excerpt(scored["text"]),
                })
    candidates.sort(key=lambda c: (-c["score"], c["paper_id"], c["anchor"]))
    return {
        "claim": claim,
        "status": "located" if candidates else "not_mentioned",
        "candidates": candidates[:top],
        "searched_papers": paper_ids,
    }


def record_claim_check(project_dir: Path, paper_id: str, claim: str,
                       verdict: str, anchors: list[str] | None = None,
                       note: str | None = None) -> dict:
    """校验一条 claim-support 判定并追加 claim_support.jsonl 一行。"""
    project_dir = Path(project_dir)
    if verdict not in VERDICTS:
        raise ValueError(f"verdict 必须是 {VERDICTS} 之一，给的是 {verdict!r}")
    if not (claim or "").strip():
        raise ValueError("主张文本不许为空")
    anchors = list(anchors or [])
    blocks = _blocks_by_id(project_dir, paper_id)
    missing = [a for a in anchors if a not in blocks]
    if missing:
        raise ValueError(
            f"锚点在 {paper_id} 的 source_map 中不存在：{missing}"
            "（不许引用不存在的锚点）")
    if verdict in ("supports", "contradicts") and not anchors:
        raise ValueError(f"verdict={verdict} 必须给出至少一个证据锚点")

    cited_text = "\n".join(textmatch.block_text(blocks[a]) for a in anchors)
    claim_numbers = textmatch.extract_numbers(claim)
    numbers_found = [n for n in claim_numbers
                     if textmatch.number_in_text(n, cited_text)]
    numbers_missing = [n for n in claim_numbers if n not in numbers_found]
    if verdict == "supports" and numbers_missing:
        raise ValueError(
            f"主张数字未在所引块中逐字出现：{numbers_missing}"
            "（supports 拒绝写入：先核对数字或改判）")

    if verdict == "not_mentioned":
        reason = ("no_block_mentions" if not anchors else
                  "cited_blocks_do_not_mention"
                  if not textmatch.tokenize(claim) & textmatch.tokenize(
                      cited_text) else "judged_insufficient")
    else:
        reason = None
    signals = {
        "claim_numbers": claim_numbers,
        "numbers_found_in_cited": numbers_found,
        "numbers_missing_in_cited": numbers_missing,
        "reason": reason,
    }

    ledger = literature_dir(project_dir) / _LEDGER_FILENAME
    ledger.parent.mkdir(parents=True, exist_ok=True)
    existing = 0
    if ledger.exists():
        existing = sum(1 for ln in ledger.read_text(
            encoding="utf-8").splitlines() if ln.strip())
    row = {
        "claim_id": f"CS{existing + 1:03d}",
        "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "paper_id": paper_id,
        "claim": claim,
        "anchors": anchors,
        "verdict": verdict,
        "signals": signals,
        "note": note,
        "cited_excerpts": {a: _excerpt(textmatch.block_text(blocks[a]))
                           for a in anchors},
    }
    with open(ledger, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    row["ledger"] = str(ledger)
    return row
