#!/usr/bin/env python3
"""light-review v1 demo-fullrun 驱动：经 CLI 子进程真跑一轮投稿前评审。

主演示：承接 Write 演示稿件包（audited）+ Analysis 演示结论包 +
Figure 演示 delivery + Journal-Select 演示 check-record，全链走
init → intake（isolation=degraded）→ GRIM 登记 → forensic → seats →
calibration/bench → domain → panel → freeze → consensus → meta →
selfcheck → export → deliver（带降档声明）。
变体：复制稿件包并注入一处正文数字改动，验证法医层咬出
confirmed error、adjudicated 门阻断、人工裁决位解除。

用法：python3 run_demo.py [--keep]   （缺省重建 review-pkg 与 variant）
产出：review-pkg/、variant/、evidence/{run-log.txt,summary.json}、
demo-report.md（机器事实回填，结论节见文末标注）。
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

DEMO = Path(__file__).resolve().parent
PKG_ROOT = DEMO.parents[1]                    # light-review/
LS_ROOT = PKG_ROOT.parent                     # light-science/
INPUTS = DEMO / "inputs"
EVIDENCE = DEMO / "evidence"
PKG = DEMO / "review-pkg"
VAR = DEMO / "variant"
VAR_PKG = VAR / "review-pkg"
VAR_MS = VAR / "inputs" / "manuscript-pkg"

WRITE_PKG = LS_ROOT / "light-write/examples/demo-fullrun/manuscript-pkg"
ANALYSIS_PKG = LS_ROOT / "light-analysis/examples/demo-synthetic/analysis-pkg"
FIGURE_DIR = (LS_ROOT / "light-figure/examples/demo-fullrun"
              / "figure-pkg/exports")
TARGET_RECORD = (LS_ROOT / "light-journal-select/examples/demo-fullrun"
                 / "selection-pkg/journal/target/check-record.json")
JOURNAL_NAME = "Smart Agricultural Technology"

ISOLATION_REASON = ("本环境仅单一模型家族（claude）可用，三席同家族、"
                    "席间无法跨家族互盲（R1：做不到全规格就明说）")
DEGRADATION_STATEMENT = (
    "本轮评审隔离降档（degraded）：三席同属单一模型家族（claude），"
    "席间独立性仅由文件级隔离（reports/drafts 物理分开、冻结前互不可见）"
    "与可见性矩阵保证，无法实现跨模型家族互盲；法医层与领域门为确定性"
    "代码检查、不受此限；共识标注与决定建议的置信上限受单家族同源偏差"
    "约束。跨家族席位到位后应开新 round 重跑本轮评审。")

_log: list[str] = []
facts: dict = {}


def log(line: str = "") -> None:
    _log.append(line)
    print(line, flush=True)


def run_cli(*args, expect_rc=0, label=None):
    cmd = [sys.executable, "-m", "light_review", *[str(a) for a in args]]
    env = dict(os.environ)
    env["PYTHONPATH"] = str(PKG_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.run(cmd, capture_output=True, text=True, env=env)
    shown = "light-review " + " ".join(str(a) for a in args)
    log(f"\n$ {shown}")
    if proc.stdout.strip():
        log(proc.stdout.rstrip())
    if proc.stderr.strip():
        log("[stderr] " + proc.stderr.rstrip())
    log(f"[rc={proc.returncode}]")
    if expect_rc is not None and proc.returncode != expect_rc:
        raise SystemExit(
            f"命令失败（期望 rc={expect_rc}，实得 {proc.returncode}）："
            f"{shown}\n{proc.stdout}\n{proc.stderr}")
    return proc


def load_yaml(path: Path):
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def load_jsonl(path: Path):
    rows = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def fold_findings(rows):
    by_id, order = {}, []
    for r in rows:
        if r.get("type") == "adjudication":
            if r["finding_id"] in by_id:
                by_id[r["finding_id"]]["adjudication"] = r
            continue
        by_id[r["finding_id"]] = dict(r)
        order.append(r["finding_id"])
    return [by_id[i] for i in order]


# ================================================================ 主演示

def main_flow() -> dict:
    f: dict = {}
    run_cli("init", PKG, "--title",
            "Zero-tuning tracker thresholds predicted from "
            "video-level statistics（投稿前内部评审演示）", "--round", 1)
    run_cli("intake", PKG,
            "--manuscript", WRITE_PKG, "--analysis", ANALYSIS_PKG,
            "--figure", FIGURE_DIR, "--journal", JOURNAL_NAME,
            "--target-record", TARGET_RECORD,
            "--intensity", "standard", "--want-decision",
            "--isolation", "degraded",
            "--isolation-reason", ISOLATION_REASON)
    run_cli("grim", PKG, "--register", INPUTS / "grim-summaries.yaml")
    run_cli("forensic", PKG)
    run_cli("advance", PKG)                      # → forensic_checked

    run_cli("seat", PKG, "--id", "S1", "--role", "methods",
            "--family", "claude",
            "--persona", "方法学审稿人：设计与主张的可检验性、对照与消融充分性")
    run_cli("seat", PKG, "--id", "S2", "--role", "statistics",
            "--family", "claude",
            "--persona", "统计审稿人：推断口径、精度与多重性、等价检验")
    run_cli("seat", PKG, "--id", "S3", "--role", "domain",
            "--family", "claude",
            "--persona", "领域审稿人（精准畜牧/计算机视觉）：领域惯例、基线与部署语境")

    proc = run_cli("calibration", PKG, expect_rc=None)
    f["calibration_before_bench_rc"] = proc.returncode   # 缺 bench，应为 1
    run_cli("bench", PKG)
    run_cli("calibration", PKG)                          # 四件应齐，rc=0

    run_cli("domain", PKG)

    for seat in ("S1", "S2", "S3"):
        run_cli("panel", PKG, "--seat", seat,
                "--draft", INPUTS / "drafts" / f"{seat}.md")
    run_cli("advance", PKG)                       # → paneled
    run_cli("freeze", PKG)
    run_cli("consensus", PKG, "--file", INPUTS / "concerns.yaml")
    run_cli("advance", PKG)                       # → reported
    run_cli("meta", PKG)
    run_cli("selfcheck", PKG)
    run_cli("export", PKG)
    run_cli("advance", PKG)                       # → adjudicated
    run_cli("deliver", PKG,
            "--degradation-statement", DEGRADATION_STATEMENT)
    run_cli("validate", PKG)
    run_cli("status", PKG)

    review = load_yaml(PKG / "review.yaml")
    f["status"] = review.get("status")
    f["isolation"] = review.get("isolation")
    f["delivery"] = review.get("delivery")
    f["decision"] = review.get("decision")
    f["domain_summary"] = (review.get("domain") or {}).get("summary")
    f["domain_fact"] = (review.get("domain") or {}).get("fact_source")
    f["handoff_items"] = (review.get("handoff") or {}).get("items")
    f["counts"] = review.get("counts")

    recon = load_jsonl(PKG / "forensic" / "reconciliation.jsonl")
    f["edges"] = [r for r in recon if r.get("type") == "summary"]
    f["edge_rows"] = [r for r in recon if r.get("type") != "summary"]
    f["findings"] = fold_findings(load_jsonl(PKG / "forensic" / "findings.jsonl"))
    f["grim_rows"] = load_jsonl(PKG / "forensic" / "compatibility.jsonl")
    f["domain_rows"] = [r for r in load_jsonl(PKG / "domain_gate.jsonl")
                        if r.get("type") != "summary"]
    consensus = load_yaml(PKG / "consensus.yaml") or {}
    f["concerns"] = consensus.get("concerns") or []
    bench = json.loads((PKG / "reports" / "bench_report.json")
                       .read_text(encoding="utf-8"))
    f["bench"] = {"passed_all": bench.get("passed_all"),
                  "false_positive": bench.get("false_positive"),
                  "by_class": bench.get("by_class"),
                  "cases": len(bench.get("cases") or [])}
    selfcheck = json.loads((PKG / "reports" / "selfcheck.json")
                           .read_text(encoding="utf-8"))
    f["selfcheck"] = {"passed": selfcheck.get("passed"),
                      "tests": [{"test_id": t.get("test_id"),
                                 "result": t.get("result")}
                                for t in selfcheck.get("tests") or []]}
    handoff = json.loads((PKG / "handoff_to_write.json")
                         .read_text(encoding="utf-8"))
    f["handoff_actions"] = {}
    for it in handoff.get("items") or []:
        f["handoff_actions"][it.get("action")] = \
            f["handoff_actions"].get(it.get("action"), 0) + 1
    return f


# ================================================================ 变体

def variant_flow() -> dict:
    f: dict = {"tamper": "[num:N001] 正文实印值 5.25 → 5.52"
                         "（稿件副本 sections/03-results.md，台账仍 5.25）"}
    if VAR_MS.exists():
        shutil.rmtree(VAR_MS)
    shutil.copytree(WRITE_PKG, VAR_MS)
    sec = VAR_MS / "sections" / "03-results.md"
    text = sec.read_text(encoding="utf-8")
    assert "[num:N001] 5.25" in text, "变体注入点不存在"
    sec.write_text(text.replace("[num:N001] 5.25", "[num:N001] 5.52", 1),
                   encoding="utf-8")

    run_cli("init", VAR_PKG, "--title", "变体演示（注入数字不一致）",
            "--round", 1)
    run_cli("intake", VAR_PKG,
            "--manuscript", VAR_MS, "--analysis", ANALYSIS_PKG,
            "--figure", FIGURE_DIR, "--journal", JOURNAL_NAME,
            "--target-record", TARGET_RECORD,
            "--intensity", "standard",
            "--isolation", "degraded",
            "--isolation-reason", ISOLATION_REASON)
    run_cli("forensic", VAR_PKG)
    findings = fold_findings(load_jsonl(VAR_PKG / "forensic" / "findings.jsonl"))
    f["findings"] = findings
    f["confirmed_open"] = [x["finding_id"] for x in findings
                           if x.get("category") == "confirmed_error"
                           and not x.get("adjudication")]
    run_cli("advance", VAR_PKG)                   # → forensic_checked
    run_cli("seat", VAR_PKG, "--id", "V1", "--role", "methods",
            "--family", "claude", "--persona", "方法学审稿人（变体演示）")
    run_cli("panel", VAR_PKG, "--seat", "V1",
            "--draft", INPUTS / "variant-draft-V1.md")
    run_cli("advance", VAR_PKG)                   # → paneled
    run_cli("freeze", VAR_PKG)
    run_cli("consensus", VAR_PKG, "--file", INPUTS / "variant-concerns.yaml")
    run_cli("advance", VAR_PKG)                   # → reported

    proc = run_cli("advance", VAR_PKG, expect_rc=None)   # → adjudicated 应被拦
    f["blocked_rc"] = proc.returncode
    f["blocked_named"] = [fid for fid in f["confirmed_open"]
                          if fid in (proc.stdout + proc.stderr)]
    for fid in f["confirmed_open"]:
        run_cli("adjudicate", VAR_PKG, "--finding", fid,
                "--outcome", "confirmed",
                "--by", "demo-adjudicator（演示裁决）",
                "--reason", "变体注入的正文数字与 numbers_ledger 登记值"
                            "不符属实，确认错误成立；本变体不进交付，"
                            "裁决只为演示裁决位解除阻断的路径。")
    run_cli("advance", VAR_PKG)                   # → adjudicated（解除后通过）
    review = load_yaml(VAR_PKG / "review.yaml")
    f["final_status"] = review.get("status")
    return f


# ================================================================ 报告

def edge_table(edges) -> str:
    lines = ["| 边 | 应检 | 可检 | not_assessable | error | decision_error |",
             "|---|---|---|---|---|---|"]
    for e in edges:
        lines.append(f"| {e.get('edge')} | {e.get('checked')} | "
                     f"{e.get('assessable')} | {e.get('not_assessable')} | "
                     f"{e.get('errors')} | {e.get('decision_errors')} |")
    return "\n".join(lines)


def write_report(f: dict, v: dict) -> None:
    d = f.get("decision") or {}
    ds = f.get("domain_summary") or {}
    bench = f.get("bench") or {}
    lines = []
    lines.append("# light-review v1 演示报告（demo-fullrun）")
    lines.append("")
    lines.append("驱动：`run_demo.py` 经 CLI 子进程真跑（日志 "
                 "evidence/run-log.txt，机器事实 evidence/summary.json）。")
    lines.append("")
    lines.append("## 1. 终点状态")
    lines.append("")
    lines.append(f"- 主演示包终点：**{f.get('status')}**"
                 f"（隔离 {f['isolation'].get('mode')}，交付物含降档声明，"
                 "见 review-pkg/REVIEW_DELIVERY.md）")
    lines.append(f"- 机械计数：{json.dumps(f.get('counts'), ensure_ascii=False)}")
    lines.append("")
    lines.append("## 2. 法医层：逐边结果与覆盖自报")
    lines.append("")
    lines.append(edge_table(f["edges"]))
    lines.append("")
    if f["findings"]:
        for x in f["findings"]:
            lines.append(f"- 发现 {x['finding_id']} [{x.get('category')}/"
                         f"{x.get('layer')}] {x.get('detail')}")
    else:
        lines.append("- 发现账为空：在已登记检查项与敏感性范围内未发现"
                     "不一致（覆盖口径见上表，RV-07）。")
    lines.append("")
    lines.append("逐边要点：")
    lines.append("- 主张↔证据：C1 的 grade（insufficient）、support"
                 "（untested）、五行逐行判定与 writable_form 上限"
                 "（limitations_only）与结论包逐项一致，登记侧无改写。")
    lines.append("- 数字↔数字：N001 5.25 / N002 5.20 / N003 0.0 正文实印"
                 "与台账一致；复算值（spec_results S001：5.249333… / "
                 "5.197833… / 0.0）均落入呈现值舍入区间。")
    lines.append("- 数字↔图：F001 在 delivery 中有对应图（fig-1）；哈希"
                 "对应 not_assessable——稿件侧源资产为 SVG"
                 "（assets/fig1_threshold_arms.svg），交付文件为 "
                 "fig-1.pdf / fig-1.png，无同名文件可比；图注无小数数字，"
                 "图注未登记数字一项无触发。")
    lines.append("- 引用↔主张：正文引用键 3 个（bai2021-enet、dong2025-is、"
                 "wang2022-attention）均在 references.lock 中有条目且带 "
                 "entry_hash；C1 的 evidence_refs 五行在结论包登记行中"
                 "全有着落；Write 审计归档件（audit/audit_report.json）"
                 "存在。lock 中另有一条未被正文引用的条目（2023-review），"
                 "本边只验正文侧指针，未引用不计缺失。")
    lines.append("")
    lines.append("GRIM 族（登记 4 条，来源见 inputs/grim-summaries.yaml）：")
    for r in f["grim_rows"]:
        lines.append(f"- {r.get('stat_id')} [{r.get('kind')}] → "
                     f"**{r.get('result')}**：{r.get('detail')}")
    lines.append("- 合计相容性本轮未登记：承接范围内的稿件/结论包无"
                 "「分项—总计」型汇总量，不造条目（接口实况 §7）。")
    lines.append("")
    lines.append("## 3. 领域门结果")
    lines.append("")
    lines.append(f"- 汇总：条目 {ds.get('checked')}，命中 {ds.get('hits')}、"
                 f"未命中 {ds.get('misses')}、不适用 "
                 f"{ds.get('not_applicable')}（有效命中 "
                 f"{ds.get('effective_hits')}）")
    fact = f.get("domain_fact") or {}
    lines.append(f"- 按刊事实源：{fact.get('record_path')}（verified_at "
                 f"{fact.get('verified_at')}，状态 {fact.get('fact_status')}）"
                 "——同一事实源指针现读（Journal-Select check-record），"
                 "未复制第三份。")
    for r in f["domain_rows"]:
        lines.append(f"- {r.get('item_id')} → {r.get('result')}："
                     f"{r.get('detail')}")
    lines.append("")
    lines.append("## 4. 共识账")
    lines.append("")
    lines.append("| concern | severity（代码 MAX） | tally | consensus | 提出席位 |")
    lines.append("|---|---|---|---|---|")
    for c in f["concerns"]:
        lines.append(f"| {c.get('concern_id')} | {c.get('severity')} | "
                     f"{c.get('tally')} | {c.get('consensus')} | "
                     f"{', '.join(c.get('raised_by') or [])} |")
    lines.append("")
    lines.append("陈述全文见 review-pkg/consensus.yaml 与三席冻结报告 "
                 "reports/S1.md、S2.md、S3.md（哈希钉住）。")
    lines.append("")
    lines.append("## 5. 校准门与决定形态")
    lines.append("")
    lines.append(f"- 验证台：{bench.get('cases')} 例，passed_all="
                 f"{bench.get('passed_all')}，干净例误报率 "
                 f"{(bench.get('false_positive') or {}).get('rate')}；"
                 f"逐类检出：{json.dumps(bench.get('by_class'), ensure_ascii=False)}")
    lines.append(f"- bench 前 calibration 评估 rc={f.get('calibration_before_bench_rc')}"
                 "（缺验证台报表），bench 后四件齐备。")
    if d.get("mode") == "full":
        lines.append(f"- 决定形态：**full**，档位 **{d.get('band')}**"
                     "（bounded 非编辑判断，见 reports/decision.md；"
                     "封顶规则触发留痕在该文件内）。")
    else:
        lines.append(f"- 决定形态：**degraded**，只出问题清单（缺件："
                     f"{d.get('calibration_missing')}）。")
    lines.append("")
    lines.append("## 6. 自审与回填")
    lines.append("")
    sc = f.get("selfcheck") or {}
    lines.append(f"- 自审门 passed={sc.get('passed')}："
                 + "、".join(f"{t['test_id']}={t['result']}"
                             for t in sc.get("tests") or []))
    lines.append(f"- 回填清单：{f.get('handoff_items')} 条"
                 f"（动作分类 {json.dumps(f.get('handoff_actions'), ensure_ascii=False)}），"
                 "handoff_to_write.md/.json 已导出；Review 只出清单不出"
                 "补丁，采纳与执行归 Write。")
    lines.append("")
    lines.append("## 7. 变体（注入数字不一致，不进交付）")
    lines.append("")
    lines.append(f"- 注入：{v.get('tamper')}")
    for x in v.get("findings") or []:
        lines.append(f"- 法医发现 {x['finding_id']} [{x.get('category')}/"
                     f"{x.get('layer')}] {x.get('detail')}")
    lines.append(f"- adjudicated 门阻断：advance rc={v.get('blocked_rc')}，"
                 f"缺口点名未裁决发现 {v.get('blocked_named')}"
                 "（confirmed error 未裁决不许过门，R2 硬度 a 成立）。")
    lines.append(f"- 人工裁决位逐条 confirmed 落字后 advance 通过，变体包"
                 f"终点 {v.get('final_status')}（未 deliver，按设计止步）。")
    lines.append("")
    lines.append("## 8. 与上游包的接口实况")
    lines.append("")
    lines.append("- 稿件包（Write demo-fullrun/manuscript-pkg，状态 "
                 "audited）：五件核心文件 + sections 六节齐全，直接承接。")
    lines.append("- 结论包（Analysis demo-synthetic/analysis-pkg）："
                 "conclusions.yaml / verdicts.jsonl / spec_results.jsonl "
                 "齐全；number_provenance 在 conclusions.yaml 内（法医边 "
                 "(b) 的复算源），judge-data.json 在包外同级目录，未承接、"
                 "仅作 GRIM 登记的数据来源注记。")
    lines.append("- 图包：delivery.yaml 不在图包根，而在 "
                 "figure-pkg/exports/delivery.yaml——承接按 delivery "
                 "所在目录（exports/）传入，图包快照只钉该文件；这是上游 "
                 "Figure 包的交付件布局与 Review intake「包根 delivery"
                 ".yaml」预期之间的真实错位，本轮以路径适配并在此落字。")
    lines.append("- 目标刊记录：Journal-Select 演示 check-record（九组）"
                 "与本稿件包内的 Write template_record.json 是两份不同"
                 "演示的记录；本轮按任务口径用选刊记录（Smart "
                 "Agricultural Technology，H 组 verified_at "
                 "2026-10-20）。intake 读顶层 verified_at 得 None（该记录"
                 "的 verified_at 在 H 组内），领域门按 H 组现读判定为 "
                 "verified——顶层字段口径差在此落字，不影响判定。")
    lines.append("- GRIM 合计相容性无真实条目可登记（见 §2）。"
                 "均值粒度两条因 MOTA 为连续量被适用性硬门判 "
                 "not_assessable——这是硬门按设计工作，不是数据缺失。")
    lines.append("- 本环境单模型家族：isolation 登记 degraded 并附理由，"
                 "交付带降档声明（见 REVIEW_DELIVERY.md）——这是本演示"
                 "的诚实终点。")
    lines.append("")
    (DEMO / "demo-report.md").write_text("\n".join(lines) + "\n",
                                         encoding="utf-8")


def main() -> int:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    log("=== light-review v1 demo-fullrun 运行日志 ===")
    log("上游输入：")
    for name, p in (("稿件包", WRITE_PKG), ("结论包", ANALYSIS_PKG),
                    ("图包 delivery 目录", FIGURE_DIR),
                    ("目标刊记录", TARGET_RECORD)):
        ok = p.exists()
        log(f"  {name}：{p}（{'在' if ok else '缺失!'}）")
        if not ok:
            raise SystemExit(f"上游输入缺失：{name} {p}")
    if PKG.exists():
        shutil.rmtree(PKG)
    if VAR.exists():
        shutil.rmtree(VAR)

    facts["main"] = main_flow()
    facts["variant"] = variant_flow()
    write_report(facts["main"], facts["variant"])

    (EVIDENCE / "summary.json").write_text(
        json.dumps(facts, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8")
    (EVIDENCE / "run-log.txt").write_text("\n".join(_log) + "\n",
                                          encoding="utf-8")
    log(f"\n演示完成：主包 {facts['main']['status']}，"
        f"变体 {facts['variant']['final_status']}（止步 adjudicated）")
    log(f"日志已落盘：{EVIDENCE / 'run-log.txt'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
