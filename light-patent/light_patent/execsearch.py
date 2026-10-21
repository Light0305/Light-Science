"""P2 检索执行通道（第四批 P1）：把两轮召回从规程落成可跑执行。

分工（LD-02 不变）：合规门归 light-crawler——本模块只驱动
crawler 的 CLI（init/register/precheck/confirm/gate-check/
fetch）并回读其工作区账目（prechecks/provenance/store），不复制
任何一道门。专利侧前置纪律不变：渠道须先在渠道层启用
（自动化渠道登记 crawler 预检引用、API 渠道登记披露确认），
检索式只经 channels.build_query 最小披露构造。

结果落既有登记形态：novelty.register_search 写 search_log +
候选池；执行轨迹另落 novelty/exec/ 逐次 YAML（渠道、预检号、
provenance 号、命中与解析数、自评状态）。失败分型按 LP-06：
门未过/被拒/传输失败 = channel_failure（点名原因），取回成功
但列表为空 = zero_results，取回页无结果标记（JS 壳/WAF 页）
= channel_failure 并点名形态——绝不把没取到写成无现有技术。

EPO OPS（官方 API 通道）：census 第 7.4 节口径——OPS 是 REST
API、OAuth2 注册凭据、免费 4 GB/周、search 约 10 次/分/IP 的
公平使用线。robots 不适用（授权 API 访问）；纪律映射为：渠道
登记 + 披露确认（启用门）、单次执行只发一条 search 请求、
429/403 即停不重试、凭据只从环境变量读、永不落盘。凭据缺失
时返回 credential_gap 状态（不写检索日志、不冒充已检索），
登记为待用户提供 OPS 注册凭据的缺口。
"""

from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path

from . import channels, novelty, schema
from .intake import require_audited
from .project import PatentError, load_case
from .util import dump_yaml, read_jsonl, today

# ---------------------------------------------------------------- epub 通道

EPUB_BASE_URL = "https://epub.cnipa.gov.cn"
EPUB_TARGET_ID = "cnipa-epub"
#: epub 高级查询结果页端点形态：以站点当期结构为准，由
#: parse_epub_results 的结果标记校验兜底——端点形态漂移时解析
#: 零命中且无标记 → channel_failure 点名，不冒充 zero_results。
EPUB_SEARCH_PATH = "/Dxb/IndexQuery"

#: OPS 官方端点（3.2 REST）。
OPS_TOKEN_URL = "https://ops.epo.org/3.2/auth/accesstoken"
OPS_SEARCH_URL = ("https://ops.epo.org/3.2/rest-services/"
                  "published-data/search")


def epub_search_url(query: str) -> str:
    """由最小披露检索式构造 epub 查询 URL（公布模式，每页 10 条）。"""
    return (EPUB_BASE_URL + EPUB_SEARCH_PATH + "?"
            + urllib.parse.urlencode({"query": query}))


_RESULT_ROW_HINTS = ("公布公告", "申请公布号", "申请人", "公开（公告）日")


def parse_epub_results(html: str) -> dict:
    """解析 epub 结果列表页 → 候选池条目。

    返回 {is_result_page, entries}。is_result_page=False 表示页面
    无结果列表标记（JS 壳/WAF/错误页），调用方按 channel_failure
    点名，不许记 zero_results。条目著录来自列表页，未逐项核验：
    verified=False、evidence_level=abstract（LP-01）。
    """
    import re
    _lb, _rb = "\u3010", "\u3011"  # epub labels brackets, escaped in source

    if not html or not any(h in html for h in _RESULT_ROW_HINTS):
        return {"is_result_page": False, "entries": []}
    entries = []
    # 结果条目块：以公开号锚点切分（CN + 9 位数字 + 种类码）。
    for m in re.finditer(r"(CN\d{9}[A-Z]\d?)", html):
        pub = m.group(1)
        if any(e["pub_number"] == pub for e in entries):
            continue
        window = html[max(0, m.start() - 2000): m.start() + 4000]
        title_m = re.search(_lb + "发明名称" + _rb + r"\s*([^<" + _lb + "]{2,80})", window) \
            or re.search(r"title=\"([^\"]{2,80})\"", window)
        appl_m = re.search(_lb + "申请人" + _rb + r"\s*([^<" + _lb + "]{2,60})", window)
        date_m = re.search(r"(20\d{2}-\d{2}-\d{2})", window)
        ipc_m = re.search(_lb + "国际分类号" + _rb + r"\s*([A-HY]\d{2}[A-Z]?\s*\d+/\d+)",
                          window)
        entries.append({
            "pub_number": pub,
            "title": (title_m.group(1).strip() if title_m else ""),
            "applicant": (appl_m.group(1).strip() if appl_m else ""),
            "pub_date": (date_m.group(1) if date_m else ""),
            "url": f"{EPUB_BASE_URL}/Detail/{pub}",
            "verified": False,
            "evidence_level": "abstract",
            "relevance": None,
            # 供第二轮分类号邻域构造（register_search 落池时不带此键）
            "ipc": (ipc_m.group(1).replace(" ", "") if ipc_m else ""),
        })
    return {"is_result_page": True, "entries": entries}


# ---------------------------------------------------------------- crawler 驱动

def resolve_crawler_home(explicit=None) -> Path:
    """定位 light-crawler 包根（含 light_crawler/ 子目录）。

    顺序：显式入参 → 环境变量 LIGHT_CRAWLER_HOME → 同仓兄弟包
    （工作树与发布树均为同级布局）→ 当前解释器可直接 import。
    都落空时点名缺口，不许静默降级为自研抓取。
    """
    cands = []
    if explicit:
        cands.append(Path(explicit))
    env = os.environ.get("LIGHT_CRAWLER_HOME")
    if env:
        cands.append(Path(env))
    here = Path(__file__).resolve()
    for parent in (here.parents[2], here.parents[2] / "release"):
        cands.append(parent / "light-crawler")
    for c in cands:
        if (c / "light_crawler" / "__init__.py").exists():
            return c
    try:
        import light_crawler  # noqa: F401
        return Path(light_crawler.__file__).resolve().parent.parent
    except ImportError:
        raise PatentError([
            "找不到 light-crawler 包：检索执行经 crawler 通道层，"
            "缺其包即无执行通道（设 LIGHT_CRAWLER_HOME 或与本包同仓放置）"])


def _default_cli_runner(argv, crawler_home):
    env = dict(os.environ)
    pp = str(crawler_home)
    if env.get("PYTHONPATH"):
        pp = pp + os.pathsep + env["PYTHONPATH"]
    env["PYTHONPATH"] = pp
    proc = subprocess.run(
        [sys.executable, "-m", "light_crawler", *argv],
        capture_output=True, text=True, env=env, timeout=600)
    return {"returncode": proc.returncode,
            "stdout": proc.stdout, "stderr": proc.stderr}


def _epub_target_registration(case: dict) -> dict:
    return {
        "target_id": EPUB_TARGET_ID,
        "name": "中国专利公布公告系统（light-patent 查新执行通道）",
        "base_url": EPUB_BASE_URL,
        "project": case["case_id"],
        "purpose_kind": "project_data",
        "consumer": "light-patent P2 检索查新",
        "channel": "web_page",
        "terms_basis": ("国家知识产权局专利公布公告系统使用说明"
                        "（官网在线版）：官方免费公开查询、无需登录；"
                        "自动化使用逐目标过 light-crawler 预检并留痕"),
        "personal_data_risk": "none",
        "rate": {"max_requests_per_run": 5, "max_requests_per_day": 50},
    }


def _latest_precheck(ws: Path) -> dict | None:
    rows = read_jsonl(ws / "prechecks" / f"{EPUB_TARGET_ID}.jsonl")
    recs = [r for r in rows if r.get("kind") == "precheck"]
    return recs[-1] if recs else None


def _latest_fetch_prov(ws: Path, url: str) -> dict | None:
    rows = [r for r in read_jsonl(ws / "provenance.jsonl")
            if r.get("kind") == "fetch" and r.get("url") == url]
    return rows[-1] if rows else None


def _write_exec_trace(root, trace: dict) -> Path:
    dest_dir = Path(root) / "novelty" / "exec"
    dest_dir.mkdir(parents=True, exist_ok=True)
    name = f"{today()}-{trace['channel_id']}-{trace['round']}.yaml"
    dest = dest_dir / name
    n = 2
    while dest.exists():
        dest = dest_dir / (f"{today()}-{trace['channel_id']}-"
                           f"{trace['round']}-{n}.yaml")
        n += 1
    dump_yaml(dest, trace)
    return dest


def execute_epub_search(root, payload: dict, *, cli_runner=None) -> dict:
    """经 light-crawler 执行一轮 epub 检索并登记进案件查新账。

    payload: {round, ipc_codes, means_phrases, crawler_workspace?,
    crawler_home?, confirmer?}。confirmer 仅在预检落
    pending_confirmation 时用：具名确认是责任动作，缺名即停在
    预检后点名，不代签。
    """
    root = Path(root)
    case = load_case(root)
    require_audited(root, case)
    runner = cli_runner or _default_cli_runner
    state = channels.load_channel_state(root)
    ch_state = state.get("cnipa-epub-automation") or {}
    if not ch_state.get("enabled"):
        raise PatentError([
            "渠道 cnipa-epub-automation 未启用：先 channel-enable 并"
            "登记 crawler_precheck_ref（本包只点名校验，不代行预检门）"])
    rnd = payload.get("round")
    if rnd not in schema.SEARCH_ROUNDS:
        raise PatentError([f"检索轮次 {rnd!r} 不在两轮词表内"])
    query = channels.build_query(
        case, ipc_codes=payload.get("ipc_codes"),
        means_phrases=payload.get("means_phrases"))
    crawler_home = resolve_crawler_home(payload.get("crawler_home"))
    ws = Path(payload.get("crawler_workspace")
              or (root / "novelty" / "crawler-ws"))
    trace = {"kind": "light-patent/search-exec-trace",
             "case_id": case["case_id"], "at": today(),
             "channel_id": "cnipa-epub-automation", "round": rnd,
             "query": query, "crawler_workspace": str(ws),
             "steps": [], "precision_assessment": "pending_human",
             "recall_note": "单页（公布模式 10 条）口径；召回深度自评"
                            "须与人工渠道同题对拍后落字（PLAN 11.4），"
                            "本轨迹不自报查全率"}

    def step(name, **kw):
        trace["steps"].append({"step": name, **kw})

    def fail(note):
        novelty.register_search(root, {
            "round": rnd, "channel_id": "cnipa-epub-automation",
            "query": query, "outcome": "channel_failure",
            "note": note, "results": []})
        trace["outcome"] = "channel_failure"
        trace["note"] = note
        path = _write_exec_trace(root, trace)
        return {"outcome": "channel_failure", "query": query,
                "note": note, "trace": str(path.relative_to(root))}

    # 1) 工作区与目标登记（幂等：已存在则不重复）
    if not (ws / "crawler.yaml").exists():
        out = runner(["--root", str(ws), "init",
                      "--project", case["case_id"]], crawler_home)
        step("crawler_init", returncode=out["returncode"])
        if out["returncode"] != 0:
            return fail(f"crawler 工作区初始化失败：{out['stderr'][:200]}")
    if not (ws / "targets" / EPUB_TARGET_ID / "target.yaml").exists():
        reg_path = root / "novelty" / "exec" / "cnipa-epub-target.yaml"
        reg_path.parent.mkdir(parents=True, exist_ok=True)
        dump_yaml(reg_path, _epub_target_registration(case))
        out = runner(["--root", str(ws), "register",
                      "--file", str(reg_path)], crawler_home)
        step("crawler_register", returncode=out["returncode"])
        if out["returncode"] != 0:
            return fail("crawler 目标登记失败："
                        f"{(out['stdout'] + out['stderr'])[:200]}")

    # 2) 预检（crawler 自己的门）+ 必要时具名确认
    out = runner(["--root", str(ws), "precheck",
                  "--target", EPUB_TARGET_ID], crawler_home)
    rec = _latest_precheck(ws)
    step("crawler_precheck", returncode=out["returncode"],
         precheck_id=(rec or {}).get("precheck_id"),
         status=(rec or {}).get("status"))
    if rec is None:
        return fail("crawler 预检未落记录（执行环境异常）")
    if rec.get("status") == "pending_confirmation":
        confirmer = (payload.get("confirmer") or "").strip()
        if not confirmer:
            trace["outcome"] = "awaiting_confirmation"
            trace["note"] = ("预检落 pending_confirmation（web_page 高危"
                             "通道）：须具名确认后才许 fetch，本次未发起"
                             "任何检索请求")
            path = _write_exec_trace(root, trace)
            return {"outcome": "awaiting_confirmation", "query": query,
                    "precheck_id": rec.get("precheck_id"),
                    "note": trace["note"],
                    "trace": str(path.relative_to(root))}
        out = runner(["--root", str(ws), "confirm", "--target",
                      EPUB_TARGET_ID, "--by", confirmer,
                      "--note", "light-patent 查新执行通道确认"],
                     crawler_home)
        step("crawler_confirm", returncode=out["returncode"], by=confirmer)
    out = runner(["--root", str(ws), "gate-check", "--target",
                  EPUB_TARGET_ID, "--json"], crawler_home)
    step("crawler_gate_check", returncode=out["returncode"])
    if out["returncode"] != 0:
        detail = out["stdout"].strip()[:300] or out["stderr"].strip()[:300]
        return fail(f"crawler 预检门未放行：{detail}")

    # 3) fetch 检索页（guard 在 crawler 侧：robots/速率/429 即停）
    url = epub_search_url(query)
    out = runner(["--root", str(ws), "fetch", "--target",
                  EPUB_TARGET_ID, "--url", url], crawler_home)
    step("crawler_fetch", returncode=out["returncode"], url=url)
    prov = _latest_fetch_prov(ws, url)
    if prov is None:
        detail = (out["stdout"] + out["stderr"]).strip()[:300]
        return fail(f"crawler fetch 未落 provenance（被拒或失败）：{detail}")
    trace["provenance_id"] = prov.get("prov_id")
    trace["precheck_id"] = prov.get("precheck_ref")
    trace["http_status"] = prov.get("http_status")
    if prov.get("http_status") != 200:
        return fail(f"epub 返回 HTTP {prov.get('http_status')}（crawler 已"
                    "按其纪律记账，本包不重试）")
    raw = (ws / prov["raw_path"]).read_bytes() \
        if prov.get("raw_path") else b""
    html = raw.decode("utf-8", errors="replace")
    parsed = parse_epub_results(html)
    trace["parsed_entries"] = len(parsed["entries"])
    if not parsed["is_result_page"]:
        return fail("取回页无结果列表标记（疑似 JS 驱动/WAF 页）：静态"
                    "通道未取得结果列表，不记 zero_results")
    entries = parsed["entries"]
    outcome = "ok" if entries else "zero_results"
    note = (f"经 light-crawler 执行（预检 {prov.get('precheck_ref')}、"
            f"provenance {prov.get('prov_id')}）；列表页著录未逐项核验，"
            "池内条目 verified=false（LP-01）")
    novelty.register_search(root, {
        "round": rnd, "channel_id": "cnipa-epub-automation",
        "query": query, "outcome": outcome, "note": note,
        "results": entries})
    trace["outcome"] = outcome
    trace["note"] = note
    # 第二轮衔接：按 SKILL 第 6 节两轮规程，从第一轮结果抽 IPC
    # 高频号（主组口径）作分类号邻域候选，只建议不自动发第二轮。
    from collections import Counter
    ipc_counts = Counter(
        e["ipc"].split("/")[0] for e in entries if e.get("ipc"))
    suggested = [code for code, _ in ipc_counts.most_common(3)]
    trace["suggested_round2_ipc"] = suggested
    path = _write_exec_trace(root, trace)
    return {"outcome": outcome, "query": query, "hits": len(entries),
            "pool_added": len(entries), "note": note,
            "trace": str(path.relative_to(root)),
            "suggested_round2_ipc": suggested}


# ---------------------------------------------------------------- EPO OPS

def ops_query(case: dict, *, ipc_codes=None, means_phrases=None) -> str:
    """把最小披露要素翻成 OPS CQL（分类号 ipc= / 全文 txt=）。"""
    channels.build_query(case, ipc_codes=ipc_codes,
                         means_phrases=means_phrases)  # 纪律校验复用
    parts = []
    for c in ipc_codes or []:
        parts.append(f"ipc={c.strip()}")
    for ph in means_phrases or []:
        parts.append(f'txt="{ph}"')
    return " and ".join(parts)


def parse_ops_results(xml_bytes: bytes) -> list:
    """解析 OPS published-data search 的 XML → 候选池条目。

    search 端点只回公开文献号（docdb document-id），题名/申请人
    须 biblio 端点逐条取——本批不逐条取数，字段留空并在登记
    note 中点名（不编造著录，LP-01）。日期取 document-id 的
    date（公开日）。verified=False（未逐项核验）。
    """
    import xml.etree.ElementTree as ET

    ns = {"ops": "http://ops.epo.org",
          "epo": "http://www.epo.org/exchange/documents"}
    root_el = ET.fromstring(xml_bytes)
    entries = []
    for ref in root_el.iter("{http://ops.epo.org}publication-reference"):
        doc_id = None
        for cand in ref.iter(
                "{http://www.epo.org/exchange/documents}document-id"):
            if cand.get("document-id-type") == "docdb":
                doc_id = cand
                break
        if doc_id is None:
            continue

        def _t(tag):
            el = doc_id.find(f"epo:{tag}", ns)
            return (el.text or "").strip() if el is not None and el.text \
                else ""

        country, number, kind, date = (_t("country"), _t("doc-number"),
                                       _t("kind"), _t("date"))
        if not country or not number:
            continue
        pub_date = (f"{date[:4]}-{date[4:6]}-{date[6:8]}"
                    if len(date) == 8 and date.isdigit() else date)
        entries.append({
            "pub_number": f"{country}{number}{kind}",
            "title": "", "applicant": "", "pub_date": pub_date,
            "url": ("https://worldwide.espacenet.com/patent/search?q=pn%3D"
                    f"{country}{number}{kind}"),
            "verified": False, "evidence_level": "abstract",
            "relevance": None,
        })
    return entries


def _ops_default_transport(method, url, *, headers=None, data=None,
                           timeout=60):
    req = urllib.request.Request(url, data=data, method=method,
                                 headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return {"status": resp.status, "body": resp.read()}
    except urllib.error.HTTPError as e:
        return {"status": e.code, "body": e.read() or b""}


def _ops_fail(root, trace, rnd, query, note):
    novelty.register_search(root, {
        "round": rnd, "channel_id": "epo-ops-api", "query": query,
        "outcome": "channel_failure", "note": note, "results": []})
    trace["outcome"] = "channel_failure"
    trace["note"] = note
    path = _write_exec_trace(root, trace)
    return {"outcome": "channel_failure", "query": query, "note": note,
            "trace": str(path.relative_to(root))}


def execute_ops_search(root, payload: dict, *, transport=None,
                       environ=None) -> dict:
    """EPO OPS 检索执行（一条 search 请求为限；429/403 即停）。

    凭据只从环境变量 EPO_OPS_CONSUMER_KEY / _SECRET 读；缺失 →
    credential_gap（不写检索日志、不发任何请求）。
    """
    root = Path(root)
    case = load_case(root)
    require_audited(root, case)
    state = channels.load_channel_state(root)
    ch_state = state.get("epo-ops-api") or {}
    if not ch_state.get("enabled"):
        raise PatentError([
            "渠道 epo-ops-api 未启用：先 channel-enable 并登记披露"
            "考量确认（disclosure_acknowledged）"])
    rnd = payload.get("round")
    if rnd not in schema.SEARCH_ROUNDS:
        raise PatentError([f"检索轮次 {rnd!r} 不在两轮词表内"])
    query = ops_query(case, ipc_codes=payload.get("ipc_codes"),
                      means_phrases=payload.get("means_phrases"))
    env = environ if environ is not None else os.environ
    key = env.get("EPO_OPS_CONSUMER_KEY") or ""
    secret = env.get("EPO_OPS_CONSUMER_SECRET") or ""
    trace = {"kind": "light-patent/search-exec-trace",
             "case_id": case["case_id"], "at": today(),
             "channel_id": "epo-ops-api", "round": rnd, "query": query,
             "precision_assessment": "pending_human",
             "recall_note": "OPS search 单请求口径（Range 1-25）；"
                            "查全/查准自评须人工对拍后落字"}
    if not key or not secret:
        trace["outcome"] = "credential_gap"
        trace["note"] = ("OPS 凭据缺失（环境变量 EPO_OPS_CONSUMER_KEY /"
                         " EPO_OPS_CONSUMER_SECRET 未设置）：未发出任何"
                         "请求；待用户在 developers.epo.org 完成 OPS "
                         "注册后注入凭据再跑")
        path = _write_exec_trace(root, trace)
        return {"outcome": "credential_gap", "query": query,
                "note": trace["note"], "trace": str(path.relative_to(root))}
    http = transport or _ops_default_transport
    basic = base64.b64encode(f"{key}:{secret}".encode()).decode()
    tok = http("POST", OPS_TOKEN_URL,
               headers={"Authorization": f"Basic {basic}",
                        "Content-Type": "application/x-www-form-urlencoded"},
               data=b"grant_type=client_credentials")
    if tok["status"] != 200:
        return _ops_fail(root, trace, rnd, query,
                         f"OPS OAuth 取 token 失败 HTTP {tok['status']}"
                         "（即停不重试）")
    try:
        token = json.loads(tok["body"].decode("utf-8"))["access_token"]
    except Exception:
        return _ops_fail(root, trace, rnd, query,
                         "OPS OAuth 响应无 access_token（形态异常，即停）")
    url = OPS_SEARCH_URL + "?" + urllib.parse.urlencode(
        {"q": query, "Range": "1-25"})
    resp = http("GET", url, headers={"Authorization": f"Bearer {token}",
                                     "Accept": "application/xml"})
    if resp["status"] != 200:
        return _ops_fail(root, trace, rnd, query,
                         f"OPS search 返回 HTTP {resp['status']}"
                         "（429/403 等一律即停不重试，公平使用口径）")
    entries = parse_ops_results(resp["body"])
    outcome = "ok" if entries else "zero_results"
    note = ("经 EPO OPS 官方 API 执行（单请求，Range 1-25）；search "
            "端点只回文献号与公开日，题名/申请人未取（biblio 逐条取数"
            "不在本批），条目 verified=false（LP-01）")
    novelty.register_search(root, {
        "round": rnd, "channel_id": "epo-ops-api", "query": query,
        "outcome": outcome, "note": note, "results": entries})
    trace["outcome"] = outcome
    trace["note"] = note
    trace["parsed_entries"] = len(entries)
    path = _write_exec_trace(root, trace)
    return {"outcome": outcome, "query": query, "hits": len(entries),
            "note": note, "trace": str(path.relative_to(root))}


def execute_search(root, payload: dict, **kwargs) -> dict:
    """执行入口：按 channel_id 分发（epub 自动化 / OPS API）。"""
    channel_id = payload.get("channel_id") or "cnipa-epub-automation"
    if channel_id == "epo-ops-api":
        return execute_ops_search(
            root, payload,
            transport=kwargs.get("ops_transport"),
            environ=kwargs.get("environ"))
    if channel_id == "cnipa-epub-automation":
        return execute_epub_search(
            root, payload, cli_runner=kwargs.get("cli_runner"))
    raise PatentError([
        f"渠道 {channel_id!r} 无执行通道：可执行渠道只有 "
        "cnipa-epub-automation（经 light-crawler）与 epo-ops-api"
        "（官方 API）；人工渠道仍走 search 登记"])
