#!/usr/bin/env python3
"""light-memory Phase 3 真实演示驱动（全链经 CLI 子进程真跑）。

沿火鸡主线把全项目九包 + 选刊的真实演示产物收编进一个真实记忆
项目（world/proj-a），外加 MOT17 极简项目（world/proj-b）与全局层
（world/global），走完：逐包 ingest → dossier 死胡同收编 → 索引与
校验 → 派生事实 + 构造第二代结论包取代（含 stale 传播）→ settle
候选流（accept 一条、reject 一条）→ 跨包 recall 实测 → Obsidian
投影 + 标注回读全链 → 画像 → 跨项目晋升 → bench 首测。

所有数字与产物落 evidence/，汇总写 evidence/summary.json。
构造部分（第二代结论包）全程明确标注为构造演示，不冒充真实上游。
运行：<venv>/python examples/demo-fullrun/run_demo.py（可重复执行，
每次先整删 world/ 重建）。
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

DEMO = Path(__file__).resolve().parent
PKG = DEMO.parents[1]
LS = PKG.parent
WORLD = DEMO / "world"
A = WORLD / "proj-a"
B = WORLD / "proj-b"
G = WORLD / "global"
INPUTS = DEMO / "inputs"
EVID = DEMO / "evidence"
PY = sys.executable

summary: dict = {"steps": []}


def run_cli(args, log_name, expect_rc=None):
    """经子进程真跑 CLI，输出落 evidence，返回 (rc, 文本)。"""
    proc = subprocess.run([PY, "-m", "light_memory", *args],
                          capture_output=True, text=True)
    text = (proc.stdout or "") + (proc.stderr or "")
    (EVID / log_name).write_text(
        f"$ light-memory {' '.join(str(a) for a in args)}\n"
        f"[exit {proc.returncode}]\n{text}", encoding="utf-8")
    if expect_rc is not None and proc.returncode != expect_rc:
        raise SystemExit(f"步骤失败（exit {proc.returncode}，期望 "
                         f"{expect_rc}）：{' '.join(map(str, args))}\n{text}")
    return proc.returncode, text


def read_jsonl(path):
    path = Path(path)
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8")
            .splitlines() if l.strip()]


def counts(root):
    facts = read_jsonl(root / "facts.jsonl")
    return {
        "objects": len(read_jsonl(root / "objects.jsonl")),
        "events": len(read_jsonl(root / "events.jsonl")),
        "facts": len(facts),
        "facts_current": sum(1 for f in facts
                             if f.get("status") == "current"),
        "facts_superseded": sum(1 for f in facts
                                if f.get("status") == "superseded"),
        "relations": len(read_jsonl(root / "relations.jsonl")),
        "disputes": len(read_jsonl(root / "disputes.jsonl")),
    }


def step(name, **data):
    summary["steps"].append({"step": name, **data})
    print(f"[demo] {name}: {json.dumps(data, ensure_ascii=False)[:220]}")


# ---------------------------------------------------------------- 输入面

INGESTS_A = [
    ("literature",
     LS / "light-literature/examples/demo-cea/Literature"),
    ("design",
     LS / "light-design/examples/demo-poultry-design/designs/"
          "zero-tuning-tracker-thresholds_979ee7/design.yaml"),
    ("experiment",
     LS / "light-experiment/examples/demo-synthetic/proj/executions/"
          "video-threshold-predict_synth01-b2"),
    ("analysis",
     LS / "light-analysis/examples/demo-synthetic/analysis-pkg/"
          "conclusion_card.json"),
    ("write",
     LS / "light-write/examples/demo-fullrun/manuscript-pkg/"
          "manuscript.yaml"),
    ("figure",
     LS / "light-figure/examples/demo-fullrun/figure-pkg/"
          "provenance.yaml"),
    ("journal-select",
     LS / "light-journal-select/examples/demo-fullrun/selection-pkg/"
          "selection.json"),
    ("review",
     LS / "light-review/examples/demo-fullrun/review-pkg/"
          "handoff_to_write.json"),
]

IDEA_SRC = LS / "light-idea/examples/demo-poultry"
MOT17_DESIGN = (LS / "light-design/examples/demo-poultry-design/designs/"
                "mot17_0aed08/design.yaml")


def build_dossier():
    """Idea 死胡同 dossier：从真实候选卡按约定转译为折返笔记。

    定版导出 memory_export.jsonl 只含定版卡；演示卡 C1 止步
    pre_mortem_passed（跨模型硬门未过）未定版，其余 5 卡 screened /
    draft，均无官方导出——按 REDESIGN 第四节定版口径收编为 notes/
    折返笔记（backtracks-to 关系行连回入选路线），不走 idea 适配器。
    """
    cards_dir = IDEA_SRC / "cards"
    notes_dir = A / "notes" / "idea-dossier"
    notes_dir.mkdir(parents=True, exist_ok=True)
    lead = "idea_card:zero-tuning-tracker-thresholds-predicted_77cdb7"
    made = []
    for card_path in sorted(cards_dir.glob("*/idea.yaml")):
        card = yaml.safe_load(card_path.read_text(encoding="utf-8"))
        idea_id = card["idea_id"]
        status = card.get("status")
        seeds = "、".join(s.get("doi") or s.get("title") or ""
                          for s in card.get("seed_refs") or []) or "（无）"
        if status == "pre_mortem_passed":
            state_line = ("主路线（未定版留痕）：已过 pre-mortem，定版被"
                          "跨模型复核硬门拦停（REVIEW_UNAVAILABLE），"
                          "无 memory_export 导出")
            rel_line = ("- derived-from "
                        "[[paper:abnormal-turkey-behaviour-detection"
                        "-usin_f65598]]（种子文献）")
            st = "lead-unfinalized"
        else:
            state_line = (f"死胡同（折返留痕）：Idea 阶段状态 {status}，"
                          "未入选主路线")
            rel_line = f"- backtracks-to [[{lead}]]（入选主路线）"
            st = "dead-end"
        text = (
            f"---\n"
            f"id: note-idea-{idea_id}\n"
            f"type: dossier\n"
            f"stage: idea\n"
            f"object_refs:\n  - idea_card:{idea_id}\n"
            f"created: 2026-10-20\n"
            f"status: {st}\n"
            f"---\n"
            f"# 想法卡留痕：{card.get('title')}\n\n"
            f"- [折返] {card.get('one_liner')}（算子 "
            f"{card.get('operator')}；种子：{seeds}）\n"
            f"{rel_line}\n\n"
            f"{state_line}。按 REDESIGN-DRAFT 第四节定版口径以 dossier "
            f"折返笔记形态收编进记忆：失败与折返不删除，供后续项目"
            f"避坑与复活评估；本条不走 idea 适配器（无定版导出）。\n")
        out = notes_dir / f"{idea_id}.md"
        out.write_text(text, encoding="utf-8")
        made.append({"idea_id": idea_id, "status": status,
                     "note": str(out.relative_to(DEMO))})
    return made



# ---------------------------------------------------------------- 主流程

def main():
    if WORLD.exists():
        shutil.rmtree(WORLD)
    EVID.mkdir(parents=True, exist_ok=True)
    for old in EVID.glob("*"):
        if old.is_file():
            old.unlink()

    # ---- 1. 建包 ----
    run_cli(["init", str(A), "--project", "turkey-threshold-prediction",
             "--title", "火鸡异常行为检测：零调参跟踪阈值预测"],
            "init-a.log", expect_rc=0)
    run_cli(["init", str(B), "--project", "mot17-threshold-baseline",
             "--title", "MOT17 阈值预测极简基线（跨项目对照）"],
            "init-b.log", expect_rc=0)
    run_cli(["init", str(G), "--project", "global",
             "--title", "全局层（跨项目晋升落点）"],
            "init-g.log", expect_rc=0)
    step("init", roots=["proj-a", "proj-b", "global"])

    # ---- 2. 逐包 ingest（proj-a） ----
    ingest_rows = []
    for package, source in INGESTS_A:
        before = counts(A)
        rc, _ = run_cli(["ingest", str(A), "--package", package,
                         "--source", str(source)],
                        f"ingest-{package}.log", expect_rc=0)
        after = counts(A)
        delta = {k: after[k] - before[k] for k in
                 ("objects", "events", "facts", "relations")}
        ingest_rows.append({"package": package, "source": str(source),
                            "exit": rc, **delta})
        step(f"ingest:{package}", **delta)
    # Idea：演示卡未定版、无 memory_export.jsonl —— 适配器应点名失败、
    # 水位线不动、一行不入账（如实记录，不假装收编）。
    before = counts(A)
    rc, idea_out = run_cli(["ingest", str(A), "--package", "idea",
                            "--source", str(IDEA_SRC)],
                           "ingest-idea.log")
    after = counts(A)
    idea_row = {"package": "idea", "source": str(IDEA_SRC), "exit": rc,
                **{k: after[k] - before[k] for k in
                   ("objects", "events", "facts", "relations")},
                "expected_failure": True,
                "output_tail": idea_out.strip().splitlines()[-3:]}
    ingest_rows.append(idea_row)
    step("ingest:idea（预期点名失败）", exit=rc,
         delta={k: idea_row[k] for k in
                ("objects", "events", "facts", "relations")})
    summary["ingest"] = ingest_rows

    # proj-b：MOT17 极简设计（真实第二项目材料）
    run_cli(["ingest", str(B), "--package", "design",
             "--source", str(MOT17_DESIGN)], "ingest-b-design.log",
            expect_rc=0)
    step("ingest:proj-b design", **counts(B))

    # ---- 3. dossier 死胡同收编（notes 层） ----
    dossier = build_dossier()
    summary["dossier"] = dossier
    step("dossier", notes=len(dossier))

    # ---- 4. 索引 + 校验 + 计数 ----
    run_cli(["index", str(A), "rebuild"], "index-a.log", expect_rc=0)
    run_cli(["index", str(B), "rebuild"], "index-b.log", expect_rc=0)
    run_cli(["validate", str(A)], "validate-a-after-ingest.log",
            expect_rc=0)
    run_cli(["status", str(A)], "status-a.log", expect_rc=0)
    c_ingest = counts(A)
    summary["counts_after_ingest"] = c_ingest
    step("counts_after_ingest", **c_ingest)

    # ---- 5. 取代演示：派生事实 + 构造第二代结论包 ----
    facts = read_jsonl(A / "facts.jsonl")
    gen1 = next(f for f in facts
                if f.get("fact_type") == "conclusion_verdict"
                and f.get("object_id") == "claim:C1")
    prov1 = (gen1.get("provenance") or [{}])[0]
    derived_nom = [{
        "verdict": "store",
        "nominator": "demo-driver（Write 表述口径登记）",
        "rationale": "Write 演示稿件 claims_register 对 C1 的可写口径"
                     "（writable_ceiling=limitations_only）派生自结论判定，"
                     "登记为派生事实以演示失效传播。",
        "provenance": {**prov1,
                       "source_package": "write",
                       "source_artifact": "claims_register.yaml",
                       "source_anchor": "claims_register:C1"},
        "fact": {
            "statement": "稿件对主张 C1 的表述口径："
                         "writable_ceiling=limitations_only，仅以 "
                         "insufficient 天花板写入 limitations 段"
                         "（Write claims_register 登记）",
            "fact_type": "generic", "object_id": "claim:C1",
            "valid_at": "2026-10-20",
            "derived_from": [gen1["fact_id"]]}}]
    (INPUTS / "nominations-derived.json").write_text(
        json.dumps(derived_nom, ensure_ascii=False, indent=1),
        encoding="utf-8")
    run_cli(["verdict", str(A), "--file",
             str(INPUTS / "nominations-derived.json")],
            "verdict-derived.log", expect_rc=0)

    gen2_nom = [{
        "verdict": "supersede",
        "nominator": "demo-driver（构造第二代结论包）",
        "rationale": "【构造演示，非真实上游产物】真实 Analysis 演示只有"
                     "一代结论包；此处按一期冒烟已验证的形态构造第二代："
                     "假设补跑 R-NEG 所缺 seg-05/06 后重判，R-NEG 行仍无"
                     "可判数据，判定维持并收紧边界口径。valid_at 记为"
                     "次日 2026-10-21 以使区间算术与 as-of 分界真实可检。",
        "provenance": {**prov1,
                       "source_artifact":
                           "conclusion_card.gen2-CONSTRUCTED.json",
                       "source_version": "constructed-demo"},
        "target_fact_id": gen1["fact_id"],
        "fact": {
            "statement": "主张 C1 判定：support=untested，"
                         "grade=insufficient（第二代结论包·构造演示："
                         "补跑 R-NEG 所缺 seg-05/06 后重判，R-NEG 行仍"
                         "无可判数据，support 维持 untested；口径收紧"
                         "为：结论仅适用于数据版本完整交付的登记条目）",
            "fact_type": "conclusion_verdict", "object_id": "claim:C1",
            "valid_at": "2026-10-21"}}]
    (INPUTS / "nominations-gen2.json").write_text(
        json.dumps(gen2_nom, ensure_ascii=False, indent=1),
        encoding="utf-8")
    _, sup_out = run_cli(["verdict", str(A), "--file",
                          str(INPUTS / "nominations-gen2.json")],
                         "verdict-gen2-supersede.log", expect_rc=0)
    facts = read_jsonl(A / "facts.jsonl")
    gen1_now = next(f for f in facts if f["fact_id"] == gen1["fact_id"])
    derived_now = next(f for f in facts
                       if (f.get("derived_from") or [])
                       and gen1["fact_id"] in f["derived_from"])
    events = read_jsonl(A / "events.jsonl")
    sup_events = [e.get("type") for e in events
                  if e.get("type") in ("supersede", "propagation",
                                       "verdict")]
    summary["supersede"] = {
        "constructed": True,
        "gen1_fact_id": gen1["fact_id"],
        "gen1_statement": gen1["statement"],
        "gen1_status_after": gen1_now.get("status"),
        "gen1_invalid_at": gen1_now.get("invalid_at"),
        "gen1_superseded_by": gen1_now.get("superseded_by"),
        "derived_fact_id": derived_now["fact_id"],
        "derived_stale": derived_now.get("stale"),
        "derived_stale_reason": derived_now.get("stale_reason"),
        "event_types_tail": sup_events[-4:],
        "cli_output": sup_out.strip().splitlines()[-2:],
        "retraction_note": "真实撤稿数据无结构化源（Literature 适配器"
                           "已点名缺口）；撤稿传播钩子（refutes 边 + "
                           "同套 stale 传播）已备，本次以结论包取代"
                           "实测同一传播路径。",
    }
    step("supersede（构造第二代）", gen1=gen1_now.get("status"),
         derived_stale=derived_now.get("stale"))

    # ---- 6. settle 候选流：accept 一条 / reject 一条 ----
    # 教训候选的出处指针：提名理由写明由 F-0001 提炼，落账形态须带
    # derived_from 指向失败事实（运行时注入其 fact_id，模板存 inputs/）。
    facts = read_jsonl(A / "facts.jsonl")
    fail1 = next(f for f in facts
                 if f.get("fact_type") == "failure_record"
                 and "turkey-barn-vnext-v1" in (f.get("statement")
                                                or ""))
    lesson_tpl = json.loads((INPUTS / "candidate-lesson.json")
                            .read_text(encoding="utf-8"))
    lesson_tpl["nomination"]["fact"]["derived_from"] = \
        [fail1["fact_id"]]
    lesson_file = INPUTS / "candidate-lesson.effective.json"
    lesson_file.write_text(json.dumps(lesson_tpl, ensure_ascii=False,
                                      indent=1), encoding="utf-8")
    _, out = run_cli(["candidate", str(A), "propose", "--kind", "fact",
                      "--file", str(lesson_file),
                      "--nominator", "demo-driver"],
                     "candidate-lesson-propose.log", expect_rc=0)
    lesson_cid = re.search(r"(cand_[0-9a-f]+)", out).group(1)
    run_cli(["candidate", str(A), "accept", "--id", lesson_cid,
             "--by", "demo-user"], "candidate-lesson-accept.log",
            expect_rc=0)
    _, out = run_cli(["candidate", str(A), "propose", "--kind", "fact",
                      "--file",
                      str(INPUTS / "candidate-speculative.json"),
                      "--nominator", "demo-driver"],
                     "candidate-speculative-propose.log", expect_rc=0)
    spec_cid = re.search(r"(cand_[0-9a-f]+)", out).group(1)
    run_cli(["candidate", str(A), "reject", "--id", spec_cid,
             "--by", "demo-user",
             "--note", "跨畜种迁移未经任何证据支持、属推测；来源卡本身"
                       "留 draft 未验证。驳回留痕，不入长期层。"],
            "candidate-speculative-reject.log", expect_rc=0)
    run_cli(["candidate", str(A), "list"], "candidate-list.log",
            expect_rc=0)
    facts = read_jsonl(A / "facts.jsonl")
    lesson_fact = next(f for f in facts
                       if f.get("fact_type") == "lesson"
                       and "完整交付" in (f.get("statement") or ""))
    summary["candidates"] = {
        "accepted": {"candidate_id": lesson_cid,
                     "fact_id": lesson_fact["fact_id"],
                     "statement": lesson_fact["statement"]},
        "rejected": {"candidate_id": spec_cid,
                     "note": "推测性跨域迁移、无证据，驳回留痕"}}
    step("candidates", accepted=lesson_cid, rejected=spec_cid)

    # ---- 7. 跨包 recall 实测 ----
    recalls = {}
    run_cli(["recall", str(A),
             "主张 C1 的判定 support 与 grade 是什么，承接自哪个执行包",
             "--depth", "1"], "recall-q1-cross-stage.log", expect_rc=0)
    recalls["q1_cross_stage"] = "recall-q1-cross-stage.log"
    run_cli(["recall", str(A),
             "数据版本交付不完整造成过什么失败，承接新执行前要核验什么",
             "--recipe", "failure-lookup"],
            "recall-q2-failure-reuse.log", expect_rc=0)
    recalls["q2_failure_reuse"] = "recall-q2-failure-reuse.log"
    run_cli(["facts", str(A), "--as-of", "2026-10-20"],
            "facts-asof-2026-10-20.log", expect_rc=0)
    run_cli(["recall", str(A), "主张 C1 判定口径", "--as-of",
             "2026-10-20"], "recall-q3-asof.log", expect_rc=0)
    run_cli(["facts", str(A)], "facts-current.log", expect_rc=0)
    recalls["q3_asof"] = ["facts-asof-2026-10-20.log",
                          "recall-q3-asof.log", "facts-current.log"]
    run_cli(["recall", str(A),
             "predicting tracker thresholds from video-level statistics",
             "--recipe", "paraphrase"], "recall-q4-paraphrase-en.log",
            expect_rc=0)
    recalls["q4_paraphrase_en"] = "recall-q4-paraphrase-en.log"
    summary["recalls"] = recalls
    step("recalls", files=list(recalls))

    # recall 会更新强度记账（MM-30），真相已变 → 重建索引再继续
    run_cli(["index", str(A), "rebuild"], "index-a-after-recall.log",
            expect_rc=0)

    # ---- 8. Obsidian 投影 + 标注回读全链 ----
    run_cli(["project-obsidian", str(A)], "project-obsidian.log",
            expect_rc=0)
    vault = A / "obsidian"
    vault_files = sorted(str(p.relative_to(vault))
                         for p in vault.rglob("*.md"))
    manifest = json.loads((vault / ".projection.json")
                          .read_text(encoding="utf-8"))
    anno_note = None
    for rel in vault_files:
        p = vault / rel
        if "索引" in rel or "关系" in rel:
            continue
        if "<!-- light-memory:annotations:start -->" in \
                p.read_text(encoding="utf-8"):
            anno_note = p
            break
    anno_line = ("（演示标注）第二代结论包生效后，本对象口径以第二代"
                 "为准；边界条件——仅适用于数据版本完整交付的登记"
                 "条目——组会已确认。—— demo-user，2026-10-20")
    text = anno_note.read_text(encoding="utf-8")
    marker = "<!-- light-memory:annotations:start -->"
    text = text.replace(marker, marker + "\n" + anno_line, 1)
    anno_note.write_text(text, encoding="utf-8")
    run_cli(["readback", str(A)], "readback.log", expect_rc=0)
    # 注：candidate list 的 --kind 默认 fact，annotation 候选须显式
    # --kind annotation 才列得出（接口小毛病，记入 demo-report）。
    _, cand_out = run_cli(["candidate", str(A), "list", "--kind",
                           "annotation", "--status", "pending"],
                          "candidate-list-pending.log", expect_rc=0)
    anno_cid = None
    for line in cand_out.splitlines():
        if "[annotation]" in line:
            anno_cid = re.search(r"(cand_[0-9a-f]+)", line).group(1)
    if not anno_cid:
        raise SystemExit("回读未产生 annotation 候选，演示中止")
    run_cli(["candidate", str(A), "accept", "--id", anno_cid,
             "--by", "demo-user"], "candidate-annotation-accept.log",
            expect_rc=0)
    events = read_jsonl(A / "events.jsonl")
    anno_events = [e for e in events if e.get("type") == "annotation"]
    summary["obsidian"] = {
        "vault_files": vault_files,
        "vault_note_count": len(vault_files),
        "manifest": manifest,
        "annotated_note": str(anno_note.relative_to(DEMO)),
        "annotation_candidate_id": anno_cid,
        "annotation_events": len(anno_events),
    }
    step("obsidian", notes=len(vault_files),
         annotation_candidate=anno_cid,
         annotation_events=len(anno_events))

    # ---- 9. 画像 ----
    run_cli(["profile", str(A), "build"], "profile-build.log",
            expect_rc=0)
    run_cli(["profile", str(A), "check"], "profile-check.log",
            expect_rc=0)
    step("profile", built=True)

    # ---- 10. 跨项目晋升 ----
    lesson_id = summary["candidates"]["accepted"]["fact_id"]
    _, out = run_cli(["promote", str(G), "propose", "--from", str(A),
                      "--fact-id", lesson_id, "--by", "demo-driver",
                      "--reason", "跨项目通用教训：承接执行前核验登记"
                                  "数据版本的完整交付"],
                     "promote-propose.log", expect_rc=0)
    promo_cid = re.search(r"(cand_[0-9a-f]+)", out).group(1)
    _, out = run_cli(["promote", str(G), "confirm", "--id", promo_cid,
                      "--by", "demo-user"], "promote-confirm.log",
                     expect_rc=0)
    run_cli(["promote", str(G), "list"], "promote-list.log",
            expect_rc=0)
    g_facts = read_jsonl(G / "facts.jsonl")
    g_promos = read_jsonl(G / "promotions.jsonl")
    summary["promotion"] = {
        "candidate_id": promo_cid,
        "source_fact_id": lesson_id,
        "global_facts": len(g_facts),
        "global_copy_statement":
            (g_facts[0].get("statement") if g_facts else None),
        "promotions_rows": len(g_promos),
        "confirm_output": out.strip().splitlines()[-1:],
    }
    step("promotion", global_facts=len(g_facts),
         promotions_rows=len(g_promos))

    # ---- 11. 终局校验 + bench 首测 ----
    run_cli(["index", str(A), "rebuild"], "index-a-final.log",
            expect_rc=0)
    for root, tag in ((A, "a"), (B, "b"), (G, "global")):
        run_cli(["validate", str(root)], f"validate-{tag}-final.log",
                expect_rc=0)
    summary["counts_final"] = {"proj-a": counts(A), "proj-b": counts(B),
                               "global": counts(G)}
    step("validate_final", **summary["counts_final"]["proj-a"])

    set_path = INPUTS / "bench_set_fullrun.jsonl"
    if set_path.exists():
        verify_bench_anchors(set_path)
        run_cli(["bench", "run", "--world", str(WORLD), "--set",
                 str(set_path), "--out",
                 str(EVID / "bench_report.json")],
                "bench-run.log", expect_rc=0)
        report = json.loads((EVID / "bench_report.json")
                            .read_text(encoding="utf-8"))
        summary["bench"] = {
            "set": str(set_path.relative_to(DEMO)),
            "overall": report["overall"],
            "categories": {k: {"total": v["total"],
                               "correct": v["correct"],
                               "rate": v["rate"]}
                           for k, v in report["categories"].items()},
            "embedder": (report.get("config") or {}).get("embedder"),
            "verdict": report.get("verdict"),
        }
        step("bench", **summary["bench"]["overall"])
    else:
        summary["bench"] = {"skipped": "题集文件未就位（首轮侦察运行）"}
        step("bench", skipped=True)

    (EVID / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=1),
        encoding="utf-8")
    print("[demo] 完成，汇总见 evidence/summary.json")


def verify_bench_anchors(set_path):
    """题集金标准锚点核验：include 片段必须真实存在于对应包的事实/
    笔记文本中（拒答题豁免）；不存在即报错，不许带病跑分。"""
    corpus = {}
    for key, root in (("a", A), ("b", B), ("global", G)):
        texts = [f.get("statement") or ""
                 for f in read_jsonl(root / "facts.jsonl")]
        notes_dir = root / "notes"
        if notes_dir.exists():
            for p in notes_dir.rglob("*.md"):
                texts.append(p.read_text(encoding="utf-8"))
        corpus[key] = "\n".join(texts)
    problems = []
    for q in read_jsonl(set_path):
        expect = q.get("expect") or {}
        if expect.get("refusal"):
            continue
        root_key = q.get("root") or "a"
        for sub in expect.get("include_statements") or []:
            if sub not in corpus[root_key]:
                problems.append(f"{q.get('qid')}: include 片段不在 "
                                f"{root_key} 语料中：{sub[:40]}")
        label2root = {"turkey-threshold-prediction": "a",
                      "mot17-threshold-baseline": "b"}
        for sub, label in (expect.get("include_by_project")
                           or {}).items():
            rk = label2root.get(label)
            if rk and sub not in corpus[rk]:
                problems.append(f"{q.get('qid')}: 分组片段不在 {label} "
                                f"语料中：{sub[:40]}")
    if problems:
        raise SystemExit("题集锚点核验失败：\n" + "\n".join(problems))
    print(f"[demo] 题集锚点核验通过（{len(read_jsonl(set_path))} 题）")


if __name__ == "__main__":
    main()
