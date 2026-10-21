"""Obsidian URI 链接铸造（工具层 T3，TOOLING-PLAN §5.1 uri.py）。

obsidian:// 核心协议与 Advanced URI 插件（Vinzent03，MIT）的
导航类链接铸造面：供索引页与报告嵌「一键在 Obsidian 打开」链接。

定位与纪律（DR-O §三.6 裁决沿用）：
- **只铸导航链接，不铸写入类链接**：链接即代码——索引页里只许
  放打开文件/标题/块、打开日记、触发搜索这类导航与轻触发链接；
  obsidian://new 等写入类动作在本模块直接拒绝并点名。没装
  Advanced URI 时 adv-uri 链接只是失效链接，正文可读性不受
  影响，属纯增强、失效无害。
- **只产 URI 与规程记录，不冒充执行结果**：URI 是单向触发，
  无回执、无读回——铸造函数返回的记录恒带 executed=False，
  任何调用方不许据链接存在宣称已打开/已定位；实际打开结果
  以 Obsidian 内呈现为准，本模块不验、不能验。
- 全部参数值百分号编码；vault 名必填；控制字符拒绝（防链接
  结构被参数值撑破）。
"""

from __future__ import annotations

import urllib.parse

SURFACE = "uri"
CORE_BASE = "obsidian://"
ADV_BASE = "obsidian://adv-uri"

#: 拒绝铸造的写入类动作（链接即代码，索引页只许导航类）。
WRITE_ACTIONS = frozenset({
    "new", "append", "create", "write", "edit", "delete",
    "prepend", "insert", "command",
})


class UriError(Exception):
    def __init__(self, gaps):
        self.gaps = list(gaps)
        super().__init__("；".join(self.gaps))


def _enc(value) -> str:
    return urllib.parse.quote(str(value), safe="")


def _check(label, value, required=True):
    if value is None or (required and str(value) == ""):
        raise UriError([f"{label} 不能为空"])
    text = str(value)
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in text):
        raise UriError([f"{label} 含控制字符，拒绝铸造：{label}"])
    return text


def _record(kind, action, uri, vault, target):
    """铸造记录：恒 executed=False，附规程说明（不冒充执行结果）。"""
    return {"surface": SURFACE, "kind": kind, "action": action,
            "uri": uri, "vault": vault, "target": target,
            "executed": False,
            "note": "仅铸造导航链接：单向触发、无回执、未执行；"
                    "是否打开以 Obsidian 内实际呈现为准，本记录"
                    "不构成执行证据"}


# ---------------------------------------------------------------- 核心协议

def open_uri(vault, file):
    """obsidian://open：打开 vault 内某篇笔记。"""
    vault = _check("vault", vault)
    file = _check("file", file)
    uri = (f"{CORE_BASE}open?vault={_enc(vault)}"
           f"&file={_enc(file)}")
    return _record("navigation", "open", uri, vault, {"file": file})


def search_uri(vault, query):
    """obsidian://search：打开搜索面并预填词（触发搜索，无结果回传）。"""
    vault = _check("vault", vault)
    query = _check("query", query)
    uri = (f"{CORE_BASE}search?vault={_enc(vault)}"
           f"&query={_enc(query)}")
    return _record("navigation", "search", uri, vault,
                   {"query": query})


# ---------------------------------------------------------------- Advanced URI

def _adv_uri(vault, params, action, target):
    query = "&".join(f"{k}={_enc(v)}" for k, v in params)
    return _record("navigation", action, f"{ADV_BASE}?{query}",
                   vault, target)


def open_heading_uri(vault, file, heading):
    """adv-uri：打开文件并定位到标题。"""
    vault = _check("vault", vault)
    file = _check("filepath", file)
    heading = _check("heading", heading)
    return _adv_uri(
        vault, [("vault", vault), ("filepath", file),
                ("heading", heading)],
        "open-heading", {"file": file, "heading": heading})


def open_block_uri(vault, file, block):
    """adv-uri：打开文件并定位到块引用（block 不带 ^ 前缀亦可）。"""
    vault = _check("vault", vault)
    file = _check("filepath", file)
    block = _check("block", block).lstrip("^")
    return _adv_uri(
        vault, [("vault", vault), ("filepath", file),
                ("block", block)],
        "open-block", {"file": file, "block": block})


def daily_uri(vault):
    """adv-uri：打开当日日记（daily=true）。"""
    vault = _check("vault", vault)
    return _adv_uri(vault, [("vault", vault), ("daily", "true")],
                    "daily", {"daily": True})


# ---------------------------------------------------------------- 分发

def mint(action, **kwargs):
    """按动作名铸造：只许导航类；写入类动作点名拒绝。"""
    if action in WRITE_ACTIONS:
        raise UriError([
            f"动作 {action} 是写入类：本模块只铸导航链接"
            "（DR-O §三.6『链接即代码』纪律，索引页只许放导航类"
            "链接）；写入请走文件层命令面"])
    dispatch = {"open": open_uri, "search": search_uri,
                "open-heading": open_heading_uri,
                "open-block": open_block_uri, "daily": daily_uri}
    fn = dispatch.get(action)
    if fn is None:
        raise UriError([f"未知导航动作：{action}"
                        f"（可用：{sorted(dispatch)}）"])
    return fn(**kwargs)


def markdown_link(label, record):
    """把铸造记录渲染为 Markdown 链接（供索引页/报告嵌入）。"""
    if not isinstance(record, dict) or "uri" not in record:
        raise UriError(["markdown_link 需要 uri.mint 的铸造记录"])
    return f"[{label}]({record['uri']})"
