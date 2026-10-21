"""Obsidian Local REST API 适配器（工具层 T3 增强面二，TOOLING-PLAN §5.1）。

社区插件 Local REST API（coddingtonbear，MIT，本批契约基准为
v5.5.2 本地克隆的 README 与 OpenAPI 一手形态）：在 Obsidian 内起
回环 HTTPS 服务（默认 https://127.0.0.1:27124），是唯一带段落级
寻址与乐观并发的面——按标题路径 PATCH、按 frontmatter 字段打
JSON 指令补丁，全部写操作支持 ETag If-Match 条件写（不符 412
且不落盘），If-None-Match 可做「仅不存在时创建」。

定位与纪律：
- **可选增强，默认禁用**：密钥登记后才启用，Memory 任何命令
  不依赖它。启用条件三件齐备：用户自愿装插件、Obsidian 运行中、
  密钥经环境变量登记（见下）。缺任一，探测即点名降级走文件层。
- **密钥纪律**（与 index.py 的 api_key_env 口径同构）：密钥只从
  环境变量 LIGHT_MEMORY_OBSIDIAN_REST_KEY 在每次请求时现读，
  不存进对象、不落盘、不进回执/报错/日志；回执只记方法、路径、
  状态码与 ETag。测试以工作区扫描 + 回执扫描双断言钉死。
- **读写分开授权**：只读探测（GET /）只需密钥在场；写方法须
  allow_write=True 显式开启，未开启时在发请求之前即拒并点名。
- **只许回环**：base URL 主机须为 127.0.0.1 / localhost / ::1，
  其余地址在构造期即拒（该插件本就只在本机起服务）。
- **条件写语义**：412 一律抛 RestError 点名（含服务端给出的
  当前版本信息），不自动重试、不降级成无条件写——版本冲突是
  并发事实，须回文件层或人工对账后重走先读后写。
- 验证等级：契约以本地桩 HTTP 服务器验到方法/路径/头/ETag/
  412/错误形态一级，属**桩级**；真实插件走自签 CA 的 HTTPS，
  TLS 一端未在实机验，`obsidian_live_verified` 不因此置真。
  传输可注入（transport 协议见 _default_transport），默认传输
  在登记了 CA 路径（LIGHT_MEMORY_OBSIDIAN_REST_CA）时按该 CA
  校验证书，未登记时为回环自签口径（仅限回环主机，回执点名）。
"""

from __future__ import annotations

import json
import os
import ssl
import urllib.error
import urllib.parse
import urllib.request

SURFACE = "local-rest-api"
PLUGIN_BASELINE = "5.5.2"
DEFAULT_BASE_URL = "https://127.0.0.1:27124"
KEY_ENV = "LIGHT_MEMORY_OBSIDIAN_REST_KEY"
URL_ENV = "LIGHT_MEMORY_OBSIDIAN_REST_URL"
CA_ENV = "LIGHT_MEMORY_OBSIDIAN_REST_CA"
FALLBACK = "file-layer"
DEFAULT_TIMEOUT = 10.0
_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}

_MISSING = object()


class RestError(Exception):
    def __init__(self, gaps, status=None, error_code=None):
        self.gaps = list(gaps)
        self.status = status
        self.error_code = error_code
        super().__init__("；".join(self.gaps))


# ---------------------------------------------------------------- 传输

def _default_transport(ca_path=None):
    """urllib 传输：ca_path 在场按 CA 校验，否则回环自签口径。

    返回 transport(method, url, headers, body, timeout) ->
    (status, headers, body_bytes)；HTTP 错误状态不抛、原样返回
    状态码与响应体（错误形态解析归客户端）；连接层失败抛
    ConnectionError 供客户端点名。
    """
    if ca_path:
        ctx = ssl.create_default_context(cafile=ca_path)
        tls_mode = "ca-verified"
    else:
        ctx = ssl._create_unverified_context()
        tls_mode = "unverified-loopback"

    def _send(method, url, headers, body, timeout):
        req = urllib.request.Request(url, data=body, method=method,
                                     headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout,
                                        context=ctx) as resp:
                return resp.status, dict(resp.headers), resp.read()
        except urllib.error.HTTPError as exc:
            return exc.code, dict(exc.headers or {}), exc.read()
        except (urllib.error.URLError, OSError) as exc:
            raise ConnectionError(str(exc)) from exc

    _send.tls_mode = tls_mode
    return _send


def _quote_path(path: str) -> str:
    """vault 内路径逐段百分号编码（段内 / 不编码）。"""
    return "/".join(urllib.parse.quote(seg, safe="")
                    for seg in path.strip("/").split("/") if seg)


# ---------------------------------------------------------------- 客户端

class RestClient:
    """Local REST API 客户端：密钥现读现用，写须显式授权。"""

    def __init__(self, base_url=None, key_env=KEY_ENV,
                 allow_write=False, transport=None,
                 timeout=DEFAULT_TIMEOUT, environ=None):
        env = os.environ if environ is None else environ
        base = base_url or env.get(URL_ENV) or DEFAULT_BASE_URL
        parsed = urllib.parse.urlparse(base)
        if parsed.hostname not in _LOOPBACK_HOSTS:
            raise RestError([
                f"REST base URL 只许回环地址（127.0.0.1/localhost），"
                f"拒绝：{base}"])
        self.base_url = base.rstrip("/")
        self.key_env = key_env
        self.allow_write = allow_write
        self.timeout = timeout
        self._environ = env
        self._transport_owned = transport is None
        if transport is None:
            transport = _default_transport(env.get(CA_ENV) or None)
        self._transport = transport
        self.tls_mode = getattr(transport, "tls_mode",
                                "injected-transport")

    # -- 密钥与启用 ------------------------------------------------

    def _key(self):
        return self._environ.get(self.key_env) or None

    @property
    def enabled(self) -> bool:
        """启用 = 密钥已登记（装插件与应用运行由探测另行核）。"""
        return self._key() is not None

    # -- 请求骨架 --------------------------------------------------

    def _request(self, method, path_q, body=None, headers=None,
                 write=False, expect=(200, 201, 204)):
        if not self.enabled:
            raise RestError([
                f"REST 适配未启用：环境变量 {self.key_env} 未设置"
                "（密钥由用户登记到环境/保管库后才启用；密钥不许"
                "写进任何文件），活面降级走文件层"])
        if write and not self.allow_write:
            raise RestError([
                "REST 写入未授权：allow_write=False（只读探测与"
                "写入分开授权，TOOLING-PLAN §5.1）——本次未发出"
                "任何请求"])
        url = self.base_url + path_q
        hdrs = {"Authorization": f"Bearer {self._key()}"}
        if headers:
            hdrs.update(headers)
        try:
            status, resp_headers, resp_body = self._transport(
                method, url, hdrs, body, self.timeout)
        except ConnectionError as exc:
            raise RestError([
                f"REST 连接失败（{method} {path_q}）：{exc}"
                "（Obsidian 未运行或 Local REST API 插件未启用时"
                "为此形态），活面降级走文件层"])
        resp_headers = {str(k).lower(): v for k, v in
                        (resp_headers or {}).items()}
        if status not in expect:
            raise self._error_from(status, resp_body, method, path_q)
        receipt = {"surface": SURFACE, "method": method,
                   "path": path_q, "status": status,
                   "tls": self.tls_mode}
        if resp_headers.get("etag"):
            receipt["etag"] = resp_headers["etag"]
        return status, resp_headers, resp_body, receipt

    @staticmethod
    def _error_from(status, body, method, path_q):
        """错误形态：插件错误体为 JSON {errorCode, message}。"""
        code, message = None, ""
        try:
            data = json.loads((body or b"").decode("utf-8"))
            if isinstance(data, dict):
                code = data.get("errorCode")
                message = str(data.get("message") or "")
        except (ValueError, UnicodeDecodeError):
            message = ""
        if status == 412:
            return RestError([
                f"REST 条件写被拒（412，{method} {path_q}）：文件"
                f"版本已变，本次未落盘。服务端信息：{message}"
                "——须先 GET 取当前 ETag 再重试，不许降级成"
                "无条件写"], status=412, error_code=code)
        if status == 401:
            return RestError([
                "REST 鉴权失败（401）：密钥与插件登记不一致或"
                "未登记"], status=401, error_code=code)
        if status == 404:
            return RestError([
                f"REST 目标不存在（404，{method} {path_q}）："
                f"{message}"], status=404, error_code=code)
        return RestError([
            f"REST 请求失败（{status}，{method} {path_q}）："
            f"{message or '无错误信息'}"], status=status,
            error_code=code)

    # -- 只读操作 --------------------------------------------------

    def server_status(self):
        """GET /：服务状态（status/authenticated/state 段）。"""
        _, _, body, receipt = self._request("GET", "/")
        try:
            data = json.loads(body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            data = {}
        return {"status": data.get("status"),
                "authenticated": data.get("authenticated"),
                "state": data.get("state"), "receipt": receipt}

    def list_files(self, dirpath=""):
        """GET /vault/{dir}/：目录内文件清单。"""
        path_q = "/vault/" + (_quote_path(dirpath) + "/"
                              if dirpath else "")
        _, _, body, receipt = self._request("GET", path_q)
        data = json.loads(body.decode("utf-8"))
        return {"files": data.get("files", []), "receipt": receipt}

    def get_note(self, path):
        """GET /vault/{path}：整篇正文 + 当前 ETag（版本令牌）。"""
        _, headers, body, receipt = self._request(
            "GET", "/vault/" + _quote_path(path))
        return {"text": body.decode("utf-8"),
                "etag": headers.get("etag"), "receipt": receipt}

    def search_simple(self, query, max_results=None):
        """POST /search/simple/：全文检索（文件名 + 上下文片段）。"""
        q = urllib.parse.urlencode(
            {"query": query, **({"maxResults": max_results}
                                 if max_results else {})})
        _, _, body, receipt = self._request(
            "POST", f"/search/simple/?{q}")
        return {"results": json.loads(body.decode("utf-8")),
                "receipt": receipt}

    # -- 写操作（须 allow_write） -----------------------------------

    def put_note(self, path, content, if_match=None, create_only=False):
        """PUT 整篇写入：if_match 给当前 ETag 做条件写；
        create_only=True 走 If-None-Match: *（已存在即 412）。"""
        headers = {"Content-Type": "text/markdown"}
        if if_match:
            headers["If-Match"] = if_match
        if create_only:
            headers["If-None-Match"] = "*"
        _, _, _, receipt = self._request(
            "PUT", "/vault/" + _quote_path(path),
            body=content.encode("utf-8"), headers=headers, write=True)
        return {"etag": receipt.get("etag"), "receipt": receipt}

    def append_note(self, path, content):
        """POST 追加到文末。"""
        _, _, _, receipt = self._request(
            "POST", "/vault/" + _quote_path(path),
            body=content.encode("utf-8"),
            headers={"Content-Type": "text/markdown"}, write=True)
        return {"etag": receipt.get("etag"), "receipt": receipt}

    def patch(self, path, instruction, if_match=None):
        """PATCH 段落指令：instruction 为插件 JSON 指令（见
        patch_heading / patch_frontmatter 两封装）。"""
        headers = {"Content-Type": "application/json"}
        if if_match:
            headers["If-Match"] = if_match
        body = json.dumps(instruction, ensure_ascii=False) \
            .encode("utf-8")
        _, resp_headers, _, receipt = self._request(
            "PATCH", "/vault/" + _quote_path(path), body=body,
            headers=headers, write=True)
        warnings = resp_headers.get("markdown-patch-warnings")
        return {"etag": receipt.get("etag"),
                "warnings": warnings, "receipt": receipt}

    def patch_heading(self, path, heading_path, operation,
                      content=None, if_match=None):
        """按标题路径 PATCH：heading_path 为自顶层起的标题序列，
        operation 取 replace / append / prepend / delete。"""
        if operation not in ("replace", "append", "prepend",
                             "delete"):
            raise RestError([f"PATCH operation 非法：{operation}"])
        instruction = {"targetType": "heading",
                       "target": list(heading_path),
                       "operation": operation}
        if content is not None:
            instruction["content"] = content
        return self.patch(path, instruction, if_match=if_match)

    def patch_frontmatter(self, path, key, operation, value=_MISSING,
                          if_match=None):
        """按 frontmatter 字段 PATCH：value 以 JSON 原生类型传递。"""
        if operation not in ("replace", "append", "prepend",
                             "delete"):
            raise RestError([f"PATCH operation 非法：{operation}"])
        instruction = {"targetType": "frontmatter", "target": key,
                       "operation": operation}
        if value is not _MISSING:
            instruction["value"] = value
        return self.patch(path, instruction, if_match=if_match)

    def delete_note(self, path, if_match=None):
        headers = {}
        if if_match:
            headers["If-Match"] = if_match
        _, _, _, receipt = self._request(
            "DELETE", "/vault/" + _quote_path(path),
            headers=headers, write=True)
        return {"receipt": receipt}


# ---------------------------------------------------------------- 探测

def probe_rest(client=None, **client_kwargs):
    """探测 REST 面：未登记密钥 / 连不上 / 鉴权不过 / 可用，四形态
    全部点名，永不抛错。verified 恒 False（桩级契约未算实机验）。"""
    base = {"surface": SURFACE, "fallback": FALLBACK,
            "verified": False, "plugin_baseline": PLUGIN_BASELINE}
    if client is None:
        try:
            client = RestClient(**client_kwargs)
        except RestError as exc:
            return {**base, "status": "error", "reason": exc.gaps[0]}
    if not client.enabled:
        return {**base, "status": "disabled",
                "reason": f"环境变量 {client.key_env} 未设置：REST"
                          " 面默认禁用（用户登记密钥后才启用），"
                          "降级走文件层"}
    try:
        status = client.server_status()
    except RestError as exc:
        return {**base, "status": "unreachable",
                "reason": exc.gaps[0]}
    if status.get("status") != "OK":
        return {**base, "status": "error",
                "reason": f"服务状态异常：{status.get('status')!r}"}
    if not status.get("authenticated"):
        return {**base, "status": "unauthenticated",
                "reason": "服务在答但未通过鉴权：密钥与插件登记"
                          "不一致"}
    return {**base, "status": "available",
            "server_status": status.get("status")}
