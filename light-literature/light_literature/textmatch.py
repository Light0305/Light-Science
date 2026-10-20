"""块级文本匹配小工具 (claim-check 与 ask 共用)。

只做机械匹配：分词、数字抽取与逐字在场检查、块打分。语义判断 (支持/
反对) 由执行 agent 在读块后作出，本模块只提供可核查的机械信号，
不许拿分数冒充语义结论。
"""

from __future__ import annotations

import re
import unicodedata

_NUM_RE = re.compile(r"\d+(?:,\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?")

_STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "are", "was",
    "were", "has", "have", "had", "not", "but", "can", "its", "it",
    "of", "in", "on", "to", "by", "is", "at", "or", "as", "be", "we",
    "do", "did", "does", "what", "how", "when", "which", "who", "an",
    "per", "via", "than", "then", "into", "over", "under", "between",
    "的", "了", "是", "在", "和", "与", "对", "为", "中", "上", "下",
}


def extract_numbers(text: str | None) -> list[str]:
    """抽取文本中的数字 (保序去重)：去千分位逗号，保留小数形态。"""
    out: list[str] = []
    for m in _NUM_RE.finditer(text or ""):
        num = m.group(0).replace(",", "")
        if num not in out:
            out.append(num)
    return out


def number_in_text(num: str, text: str) -> bool:
    """数字逐字在场检查：数字边界守护 (42 不算命中 420，也不算 3.42)。"""
    pattern = r"(?<![0-9.])" + re.escape(num) + r"(?![0-9])"
    return re.search(pattern, text or "") is not None


def tokenize(text: str | None) -> set[str]:
    """分词：拉丁词 (小写、长度>=2) + CJK 单字与双字组；去停用词。"""
    text = unicodedata.normalize("NFKC", (text or "").lower())
    tokens: set[str] = set()
    for word in re.findall(r"[a-z][a-z0-9_\-]+|[a-z0-9]+", text):
        if len(word) >= 2 and word not in _STOPWORDS:
            tokens.add(word)
    cjk = re.findall(r"[\u4e00-\u9fff]+", text)
    for run in cjk:
        for ch in run:
            if ch not in _STOPWORDS:
                tokens.add(ch)
        for i in range(len(run) - 1):
            tokens.add(run[i:i + 2])
    return tokens


def block_text(block: dict) -> str:
    """块的可检索文本：正文 + 表格 Markdown + 图注文本 (若有)。"""
    parts = [block.get("text") or ""]
    if block.get("table_md"):
        parts.append(block["table_md"])
    if block.get("caption_text"):
        parts.append(block["caption_text"])
    return "\n".join(p for p in parts if p)


def is_evidence(scored: dict) -> bool:
    """证据强度门：命中块须至少有一个数字命中，或 >=2 个不同词项命中。

    单个泛词 (如 energy) 在无关块里碰巧出现不构成证据——宁可拒答，
    不许拿单词碰撞冒充语料支持 (实测教训，见 phase3 构建单)。
    """
    return bool(scored["matched_numbers"]) or \
        len(scored["matched_terms"]) >= 2


def score_block(query_tokens: set[str], query_numbers: list[str],
                block: dict) -> dict:
    """块打分：词项命中数 + 数字命中数 x3；返回分数与命中明细。"""
    text = block_text(block)
    btokens = tokenize(text)
    matched_terms = sorted(query_tokens & btokens)
    matched_numbers = [n for n in query_numbers
                       if number_in_text(n, text)]
    missing_numbers = [n for n in query_numbers
                       if n not in matched_numbers]
    score = len(matched_terms) + 3 * len(matched_numbers)
    return {
        "score": score,
        "matched_terms": matched_terms,
        "matched_numbers": matched_numbers,
        "missing_numbers": missing_numbers,
        "text": text,
    }
