"""WARC 全记录档 warc_full（第五批，PLAN §13 P1；ISO 28500）。

钉口径：登记/预检/落盘三处同步放行；写出为纯标准库实现、无
第三方依赖；回读逐记录复算 block/payload 摘要，篡改与截断
必须被点名；轻量档默认行为不变。
"""

import gzip
import json
from pathlib import Path

from conftest import make_reg

from light_crawler import fetch as fetch_mod
from light_crawler import precheck as pc
from light_crawler import project, storage, warc
from light_crawler.validate import validate_workspace

NO_SLEEP = lambda s: None  # noqa: E731

BODY = b"<html><body><h1>WARC demo</h1><p>archived body bytes</p></body></html>"


# ---------------------------------------------------------------- 单元层

def test_warc_roundtrip_and_digests(tmp_path):
    path = tmp_path / "a.warc"
    arch = warc.WarcArchive(path)
    ref_resp = arch.add_response(
        uri="http://example.org/page", status=200,
        headers={"Content-Type": "text/html", "ETag": '"x1"'}, body=BODY)
    ref_res = arch.add_resource(
        uri="http://example.org/file", data=b"plain resource bytes",
        content_type="text/plain")
    result = warc.verify_file(path)
    assert result["problems"] == []
    types = [r["type"] for r in result["records"]]
    assert types == ["warcinfo", "response", "resource"]
    assert result["records"][1]["record_id"] == ref_resp["warc_record_id"]
    assert result["records"][1]["offset"] == ref_resp["warc_offset"]
    assert result["records"][2]["offset"] == ref_res["warc_offset"]

    records = warc.read_records(path)
    split = warc.split_http_block(records[1]["block"])
    assert split[0].startswith("HTTP/1.1 200")
    assert split[2] == BODY                      # 实体原样可回读
    # 重构报文的编码归一化：实体已解码，Content-Length 按实长
    assert split[1]["Content-Length"] == str(len(BODY))
    digest = records[1]["headers"]["WARC-Payload-Digest"]
    assert digest.startswith("sha1:") and "=" not in digest


def test_warc_tamper_and_truncation_named(tmp_path):
    path = tmp_path / "b.warc"
    arch = warc.WarcArchive(path)
    ref = arch.add_response(
        uri="http://example.org/p", status=200,
        headers={"Content-Type": "text/html"}, body=BODY)
    raw = bytearray(path.read_bytes())
    pos = bytes(raw).find(b"archived body bytes")
    assert pos > 0
    raw[pos] ^= 0xFF
    path.write_bytes(bytes(raw))
    result = warc.verify_file(path)
    assert any(ref["warc_record_id"] in p and "Digest" in p
               for p in result["problems"])

    path2 = tmp_path / "c.warc"
    warc.WarcArchive(path2).add_response(
        uri="http://example.org/p", status=200, headers={}, body=BODY)
    data = path2.read_bytes()
    path2.write_bytes(data[:len(data) - 30])     # 尾部截断
    result2 = warc.verify_file(path2)
    assert result2["problems"]                   # 分帧损坏被点名


def test_warc_reader_accepts_gzip(tmp_path):
    path = tmp_path / "d.warc"
    warc.WarcArchive(path).add_response(
        uri="http://example.org/p", status=200, headers={}, body=BODY)
    gz = tmp_path / "d.warc.gz"
    gz.write_bytes(gzip.compress(path.read_bytes()))
    assert warc.verify_file(gz)["problems"] == []


def test_warc_missing_file_named(tmp_path):
    result = warc.verify_file(tmp_path / "nope.warc")
    assert result["problems"] and "缺失" in result["problems"][0]


# ---------------------------------------------------------------- 集成层

def _ready(ws, base, **kw):
    reg = make_reg(base, **kw)
    project.register_target(ws, reg)
    rec = pc.run_precheck(ws, reg["target_id"])
    assert rec["status"] == "effective"
    return reg["target_id"], rec


def _transport(url, headers=None):
    return fetch_mod.Response(
        200, {"Content-Type": "text/html"}, BODY, url)


def test_warc_full_fetch_end_to_end(ws, site):
    _, base = site
    tid, rec = _ready(ws, base, retention_tier="warc_full")
    # 预检记录落了留存裁决（同步放行的证据在预检层可见）
    assert rec["checks"]["retention"]["tier"] == "warc_full"

    fetch_mod.fetch_run(ws, tid, urls=[base + "/page.html"],
                        transport=_transport, sleep=NO_SLEEP)
    prov = [r for r in storage.read_provenance(ws) if r["kind"] == "fetch"]
    assert len(prov) == 1
    row = prov[0]
    assert row["retention_tier"] == "warc_full"
    assert row["warc_path"].endswith("archive.warc")
    assert row["warc_record_id"].startswith("<urn:uuid:")
    assert row["warc_offset"] > 0                # warcinfo 之后
    # 轻量档证据链并存：原始字节仍在 store/ 且哈希对得上
    assert storage.sha256_bytes(
        (ws / row["raw_path"]).read_bytes()) == row["sha256"]

    result = warc.verify_file(ws / row["warc_path"])
    assert result["problems"] == []
    assert [r["type"] for r in result["records"]] == [
        "warcinfo", "response"]
    assert validate_workspace(ws) == []

    # 篡改归档实体 → validate 点名 WARC 摘要不符
    target = ws / row["warc_path"]
    raw = bytearray(target.read_bytes())
    pos = bytes(raw).find(b"archived body bytes")
    raw[pos] ^= 0xFF
    target.write_bytes(bytes(raw))
    problems = validate_workspace(ws)
    assert any("Digest" in p for p in problems)


def test_warc_full_import_resource_record(ws, site, tmp_path):
    _, base = site
    tid, _ = _ready(ws, base, retention_tier="warc_full")
    f = tmp_path / "dataset.csv"
    f.write_bytes(b"a,b,c\n1,2,3\n")
    prov = fetch_mod.import_file(ws, tid, str(f), "机构导出", "测试员")
    assert prov["retention_tier"] == "warc_full"
    assert prov["warc_path"] == "warc/imports.warc"
    result = warc.verify_file(ws / prov["warc_path"])
    assert result["problems"] == []
    assert [r["type"] for r in result["records"]] == [
        "warcinfo", "resource"]
    assert validate_workspace(ws) == []


def test_lightweight_default_writes_no_warc(ws, site):
    _, base = site
    tid, rec = _ready(ws, base)
    assert rec["checks"]["retention"]["tier"] == \
        "lightweight_raw_plus_hash"
    fetch_mod.fetch_run(ws, tid, urls=[base + "/page.html"],
                        transport=_transport, sleep=NO_SLEEP)
    row = storage.read_provenance(ws)[-1]
    assert row["retention_tier"] == "lightweight_raw_plus_hash"
    assert "warc_path" not in row
    assert not list(Path(ws).rglob("*.warc"))
    assert validate_workspace(ws) == []


def test_cli_warc_verify(ws, site, capsys):
    from light_crawler import cli
    _, base = site
    tid, _ = _ready(ws, base, retention_tier="warc_full")
    fetch_mod.fetch_run(ws, tid, urls=[base + "/page.html"],
                        transport=_transport, sleep=NO_SLEEP)
    root = str(ws)
    assert cli.main(["--root", root, "warc", "verify"]) == 0
    out = capsys.readouterr().out
    assert "记录 2 条" in out and "问题 0" in out
    # 篡改后 CLI 退出码 2 并点名
    row = storage.read_provenance(ws)[-1]
    target = ws / row["warc_path"]
    raw = bytearray(target.read_bytes())
    pos = bytes(raw).find(b"archived body bytes")
    raw[pos] ^= 0xFF
    target.write_bytes(bytes(raw))
    assert cli.main(["--root", root, "warc", "verify"]) == 2


def test_crawl_warc_full(ws, site):
    from light_crawler import crawl as crawl_mod
    _, base = site
    tid, _ = _ready(ws, base, retention_tier="warc_full")
    summary = crawl_mod.crawl_run(
        ws, tid, transport=_transport, sleep=NO_SLEEP,
        discover_enabled=False)
    assert summary["stored"] >= 1
    prov = [r for r in storage.read_provenance(ws) if r["kind"] == "fetch"]
    assert prov and all(r["retention_tier"] == "warc_full" for r in prov)
    assert all(r.get("warc_path") for r in prov)
    result = warc.verify_file(ws / prov[0]["warc_path"])
    assert result["problems"] == []
    assert validate_workspace(ws) == []
