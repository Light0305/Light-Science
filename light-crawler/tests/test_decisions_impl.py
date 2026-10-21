"""决策落地批验收（D1–D10 用户 2026-10-21 全按推荐批准后施工）。

D1：浏览器预授权名单（名单内放行留痕 / 名单外照旧拦 / 变更留痕 /
项目锁整锁优先）；D8：robots 预检缓存复用（命中零额外请求 /
哈希变化失效 / 超 24h 失效）；D3：render_escalation_blocked 在
refusals 清单里可按类计数查询。其余各条维持现状不在此验。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from conftest import make_reg

import fixture_sites as fx
from light_crawler import cli, crawl as crawl_mod
from light_crawler import fetch as fetch_mod
from light_crawler import precheck as precheck_mod
from light_crawler import project, robots, schema
from light_crawler.util import sha256_bytes

NO_SLEEP = lambda s: None


@pytest.fixture()
def fsite():
    srv = fx.make_fixture_server()
    yield srv, fx.base_of(srv)
    srv.shutdown()


@pytest.fixture()
def robots_counter(monkeypatch):
    """计数 robots.fetch_robots 的真实调用次数（网络取用证据）。"""
    calls = {"n": 0}
    orig = robots.fetch_robots

    def counting(url, timeout=10.0):
        calls["n"] += 1
        return orig(url, timeout=timeout)

    monkeypatch.setattr(robots, "fetch_robots", counting)
    return calls


def _events(ws, type_=None):
    rows = project.read_events(ws)
    return [e for e in rows if type_ is None or e["type"] == type_]


def _register(ws, base, tid="b1", **kw):
    reg = make_reg(base, target_id=tid, channel="browser", **kw)
    project.register_target(ws, reg)
    return tid


# ---------------------------------------------------------------- D1 名单内

def test_d1_listed_browser_target_effective_without_confirm(ws, site):
    _, base = site
    tid = _register(ws, base)  # 无 browser_enabled / browser_reason
    rec = precheck_mod.run_precheck(ws, tid)
    assert rec["status"] == "blocked"  # 名单外现状：默认关拦下
    project.add_browser_preauthorization(
        ws, tid, by="alice", reason="项目 JS 站群统一授权")
    rec = precheck_mod.run_precheck(ws, tid)
    assert rec["status"] == "effective" and rec["ready_to_fetch"] is True
    waiver = rec["confirmation_waiver"]
    assert waiver["waived_via"] == "browser_preauthorized_list"
    assert waiver["listed_by"] == "alice"
    chan = rec["checks"]["channel"]
    assert chan["browser_preauthorized"]["listed_by"] == "alice"
    # guard 口径一致：gate 直接 ready，无须 confirm
    verdict = fetch_mod.gate_check(ws, tid)
    assert verdict["ready"] is True
    # 留痕三件齐：列入、命中生效各一条
    assert _events(ws, "browser_preauthorization_added")
    assert _events(ws, "browser_preauthorization_applied")


def test_d1_unlisted_browser_target_keeps_s1_flow(ws, site):
    _, base = site
    tid = _register(ws, base, browser_enabled=True,
                    browser_reason="单目标开启")
    rec = precheck_mod.run_precheck(ws, tid)
    assert rec["status"] == "pending_confirmation"  # 名单外照旧待确认
    assert rec["confirmation_waiver"] is None
    precheck_mod.confirm_precheck(ws, tid, "bob", "逐个确认")
    assert precheck_mod.current_precheck(ws, tid)["status"] == "effective"


def test_d1_removal_restores_block_and_changes_traced(ws, site):
    _, base = site
    tid = _register(ws, base)
    project.add_browser_preauthorization(ws, tid, by="alice", reason="临时授权")
    assert precheck_mod.run_precheck(ws, tid)["status"] == "effective"
    project.remove_browser_preauthorization(
        ws, tid, by="alice", reason="授权到期")
    assert _events(ws, "browser_preauthorization_removed")
    rec = precheck_mod.run_precheck(ws, tid)
    assert rec["status"] == "blocked"  # 移出后回到默认关
    with pytest.raises(project.WorkspaceError):
        project.remove_browser_preauthorization(
            ws, tid, by="alice", reason="重复移出")
    with pytest.raises(project.WorkspaceError):
        project.add_browser_preauthorization(
            ws, "ghost-target", by="alice", reason="未登记目标")
    project.add_browser_preauthorization(ws, tid, by="alice", reason="再授权")
    with pytest.raises(project.WorkspaceError):
        project.add_browser_preauthorization(
            ws, tid, by="alice", reason="重复列入")
    with pytest.raises(project.WorkspaceError):
        project.add_browser_preauthorization(ws, tid, by=" ", reason="无名")
    # header 落盘形态：名单就是 lock 段的具名条目
    entries = project.list_browser_preauthorizations(ws)
    assert entries and entries[-1]["target_id"] == tid


def test_d1_project_lock_allow_browser_false_overrides_list(ws, site):
    _, base = site
    tid = _register(ws, base)
    project.add_browser_preauthorization(ws, tid, by="alice", reason="已授权")
    header = project.load_header(ws)
    header["lock"]["allow_browser"] = False
    project.save_header(ws, header)
    rec = precheck_mod.run_precheck(ws, tid)
    assert rec["status"] == "blocked"  # 项目锁只紧不松，名单不越锁
    assert any("allow_browser" in r for r in rec["blocked_reasons"])


def test_d1_cli_browser_preauth_roundtrip(ws, site, capsys):
    _, base = site
    tid = _register(ws, base)
    root = str(ws)
    assert cli.main(["--root", root, "browser-preauth", "add",
                     "--target", tid, "--by", "alice",
                     "--reason", "CLI 授权"]) == 0
    assert cli.main(["--root", root, "browser-preauth", "list"]) == 0
    out = capsys.readouterr().out
    assert tid in out and "共 1 条预授权" in out
    rec = precheck_mod.run_precheck(ws, tid)
    assert rec["status"] == "effective"
    assert cli.main(["--root", root, "browser-preauth", "remove",
                     "--target", tid, "--by", "alice",
                     "--reason", "CLI 撤销"]) == 0
    assert project.list_browser_preauthorizations(ws) == []


# ---------------------------------------------------------------- D8 缓存

def _ready_official(ws, base, tid="t1"):
    reg = make_reg(base, target_id=tid, channel="official_api")
    project.register_target(ws, reg)
    rec = precheck_mod.run_precheck(ws, tid)
    assert rec["status"] == "effective"
    return tid


def test_d8_fetch_reuses_cache_zero_extra_robots_requests(
        ws, site, robots_counter):
    _, base = site
    tid = _ready_official(ws, base)
    robots_counter["n"] = 0  # 预检那次不计，只数 fetch 期
    rec = fetch_mod.fetch_run(ws, tid, urls=[base + "/data.json"],
                              sleep=NO_SLEEP)
    assert rec["stored"] == 1
    assert robots_counter["n"] == 0  # 命中复用：零额外 robots 请求
    reused = _events(ws, "robots_cache_reused")
    assert reused and reused[-1]["data"]["precheck_id"]


def test_d8_hash_mismatch_invalidates_and_refetches(
        ws, site, robots_counter):
    _, base = site
    tid = _ready_official(ws, base)
    record = precheck_mod.current_precheck(ws, tid)["record"]
    rel = record["checks"]["robots"]["body_cache_path"]
    from pathlib import Path
    dest = Path(ws) / rel
    dest.write_bytes(b"User-agent: *\nDisallow: /\n")  # 篡改缓存本体
    robots_counter["n"] = 0
    rec = fetch_mod.fetch_run(ws, tid, urls=[base + "/data.json"],
                              sleep=NO_SLEEP)
    assert robots_counter["n"] == 1  # 作废后回落实时取
    assert rec["stored"] == 1  # 实时 robots 仍是放行版
    bad = _events(ws, "robots_cache_invalidated")
    assert bad and bad[-1]["data"]["reason"] == "hash_mismatch"


def test_d8_expired_cache_returns_fresh(ws, site, robots_counter):
    _, base = site
    body = b"User-agent: *\nAllow: /\n"
    rel = robots.store_cached_body(
        ws, robots.RobotsFetch("ok", status=200, body=body))
    assert rel
    past = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat(
        timespec="seconds")
    record = {"precheck_id": "pc-old", "robots_fetched_at": past,
              "checks": {"robots": {
                  "outcome": "ok", "http_status": 200,
                  "body_sha256": sha256_bytes(body), "fetched_at": past}}}
    robots_counter["n"] = 0
    fetched, info = robots.resolve_robots(ws, base, record=record)
    assert info["source"] == "fresh" and robots_counter["n"] == 1
    assert fetched.outcome == "ok"


def test_d8_unavailable_outcome_reused_without_network(ws, monkeypatch):
    def boom(url, timeout=10.0):
        raise AssertionError("不应发生网络取用")

    monkeypatch.setattr(robots, "fetch_robots", boom)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    record = {"precheck_id": "pc-404", "robots_fetched_at": now,
              "checks": {"robots": {
                  "outcome": "unavailable", "http_status": 404,
                  "body_sha256": None, "fetched_at": now}}}
    fetched, info = robots.resolve_robots(
        ws, "http://example.invalid", record=record)
    assert info["source"] == "precheck_cache"
    assert fetched.outcome == "unavailable"
    assert robots.check_url(fetched, "http://example.invalid/x")["allowed"]


def test_d8_crawl_reuses_cache_too(ws, site, robots_counter):
    _, base = site
    tid = _ready_official(ws, base)
    robots_counter["n"] = 0
    summary = crawl_mod.crawl_run(ws, tid, seeds=[base + "/data.json"],
                                  sleep=NO_SLEEP, max_pages=5)
    assert summary["stored"] >= 1
    assert robots_counter["n"] == 0
    assert _events(ws, "robots_cache_reused")


# ---------------------------------------------------------------- D3 计数

def test_d3_render_escalation_blocked_countable_in_refusals(
        ws, fsite, capsys):
    _, base = fsite
    reg = make_reg(base, target_id="t1", channel="web_page")
    project.register_target(ws, reg)
    rec = precheck_mod.run_precheck(ws, "t1")
    assert rec["status"] == "pending_confirmation"
    precheck_mod.confirm_precheck(ws, "t1", "tester", "夹具验收")
    s = crawl_mod.crawl_run(ws, "t1", seeds=[base + "/spa"],
                            sleep=NO_SLEEP)
    assert s["stored"] == 1  # 维持逐目标确认：未授权只存壳并落 blocked
    blocked = [e for e in project.read_events(ws)
               if e["type"] == "render_escalation_blocked"]
    assert blocked
    assert "render_escalation_blocked" in schema.REFUSAL_EVENT_TYPES
    rows = [e for e in project.read_events(ws)
            if e["type"] in schema.REFUSAL_EVENT_TYPES
            and e["type"] == "render_escalation_blocked"]
    assert len(rows) == len(blocked)  # refusals 过滤口径可计数
    rc = cli.main(["--root", str(ws), "refusals",
                   "--type", "render_escalation_blocked"])
    assert rc == 0
    out = capsys.readouterr().out
    assert f"共 {len(blocked)} 条拒绝留痕（类型 render_escalation_blocked）" \
        in out
    assert cli.main(["--root", str(ws), "refusals",
                     "--type", "not_a_refusal"]) == 2
