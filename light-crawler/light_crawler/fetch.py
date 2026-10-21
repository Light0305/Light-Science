"""guard 与获取执行（C2）+ 人工导入（S2 替代）+ 对外预检门接口。

guard 纪律（HC-1，学 reverse-skill 的 case-guard 形态）：fetch 启动
前逐项校验登记、预检生效与新鲜度、熔断状态、通道可执行性，缺项
逐项点名退出；本包不设任何绕过旗标（force 不绕硬门——干脆不给）。
获取执行：通道优先级已在登记/预检层裁决，这里只按裁决执行；
被拒即停（HC-8）、越域即停（HC-7）、量上限即停，全程落事件。
"""

from __future__ import annotations

import time
from pathlib import Path
from urllib.parse import urlparse

from . import precheck as precheck_mod
from . import project, robots, schema, storage
from .throttle import Throttler, parse_retry_after
from .util import dump_yaml, load_yaml, today, utcnow


class Refusal(Exception):
    """guard 或执行层的拒绝：reasons 逐项点名，CLI 原样呈现。"""

    def __init__(self, reasons):
        self.reasons = list(reasons)
        super().__init__("；".join(self.reasons))


# ---------------------------------------------------------------- 传输层

class Response:
    def __init__(self, status, headers, body, final_url):
        self.status = status
        self.headers = headers or {}
        self.body = body or b""
        self.final_url = final_url
        #: 重定向链（transport v2 起逐跳记录；注入的 fake 传输可不带）
        self.redirect_chain = []
        #: 渲染信息（浏览器通道产物才有：engine/状态依据/资源数等）
        self.render_info = None


def http_get(url, headers=None, timeout=30.0) -> Response:
    """默认 HTTP 传输（transport v2）：手动重定向链、解压、逐跳记录。

    HTTP 状态不抛错、原样返回；网络层错误抛 TransportError 给调用
    方按失败口径处理。重定向超限/成环抛错，绝不把 3xx 空 body
    当成功内容（v1 的静默落垃圾行为已消除）。
    """
    from . import transport
    result = transport.fetch(url, headers=headers, timeout=timeout)
    resp = Response(result.status, result.headers, result.body,
                    result.final_url)
    resp.redirect_chain = result.redirect_chain
    return resp


# ---------------------------------------------------------------- gate 接口

def gate_check(root, target_id) -> dict:
    """对外预检门接口（供 light-patent 等包按契约查询；只读、无副作用）。

    典型用途：patent 的 CNIPA 公布站自动化默认关，开启前先在本包
    登记目标并过预检，再经本接口查 ready —— ready 为假时给出的
    reasons 即点名清单。接口形态在本包定版，消费方只读不改。
    """
    out = {"target_id": target_id, "ready": False, "status": "unknown",
           "reasons": [], "channel": None, "effective_interval_sec": None,
           "precheck_id": None}
    try:
        reg = project.load_target(root, target_id)
    except project.WorkspaceError as e:
        out["status"] = "unregistered"
        out["reasons"] = e.problems
        return out
    out["channel"] = reg.get("channel")
    state = project.load_state(root, target_id)
    if state.get("circuit_broken"):
        out["status"] = "circuit_broken"
        out["reasons"] = [f"目标已熔断：{state.get('circuit_reason')}；"
                          "须具名 unblock 留痕后才恢复"]
        return out
    cur = precheck_mod.current_precheck(root, target_id)
    out["status"] = cur["status"]
    rec = cur["record"]
    if rec:
        out["precheck_id"] = rec["precheck_id"]
        rate = (rec.get("checks") or {}).get("rate") or {}
        out["effective_interval_sec"] = rate.get("effective_interval_sec")
    if cur["status"] == "effective":
        out["ready"] = True
    elif cur["status"] == "none":
        out["reasons"] = ["尚无预检记录：先跑 precheck"]
    elif cur["status"] == "pending_confirmation":
        out["reasons"] = ["高危通道预检待具名人工确认（S4）：confirm 后生效"]
    elif cur["status"] == "blocked":
        out["reasons"] = list(rec.get("blocked_reasons") or [])
    elif cur["status"] == "incomplete":
        out["reasons"] = [f"缺项：{m}" for m in (rec.get("missing") or [])]
    elif cur["status"] == "expired":
        out["reasons"] = ["预检已过期（robots 缓存 24 小时上限，RFC 9309 "
                          "第 2.4 节口径）：重跑 precheck"]
    return out


def guard_check(root, target_id) -> dict:
    """fetch 前的硬门：不通过抛 Refusal（逐项点名 + 合法替代指针）。"""
    verdict = gate_check(root, target_id)
    if not verdict["ready"]:
        reasons = verdict["reasons"] or [f"预检状态 {verdict['status']}"]
        reasons.append(
            "合法替代：改走官方 API 通道重新登记，或人工获取后用 "
            "import 登记导入（预检门不设绕过旗标）")
        project.append_event(root, "fetch_refused", target_id=target_id,
                             detail="guard 拒绝：" + "；".join(reasons),
                             data={"gate_status": verdict["status"]})
        raise Refusal(reasons)
    reg = project.load_target(root, target_id)
    record = precheck_mod.current_precheck(root, target_id)["record"]
    return {"reg": reg, "verdict": verdict, "record": record}


# ---------------------------------------------------------------- 凭据会话与内置浏览器执行器

def resolve_session(root, target_id, reg, credential_provider):
    """凭据访问通道的会话解析（非凭据目标返回 None）。

    credential_provider(credential_ref) 由接入运行环境注入（凭据
    本体在 Secure Vault 里），返回 {"cookies": [...], "headers":
    {...}, "account_label": "脱敏账号标识"}。provider 缺失或返回
    空会话一律 Refusal 并落事件：凭据通道宁可不开，不许裸奔。
    凭据值只在 provider 返回值与浏览器进程之间流转，本包任何
    落盘产物只记 cookie 名、权限依据与脱敏账号标识。
    """
    login = reg.get("login_state") or "none"
    if login == "none":
        return None
    if credential_provider is None:
        reason = (f"目标 {target_id} 为凭据访问通道（login_state="
                  f"{login}），但本次运行未注入 credential_provider："
                  "凭据只经接入运行环境从 Secure Vault 注入，本包与 "
                  "CLI 不持有凭据；注入后重跑，或改走 import 人工导入")
        project.append_event(root, "fetch_refused", target_id=target_id,
                             detail=reason, data={"channel": "browser",
                                                  "login_state": login})
        raise Refusal([reason])
    try:
        session = credential_provider(reg.get("credential_ref"))
    except Exception as e:
        reason = (f"credential_provider 解析 {reg.get('credential_ref')} "
                  f"失败：{type(e).__name__}（凭据值不回显）")
        project.append_event(root, "fetch_refused", target_id=target_id,
                             detail=reason, data={"login_state": login})
        raise Refusal([reason]) from e
    if not session or not (session.get("cookies")
                            or session.get("headers")):
        reason = ("credential_provider 未返回可用会话（cookies/headers "
                  "皆空）：凭据可能已失效或 vault 引用不存在")
        project.append_event(root, "fetch_refused", target_id=target_id,
                             detail=reason, data={"login_state": login})
        raise Refusal([reason])
    return session


class _BuiltinBrowserFetcher:
    """随包浏览器执行器的 fetch 适配器（CLI 与 crawl 注入用）。

    库层 fetch_run 的 browser_fetcher 注入契约不变（v1 口径）；
    本适配器把 ChromiumRenderer 的渲染产物转成 Response，并把
    人机校验 blocked 映射为 403、凭据会话失效映射为 401，接入
    既有 HC-8 熔断记账。渲染细节（engine、状态依据、资源数、
    cookie 名、脱敏账号标识）经 render_info 进 provenance。
    """

    def __init__(self, renderer=None):
        self.renderer = renderer
        self.session = None

    def set_session(self, session) -> None:
        self.session = session

    def __call__(self, url, headers):
        from . import browser as browser_mod
        renderer = self.renderer or browser_mod.ChromiumRenderer()
        if not renderer.available():
            raise Refusal([
                "浏览器通道预检门已齐备，但本机未找到 Chromium 可执行"
                "文件：请安装 Chromium 或经 LIGHT_CRAWLER_CHROMIUM "
                "指明路径，或改走人工导出 + import 登记导入"])
        cookies = (self.session or {}).get("cookies") or []
        extra = dict((self.session or {}).get("headers") or {})
        page = browser_mod.render_with_fallback(
            renderer, url, cookies=cookies, extra_headers=extra)
        info = {"engine": page.engine,
                "status_basis": page.status_basis,
                "resources": len(page.resources),
                "cookie_names": [c.get("name") for c in cookies],
                "account_label": (self.session or {}).get(
                    "account_label")}
        if page.blocked:
            info["blocked"] = page.blocked
        if page.login_required:
            info["login_required"] = True
        status = page.status
        if page.blocked:
            status = 403
        elif page.login_required and self.session:
            status = 401
        elif status is None:
            status = 200
            info["status_estimated"] = True
        resp = Response(status, {"Content-Type": "text/html; charset=utf-8"},
                        page.body, page.final_url)
        resp.redirect_chain = page.redirect_chain
        resp.render_info = info
        return resp


def make_builtin_browser_fetcher(renderer=None) -> _BuiltinBrowserFetcher:
    return _BuiltinBrowserFetcher(renderer=renderer)


def note_render_refusal(root, target_id, run_id, url, resp, session,
                        reg) -> str:
    """渲染类回绝的专项留痕：人机校验 blocked 与凭据会话失效各落
    一条专项事件，返回供 http_refused detail 拼接的附加说明。
    fetch_run 与 crawl_run 共用，回绝口径不许两处漂移。"""
    render_info = getattr(resp, "render_info", None) or {}
    extra = ""
    if render_info.get("blocked"):
        project.append_event(
            root, "render_blocked", target_id=target_id,
            detail=f"{url} 渲染命中人机校验强标记 "
                   f"{render_info['blocked'].get('markers')}："
                   "本包不代解验证码，按回绝处理（HC-8 同口径）",
            data={"run_id": run_id, "url": url,
                  "markers": render_info["blocked"].get("markers")})
        extra += "；渲染命中人机校验（render_blocked 已另记）"
    if render_info.get("login_required") and session:
        project.append_event(
            root, "credential_session_invalid", target_id=target_id,
            detail=f"{url} 凭据会话失效（落到登录墙）：权限依据 "
                   f"{reg.get('entitlement_basis')}；按被拒口径熔断"
                   "记账，凭据值不落盘",
            data={"run_id": run_id, "url": url,
                  "entitlement_basis": reg.get("entitlement_basis")})
        extra += "；凭据会话失效（已另记）"
    return extra


def note_run_outcome(root, target_id, run_id, refused: bool,
                     stored_any: bool) -> None:
    """run 结束后的熔断记账（HC-8）：被拒累计、成功清零、达阈熔断。

    fetch_run 与 crawl_run 共用同一份记账，口径不许两处漂移。
    """
    state = project.load_state(root, target_id)
    if refused:
        state["consecutive_refusals"] = int(
            state.get("consecutive_refusals") or 0) + 1
        if state["consecutive_refusals"] >= schema.CIRCUIT_BREAK_THRESHOLD \
                and not state.get("circuit_broken"):
            state["circuit_broken"] = True
            state["circuit_reason"] = (
                f"连续 {state['consecutive_refusals']} 个 run 被目标回绝"
                f"（最近 {run_id}）")
            project.append_event(
                root, "circuit_broken", target_id=target_id,
                detail=state["circuit_reason"] + "；guard 将拒绝一切 fetch，"
                       "须具名 unblock 留痕才恢复",
                data={"run_id": run_id})
    elif stored_any:
        state["consecutive_refusals"] = 0
    project.save_state(root, state)
    project.refresh_status(root)


# ---------------------------------------------------------------- 获取

def _same_host(a: str, b: str) -> bool:
    pa, pb = urlparse(a), urlparse(b)
    return (pa.scheme, pa.netloc) == (pb.scheme, pb.netloc)


def _large_download(run_dir, fp, url, headers):
    """大文件断点续传取数（仅默认传输可用；.part 落在 run 目录内）。"""
    from . import transport as transport_mod
    part = Path(run_dir) / "downloads" / f"{fp[:16]}.part"
    info = transport_mod.download_resumable(
        url, part, headers=headers, raise_on_status=False)
    body = b""
    if info["status"] in (200, 206, 416) and part.exists():
        body = part.read_bytes()
    resp = Response(info["status"], info.get("headers") or {}, body,
                    info.get("final_url") or url)
    return resp, info


def _emit_adaptation(root, target_id, run_id, throttler, before):
    if throttler.interval != before and throttler.adaptations:
        kind, old, new = throttler.adaptations[-1]
        project.append_event(
            root, "adaptive_backoff", target_id=target_id,
            detail=f"自适应限速：间隔 {old}s -> {new}s（触发 {kind}；"
                   "基线为预检裁决值，只加严或向其回落，永不越界）",
            data={"run_id": run_id, "kind": kind})


def fetch_run(root, target_id, urls=None, transport=None, sleep=None,
              browser_fetcher=None, refetch_seen=False,
              credential_provider=None) -> dict:
    """执行一次采集 run。返回 run 摘要 dict。

    transport / sleep / browser_fetcher 可注入（测试与外部浏览器
    工具接入点）；生产默认 transport 为 transport v2、sleep 为真睡。
    credential_provider 为凭据访问通道的会话注入点（见 resolve_session）。
    """
    ctx = guard_check(root, target_id)
    reg, channel = ctx["reg"], ctx["reg"].get("channel")
    transport = transport or http_get
    transport_is_default = transport is http_get

    if channel == "browser" and browser_fetcher is None:
        reason = ("浏览器通道的预检门已齐备，但执行器不随包提供默认"
                  "实例：库层须由调用方注入 browser_fetcher（CLI 已接"
                  "随包 Chromium 执行器，或登记在案的外部浏览器工具），"
                  "或改走人工导出 + import 登记导入")
        project.append_event(root, "fetch_refused", target_id=target_id,
                             detail=reason, data={"channel": "browser"})
        raise Refusal([reason])

    session = None
    if (reg.get("login_state") or "none") != "none":
        session = resolve_session(root, target_id, reg,
                                  credential_provider)
        if not hasattr(browser_fetcher, "set_session"):
            reason = ("凭据会话只能由支持 set_session 的浏览器执行器"
                      "承载（随包 _BuiltinBrowserFetcher）；当前注入的 "
                      "browser_fetcher 无会话承载面，拒绝裸奔")
            project.append_event(root, "fetch_refused", target_id=target_id,
                                 detail=reason, data={"channel": "browser"})
            raise Refusal([reason])
        browser_fetcher.set_session(session)

    rate = (ctx["record"].get("checks") or {}).get("rate") or {}
    max_run = rate.get("max_requests_per_run",
                       schema.DEFAULT_MAX_REQUESTS_PER_RUN)
    max_day = rate.get("max_requests_per_day",
                       schema.DEFAULT_MAX_REQUESTS_PER_DAY)
    interval = rate.get("effective_interval_sec") or schema.TEMPLATE_MIN_INTERVAL_SEC[
        channel]

    run_id = project.new_run_id(target_id)
    project.acquire_run_lock(root, target_id, run_id)
    run_dir = Path(root) / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "cleaned").mkdir(exist_ok=True)
    run_rec = {
        "run_id": run_id, "target_id": target_id, "channel": channel,
        "status": "running", "started_at": utcnow(),
        "precheck_id": ctx["record"]["precheck_id"],
        "run_config_hash": ctx["record"].get("run_config_hash"),
        "requested": 0, "stored": 0, "not_modified": 0, "duplicates": 0,
        "near_duplicates": 0,
        "errors": [], "refused": False,
    }
    # 留存档位与近重配置在 run 启动时按登记定版（中途改登记不影响
    # 在飞 run 的口径，run_config_hash 已把登记纳入哈希）。
    tier = schema.effective_retention_tier(reg)
    warc_archive = None
    warc_rel = None
    dump_yaml(run_dir / "run.yaml", run_rec)
    project.append_event(root, "fetch_run_started", target_id=target_id,
                         detail=f"{run_id} 启动（通道 {channel}）",
                         data={"run_id": run_id})

    state = project.load_state(root, target_id)
    throttler = Throttler(interval, sleep=sleep or time.sleep)
    seen = storage.load_seen(root)
    prior_texts = []
    today_count = sum(
        1 for r in storage.read_provenance(root)
        if r.get("kind") == "fetch" and r.get("target_id") == target_id
        and (r.get("at") or "").startswith(today()))

    url_list = list(urls) if urls else [reg["base_url"]]
    # fetch 期 robots 复核（逐 URL；不可达即整 run 失败关闭）。
    # D8：取用先走预检 24h 缓存（哈希比对），命中零额外请求；
    # 缓存损坏作废后回落实时取，两条路径都落事件可查。
    robots_fetch, robots_src = robots.resolve_robots(
        root, reg["base_url"], record=ctx["record"])
    if robots_src["source"] == "precheck_cache":
        project.append_event(
            root, "robots_cache_reused", target_id=target_id,
            detail="fetch 期复用预检 robots 缓存（24h 内、原文哈希相符，"
                   "本次未再请求 robots.txt，D8）",
            data={"run_id": run_id, "precheck_id": robots_src["precheck_id"],
                  "body_sha256": robots_src.get("body_sha256")})
    elif robots_src.get("cache_invalidated"):
        project.append_event(
            root, "robots_cache_invalidated", target_id=target_id,
            detail=f"预检 robots 缓存作废（{robots_src['cache_invalidated']}），"
                   "fetch 期已回落实时取用（D8）",
            data={"run_id": run_id,
                  "precheck_id": robots_src["precheck_id"],
                  "reason": robots_src["cache_invalidated"]})
    try:
        for url in url_list:
            if run_rec["requested"] >= max_run:
                project.append_event(
                    root, "volume_cap_hit", target_id=target_id,
                    detail=f"单 run 请求上限 {max_run} 已达，余下 URL 未请求",
                    data={"run_id": run_id, "cap": "max_requests_per_run"})
                break
            if today_count + run_rec["requested"] >= max_day:
                project.append_event(
                    root, "volume_cap_hit", target_id=target_id,
                    detail=f"单目标日上限 {max_day} 已达",
                    data={"run_id": run_id, "cap": "max_requests_per_day"})
                break
            if not _same_host(url, reg["base_url"]):
                project.append_event(
                    root, "fetch_refused", target_id=target_id,
                    detail=f"URL {url} 不在登记域名内，拒绝请求",
                    data={"run_id": run_id, "url": url})
                run_rec["errors"].append(f"{url}: 不在登记域名内")
                continue
            verdict = robots.check_url(robots_fetch, url)
            if not verdict["allowed"]:
                project.append_event(
                    root, "fetch_refused", target_id=target_id,
                    detail=f"fetch 期 robots 复核禁止 {url}：{verdict['detail']}",
                    data={"run_id": run_id, "url": url})
                run_rec["errors"].append(f"{url}: robots 禁止（fetch 期复核）")
                if robots_fetch.outcome == "unreachable":
                    run_rec["errors"].append("robots 不可达，整 run 失败关闭")
                    break
                continue

            fp = storage.fingerprint("GET", url)
            prior_seen = seen.get(fp)
            if prior_seen and not refetch_seen:
                project.append_event(
                    root, "duplicate_skipped", target_id=target_id,
                    detail=f"{url} 请求指纹已见，跳过（增量口径）",
                    data={"run_id": run_id, "url": url})
                run_rec["duplicates"] += 1
                continue

            headers = {"User-Agent": schema.USER_AGENT}
            if prior_seen:
                if prior_seen.get("etag"):
                    headers["If-None-Match"] = prior_seen["etag"]
                if prior_seen.get("last_modified"):
                    headers["If-Modified-Since"] = prior_seen["last_modified"]

            throttler.wait()
            run_rec["requested"] += 1
            interval_before = throttler.interval
            dl_info = None
            try:
                if channel == "browser":
                    resp = browser_fetcher(url, headers)
                elif reg.get("large_files") and transport_is_default:
                    resp, dl_info = _large_download(run_dir, fp, url,
                                                    headers)
                else:
                    resp = transport(url, headers=headers)
            except Refusal:
                raise
            except Exception as e:
                # 传输层失败（超时/断连/重定向环）：单 URL 记账、
                # 自适应加严、不停 run（与 HTTP 回绝的熔断口径分开）
                throttler.note_outcome("network_error")
                _emit_adaptation(root, target_id, run_id, throttler,
                                  interval_before)
                project.append_event(
                    root, "fetch_error", target_id=target_id,
                    detail=f"{url} 传输失败：{type(e).__name__}: {e}",
                    data={"run_id": run_id, "url": url,
                          "kind": getattr(e, "kind", "transport")})
                run_rec["errors"].append(f"{url}: 传输失败 {e}")
                continue
            throttler.note_response(resp.headers)
            if dl_info and dl_info.get("resumed_from"):
                project.append_event(
                    root, "download_resumed", target_id=target_id,
                    detail=f"{url} 断点续传：自 {dl_info['resumed_from']} "
                           f"字节接续，共 {dl_info['bytes_total']} 字节",
                    data={"run_id": run_id, "url": url})
            if resp.status >= 500:
                throttler.note_outcome("server_error")
            elif resp.status < 400:
                throttler.note_outcome("ok")
            _emit_adaptation(root, target_id, run_id, throttler,
                             interval_before)

            if not _same_host(resp.final_url, reg["base_url"]):
                project.append_event(
                    root, "redirect_out_of_scope", target_id=target_id,
                    detail=f"{url} 重定向跳出登记域名至 {resp.final_url}，"
                           "响应不落盘（HC-7）",
                    data={"run_id": run_id, "url": url,
                          "final_url": resp.final_url})
                run_rec["errors"].append(f"{url}: 重定向越域")
                continue

            if resp.status == 304:
                project.append_event(
                    root, "not_modified", target_id=target_id,
                    detail=f"{url} 条件请求 304，未变更不落新版",
                    data={"run_id": run_id, "url": url})
                run_rec["not_modified"] += 1
                if prior_seen:
                    prior_seen["last_seen_run"] = run_id
                    storage.record_seen(root, prior_seen)
                continue

            if resp.status in (401, 403, 429):
                ra = parse_retry_after(
                    next((v for k, v in resp.headers.items()
                          if k.lower() == "retry-after"), None))
                extra_detail = note_render_refusal(
                    root, target_id, run_id, url, resp, session, reg)
                project.append_event(
                    root, "http_refused", target_id=target_id,
                    detail=f"{url} 被目标以 HTTP {resp.status} 回绝，本 run "
                           "即停（HC-8）"
                           + (f"；Retry-After {ra}s 已记录供后续预检参考"
                              if ra is not None else "")
                           + extra_detail,
                    data={"run_id": run_id, "url": url,
                          "status": resp.status, "retry_after_sec": ra})
                run_rec["refused"] = True
                run_rec["errors"].append(f"{url}: HTTP {resp.status} 被拒")
                break

            if resp.status >= 400:
                run_rec["errors"].append(f"{url}: HTTP {resp.status}")
                continue

            stored = storage.store_raw(root, resp.body)
            cleaned = storage.clean_content(
                resp.body,
                next((v for k, v in resp.headers.items()
                      if k.lower() == "content-type"), ""),
                profile=reg.get("clean_profile", "html_text_v1"),
                prior_texts=prior_texts)
            prior_texts.append(cleaned["text"])
            if cleaned.get("kind") == "html":
                from . import discover as discover_mod
                from . import transport as transport_mod
                shell = discover_mod.js_shell_signals(
                    transport_mod.decode_text(resp.body, resp.headers),
                    cleaned["text"])
                if shell["suspected"]:
                    cleaned["js_shell"] = shell
                    project.append_event(
                        root, "js_shell_detected", target_id=target_id,
                        detail=f"{url} 静态产物疑似 JS 壳（信号 "
                               f"{shell['signals']}）：内容靠脚本注入，"
                               "静态形态未拿到正文；渲染升级走 crawl "
                               "回退链（须登记授权）或浏览器通道",
                        data={"run_id": run_id, "url": url,
                              "signals": shell["signals"]})
            # 跨 run 近重检查（simhash 层）：在清洗件落盘前标注；
            # 指纹入库与事件在 provenance 落账后（见下）。
            nd_hit = storage.check_near_duplicate(root, reg, cleaned)
            if nd_hit is not None:
                cleaned["near_duplicate_cross_run"] = nd_hit
            cleaned_rel = None
            if cleaned["kind"] in ("html", "json", "text"):
                cpath = run_dir / "cleaned" / f"{fp[:12]}.json"
                import json as _json
                cpath.write_text(_json.dumps(
                    cleaned, ensure_ascii=False, indent=1), encoding="utf-8")
                cleaned_rel = cpath.relative_to(Path(root)).as_posix()
            warc_fields = {}
            if tier == storage.WARC_TIER:
                if warc_archive is None:
                    warc_archive, warc_rel = storage.run_archive(
                        root, run_dir)
                ref = warc_archive.add_response(
                    uri=resp.final_url, status=resp.status,
                    headers=resp.headers, body=resp.body)
                warc_fields = {"warc_path": warc_rel, **ref}
            prior_prov = storage.last_provenance_for(root, url)
            prov = storage.append_provenance(root, {
                "kind": "fetch", "target_id": target_id, "run_id": run_id,
                "url": url, "final_url": resp.final_url, "channel": channel,
                "http_status": resp.status,
                "bytes": len(resp.body), **stored,
                "cleaned_path": cleaned_rel,
                "precheck_ref": ctx["record"]["precheck_id"],
                "run_config_hash": run_rec["run_config_hash"],
                "retention_tier": tier, **warc_fields,
                "etag": next((v for k, v in resp.headers.items()
                              if k.lower() == "etag"), None),
                "last_modified": next((v for k, v in resp.headers.items()
                                       if k.lower() == "last-modified"), None),
                "fingerprint": fp,
                "supersedes": prior_prov["prov_id"] if prior_prov else None,
                "redirect_chain": getattr(resp, "redirect_chain", []) or [],
                "render": getattr(resp, "render_info", None),
                "entitlement": (
                    {"basis": reg.get("entitlement_basis"),
                     "credential_ref": reg.get("credential_ref"),
                     "account_label": (session or {}).get("account_label")}
                    if session else None),
            })
            seen[fp] = {
                "fingerprint": fp, "url": url, "target_id": target_id,
                "etag": prov["etag"], "last_modified": prov["last_modified"],
                "sha256": stored["sha256"], "first_seen_run": (
                    prior_seen or {}).get("first_seen_run", run_id),
                "last_seen_run": run_id,
            }
            storage.record_seen(root, seen[fp])
            storage.record_content_fingerprint(
                root, reg, cleaned=cleaned, prov_id=prov["prov_id"],
                target_id=target_id, run_id=run_id, url=url)
            if nd_hit is not None:
                run_rec["near_duplicates"] += 1
                project.append_event(
                    root, "near_duplicate_detected",
                    target_id=target_id,
                    detail=f"{url} 与既有产物近重复（simhash 汉明距离 "
                           f"{nd_hit['hamming_distance']} ≤ 阈值 "
                           f"{nd_hit['hamming_threshold']}；来源产物 "
                           f"{nd_hit['matched_prov_id']} / run "
                           f"{nd_hit['matched_run_id']}）：只标记不处置，"
                           "内容已照常落盘，去留由下游按版本链决定",
                    data={"run_id": run_id, "url": url,
                          "prov_id": prov["prov_id"], **nd_hit})
            run_rec["stored"] += 1
    finally:
        run_rec["finished_at"] = utcnow()
        run_rec["status"] = "refused" if run_rec["refused"] else "finished"
        dump_yaml(run_dir / "run.yaml", run_rec)
        project.release_run_lock(root, target_id)

    # 熔断记账（HC-8）：与 crawl 共用同一份记账函数，口径不漂移
    note_run_outcome(root, target_id, run_id, run_rec["refused"],
                     run_rec["stored"] > 0)
    project.append_event(root, "fetch_run_finished", target_id=target_id,
                         detail=f"{run_id} 结束：请求 {run_rec['requested']}、"
                                f"落盘 {run_rec['stored']}、未变更 "
                                f"{run_rec['not_modified']}、重复 "
                                f"{run_rec['duplicates']}",
                         data={"run_id": run_id, "status": run_rec["status"]})
    return run_rec


def unblock_target(root, target_id, by: str, reason: str) -> dict:
    """熔断恢复：须具名 + 理由，落痕后才清熔断（HC-8）。"""
    if not (by or "").strip() or not (reason or "").strip():
        raise Refusal(["unblock 须具名（--by）并给理由（--reason）："
                       "熔断恢复是责任动作"])
    state = project.load_state(root, target_id)
    if not state.get("circuit_broken"):
        raise Refusal([f"目标 {target_id} 未熔断，无可恢复项"])
    state["circuit_broken"] = False
    state["circuit_reason"] = None
    state["consecutive_refusals"] = 0
    project.save_state(root, state)
    project.refresh_status(root)
    project.append_event(root, "target_unblocked", target_id=target_id,
                         detail=f"{by} 解除熔断：{reason}", data={"by": by})
    return state


def import_file(root, target_id, file_path, note: str, by: str) -> dict:
    """人工导出后登记导入（S2 的正当替代通道）。

    不发生任何自动访问：文件由人从目标处合法导出，本命令只负责把
    它按与抓取产物同一口径落盘（内容寻址 + provenance），来源说明
    与经手人必填——无留痕的导入与无 provenance 的产物一样拒收。
    """
    if not (note or "").strip():
        raise Refusal(["import 须填 --note 来源说明（从何处、经何合法"
                       "途径导出）：无来源说明不落盘"])
    if not (by or "").strip():
        raise Refusal(["import 须具名 --by（经手人）"])
    reg = project.load_target(root, target_id)  # 未登记目标同样拒（HC-1）
    src = Path(file_path)
    if not src.is_file():
        raise Refusal([f"导入文件不存在：{file_path}"])
    data = src.read_bytes()
    stored = storage.store_raw(root, data)
    tier = schema.effective_retention_tier(reg)
    warc_fields = {}
    if tier == storage.WARC_TIER:
        import mimetypes
        arch, rel = storage.imports_archive(root)
        ref = arch.add_resource(
            uri=reg["base_url"], data=data,
            content_type=mimetypes.guess_type(src.name)[0]
            or "application/octet-stream")
        warc_fields = {"warc_path": rel, **ref}
    prov = storage.append_provenance(root, {
        "kind": "manual_import", "target_id": target_id, "run_id": None,
        "url": reg["base_url"], "channel": "manual_import",
        "http_status": None, "bytes": len(data), **stored,
        "cleaned_path": None, "precheck_ref": None, "run_config_hash": None,
        "retention_tier": tier, **warc_fields,
        "source_file_name": src.name, "source_note": note, "imported_by": by,
        "fingerprint": storage.fingerprint("IMPORT", str(src)),
        "supersedes": None,
    })
    project.append_event(root, "manual_import", target_id=target_id,
                         detail=f"{by} 登记导入 {src.name}（{len(data)} 字节）："
                                f"{note}",
                         data={"prov_id": prov["prov_id"]})
    # 导入内容同样进指纹库并过跨 run 近重比对（口径与 fetch 一致：
    # 先比对、后入库、命中只落事件不拦导入）。
    from . import transport as _transport_mod
    pseudo_cleaned = {"text": _transport_mod.decode_text(data, {})}
    nd_hit = storage.check_near_duplicate(root, reg, pseudo_cleaned)
    storage.record_content_fingerprint(
        root, reg, cleaned=pseudo_cleaned, prov_id=prov["prov_id"],
        target_id=target_id, run_id=None, url=reg["base_url"],
        kind="manual_import")
    if nd_hit is not None:
        project.append_event(
            root, "near_duplicate_detected", target_id=target_id,
            detail=f"导入文件 {src.name} 与既有产物近重复（simhash "
                   f"汉明距离 {nd_hit['hamming_distance']} ≤ 阈值 "
                   f"{nd_hit['hamming_threshold']}；来源产物 "
                   f"{nd_hit['matched_prov_id']} / run "
                   f"{nd_hit['matched_run_id']}）：只标记不处置，"
                   "导入已照常落盘",
            data={"run_id": None, "url": reg["base_url"],
                  "prov_id": prov["prov_id"], **nd_hit})
    return prov
