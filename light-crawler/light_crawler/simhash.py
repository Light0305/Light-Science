"""simhash 跨 run 近重复检测（第五批计算扩面，PLAN §13 P1）。

与包内既有两层去重的关系（口径定版，勿混）：
1. 请求层精确去重：seen.jsonl 的请求指纹（方法 + URL），命中落
   duplicate_skipped、根本不发请求——这是增量口径，不动。
2. 内容层精确去重：store/ 内容寻址（sha256 相同只存一份）与清洗件
   text_sha256——字节/文本全同才算同，不动。
3. 本层（新增）：内容层近重检测。清洗文本算 64 位 simhash，落
   fingerprints.jsonl 指纹库（工作区级、跨 run 持久）；新内容入库时
   与库内全部指纹比汉明距离，不大于生效阈值（登记可配，默认
   schema.DEFAULT_NEAR_DUP_HAMMING_THRESHOLD）即记近重命中。
   命中只做三件事：清洗件标注、near_duplicate_detected 事件落账
   （点名来源 run / 来源产物 / 实际距离 / 生效阈值）、指纹照常入库。
   永不跳过抓取、永不丢弃内容、永不改动版本链——删不删、何时删，
   由下游按版本链与项目口径决定（与 run 内 shingle Jaccard 标记
   「只标记不删除」的纪律同构；run 内标记仍在 clean_content 内，
   两层并存，互不替代）。

算法：Charikar simhash。特征 = 清洗文本的小写词元（\\S+ 切分，与
clean_content 的 shingle 切分同源），特征哈希取 sha256 前 8 字节
（不用内置 hash()——其逐进程加盐会让指纹跨 run 不可比），词频作
权重，逐位加权投票后取符号。空文本指纹为 0 且永不参与命中判定
（空内容之间不许互相「近重」）。

指纹库逐条线性扫描：本包单 run 请求量受总量上限约束（默认 200），
库规模在项目生命周期内为万级以内，整数比对成本可忽略；不引入
LSH 等近似索引——精确全扫保证命中判定可复算、可审计。
"""

from __future__ import annotations

import hashlib
import re
import uuid
from pathlib import Path

from .util import append_jsonl, read_jsonl, sha256_bytes, utcnow

BITS = 64

_WORDS = re.compile(r"\S+")


def _feature_hash(token: str) -> int:
    return int.from_bytes(
        hashlib.sha256(token.encode("utf-8")).digest()[:8], "big")


def simhash64(text: str) -> int:
    """清洗文本的 64 位 simhash；无词元时返回 0（不参与判定）。"""
    counts: dict = {}
    for tok in _WORDS.findall((text or "").lower()):
        counts[tok] = counts.get(tok, 0) + 1
    if not counts:
        return 0
    weights = [0] * BITS
    for tok, freq in counts.items():
        h = _feature_hash(tok)
        for i in range(BITS):
            weights[i] += freq if (h >> i) & 1 else -freq
    out = 0
    for i in range(BITS):
        if weights[i] > 0:
            out |= 1 << i
    return out


def hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def fingerprint_hex(value: int) -> str:
    return f"{value:016x}"


# ---------------------------------------------------------------- 指纹库

def fingerprints_path(root) -> Path:
    return Path(root) / "fingerprints.jsonl"


def load_fingerprints(root) -> list:
    return read_jsonl(fingerprints_path(root))


def record_fingerprint(root, *, text: str, prov_id, target_id, run_id,
                       url, kind: str = "fetch") -> dict:
    """把一份已落盘内容的指纹入库，返回入库行。

    text_sha256 与清洗件口径一致（清洗文本的 sha256）；调用方须在
    provenance 落账之后调用（行内 prov_id 指向已存在的产物行）。
    """
    value = simhash64(text)
    row = {
        "fp_id": f"sf-{uuid.uuid4().hex[:12]}",
        "at": utcnow(),
        "simhash": fingerprint_hex(value),
        "text_sha256": sha256_bytes(text.encode("utf-8")),
        "prov_id": prov_id,
        "target_id": target_id,
        "run_id": run_id,
        "url": url,
        "kind": kind,
    }
    append_jsonl(fingerprints_path(root), row)
    return row


def find_match(root, text: str, threshold: int):
    """在指纹库中找与 text 最近的近重命中；无命中返回 None。

    判定规则：候选须 text_sha256 与本次不同（全同文本归精确层，
    本层不重复报告）、simhash 非零、本次 simhash 非零、汉明距离
    不大于 threshold。多条命中只报最近一条，data 里另记阈值内
    命中总数（matches_within_threshold），不逐条刷事件。
    """
    value = simhash64(text)
    if value == 0:
        return None
    mine = sha256_bytes((text or "").encode("utf-8"))
    best = None
    within = 0
    for row in load_fingerprints(root):
        if row.get("text_sha256") == mine:
            continue
        try:
            other = int(row.get("simhash") or "0", 16)
        except ValueError:
            continue
        if other == 0:
            continue
        d = hamming(value, other)
        if d <= threshold:
            within += 1
            if best is None or d < best["hamming_distance"]:
                best = {"row": row, "hamming_distance": d}
    if best is None:
        return None
    best["simhash"] = fingerprint_hex(value)
    best["matches_within_threshold"] = within
    return best
