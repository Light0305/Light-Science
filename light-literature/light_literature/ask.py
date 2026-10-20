"""ask 问语料模式 (LIT-D01)：对已入库语料提问，答案只许引用命中块。

与 light-memory recall 的边界 (SKILL §6)：ask 查的是文献全文证据
(source_map 块)，recall 查的是沉淀后的事实账——两者不互相替代。

纪律 (形态学 paper-qa，按诊断 D01 落地)：
- 块级检索：对已入库论文的 source_map 块 (S/C 正文、T 表格) 做词项/
  数字机械匹配，逐块分数与命中信号全部留痕。
- 引用白名单：答案的引用只能取自本次命中块的锚点，且引用数不许
  超过上限 (默认 5)；白名单外的锚点一律拒绝落盘。
- 固定拒答：无任一块命中时，产物只写固定拒答句；此时即使调用方
  传入答案也报错拒绝——证据不足不许生成答案。
- 证据资格门：paper.yaml 顶层 identity_status 非 verified 或
  retraction_status=retracted 的论文 (若有标记)，其块不进命中集
  (未核实文献不入成稿层，硬规则 1 在问答面的落点)。
- 产物全留痕：Literature/问答记录/<日期>-<序号>.md (问题、命中块、
  答案或拒答、引用清单)。
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

from . import textmatch
from .util import (corpus_paper_ids, literature_dir, load_paper_yaml,
                   read_json)

#: 证据不足时的固定拒答句 (措辞冻结，改动须同步 SKILL 与测试)。
REFUSAL_TEXT = ("证据不足：已入库语料中未找到可支持回答的证据块，"
                "本次拒答。")
DEFAULT_MAX_CITATIONS = 5
_RECORD_DIRNAME = "问答记录"
_EXCERPT_CHARS = 200
_BLOCK_TYPES = ("text", "caption", "table")


def _paper_eligible(paper: dict) -> tuple[bool, str | None]:
    """证据资格门：只排除被显式标记未核实/已撤稿的论文。"""
    identity = paper.get("identity_status")
    if identity is not None and identity != "verified":
        return False, f"identity_status={identity}"
    if paper.get("retraction_status") == "retracted":
        return False, "retraction_status=retracted"
    return True, None


def retrieve(project_dir: Path, question: str) -> dict:
    """块级检索：返回 hits (命中块) 与 excluded (资格门排除留痕)。"""
    project_dir = Path(project_dir)
    if not (question or "").strip():
        raise ValueError("问题不许为空")
    q_tokens = textmatch.tokenize(question)
    q_numbers = textmatch.extract_numbers(question)
    hits: list[dict] = []
    excluded: list[dict] = []
    for pid in corpus_paper_ids(project_dir):
        pdir, paper = load_paper_yaml(project_dir, pid)
        ok, why = _paper_eligible(paper)
        if not ok:
            excluded.append({"paper_id": pid, "reason": why})
            continue
        smap = read_json(pdir / "source_map.json")
        for block in smap.get("blocks", []):
            if not block.get("id") or block.get("type") not in _BLOCK_TYPES:
                continue
            scored = textmatch.score_block(q_tokens, q_numbers, block)
            if textmatch.is_evidence(scored):
                hits.append({
                    "paper_id": pid,
                    "anchor": block["id"],
                    "page": block.get("page"),
                    "type": block.get("type"),
                    "score": scored["score"],
                    "matched_terms": scored["matched_terms"],
                    "matched_numbers": scored["matched_numbers"],
                    "excerpt": " ".join(scored["text"].split())[
                        :_EXCERPT_CHARS],
                })
    hits.sort(key=lambda h: (-h["score"], h["paper_id"], h["anchor"]))
    return {"hits": hits, "excluded": excluded}


def _parse_citation(raw: str, whitelist: dict[str, dict]) -> str:
    """引用解析：接受 'paper_id#S001' 或裸锚点 (须在命中集内唯一)。"""
    if "#" in raw:
        pid, anchor = raw.split("#", 1)
        key = f"{pid}#{anchor}"
        if key in whitelist:
            return key
        raise ValueError(f"引用不在本次命中白名单内：{raw}")
    matches = [k for k in whitelist if k.endswith(f"#{raw}")]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise ValueError(f"引用不在本次命中白名单内：{raw}")
    raise ValueError(f"裸锚点 {raw} 在命中集中不唯一，须写 paper_id#锚点")


def ask(project_dir: Path, question: str, answer: str | None = None,
        citations: list[str] | None = None,
        max_citations: int = DEFAULT_MAX_CITATIONS) -> dict:
    """执行一次问语料：检索 → (拒答 | 待答 | 落答案) → 写问答记录。"""
    project_dir = Path(project_dir)
    citations = list(citations or [])
    found = retrieve(project_dir, question)
    hits = found["hits"]

    if not hits:
        if answer is not None:
            raise ValueError(
                "无命中证据块：固定拒答，不许附答案 (证据不足拒答纪律)")
        status = "refused"
    elif answer is not None:
        if not citations:
            raise ValueError("给出答案时必须同时给出引用锚点 (--cite)")
        if len(citations) > max_citations:
            raise ValueError(
                f"引用数 {len(citations)} 超过上限 {max_citations}")
        whitelist = {f"{h['paper_id']}#{h['anchor']}": h for h in hits}
        citations = [_parse_citation(c, whitelist) for c in citations]
        status = "answered"
    else:
        status = "awaiting_answer"

    rec_dir = literature_dir(project_dir) / _RECORD_DIRNAME
    rec_dir.mkdir(parents=True, exist_ok=True)
    seq = len(list(rec_dir.glob("*.md"))) + 1
    rec_path = rec_dir / f"{date.today().isoformat()}-{seq:03d}.md"

    lines = [
        "# 问答记录 (ask-the-corpus)",
        "",
        f"- 问题：{question}",
        f"- 时间 (UTC)：{datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        f"- 状态：{status}",
        f"- 引用上限：{max_citations}",
        "",
        "## 命中证据块",
        "",
    ]
    if hits:
        lines += ["| 论文 | 锚点 | 页 | 分数 | 命中词项 | 摘录 |",
                  "|---|---|---|---|---|---|"]
        for h in hits:
            terms = ", ".join(h["matched_terms"][:8])
            lines.append(
                f"| {h['paper_id']} | {h['anchor']} | {h['page']} "
                f"| {h['score']} | {terms} | {h['excerpt']} |")
    else:
        lines.append("（无命中）")
    if found["excluded"]:
        lines += ["", "## 证据资格门排除（未核实/撤稿，不入证据）", ""]
        for e in found["excluded"]:
            lines.append(f"- {e['paper_id']}：{e['reason']}")
    lines += ["", "## 答案", ""]
    if status == "refused":
        lines.append(REFUSAL_TEXT)
    elif status == "answered":
        lines.append(answer or "")
        lines += ["", "引用："]
        for c in citations:
            lines.append(f"- {c}")
    else:
        lines.append(
            "（待执行 agent 依据上表命中块作答；引用只能取自上表锚点，"
            f"且不超过 {max_citations} 条。用 ask --answer/--cite 落盘。）")
    lines.append("")
    rec_path.write_text("\n".join(lines), encoding="utf-8")

    return {
        "question": question,
        "status": status,
        "hits": len(hits),
        "excluded": found["excluded"],
        "citations": citations if status == "answered" else [],
        "record": str(rec_path),
    }
