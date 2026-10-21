"""合规预检（C1）：目标级检查 + 项目锁 + 拒绝留痕。

ready_to_fetch 是代码计算值，不是任何人的声明：本模块逐项检查并
把每一项的结论与依据落进预检记录；guard 在 fetch 前只认这里的最
新结论。预检分级（S4）：低危通道全过自动生效，高危通道须具名
人工确认；硬不通过落 blocked + 事件点名，缺项落 incomplete 点名。
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlparse

from . import project, robots, schema
from .util import parse_ts, read_jsonl, sha256_bytes, utcnow


def _risk_rank(risk):
    return {"none": 0, "low": 1, "high": 2}.get(risk, 99)


def run_precheck(root, target_id, robots_timeout: float = 10.0) -> dict:
    """对一个已登记目标跑全量预检并落记录（只增）。返回预检记录。"""
    reg = project.load_target(root, target_id)
    header = project.load_header(root)
    lock = header.get("lock") or {}
    channel = reg.get("channel")
    checks = {}
    blocked_reasons, missing = [], []

    # ---- 登记自洽（校验器复跑：登记文件可能被手改）
    problems = schema.validate_target(reg)
    checks["registration"] = {"ok": not problems, "problems": problems}
    blocked_reasons += [f"登记不合格：{p}" for p in problems]

    # ---- 通道合法性
    chan = {"channel": channel}
    preauth_entry = None
    alt = reg.get("official_alternative") or {}
    if alt.get("available") and channel in ("web_page", "browser"):
        chan["ok"] = False
        blocked_reasons.append(
            "官方通道优先（HC-3）：登记已声明存在官方替代通道 "
            f"（{alt.get('note') or alt.get('channel_ref') or '见登记'}），"
            f"{channel} 通道出局，请改走官方通道重新登记")
    elif channel == "browser":
        if lock.get("allow_browser") is False:
            chan["ok"] = False
            blocked_reasons.append(
                "项目锁已关闭浏览器通道（lock.allow_browser=false），"
                "单目标预检不得放松项目锁")
        else:
            # D1 预授权名单（决策清单 D1 选项 a，2026-10-21 批准）：
            # 名单内目标以名单层具名与理由替代逐目标开启手续。
            preauth_entry = project.find_browser_preauthorization(
                header, target_id)
            if preauth_entry is not None:
                chan["ok"] = True
                chan["browser_preauthorized"] = {
                    "listed_by": preauth_entry.get("listed_by"),
                    "reason": preauth_entry.get("reason"),
                    "listed_at": preauth_entry.get("listed_at"),
                }
                chan["browser_reason"] = preauth_entry.get("reason")
            elif not reg.get("browser_enabled"):
                chan["ok"] = False
                blocked_reasons.append(
                    "浏览器通道默认关（S1）：登记须置 browser_enabled=true 并在"
                    "预检中登记开启理由，或由具名者列入项目级预授权名单（D1）")
            elif not (reg.get("browser_reason") or "").strip():
                chan["ok"] = False
                blocked_reasons.append(
                    "浏览器通道开启缺理由（S1）：browser_reason 必填")
            else:
                chan["ok"] = True
                chan["browser_reason"] = reg["browser_reason"]
    else:
        chan["ok"] = True
    chan["render_escalation_authorized"] = bool(
        reg.get("allow_render_escalation"))
    checks["channel"] = chan

    # ---- 凭据访问通道（登记面由 schema 校验；预检只落记录行）
    login = reg.get("login_state", "none")
    cred = {"login_state": login, "ok": True}
    if login != "none":
        cred.update({
            "entitlement_basis": reg.get("entitlement_basis"),
            "credential_ref": reg.get("credential_ref"),
            "validity": "not_verified_at_precheck",
            "note": "预检不验证凭据真实有效性、不发起登录；会话失效"
                    "在 fetch 期按被拒口径熔断留痕",
        })
    checks["credentials"] = cred

    # ---- 个人数据（项目锁只能收紧）
    risk = reg.get("personal_data_risk", "none")
    lock_max = lock.get("max_personal_data_risk", "low")
    pdata = {"risk": risk, "lock_max": lock_max, "ok": True}
    if _risk_rank(risk) > _risk_rank(lock_max):
        pdata["ok"] = False
        blocked_reasons.append(
            f"个人数据风险 {risk} 超过项目锁上限 {lock_max}（项目锁只紧不松）")
    checks["personal_data"] = pdata

    # ---- 条款依据（缺失 = incomplete，非 blocked：补齐即可重检）
    terms = reg.get("terms_basis")
    checks["terms"] = {"ok": bool(terms), "terms_basis": terms}
    if not terms:
        missing.append("terms_basis（站点条款/API 条款依据指针）未登记")

    # ---- 留存档位（S3 现行口径：两档均可登记，本行只落裁决事实；
    # 档位词表本身在 checks["registration"] 已由 validate_target 把关）
    tier = schema.effective_retention_tier(reg)
    checks["retention"] = {
        "ok": True,
        "tier": tier,
        "form": ("ISO 28500 WARC 全记录（另附轻量档原始字节 + 哈希）"
                 if tier == "warc_full" else
                 "原始响应文件 + 哈希（内容寻址）"),
    }

    # ---- robots（失败关闭；逐个登记 URL 模式各查一遍）
    urls_to_check = [reg["base_url"]] + list(reg.get("url_patterns") or [])
    fetched = robots.fetch_robots(reg["base_url"], timeout=robots_timeout)
    per_url, worst_delay = [], None
    for u in urls_to_check:
        verdict = robots.check_url(fetched, u)
        per_url.append({"url": u, **{k: verdict[k] for k in (
            "outcome", "allowed", "basis", "matched_rule", "detail")}})
        if verdict.get("crawl_delay_sec") is not None:
            d = verdict["crawl_delay_sec"]
            worst_delay = d if worst_delay is None else max(worst_delay, d)
        if not verdict["allowed"]:
            blocked_reasons.append(
                f"robots 结论禁止 {u}：{verdict['detail']}（{verdict['basis']}）")
    checks["robots"] = {
        "ok": all(v["allowed"] for v in per_url),
        "outcome": fetched.outcome,
        "http_status": fetched.status,
        "fetched_at": utcnow(),
        "body_sha256": sha256_bytes(fetched.body) if fetched.body else None,
        "per_url": per_url,
        "crawl_delay_sec": worst_delay,
        "crawl_delay_note": ("crawl-delay 为常见扩展，不在 RFC 9309 内；"
                             "只作公示意愿事实参与速率取严"),
    }
    # D8：robots 原文按哈希落缓存，执行期 24h 内凭记录哈希复用
    # （robots.resolve_robots）；缓存路径只作定位，复用时重算哈希比对。
    cache_rel = robots.store_cached_body(root, fetched)
    if cache_rel:
        checks["robots"]["body_cache_path"] = cache_rel

    # ---- 速率裁决（公式取严；项目锁下限参与且只抬不降）
    lock_min = lock.get("min_interval_sec")
    decision = schema.effective_interval(
        reg, crawl_delay_sec=worst_delay,
        lock_min_interval_sec=float(lock_min) if lock_min else None)
    lock_raised = (lock_min is not None
                   and decision["decided_by"] == "project_lock")
    checks["rate"] = {
        "ok": True, **decision,
        "concurrency": schema.REQUIRED_CONCURRENCY,
        "max_requests_per_run": (reg.get("rate") or {}).get(
            "max_requests_per_run", schema.DEFAULT_MAX_REQUESTS_PER_RUN),
        "max_requests_per_day": (reg.get("rate") or {}).get(
            "max_requests_per_day", schema.DEFAULT_MAX_REQUESTS_PER_DAY),
        "lock_raised": lock_raised,
    }

    # ---- 裁决合成
    if blocked_reasons:
        status = "blocked"
    elif missing:
        status = "incomplete"
    elif channel in schema.HIGH_RISK_CHANNELS:
        status = "pending_confirmation"
    else:
        status = "effective"
    # D1：名单内 browser 目标免逐个确认——pending 直接转 effective，
    # 豁免依据（名单条目）落进预检记录，另落 applied 事件（见下）。
    confirmation_waiver = None
    if status == "pending_confirmation" and preauth_entry is not None:
        status = "effective"
        confirmation_waiver = {
            "waived_via": "browser_preauthorized_list",
            "listed_by": preauth_entry.get("listed_by"),
            "reason": preauth_entry.get("reason"),
            "listed_at": preauth_entry.get("listed_at"),
            "decision_ref": "crawler-decision-list.md D1（2026-10-21 批准）",
        }

    now = parse_ts(utcnow())
    record = {
        "kind": "precheck",
        "precheck_id": f"pc-{uuid.uuid4().hex[:10]}",
        "at": utcnow(),
        "target_id": target_id,
        "status": status,
        "ready_to_fetch": status == "effective",
        "confirmation_waiver": confirmation_waiver,
        "channel": channel,
        "checks": checks,
        "blocked_reasons": blocked_reasons,
        "missing": missing,
        "robots_fetched_at": checks["robots"]["fetched_at"],
        "expires_at": (now + timedelta(
            hours=schema.ROBOTS_CACHE_MAX_HOURS)).isoformat(timespec="seconds"),
        "run_config_hash": None,  # 下行回填
    }
    import hashlib
    import json as _json
    record["run_config_hash"] = hashlib.sha256(_json.dumps(
        {"target": reg, "rate": checks["rate"]}, sort_keys=True,
        ensure_ascii=False).encode("utf-8")).hexdigest()

    from .util import append_jsonl
    append_jsonl(Path(root) / "prechecks" / f"{target_id}.jsonl", record)
    project.append_event(
        root, "precheck_blocked" if status == "blocked" else "precheck_completed",
        target_id=target_id,
        detail=f"预检结论 {status}"
               + (("：" + "；".join(blocked_reasons)) if blocked_reasons else "")
               + (("；缺项：" + "；".join(missing)) if missing else ""),
        data={"precheck_id": record["precheck_id"], "status": status})
    if lock_raised:
        project.append_event(
            root, "lock_applied", target_id=target_id,
            detail=f"项目锁下限 {lock_min}s 抬高了有效间隔至 "
                   f"{decision['effective_interval_sec']}s（只紧不松）",
            data={"precheck_id": record["precheck_id"]})
    if confirmation_waiver is not None:
        project.append_event(
            root, "browser_preauthorization_applied", target_id=target_id,
            detail=f"目标在浏览器预授权名单内（{confirmation_waiver['listed_by']} "
                   f"列入：{confirmation_waiver['reason']}），预检免逐个确认"
                   "直接生效（D1）",
            data={"precheck_id": record["precheck_id"],
                  "listed_by": confirmation_waiver["listed_by"]})
    return record


def confirm_precheck(root, target_id, confirmer: str, note: str = "") -> dict:
    """高危通道的人工确认（S4）：须具名；只对 pending_confirmation 生效。"""
    if not (confirmer or "").strip():
        raise project.WorkspaceError(
            ["确认须具名（--by）：人工确认是责任动作，不许匿名"])
    current = current_precheck(root, target_id)
    if current["status"] != "pending_confirmation":
        raise project.WorkspaceError([
            f"当前预检状态 {current['status']}，不是 pending_confirmation，"
            "无可确认项（低危通道自动生效、blocked/incomplete 须先解决点名项）"])
    row = {
        "kind": "confirmation",
        "precheck_id": current["record"]["precheck_id"],
        "at": utcnow(), "target_id": target_id,
        "confirmer": confirmer, "note": note,
    }
    from .util import append_jsonl
    append_jsonl(Path(root) / "prechecks" / f"{target_id}.jsonl", row)
    project.append_event(root, "precheck_confirmed", target_id=target_id,
                         detail=f"{confirmer} 确认预检 "
                                f"{current['record']['precheck_id']}"
                                + (f"：{note}" if note else ""),
                         data={"precheck_id": current["record"]["precheck_id"]})
    return row


def current_precheck(root, target_id) -> dict:
    """折叠某目标的预检账，给出当前生效状态（代码计算，含过期）。"""
    rows = read_jsonl(Path(root) / "prechecks" / f"{target_id}.jsonl")
    records = [r for r in rows if r.get("kind") == "precheck"]
    if not records:
        return {"status": "none", "record": None}
    latest = records[-1]
    status = latest["status"]
    if status == "pending_confirmation":
        confirmed = any(
            r.get("kind") == "confirmation"
            and r.get("precheck_id") == latest["precheck_id"] for r in rows)
        if confirmed:
            status = "effective"
    if status == "effective":
        expires = parse_ts(latest.get("expires_at"))
        if expires is not None and parse_ts(utcnow()) > expires:
            status = "expired"
    return {"status": status, "record": latest}
