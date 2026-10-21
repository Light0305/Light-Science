"""强化夹具站点集：复现真实世界撞墙场景（确定性、本地回环）。

与 conftest 的基础夹具分开：本服务器专为能力强化验收而设，路由覆盖
JS 渲染页、前端接口、分页、sitemap、人机校验墙、重定向链与环、
GBK 编码、gzip 压缩、大文件 Range、慢站与不稳定站。服务器记录
全部请求（路径 + 关键头）到 request_log，供断言以服务端日志为准。
"""

from __future__ import annotations

import gzip
import hashlib
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SPA_SHELL = (
    "<!doctype html><html><head><title>SPA Demo</title></head>"
    "<body><div id=\"app\"></div>"
    "<script>document.getElementById('app').textContent = "
    "'RENDERED-MARKER-42 ' + 'rendered poultry data';</script>"
    "</body></html>").encode()

API_PAGE = (
    "<!doctype html><html><head><title>API Page</title>"
    "<script src=\"/app.js\"></script></head>"
    "<body><h1>Catalog</h1>"
    "<script id=\"__NEXT_DATA__\" type=\"application/json\">"
    "{\"props\": {\"total\": 3, \"marker\": \"NEXTDATA-MARKER\"}}</script>"
    "<a href=\"/api/items\">items json</a>"
    "</body></html>").encode()

APP_JS = (
    "fetch('/api/items').then(r => r.json());\n"
    "axios.get(\"/api/v2/search?q=turkey\");\n"
    "var xhr = new XMLHttpRequest(); xhr.open('GET', '/api/detail?id=7');\n"
    "const cfg = {url: '/api/config'};\n").encode()

ITEMS_JSON = json.dumps({"items": [{"id": 1}, {"id": 2}],
                         "marker": "ITEMS-MARKER"}).encode()

GBK_TEXT = "中文编码标记：火鸡行为数据集 GBK-MARKER"
GBK_PAGE = ("<!doctype html><html><head><meta charset=\"gb2312\">"
            "<title>编码页</title></head><body><p>" + GBK_TEXT +
            "</p></body></html>").encode("gb18030")

GZIP_INNER = (b"<!doctype html><html><head><title>Gzip</title></head>"
              b"<body><p>GZIP-MARKER compressed content</p></body></html>")

CHALLENGE_PAGE = (
    "<!doctype html><html><head><title>Attention Required</title></head>"
    "<body><h1>Verify you are human</h1>"
    "<div class=\"g-recaptcha\" data-sitekey=\"fixture\"></div>"
    "<p>Please complete the captcha check below.</p>"
    "</body></html>").encode()

BIG_BODY = bytes((i * 7 + 13) % 256 for i in range(300_000))
BIG_SHA256 = hashlib.sha256(BIG_BODY).hexdigest()


def _list_page(n, total=3):
    items = "".join(f"<li>row {n}-{i}</li>" for i in range(3))
    nxt = (f"<link rel=\"next\" href=\"/list?page={n + 1}\">"
           f"<a rel=\"next\" href=\"/list?page={n + 1}\">next</a>"
           if n < total else "")
    return ("<!doctype html><html><head><title>List</title></head>"
            f"<body><h1>Page {n}</h1><ul>{items}</ul>{nxt}"
            "</body></html>").encode()


SITEMAP_XML = (
    "<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
    "<urlset xmlns=\"http://www.sitemaps.org/schemas/sitemap/0.9\">"
    "<url><loc>{base}/list?page=1</loc></url>"
    "<url><loc>{base}/list?page=2</loc></url>"
    "<url><loc>{base}/data.json</loc></url>"
    "</urlset>").encode()

DATA_JSON = json.dumps({"kind": "fixture-data"}).encode()


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def _log(self):
        self.server.request_log.append({
            "path": self.path,
            "range": self.headers.get("Range"),
            "ua": self.headers.get("User-Agent"),
        })

    def _send(self, code, body=b"", ctype="text/plain", extra=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if body:
            self.wfile.write(body)

    def do_GET(self):
        self._log()
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
        if path == "/sitemap.xml":
            if srv.sitemap_enabled:
                base = f"http://127.0.0.1:{srv.server_address[1]}"
                self._send(200, SITEMAP_XML.replace(b"{base}",
                                                     base.encode()),
                           "application/xml")
            else:
                self._send(404, b"no sitemap")
            return
        if path == "/spa":
            self._send(200, SPA_SHELL, "text/html")
            return
        if path == "/api-page":
            self._send(200, API_PAGE, "text/html")
            return
        if path == "/app.js":
            self._send(200, APP_JS, "application/javascript")
            return
        if path == "/api/items":
            self._send(200, ITEMS_JSON, "application/json")
            return
        if path == "/api/v2/search":
            self._send(200, b'{"hits": []}', "application/json")
            return
        if path == "/api/detail":
            self._send(200, b'{"detail": true}', "application/json")
            return
        if path == "/api/config":
            self._send(200, b'{"config": true}', "application/json")
            return
        if path == "/list":
            q = self.path.split("?", 1)[1] if "?" in self.path else ""
            page = 1
            for part in q.split("&"):
                if part.startswith("page="):
                    page = int(part.split("=", 1)[1])
            self._send(200, _list_page(page), "text/html")
            return
        if path == "/data.json":
            self._send(200, DATA_JSON, "application/json")
            return
        if path == "/walled":
            self._send(403, b"Forbidden by site policy")
            return
        if path == "/challenge":
            self._send(200, CHALLENGE_PAGE, "text/html")
            return
        if path == "/chain1":
            self._send(302, b"", extra={"Location": "/chain2"})
            return
        if path == "/chain2":
            self._send(302, b"", extra={"Location": "/data.json"})
            return
        if path == "/loop":
            self._send(302, b"", extra={"Location": "/loop"})
            return
        if path == "/gbk":
            self._send(200, GBK_PAGE, "text/html")
            return
        if path == "/gzip-page":
            self._send(200, gzip.compress(GZIP_INNER), "text/html",
                       {"Content-Encoding": "gzip"})
            return
        if path == "/big.bin":
            rng = self.headers.get("Range")
            if rng and rng.startswith("bytes="):
                spec = rng[6:].split(",", 1)[0]
                start_s, _, end_s = spec.partition("-")
                start = int(start_s) if start_s else 0
                end = int(end_s) if end_s else len(BIG_BODY) - 1
                end = min(end, len(BIG_BODY) - 1)
                chunk = BIG_BODY[start:end + 1]
                self._send(206, chunk, "application/octet-stream", {
                    "Content-Range": f"bytes {start}-{end}/{len(BIG_BODY)}",
                    "Accept-Ranges": "bytes"})
            else:
                self._send(200, BIG_BODY, "application/octet-stream",
                           {"Accept-Ranges": "bytes"})
            return
        if path == "/slow":
            time.sleep(srv.slow_delay)
            self._send(200, b"slow ok", "text/plain")
            return
        if path == "/unstable":
            srv.unstable_hits += 1
            if srv.unstable_hits <= srv.unstable_failures:
                self._send(503, b"temporarily unavailable")
            else:
                self._send(200, b'{"recovered": true}', "application/json")
            return
        self._send(404, b"not found")


def make_fixture_server():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    srv.robots_status = 200
    srv.robots_text = "User-agent: *\nAllow: /\n"
    srv.sitemap_enabled = False
    srv.slow_delay = 1.5
    srv.unstable_failures = 2
    srv.unstable_hits = 0
    srv.request_log = []
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    return srv


def base_of(srv) -> str:
    return f"http://127.0.0.1:{srv.server_address[1]}"


def hits(srv, path_prefix) -> int:
    return sum(1 for r in srv.request_log
               if r["path"].split("?")[0] == path_prefix)
