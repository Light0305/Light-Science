"""uri 链接铸造：只铸导航链接、不冒充执行结果（T3）。

形态来源：obsidian:// 核心协议（open/search）与 Advanced URI
插件（Vinzent03，MIT）文档形态，DR-O §三.6 与 TOOLING-PLAN
§5.1 沿用——链接单向触发、无回执；本文件只验铸造形态与拒绝
口径，不验任何真实打开行为（VM 内无 Obsidian 活应用）。
"""

import urllib.parse

import pytest

from light_memory import uri


def _params(record):
    query = urllib.parse.urlparse(record["uri"]).query
    return dict(urllib.parse.parse_qsl(query))


def test_open_uri_form_and_encoding():
    rec = uri.open_uri("演示 vault", "笔记/火鸡 行为.md")
    assert rec["uri"].startswith("obsidian://open?")
    params = _params(rec)
    assert params == {"vault": "演示 vault", "file": "笔记/火鸡 行为.md"}
    assert "%20" in rec["uri"] and " " not in rec["uri"]
    assert rec["executed"] is False
    assert "不构成执行证据" in rec["note"]


def test_search_uri():
    rec = uri.search_uri("v", "火鸡 行为")
    assert rec["uri"].startswith("obsidian://search?")
    assert _params(rec)["query"] == "火鸡 行为"


def test_open_heading_uri_encodes_specials():
    rec = uri.open_heading_uri("v", "a.md", "结果 #1 讨论")
    assert rec["uri"].startswith("obsidian://adv-uri?")
    params = _params(rec)
    assert params["filepath"] == "a.md"
    assert params["heading"] == "结果 #1 讨论"
    assert "%23" in rec["uri"]  # # 必须编码，否则会切碎链接


def test_open_block_uri_strips_caret():
    rec = uri.open_block_uri("v", "a.md", "^blk42")
    assert _params(rec)["block"] == "blk42"


def test_daily_uri():
    rec = uri.daily_uri("v")
    assert _params(rec) == {"vault": "v", "daily": "true"}


def test_mint_dispatch_and_write_actions_refused():
    assert uri.mint("open", vault="v", file="a.md")["action"] == "open"
    assert uri.mint("daily", vault="v")["action"] == "daily"
    for action in ("new", "append", "create", "command", "delete"):
        with pytest.raises(uri.UriError) as exc:
            uri.mint(action, vault="v", file="a.md")
        assert "只铸导航链接" in exc.value.gaps[0]
    with pytest.raises(uri.UriError):
        uri.mint("teleport", vault="v")


def test_mint_validation():
    with pytest.raises(uri.UriError):
        uri.open_uri("", "a.md")
    with pytest.raises(uri.UriError):
        uri.open_uri("v", "a\x01b.md")


def test_markdown_link_render():
    rec = uri.open_uri("v", "a.md")
    assert uri.markdown_link("打开", rec) == \
        "[打开](obsidian://open?vault=v&file=a.md)"
    with pytest.raises(uri.UriError):
        uri.markdown_link("x", {"nope": 1})


def test_all_records_navigation_only():
    records = [
        uri.open_uri("v", "a.md"), uri.search_uri("v", "q"),
        uri.open_heading_uri("v", "a.md", "h"),
        uri.open_block_uri("v", "a.md", "b"), uri.daily_uri("v"),
    ]
    assert all(r["kind"] == "navigation" and r["executed"] is False
               for r in records)
