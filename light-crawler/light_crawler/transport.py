"""传输层 v2：重定向链、解压、解码、断点续传（能力强化批）。

v1 的传输是 fetch.http_get 一层 urllib 默认行为：重定向由 urllib
静默跟随（链条不可见、超限时把 302 空 body 当成功内容落盘）、
Content-Encoding 不解压、解码写死 utf-8。本模块逐项补齐：

- 重定向手动跟随：每一跳落 redirect_chain，环与超限显式报错，
  绝不把重定向响应本身当内容；
- 解压：Content-Encoding gzip/deflate 解开，并对误标服务器做
  gzip 魔数兜底；
- 解码：charset 判定链（响应头 -> HTML meta -> utf-8 -> gb18030
  兜底），中文站点常见的 GBK/GB2312 不再花屏；
- 断点续传：大文件流式下载落 .part + 元数据 sidecar，中断后以
  Range 续传，服务器不支持 Range 时整件重下并如实记录。

本模块只管传输，不管合规：robots、速率、熔断都在调用方。
"""

from __future__ import annotations

import gzip
import json
import re
import urllib.error
import urllib.request
import zlib
from pathlib import Path
from urllib.parse import urljoin

REDIRECT_STATUSES = (301, 302, 303, 307, 308)
MAX_REDIRECTS = 10


class TransportError(Exception):
    """传输层失败：kind 区分 timeout / network / redirect_loop /
    too_many_redirects / http_stream，供调用方落事件时点名。"""

    def __init__(self, kind, message):
        self.kind = kind
        super().__init__(message)


class FetchResult:
    def __init__(self, status, headers, body, final_url, redirect_chain,
                 decompressed=False):
        self.status = status
        self.headers = headers or {}
        self.body = body or b""
        self.final_url = final_url
        #: list[dict(url, status)]：每一跳重定向（不含最终响应）
        self.redirect_chain = redirect_chain
        self.decompressed = decompressed

    def header(self, name):
        for k, v in self.headers.items():
            if k.lower() == name.lower():
                return v
        return None


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_OPENER = urllib.request.build_opener(_NoRedirect)


def _request_once(url, headers, timeout):
    """发一次请求（不跟随重定向），返回 (status, headers, stream)。

    HTTP 错误状态不抛：以最终响应形态返回，判定留给调用方；网络
    层错误统一抛 TransportError。抽成独立函数便于测试注入。
    """
    req = urllib.request.Request(url, headers=headers or {})
    try:
        resp = _OPENER.open(req, timeout=timeout)
        return resp.status, dict(resp.headers.items()), resp
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers.items()) if e.headers else {}, e
    except Exception as e:
        kind = "timeout" if "timed out" in str(e).lower() else "network"
        raise TransportError(kind, f"{type(e).__name__}: {e}") from e


def _decompress(body: bytes, headers: dict):
    """按 Content-Encoding 解压；误标时以 gzip 魔数兜底。"""
    enc = ""
    for k, v in (headers or {}).items():
        if k.lower() == "content-encoding":
            enc = (v or "").lower()
    out, done = body, False
    try:
        if "gzip" in enc or body[:2] == b"\x1f\x8b":
            out, done = gzip.decompress(body), True
        elif "deflate" in enc:
            out, done = zlib.decompress(body), True
    except Exception:
        return body, False
    return out, done


def fetch(url, headers=None, timeout=30.0) -> FetchResult:
    """GET 并手动跟随重定向，返回最终响应（含完整重定向链）。"""
    chain, visited, current = [], set(), url
    while True:
        if current in visited:
            raise TransportError(
                "redirect_loop", f"重定向成环：{current} 已访问过")
        visited.add(current)
        status, resp_headers, stream = _request_once(
            current, headers, timeout)
        location = None
        for k, v in resp_headers.items():
            if k.lower() == "location":
                location = v
        if status in REDIRECT_STATUSES and location:
            try:
                stream.read()
            except Exception:
                pass
            chain.append({"url": current, "status": status})
            if len(chain) > MAX_REDIRECTS:
                raise TransportError(
                    "too_many_redirects",
                    f"重定向超过 {MAX_REDIRECTS} 跳（链长 {len(chain)}）")
            current = urljoin(current, location)
            continue
        try:
            raw = stream.read()
        except Exception as e:
            raise TransportError(
                "http_stream", f"响应体读取中断：{type(e).__name__}: {e}"
            ) from e
        body, decompressed = _decompress(raw, resp_headers)
        return FetchResult(status, resp_headers, body, current, chain,
                           decompressed=decompressed)


# ---------------------------------------------------------------- 解码

_CHARSET_ALIASES = {"gb2312": "gb18030", "gbk": "gb18030",
                    "gb-2312": "gb18030", "x-gbk": "gb18030"}


def _sniff_meta_charset(body: bytes):
    head = body[:4096].decode("ascii", errors="ignore")
    m = re.search(r"charset\s*=\s*[\"']?\s*([a-zA-Z0-9_\-]+)", head)
    return m.group(1) if m else None


def decode_text(body: bytes, headers: dict = None) -> str:
    """字节 -> 文本的判定链：响应头 charset -> meta charset ->
    utf-8 严格解码 -> gb18030 兜底 -> utf-8 宽容解码。

    每一步失败都落到下一档，不抛错：清洗层需要的是尽力可读的
    文本 + 如实的花屏消除，而不是异常。
    """
    if not body:
        return ""
    if body.startswith(b"\xef\xbb\xbf"):
        return body.decode("utf-8-sig", errors="replace")
    if body.startswith((b"\xff\xfe", b"\xfe\xff")):
        return body.decode("utf-16", errors="replace")
    candidates = []
    ctype = ""
    for k, v in (headers or {}).items():
        if k.lower() == "content-type":
            ctype = v or ""
    m = re.search(r"charset=([a-zA-Z0-9_\-]+)", ctype)
    if m:
        candidates.append(m.group(1))
    meta = _sniff_meta_charset(body)
    if meta:
        candidates.append(meta)
    candidates += ["utf-8", "gb18030"]
    seen = set()
    for enc in candidates:
        enc_norm = _CHARSET_ALIASES.get(enc.lower(), enc.lower())
        if enc_norm in seen:
            continue
        seen.add(enc_norm)
        try:
            return body.decode(enc_norm)
        except (UnicodeDecodeError, LookupError):
            continue
    return body.decode("utf-8", errors="replace")


# ---------------------------------------------------------------- 断点续传

def _part_meta_path(part_path: Path) -> Path:
    return part_path.with_suffix(part_path.suffix + ".meta.json")


def download_resumable(url, part_path, headers=None, timeout=60.0,
                       chunk_size=65536, raise_on_status=True) -> dict:
    """流式下载到 part_path（.part 文件），支持 Range 断点续传。

    返回 dict：bytes_total / resumed_from / restarted / sha256 /
    status / headers。传输中断抛 TransportError，已落盘的字节与
    sidecar 元数据保留，下次调用自动从断点续。服务器忽略 Range
    回 200 时整件重下（restarted=True），不假装续上。
    raise_on_status=False 时，非 200/206 的状态不抛错而是原样
    返回（供调用方走回绝记账口径，如 403 触发熔断）。
    """
    import hashlib
    part_path = Path(part_path)
    part_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path = _part_meta_path(part_path)
    meta = {}
    if meta_path.is_file():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8")) or {}
        except Exception:
            meta = {}
    if meta.get("url") != url:
        meta = {"url": url}
        if part_path.exists():
            part_path.unlink()
    have = part_path.stat().st_size if part_path.exists() else 0
    resumed_from, restarted = have, False

    req_headers = dict(headers or {})
    if have > 0:
        req_headers["Range"] = f"bytes={have}-"
    current, chain_seen = url, set()
    while True:
        if current in chain_seen:
            raise TransportError("redirect_loop", f"重定向成环：{current}")
        chain_seen.add(current)
        status, resp_headers, stream = _request_once(
            current, req_headers, timeout)
        location = next((v for k, v in resp_headers.items()
                         if k.lower() == "location"), None)
        if status in REDIRECT_STATUSES and location:
            try:
                stream.read()
            except Exception:
                pass
            if len(chain_seen) > MAX_REDIRECTS:
                raise TransportError("too_many_redirects",
                                     "下载重定向超限")
            current = urljoin(current, location)
            continue
        break

    mode = "ab"
    if have > 0 and status == 200:
        # 服务器不支持 Range：整件重下
        mode, resumed_from, restarted = "wb", 0, True
        have = 0
    if status == 416 and have > 0:
        # 已有字节即全件（服务器称范围不可满足且总长吻合时由调用方核对）
        data = part_path.read_bytes()
        return {"bytes_total": have, "resumed_from": have,
                "restarted": False, "status": status, "headers": resp_headers,
                "final_url": current,
                "sha256": hashlib.sha256(data).hexdigest()}
    if status not in (200, 206):
        if not raise_on_status:
            return {"bytes_total": have, "resumed_from": resumed_from,
                    "restarted": restarted, "status": status,
                    "headers": resp_headers, "final_url": current,
                    "sha256": None}
        raise TransportError("http_stream",
                             f"下载响应状态 {status}，不可续传")

    written = have
    try:
        with part_path.open(mode) as f:
            while True:
                chunk = stream.read(chunk_size)
                if not chunk:
                    break
                f.write(chunk)
                written += len(chunk)
    except TransportError:
        raise
    except Exception as e:
        meta["bytes_written"] = written
        meta_path.write_text(json.dumps(meta, ensure_ascii=False),
                             encoding="utf-8")
        raise TransportError(
            "http_stream",
            f"下载中断于 {written} 字节（.part 已保留可续传）："
            f"{type(e).__name__}: {e}") from e
    total = written
    meta.update({"bytes_written": total, "complete": True})
    meta_path.write_text(json.dumps(meta, ensure_ascii=False),
                         encoding="utf-8")
    data = part_path.read_bytes()
    return {"bytes_total": total, "resumed_from": resumed_from,
            "restarted": restarted, "status": status,
            "headers": resp_headers, "final_url": current,
            "sha256": hashlib.sha256(data).hexdigest()}
