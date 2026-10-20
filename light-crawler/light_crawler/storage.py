"""留存与 provenance（C3/C4）+ 已见集（C5 的最小形态）。

S3 轻量档：原始响应字节按内容寻址落 store/（同一哈希只存一份），
provenance 总账逐条记：源 URL、获取时间、通道、run 配置哈希、原
始响应哈希、预检记录指针、留存档位——缺 provenance 的产物下游有
权拒收（HC-6），validate 会重算哈希点名对不上的条目。
版本链：同 URL 再抓到不同哈希，新行以 supersedes 指向上一行 id；
条件请求 304 不落新行，只记 not_modified 事件（在 fetch 层）。
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from html.parser import HTMLParser
from pathlib import Path

from .util import append_jsonl, read_jsonl, sha256_bytes, sha256_file, utcnow

RETENTION_TIER = "lightweight_raw_plus_hash"


def store_raw(root, data: bytes) -> dict:
    """内容寻址落盘原始字节，返回 (sha256, 相对路径, 是否已存在)。"""
    digest = sha256_bytes(data)
    rel = Path("store") / digest[:2] / digest
    dest = Path(root) / rel
    existed = dest.exists()
    if not existed:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
    return {"sha256": digest, "raw_path": rel.as_posix(), "existed": existed}


def append_provenance(root, row: dict) -> dict:
    row = {"prov_id": f"pv-{uuid.uuid4().hex[:12]}", "at": utcnow(), **row}
    append_jsonl(Path(root) / "provenance.jsonl", row)
    return row


def read_provenance(root) -> list:
    return read_jsonl(Path(root) / "provenance.jsonl")


def last_provenance_for(root, url: str):
    rows = [r for r in read_provenance(root) if r.get("url") == url
            and r.get("kind") == "fetch"]
    return rows[-1] if rows else None


# ---------------------------------------------------------------- 已见集

def fingerprint(method: str, url: str, body: bytes = b"") -> str:
    """请求指纹：方法 + URL + body 规范化哈希（Scrapy 谱系）。"""
    h = hashlib.sha256()
    h.update(method.upper().encode())
    h.update(b"\n")
    h.update(url.encode("utf-8"))
    h.update(b"\n")
    h.update(body or b"")
    return h.hexdigest()


def seen_path(root) -> Path:
    return Path(root) / "seen.jsonl"


def load_seen(root) -> dict:
    seen = {}
    for row in read_jsonl(seen_path(root)):
        seen[row["fingerprint"]] = row
    return seen


def record_seen(root, row: dict) -> None:
    append_jsonl(seen_path(root), row)


# ---------------------------------------------------------------- 清洗（C3）

class _TextExtractor(HTMLParser):
    """最小正文抽取：标题 + meta + 可见文本。清洗规则按目标登记的
    clean_profile 选档，v1 内置 html_text_v1 一档；复杂抽取
    （trafilatura 谱系）留作后续适配器，接口形态即本函数签名。"""

    SKIP = {"script", "style", "noscript", "template"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title = None
        self.meta = {}
        self._chunks = []
        self._skip_depth = 0
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self._skip_depth += 1
        if tag == "title":
            self._in_title = True
        if tag == "meta":
            d = dict(attrs)
            key = d.get("name") or d.get("property")
            if key and d.get("content"):
                self.meta[key] = d["content"]

    def handle_endtag(self, tag):
        if tag in self.SKIP and self._skip_depth > 0:
            self._skip_depth -= 1
        if tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._skip_depth:
            return
        text = data.strip()
        if not text:
            return
        if self._in_title:
            self.title = (self.title or "") + text
        else:
            self._chunks.append(text)

    def text(self):
        return "\n".join(self._chunks)


def _shingles(text: str, n: int = 5) -> set:
    words = re.findall(r"\S+", text.lower())
    if len(words) < n:
        return {" ".join(words)} if words else set()
    return {" ".join(words[i:i + n]) for i in range(len(words) - n + 1)}


def clean_content(data: bytes, content_type: str, profile: str = "html_text_v1",
                  prior_texts=()) -> dict:
    """产出清洗件：正文 + 元数据 + 内容指纹 + 近重复标记。

    prior_texts: 本 run 已产出的清洗文本集合，用于近重复判定
    （shingle Jaccard 大于等于 0.9 记 near_duplicate_of 候选，只标记
    不删除——删不删由下游按版本链决定）。
    """
    ctype = (content_type or "").lower()
    out = {"profile": profile, "content_type": ctype}
    if "json" in ctype:
        try:
            parsed = json.loads(data.decode("utf-8", errors="replace"))
            out["kind"] = "json"
            out["json"] = parsed
            text = json.dumps(parsed, ensure_ascii=False, sort_keys=True)
        except json.JSONDecodeError:
            out["kind"] = "text"
            text = data.decode("utf-8", errors="replace")
    elif "html" in ctype or data.lstrip()[:15].lower().startswith(b"<!doctype html") \
            or b"<html" in data[:512].lower():
        parser = _TextExtractor()
        parser.feed(data.decode("utf-8", errors="replace"))
        out["kind"] = "html"
        out["title"] = parser.title
        out["metadata"] = parser.meta
        text = parser.text()
    else:
        out["kind"] = "text"
        text = data.decode("utf-8", errors="replace")
    out["text"] = text
    out["text_sha256"] = sha256_bytes(text.encode("utf-8"))
    mine = _shingles(text)
    near = None
    for prior in prior_texts:
        theirs = _shingles(prior)
        if mine and theirs:
            j = len(mine & theirs) / len(mine | theirs)
            if j >= 0.9:
                near = {"jaccard": round(j, 3)}
                break
    out["near_duplicate"] = near
    return out


def verify_store(root) -> list:
    """validate 用：逐条 provenance 重算原始哈希，对不上逐项点名。"""
    problems = []
    for row in read_provenance(root):
        if row.get("kind") not in ("fetch", "manual_import"):
            continue
        raw_path = row.get("raw_path")
        if not raw_path:
            problems.append(f"{row.get('prov_id')}：缺 raw_path（HC-6）")
            continue
        dest = Path(root) / raw_path
        if not dest.exists():
            problems.append(f"{row.get('prov_id')}：原始文件缺失 {raw_path}")
            continue
        actual = sha256_file(dest)
        if actual != row.get("sha256"):
            problems.append(
                f"{row.get('prov_id')}：原始哈希不符（登记 {row.get('sha256')}，"
                f"实算 {actual}）")
    return problems
