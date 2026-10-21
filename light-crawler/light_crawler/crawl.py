"""frontier 任务、回退策略链与断点续爬（C2 能力强化批）。

v1 的获取只有「点名 URL 批量抓」：没有链接发现就没有任务前沿，
中断恢复只靠已见集顺带实现。本模块补成正式任务形态：

- frontier 落盘：targets/<id>/job.json（原子写），每处理完一个
  条目即检查点落盘；中断后重跑 crawl 自动续跑（inflight 条目
  回滚为 pending，已完成条目不重抓，凭据/robots/熔断口径不变）；
- 回退策略链（逐级留痕）：登记 API 端点 -> sitemap -> 静态抓取
  + 链接发现 -> 浏览器渲染。前三级是任务的种子与扩展策略；
  渲染一级是逐页升级：页面被判 JS 壳时，须登记
  allow_render_escalation=true（且预检已确认）才执行，未授权
  落 render_escalation_blocked 事件并存壳标注，绝不擅自升级；
- 发现联动：每抓到一个 HTML 页就抽链接/分页/脚本端点，端点
  登记进发现账并入队（同域、robots、深度与总量上限全程生效）；
- 纪律同 fetch：guard 前置、robots 失败关闭、被拒即停并走
  同一份熔断记账（fetch.note_run_outcome）、自适应限速同源。
"""

from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from urllib.parse import urlparse

from . import discover as discover_mod
from . import fetch as fetch_mod
from . import project, robots, schema, storage
from . import transport as transport_mod
from .throttle import Throttler, parse_retry_after
from .util import dump_yaml, today, utcnow

JOB_FILE = "job.json"
MAX_SCRIPTS_PER_JOB = 20


# ---------------------------------------------------------------- job 状态

def job_path(root, target_id) -> Path:
    return Path(root) / "targets" / target_id / JOB_FILE


def load_job(root, target_id):
    path = job_path(root, target_id)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def save_job(root, job) -> None:
    """原子落盘：先写临时文件再 os.replace，进程被杀不丢已检点。"""
    path = job_path(root, job["target_id"])
    path.parent.mkdir(parents=True, exist_ok=True)
    job["updated_at"] = utcnow()
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(job, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    os.replace(tmp, path)


def _add_item(job, url, kind, depth, discovered_from) -> bool:
    if url in job["items"]:
        return False
    job["items"][url] = {
        "url": url, "kind": kind, "depth": depth,
        "discovered_from": discovered_from, "status": "pending",
        "attempts": 0, "prov_id": None, "error": None,
        "rendered": False,
    }
    job["order"].append(url)
    return True


def _resolve_robots(root, target_id, base, record, run_id=None):
    """crawl/discover 的 robots 取用（D8）：与 fetch 同口径走预检
    24h 缓存（robots.resolve_robots），复用与作废各落一条事件。"""
    fetched, src = robots.resolve_robots(root, base, record=record)
    data = {"precheck_id": src["precheck_id"]}
    if run_id:
        data["run_id"] = run_id
    if src["source"] == "precheck_cache":
        data["body_sha256"] = src.get("body_sha256")
        project.append_event(
            root, "robots_cache_reused", target_id=target_id,
            detail="执行期复用预检 robots 缓存（24h 内、原文哈希相符，"
                   "本次未再请求 robots.txt，D8）", data=data)
    elif src.get("cache_invalidated"):
        data["reason"] = src["cache_invalidated"]
        project.append_event(
            root, "robots_cache_invalidated", target_id=target_id,
            detail=f"预检 robots 缓存作废（{src['cache_invalidated']}），"
                   "执行期已回落实时取用（D8）", data=data)
    return fetched


def _counts(job) -> dict:
    counts = {}
    for item in job["items"].values():
        counts[item["status"]] = counts.get(item["status"], 0) + 1
    return counts


# ---------------------------------------------------------------- 发现 pass

def discover_pass(root, target_id, transport=None, sleep=None) -> dict:
    """独立发现 pass（discover 命令）：种子页 + 脚本 + sitemap，
    结果登记进发现账，不抓正文页本体之外的任何东西。"""
    ctx = fetch_mod.guard_check(root, target_id)
    reg = ctx["reg"]
    base = reg["base_url"]
    transport_fn = transport or fetch_mod.http_get
    rate = (ctx["record"].get("checks") or {}).get("rate") or {}
    interval = rate.get("effective_interval_sec") or \
        schema.TEMPLATE_MIN_INTERVAL_SEC[reg["channel"]]
    throttler = Throttler(interval, sleep=sleep or time.sleep)
    robots_fetch = _resolve_robots(root, target_id, base, ctx["record"])
    if robots_fetch.outcome == "unreachable":
        raise fetch_mod.Refusal([
            "robots 不可达，失败关闭（RFC 9309 第 2.3.1.4 节）："
            "发现 pass 同样不许在 robots 未定义时前进"])

    def get(url):
        verdict = robots.check_url(robots_fetch, url)
        if not verdict["allowed"]:
            return None
        throttler.wait()
        try:
            return transport_fn(url, headers={
                "User-Agent": schema.USER_AGENT})
        except Exception:
            return None

    added_total = []
    resp = get(base)
    if resp is not None and resp.status < 400:
        html = transport_mod.decode_text(resp.body, resp.headers)
        links = discover_mod.extract_links(html, resp.final_url)
        rows = [{"kind": "page", "url": u, "discovered_from": base,
                 "via": "link"} for u in links["pages"]
                if discover_mod.same_host(u, base)]
        rows += [{"kind": "embedded_data", "url": base,
                  "discovered_from": base, "via": b["kind"]}
                 for b in discover_mod.extract_embedded_json(html)]
        for script_url in links["scripts"][:MAX_SCRIPTS_PER_JOB]:
            if not discover_mod.same_host(script_url, base):
                continue
            sresp = get(script_url)
            if sresp is None or sresp.status >= 400:
                continue
            js = transport_mod.decode_text(sresp.body, sresp.headers)
            for ep in discover_mod.mine_script_endpoints(
                    js, script_url):
                if ep["url"]:
                    rows.append({"kind": "api_endpoint", "url": ep["url"],
                                 "discovered_from": script_url,
                                 "via": ep["via"]})
                else:
                    rows.append({"kind": "api_template", "url": None,
                                 "discovered_from": script_url,
                                 "via": ep["via"], "raw": ep["raw"]})
        added_total += discover_mod.register_discovered(
            root, target_id, rows)

    sitemap_urls = []
    if robots_fetch.outcome == "ok":
        sitemap_urls += robots.parse_robots(robots_fetch.body).sitemaps
    sitemap_urls.append(base.rstrip("/") + "/sitemap.xml")
    sm_rows = []
    for sm in dict.fromkeys(sitemap_urls):
        sresp = get(sm)
        if sresp is None or sresp.status >= 400:
            continue
        parsed = discover_mod.parse_sitemap(sresp.body)
        sm_rows += [{"kind": "page", "url": u, "discovered_from": sm,
                     "via": "sitemap"} for u in parsed["urls"]
                    if discover_mod.same_host(u, base)]
        if parsed["urls"]:
            break
    added_total += discover_mod.register_discovered(
        root, target_id, sm_rows)
    summary = {
        "target_id": target_id,
        "registered_new": len([r for r in added_total
                               if r.get("source_id")]),
        "by_kind": {},
    }
    for row in discover_mod.list_discovered(root, target_id):
        summary["by_kind"][row["kind"]] = \
            summary["by_kind"].get(row["kind"], 0) + 1
    project.append_event(
        root, "discovery_completed", target_id=target_id,
        detail=f"发现 pass 完成：发现账共 "
               f"{sum(summary['by_kind'].values())} 条"
               f"（{summary['by_kind']}），本次新增 "
               f"{summary['registered_new']}",
        data=summary)
    return summary


# ---------------------------------------------------------------- crawl 主循环

def crawl_run(root, target_id, seeds=None, max_pages=None, transport=None,
              sleep=None, browser_fetcher=None, credential_provider=None,
              discover_enabled=True, fresh=False,
              refetch_seen=False) -> dict:
    """执行/续跑一个 frontier 任务。返回任务摘要 dict。

    中断语义：会话请求数达上限、进程异常、被拒即停都会把已检点
    的 job 落盘；再次调用即续跑（inflight 回滚 pending、done 与
    skipped 不重抓）。运行锁残锁按项目锁口径只点名不夺锁。
    """
    ctx = fetch_mod.guard_check(root, target_id)
    reg, channel = ctx["reg"], ctx["reg"].get("channel")
    base = reg["base_url"]
    transport_fn = transport or fetch_mod.http_get
    transport_is_default = transport_fn is fetch_mod.http_get
    if browser_fetcher is None:
        browser_fetcher = fetch_mod.make_builtin_browser_fetcher()
    session = None
    if (reg.get("login_state") or "none") != "none":
        session = fetch_mod.resolve_session(
            root, target_id, reg, credential_provider)
        if not hasattr(browser_fetcher, "set_session"):
            raise fetch_mod.Refusal([
                "凭据会话只能由支持 set_session 的浏览器执行器承载"
                "（随包 _BuiltinBrowserFetcher）"])
        browser_fetcher.set_session(session)

    rate = (ctx["record"].get("checks") or {}).get("rate") or {}
    max_run = rate.get("max_requests_per_run",
                       schema.DEFAULT_MAX_REQUESTS_PER_RUN)
    max_day = rate.get("max_requests_per_day",
                       schema.DEFAULT_MAX_REQUESTS_PER_DAY)
    interval = rate.get("effective_interval_sec") or \
        schema.TEMPLATE_MIN_INTERVAL_SEC[channel]
    session_cap = max_pages or max_run
    max_depth = (reg.get("discovery") or {}).get("max_depth", 2)

    # ---- job 装载/新建（续跑判定：有未完成条目即续）
    job = None if fresh else load_job(root, target_id)
    resumed = False
    if job is not None:
        pending_like = [i for i in job["items"].values()
                        if i["status"] in ("pending", "inflight")]
        if pending_like:
            resumed = True
            for item in job["items"].values():
                if item["status"] == "inflight":
                    item["status"] = "pending"
        else:
            job = None
    if job is None:
        job = {"job_id": f"job-{uuid.uuid4().hex[:8]}",
               "target_id": target_id, "created_at": utcnow(),
               "status": "running", "strategy": None,
               "items": {}, "order": [], "scripts_mined": 0}
    job["status"] = "running"
    save_job(root, job)

    run_id = project.new_run_id(target_id)
    project.acquire_run_lock(root, target_id, run_id)
    run_dir = Path(root) / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "cleaned").mkdir(exist_ok=True)
    run_rec = {"run_id": run_id, "target_id": target_id,
               "channel": channel, "kind": "crawl",
               "status": "running", "started_at": utcnow(),
               "precheck_id": ctx["record"]["precheck_id"],
               "run_config_hash": ctx["record"].get("run_config_hash"),
               "requested": 0, "stored": 0, "errors": [],
               "refused": False, "job_id": job["job_id"]}
    dump_yaml(run_dir / "run.yaml", run_rec)
    project.append_event(
        root, "crawl_job_resumed" if resumed else "crawl_job_started",
        target_id=target_id,
        detail=f"{job['job_id']} {'续跑' if resumed else '启动'}"
               f"（{run_id}，策略 {job.get('strategy') or '待选'}，"
               f"条目 {len(job['items'])}）",
        data={"run_id": run_id, "job_id": job["job_id"]})

    throttler = Throttler(interval, sleep=sleep or time.sleep)
    seen = storage.load_seen(root)
    today_count = sum(
        1 for r in storage.read_provenance(root)
        if r.get("kind") == "fetch" and r.get("target_id") == target_id
        and (r.get("at") or "").startswith(today()))
    robots_fetch = _resolve_robots(root, target_id, base, ctx["record"],
                                   run_id=run_id)
    summary = {"job_id": job["job_id"], "run_id": run_id,
               "target_id": target_id, "resumed": resumed,
               "strategy": job.get("strategy"), "requested": 0,
               "stored": 0, "status": "running"}

    def counted_get(url, headers, render=False, large=False, fp=None):
        """统一计数/节流/自适应出口：返回 (resp, dl_info)。"""
        interval_before = throttler.interval
        throttler.wait()
        summary["requested"] += 1
        run_rec["requested"] += 1
        if render:
            resp, dl_info = browser_fetcher(url, headers), None
        elif large:
            resp, dl_info = fetch_mod._large_download(
                Path(root) / "targets" / target_id, fp, url, headers)
        else:
            resp, dl_info = transport_fn(url, headers=headers), None
        throttler.note_response(resp.headers)
        if resp.status >= 500:
            throttler.note_outcome("server_error")
        elif resp.status < 400:
            throttler.note_outcome("ok")
        fetch_mod._emit_adaptation(root, target_id, run_id, throttler,
                                   interval_before)
        return resp, dl_info

    try:
        if robots_fetch.outcome == "unreachable":
            project.append_event(
                root, "fetch_refused", target_id=target_id,
                detail="crawl 期 robots 复核不可达，整任务失败关闭"
                       "（RFC 9309 第 2.3.1.4 节）",
                data={"run_id": run_id, "job_id": job["job_id"]})
            job["status"] = "refused"
            summary["status"] = "refused"
            save_job(root, job)
            return summary

        # ---- 策略链播种（仅新 job）
        if not job["order"]:
            strategy = None
            api_eps = reg.get("api_endpoints") or []
            if api_eps:
                strategy = "api"
                for u in api_eps:
                    _add_item(job, u, "api_endpoint", 0,
                              "registration.api_endpoints")
            if strategy is None:
                sm_candidates = []
                if robots_fetch.outcome == "ok":
                    sm_candidates += robots.parse_robots(
                        robots_fetch.body).sitemaps
                sm_candidates.append(base.rstrip("/") + "/sitemap.xml")
                for sm in dict.fromkeys(sm_candidates):
                    if summary["requested"] >= session_cap:
                        break
                    if not robots.check_url(robots_fetch, sm)["allowed"]:
                        continue
                    try:
                        resp, _ = counted_get(
                            sm, {"User-Agent": schema.USER_AGENT})
                    except Exception:
                        continue
                    if resp.status >= 400:
                        continue
                    parsed = discover_mod.parse_sitemap(resp.body)
                    todo = list(parsed["urls"])
                    for child in parsed["child_sitemaps"][:3]:
                        try:
                            cresp, _ = counted_get(
                                child, {"User-Agent": schema.USER_AGENT})
                            if cresp.status < 400:
                                todo += discover_mod.parse_sitemap(
                                    cresp.body)["urls"]
                        except Exception:
                            continue
                    if todo:
                        strategy = "sitemap"
                        for u in todo:
                            kind = "api_endpoint" if u.endswith(".json") \
                                else "page"
                            _add_item(job, u, kind, 0, f"sitemap:{sm}")
                        break
            if strategy is None:
                strategy = "static"
            job["strategy"] = strategy
            summary["strategy"] = strategy
            for u in (seeds or ([base] if strategy != "api" else [])):
                _add_item(job, u, "page", 0, "seed")
            project.append_event(
                root, "strategy_selected", target_id=target_id,
                detail=f"回退链起始策略：{strategy}"
                       f"（种子 {len(job['order'])} 条）",
                data={"run_id": run_id, "strategy": strategy})
            save_job(root, job)

        # ---- 主循环（order 动态增长，索引推进）
        idx = 0
        while idx < len(job["order"]):
            if summary["requested"] >= session_cap:
                break
            if today_count + summary["requested"] >= max_day:
                project.append_event(
                    root, "volume_cap_hit", target_id=target_id,
                    detail=f"单目标日上限 {max_day} 已达，任务暂停待续",
                    data={"run_id": run_id, "cap": "max_requests_per_day"})
                break
            url = job["order"][idx]
            idx += 1
            item = job["items"][url]
            if item["status"] != "pending":
                continue
            if urlparse(url).netloc != urlparse(base).netloc:
                item["status"] = "failed"
                item["error"] = "不在登记域名内"
                save_job(root, job)
                continue
            verdict = robots.check_url(robots_fetch, url)
            if not verdict["allowed"]:
                item["status"] = "refused_robots"
                item["error"] = verdict["detail"]
                project.append_event(
                    root, "fetch_refused", target_id=target_id,
                    detail=f"crawl robots 复核禁止 {url}："
                           f"{verdict['detail']}",
                    data={"run_id": run_id, "url": url})
                save_job(root, job)
                continue
            fp = storage.fingerprint("GET", url)
            prior_seen = seen.get(fp)
            if prior_seen and not refetch_seen:
                item["status"] = "skipped_seen"
                save_job(root, job)
                continue
            item["status"] = "inflight"
            item["attempts"] += 1
            save_job(root, job)

            headers = {"User-Agent": schema.USER_AGENT}
            if prior_seen:
                if prior_seen.get("etag"):
                    headers["If-None-Match"] = prior_seen["etag"]
                if prior_seen.get("last_modified"):
                    headers["If-Modified-Since"] = \
                        prior_seen["last_modified"]
            need_render = channel == "browser"
            large = bool(reg.get("large_files")) and not need_render \
                and transport_is_default
            try:
                resp, dl_info = counted_get(url, headers,
                                            render=need_render,
                                            large=large, fp=fp)
            except fetch_mod.Refusal:
                item["status"] = "pending"
                save_job(root, job)
                raise
            except Exception as e:
                throttler.note_outcome("network_error")
                project.append_event(
                    root, "fetch_error", target_id=target_id,
                    detail=f"{url} 传输失败：{type(e).__name__}: {e}",
                    data={"run_id": run_id, "url": url,
                          "kind": getattr(e, "kind", "transport")})
                item["status"] = "failed"
                item["error"] = f"{type(e).__name__}: {e}"
                run_rec["errors"].append(item["error"])
                save_job(root, job)
                continue
            if dl_info and dl_info.get("resumed_from"):
                project.append_event(
                    root, "download_resumed", target_id=target_id,
                    detail=f"{url} 断点续传：自 "
                           f"{dl_info['resumed_from']} 字节接续，共 "
                           f"{dl_info['bytes_total']} 字节",
                    data={"run_id": run_id, "url": url})

            if urlparse(resp.final_url).netloc != urlparse(base).netloc:
                project.append_event(
                    root, "redirect_out_of_scope", target_id=target_id,
                    detail=f"{url} 重定向跳出登记域名至 "
                           f"{resp.final_url}，响应不落盘（HC-7）",
                    data={"run_id": run_id, "url": url,
                          "final_url": resp.final_url})
                item["status"] = "failed"
                item["error"] = "重定向越域"
                save_job(root, job)
                continue
            if resp.status == 304:
                project.append_event(
                    root, "not_modified", target_id=target_id,
                    detail=f"{url} 条件请求 304，未变更",
                    data={"run_id": run_id, "url": url})
                item["status"] = "done"
                if prior_seen:
                    prior_seen["last_seen_run"] = run_id
                    storage.record_seen(root, prior_seen)
                save_job(root, job)
                continue
            if resp.status in (401, 403, 429):
                fetch_mod.note_render_refusal(
                    root, target_id, run_id, url, resp, session, reg)
                ra = parse_retry_after(next(
                    (v for k, v in resp.headers.items()
                     if k.lower() == "retry-after"), None))
                project.append_event(
                    root, "http_refused", target_id=target_id,
                    detail=f"{url} 被目标以 HTTP {resp.status} 回绝，"
                           "任务即停（HC-8）"
                           + (f"；Retry-After {ra}s 已记录" if ra
                              is not None else ""),
                    data={"run_id": run_id, "url": url,
                          "status": resp.status, "retry_after_sec": ra})
                item["status"] = "refused"
                run_rec["refused"] = True
                summary["status"] = "refused"
                save_job(root, job)
                break
            if resp.status >= 400:
                item["status"] = "failed"
                item["error"] = f"HTTP {resp.status}"
                run_rec["errors"].append(f"{url}: HTTP {resp.status}")
                save_job(root, job)
                continue

            # ---- 落盘与清洗
            stored = storage.store_raw(root, resp.body)
            cleaned = storage.clean_content(
                resp.body,
                next((v for k, v in resp.headers.items()
                      if k.lower() == "content-type"), ""),
                profile=reg.get("clean_profile", "html_text_v1"))
            rendered = need_render
            # ---- JS 壳升级（回退链最后一一级，须登记授权）
            if cleaned.get("kind") == "html" and not need_render:
                shell = discover_mod.js_shell_signals(
                    transport_mod.decode_text(resp.body, resp.headers),
                    cleaned["text"])
                if shell["suspected"]:
                    cleaned["js_shell"] = shell
                    if reg.get("allow_render_escalation"):
                        if summary["requested"] < session_cap:
                            project.append_event(
                                root, "strategy_escalated",
                                target_id=target_id,
                                detail=f"{url} 静态形态为 JS 壳，按登记"
                                       "授权升级浏览器渲染（回退链）",
                                data={"run_id": run_id, "url": url,
                                      "signals": shell["signals"]})
                            try:
                                resp2, _ = counted_get(
                                    url, headers, render=True)
                            except Exception as e:
                                resp2 = None
                                run_rec["errors"].append(
                                    f"{url}: 渲染升级失败 {e}")
                            if resp2 is not None:
                                if resp2.status in (401, 403, 429):
                                    fetch_mod.note_render_refusal(
                                        root, target_id, run_id, url,
                                        resp2, session, reg)
                                    project.append_event(
                                        root, "http_refused",
                                        target_id=target_id,
                                        detail=f"{url} 渲染升级后被以 "
                                               f"HTTP {resp2.status} "
                                               "回绝，任务即停（HC-8）",
                                        data={"run_id": run_id,
                                              "url": url,
                                              "status": resp2.status})
                                    item["status"] = "refused"
                                    run_rec["refused"] = True
                                    summary["status"] = "refused"
                                    save_job(root, job)
                                    break
                                if resp2.status < 400:
                                    resp, rendered = resp2, True
                                    stored = storage.store_raw(
                                        root, resp.body)
                                    cleaned = storage.clean_content(
                                        resp.body, "text/html",
                                        profile=reg.get(
                                            "clean_profile",
                                            "html_text_v1"))
                    else:
                        project.append_event(
                            root, "render_escalation_blocked",
                            target_id=target_id,
                            detail=f"{url} 为 JS 壳（信号 "
                                   f"{shell['signals']}）但登记未授权"
                                   "渲染升级：壳产物照存并标注；授权"
                                   "路径 = 登记 allow_render_escalation"
                                   "=true 后重跑预检确认，或改登记 "
                                   "browser 通道",
                            data={"run_id": run_id, "url": url,
                                  "signals": shell["signals"]})
            cleaned_rel = None
            if cleaned["kind"] in ("html", "json", "text"):
                cpath = run_dir / "cleaned" / f"{fp[:12]}.json"
                cpath.write_text(json.dumps(
                    cleaned, ensure_ascii=False, indent=1),
                    encoding="utf-8")
                cleaned_rel = cpath.relative_to(Path(root)).as_posix()
            prior_prov = storage.last_provenance_for(root, url)
            prov = storage.append_provenance(root, {
                "kind": "fetch", "target_id": target_id,
                "run_id": run_id, "url": url,
                "final_url": resp.final_url, "channel": channel,
                "http_status": resp.status, "bytes": len(resp.body),
                **stored, "cleaned_path": cleaned_rel,
                "precheck_ref": ctx["record"]["precheck_id"],
                "run_config_hash": run_rec["run_config_hash"],
                "retention_tier": storage.RETENTION_TIER,
                "etag": next((v for k, v in resp.headers.items()
                              if k.lower() == "etag"), None),
                "last_modified": next((v for k, v in resp.headers.items()
                                       if k.lower() == "last-modified"),
                                      None),
                "fingerprint": fp,
                "supersedes": prior_prov["prov_id"] if prior_prov else None,
                "redirect_chain": getattr(resp, "redirect_chain",
                                          []) or [],
                "render": getattr(resp, "render_info", None),
                "entitlement": (
                    {"basis": reg.get("entitlement_basis"),
                     "credential_ref": reg.get("credential_ref"),
                     "account_label": (session or {}).get(
                         "account_label")}
                    if session else None),
                "via": {"strategy": job["strategy"],
                        "item_kind": item["kind"],
                        "discovered_from": item["discovered_from"],
                        "rendered": rendered},
            })
            seen[fp] = {
                "fingerprint": fp, "url": url, "target_id": target_id,
                "etag": prov["etag"],
                "last_modified": prov["last_modified"],
                "sha256": stored["sha256"],
                "first_seen_run": (prior_seen or {}).get(
                    "first_seen_run", run_id),
                "last_seen_run": run_id,
            }
            storage.record_seen(root, seen[fp])
            item["status"] = "done"
            item["prov_id"] = prov["prov_id"]
            item["rendered"] = rendered
            summary["stored"] += 1
            run_rec["stored"] += 1

            # ---- 发现扩展（链接/分页/脚本端点/内嵌数据）
            if discover_enabled and cleaned.get("kind") == "html" \
                    and item["depth"] < max_depth:
                html = transport_mod.decode_text(resp.body, resp.headers)
                links = discover_mod.extract_links(html, resp.final_url)
                rows = []
                for u in links["pages"]:
                    if discover_mod.same_host(u, base):
                        _add_item(job, u, "page", item["depth"] + 1,
                                  f"link:{url}")
                        rows.append({"kind": "page", "url": u,
                                     "discovered_from": url,
                                     "via": "link"})
                for block in discover_mod.extract_embedded_json(html):
                    rows.append({"kind": "embedded_data",
                                 "url": url, "discovered_from": url,
                                 "via": block["kind"]})
                discover_mod.register_discovered(root, target_id, rows)
                for script_url in links["scripts"]:
                    if job["scripts_mined"] >= MAX_SCRIPTS_PER_JOB:
                        break
                    if not discover_mod.same_host(script_url, base):
                        continue
                    if summary["requested"] >= session_cap:
                        break
                    if not robots.check_url(
                            robots_fetch, script_url)["allowed"]:
                        continue
                    job["scripts_mined"] += 1
                    try:
                        sresp, _ = counted_get(
                            script_url,
                            {"User-Agent": schema.USER_AGENT})
                    except Exception:
                        continue
                    if sresp.status >= 400:
                        continue
                    js = transport_mod.decode_text(sresp.body,
                                                   sresp.headers)
                    ep_rows = []
                    for ep in discover_mod.mine_script_endpoints(
                            js, script_url):
                        if ep["url"]:
                            ep_rows.append(
                                {"kind": "api_endpoint",
                                 "url": ep["url"],
                                 "discovered_from": script_url,
                                 "via": ep["via"]})
                            _add_item(job, ep["url"], "api_endpoint",
                                      item["depth"] + 1,
                                      f"script:{script_url}")
                    discover_mod.register_discovered(
                        root, target_id, ep_rows)
            save_job(root, job)
    finally:
        counts = _counts(job)
        if summary["status"] != "refused":
            summary["status"] = (
                "partial" if counts.get("pending") or
                counts.get("inflight") else "finished")
        job["status"] = summary["status"]
        save_job(root, job)
        run_rec["finished_at"] = utcnow()
        run_rec["status"] = summary["status"]
        run_rec["job_counts"] = counts
        dump_yaml(run_dir / "run.yaml", run_rec)
        project.release_run_lock(root, target_id)

    fetch_mod.note_run_outcome(root, target_id, run_id,
                               run_rec["refused"],
                               run_rec["stored"] > 0)
    summary["counts"] = _counts(job)
    project.append_event(
        root, "crawl_job_finished", target_id=target_id,
        detail=f"{job['job_id']} 结束：{summary['status']}"
               f"（请求 {summary['requested']}、落盘 "
               f"{summary['stored']}、条目 {summary['counts']}）",
        data={"run_id": run_id, "job_id": job["job_id"],
              "status": summary["status"]})
    return summary
