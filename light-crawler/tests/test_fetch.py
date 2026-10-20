"""guard、获取全链、被拒熔断、导入与 gate 接口（HC-1/6/7/8、S2）。"""

import pytest
from conftest import make_reg

from light_crawler import fetch as fetch_mod
from light_crawler import precheck as pc
from light_crawler import project, storage
from light_crawler.validate import validate_workspace

NO_SLEEP = lambda s: None  # noqa: E731 - 测试注入：节流不真睡


def _ready(ws, base, channel="official_api", **kw):
    reg = make_reg(base, channel=channel, **kw)
    project.register_target(ws, reg)
    rec = pc.run_precheck(ws, reg["target_id"])
    if rec["status"] == "pending_confirmation":
        pc.confirm_precheck(ws, reg["target_id"], confirmer="测试员")
    return reg["target_id"]


def test_fetch_without_precheck_refused_and_named(ws, site):
    _, base = site
    project.register_target(ws, make_reg(base))
    with pytest.raises(fetch_mod.Refusal) as ei:
        fetch_mod.fetch_run(ws, "t1", sleep=NO_SLEEP)
    assert any("precheck" in r for r in ei.value.reasons)
    events = project.read_events(ws)
    assert any(e["type"] == "fetch_refused" for e in events)


def test_fetch_unregistered_target_refused(ws):
    verdict = fetch_mod.gate_check(ws, "ghost")
    assert verdict["status"] == "unregistered" and not verdict["ready"]


def test_happy_path_stores_raw_and_provenance(ws, site):
    _, base = site
    tid = _ready(ws, base)
    rec = fetch_mod.fetch_run(
        ws, tid, urls=[base + "/data.json", base + "/page.html"],
        sleep=NO_SLEEP)
    assert rec["status"] == "finished" and rec["stored"] == 2
    prov = [r for r in storage.read_provenance(ws) if r["kind"] == "fetch"]
    assert len(prov) == 2
    for row in prov:
        assert row["retention_tier"] == "lightweight_raw_plus_hash"
        assert row["precheck_ref"] and row["run_config_hash"]
        raw = (ws / row["raw_path"]).read_bytes()
        assert storage.sha256_bytes(raw) == row["sha256"]
        assert row["supersedes"] is None
    assert validate_workspace(ws) == []


def test_cleaned_output_for_html(ws, site):
    _, base = site
    tid = _ready(ws, base)
    fetch_mod.fetch_run(ws, tid, urls=[base + "/page.html"], sleep=NO_SLEEP)
    prov = storage.read_provenance(ws)[-1]
    assert prov["cleaned_path"]
    import json
    cleaned = json.loads((ws / prov["cleaned_path"]).read_text("utf-8"))
    assert cleaned["title"] == "Demo Page"
    assert "Some public data text" in cleaned["text"]
    assert "var x" not in cleaned["text"]


def test_duplicate_skipped_then_conditional_304(ws, site):
    _, base = site
    tid = _ready(ws, base)
    url = base + "/data.json"
    fetch_mod.fetch_run(ws, tid, urls=[url], sleep=NO_SLEEP)
    rec2 = fetch_mod.fetch_run(ws, tid, urls=[url], sleep=NO_SLEEP)
    assert rec2["duplicates"] == 1 and rec2["stored"] == 0
    rec3 = fetch_mod.fetch_run(ws, tid, urls=[url], sleep=NO_SLEEP,
                               refetch_seen=True)
    assert rec3["not_modified"] == 1 and rec3["stored"] == 0
    prov = [r for r in storage.read_provenance(ws) if r["kind"] == "fetch"]
    assert len(prov) == 1  # 304 不落新版


def test_version_chain_supersedes(ws, site):
    srv, base = site
    tid = _ready(ws, base)
    url = base + "/data.json"
    fetch_mod.fetch_run(ws, tid, urls=[url], sleep=NO_SLEEP)
    first = storage.read_provenance(ws)[-1]
    # 站点内容变更（ETag 随之变化）后重取：新行 supersedes 指向旧行
    srv.data_body = b'{"items": [9], "kind": "demo-v2"}'
    rec = fetch_mod.fetch_run(ws, tid, urls=[url], sleep=NO_SLEEP,
                              refetch_seen=True)
    assert rec["stored"] == 1
    second = storage.read_provenance(ws)[-1]
    assert second["supersedes"] == first["prov_id"]
    assert second["sha256"] != first["sha256"]


def test_http_refusal_stops_run_and_counts(ws, site):
    _, base = site
    tid = _ready(ws, base)
    rec = fetch_mod.fetch_run(
        ws, tid, urls=[base + "/forbidden", base + "/data.json"],
        sleep=NO_SLEEP)
    assert rec["refused"] and rec["stored"] == 0  # 被拒即停，后一 URL 不再请求
    events = project.read_events(ws)
    http_refusals = [e for e in events if e["type"] == "http_refused"]
    assert http_refusals and "403" in http_refusals[-1]["detail"]
    assert project.load_state(ws, tid)["consecutive_refusals"] == 1


def test_circuit_breaks_after_two_refused_runs_and_unblock_needs_name(ws, site):
    _, base = site
    tid = _ready(ws, base)
    for _ in range(2):
        fetch_mod.fetch_run(ws, tid, urls=[base + "/forbidden"], sleep=NO_SLEEP)
    state = project.load_state(ws, tid)
    assert state["circuit_broken"]
    verdict = fetch_mod.gate_check(ws, tid)
    assert verdict["status"] == "circuit_broken" and not verdict["ready"]
    with pytest.raises(fetch_mod.Refusal):
        fetch_mod.fetch_run(ws, tid, urls=[base + "/data.json"], sleep=NO_SLEEP)
    with pytest.raises(fetch_mod.Refusal):
        fetch_mod.unblock_target(ws, tid, by="", reason="试试")
    fetch_mod.unblock_target(ws, tid, by="张三", reason="目标站已恢复且条款复核")
    assert fetch_mod.gate_check(ws, tid)["ready"]
    rec = fetch_mod.fetch_run(ws, tid, urls=[base + "/data.json"], sleep=NO_SLEEP)
    assert rec["stored"] == 1
    assert any(e["type"] == "target_unblocked"
               for e in project.read_events(ws))


def test_429_records_retry_after(ws, site):
    _, base = site
    tid = _ready(ws, base)
    rec = fetch_mod.fetch_run(ws, tid, urls=[base + "/limited"], sleep=NO_SLEEP)
    assert rec["refused"]
    e = [x for x in project.read_events(ws) if x["type"] == "http_refused"][-1]
    assert e["data"]["retry_after_sec"] == 30


def test_redirect_out_of_scope_not_stored(ws, site, outside):
    srv, base = site
    srv.outside_url = outside
    tid = _ready(ws, base)
    rec = fetch_mod.fetch_run(ws, tid, urls=[base + "/redir-out"], sleep=NO_SLEEP)
    assert rec["stored"] == 0
    assert any(e["type"] == "redirect_out_of_scope"
               for e in project.read_events(ws))


def test_redirect_in_scope_followed(ws, site):
    _, base = site
    tid = _ready(ws, base)
    rec = fetch_mod.fetch_run(ws, tid, urls=[base + "/redir-in"], sleep=NO_SLEEP)
    assert rec["stored"] == 1


def test_fetch_time_robots_recheck_refuses_disallowed_path(ws, site):
    srv, base = site
    srv.robots_text = "User-agent: *\nAllow: /\nDisallow: /private\n"
    tid = _ready(ws, base)  # 预检只查 base（/），通过
    rec = fetch_mod.fetch_run(
        ws, tid, urls=[base + "/private/secret.json"], sleep=NO_SLEEP)
    assert rec["stored"] == 0
    assert any("robots" in e for e in rec["errors"])


def test_volume_cap_stops_run(ws, site):
    _, base = site
    tid = _ready(ws, base, rate={"max_requests_per_run": 1})
    rec = fetch_mod.fetch_run(
        ws, tid, urls=[base + "/data.json", base + "/page.html"], sleep=NO_SLEEP)
    assert rec["requested"] == 1
    assert any(e["type"] == "volume_cap_hit" for e in project.read_events(ws))


def test_url_outside_registered_host_refused(ws, site, outside):
    _, base = site
    tid = _ready(ws, base)
    rec = fetch_mod.fetch_run(ws, tid, urls=[outside], sleep=NO_SLEEP)
    assert rec["stored"] == 0 and rec["errors"]


def test_browser_channel_without_executor_refused_honestly(ws, site):
    _, base = site
    tid = _ready(ws, base, channel="browser", browser_enabled=True,
                 browser_reason="公开页须 JS 渲染")
    with pytest.raises(fetch_mod.Refusal) as ei:
        fetch_mod.fetch_run(ws, tid, sleep=NO_SLEEP)
    assert any("执行器不随包提供" in r for r in ei.value.reasons)


def test_browser_channel_with_injected_fetcher_runs(ws, site):
    _, base = site
    tid = _ready(ws, base, channel="browser", browser_enabled=True,
                 browser_reason="公开页须 JS 渲染")

    def fake_browser(url, headers):
        return fetch_mod.Response(200, {"Content-Type": "text/html"},
                                  b"<html><body>rendered</body></html>", url)

    rec = fetch_mod.fetch_run(ws, tid, urls=[base + "/page.html"],
                              sleep=NO_SLEEP, browser_fetcher=fake_browser)
    assert rec["stored"] == 1


def test_manual_import_channel(ws, site, tmp_path):
    _, base = site
    project.register_target(ws, make_reg(base))
    src = tmp_path / "export.csv"
    src.write_bytes(b"a,b\n1,2\n")
    with pytest.raises(fetch_mod.Refusal):
        fetch_mod.import_file(ws, "t1", src, note="", by="张三")
    with pytest.raises(fetch_mod.Refusal):
        fetch_mod.import_file(ws, "t1", src, note="后台导出", by="")
    prov = fetch_mod.import_file(ws, "t1", src, note="用户从平台后台导出", by="张三")
    assert prov["kind"] == "manual_import"
    assert prov["channel"] == "manual_import"
    assert (ws / prov["raw_path"]).read_bytes() == b"a,b\n1,2\n"
    assert validate_workspace(ws) == []


def test_validate_names_tampered_raw(ws, site):
    _, base = site
    tid = _ready(ws, base)
    fetch_mod.fetch_run(ws, tid, urls=[base + "/data.json"], sleep=NO_SLEEP)
    prov = storage.read_provenance(ws)[-1]
    raw = ws / prov["raw_path"]
    raw.write_bytes(b"tampered")
    problems = validate_workspace(ws)
    assert any("哈希不符" in p for p in problems)


def test_gate_check_reports_rate_and_precheck_id(ws, site):
    _, base = site
    tid = _ready(ws, base)
    verdict = fetch_mod.gate_check(ws, tid)
    assert verdict["ready"] and verdict["precheck_id"]
    assert verdict["effective_interval_sec"] == 1.0
