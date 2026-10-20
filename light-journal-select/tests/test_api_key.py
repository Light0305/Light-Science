"""可选 OpenAlex API Key（JS-11）：环境注入、请求携带、落痕脱敏。

钉死三条：
1. live_fetcher 在 OPENALEX_API_KEY 在场时以 api_key 参数带上，
   不在场时匿名、URL 不带该参数；
2. precedent_runs 落痕的 URL 与异常消息一律脱敏（REDACTED）；
3. 注入假 Key 跑完整先例路后，选刊包全目录 grep 无 Key 明文。
"""

from __future__ import annotations

import io
import json
import urllib.parse
import urllib.request

import pytest

from conftest import FakeFetcher, Q0, Q1, VOLUMES, works_payload
from light_journal_select import precedent as precedent_mod
from light_journal_select.precedent import (
    redact_text, redact_url, run_precedent, with_api_key,
)
from light_journal_select.project import load_selection

FAKE_KEY = "FAKEKEY-9f8e7d6c5b4a3210"


def _grep_tree(root, needle: str) -> list[str]:
    """全目录文本 grep：返回命中 needle 的文件相对路径。"""
    hits = []
    for path in sorted(root.rglob("*")):
        if path.is_file() and needle in path.read_text(
                encoding="utf-8", errors="ignore"):
            hits.append(str(path.relative_to(root)))
    return hits


# ------------------------------------------------------------ 单元

def test_with_api_key_appends_and_dedupes():
    url = with_api_key("https://api.openalex.org/works?search=x", FAKE_KEY)
    assert url.endswith(f"api_key={FAKE_KEY}")
    again = with_api_key(url, "OTHER")
    assert again.count("api_key=") == 1
    assert "api_key=OTHER" in again and FAKE_KEY not in again
    bare = with_api_key("https://api.openalex.org/works", FAKE_KEY)
    assert bare == f"https://api.openalex.org/works?api_key={FAKE_KEY}"


def test_redact_url_only_touches_key_param():
    clean = "https://api.openalex.org/works?search=a%20b&per-page=50"
    assert redact_url(clean) == clean  # 无 Key 时逐字不变
    keyed = f"https://api.openalex.org/works?search=x&api_key={FAKE_KEY}"
    out = redact_url(keyed)
    assert FAKE_KEY not in out and "api_key=REDACTED" in out
    assert "search=x" in out


def test_redact_text_covers_param_and_bare_key():
    msg = f"GET https://h/works?api_key={FAKE_KEY}&y=1 failed; key={FAKE_KEY}"
    out = redact_text(msg, key=FAKE_KEY)
    assert FAKE_KEY not in out
    assert out.count("REDACTED") == 2
    assert redact_text("plain error", key=FAKE_KEY) == "plain error"


# ------------------------------------------------------- live_fetcher

class _FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


def _capture_urlopen(monkeypatch, payload):
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        return _FakeResponse(json.dumps(payload).encode("utf-8"))

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    return captured


def test_live_fetcher_carries_key_when_env_set(monkeypatch):
    monkeypatch.setenv("OPENALEX_API_KEY", FAKE_KEY)
    captured = _capture_urlopen(monkeypatch, {"ok": True})
    out = precedent_mod.live_fetcher("https://api.openalex.org/works?search=x")
    assert out == {"ok": True}
    params = urllib.parse.parse_qs(
        urllib.parse.urlparse(captured["url"]).query)
    assert params["api_key"] == [FAKE_KEY]
    assert params["search"] == ["x"]


def test_live_fetcher_anonymous_without_key(monkeypatch):
    monkeypatch.delenv("OPENALEX_API_KEY", raising=False)
    captured = _capture_urlopen(monkeypatch, {"ok": True})
    precedent_mod.live_fetcher("https://api.openalex.org/works?search=x")
    assert "api_key" not in captured["url"]


# ------------------------------------------------- 落痕脱敏（整链）

def test_keyed_failure_error_is_redacted(pkg, monkeypatch):
    """fetcher 异常消息内嵌带 Key 的 URL：落盘的 error 必须脱敏。"""
    monkeypatch.setenv("OPENALEX_API_KEY", FAKE_KEY)

    class KeyedFailFetcher(FakeFetcher):
        def __call__(self, url):
            params = urllib.parse.parse_qs(
                urllib.parse.urlparse(url).query)
            if params.get("search", [""])[0] == Q1:
                raise RuntimeError(
                    f"HTTP 429 from {with_api_key(url, FAKE_KEY)}")
            return super().__call__(url)

    result = run_precedent(pkg, fetcher=KeyedFailFetcher(),
                           today_str="2026-10-20")
    assert result["queries_ok"] == 1  # 一成一败仍推进
    selection = load_selection(pkg)
    failed = [r for r in selection["precedent_runs"]
              if r["status"] == "failed"]
    assert len(failed) == 1
    assert FAKE_KEY not in failed[0]["error"]
    assert "api_key=REDACTED" in failed[0]["error"]
    assert _grep_tree(pkg, FAKE_KEY) == []  # 全目录无 Key 明文


def test_live_path_with_key_leaves_no_trace(pkg, monkeypatch):
    """走真 live_fetcher（urlopen 打桩）+ 假 Key 跑完整先例路：
    池建成、证据落盘、全目录 grep 无 Key 明文、落痕 URL 无 api_key。"""
    monkeypatch.setenv("OPENALEX_API_KEY", FAKE_KEY)

    def fake_urlopen(req, timeout=None):
        url = req.full_url
        assert FAKE_KEY in url  # 线上确实带了 Key（只活在本断言里）
        params = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        if "search" in params:
            payload = works_payload(params["search"][0])
        else:
            filt = params.get("filter", [""])[0]
            count = next((c for sid, c in VOLUMES.items()
                          if f"source.id:{sid}" in filt), 0)
            payload = {"meta": {"count": count}, "results": []}
        return _FakeResponse(json.dumps(payload).encode("utf-8"))

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    result = run_precedent(pkg, today_str="2026-10-20")  # 缺省 live_fetcher
    assert result["queries_ok"] == 2
    assert set(result["admitted"]) == {
        "Computers and Electronics in Agriculture", "Animals",
        "Poultry Science"}
    selection = load_selection(pkg)
    for run in selection["precedent_runs"]:
        assert "api_key" not in run["url"]
        assert (pkg / run["evidence_file"]).exists()
    assert _grep_tree(pkg, FAKE_KEY) == []
