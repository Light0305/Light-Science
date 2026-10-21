"""前端接口与链接发现（能力强化批）。

v1 没有任何发现能力：fetch 只抓调用方逐个点名的 URL，sitemap
只在 robots 解析里被读出、无人消费，分页与前端接口全靠人肉。
本模块补四件事，全部证据驱动（只登记页面/脚本里真实出现的
东西，不猜 URL）：

- 链接与资源抽取：a/link/script/img/iframe/form 目标归一化，
  分页关系（rel=next）单列；
- 内嵌数据抽取：__NEXT_DATA__ / __NUXT__ / JSON-LD / 内联
  application/json 脚本块；
- 脚本端点挖掘：从同源脚本里提取 fetch/axios/XHR/url 字段中
  的接口候选，登记为可枚举数据源；
- sitemap 解析：urlset 与 sitemapindex 两形态，子图递归由
  调用方按上限展开。

发现结果落 targets/<id>/discovered.jsonl（只增、去重），是
crawl 任务的前沿来源之一，也可经 sources 命令单独查询。
JS 壳识别（js_shell_signals）供回退链判断页面是否需要渲染。
"""

from __future__ import annotations

import hashlib
import json
import re
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse

from .util import append_jsonl, read_jsonl, utcnow


# ---------------------------------------------------------------- 链接抽取

class _LinkParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []        # {href, rel, tag}
        self.scripts = []      # script src
        self.embedded = []     # {id/type, text}

    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        if tag == "a" and d.get("href"):
            self.links.append({"href": d["href"],
                               "rel": (d.get("rel") or "").lower(),
                               "tag": "a"})
        elif tag == "link" and d.get("href"):
            self.links.append({"href": d["href"],
                               "rel": (d.get("rel") or "").lower(),
                               "tag": "link"})
        elif tag == "script" and d.get("src"):
            self.scripts.append(d["src"])
        elif tag in ("img", "iframe") and d.get("src"):
            self.links.append({"href": d["src"], "rel": "", "tag": tag})
        elif tag == "form" and d.get("action"):
            self.links.append({"href": d["action"], "rel": "",
                               "tag": "form"})

    def handle_data(self, data):
        pass


class _EmbeddedParser(HTMLParser):
    """抓取带 id 的 JSON 脚本块与 JSON-LD（与正文抽取分工）。"""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocks = []
        self._cur = None

    def handle_starttag(self, tag, attrs):
        if tag != "script":
            return
        d = dict(attrs)
        t = (d.get("type") or "").lower()
        sid = d.get("id") or ""
        if sid in ("__NEXT_DATA__", "__NUXT__") or "json" in t:
            self._cur = {"id": sid or None, "type": t, "text": ""}

    def handle_data(self, data):
        if self._cur is not None:
            self._cur["text"] += data

    def handle_endtag(self, tag):
        if tag == "script" and self._cur is not None:
            self.blocks.append(self._cur)
            self._cur = None


def _abs(base_url: str, href: str):
    if not href or href.startswith(("javascript:", "mailto:", "tel:",
                                    "data:", "#")):
        return None
    return urljoin(base_url, href)


def extract_links(html_text: str, page_url: str) -> dict:
    """从 HTML 抽链接：pages（a 链接）/ next（分页）/ assets。"""
    parser = _LinkParser()
    parser.feed(html_text or "")
    pages, next_urls, assets = [], [], []
    seen = {"pages": set(), "next": set(), "assets": set()}

    def push(bucket_name, url):
        bucket = {"pages": pages, "next": next_urls,
                  "assets": assets}[bucket_name]
        if url and url not in seen[bucket_name]:
            seen[bucket_name].add(url)
            bucket.append(url)

    for link in parser.links:
        url = _abs(page_url, link["href"])
        if url is None:
            continue
        if "next" in (link["rel"] or ""):
            push("next", url)
            push("pages", url)
        elif link["tag"] == "a" or link["tag"] == "form":
            push("pages", url)
        else:
            push("assets", url)
    scripts = []
    for src in parser.scripts:
        url = _abs(page_url, src)
        if url:
            scripts.append(url)
            push("assets", url)
    return {"pages": pages, "next": next_urls, "assets": assets,
            "scripts": scripts}


def extract_embedded_json(html_text: str) -> list:
    """抽取内嵌结构化数据块（可解析的解析、不可解析的留原文片段）。"""
    parser = _EmbeddedParser()
    parser.feed(html_text or "")
    out = []
    for block in parser.blocks:
        text = block["text"].strip()
        if not text:
            continue
        kind = ("next_data" if block["id"] == "__NEXT_DATA__"
                else "nuxt" if block["id"] == "__NUXT__"
                else "json_ld" if "ld+json" in block["type"]
                else "inline_json")
        row = {"kind": kind, "raw_len": len(text)}
        try:
            row["data"] = json.loads(text)
        except json.JSONDecodeError:
            row["raw_head"] = text[:200]
        out.append(row)
    return out


# ---------------------------------------------------------------- 脚本端点挖掘

_ENDPOINT_PATTERNS = (
    ("fetch", re.compile(r"fetch\(\s*[`'\"]([^`'\"]+)[`'\"]")),
    ("axios", re.compile(r"axios\.(?:get|post|put|delete)\(\s*[`'\"]([^`'\"]+)[`'\"]")),
    ("xhr", re.compile(r"\.open\(\s*[`'\"][A-Z]+[`'\"]\s*,\s*[`'\"]([^`'\"]+)[`'\"]")),
    ("url_field", re.compile(r"\burl\s*:\s*[`'\"]([^`'\"]+)[`'\"]")),
    ("api_literal", re.compile(r"[`'\"](/api/[^`'\"\s]+)[`'\"]")),
)


def mine_script_endpoints(js_text: str, page_url: str) -> list:
    """从脚本源码里挖接口候选 URL（证据 = 命中的调用形态）。

    只收同源可达者与站内绝对路径；含模板占位（${...}）的记为
    template 形态、不当可抓 URL 登记。
    """
    found = {}
    for via, pattern in _ENDPOINT_PATTERNS:
        for m in pattern.finditer(js_text or ""):
            raw = m.group(1)
            if "${" in raw or "{ {" in raw:
                key = ("template", raw)
                found.setdefault(key, {
                    "kind": "api_template", "url": None, "raw": raw,
                    "via": via})
                continue
            url = _abs(page_url, raw)
            if url is None:
                continue
            found.setdefault(("ep", url), {
                "kind": "api_endpoint", "url": url, "raw": raw,
                "via": via})
    return sorted(found.values(), key=lambda r: r.get("url") or r["raw"])


# ---------------------------------------------------------------- sitemap

def parse_sitemap(xml_bytes: bytes) -> dict:
    """解析 sitemap：返回 {urls, child_sitemaps}。坏 XML 返回空并标注。"""
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return {"urls": [], "child_sitemaps": [], "error": "xml_parse_failed"}
    urls, children = [], []
    for elem in root.iter():
        tag = elem.tag.rsplit("}", 1)[-1]
        if tag == "loc" and elem.text:
            urls.append(elem.text.strip())
    # urlset 与 sitemapindex 的 loc 语义靠根元素名区分
    root_tag = root.tag.rsplit("}", 1)[-1]
    if root_tag == "sitemapindex":
        return {"urls": [], "child_sitemaps": urls, "error": None}
    return {"urls": urls, "child_sitemaps": [], "error": None}


# ---------------------------------------------------------------- JS 壳识别

def js_shell_signals(html_text: str, cleaned_text: str) -> dict:
    """判断一个静态抓到的 HTML 页是否是 JS 壳（内容靠脚本注入）。

    依据全是页面自身证据：可见文本极少、挂载点容器在场、框架
    数据岛在场、noscript 提示。命中只说明「静态形态没拿到内容」，
    是否升级渲染由回退链按登记授权裁决。
    """
    html = html_text or ""
    signals = []
    text_len = len((cleaned_text or "").strip())
    if text_len < 40:
        signals.append(f"visible_text_len={text_len} (<40)")
    if re.search(r'id=["\'](root|app|__next)["\']', html):
        signals.append("mount_container_present")
    if "__NEXT_DATA__" in html or "__NUXT__" in html:
        signals.append("framework_data_island_present")
    if len(re.findall(r"<script", html)) >= 2:
        signals.append("script_tags>=2")
    if "enable javascript" in html.lower() or "noscript" in html.lower():
        signals.append("noscript_hint")
    suspected = bool(
        text_len < 40 and (len(signals) >= 2))
    return {"suspected": suspected, "signals": signals,
            "visible_text_len": text_len}


# ---------------------------------------------------------------- 发现源登记账

def discovered_path(root, target_id) -> Path:
    return Path(root) / "targets" / target_id / "discovered.jsonl"


def register_discovered(root, target_id, rows: list) -> list:
    """把发现结果登记进发现账（按 kind+url 去重，只增）。返回新增行。"""
    path = discovered_path(root, target_id)
    existing = {(r.get("kind"), r.get("url"))
                for r in read_jsonl(path) if r.get("url")}
    added = []
    for row in rows:
        url = row.get("url")
        if not url or (row.get("kind"), url) in existing:
            continue
        existing.add((row.get("kind"), url))
        full = {
            "source_id": "ds-" + hashlib.sha256(
                f"{row.get('kind')}|{url}".encode()).hexdigest()[:12],
            "at": utcnow(), "target_id": target_id, **row}
        append_jsonl(path, full)
        added.append(full)
    return added


def list_discovered(root, target_id) -> list:
    return read_jsonl(discovered_path(root, target_id))


def same_host(url: str, base_url: str) -> bool:
    a, b = urlparse(url), urlparse(base_url)
    return (a.scheme, a.netloc) == (b.scheme, b.netloc)
