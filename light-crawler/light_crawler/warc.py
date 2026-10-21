"""WARC 全记录档（ISO 28500，第五批计算扩面，PLAN §13 P1）。

留存档位 warc_full 的实现：纯标准库自写 WARC/1.0 记录，不依赖
warcio 等第三方库——该档因此恒可用，不存在「登记了却跑不起来」
的假装空间。写出形态定版：

- 不压缩的 .warc 字节流（gzip 的多成员封装由回读端兼容接受，
  见 read_records）。选不压缩是审计取向：记录偏移稳定、摘要可
  逐条复算、文本工具可直读；体积代价对本包的 run 量级可接受。
- 文件布局：一 run 一档，落 runs/<run_id>/archive.warc，首条必为
  warcinfo；人工导入无 run，落 warc/imports.warc 追加写。
- response 记录的 block 为 HTTP 报文：状态行 + 响应头 + 空行 +
  实体。传输层交到本模块时实体已解压/解块，故重构报文时剔除
  Content-Encoding / Transfer-Encoding 并按实体实际长度重写
  Content-Length——记录内部自洽（payload 摘要按记录内实体字节
  复算可过）；原始响应字节本身仍由 store/ 内容寻址原样留存，
  sha256 在 provenance 中，两条证据链并存互不冒充。
- 摘要口径（ISO 28500）：WARC-Block-Digest 覆盖整个 block；
  WARC-Payload-Digest 在 response 记录覆盖实体、在 resource
  记录覆盖资源字节本体；算法 sha1、Base32 大写去填充、前缀
  「sha1:」——与生态通行形态一致，外部 WARC 工具可复算。

回读校验（verify_*）：逐记录重验分帧（Content-Length）、block
摘要、payload 摘要与记录尾分隔，问题逐条点名（记录 id + 偏移 +
项）。校验只读，不修复、不回写。
"""

from __future__ import annotations

import base64
import gzip
import hashlib
import uuid
from datetime import datetime, timezone
from pathlib import Path

WARC_VERSION_LINE = b"WARC/1.0"
CRLF = b"\r\n"
RECORD_SEPARATOR = b"\r\n\r\n"

SOFTWARE_FIELD = "light-crawler (Light-Science channel layer)"
CONFORMS_TO = "http://bibnum.bnf.fr/WARC/WARC_ISO_28500_version1_latestdraft.pdf"


def _digest(data: bytes) -> str:
    """ISO 28500 摘要形态：sha1 + Base32（大写、去填充）。"""
    return "sha1:" + base64.b32encode(
        hashlib.sha1(data).digest()).decode("ascii").rstrip("=")


def _warc_date(ts: str = None) -> str:
    if ts:
        return ts
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _record_id() -> str:
    return f"<urn:uuid:{uuid.uuid4()}>"


def _build_record(headers: list, block: bytes) -> bytes:
    lines = [WARC_VERSION_LINE]
    for key, value in headers:
        lines.append(f"{key}: {value}".encode("utf-8"))
    return CRLF.join(lines) + CRLF + CRLF + block + RECORD_SEPARATOR


def build_http_block(status: int, headers: dict, body: bytes) -> bytes:
    """由传输层部件重构 HTTP 响应报文（见模块头注的归一化口径）。"""
    from http.client import responses as _reasons
    reason = _reasons.get(status, "")
    lines = [f"HTTP/1.1 {status} {reason}".rstrip()]
    for key, value in (headers or {}).items():
        if key.lower() in ("content-length", "content-encoding",
                           "transfer-encoding"):
            continue
        lines.append(f"{key}: {value}")
    lines.append(f"Content-Length: {len(body)}")
    return ("\r\n".join(lines) + "\r\n\r\n").encode(
        "utf-8", "surrogateescape") + body


def split_http_block(block: bytes):
    """把 HTTP 报文 block 拆为 (状态行, 头 dict, 实体)；非报文返回 None。"""
    head, sep, entity = block.partition(b"\r\n\r\n")
    if not sep:
        return None
    lines = head.split(b"\r\n")
    if not lines or not lines[0].startswith(b"HTTP/"):
        return None
    headers = {}
    for line in lines[1:]:
        key, _, value = line.partition(b":")
        if key.strip():
            headers[key.decode("utf-8", "replace").strip()] = \
                value.decode("utf-8", "replace").strip()
    return lines[0].decode("utf-8", "replace"), headers, entity


class WarcArchive:
    """追加式 WARC 写出器：一档一实例，首条记录自动写 warcinfo。

    已存在的文件（imports.warc 场景）以追加模式打开、不重写
    warcinfo。每条 add_* 返回 {warc_record_id, warc_offset}，
    offset 为该记录在文件字节流中的起始偏移（含 warcinfo 之后
    的累计值），供 provenance 引用与定向回读。
    """

    def __init__(self, path):
        self.path = Path(path)
        self._warcinfo_done = self.path.exists() and self.path.stat().st_size > 0

    def _append(self, record: bytes) -> int:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        offset = self.path.stat().st_size if self.path.exists() else 0
        with self.path.open("ab") as f:
            f.write(record)
        return offset

    def _ensure_warcinfo(self) -> None:
        if self._warcinfo_done:
            return
        fields = [
            ("software", SOFTWARE_FIELD),
            ("format", "WARC File Format 1.0"),
            ("conformsTo", CONFORMS_TO),
            ("created", _warc_date()),
            ("description", "light-crawler warc_full retention tier: "
                            "one archive per run (runs/<run_id>/archive.warc); "
                            "manual imports append to warc/imports.warc"),
        ]
        block = "".join(f"{k}: {v}\r\n" for k, v in fields).encode("utf-8")
        rid = _record_id()
        record = _build_record([
            ("WARC-Type", "warcinfo"),
            ("WARC-Date", _warc_date()),
            ("WARC-Filename", self.path.name),
            ("WARC-Record-ID", rid),
            ("Content-Type", "application/warc-fields"),
            ("Content-Length", str(len(block))),
        ], block)
        self._append(record)
        self._warcinfo_done = True

    def add_response(self, *, uri: str, status: int, headers: dict,
                     body: bytes, ip_address: str = None) -> dict:
        """写一条 response 记录（HTTP 捕获）。返回 provenance 引用段。"""
        self._ensure_warcinfo()
        block = build_http_block(status, headers, body)
        rid = _record_id()
        hdrs = [
            ("WARC-Type", "response"),
            ("WARC-Target-URI", uri),
            ("WARC-Date", _warc_date()),
            ("WARC-Record-ID", rid),
            ("WARC-Block-Digest", _digest(block)),
            ("WARC-Payload-Digest", _digest(body)),
            ("Content-Type", "application/http; msgtype=response"),
            ("Content-Length", str(len(block))),
        ]
        if ip_address:
            hdrs.insert(4, ("WARC-IP-Address", ip_address))
        offset = self._append(_build_record(hdrs, block))
        return {"warc_record_id": rid, "warc_offset": offset}

    def add_resource(self, *, uri: str, data: bytes,
                     content_type: str) -> dict:
        """写一条 resource 记录（人工导入等非 HTTP 捕获的资源本体）。"""
        self._ensure_warcinfo()
        rid = _record_id()
        hdrs = [
            ("WARC-Type", "resource"),
            ("WARC-Target-URI", uri),
            ("WARC-Date", _warc_date()),
            ("WARC-Record-ID", rid),
            ("WARC-Block-Digest", _digest(data)),
            ("WARC-Payload-Digest", _digest(data)),
            ("Content-Type", content_type or "application/octet-stream"),
            ("Content-Length", str(len(data))),
        ]
        offset = self._append(_build_record(hdrs, data))
        return {"warc_record_id": rid, "warc_offset": offset}


# ---------------------------------------------------------------- 回读校验

def read_records(path) -> list:
    """解析一个 WARC 文件为记录清单（只读）。

    接受不压缩 .warc 与 gzip 封装 .warc.gz（gzip 流整体解压后按
    同一分帧解析；偏移以解压后字节流为准）。每条返回
    {offset, headers, block, raw_length, framing_problem}；
    framing_problem 非空表示该记录分帧已坏、后续解析不可信，
    调用方（verify）会点名并停止对该文件的继续解析。
    """
    raw = Path(path).read_bytes()
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    records = []
    pos = 0
    total = len(raw)
    while pos < total:
        # 记录间允许残余分隔空白（本包写出恒为紧接的下一条记录）
        if raw[pos:pos + 2] == CRLF:
            pos += 2
            continue
        start = pos
        head_end = raw.find(CRLF + CRLF, pos)
        if head_end < 0:
            records.append({"offset": start, "headers": {},
                            "block": b"", "raw_length": total - start,
                            "framing_problem": "找不到记录头结束标记"})
            break
        head = raw[pos:head_end].split(CRLF)
        if head[0] != WARC_VERSION_LINE:
            records.append({"offset": start, "headers": {},
                            "block": b"", "raw_length": total - start,
                            "framing_problem":
                                f"版本行不是 WARC/1.0：{head[0][:40]!r}"})
            break
        headers = {}
        bad = None
        for line in head[1:]:
            key, _, value = line.partition(b":")
            if not _:
                bad = f"头行不可解析：{line[:60]!r}"
                break
            headers[key.decode("utf-8", "replace").strip()] = \
                value.decode("utf-8", "replace").strip()
        if bad:
            records.append({"offset": start, "headers": headers,
                            "block": b"", "raw_length": total - start,
                            "framing_problem": bad})
            break
        try:
            length = int(headers.get("Content-Length", ""))
        except ValueError:
            records.append({"offset": start, "headers": headers,
                            "block": b"", "raw_length": total - start,
                            "framing_problem": "Content-Length 缺失或非整数"})
            break
        block_start = head_end + 4
        block_end = block_start + length
        if block_end > total:
            records.append({"offset": start, "headers": headers,
                            "block": raw[block_start:],
                            "raw_length": total - start,
                            "framing_problem":
                                f"Content-Length {length} 超出文件剩余字节"})
            break
        block = raw[block_start:block_end]
        tail = raw[block_end:block_end + 4]
        framing = None
        if tail not in (RECORD_SEPARATOR, b""):
            framing = "记录尾分隔不是双 CRLF"
        records.append({"offset": start, "headers": headers,
                        "block": block,
                        "raw_length": block_end + 4 - start
                        if tail == RECORD_SEPARATOR else block_end - start,
                        "framing_problem": framing})
        pos = block_end + (4 if tail == RECORD_SEPARATOR else 0)
    return records


def verify_records(records: list) -> list:
    """逐记录复算摘要，返回问题清单（空 = 全过）。逐条点名。"""
    problems = []
    for rec in records:
        label = (rec["headers"].get("WARC-Record-ID")
                 or f"offset {rec['offset']}")
        if rec.get("framing_problem"):
            problems.append(f"{label}：分帧损坏——{rec['framing_problem']}")
            continue
        block = rec["block"]
        declared_block = rec["headers"].get("WARC-Block-Digest")
        if declared_block and declared_block != _digest(block):
            problems.append(
                f"{label}：WARC-Block-Digest 不符（登记 {declared_block}，"
                f"实算 {_digest(block)}）")
        declared_payload = rec["headers"].get("WARC-Payload-Digest")
        if declared_payload:
            rtype = rec["headers"].get("WARC-Type")
            payload = None
            if rtype == "response":
                split = split_http_block(block)
                if split is None:
                    problems.append(
                        f"{label}：response 记录的 block 不是 HTTP 报文，"
                        "payload 摘要无从复算")
                else:
                    payload = split[2]
            elif rtype in ("resource", "revisit"):
                payload = block
            if payload is not None and declared_payload != _digest(payload):
                problems.append(
                    f"{label}：WARC-Payload-Digest 不符"
                    f"（登记 {declared_payload}，实算 {_digest(payload)}）")
    return problems


def verify_file(path) -> dict:
    """校验一个 WARC 文件：返回 {path, records: [...摘要], problems}。"""
    path = Path(path)
    if not path.is_file():
        return {"path": str(path), "records": [],
                "problems": [f"WARC 文件缺失：{path}"]}
    records = read_records(path)
    summary = [{
        "offset": r["offset"],
        "record_id": r["headers"].get("WARC-Record-ID"),
        "type": r["headers"].get("WARC-Type"),
        "uri": r["headers"].get("WARC-Target-URI"),
    } for r in records]
    return {"path": str(path), "records": summary,
            "problems": verify_records(records)}
