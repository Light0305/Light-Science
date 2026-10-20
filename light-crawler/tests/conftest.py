"""测试夹具：本地自搭 HTTP 站点（确定性、无外网）+ 工作区助手。

站点行为由 server 属性控制：robots_text / robots_status 决定
robots.txt 的应答形态；路由含 JSON（带 ETag）、HTML 页、403、
429（带 Retry-After）、站内与越域重定向。
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from light_crawler import project

HTML_PAGE = (b"<!doctype html><html><head><title>Demo Page</title>"
             b"<meta name=\"author\" content=\"Demo Author\"></head>"
             b"<body><h1>Hello</h1><p>Some public data text.</p>"
             b"<script>var x = 1;</script></body></html>")
DATA_JSON = json.dumps({"items": [1, 2, 3], "kind": "demo"}).encode()


def _etag_of(body: bytes) -> str:
    import hashlib
    return '"' + hashlib.sha256(body).hexdigest()[:12] + '"'


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # 测试输出保持安静
        pass

    def _send(self, code, body=b"", ctype="text/plain", extra=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if body:
            self.wfile.write(body)

    def do_GET(self):
        srv = self.server
        path = self.path.split("?")[0]
        if path == "/robots.txt":
            if srv.robots_status != 200:
                self._send(srv.robots_status, b"robots unavailable")
            elif srv.robots_text is None:
                self._send(404, b"no robots")
            else:
                self._send(200, srv.robots_text.encode(), "text/plain")
            return
        if path == "/data.json":
            body = srv.data_body if srv.data_body is not None else DATA_JSON
            etag = _etag_of(body)
            if self.headers.get("If-None-Match") == etag:
                self._send(304)
                return
            self._send(200, body, "application/json", {"ETag": etag})
            return
        if path == "/page.html":
            self._send(200, HTML_PAGE, "text/html")
            return
        if path == "/private/secret.json":
            self._send(200, b'{"secret": true}', "application/json")
            return
        if path == "/forbidden":
            self._send(403, b"forbidden")
            return
        if path == "/limited":
            self._send(429, b"slow down", extra={"Retry-After": "30"})
            return
        if path == "/redir-in":
            self._send(302, b"", extra={"Location": "/data.json"})
            return
        if path == "/redir-out":
            self._send(302, b"", extra={"Location": srv.outside_url})
            return
        self._send(404, b"not found")


def make_server():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    srv.robots_status = 200
    srv.robots_text = "User-agent: *\nAllow: /\n"
    srv.data_body = None
    srv.outside_url = "http://127.0.0.1:9/elsewhere"
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    return srv


@pytest.fixture()
def site():
    srv = make_server()
    yield srv, f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


@pytest.fixture()
def outside():
    srv = make_server()
    yield f"http://127.0.0.1:{srv.server_address[1]}/landing"
    srv.shutdown()


@pytest.fixture()
def ws(tmp_path):
    root = tmp_path / "data-sources"
    project.init_workspace(root, "demo-project")
    return root


def make_reg(base_url, target_id="t1", channel="official_api", **kw):
    reg = {
        "target_id": target_id,
        "name": f"目标 {target_id}",
        "base_url": base_url,
        "project": "demo-project",
        "purpose_kind": "dataset_batch",
        "consumer": "light-experiment 数据入口",
        "channel": channel,
        "terms_basis": "fixture 条款页（本地夹具）",
    }
    reg.update(kw)
    return reg
