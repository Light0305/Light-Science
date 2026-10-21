"""浏览器渲染通道：随包提供的无头 Chromium 执行器（能力强化批）。

v1 的浏览器通道只有预检门与注入契约、执行器不随包提供（SKILL
第 12 节局限 1）。本模块补上执行器本体，定位是正式通道：

- 主通道走 CDP（DevTools 协议）：导航、网络事件采集（状态码、
  资源清单、重定向链）、滚动收割（无限滚动页逐屏滚到底、DOM
  增量稳定才停）、渲染后 DOM 回读；
- 回环/内网目标的桥接模式：Chrome 152 起，页面发起的导航访问
  本地地址空间会被 Local Network Access 检查拦截（实测：启动
  flag、权限预授权、代理均不能解，见强化报告）。命中该拦截或
  目标主机字面为 localhost/回环/内网地址时，自动转桥接模式：
  浏览器请求经 Fetch 域拦截后由本包静态传输层取回真实字节再
  回填渲染（engine 标注 cdp+fetch-bridge）——渲染的是目标站
  的真实响应，拦截的只是浏览器自带的本地网络自我保护，不是
  目标站的任何访问控制；目标站照常可以 403 回绝并触发熔断；
- CDP 不可用时降级 dump-dom（只有渲染 DOM，状态码与资源清单
  如实标注不可得，不冒充）；
- 人机校验识别：渲染产物命中强挑战标记（验证码组件等）时
  返回 blocked 结论，由调用方按 HC-8 熔断留痕——本模块不做
  任何验证码代解或挑战绕过；
- 凭据会话：凭据访问通道的目标由本渲染器承载会话——调用方
  经 provider 注入 cookie 后再导航；cookie 值只进浏览器进程，
  本模块不落盘、不回显，只记 cookie 名。

身份纪律：渲染器以本包声明 UA 覆盖 HeadlessChrome 默认串
（Network.setUserAgentOverride），与静态通道同一身份，不伪装
真人浏览器、不做指纹模拟（HC-7 的工具箱禁区不变）。
"""

from __future__ import annotations

import base64
import ipaddress
import json
import os
import re
import shutil
import socket
import struct
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

from . import schema

RENDER_TIMEOUT_SEC = 45.0
MAX_SCROLLS = 12
SCROLL_SETTLE_SEC = 0.45

#: 人机校验强标记：命中任一即判 blocked（验证码组件/挑战框架在场）
STRONG_CHALLENGE_MARKERS = (
    "g-recaptcha", "h-captcha", "cf-turnstile", "cf-chl",
    "challenges.cloudflare.com", "verify you are human",
    "are you a robot",
)
#: 弱标记：只标注 suspected，不单独构成 blocked
WEAK_CHALLENGE_MARKERS = ("captcha", "checking your browser",
                          "just a moment", "attention required")

LOGIN_PATH_HINTS = ("/login", "/signin", "/sign-in", "/auth/login",
                    "/accounts/login")


class RenderError(Exception):
    def __init__(self, kind, message):
        self.kind = kind
        super().__init__(message)


class RenderedPage:
    def __init__(self, url, final_url, status, dom, resources,
                 redirect_chain, engine, blocked=None,
                 challenge_suspected=None, login_required=False,
                 status_basis="network"):
        self.url = url
        self.final_url = final_url
        self.status = status            # None 表示该引擎不可得
        self.dom = dom or ""
        self.resources = resources or []
        self.redirect_chain = redirect_chain or []
        self.engine = engine
        self.blocked = blocked          # {"kind","markers"} 或 None
        self.challenge_suspected = challenge_suspected or []
        self.login_required = login_required
        self.status_basis = status_basis

    @property
    def body(self) -> bytes:
        return self.dom.encode("utf-8")


def find_chromium() -> str | None:
    """定位 Chromium 可执行文件：环境变量 -> PATH -> 已知路径。"""
    env = os.environ.get("LIGHT_CRAWLER_CHROMIUM")
    if env and Path(env).is_file():
        return env
    for name in ("chromium", "chromium-browser", "google-chrome",
                 "google-chrome-stable", "chrome"):
        found = shutil.which(name)
        if found:
            return found
    for cand in ("/opt/meta-chromium/chrome",
                 "/usr/lib/chromium/chromium",
                 "/snap/bin/chromium"):
        if Path(cand).is_file():
            return cand
    return None


def host_is_local(url: str) -> bool:
    """目标主机是否为回环/内网地址空间（字面判定，不做 DNS 解析）。

    这类目标在 Chrome 152 里会被 Local Network Access 检查拦下
    页面发起的导航，渲染器据此预先启用桥接模式；域名解析后落
    内网的情形靠导航失败后的被动桥接兜底。
    """
    host = (urlparse(url).hostname or "").lower()
    if host in ("localhost",) or host.endswith(".localhost"):
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return bool(ip.is_loopback or ip.is_private or ip.is_link_local
                or ip.is_reserved)


def detect_challenge(dom: str) -> dict:
    """扫描渲染 DOM 的人机校验标记。返回 blocked/suspected 结论。"""
    low = (dom or "").lower()
    strong = [m for m in STRONG_CHALLENGE_MARKERS if m in low]
    weak = [m for m in WEAK_CHALLENGE_MARKERS if m in low]
    blocked = None
    if strong:
        blocked = {"kind": "human_verification",
                   "markers": strong,
                   "detail": "渲染产物命中人机校验强标记，本通道不代解"
                             "验证码：按回绝处理并留痕（HC-8 同口径）"}
    return {"blocked": blocked, "suspected": weak if not strong else []}


def detect_login_required(final_url: str, dom: str) -> bool:
    """登录墙启发式：最终 URL 落在登录路径，或 DOM 含密码框表单。"""
    path = urlparse(final_url or "").path.lower()
    if any(h in path for h in LOGIN_PATH_HINTS):
        return True
    low = (dom or "").lower()
    return 'type="password"' in low and "<form" in low


# ---------------------------------------------------------------- WebSocket（CDP 传输，最小实现）

class _WS:
    """最小 WebSocket 客户端：仅实现 CDP 所需的文本帧收发。

    客户端帧按 RFC 6455 掩码；服务端帧处理分片、ping/pong、close。
    """

    def __init__(self, ws_url: str, timeout: float = 10.0):
        parts = urlparse(ws_url)
        self.sock = socket.create_connection(
            (parts.hostname, parts.port), timeout=timeout)
        self.sock.settimeout(timeout)
        key = base64.b64encode(os.urandom(16)).decode()
        path = parts.path + (("?" + parts.query) if parts.query else "")
        req = (
            f"GET {path} HTTP/1.1\r\nHost: {parts.hostname}:{parts.port}\r\n"
            "Upgrade: websocket\r\nConnection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n")
        self.sock.sendall(req.encode())
        buf = b""
        while b"\r\n\r\n" not in buf:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise RenderError("cdp_handshake", "WebSocket 握手无响应")
            buf += chunk
        head, _, rest = buf.partition(b"\r\n\r\n")
        if b" 101 " not in head.split(b"\r\n", 1)[0] + b" ":
            raise RenderError("cdp_handshake",
                              f"WebSocket 升级被拒：{head[:120]!r}")
        self._rest = rest
        self._fragments = []

    def _read_exact(self, n: int) -> bytes:
        while len(self._rest) < n:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise RenderError("cdp_closed", "WebSocket 连接被关闭")
            self._rest += chunk
        out, self._rest = self._rest[:n], self._rest[n:]
        return out

    def send_text(self, text: str) -> None:
        payload = text.encode("utf-8")
        mask = os.urandom(4)
        header = bytearray([0x81])
        if len(payload) < 126:
            header.append(0x80 | len(payload))
        elif len(payload) < 65536:
            header.append(0x80 | 126)
            header += struct.pack(">H", len(payload))
        else:
            header.append(0x80 | 127)
            header += struct.pack(">Q", len(payload))
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        self.sock.sendall(bytes(header) + mask + masked)

    def recv_message(self) -> str | None:
        """收一条完整文本消息；控制帧内部处理；关闭返回 None。"""
        while True:
            b1, b2 = self._read_exact(2)
            fin, opcode = b1 & 0x80, b1 & 0x0F
            masked, length = b2 & 0x80, b2 & 0x7F
            if length == 126:
                length = struct.unpack(">H", self._read_exact(2))[0]
            elif length == 127:
                length = struct.unpack(">Q", self._read_exact(8))[0]
            if masked:
                mask = self._read_exact(4)
            payload = self._read_exact(length) if length else b""
            if masked:
                payload = bytes(b ^ mask[i % 4]
                                for i, b in enumerate(payload))
            if opcode == 0x8:
                return None
            if opcode == 0x9:  # ping -> pong
                self._send_control(0xA, payload)
                continue
            if opcode == 0xA:
                continue
            self._fragments.append(payload)
            if fin:
                data = b"".join(self._fragments)
                self._fragments = []
                return data.decode("utf-8", errors="replace")

    def _send_control(self, opcode: int, payload: bytes) -> None:
        mask = os.urandom(4)
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        self.sock.sendall(bytes([0x80 | opcode, 0x80 | len(payload)])
                          + mask + masked)

    def close(self) -> None:
        try:
            self._send_control(0x8, b"")
        except Exception:
            pass
        try:
            self.sock.close()
        except Exception:
            pass


class _CDPSession:
    """一条页面级 CDP 会话：请求/响应配对 + 事件收集。"""

    def __init__(self, ws: _WS):
        self.ws = ws
        self._next_id = 0
        self.events = []       # (method, params)
        self.on_event = None   # callable(method, params)

    def send_only(self, method: str, params: dict = None) -> None:
        """只发不等回执（桥接回填用：回执在后续读循环里被无害丢弃）。"""
        self._next_id += 1
        self.ws.send_text(json.dumps(
            {"id": self._next_id, "method": method,
             "params": params or {}}))

    def call(self, method: str, params: dict = None, timeout: float = 20.0):
        self._next_id += 1
        mid = self._next_id
        self.ws.send_text(json.dumps(
            {"id": mid, "method": method, "params": params or {}}))
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            raw = self.ws.recv_message()
            if raw is None:
                raise RenderError("cdp_closed", f"CDP 在 {method} 期间关闭")
            msg = json.loads(raw)
            if msg.get("id") == mid:
                if "error" in msg:
                    raise RenderError(
                        "cdp_error",
                        f"{method} 失败：{msg['error'].get('message')}")
                return msg.get("result") or {}
            if "method" in msg:
                self.events.append((msg["method"], msg.get("params") or {}))
                if self.on_event:
                    self.on_event(msg["method"], msg.get("params") or {})
        raise RenderError("cdp_timeout", f"CDP 调用超时：{method}")

    def pump(self, seconds: float) -> None:
        """在给定时间内只收事件（等加载/滚动稳定用）。"""
        deadline = time.monotonic() + seconds
        old_timeout = self.ws.sock.gettimeout()
        try:
            while time.monotonic() < deadline:
                self.ws.sock.settimeout(
                    max(0.05, deadline - time.monotonic()))
                try:
                    raw = self.ws.recv_message()
                except (socket.timeout, TimeoutError):
                    break
                if raw is None:
                    break
                msg = json.loads(raw)
                if "method" in msg:
                    self.events.append(
                        (msg["method"], msg.get("params") or {}))
                    if self.on_event:
                        self.on_event(msg["method"],
                                      msg.get("params") or {})
        finally:
            self.ws.sock.settimeout(old_timeout)


# ---------------------------------------------------------------- 渲染器

class ChromiumRenderer:
    """无头 Chromium 渲染器：CDP 主通道，dump-dom 降级兜底。"""

    def __init__(self, executable=None, timeout=RENDER_TIMEOUT_SEC,
                 max_scrolls=MAX_SCROLLS, user_agent=None):
        self.executable = executable or find_chromium()
        self.timeout = float(timeout)
        self.max_scrolls = int(max_scrolls)
        self.user_agent = user_agent or schema.USER_AGENT

    def available(self) -> bool:
        return bool(self.executable and Path(self.executable).is_file())

    # ---- 进程与目标管理

    def _launch(self):
        tmp = tempfile.mkdtemp(prefix="lc-chrome-")
        err_path = Path(tmp) / "stderr.log"
        err = open(err_path, "wb")
        args = [self.executable, "--headless=new", "--no-sandbox",
                "--disable-gpu", "--disable-dev-shm-usage",
                "--no-first-run", "--no-default-browser-check",
                "--remote-debugging-address=127.0.0.1",
                "--remote-debugging-port=0",
                f"--user-data-dir={tmp}", "about:blank"]
        proc = subprocess.Popen(args, stdout=subprocess.DEVNULL,
                                stderr=err)
        port = None
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                break
            try:
                data = err_path.read_text(errors="replace")
            except Exception:
                data = ""
            m = re.search(r"DevTools listening on ws://\S+?:(\d+)", data)
            if m:
                port = int(m.group(1))
                break
            time.sleep(0.1)
        err.close()
        if port is None:
            self._cleanup(proc, tmp)
            raise RenderError(
                "launch", "Chromium 启动失败或未开放 DevTools 端口")
        return proc, tmp, port

    @staticmethod
    def _cleanup(proc, tmp):
        try:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
        except Exception:
            pass
        shutil.rmtree(tmp, ignore_errors=True)

    @staticmethod
    def _new_page_ws(port: int) -> str:
        url = f"http://127.0.0.1:{port}/json/new?about:blank"
        for method in ("PUT", "GET"):
            try:
                req = urllib.request.Request(url, method=method)
                with urllib.request.urlopen(req, timeout=5) as resp:
                    info = json.loads(resp.read().decode("utf-8"))
                if info.get("webSocketDebuggerUrl"):
                    return info["webSocketDebuggerUrl"]
            except Exception:
                continue
        with urllib.request.urlopen(
                f"http://127.0.0.1:{port}/json/list", timeout=5) as resp:
            pages = json.loads(resp.read().decode("utf-8"))
        for p in pages:
            if p.get("type") == "page" and p.get("webSocketDebuggerUrl"):
                return p["webSocketDebuggerUrl"]
        raise RenderError("cdp_target", "无法创建或定位页面目标")

    # ---- 主入口

    def render(self, url, cookies=None, extra_headers=None,
               scroll=True) -> RenderedPage:
        if not self.available():
            raise RenderError(
                "chromium_missing",
                "未找到 Chromium 可执行文件（环境变量 "
                "LIGHT_CRAWLER_CHROMIUM / PATH / 已知路径均无）")
        cookies, extra_headers = cookies or [], extra_headers or {}
        try:
            if host_is_local(url):
                return self._render_cdp(url, cookies, extra_headers,
                                        scroll, bridge=True)
            try:
                return self._render_cdp(url, cookies, extra_headers,
                                        scroll)
            except RenderError as e:
                if e.kind != "lna_blocked":
                    raise
                return self._render_cdp(url, cookies, extra_headers,
                                        scroll, bridge=True)
        except RenderError:
            raise
        except Exception as e:
            raise RenderError("render_failed",
                              f"{type(e).__name__}: {e}") from e

    def _render_cdp(self, url, cookies, extra_headers, scroll,
                    bridge=False):
        proc, tmp, port = self._launch()
        ws = None
        try:
            ws_url = self._new_page_ws(port)
            ws = _WS(ws_url, timeout=10)
            session = _CDPSession(ws)
            requests, responses = {}, {}
            doc_request_ids = []
            bridged, doc_fulfillments = [], []

            def bridge_fetch(req_url, req_method, req_headers, post_data):
                """桥接取数：本包静态传输层取回真实字节（不跟随重定向，
                重定向由浏览器按回填的 3xx 自行跟进，链条不丢）。"""
                from . import transport
                headers = {k: v for k, v in (req_headers or {}).items()
                           if k.lower() not in ("host", "content-length")}
                data = post_data.encode("utf-8") if post_data else None
                req = urllib.request.Request(
                    req_url, data=data, headers=headers,
                    method=req_method or "GET")
                try:
                    resp = transport._OPENER.open(
                        req, timeout=self.timeout)
                    return (resp.status, dict(resp.headers.items()),
                            resp.read())
                except urllib.error.HTTPError as e:
                    return (e.code,
                            dict(e.headers.items()) if e.headers else {},
                            e.read() if hasattr(e, "read") else b"")

            def on_event(method, params):
                if method == "Fetch.requestPaused":
                    rid = params.get("requestId")
                    req = params.get("request") or {}
                    rurl = req.get("url", "")
                    rtype = params.get("resourceType")
                    try:
                        status, rheaders, raw = bridge_fetch(
                            rurl, req.get("method", "GET"),
                            req.get("headers"), req.get("postData"))
                    except Exception:
                        session.send_only(
                            "Fetch.failRequest",
                            {"requestId": rid, "errorReason": "Failed"})
                        bridged.append({"url": rurl, "type": rtype,
                                        "status": None, "error": True})
                        return
                    bridged.append({"url": rurl, "type": rtype,
                                    "status": status})
                    if rtype == "Document":
                        doc_fulfillments.append(
                            {"url": rurl, "status": status})
                    out_headers = [
                        {"name": k, "value": v}
                        for k, v in rheaders.items()
                        if k.lower() not in ("content-length",
                                             "transfer-encoding",
                                             "connection")]
                    session.send_only("Fetch.fulfillRequest", {
                        "requestId": rid, "responseCode": status,
                        "responseHeaders": out_headers,
                        "body": base64.b64encode(raw).decode()})
                    return
                if method == "Network.requestWillBeSent":
                    rid = params.get("requestId")
                    requests[rid] = {
                        "url": params.get("request", {}).get("url"),
                        "type": params.get("type"),
                        "redirect_response": params.get("redirectResponse"),
                    }
                    if params.get("type") == "Document":
                        doc_request_ids.append(rid)
                elif method == "Network.responseReceived":
                    responses[params.get("requestId")] = {
                        "url": params.get("response", {}).get("url"),
                        "status": params.get("response", {}).get("status"),
                        "mime": params.get("response", {}).get("mimeType"),
                        "type": params.get("type"),
                    }

            session.on_event = on_event
            session.call("Network.enable")
            session.call("Page.enable")
            session.call("Network.setUserAgentOverride",
                         {"userAgent": self.user_agent})
            if extra_headers:
                session.call("Network.setExtraHTTPHeaders",
                             {"headers": extra_headers})
            for cookie in cookies:
                params = {"name": cookie["name"],
                          "value": cookie["value"], "url": url,
                          "path": cookie.get("path", "/")}
                for key in ("domain", "secure", "httpOnly", "expires"):
                    if cookie.get(key) is not None:
                        params[key] = cookie[key]
                result = session.call("Network.setCookie", params)
                if result and result.get("success") is False:
                    raise RenderError(
                        "credential_injection_failed",
                        f"cookie {cookie['name']} 注入被浏览器拒绝"
                        "（值不落盘、不回显）")
            if bridge:
                session.call("Fetch.enable", {
                    "patterns": [{"urlPattern": "*",
                                  "requestStage": "Request"}]})
            nav = session.call("Page.navigate", {"url": url})
            if nav.get("errorText"):
                if "LOCAL_NETWORK_ACCESS" in nav["errorText"] \
                        and not bridge:
                    raise RenderError(
                        "lna_blocked",
                        "导航被 Chrome 的 Local Network Access 检查拦截"
                        "（目标在本地/内网地址空间）；将自动转桥接模式")
                raise RenderError("navigate_failed",
                                  f"导航失败：{nav['errorText']}")
            # 等加载事件（其余时间留给滚动收割）
            load_deadline = time.monotonic() + self.timeout * 0.5
            while time.monotonic() < load_deadline:
                if any(m == "Page.loadEventFired"
                       for m, _ in session.events):
                    break
                session.pump(0.4)

            def evaluate(expr):
                out = session.call(
                    "Runtime.evaluate",
                    {"expression": expr, "returnByValue": True})
                result = out.get("result") or {}
                if out.get("exceptionDetails"):
                    raise RenderError("evaluate_failed",
                                      str(out["exceptionDetails"])[:200])
                return result.get("value")

            if scroll:
                last_mark = None
                stable = 0
                for _ in range(self.max_scrolls):
                    evaluate("window.scrollTo(0, "
                             "document.body ? document.body.scrollHeight"
                             " : 0)")
                    session.pump(SCROLL_SETTLE_SEC)
                    mark = evaluate(
                        "(document.documentElement.outerHTML.length)"
                        " + ':' + (document.body"
                        " ? document.body.scrollHeight : 0)")
                    if mark == last_mark:
                        stable += 1
                        if stable >= 2:
                            break
                    else:
                        stable = 0
                    last_mark = mark
            dom = evaluate("document.documentElement.outerHTML") or ""
            final_url = evaluate("location.href") or url

            status, chain = None, []
            for rid in doc_request_ids:
                resp = responses.get(rid)
                if resp and resp.get("status") is not None:
                    status = resp["status"]
                rr = requests.get(rid, {}).get("redirect_response")
                if rr:
                    chain.append({"url": rr.get("url"),
                                  "status": rr.get("status")})
            resources = [
                {"url": r["url"], "type": r.get("type"),
                 "status": r.get("status"), "mime": r.get("mime")}
                for r in responses.values()]
            status_basis = ("network" if status is not None
                            else "cdp_no_document_response")
            if bridge:
                if status is None and doc_fulfillments:
                    status = doc_fulfillments[-1]["status"]
                    status_basis = "transport_bridge"
                if not resources:
                    resources = bridged
                for f in doc_fulfillments[:-1]:
                    if f["status"] in (301, 302, 303, 307, 308):
                        chain.append({"url": f["url"],
                                      "status": f["status"]})
            challenge = detect_challenge(dom)
            return RenderedPage(
                url=url, final_url=final_url, status=status, dom=dom,
                resources=resources, redirect_chain=chain,
                engine="cdp+fetch-bridge" if bridge else "cdp",
                blocked=challenge["blocked"],
                challenge_suspected=challenge["suspected"],
                login_required=detect_login_required(final_url, dom),
                status_basis=status_basis)
        finally:
            if ws is not None:
                ws.close()
            self._cleanup(proc, tmp)

    # ---- 降级通道

    def render_dump_dom(self, url) -> RenderedPage:
        """dump-dom 降级：只有渲染 DOM，状态/资源如实标注不可得。"""
        if not self.available():
            raise RenderError("chromium_missing", "未找到 Chromium")
        args = [self.executable, "--headless=new", "--no-sandbox",
                "--disable-gpu", "--disable-dev-shm-usage",
                "--virtual-time-budget=12000",
                "--dump-dom", url]
        try:
            done = subprocess.run(
                args, capture_output=True, timeout=self.timeout + 20)
        except subprocess.TimeoutExpired as e:
            raise RenderError("dump_dom_timeout",
                              f"dump-dom 超时（{self.timeout + 20}s）") from e
        dom = done.stdout.decode("utf-8", errors="replace")
        if not dom.strip():
            raise RenderError("dump_dom_empty", "dump-dom 无输出")
        if "chrome-error://" in dom:
            raise RenderError(
                "target_unreachable",
                "浏览器落到 Chrome 错误页（目标不可达或导航失败），"
                "不把错误页当内容")
        challenge = detect_challenge(dom)
        return RenderedPage(
            url=url, final_url=url, status=None, dom=dom, resources=[],
            redirect_chain=[], engine="dump-dom",
            blocked=challenge["blocked"],
            challenge_suspected=challenge["suspected"],
            login_required=detect_login_required(url, dom),
            status_basis="dump_dom_unavailable")


def render_with_fallback(renderer: ChromiumRenderer, url, **kw) -> RenderedPage:
    """CDP 失败时降级 dump-dom 并在 engine 字段如实标注降级来源。"""
    try:
        return renderer.render(url, **kw)
    except RenderError as e:
        if e.kind in ("chromium_missing",):
            raise
        page = renderer.render_dump_dom(url)
        page.status_basis = f"dump_dom_after_cdp_failure:{e.kind}"
        return page
