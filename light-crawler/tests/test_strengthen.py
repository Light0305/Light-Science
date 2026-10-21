"""能力强化批验收：撞墙场景夹具对照（强化后行为）。

夹具在 fixture_sites.py；强化前的撞墙证据由探针实测（见
20-build/crawler-strengthen.md 的审计表）：SPA 清洗为空、GBK
花屏、gzip 无内容、分页只得 1 页、重定向环被当成功内容落盘、
浏览器通道无执行器、自适应限速不存在、大文件零 Range。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from conftest import make_reg

import fixture_sites as fx
from light_crawler import crawl as crawl_mod
from light_crawler import discover as discover_mod
from light_crawler import fetch as fetch_mod
from light_crawler import precheck as precheck_mod
from light_crawler import project, schema, storage
from light_crawler import transport as transport_mod

NO_SLEEP = lambda s: None


@pytest.fixture()
def fsite():
    srv = fx.make_fixture_server()
    yield srv, fx.base_of(srv)
    srv.shutdown()


def _ready(ws, base, tid="t1", channel="web_page", **kw):
    reg = make_reg(base, target_id=tid, channel=channel, **kw)
    project.register_target(ws, reg)
    rec = precheck_mod.run_precheck(ws, tid)
    if rec["status"] == "pending_confirmation":
        precheck_mod.confirm_precheck(ws, tid, "tester", "夹具验收")
    return tid


def _cleaned_texts(ws):
    out = []
    for f in sorted((Path(ws) / "runs").glob("*/cleaned/*.json")):
        out.append(json.loads(f.read_text(encoding="utf-8")))
    return out


def _events(ws, type_=None):
    rows = project.read_events(ws)
    return [e for e in rows if type_ is None or e["type"] == type_]


# ---------------------------------------------------------------- 传输层

def test_gzip_and_gbk_decode(ws, fsite):
    _, base = fsite
    tid = _ready(ws, base)
    fetch_mod.fetch_run(ws, tid, urls=[base + "/gzip-page"],
                        sleep=NO_SLEEP)
    fetch_mod.fetch_run(ws, tid, urls=[base + "/gbk"], sleep=NO_SLEEP)
    texts = [c["text"] for c in _cleaned_texts(ws)]
    assert any("GZIP-MARKER" in t for t in texts)
    assert any("火鸡行为数据集" in t and "GBK-MARKER" in t
               for t in texts)


def test_redirect_chain_recorded(ws, fsite):
    _, base = fsite
    tid = _ready(ws, base)
    fetch_mod.fetch_run(ws, tid, urls=[base + "/chain1"], sleep=NO_SLEEP)
    prov = [r for r in storage.read_provenance(ws)
            if r["url"] == base + "/chain1"]
    assert prov and prov[-1]["final_url"].endswith("/data.json")
    assert len(prov[-1]["redirect_chain"]) == 2


def test_redirect_loop_is_error_not_content(ws, fsite):
    _, base = fsite
    tid = _ready(ws, base)
    rec = fetch_mod.fetch_run(ws, tid, urls=[base + "/loop"],
                              sleep=NO_SLEEP)
    assert rec["stored"] == 0
    assert any("传输失败" in e for e in rec["errors"])
    assert _events(ws, "fetch_error")
    assert not [r for r in storage.read_provenance(ws)
                if r["url"] == base + "/loop"]


def test_transport_timeout_named(fsite):
    _, base = fsite
    with pytest.raises(transport_mod.TransportError) as ei:
        transport_mod.fetch(base + "/slow", timeout=0.3)
    assert ei.value.kind == "timeout"


def test_range_resume_download(fsite, tmp_path):
    srv, base = fsite
    part = tmp_path / "big.part"
    part.write_bytes(fx.BIG_BODY[:100_000])
    (tmp_path / "big.part.meta.json").write_text(json.dumps(
        {"url": base + "/big.bin"}), encoding="utf-8")
    info = transport_mod.download_resumable(base + "/big.bin", part)
    assert info["resumed_from"] == 100_000
    assert info["sha256"] == fx.BIG_SHA256
    assert info["bytes_total"] == len(fx.BIG_BODY)
    ranges = [r["range"] for r in srv.request_log
              if r["path"] == "/big.bin"]
    assert ranges and ranges[-1] == "bytes=100000-"


def test_large_files_fetch_run(ws, fsite):
    _, base = fsite
    tid = _ready(ws, base, large_files=True)
    fetch_mod.fetch_run(ws, tid, urls=[base + "/big.bin"],
                        sleep=NO_SLEEP)
    prov = [r for r in storage.read_provenance(ws)
            if r["url"] == base + "/big.bin"]
    assert prov and prov[-1]["bytes"] == len(fx.BIG_BODY)
    assert prov[-1]["sha256"] == fx.BIG_SHA256


def test_adaptive_throttle_never_below_base():
    from light_crawler.throttle import Throttler
    waits = []
    t = Throttler(5.0, sleep=waits.append, clock=lambda: 0.0)
    assert t.interval == 5.0
    t.note_outcome("server_error")
    first = t.interval
    assert first > 5.0
    t.note_outcome("network_error")
    assert t.interval > first
    for _ in range(30):
        t.note_outcome("ok")
    assert t.interval == 5.0  # 回落至基线为止，永不更低


# ---------------------------------------------------------------- JS 壳与渲染

def test_spa_static_fetch_flags_js_shell(ws, fsite):
    _, base = fsite
    tid = _ready(ws, base)
    fetch_mod.fetch_run(ws, tid, urls=[base + "/spa"], sleep=NO_SLEEP)
    assert _events(ws, "js_shell_detected")
    texts = [c["text"] for c in _cleaned_texts(ws)]
    assert all("RENDERED-MARKER-42" not in t for t in texts)


def test_browser_channel_renders_spa(ws, fsite):
    _, base = fsite
    tid = _ready(ws, base, channel="browser", browser_enabled=True,
                 browser_reason="SPA 须渲染")
    fetcher = fetch_mod.make_builtin_browser_fetcher()
    rec = fetch_mod.fetch_run(ws, tid, urls=[base + "/spa"],
                              sleep=NO_SLEEP, browser_fetcher=fetcher)
    assert rec["stored"] == 1
    texts = [c["text"] for c in _cleaned_texts(ws)]
    assert any("RENDERED-MARKER-42" in t for t in texts)
    prov = storage.read_provenance(ws)[-1]
    assert prov["render"]["engine"].startswith("cdp")


def test_browser_challenge_is_refusal_not_content(ws, fsite):
    _, base = fsite
    tid = _ready(ws, base, channel="browser", browser_enabled=True,
                 browser_reason="公开页须渲染")
    fetcher = fetch_mod.make_builtin_browser_fetcher()
    rec = fetch_mod.fetch_run(ws, tid, urls=[base + "/challenge"],
                              sleep=NO_SLEEP, browser_fetcher=fetcher)
    assert rec["refused"] is True and rec["stored"] == 0
    assert _events(ws, "render_blocked")
    assert _events(ws, "http_refused")


# ---------------------------------------------------------------- 发现与 crawl

def test_discover_pass_registers_api_endpoints(ws, fsite):
    _, base = fsite
    tid = _ready(ws, base + "/api-page")
    summary = crawl_mod.discover_pass(ws, tid, sleep=NO_SLEEP)
    rows = discover_mod.list_discovered(ws, tid)
    api = {r["url"] for r in rows if r["kind"] == "api_endpoint"}
    assert base + "/api/items" in api
    assert base + "/api/v2/search?q=turkey" in api
    assert any(u.startswith(base + "/api/detail") for u in api)
    assert base + "/api/config" in api
    assert any(r["kind"] == "embedded_data" for r in rows)
    assert summary["by_kind"].get("api_endpoint", 0) >= 4


def test_crawl_pagination_then_resume(ws, fsite):
    srv, base = fsite
    tid = _ready(ws, base)
    s1 = crawl_mod.crawl_run(ws, tid, seeds=[base + "/list?page=1"],
                             max_pages=3, sleep=NO_SLEEP)
    assert s1["status"] == "partial"
    assert fx.hits(srv, "/list") == 2
    s2 = crawl_mod.crawl_run(ws, tid, sleep=NO_SLEEP)
    assert s2["resumed"] is True
    assert s2["status"] == "finished"
    assert fx.hits(srv, "/list") == 3  # 已抓页不重抓
    prov = [r for r in storage.read_provenance(ws)
            if r.get("target_id") == tid]
    assert len(prov) == 3


def test_crawl_sitemap_strategy(ws, fsite):
    srv, base = fsite
    srv.sitemap_enabled = True
    srv.robots_text = ("User-agent: *\nAllow: /\n"
                       f"Sitemap: {base}/sitemap.xml\n")
    tid = _ready(ws, base)
    s = crawl_mod.crawl_run(ws, tid, sleep=NO_SLEEP, max_pages=6)
    assert s["strategy"] == "sitemap"
    urls = {r["url"] for r in storage.read_provenance(ws)}
    assert base + "/data.json" in urls
    assert base + "/list?page=1" in urls


def test_crawl_render_escalation_authorized(ws, fsite):
    _, base = fsite
    tid = _ready(ws, base, allow_render_escalation=True)
    s = crawl_mod.crawl_run(ws, tid, seeds=[base + "/spa"],
                            sleep=NO_SLEEP)
    assert s["stored"] == 1
    assert _events(ws, "strategy_escalated")
    texts = [c["text"] for c in _cleaned_texts(ws)]
    assert any("RENDERED-MARKER-42" in t for t in texts)
    prov = storage.read_provenance(ws)[-1]
    assert prov["via"]["rendered"] is True


def test_crawl_render_escalation_blocked_without_auth(ws, fsite):
    _, base = fsite
    tid = _ready(ws, base)
    s = crawl_mod.crawl_run(ws, tid, seeds=[base + "/spa"],
                            sleep=NO_SLEEP)
    assert s["stored"] == 1  # 壳照存，但标注在案
    assert _events(ws, "render_escalation_blocked")
    assert not _events(ws, "strategy_escalated")
    texts = [c["text"] for c in _cleaned_texts(ws)]
    assert all("RENDERED-MARKER-42" not in t for t in texts)


def test_crawl_403_stops_and_skips_rest(ws, fsite):
    srv, base = fsite
    tid = _ready(ws, base)
    s = crawl_mod.crawl_run(
        ws, tid, seeds=[base + "/walled", base + "/data.json"],
        sleep=NO_SLEEP)
    assert s["status"] == "refused"
    assert fx.hits(srv, "/data.json") == 0
    job = crawl_mod.load_job(ws, tid)
    assert job["items"][base + "/walled"]["status"] == "refused"


def test_crawl_unstable_backoff_then_fresh_recovers(ws, fsite):
    srv, base = fsite
    srv.unstable_failures = 1  # 首击 503、其后恢复
    tid = _ready(ws, base)
    s1 = crawl_mod.crawl_run(ws, tid, seeds=[base + "/unstable"],
                             sleep=NO_SLEEP)
    job = crawl_mod.load_job(ws, tid)
    assert job["items"][base + "/unstable"]["status"] == "failed"
    assert _events(ws, "adaptive_backoff")
    s2 = crawl_mod.crawl_run(ws, tid, seeds=[base + "/unstable"],
                             sleep=NO_SLEEP, fresh=True)
    assert s2["stored"] == 1  # 站点恢复后 fresh 任务抓到 200


# ---------------------------------------------------------------- 凭据访问通道

COOKIE_VALUE = "fixture-cookie-123"


def _cred_reg(base, **kw):
    reg = {
        "target_id": "cred1", "name": "凭据目标", "base_url": base,
        "project": "demo-project", "purpose_kind": "dataset_batch",
        "consumer": "light-experiment 数据入口", "channel": "browser",
        "browser_enabled": True, "browser_reason": "会员数据页须登录会话",
        "terms_basis": "机构订阅条款（fixture）",
        "login_state": "institutional",
        "entitlement_basis": "机构订阅（fixture 大学图书馆）",
        "credential_ref": "vault:fixture-main",
    }
    reg.update(kw)
    return reg


def _cred_ready(ws, base, **kw):
    project.register_target(ws, _cred_reg(base, **kw))
    rec = precheck_mod.run_precheck(ws, "cred1")
    if rec["status"] == "pending_confirmation":
        precheck_mod.confirm_precheck(ws, "cred1", "tester", "夹具验收")
    return "cred1"


def test_credential_registration_validation():
    base = "https://example.org"
    ok = schema.validate_target(_cred_reg(base))
    assert ok == []
    no_basis = schema.validate_target(_cred_reg(base, entitlement_basis=""))
    assert any("entitlement_basis" in p for p in no_basis)
    raw_ref = schema.validate_target(
        _cred_reg(base, credential_ref="my-password-123"))
    assert any("vault:" in p for p in raw_ref)
    wrong_channel = schema.validate_target(
        _cred_reg(base, channel="web_page"))
    assert any("浏览器通道承载" in p for p in wrong_channel)


def test_credential_requires_provider_injection(ws, fsite):
    _, base = fsite
    tid = _cred_ready(ws, base)
    fetcher = fetch_mod.make_builtin_browser_fetcher()
    with pytest.raises(fetch_mod.Refusal) as ei:
        fetch_mod.fetch_run(ws, tid, urls=[base + "/spa"],
                            sleep=NO_SLEEP, browser_fetcher=fetcher)
    assert any("credential_provider" in r for r in ei.value.reasons)


class _SessionFetcher:
    """带 set_session 的假执行器：断言会话到达且不外泄。"""

    def __init__(self, login_required=False):
        self.session = None
        self.login_required = login_required

    def set_session(self, session):
        self.session = session

    def __call__(self, url, headers):
        assert self.session is not None
        assert self.session["cookies"][0]["value"] == COOKIE_VALUE
        resp = fetch_mod.Response(
            401 if self.login_required else 200,
            {"Content-Type": "text/html"},
            b"<html><body>member area</body></html>", url)
        resp.render_info = {"engine": "fake",
                            "login_required": self.login_required}
        return resp


def _provider(ref):
    assert ref == "vault:fixture-main"
    return {"cookies": [{"name": "sess", "value": COOKIE_VALUE}],
            "account_label": "user***@example.org"}


def test_credential_session_flow_provenance_masked(ws, fsite):
    _, base = fsite
    tid = _cred_ready(ws, base)
    fetcher = _SessionFetcher()
    rec = fetch_mod.fetch_run(
        ws, tid, urls=[base + "/page.html"], sleep=NO_SLEEP,
        browser_fetcher=fetcher, credential_provider=_provider)
    assert rec["stored"] == 1
    prov = storage.read_provenance(ws)[-1]
    assert prov["entitlement"]["basis"].startswith("机构订阅")
    assert prov["entitlement"]["account_label"] == "user***@example.org"
    # 凭据值绝不落盘：全工作区文本扫描
    for path in Path(ws).rglob("*"):
        if path.is_file():
            assert COOKIE_VALUE not in path.read_text(
                encoding="utf-8", errors="ignore")


def test_credential_session_invalid_is_refusal(ws, fsite):
    _, base = fsite
    tid = _cred_ready(ws, base)
    fetcher = _SessionFetcher(login_required=True)
    rec = fetch_mod.fetch_run(
        ws, tid, urls=[base + "/page.html"], sleep=NO_SLEEP,
        browser_fetcher=fetcher, credential_provider=_provider)
    assert rec["refused"] is True and rec["stored"] == 0
    assert _events(ws, "credential_session_invalid")
    state = project.load_state(ws, tid)
    assert state["consecutive_refusals"] == 1


def test_credential_fetcher_without_session_surface_refused(ws, fsite):
    _, base = fsite
    tid = _cred_ready(ws, base)

    def plain_fetcher(url, headers):  # 无 set_session
        return fetch_mod.Response(200, {}, b"x", url)

    with pytest.raises(fetch_mod.Refusal):
        fetch_mod.fetch_run(
            ws, tid, urls=[base + "/page.html"], sleep=NO_SLEEP,
            browser_fetcher=plain_fetcher, credential_provider=_provider)
