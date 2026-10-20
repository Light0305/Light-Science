#!/usr/bin/env python3
"""Light-Journal-Select v1 端到端真实联网演示驱动。

主题承 Light-Literature / Light-Write 演示的那篇火鸡论文
（Zhang et al., Computers and Electronics in Agriculture 239
(2025) 110856 的研究主题）：以「火鸡异常行为检测」稿件指纹
走完整选刊链——init → fingerprint → precedent（OpenAlex
实时先例路）→ verify（逐刊联网核验）→ gate（风险门）→
report（分档证据卡）→ decide（定刊）→ handoff（journal/
target/ + check-record 过 Write 自检）→ validate。

全程经 CLI 子进程执行（`python -m light_journal_select ...`），
命令与输出 tee 进 evidence/run-log.txt；核验环节的联网取数由
本驱动完成（OpenAlex 源记录经包内 live_fetcher——Key 纪律在
包内；DOAJ 与期刊官网用本文件内的普通抓取，不带 OpenAlex
Key）。跑完产出 demo-report.md 骨架：机器可采的事实由脚本
回填，叙述性结论留「主线回填」区。

前置条件：
- 本包已安装（在 light-journal-select 目录下
  `pip install -e .`，或以其所在 venv 运行）；
- 先例路需 OpenAlex 可达：匿名走共享免费日预算，预算耗尽
  （429）时请注入用户自备的免费 Key——环境变量
  OPENALEX_API_KEY（值可能是运行时代理凭据 hsurr: 前缀，
  由主线经连接器注入；本脚本只透传环境、从不读值落字）；
- 本机出站经 https_proxy 环境代理（urllib 自动读取）。

演示替身披露（细节见 demo-report.md 第三节）：风险名单为
demo fixture（靶子是虚构刊，不命中任何真实期刊）；handoff
指南字段集为演示种子值；指南/模板文件不真下载、只落
pending_download。
"""

from __future__ import annotations

import csv
import json
import os
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
PKG = HERE / "selection-pkg"
INPUTS = HERE / "inputs"
EVIDENCE = HERE / "evidence"
LOG_PATH = EVIDENCE / "run-log.txt"
REPORT_PATH = HERE / "demo-report.md"
WRITE_ROOT = HERE.parents[2] / "light-write"

TITLE = ("Abnormal turkey behaviour detection in intensive "
         "farming using computer vision")
CEA_NAME = "Computers and Electronics in Agriculture"
CEA_GUIDE_URL = ("https://www.sciencedirect.com/journal/"
                 "computers-and-electronics-in-agriculture/"
                 "publish/guide-for-authors")
FICTIONAL_NAME = "Journal of Fictional Turkey Studies"
UA = "light-journal-select-demo/1.0"

FINGERPRINT_PAYLOAD = {
    "manuscript": {
        "abstract": (
            "We present a computer-vision method for detecting "
            "abnormal behaviour of turkeys in commercial barns. "
            "A multi-object tracker follows individual birds in "
            "top-view video; video-level statistics predict "
            "per-tracklet decision thresholds without per-video "
            "manual tuning, and abnormal events (piling, "
            "huddling, prolonged immobility) are flagged for "
            "stockperson review. On a multi-barn benchmark the "
            "method matches an oracle per-video tuned baseline "
            "while requiring no manual threshold setting."),
        "keywords": ["turkey", "abnormal behaviour detection",
                     "computer vision", "multi-object tracking",
                     "precision livestock farming"],
        "source_ref": None,
    },
    "fingerprint": {
        "field": "agricultural engineering",
        "subfield": "precision livestock farming",
        "study_object": "turkeys",
        "core_problem": "abnormal behaviour detection from barn video",
        "contribution_type": "method",
        "audience": "precision livestock farming and "
                    "agricultural engineering researchers",
        "methods_role": "core_method_contribution",
    },
    "queries": ["turkey behaviour detection",
                "poultry welfare monitoring computer vision",
                "livestock behaviour recognition tracking"],
    "constraints": {
        "tier_expectation": "challenge/target/safety 三档都要",
        "apc_budget": 3500,
        "review_cycle_limit": 12,
        "excluded_journals": None,
        "excluded_publishers": None,
        "excluded_modes": None,
        "journal_language_pref": "en",
        "recognized_catalogs": ["SCI", "Scopus"],
    },
    "constraints_confirmed": True,
}

# OpenAlex 源记录（/sources/{id} 全量记录）里取得的刊首页，
# 按刊名存：候选对象上的 homepage_url 取自 works 的脱水源
# 记录、该字段恒缺，此表是演示执行者联网核验时的实测留存，
# 供 handoff 的 H.source_url 与下载清单取用。
_HOMEPAGES: dict = {}

SCOPE_KEYWORDS = ["turkey", "poultry", "livestock",
                  "animal behaviour", "animal behavior",
                  "precision livestock", "agricultural",
                  "animal production", "animal welfare"]

# handoff 指南字段种子集（演示值）：结构照 Elsevier elsarticle
# 常规与 CEA 作者指南的公开形态填写，形态与 tests/
# test_phase2.py 的 GUIDE_FIELDS 对齐（已过 Write 校验器）。
# 纪律说明：产品口径是字段由执行者读官网指南后提供；演示以
# 种子集替代并在 demo-report 中披露，逐项数值正式使用前须对
# 官网 Guide for Authors 复核。
GUIDE_FIELDS = {
    "A": {"template_version": "elsarticle-2026",
          "applicable_years": [2026]},
    "B": {"format_track": "latex", "latex_class": "elsarticle",
          "class_version": "3.4", "options_axis": ["preprint", "review"],
          "word_template": None, "citation_package": "natbib"},
    "C": {"section_sequence": ["Abstract", "Introduction", "Methods",
                               "Results", "Discussion", "Conclusions"],
          "abstract_form": "unstructured", "keyword_limit": 6,
          "special_sections": ["CRediT authorship statement"]},
    "D": {"word_limit_total": 8000, "word_limit_abstract": 250,
          "page_limit": None, "figure_limit": None, "table_limit": None,
          "reference_limit": None, "title_char_limit": 120,
          "short_title_char_limit": 45},
    "E": {"style_name": "Elsevier Harvard", "csl_id": "elsevier-harvard",
          "bst_name": "elsarticle-harv",
          "citation_style_kind": "author-year"},
    "F": {"figure_submission_mode": "separate_files",
          "figure_formats": ["pdf", "eps", "tiff"],
          "figure_resolution": "300 dpi", "caption_position": "below"},
    "G": {"declarations": [
              {"type": "data_availability", "required": True,
               "position": "end", "field_name": "data_availability"},
              {"type": "conflict_of_interest", "required": True,
               "position": "end", "field_name": "conflict"}],
          "ai_policy": {
              "has_guideline": True, "ai_authorship_banned": True,
              "disclosure_required": True,
              "disclosure_content_standard": "tool name and purpose",
              "disclosure_title": "Declaration of generative AI use",
              "disclosure_wording_template": None,
              "disclosure_positions": ["Methods", "Acknowledgments"],
              "language_editing_stance": "allowed with disclosure",
              "publisher_conflict": {"conflict": False,
                                      "resolution_note": None},
              "output_validity_evaluation": None}},
    "I": {"redistribution": "channel_only",
          "terms_pointer": "https://www.elsevier.com/about/policies",
          "purpose_restriction": "submission use only"},
}

_log_lines: list[str] = []


def log(text: str = "") -> None:
    _log_lines.append(text)
    print(text, flush=True)


def driver_note(text: str) -> None:
    log(f"[driver] {text}")


def run_cli(*args, expect_fail: bool = False) -> tuple[int, dict]:
    cmd = [sys.executable, "-m", "light_journal_select",
           *[str(a) for a in args]]
    log(f"\n$ light-journal-select {' '.join(str(a) for a in args)}")
    proc = subprocess.run(cmd, cwd=HERE, capture_output=True, text=True)
    out = (proc.stdout or "") + (proc.stderr or "")
    log(out.rstrip())
    if expect_fail and proc.returncode == 0:
        raise SystemExit(f"期望失败但成功：{args}")
    if not expect_fail and proc.returncode != 0:
        raise SystemExit(f"命令失败（rc={proc.returncode}）：{args}\n{out}")
    try:
        return proc.returncode, json.loads(proc.stdout)
    except (json.JSONDecodeError, ValueError):
        return proc.returncode, {}


def dump_input(name: str, obj) -> Path:
    path = INPUTS / name
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
    return path


# ------------------------------------------------------------ 联网取数

def fetch_json_plain(url: str):
    """普通 JSON GET（DOAJ 等第三方）：不带 OpenAlex Key。"""
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=20) as resp:  # noqa: S310
        return json.loads(resp.read().decode("utf-8"))


def fetch_text(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310
        return resp.read(300_000).decode("utf-8", errors="replace")


def _verified(value, source_url, source_year, queried_at, provenance,
              **extra):
    entry = {"value": value, "source_url": source_url,
             "source_year": source_year, "queried_at": queried_at,
             "status": "verified", "provenance": provenance}
    entry.update(extra)
    return entry


def _unconfirmed(source_status, note):
    return {"value": None, "status": "unconfirmed",
            "source_status": source_status, "note": note}


def build_verify_record(cand: dict, today_str: str) -> dict:
    """逐刊联网核验（演示执行者）：OpenAlex/DOAJ/官网可得者
    verified，拿不到的如实 unconfirmed（JS-01/JS-02）。"""
    from light_journal_select.precedent import live_fetcher
    from light_journal_select.schema import OPENALEX_BASE

    name = cand.get("name")
    if name == FICTIONAL_NAME:
        return {"candidate": name, "source_status": "skipped",
                "metrics": {}}
    year = int(today_str[:4])
    metrics: dict = {}
    source_id = cand.get("openalex_source_id")
    short = source_id.rsplit("/", 1)[-1] if source_id else None
    src = None
    if short:
        try:
            src = live_fetcher(f"{OPENALEX_BASE}/sources/{short}")
        except Exception as exc:  # 取不到如实落 attempted，不猜
            driver_note(f"{name}：OpenAlex 源记录获取失败"
                        f"（{type(exc).__name__}），年发文量/收录落未确认")
    if src is not None:
        if src.get("homepage_url"):
            _HOMEPAGES[name] = src["homepage_url"]
        counts = {e.get("year"): e.get("works_count")
                  for e in src.get("counts_by_year") or []}
        past = [y for y in counts if isinstance(y, int) and y < year]
        if past:
            latest = max(past)
            metrics["annual_volume"] = _verified(
                counts[latest], f"https://openalex.org/{short}",
                str(latest), today_str, "aggregator")
        if src.get("is_in_doaj") is not None:
            metrics["indexing"] = _verified(
                "DOAJ 收录（OpenAlex 源记录）" if src["is_in_doaj"]
                else "未收录于 DOAJ（OpenAlex 源记录）",
                f"https://openalex.org/{short}", str(year),
                today_str, "aggregator")
    if "annual_volume" not in metrics:
        metrics["annual_volume"] = _unconfirmed(
            "attempted", "OpenAlex 源记录未取得，本轮未确认")
    # APC：DOAJ 公开 API（按 ISSN）；不在 DOAJ/无数据如实未确认
    issn = cand.get("issn")
    if issn:
        try:
            doaj = fetch_json_plain(f"https://doaj.org/api/journals/{issn}")
            apc = ((doaj.get("bibjson") or {}).get("apc") or {})
            if apc.get("has_apc") is False:
                metrics["apc"] = _verified(
                    0, f"https://doaj.org/toc/{issn}", str(year),
                    today_str, "doaj")
            elif apc.get("has_apc") and apc.get("max"):
                top = apc["max"][0]
                metrics["apc"] = _verified(
                    top.get("price"), f"https://doaj.org/toc/{issn}",
                    str(year), today_str, "doaj",
                    currency=top.get("currency"))
        except Exception:
            pass  # 落到下方 unconfirmed
    if "apc" not in metrics:
        metrics["apc"] = _unconfirmed(
            "attempted", "DOAJ 未检得该刊 APC 登记（混合刊多不在 DOAJ）")
    # scope：抓官网首页做主题词核对（JS-03 官网权威的轻量形态）
    homepage = cand.get("homepage_url")
    if homepage:
        try:
            text = fetch_text(homepage).lower()
            hits = [k for k in SCOPE_KEYWORDS if k in text]
            if len(hits) >= 2:
                metrics["scope_fit"] = _verified(
                    "strong", homepage, str(year), today_str, "official")
            elif len(hits) == 1:
                metrics["scope_fit"] = _verified(
                    "partial", homepage, str(year), today_str, "official")
        except Exception:
            pass
    if "scope_fit" not in metrics:
        metrics["scope_fit"] = _unconfirmed(
            "attempted", "官网首页未抓得或未检得主题词（页面可能需 JS 渲染）")
    # 专有指标：无开放渠道，不许凭记忆报数（JS-01/JS-11）
    for key, label in (("impact_factor", "影响因子"),
                       ("quartile_jcr", "JCR 分区"),
                       ("quartile_cas", "中科院分区")):
        metrics[key] = _unconfirmed(
            "skipped", f"{label}为专有数据（需机构订阅或用户自备 Key "
                       "实时查询），本演示未接入（JS-11）")
    metrics["self_cite_rate"] = _unconfirmed(
        "skipped", "自引率需 WoS 数据，本演示未接入")
    metrics["review_cycle"] = _unconfirmed(
        "attempted", "官网未检得可抓取的官方审稿周期统计（E4："
                     "官方无则未确认，不许众包单独定档）")
    return {"candidate": name, "source_status": "partial",
            "metrics": metrics}


# ------------------------------------------------------------ 风险门 fixture

def write_name_list(pool_names: list[str]) -> Path:
    """stop-predatory 风格名单 fixture（演示注入，来源串如实标注）。

    quasi 靶子 = 虚构刊（predatory_list_hit），不命中任何真实
    期刊；无放行记录则默认排除，演示准硬门。soft 行 = Animals
    在池时注入 volume_surge（演示注入的软警告，非真实核查
    结论），演示软警告显形。
    """
    path = INPUTS / "name-list.csv"
    rows = [{
        "name": FICTIONAL_NAME, "issn": "",
        "condition": "predatory_list_hit",
        "source": "demo-fixture 名单（stop-predatory 风格，演示注入；"
                  "靶子为虚构刊，非真实名单命中）",
        "version": "demo-0.1",
    }]
    if "Animals" in pool_names:
        rows.append({
            "name": "Animals", "issn": "",
            "condition": "volume_surge",
            "source": "demo-fixture（演示注入的软警告，"
                      "非真实核查结论）",
            "version": "demo-0.1",
        })
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh, fieldnames=["name", "issn", "condition", "source",
                            "version"])
        writer.writeheader()
        writer.writerows(rows)
    driver_note("风险名单 fixture 已生成（inputs/name-list.csv）："
                "predatory_list_hit 靶子为虚构刊、volume_surge 为"
                "演示注入软警告，来源串均如实标注 demo-fixture")
    return path


# ------------------------------------------------------------ 报告骨架

def write_report_skeleton(facts: dict) -> None:
    key_state = ("已注入（值不落字）" if facts["api_key_present"]
                 else "未注入（匿名共享预算）")
    lines = [
        "# Light-Journal-Select v1 演示报告（demo-fullrun，骨架）",
        "",
        "> 本文件由 run_demo.py 跑完后自动生成：机器可采的事实",
        "> 由脚本回填（第一节），叙述性结论留第四节「主线回填」",
        "> 区，主线核对后补写。演示身份与替身披露见第三节。",
        "",
        "## 一、运行环境与全链结果（脚本回填）",
        "",
        f"- 运行日期：{facts['today']}",
        f"- OpenAlex API Key：{key_state}",
        f"- 稿件：{TITLE}",
        f"- 选刊包：selection-pkg/（selection_id "
        f"{facts.get('selection_id')}）",
    ]
    if facts.get("aborted_at"):
        lines += [
            f"- **演示中止于：{facts['aborted_at']}**"
            f"（{facts.get('abort_reason')}）",
            "- 先例路全部查询失败时工具如实落 failed 并拒绝推进"
            "（不编造候选）；注入 OPENALEX_API_KEY 或等匿名预算"
            "重置（UTC 午夜）后重跑本脚本。",
        ]
    else:
        prec = facts["precedent"]
        lines += [
            f"- 先例路：{prec['queries_ok']}/{prec['queries_total']} "
            f"条检索式成功；入池 {len(prec['admitted'])} 刊："
            f"{', '.join(prec['admitted'])}",
            f"- 近失刊：{', '.join(prec['near_misses']) or '无'}",
            f"- 核验：{len(facts['verify_records'])} 刊落核验块"
            "（verified/unconfirmed 逐项见 selection.yaml）",
            "- 风险门等级：" + "；".join(
                f"{k} = {v}" for k, v in facts["gate_levels"].items()),
            f"- 风险门排除：{', '.join(facts['gate_excluded']) or '无'}",
            "- 分档：" + "；".join(
                f"{tier} {n} 刊"
                for tier, n in facts["tiers"].items()),
            f"- 定刊：{facts['decision']['journal']}"
            f"（{facts['decision']['decided_by']}，"
            f"{facts['decision']['decided_at']}）",
            f"- 交接自检：本地结构 {facts['handoff']['self_check']['local_structure']}"
            f" / Write 校验器 {facts['handoff']['self_check']['write_check']}",
            f"- 下载清单：已下载 {facts['manifest_counts']['downloaded']} 件"
            f" / 待下载 {facts['manifest_counts']['pending_download']} 件"
            f"（{', '.join(facts['pending_names']) or '无'}）",
            f"- 最终状态：{facts['final_status']}"
            f"（validate ok = {facts['validate_ok']}）",
        ]
    lines += [
        "",
        "## 二、产物索引",
        "",
        "- selection-pkg/selection.yaml（登记头，权威）",
        "- selection-pkg/evidence/（OpenAlex 原始响应留痕）",
        "- selection-pkg/SELECTION_REPORT.md（三档证据卡）",
        "- selection-pkg/selection.json（机器可读导出）",
        "- selection-pkg/journal/target/（download-manifest.json / "
        "check-record.json / handoff.md）",
        "- evidence/run-log.txt（全程命令与输出）、"
        "evidence/summary.json",
        "- inputs/（指纹/核验记录/名单 fixture/指南字段/下载登记）",
        "",
        "## 三、披露（演示替身与种子）",
        "",
        "1. **风险名单是 demo fixture**（inputs/name-list.csv，"
        "stop-predatory 风格）：predatory_list_hit 的靶子是演示"
        "虚构刊「Journal of Fictional Turkey Studies」（经 search "
        "路入池），不是任何真实名单对真实期刊的命中；"
        "volume_surge 软警告为演示注入、非真实核查结论。名单与"
        "报告中的来源串均如实标注 demo-fixture。",
        "2. **handoff 指南字段集是演示种子值**"
        "（inputs/guide-fields.json）：结构照 Elsevier elsarticle "
        "常规与 CEA 作者指南的公开形态填写。产品纪律是字段由"
        "执行者读官网指南后提供；演示以种子集替代，逐项数值在"
        "正式投稿前须对官网 Guide for Authors 复核。",
        "3. **指南与模板未真下载**：download-manifest 中条目"
        "均为 pending_download 并逐个点名，未伪造已下载；真文件"
        "请按 manifest 的 source_url 从官网取回后回填登记。",
        "4. **专有指标未确认**：影响因子 / JCR 分区 / 中科院"
        "分区 / 自引率无开放渠道，核验中如实落 unconfirmed"
        "（skipped），未凭记忆报数（JS-01 / JS-11）；审稿周期"
        "官网无可抓取的官方统计，落 unconfirmed（attempted）。",
        "5. 核验中的 annual_volume / indexing 来自 OpenAlex 源"
        "记录（聚合源，provenance=aggregator）、APC 来自 DOAJ "
        "公开 API、scope_fit 来自官网首页主题词核对——均为"
        "本次运行联网现查并带来源与日期（JS-01）。",
        "",
        "## 四、主线回填（跑完后由主线补写）",
        "",
        "- 演示结论：[待主线回填]",
        "- 与预期差异：[待主线回填]",
        "- 发现的问题：[待主线回填]",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    log(f"\n演示报告骨架已落盘：{REPORT_PATH}")


# ------------------------------------------------------------ 主链

def main() -> int:
    from light_journal_select.project import load_selection
    from light_journal_select.util import dump_json, today

    for target in (PKG, INPUTS, EVIDENCE):
        if target.exists():
            shutil.rmtree(target)
    INPUTS.mkdir(parents=True)
    EVIDENCE.mkdir(parents=True)
    today_str = today()
    facts: dict = {
        "today": today_str,
        "api_key_present": bool(os.environ.get("OPENALEX_API_KEY")),
    }
    log("=== Light-Journal-Select v1 demo-fullrun 运行日志 ===")
    driver_note("OpenAlex API Key："
                + ("已注入（只记有无，值不落字）"
                   if facts["api_key_present"]
                   else "未注入——匿名共享预算，耗尽时先例路将"
                        "如实 failed 并中止演示"))

    _, init_out = run_cli("init", PKG, "--title", TITLE,
                          "--language", "en", "--type", "research")
    facts["selection_id"] = init_out.get("selection_id")
    fp_path = dump_input("fingerprint.json", FINGERPRINT_PAYLOAD)
    run_cli("fingerprint", PKG, "--file", fp_path)

    _, prec = run_cli("precedent", PKG)
    if prec.get("queries_ok", 0) == 0:
        facts["aborted_at"] = "precedent（先例路）"
        facts["abort_reason"] = (
            "全部查询失败，gaps 见运行日志；多为匿名 429 预算耗尽")
        dump_json(EVIDENCE / "summary.json", facts)
        write_report_skeleton(facts)
        LOG_PATH.write_text("\n".join(_log_lines) + "\n",
                            encoding="utf-8")
        print(f"\n日志已落盘：{LOG_PATH}")
        return 2
    facts["precedent"] = prec
    driver_note(f"先例路入池：{', '.join(prec['admitted'])}")

    run_cli("add-candidate", PKG, "--name", FICTIONAL_NAME,
            "--source", "search",
            "--detail", "演示虚构刊（gate fixture 靶子，非真实期刊）")

    selection = load_selection(PKG)
    records = [build_verify_record(cand, today_str)
               for cand in selection.get("candidates") or []]
    facts["verify_records"] = [r["candidate"] for r in records]
    verify_path = dump_input("verify-records.json", records)
    run_cli("verify", PKG, "--file", verify_path)

    selection = load_selection(PKG)
    pool_names = [c["name"] for c in selection.get("candidates") or []]
    name_list = write_name_list(pool_names)
    _, gate_out = run_cli("gate", PKG, "--name-list", name_list)
    facts["gate_levels"] = gate_out["levels"]
    facts["gate_excluded"] = gate_out["excluded"]

    _, report_out = run_cli("report", PKG)
    facts["tiers"] = report_out["tiers"]

    selection = load_selection(PKG)
    cards = [c for c in selection.get("candidates") or []
             if c.get("tier")]
    if not cards:
        raise SystemExit("报告无任何证据卡候选，演示数据异常，停")
    target = next((c for c in cards if c["name"] == CEA_NAME), None)
    if target is None:
        def _evidence(cand):
            s = cand.get("precedent") or {}
            return (-(s.get("similar_works_n") or 0),
                    -(s.get("queries_covered") or 0),
                    -(s.get("rate_per_10k") or 0))
        pool = [c for c in cards if c["tier"] == "target"] or cards
        target = sorted(pool, key=_evidence)[0]
        driver_note(f"CEA 未入证据卡（分档按归一化率排序取卡，"
                    f"CEA 未进前 {len(cards)}），改按先例证据量"
                    f"（篇数→覆盖式数→归一化率）在 target 档选定："
                    f"{target['name']}（档位 {target['tier']}）")
    stats = target.get("precedent") or {}
    scope_entry = ((target.get("verification") or {}).get("metrics")
                   or {}).get("scope_fit") or {}
    scope_txt = ("官网 scope 已核验"
                 if scope_entry.get("status") == "verified"
                 else "scope_fit 未确认（官网未取得，正式投稿前"
                      "须人工核对该刊 scope）")
    reason = (
        f"演示定刊：先例 {stats.get('similar_works_n')} 篇"
        f"（归一化 {stats.get('rate_per_10k')} 篇/万篇）、风险等级 "
        f"{(target.get('risk') or {}).get('level')}、报告档位 "
        f"{target['tier']}；{scope_txt}，证据见 "
        "SELECTION_REPORT.md。由演示脚本代用户执行 CEA 优先口径"
        "的选择，正式投稿前请用户复核。")
    _, decide_out = run_cli("decide", PKG, "--candidate", target["name"],
                            "--by", "demo-author（演示代行）",
                            "--reason", reason)
    facts["decision"] = decide_out["decision"]

    fields_payload = json.loads(json.dumps(GUIDE_FIELDS))
    guide_url = (CEA_GUIDE_URL if target["name"] == CEA_NAME
                 else _HOMEPAGES.get(target["name"]))
    if guide_url:
        fields_payload["H"] = {
            "source_url": guide_url,
            "official_channel": "journal homepage",
            "verified_by": "demo driver（演示代行：指南来源 URL "
                           "取自官网/OpenAlex 源记录实测）"}
    else:
        driver_note("目标刊指南来源 URL 未取得：H 组不注入，"
                    "handoff 将如实报 H.source_url 缺失")
    fields_path = dump_input("guide-fields.json", fields_payload)
    if target["name"] == CEA_NAME:
        file_specs = [
            {"kind": "guideline", "filename": "guide-for-authors.html",
             "source_url": CEA_GUIDE_URL,
             "note": "演示环境未真下载官网指南页，待操作员从官网"
                     "取回后回填登记"},
            {"kind": "template", "filename": "elsarticle-template.zip",
             "source_url": "https://ctan.org/pkg/elsarticle",
             "note": "演示环境未真下载模板包，待从 CTAN 取回后"
                     "回填登记"},
        ]
    else:
        file_specs = [
            {"kind": "guideline", "filename": "author-guide",
             "source_url": target.get("guide_url")
             or target.get("homepage_url")
             or _HOMEPAGES.get(target["name"]),
             "note": "演示环境未真下载，待从官网取回后回填登记"},
        ]
    files_path = dump_input("download-files.json", file_specs)
    handoff_args = ["handoff", PKG, "--fields", fields_path,
                    "--files", files_path]
    if (WRITE_ROOT / "light_write").exists():
        handoff_args += ["--write-root", WRITE_ROOT]
    else:
        driver_note("light-write 姊妹包不在场：handoff 只跑本地"
                    "结构自检（Write 校验器自检 not_run）")
    _, handoff_out = run_cli(*handoff_args)
    facts["handoff"] = handoff_out

    manifest = json.loads(
        (PKG / "journal" / "target" / "download-manifest.json")
        .read_text(encoding="utf-8"))
    counts = {"downloaded": 0, "pending_download": 0}
    pending = []
    for entry in manifest.get("entries") or []:
        counts[entry["status"]] = counts.get(entry["status"], 0) + 1
        if entry["status"] == "pending_download":
            pending.append(entry["filename"])
    facts["manifest_counts"] = counts
    facts["pending_names"] = pending

    _, status_out = run_cli("status", PKG)
    facts["final_status"] = status_out["status"]
    rc_validate, _ = run_cli("validate", PKG)
    facts["validate_ok"] = rc_validate == 0

    dump_json(EVIDENCE / "summary.json", facts)
    log("\n=== summary ===\n" + json.dumps(facts, ensure_ascii=False,
                                           indent=2))
    write_report_skeleton(facts)
    LOG_PATH.write_text("\n".join(_log_lines) + "\n", encoding="utf-8")
    print(f"\n日志已落盘：{LOG_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
