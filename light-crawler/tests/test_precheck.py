"""预检分级与三件（S1/S4、HC-2/HC-3、项目锁、24h 过期）。"""

from conftest import make_reg

from light_crawler import precheck as pc
from light_crawler import project
from light_crawler.util import append_jsonl


def _register(ws, reg):
    project.register_target(ws, reg)
    return reg["target_id"]


def test_low_risk_auto_effective(ws, site):
    _, base = site
    tid = _register(ws, make_reg(base))
    rec = pc.run_precheck(ws, tid)
    assert rec["status"] == "effective" and rec["ready_to_fetch"]


def test_high_risk_needs_named_confirmation(ws, site):
    _, base = site
    tid = _register(ws, make_reg(base, channel="web_page"))
    rec = pc.run_precheck(ws, tid)
    assert rec["status"] == "pending_confirmation"
    assert pc.current_precheck(ws, tid)["status"] == "pending_confirmation"
    pc.confirm_precheck(ws, tid, confirmer="张三", note="条款已逐项核对")
    assert pc.current_precheck(ws, tid)["status"] == "effective"


def test_confirmation_must_be_named(ws, site):
    _, base = site
    tid = _register(ws, make_reg(base, channel="web_page"))
    pc.run_precheck(ws, tid)
    try:
        pc.confirm_precheck(ws, tid, confirmer="  ")
        raise AssertionError("匿名确认不应通过")
    except project.WorkspaceError as e:
        assert any("具名" in p for p in e.problems)


def test_missing_terms_is_incomplete_and_named(ws, site):
    _, base = site
    reg = make_reg(base)
    del reg["terms_basis"]
    tid = _register(ws, reg)
    rec = pc.run_precheck(ws, tid)
    assert rec["status"] == "incomplete"
    assert any("terms_basis" in m for m in rec["missing"])


def test_robots_disallow_blocks_with_rule_named(ws, site):
    srv, base = site
    srv.robots_text = "User-agent: *\nDisallow: /\n"
    tid = _register(ws, make_reg(base))
    rec = pc.run_precheck(ws, tid)
    assert rec["status"] == "blocked"
    assert any("robots" in r for r in rec["blocked_reasons"])
    events = project.read_events(ws)
    assert any(e["type"] == "precheck_blocked" for e in events)


def test_robots_500_fail_closed_blocks(ws, site):
    srv, base = site
    srv.robots_status = 500
    tid = _register(ws, make_reg(base))
    rec = pc.run_precheck(ws, tid)
    assert rec["status"] == "blocked"
    assert any("2.3.1.4" in r or "失败关闭" in r for r in rec["blocked_reasons"])


def test_robots_404_allows(ws, site):
    srv, base = site
    srv.robots_status = 404
    srv.robots_text = None
    tid = _register(ws, make_reg(base))
    rec = pc.run_precheck(ws, tid)
    assert rec["status"] == "effective"
    assert rec["checks"]["robots"]["outcome"] == "unavailable"


def test_crawl_delay_enters_rate_decision(ws, site):
    srv, base = site
    srv.robots_text = "User-agent: *\nCrawl-delay: 7\nAllow: /\n"
    tid = _register(ws, make_reg(base))  # official_api 模板下限 1s
    rec = pc.run_precheck(ws, tid)
    rate = rec["checks"]["rate"]
    assert rate["inputs"]["robots_crawl_delay"] == 7.0
    assert rate["effective_interval_sec"] == 7.0


def test_official_alternative_blocks_web_channel(ws, site):
    _, base = site
    reg = make_reg(base, channel="web_page", official_alternative={
        "available": True, "channel_ref": "official_api",
        "note": "该源有官方 API"})
    tid = _register(ws, reg)
    rec = pc.run_precheck(ws, tid)
    assert rec["status"] == "blocked"
    assert any("HC-3" in r for r in rec["blocked_reasons"])


def test_browser_default_off_then_needs_reason_and_confirmation(ws, site):
    _, base = site
    tid = _register(ws, make_reg(base, channel="browser"))
    rec = pc.run_precheck(ws, tid)
    assert rec["status"] == "blocked"  # S1 默认关
    reg = make_reg(base, channel="browser", browser_enabled=True,
                   browser_reason="公开检索页须 JS 渲染才见数据")
    project.register_target(ws, reg, update=True)
    rec = pc.run_precheck(ws, tid)
    assert rec["status"] == "pending_confirmation"  # 高危分级


def test_browser_project_lock_off_blocks(ws, site):
    _, base = site
    header = project.load_header(ws)
    header["lock"]["allow_browser"] = False
    project.save_header(ws, header)
    reg = make_reg(base, channel="browser", browser_enabled=True,
                   browser_reason="公开页须渲染")
    tid = _register(ws, reg)
    rec = pc.run_precheck(ws, tid)
    assert rec["status"] == "blocked"
    assert any("项目锁" in r for r in rec["blocked_reasons"])


def test_project_lock_raises_interval_and_logs(ws, site):
    _, base = site
    header = project.load_header(ws)
    header["lock"]["min_interval_sec"] = 30
    project.save_header(ws, header)
    tid = _register(ws, make_reg(base))
    rec = pc.run_precheck(ws, tid)
    assert rec["checks"]["rate"]["effective_interval_sec"] == 30
    assert rec["checks"]["rate"]["lock_raised"]
    assert any(e["type"] == "lock_applied" for e in project.read_events(ws))


def test_expired_precheck_not_effective(ws, site):
    _, base = site
    tid = _register(ws, make_reg(base))
    pc.run_precheck(ws, tid)
    stale = {
        "kind": "precheck", "precheck_id": "pc-stale01", "target_id": tid,
        "status": "effective", "ready_to_fetch": True, "channel": "official_api",
        "checks": {"rate": {"effective_interval_sec": 1.0}},
        "blocked_reasons": [], "missing": [],
        "robots_fetched_at": "2020-01-01T00:00:00+00:00",
        "expires_at": "2020-01-02T00:00:00+00:00",
        "run_config_hash": "x",
    }
    append_jsonl(ws / "prechecks" / f"{tid}.jsonl", stale)
    assert pc.current_precheck(ws, tid)["status"] == "expired"
