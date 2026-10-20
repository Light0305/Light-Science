"""robots 判定（RFC 9309 逐节口径）。"""

from light_crawler import robots


def _rules(body: bytes) -> robots.RobotsRules:
    return robots.parse_robots(body)


def test_longest_match_allow_wins():
    rules = _rules(b"User-agent: *\nDisallow: /data\nAllow: /data.json\n")
    allowed, matched = rules.is_allowed("/data.json")
    assert allowed and matched["kind"] == "allow"
    allowed, matched = rules.is_allowed("/data-other")
    assert not allowed and matched["kind"] == "disallow"


def test_tie_prefers_allow():
    rules = _rules(b"User-agent: *\nDisallow: /x\nAllow: /x\n")
    allowed, _ = rules.is_allowed("/x")
    assert allowed


def test_no_rule_means_allowed():
    rules = _rules(b"User-agent: *\nDisallow: /only-this\n")
    allowed, matched = rules.is_allowed("/anything-else")
    assert allowed and matched is None


def test_group_merge_specific_and_star():
    body = (b"User-agent: LightCrawler\nDisallow: /a\n\n"
            b"User-agent: *\nDisallow: /b\n")
    rules = _rules(body)
    assert not rules.is_allowed("/a")[0]
    assert not rules.is_allowed("/b")[0]


def test_other_agent_group_ignored():
    rules = _rules(b"User-agent: SomeOtherBot\nDisallow: /\n")
    assert rules.is_allowed("/")[0]


def test_crawl_delay_read_as_extension_fact():
    rules = _rules(b"User-agent: *\nCrawl-delay: 7\nAllow: /\n")
    assert rules.crawl_delay == 7.0


def test_broken_lines_skipped_not_fatal():
    rules = _rules(b"User-agent: *\nthis line has no colon\nDisallow: /x\n")
    assert not rules.is_allowed("/x")[0]
    assert rules.parse_warnings


def test_fetch_outcomes_against_fixture(site):
    srv, base = site
    f = robots.fetch_robots(base)
    assert f.outcome == "ok"
    srv.robots_status = 404
    srv.robots_text = None
    f = robots.fetch_robots(base)
    assert f.outcome == "unavailable"
    verdict = robots.check_url(f, base + "/data.json")
    assert verdict["allowed"] and verdict["basis"] == "RFC 9309 2.3.1.3"
    srv.robots_status = 500
    f = robots.fetch_robots(base)
    assert f.outcome == "unreachable"
    verdict = robots.check_url(f, base + "/data.json")
    assert not verdict["allowed"] and verdict["basis"] == "RFC 9309 2.3.1.4"


def test_fetch_unreachable_closed_port():
    f = robots.fetch_robots("http://127.0.0.1:1")
    assert f.outcome == "unreachable"
    verdict = robots.check_url(f, "http://127.0.0.1:1/data")
    assert not verdict["allowed"]


def test_disallow_verdict_names_rule(site):
    srv, base = site
    srv.robots_text = "User-agent: *\nDisallow: /private\n"
    f = robots.fetch_robots(base)
    verdict = robots.check_url(f, base + "/private/secret.json")
    assert not verdict["allowed"]
    assert verdict["matched_rule"]["pattern"] == "/private"
