"""guard 与获取执行（C2）+ 人工导入（S2 替代）+ 对外预检门接口。

guard 纪律（HC-1，学 reverse-skill 的 case-guard 形态）：fetch 启动
前逐项校验登记、预检生效与新鲜度、熔断状态、通道可执行性，缺项
逐项点名退出；本包不设任何绕过旗标（force 不绕硬门——干脆不给）。
获取执行：通道优先级已在登记/预检层裁决，这里只按裁决执行；
被拒即停（HC-8）、越域即停（HC-7）、量上限即停，全程落事件。
"""

from __future__ import annotations

import time
import urllib.error
import urllib.request
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


def http_get(url, headers=None, timeout=30.0) -> Response:
    """默认 HTTP 传输（urllib）。HTTP 状态不抛错、原样返回；
    网络层错误抛给调用方按失败关闭处理。"""
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return Response(resp.status, dict(resp.headers.items()),
                            resp.read(), resp.geturl())
    except urllib.error.HTTPError as e:
        # HTTPError 携带的是重定向跟随后的最终 URL（e.geturl()），
        # 越域判定必须以它为准，不许用请求原 URL 冒充。
        return Response(e.code, dict(e.headers.items()) if e.headers else {},
                        e.read() if hasattr(e, "read") else b"", e.geturl())


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


# ---------------------------------------------------------------- 获取

def _same_host(a: str, b: str) -> bool:
    pa, pb = urlparse(a), urlparse(b)
    return (pa.scheme, pa.netloc) == (pb.scheme, pb.netloc)


def fetch_run(root, target_id, urls=None, transport=None, sleep=None,
              browser_fetcher=None, refetch_seen=False) -> dict:
    """执行一次采集 run。返回 run 摘要 dict。

    transport / sleep / browser_fetcher 可注入（测试与外部浏览器
    工具接入点）；生产默认 transport 为 urllib、sleep 为真睡。
    """
    ctx = guard_check(root, target_id)
    reg, channel = ctx["reg"], ctx["reg"].get("channel")
    transport = transport or http_get

    if channel == "browser" and browser_fetcher is None:
        reason = ("浏览器通道的预检门已齐备，但执行器不随包提供（S1 窄口径）："
                  "请以登记在案的外部浏览器工具在本预检记录下执行，"
                  "或改走人工导出 + import 登记导入")
        project.append_event(root, "fetch_refused", target_id=target_id,
                             detail=reason, data={"channel": "browser"})
        raise Refusal([reason])

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
        "errors": [], "refused": False,
    }
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
    # fetch 期 robots 复核（逐 URL；不可达即整 run 失败关闭）
    robots_fetch = robots.fetch_robots(reg["base_url"])
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
            if channel == "browser":
                resp = browser_fetcher(url, headers)
            else:
                resp = transport(url, headers=headers)
            throttler.note_response(resp.headers)

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
                project.append_event(
                    root, "http_refused", target_id=target_id,
                    detail=f"{url} 被目标以 HTTP {resp.status} 回绝，本 run "
                           "即停（HC-8）"
                           + (f"；Retry-After {ra}s 已记录供后续预检参考"
                              if ra is not None else ""),
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
            cleaned_rel = None
            if cleaned["kind"] in ("html", "json", "text"):
                cpath = run_dir / "cleaned" / f"{fp[:12]}.json"
                import json as _json
                cpath.write_text(_json.dumps(
                    cleaned, ensure_ascii=False, indent=1), encoding="utf-8")
                cleaned_rel = cpath.relative_to(Path(root)).as_posix()
            prior_prov = storage.last_provenance_for(root, url)
            prov = storage.append_provenance(root, {
                "kind": "fetch", "target_id": target_id, "run_id": run_id,
                "url": url, "final_url": resp.final_url, "channel": channel,
                "http_status": resp.status,
                "bytes": len(resp.body), **stored,
                "cleaned_path": cleaned_rel,
                "precheck_ref": ctx["record"]["precheck_id"],
                "run_config_hash": run_rec["run_config_hash"],
                "retention_tier": storage.RETENTION_TIER,
                "etag": next((v for k, v in resp.headers.items()
                              if k.lower() == "etag"), None),
                "last_modified": next((v for k, v in resp.headers.items()
                                       if k.lower() == "last-modified"), None),
                "fingerprint": fp,
                "supersedes": prior_prov["prov_id"] if prior_prov else None,
            })
            seen[fp] = {
                "fingerprint": fp, "url": url, "target_id": target_id,
                "etag": prov["etag"], "last_modified": prov["last_modified"],
                "sha256": stored["sha256"], "first_seen_run": (
                    prior_seen or {}).get("first_seen_run", run_id),
                "last_seen_run": run_id,
            }
            storage.record_seen(root, seen[fp])
            run_rec["stored"] += 1
    finally:
        run_rec["finished_at"] = utcnow()
        run_rec["status"] = "refused" if run_rec["refused"] else "finished"
        dump_yaml(run_dir / "run.yaml", run_rec)
        project.release_run_lock(root, target_id)

    # 熔断记账（HC-8）：被拒 run 累计，成功 run 清零
    if run_rec["refused"]:
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
    elif run_rec["stored"] > 0:
        state["consecutive_refusals"] = 0
    project.save_state(root, state)
    project.refresh_status(root)
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
    prov = storage.append_provenance(root, {
        "kind": "manual_import", "target_id": target_id, "run_id": None,
        "url": reg["base_url"], "channel": "manual_import",
        "http_status": None, "bytes": len(data), **stored,
        "cleaned_path": None, "precheck_ref": None, "run_config_hash": None,
        "retention_tier": storage.RETENTION_TIER,
        "source_file_name": src.name, "source_note": note, "imported_by": by,
        "fingerprint": storage.fingerprint("IMPORT", str(src)),
        "supersedes": None,
    })
    project.append_event(root, "manual_import", target_id=target_id,
                         detail=f"{by} 登记导入 {src.name}（{len(data)} 字节）："
                                f"{note}",
                         data={"prov_id": prov["prov_id"]})
    return prov
