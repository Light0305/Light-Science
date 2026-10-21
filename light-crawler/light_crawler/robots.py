"""robots.txt 获取与判定（RFC 9309）。

判据锚点（逐节核验过原文，见 14-crawler/deep-read.md 单元 B9）：
- 第 2.3.1.4 节（Unreachable）：服务器或网络错误导致不可达时，
  robots.txt 视为未定义，crawler 必须假定全面禁止（MUST）——
  本包的失败关闭不是自创姿态，是标准原文。
- 第 2.3.1.3 节（Unavailable）：4xx 表明不可用时可以访问（MAY）。
- 第 2.3.1.5 节：解析错误时逐行尽力解析，用可解析的规则。
- 第 2.2 节：UA 组不区分大小写，多组命中合并；路径按最长（最
  具体）规则判定，allow 与 disallow 等长时 allow 优先。
- 第 2.4 节：缓存不应超过 24 小时（预检过期口径在 precheck.py）。
- 第 2.5 节：解析至少支持 500 KiB。
- crawl-delay / request-rate 不在 RFC 9309 全文内：本模块只把
  crawl-delay 作为已登记的常见扩展事实读出，速率裁决回 schema.py，
  依据写站点公示意愿与本包自律，绝不冒充标准要求。
"""

from __future__ import annotations

import re
import urllib.error
import urllib.request
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlparse

from . import schema
from .util import parse_ts, sha256_bytes, utcnow

MAX_ROBOTS_BYTES = 500 * 1024  # 第 2.5 节下限口径：至少解析 500 KiB


class RobotsFetch:
    """一次 robots 获取的结果分类。"""

    def __init__(self, outcome, status=None, body=b"", final_url=None,
                 error=None):
        #: ok（2xx 已取到）/ unavailable（4xx）/ unreachable（5xx 或网络错误）
        self.outcome = outcome
        self.status = status
        self.body = body
        self.final_url = final_url
        self.error = error


def fetch_robots(base_url: str, timeout: float = 10.0) -> RobotsFetch:
    """取 <scheme>://<host>/robots.txt 并按状态分类。

    urllib 默认跟随重定向（上限内）；第 2.3.1.2 节要求至少跟随
    5 次，urllib 的默认行为满足下限，超限抛错归 unreachable 处理。
    """
    parts = urlparse(base_url)
    robots_url = f"{parts.scheme}://{parts.netloc}/robots.txt"
    req = urllib.request.Request(
        robots_url, headers={"User-Agent": schema.USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read(MAX_ROBOTS_BYTES + 1)[:MAX_ROBOTS_BYTES]
            return RobotsFetch("ok", status=resp.status, body=body,
                               final_url=resp.geturl())
    except urllib.error.HTTPError as e:
        if 400 <= e.code < 500:
            return RobotsFetch("unavailable", status=e.code,
                               final_url=robots_url)
        return RobotsFetch("unreachable", status=e.code,
                           final_url=robots_url,
                           error=f"HTTP {e.code}")
    except Exception as e:  # URLError / timeout / DNS 等一切网络错误
        return RobotsFetch("unreachable", status=None,
                           final_url=robots_url,
                           error=f"{type(e).__name__}: {e}")


# ------------------------------------------------ 预检缓存（D8，2026-10-21 批准落地）

def cache_body_relpath(body_sha256: str) -> str:
    """预检 robots 原文的缓存落点（按内容哈希寻址，与 store 同理）。"""
    return f"prechecks/robots-cache/{body_sha256[:2]}/{body_sha256}"


def store_cached_body(root, fetch: RobotsFetch) -> str | None:
    """预检侧调用：把取到的 robots 原文按哈希落进缓存，返回相对路径。

    只有 outcome=ok 且有原文时才落；4xx（unavailable）无原文，其
    结论本身（状态码）随预检记录即可复用，不需要本体文件。
    """
    if fetch.outcome != "ok" or not fetch.body:
        return None
    digest = sha256_bytes(fetch.body)
    rel = cache_body_relpath(digest)
    dest = Path(root) / rel
    if not dest.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(fetch.body)
    return rel


def resolve_robots(root, base_url: str, record: dict | None = None,
                   timeout: float = 10.0):
    """执行期 robots 的统一取用口（D8）：先预检缓存，后实时取。

    返回 (RobotsFetch, info)。info["source"] 为 "precheck_cache"
    （命中复用、本次零网络请求）或 "fresh"；复用落空且属缓存损坏
    时 info["cache_invalidated"] 给出原因（hash_mismatch /
    body_missing），调用方据此落 robots_cache_invalidated 事件。

    复用条件（三者齐备）：预检记录在册、robots 取回时刻未超
    24 小时（RFC 9309 第 2.4 节，与预检 expires_at 同口径）、
    缓存原文哈希与预检记录 body_sha256 逐字相符。过期不算损坏
    （预检层会先以 expired 挡住执行），这里静默回落实时取。
    """
    info = {"source": "fresh", "cache_invalidated": None,
            "precheck_id": (record or {}).get("precheck_id")}
    if record:
        rob = ((record.get("checks") or {}).get("robots")) or {}
        fetched_at = record.get("robots_fetched_at") or rob.get("fetched_at")
        ts = parse_ts(fetched_at) if fetched_at else None
        fresh = (ts is not None and parse_ts(utcnow()) <= ts + timedelta(
            hours=schema.ROBOTS_CACHE_MAX_HOURS))
        if fresh:
            outcome = rob.get("outcome")
            if outcome == "unavailable":
                info["source"] = "precheck_cache"
                return RobotsFetch("unavailable", status=rob.get(
                    "http_status"), final_url=base_url), info
            sha = rob.get("body_sha256")
            if outcome == "ok" and sha:
                dest = Path(root) / cache_body_relpath(sha)
                if not dest.exists():
                    info["cache_invalidated"] = "body_missing"
                else:
                    body = dest.read_bytes()
                    if sha256_bytes(body) != sha:
                        info["cache_invalidated"] = "hash_mismatch"
                    else:
                        info.update({"source": "precheck_cache",
                                     "body_sha256": sha})
                        return RobotsFetch(
                            "ok", status=rob.get("http_status"), body=body,
                            final_url=base_url), info
    return fetch_robots(base_url, timeout=timeout), info


class RobotsRules:
    """解析后的规则集：判定 + crawl-delay 事实读出。"""

    def __init__(self, rules, crawl_delay=None, sitemaps=(),
                 parse_warnings=()):
        #: rules: list[(kind, pattern)]，kind in {"allow", "disallow"}
        self.rules = rules
        self.crawl_delay = crawl_delay
        self.sitemaps = list(sitemaps)
        self.parse_warnings = list(parse_warnings)

    def is_allowed(self, path: str):
        """最长匹配判定（第 2.2 节）。返回 (allowed, matched_rule|None)。"""
        best = None  # (specificity, kind, pattern)
        for kind, pattern in self.rules:
            spec = _match_specificity(pattern, path)
            if spec is None:
                continue
            if (best is None or spec > best[0]
                    or (spec == best[0] and kind == "allow")):
                best = (spec, kind, pattern)
        if best is None:
            return True, None
        return best[1] == "allow", {"kind": best[1], "pattern": best[2]}


def _match_specificity(pattern: str, path: str):
    """RFC 9309 路径匹配：支持 * 通配与 $ 结尾锚。

    返回具体度（匹配到的模式字面长度）或 None（不匹配）。
    """
    if not pattern:
        return None
    anchored = pattern.endswith("$")
    core = pattern[:-1] if anchored else pattern
    regex = "^" + re.escape(core).replace(r"\*", ".*")
    if anchored:
        regex += "$"
    if re.match(regex, path):
        return len(core)
    return None


def parse_robots(body: bytes, our_token: str = None) -> RobotsRules:
    """逐行尽力解析（第 2.3.1.5 节）：坏行记 warning 并跳过，不整体放弃。

    组匹配（第 2.2 节）：UA 行不区分大小写；命中我们 token 的组与
    通配组（*）合并适用。crawl-delay 取合并组中的最大值（取严方向），
    只是扩展事实读出，标准内无此字段。
    """
    token = (our_token or schema.ROBOTS_AGENT_NAME).lower()
    text = body.decode("utf-8-sig", errors="replace")
    groups = []          # list[(agents:set, rules:list, delays:list)]
    agents, rules, delays = set(), [], []
    sitemaps, warnings = [], []
    seen_rule = False

    def flush():
        nonlocal agents, rules, delays, seen_rule
        if agents:
            groups.append((agents, rules, delays))
        agents, rules, delays = set(), [], []
        seen_rule = False

    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if ":" not in line:
            warnings.append(f"第 {lineno} 行无冒号分隔，已跳过")
            continue
        key, _, value = line.partition(":")
        key, value = key.strip().lower(), value.strip()
        if key == "user-agent":
            if seen_rule:
                flush()
            agents.add(value.lower())
        elif key in ("allow", "disallow"):
            if not agents:
                warnings.append(f"第 {lineno} 行规则出现在任何 user-agent 之前，已跳过")
                continue
            seen_rule = True
            rules.append((key, value))
        elif key == "crawl-delay":
            if not agents:
                continue
            seen_rule = True
            try:
                delays.append(float(value))
            except ValueError:
                warnings.append(f"第 {lineno} 行 crawl-delay 非数值，已跳过")
        elif key == "sitemap":
            sitemaps.append(value)
        # 其余扩展字段忽略不记警告（逐行尽力口径）
    flush()

    merged_rules, merged_delays = [], []
    for g_agents, g_rules, g_delays in groups:
        if token in g_agents or "*" in g_agents:
            merged_rules.extend(g_rules)
            merged_delays.extend(g_delays)
    crawl_delay = max(merged_delays) if merged_delays else None
    return RobotsRules(merged_rules, crawl_delay=crawl_delay,
                       sitemaps=sitemaps, parse_warnings=warnings)


def check_url(fetch: RobotsFetch, url: str) -> dict:
    """对一个具体 URL 给出 robots 结论（供预检逐项落字）。

    返回 dict: outcome / allowed / basis（RFC 节号）/ matched_rule /
    crawl_delay_sec / detail。
    """
    if fetch.outcome == "unreachable":
        return {
            "outcome": "unreachable", "allowed": False,
            "basis": "RFC 9309 2.3.1.4",
            "matched_rule": None, "crawl_delay_sec": None,
            "detail": ("robots.txt 不可达（5xx 或网络错误），视为未定义，"
                       "必须假定全面禁止（失败关闭）"
                       + (f"；错误：{fetch.error}" if fetch.error else "")),
        }
    if fetch.outcome == "unavailable":
        return {
            "outcome": "unavailable", "allowed": True,
            "basis": "RFC 9309 2.3.1.3",
            "matched_rule": None, "crawl_delay_sec": None,
            "detail": "robots.txt 以 4xx 表明不可用，即无 robots 限制，可以访问",
        }
    rules = parse_robots(fetch.body)
    parts = urlparse(url)
    path = parts.path or "/"
    if parts.query:
        path = f"{path}?{parts.query}"
    allowed, matched = rules.is_allowed(path)
    return {
        "outcome": "ok", "allowed": allowed,
        "basis": "RFC 9309 2.2",
        "matched_rule": matched, "crawl_delay_sec": rules.crawl_delay,
        "detail": ("命中规则 " + (f"{matched['kind']}: {matched['pattern']}"
                                 if matched else "无（默认允许）")),
        "parse_warnings": rules.parse_warnings,
        "sitemaps": rules.sitemaps,
    }
