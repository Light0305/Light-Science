"""想法卡去重：离线文本相似度（不用任何外部 embedding 服务）。

方法：字符 n-gram（3–5）TF-IDF + 余弦相似度，纯标准库实现。
选型理由：想法卡文本短、中英混排，字符 n-gram 对词序与语言不敏感，
不需要分词器与外部服务，离线可复现；语义级去重（嵌入）在二期接入，
本工序的职责是机械地标出「疑似重复对」供人工裁决——**不自动删卡**。

去重率报告口径（约束 5：去重率是生成健康体检指标）：
    生成总数 N → 疑似重复对 P（阈值以上）→ 按并查集聚出的重复簇 C
    → 若人工裁决全部成立，去重后存活数 = N - (簇内冗余数)。
报告只给口径与数字，不替人工下裁决。
"""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict

NGRAM_RANGE = (3, 5)
DEFAULT_THRESHOLD = 0.55


def card_text(card: dict) -> str:
    """拼出一张卡的去重文本：题名 + 一句话 + facet 短语/展开 + 方法步。"""
    parts = [card.get("title") or "", card.get("one_liner") or ""]
    facets = card.get("facets") or {}
    for f in ("purpose", "mechanism", "evaluation"):
        fd = facets.get(f) or {}
        parts.append(fd.get("phrase") or "")
        parts.append(fd.get("detail") or "")
    body = card.get("body") or {}
    parts.append(body.get("hypothesis") or "")
    parts.extend(body.get("method_steps") or [])
    text = " ".join(parts).lower()
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _ngrams(text: str, n_range=NGRAM_RANGE) -> Counter:
    text = re.sub(r"[^0-9a-z\u4e00-\u9fff]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    grams: Counter = Counter()
    lo, hi = n_range
    for n in range(lo, hi + 1):
        for i in range(len(text) - n + 1):
            grams[text[i:i + n]] += 1
    return grams


def tfidf_vectors(texts: list[str]) -> list[dict[str, float]]:
    """把文本列表转成 L2 归一化的 TF-IDF 稀疏向量（dict）。"""
    docs = [_ngrams(t) for t in texts]
    n_docs = len(docs)
    df: Counter = Counter()
    for grams in docs:
        for g in grams:
            df[g] += 1
    vectors: list[dict[str, float]] = []
    for grams in docs:
        vec: dict[str, float] = {}
        for g, cnt in grams.items():
            idf = math.log((1 + n_docs) / (1 + df[g])) + 1.0
            vec[g] = (1.0 + math.log(cnt)) * idf
        norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
        vectors.append({g: v / norm for g, v in vec.items()})
    return vectors


def cosine(a: dict[str, float], b: dict[str, float]) -> float:
    if len(a) > len(b):
        a, b = b, a
    return sum(v * b.get(g, 0.0) for g, v in a.items())


def find_pairs(cards: list[dict], threshold: float = DEFAULT_THRESHOLD) -> list[dict]:
    """返回相似度 ≥ 阈值的疑似重复对，按相似度降序。

    每项：{a, b, similarity}（a/b 为 idea_id）。空文本卡不参与比较，
    但会在报告里被点名（空卡本身就是生成事故）。"""
    texts = [card_text(c) for c in cards]
    vectors = tfidf_vectors(texts)
    pairs = []
    for i in range(len(cards)):
        if not texts[i]:
            continue
        for j in range(i + 1, len(cards)):
            if not texts[j]:
                continue
            sim = cosine(vectors[i], vectors[j])
            if sim >= threshold:
                pairs.append({"a": cards[i]["idea_id"], "b": cards[j]["idea_id"],
                              "similarity": round(sim, 4)})
    pairs.sort(key=lambda p: -p["similarity"])
    return pairs


def clusters_from_pairs(pairs: list[dict]) -> list[list[str]]:
    """并查集把重复对聚成簇（簇内 ≥2 张卡）。"""
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for p in pairs:
        ra, rb = find(p["a"]), find(p["b"])
        if ra != rb:
            parent[ra] = rb
    groups: dict[str, list[str]] = defaultdict(list)
    for x in list(parent):
        groups[find(x)].append(x)
    return sorted((sorted(v) for v in groups.values() if len(v) > 1),
                  key=lambda g: -len(g))


def most_similar_map(cards: list[dict], pairs: list[dict]) -> dict[str, dict]:
    """每张卡的最相似对象与分数（回写 dedup 字段用）。"""
    best: dict[str, dict] = {}
    for p in pairs:
        for me, other in ((p["a"], p["b"]), (p["b"], p["a"])):
            if me not in best or p["similarity"] > best[me]["similarity"]:
                best[me] = {"most_similar_to": other, "max_similarity": p["similarity"]}
    return best


def dedup_report(cards: list[dict], pairs: list[dict], threshold: float) -> dict:
    """去重率报告（只给口径数字，裁决归人工）。"""
    clusters = clusters_from_pairs(pairs)
    redundant = sum(len(c) - 1 for c in clusters)
    empty = [c["idea_id"] for c in cards if not card_text(c)]
    return {
        "total_generated": len(cards),
        "threshold": threshold,
        "suspected_pairs": len(pairs),
        "clusters": clusters,
        "redundant_if_all_confirmed": redundant,
        "survivors_if_all_confirmed": len(cards) - redundant,
        "dedup_rate_if_all_confirmed": (
            round(redundant / len(cards), 4) if cards else 0.0
        ),
        "empty_text_cards": empty,
        "pairs": pairs,
    }
