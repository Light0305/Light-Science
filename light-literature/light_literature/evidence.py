"""证据行：向项目级 证据表.jsonl 只增追加，含纠错追加。

纪律（deep-read-A 5.3）：evidence_id 只增不改不复用，格式 E + 三位序号
（扫描全表最大值 +1）；纠错不改原行，而是追加一条带 corrects 字段的新行，
原行与新行都在表中，审计链完整。字段口径见 SKILL.md §4。
"""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

from . import project as project_mod
from .util import literature_dir

CLAIM_STRENGTHS = ("direct", "indirect", "conflicting", "background")
_ID_RE = re.compile(r"^E(\d+)$")
# 启发式句末标点计数：中文句末标点直接计；英文 .!? 仅在其后为空白或行尾
# 时计（避免把 3.14、e.g. 的小数点/缩写点误计——仍是启发式，缩写如
# "et al. Next" 会被计为两句，宁严勿松）。
_SENTENCE_END_RE = re.compile(r"[。！？]|[.!?](?=\s|$)")


def count_sentences(text: str) -> int:
    """启发式数句数（按句末标点计，见模块内 _SENTENCE_END_RE 注释）。"""
    return len(_SENTENCE_END_RE.findall(text or ""))


def _table_path(project_dir: Path) -> Path:
    return literature_dir(project_dir) / "证据表.jsonl"


def _read_rows(project_dir: Path) -> list[dict]:
    path = _table_path(project_dir)
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def _next_id(rows: list[dict]) -> str:
    nums = [int(m.group(1)) for r in rows
            if (m := _ID_RE.match(str(r.get("evidence_id", ""))))]
    return f"E{(max(nums) + 1) if nums else 1:03d}"


def _append(project_dir: Path, row: dict) -> dict:
    path = _table_path(project_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


def _check_quote(quote: str | None) -> None:
    if quote and count_sentences(quote) > 1:
        raise ValueError(
            "quote 超过一句（上限一句）：按句末标点启发式计数为 "
            f"{count_sentences(quote)} 句。请截断到一句以内，或不用 quote 字段"
            "（启发式说明：英文缩写后的句点可能误判，宁严勿松）")


def _check_strength(claim_strength: str | None) -> None:
    if claim_strength is not None and claim_strength not in CLAIM_STRENGTHS:
        raise ValueError(
            f"claim_strength 必须是 {'|'.join(CLAIM_STRENGTHS)} 之一，"
            f"收到：{claim_strength}")


def add_evidence(project_dir: Path, paper_id: str, finding: str, page: int,
                 statistic: str | None = None, quote: str | None = None,
                 supports_claim: str | None = None,
                 claim_strength: str | None = None,
                 limitations: str | None = None,
                 note_anchor: str | None = None) -> dict:
    """追加一条证据行并返回该行。校验不通过抛 ValueError，不写文件。"""
    if not finding or not finding.strip():
        raise ValueError("finding 不能为空")
    if page is None:
        raise ValueError("page 必填（证据必须可回原文定位）")
    _check_quote(quote)
    _check_strength(claim_strength)
    project_mod.init_project(project_dir)  # 确保项目级文件存在
    rows = _read_rows(project_dir)
    row = {
        "evidence_id": _next_id(rows),
        "paper_id": paper_id,
        "finding": finding.strip(),
        "statistic": statistic or "",
        "page": page,
        "quote": quote or "",
        "supports_claim": supports_claim or "",
        "claim_strength": claim_strength or "",
        "limitations": limitations or "",  # 仅作者自述局限
        "note_path": f"Literature/{paper_id}/阅读笔记.md",
        "note_anchor": note_anchor or "",
        "created_at": date.today().isoformat(),
    }
    return _append(project_dir, row)


def correct_evidence(project_dir: Path, corrects: str,
                     finding: str | None = None, page: int | None = None,
                     statistic: str | None = None, quote: str | None = None,
                     supports_claim: str | None = None,
                     claim_strength: str | None = None,
                     limitations: str | None = None,
                     note_anchor: str | None = None) -> dict:
    """追加纠错行：带 corrects 指向原行，原行不动。

    未给出的字段继承原行（page/paper_id 亦然）；至少要给出一个被修正的
    内容字段，否则视为无意义纠错并拒绝。
    """
    _check_quote(quote)
    _check_strength(claim_strength)
    rows = _read_rows(project_dir)
    original = next((r for r in rows if r.get("evidence_id") == corrects), None)
    if original is None:
        raise ValueError(f"被纠错的 evidence_id 不存在：{corrects}")
    given = {"finding": finding, "statistic": statistic, "quote": quote,
             "supports_claim": supports_claim, "claim_strength": claim_strength,
             "limitations": limitations, "note_anchor": note_anchor,
             "page": page}
    if all(v is None for v in given.values()):
        raise ValueError("纠错行至少要给出一个被修正的字段"
                         "（--finding/--page/--statistic/--quote 等）")
    row = dict(original)
    row.pop("corrects", None)
    for key, value in given.items():
        if value is not None:
            row[key] = value.strip() if isinstance(value, str) else value
    row["evidence_id"] = _next_id(rows)
    row["corrects"] = corrects
    row["created_at"] = date.today().isoformat()
    return _append(project_dir, row)
