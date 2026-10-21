"""P2 检索执行通道：epub 经 light-crawler 驱动（假 runner 模拟
crawler 的文件账目效果）、OPS 适配器（假 transport + 自造
fixture XML）。全部离线；fixture 均为自造合成件，非真实抓取。"""

import json
from pathlib import Path

import pytest

from light_patent import channels, execsearch, novelty
from light_patent.project import PatentError, case_path
from light_patent.util import append_jsonl, dump_yaml, read_jsonl

from conftest import drive_to_mined

# 自造合成 fixture：仿 epub 公布模式结果页的著录标记形态。
EPUB_RESULT_HTML = """<html><body>
<div class="content_listx">
 <div class="item">
  <span>\u3010申请公布号\u3011CN118229001A</span>
  <span>\u3010发明名称\u3011一种禽类行为识别方法及系统</span>
  <span>\u3010申请人\u3011某农业大学</span>
  <span>\u3010公开（公告）日\u30112024-06-14</span>
  <span>\u3010国际分类号\u3011G06V 10/764</span>
 </div>
 <div class="item">
  <span>\u3010申请公布号\u3011CN117496328A</span>
  <span>\u3010发明名称\u3011基于视频分析的畜禽异常报警方法</span>
  <span>\u3010申请人\u3011某智能科技有限公司</span>
  <span>\u3010公开（公告）日\u30112024-02-02</span>
  <span>\u3010国际分类号\u3011G06V 20/52</span>
 </div>
</div></body></html>"""

OPS_FIXTURE_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<ops:world-patent-data xmlns:ops="http://ops.epo.org"
  xmlns:epo="http://www.epo.org/exchange/documents">
 <ops:biblio-search total-result-count="2">
  <ops:search-result>
   <ops:publication-reference>
    <epo:document-id document-id-type="docdb">
     <epo:country>EP</epo:country><epo:doc-number>4356789</epo:doc-number>
     <epo:kind>A1</epo:kind><epo:date>20240103</epo:date>
    </epo:document-id>
   </ops:publication-reference>
  </ops:search-result>
  <ops:search-result>
   <ops:publication-reference>
    <epo:document-id document-id-type="docdb">
     <epo:country>CN</epo:country><epo:doc-number>118229001</epo:doc-number>
     <epo:kind>A</epo:kind><epo:date>20240614</epo:date>
    </epo:document-id>
   </ops:publication-reference>
  </ops:search-result>
 </ops:biblio-search>
</ops:world-patent-data>"""


class FakeCrawlerRunner:
    """模拟 light-crawler CLI 的文件效果（不冒充真 crawler 跑通）。"""

    def __init__(self, *, precheck_status="effective",
                 fetch_html=EPUB_RESULT_HTML, fetch_status=200,
                 gate_ok=True):
        self.precheck_status = precheck_status
        self.fetch_html = fetch_html
        self.fetch_status = fetch_status
        self.gate_ok = gate_ok
        self.calls = []
        self.confirmed = False

    def __call__(self, argv, crawler_home):
        self.calls.append(list(argv))
        ws = Path(argv[argv.index("--root") + 1])
        cmd = argv[2]
        if cmd == "init":
            ws.mkdir(parents=True, exist_ok=True)
            (ws / "crawler.yaml").write_text("kind: workspace\n",
                                             encoding="utf-8")
            return {"returncode": 0, "stdout": "ok", "stderr": ""}
        if cmd == "register":
            d = ws / "targets" / "cnipa-epub"
            d.mkdir(parents=True, exist_ok=True)
            (d / "target.yaml").write_text("target_id: cnipa-epub\n",
                                           encoding="utf-8")
            return {"returncode": 0, "stdout": "ok", "stderr": ""}
        if cmd == "precheck":
            append_jsonl(ws / "prechecks" / "cnipa-epub.jsonl", [{
                "kind": "precheck", "precheck_id": "pc-test0001",
                "status": self.precheck_status}])
            return {"returncode": 0, "stdout": "ok", "stderr": ""}
        if cmd == "confirm":
            self.confirmed = True
            append_jsonl(ws / "prechecks" / "cnipa-epub.jsonl", [{
                "kind": "confirmation", "precheck_id": "pc-test0001"}])
            return {"returncode": 0, "stdout": "ok", "stderr": ""}
        if cmd == "gate-check":
            ok = self.gate_ok and (
                self.precheck_status == "effective" or self.confirmed)
            return {"returncode": 0 if ok else 2,
                    "stdout": json.dumps({"ready": ok}), "stderr": ""}
        if cmd == "fetch":
            url = argv[argv.index("--url") + 1]
            raw_rel = "store/ab/abcafe"
            dest = ws / raw_rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(self.fetch_html.encode("utf-8"))
            append_jsonl(ws / "provenance.jsonl", [{
                "kind": "fetch", "url": url, "prov_id": "pv-test1",
                "precheck_ref": "pc-test0001",
                "http_status": self.fetch_status, "raw_path": raw_rel}])
            return {"returncode": 0, "stdout": "ok", "stderr": ""}
        raise AssertionError(f"未模拟的 crawler 子命令 {cmd}")


def _enable_epub(case_root):
    channels.enable_channel(case_root, "cnipa-epub-automation", {
        "enabled_by": "测试", "crawler_precheck_ref": "pc-test0001"})


def _payload(**kw):
    base = {"round": "means_phrases", "ipc_codes": ["G06V"],
            "means_phrases": ["家禽行为检测"]}
    base.update(kw)
    return base


def test_epub_exec_requires_channel_enabled(case_root):
    drive_to_mined(case_root)
    with pytest.raises(PatentError):
        execsearch.execute_search(case_root, _payload(),
                                  cli_runner=FakeCrawlerRunner())


def test_epub_exec_full_flow(case_root):
    drive_to_mined(case_root)
    _enable_epub(case_root)
    runner = FakeCrawlerRunner(precheck_status="pending_confirmation")
    result = execsearch.execute_search(
        case_root, _payload(confirmer="测试确认人"), cli_runner=runner)
    assert result["outcome"] == "ok"
    assert result["hits"] == 2
    assert "G06V10" in result["suggested_round2_ipc"]
    assert runner.confirmed is True
    summary = novelty.search_summary(case_root)
    assert summary["pool_size"] == 2
    pool = read_jsonl(case_path(case_root, "search_log"))
    row = pool[-1]
    assert row["channel_id"] == "cnipa-epub-automation"
    assert row["outcome"] == "ok"
    from light_patent.project import load_yaml_or
    entries = load_yaml_or(case_root, "pool", {})["entries"]
    assert all(e["verified"] is False for e in entries)
    assert {e["pub_number"] for e in entries} == {
        "CN118229001A", "CN117496328A"}
    trace = Path(case_root) / result["trace"]
    assert trace.exists()


def test_epub_exec_awaiting_confirmation(case_root):
    drive_to_mined(case_root)
    _enable_epub(case_root)
    runner = FakeCrawlerRunner(precheck_status="pending_confirmation")
    result = execsearch.execute_search(case_root, _payload(),
                                       cli_runner=runner)
    assert result["outcome"] == "awaiting_confirmation"
    assert not any(c[2] == "fetch" for c in runner.calls)
    # 未发起检索 → 不许在检索日志里留行（更不许记 zero_results）
    assert read_jsonl(case_path(case_root, "search_log")) == []


def test_epub_exec_non_result_page_is_channel_failure(case_root):
    drive_to_mined(case_root)
    _enable_epub(case_root)
    runner = FakeCrawlerRunner(
        fetch_html="<html><body><div id='app'></div></body></html>")
    result = execsearch.execute_search(case_root, _payload(),
                                       cli_runner=runner)
    assert result["outcome"] == "channel_failure"
    rows = read_jsonl(case_path(case_root, "search_log"))
    assert rows[-1]["outcome"] == "channel_failure"
    assert "zero" not in rows[-1]["outcome"]


def test_epub_exec_gate_blocked_is_channel_failure(case_root):
    drive_to_mined(case_root)
    _enable_epub(case_root)
    runner = FakeCrawlerRunner(gate_ok=False)
    result = execsearch.execute_search(case_root, _payload(),
                                       cli_runner=runner)
    assert result["outcome"] == "channel_failure"
    assert not any(c[2] == "fetch" for c in runner.calls)


def test_parse_epub_results_dedupes():
    parsed = execsearch.parse_epub_results(EPUB_RESULT_HTML)
    assert parsed["is_result_page"] is True
    assert len(parsed["entries"]) == 2
    assert parsed["entries"][0]["ipc"] == "G06V10/764"
    assert execsearch.parse_epub_results("<html>壳</html>")[
        "is_result_page"] is False


# ---------------------------------------------------------------- OPS

def _enable_ops(case_root):
    channels.enable_channel(case_root, "epo-ops-api", {
        "enabled_by": "测试", "disclosure_acknowledged": True})


class FakeOpsTransport:
    def __init__(self, search_status=200, search_body=OPS_FIXTURE_XML):
        self.search_status = search_status
        self.search_body = search_body
        self.calls = []

    def __call__(self, method, url, *, headers=None, data=None, timeout=60):
        self.calls.append((method, url))
        if "accesstoken" in url:
            return {"status": 200,
                    "body": json.dumps(
                        {"access_token": "fixture-token"}).encode()}
        return {"status": self.search_status, "body": self.search_body}


CREDS = {"EPO_OPS_CONSUMER_KEY": "fixture-key",
         "EPO_OPS_CONSUMER_SECRET": "fixture-secret"}


def test_ops_credential_gap(case_root):
    drive_to_mined(case_root)
    _enable_ops(case_root)
    result = execsearch.execute_search(
        case_root, {"channel_id": "epo-ops-api", **_payload()},
        ops_transport=FakeOpsTransport(), environ={})
    assert result["outcome"] == "credential_gap"
    assert read_jsonl(case_path(case_root, "search_log")) == []


def test_ops_fixture_flow(case_root):
    drive_to_mined(case_root)
    _enable_ops(case_root)
    transport = FakeOpsTransport()
    result = execsearch.execute_search(
        case_root, {"channel_id": "epo-ops-api", **_payload()},
        ops_transport=transport, environ=CREDS)
    assert result["outcome"] == "ok" and result["hits"] == 2
    from light_patent.project import load_yaml_or
    entries = load_yaml_or(case_root, "pool", {})["entries"]
    by_pub = {e["pub_number"]: e for e in entries}
    assert by_pub["EP4356789A1"]["pub_date"] == "2024-01-03"
    # search 端点不回题名：留空不编造（LP-01）
    assert by_pub["EP4356789A1"]["title"] == ""
    assert len(transport.calls) == 2  # token + 一条 search，无分页


def test_ops_429_stops_without_retry(case_root):
    drive_to_mined(case_root)
    _enable_ops(case_root)
    transport = FakeOpsTransport(search_status=429, search_body=b"")
    result = execsearch.execute_search(
        case_root, {"channel_id": "epo-ops-api", **_payload()},
        ops_transport=transport, environ=CREDS)
    assert result["outcome"] == "channel_failure"
    assert len(transport.calls) == 2  # 没有第三次调用（不重试）


def test_ops_requires_enable(case_root):
    drive_to_mined(case_root)
    with pytest.raises(PatentError):
        execsearch.execute_search(
            case_root, {"channel_id": "epo-ops-api", **_payload()},
            ops_transport=FakeOpsTransport(), environ=CREDS)


def test_execute_rejects_manual_channel(case_root):
    drive_to_mined(case_root)
    with pytest.raises(PatentError):
        execsearch.execute_search(
            case_root, {"channel_id": "cnipa-pss-manual", **_payload()},
            cli_runner=FakeCrawlerRunner())
