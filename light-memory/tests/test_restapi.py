"""restapi Local REST API 适配器：本地桩 HTTP 服务器契约测试（T3）。

契约来源声明：方法/路径/头/ETag/412/错误体形态按插件
coddingtonbear/obsidian-local-rest-api v5.5.2 本地克隆的 README
与 docs/openapi.yaml 一手实读建模（GET 应答 ETag 为版本令牌、
写带 If-Match 不符 412 且不落盘、错误体为 {errorCode, message}、
PATCH 为 JSON 指令 {targetType, target, operation, content/value}）。
桩是本测试自建的内存实现、不是插件本体；真实插件的自签 CA
HTTPS 一端未验，实机冒烟在 22-user-machine/checklist 第 6 项。
"""

import json
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from light_memory import restapi, vaultio

KEY = "fixture-key-not-a-real-secret"
AUTH = f"Bearer {KEY}"


# ---------------------------------------------------------------- 桩

class _Stub:
    def __init__(self):
        self.notes = {}   # rel -> {"text": str, "version": int}
        self.log = []     # (method, raw_path, headers{lower: value})

    def etag(self, rel):
        return f'"{self.notes[rel]["version"]}"'

    def bump(self, rel, text):
        note = self.notes.setdefault(rel, {"text": "", "version": 0})
        note["text"] = text
        note["version"] += 1
        return self.etag(rel)


def _make_handler(stub):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *a):
            pass

        # -- 骨架 ------------------------------------------------
        def _send(self, status, body=b"", ctype="application/json",
                  etag=None):
            if isinstance(body, str):
                body = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            if etag:
                self.send_header("ETag", etag)
            self.end_headers()
            if body:
                self.wfile.write(body)

        def _err(self, status, code, message):
            self._send(status, json.dumps(
                {"errorCode": code, "message": message}))

        def _handle(self, method):
            parsed = urllib.parse.urlparse(self.path)
            segments = [urllib.parse.unquote(s) for s in
                        parsed.path.split("/") if s]
            headers = {k.lower(): v for k, v in self.headers.items()}
            stub.log.append((method, self.path, headers))
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length) if length else b""
            authed = headers.get("authorization") == AUTH

            if method == "GET" and not segments:
                return self._send(200, json.dumps({
                    "status": "OK", "authenticated": authed,
                    "state": {"metadataCache": {}}}))
            if not authed:
                return self._err(401, 40100,
                                 "Authorization required")
            if segments[:1] == ["search"]:
                query = urllib.parse.parse_qs(parsed.query) \
                    .get("query", [""])[0]
                results = []
                for rel, note in sorted(stub.notes.items()):
                    hits = [ln for ln in note["text"].split("\n")
                            if query in ln]
                    if hits:
                        results.append({
                            "filename": rel, "score": 1.0,
                            "matches": [{"context": h}
                                        for h in hits]})
                return self._send(200, json.dumps(results))
            if segments[:1] != ["vault"]:
                return self._err(404, 40400, "Unknown route")
            if method == "GET" and len(segments) == 1:
                return self._send(200, json.dumps(
                    {"files": sorted(stub.notes)}))

            rel = "/".join(segments[1:])
            note = stub.notes.get(rel)
            if method == "GET":
                if note is None:
                    return self._err(404, 40400,
                                     f"File not found: {rel}")
                return self._send(200, note["text"],
                                  "text/markdown", stub.etag(rel))
            # 写方法先过条件门
            if_match = headers.get("if-match")
            if if_match and (note is None
                             or if_match != stub.etag(rel)):
                current = stub.etag(rel) if note else "none"
                return self._err(
                    412, 41200,
                    f"Precondition failed; current version is "
                    f"{current}")
            if headers.get("if-none-match") == "*" and note:
                return self._err(
                    412, 41200,
                    f"Precondition failed; current version is "
                    f"{stub.etag(rel)}")
            if method == "PUT":
                etag = stub.bump(rel, body.decode("utf-8"))
                return self._send(204, b"", etag=etag)
            if method == "POST":
                old = note["text"] if note else ""
                etag = stub.bump(rel, old + body.decode("utf-8"))
                return self._send(200, b"", etag=etag)
            if method == "DELETE":
                if note is None:
                    return self._err(404, 40400,
                                     f"File not found: {rel}")
                del stub.notes[rel]
                return self._send(204, b"")
            if method == "PATCH":
                if note is None:
                    return self._err(404, 40400,
                                     f"File not found: {rel}")
                ins = json.loads(body.decode("utf-8"))
                text = note["text"]
                if ins["targetType"] == "frontmatter":
                    text = vaultio.fm_set_in_text(
                        text, ins["target"], ins.get("value"))
                else:
                    lines = text.split("\n")
                    sec = vaultio.find_section(
                        lines, "/".join(ins["target"]))
                    assert sec is not None, "夹具标题须存在"
                    start, end, _ = sec
                    content_lines = (ins.get("content") or "") \
                        .split("\n")
                    if ins["operation"] == "append":
                        merged = lines[:end] + content_lines \
                            + lines[end:]
                    elif ins["operation"] == "replace":
                        merged = lines[:start] + content_lines \
                            + lines[end:]
                    elif ins["operation"] == "delete":
                        merged = lines[:start - 1] + lines[end:]
                    else:
                        raise AssertionError(ins["operation"])
                    text = "\n".join(merged)
                etag = stub.bump(rel, text)
                return self._send(200, b"", etag=etag)
            return self._err(405, 40500, "Method not allowed")

        do_GET = lambda self: self._handle("GET")
        do_PUT = lambda self: self._handle("PUT")
        do_POST = lambda self: self._handle("POST")
        do_PATCH = lambda self: self._handle("PATCH")
        do_DELETE = lambda self: self._handle("DELETE")

    return Handler


@pytest.fixture()
def stub():
    state = _Stub()
    server = ThreadingHTTPServer(("127.0.0.1", 0),
                                 _make_handler(state))
    thread = threading.Thread(target=server.serve_forever,
                              daemon=True)
    thread.start()
    state.base_url = f"http://127.0.0.1:{server.server_address[1]}"
    yield state
    server.shutdown()


def _client(stub, allow_write=True, key=KEY):
    return restapi.RestClient(base_url=stub.base_url,
                              allow_write=allow_write,
                              environ={restapi.KEY_ENV: key})


# ---------------------------------------------------------------- 启用与授权

def test_disabled_without_key_sends_nothing(stub):
    calls = []

    def spy(method, url, headers, body, timeout):
        calls.append(method)
        raise AssertionError("未启用不许发请求")

    client = restapi.RestClient(base_url=stub.base_url,
                                transport=spy, environ={})
    assert client.enabled is False
    with pytest.raises(restapi.RestError) as exc:
        client.get_note("a.md")
    assert restapi.KEY_ENV in exc.value.gaps[0]
    assert calls == []
    probe = restapi.probe_rest(client=client)
    assert probe["status"] == "disabled" and probe["verified"] is False


def test_write_requires_separate_authorization(stub):
    calls = []

    def spy(method, url, headers, body, timeout):
        calls.append(method)
        raise AssertionError("未授权不许发请求")

    client = restapi.RestClient(base_url=stub.base_url,
                                allow_write=False, transport=spy,
                                environ={restapi.KEY_ENV: KEY})
    with pytest.raises(restapi.RestError) as exc:
        client.put_note("a.md", "x")
    assert "分开授权" in exc.value.gaps[0]
    assert calls == []


def test_non_loopback_base_refused():
    with pytest.raises(restapi.RestError):
        restapi.RestClient(base_url="https://example.com:27124",
                           environ={restapi.KEY_ENV: KEY})


def test_probe_available_and_status(stub):
    client = _client(stub, allow_write=False)
    probe = restapi.probe_rest(client=client)
    assert probe["status"] == "available"
    assert probe["plugin_baseline"] == "5.5.2"
    status = client.server_status()
    assert status["status"] == "OK"
    assert status["authenticated"] is True
    assert status["receipt"]["surface"] == "local-rest-api"


def test_probe_unauthenticated_with_wrong_key(stub):
    client = _client(stub, key="wrong-key")
    assert restapi.probe_rest(client=client)["status"] == \
        "unauthenticated"
    with pytest.raises(restapi.RestError) as exc:
        client.get_note("a.md")
    assert exc.value.status == 401


def test_probe_unreachable_closed_port():
    client = restapi.RestClient(base_url="http://127.0.0.1:1",
                                environ={restapi.KEY_ENV: KEY})
    probe = restapi.probe_rest(client=client)
    assert probe["status"] == "unreachable"
    assert "连接失败" in probe["reason"]


# ---------------------------------------------------------------- 契约

def test_put_get_etag_conditional_roundtrip(stub):
    client = _client(stub)
    r = client.put_note("notes/a.md", "# A\n\n正文一\n")
    assert r["etag"] == '"1"'
    got = client.get_note("notes/a.md")
    assert got["text"] == "# A\n\n正文一\n" and got["etag"] == '"1"'
    # 带当前 ETag 的条件写通过并换新版本
    r2 = client.put_note("notes/a.md", "# A\n\n正文二\n",
                         if_match=got["etag"])
    assert r2["etag"] == '"2"'
    # 拿旧 ETag 再写：412 点名且不落盘
    with pytest.raises(restapi.RestError) as exc:
        client.put_note("notes/a.md", "篡改\n", if_match='"1"')
    assert exc.value.status == 412 and exc.value.error_code == 41200
    assert "current version is" in exc.value.gaps[0]
    assert client.get_note("notes/a.md")["text"] == "# A\n\n正文二\n"


def test_create_only_if_none_match(stub):
    client = _client(stub)
    client.put_note("b.md", "已有\n")
    with pytest.raises(restapi.RestError) as exc:
        client.put_note("b.md", "覆盖\n", create_only=True)
    assert exc.value.status == 412
    r = client.put_note("c.md", "新建\n", create_only=True)
    assert r["etag"] == '"1"'


def test_patch_heading_append_and_replace(stub):
    client = _client(stub)
    client.put_note("n.md", "# 标题\n\n## 甲\n\n甲一\n\n## 乙\n\n乙一\n")
    client.patch_heading("n.md", ["标题", "甲"], "append",
                         content="甲二")
    text = client.get_note("n.md")["text"]
    # 插件口径：append 落为独立块（自带空行分隔），且只进目标段
    sec_a = text.split("## 甲")[1].split("## 乙")[0]
    assert "甲一" in sec_a and "甲二" in sec_a
    assert "## 乙\n\n乙一" in text
    client.patch_heading("n.md", ["标题", "乙"], "replace",
                         content="乙改")
    text = client.get_note("n.md")["text"]
    assert "乙改" in text and "乙一" not in text
    assert text.startswith("# 标题")


def test_patch_frontmatter_value(stub):
    client = _client(stub)
    client.put_note("f.md", "---\nstatus: draft  # 保留注释\n"
                            "other: 1\n---\n\n正文\n")
    client.patch_frontmatter("f.md", "status", "replace",
                             value="done")
    text = client.get_note("f.md")["text"]
    found, value = vaultio.fm_get(text, "status")
    assert found and value == "done"
    assert "other: 1" in text


def test_append_and_delete(stub):
    client = _client(stub)
    client.put_note("d.md", "一\n")
    client.append_note("d.md", "二\n")
    assert client.get_note("d.md")["text"] == "一\n二\n"
    etag = client.get_note("d.md")["etag"]
    client.delete_note("d.md", if_match=etag)
    with pytest.raises(restapi.RestError) as exc:
        client.get_note("d.md")
    assert exc.value.status == 404 and exc.value.error_code == 40400


def test_list_and_search(stub):
    client = _client(stub)
    client.put_note("s1.md", "火鸡行为研究\n")
    client.put_note("s2.md", "无关内容\n")
    assert client.list_files()["files"] == ["s1.md", "s2.md"]
    results = client.search_simple("火鸡")["results"]
    assert [r["filename"] for r in results] == ["s1.md"]


# ---------------------------------------------------------------- 密钥纪律

def test_key_never_leaks_into_receipts_or_errors(stub):
    client = _client(stub)
    receipts = []
    receipts.append(client.put_note("k.md", "正文\n")["receipt"])
    receipts.append(client.get_note("k.md")["receipt"])
    receipts.append(client.server_status()["receipt"])
    try:
        client.put_note("k.md", "x", if_match='"999"')
    except restapi.RestError as exc:
        receipts.append({"error": exc.gaps})
    dumped = json.dumps(receipts, ensure_ascii=False)
    assert KEY not in dumped
    # 密钥在通道上只许出现在 Authorization 头里
    for method, path, headers in stub.log:
        for name, value in headers.items():
            if KEY in value:
                assert name == "authorization"
