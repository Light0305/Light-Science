"""I6 交接导出与项目报告（三期）。

交接三件套（ARIS 形态，草案 §7）：对 **finalized**（两级定版之一）
的卡产出到 <project>/exports/<idea_id>/：
- design_handoff.md —— 给 Light-Design 的人读交接：核心主张、执行级
  规格、最小判别实验与判读标准（= minimum convincing evidence）、
  最强基线、查新结论与证据指针、风险与最强反对意见、next-step；
- idea_card.json —— 想法卡结构化全量（idea.yaml 的 JSON 形态）；
- memory_export.jsonl —— 按 evo-memory 风格抽象到**方向层级**的条目
  （Summary / Why / Evidence 指针 / Status / Retrieval Tags /
  Boundary Conditions），供未来 Light-Memory 收编（拍板 9.5-A：
  判据先行、系统后置，v1 只留结构化导出，不自建记忆系统）。

**未定版卡拒绝导出**：差哪一步、定版门还剩什么错，逐条说明——导出
不是绕过定版门的后门（完成性由确定性检查守门，约束/LEARNING §7）。

项目级 report：生成/刷新 idea-stage/IDEA_REPORT.md（唯一权威文档）：
全池状态、定版清单、已杀区摘要、去重率（按 dedup 工序现场重算）、
对决摘要（分数标「暂定」，循环胜负如实提示）。
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from . import dedup as dedup_mod
from . import duel as duel_mod
from .gates import check_transition
from .project import list_cards, project_paths
from .schema import ALL_STATES, MAIN_STATES, _nonempty_str
from .util import read_yaml, today

FINAL_STATES = ("finalized_executable", "finalized_conceptual")


class ExportError(Exception):
    """导出被拒。errors 为逐条人读原因（缺口说明）。"""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("；".join(errors))


def export_dir(root: Path, idea_id: str) -> Path:
    return root / "exports" / idea_id


def _remaining_path(status: str) -> list[str]:
    """从当前主线状态到定版还差的状态序列（旁路状态返回空）。"""
    if status not in MAIN_STATES:
        return []
    i = MAIN_STATES.index(status)
    return list(MAIN_STATES[i + 1:])


def export_card(root: Path, card: dict, *, date: str | None = None) -> dict:
    """对定版卡产出交接三件套。未定版抛 ExportError 并说明缺口。"""
    date = date or today()
    status = card.get("status")
    if status not in FINAL_STATES:
        errs = [f"卡状态为 {status}，未定版——交接三件套只对定版卡产出，"
                f"不许拿未定版卡冒充交接件"]
        rest = _remaining_path(status or "")
        if rest:
            errs.append("主线还差：" + " → ".join(rest))
        if status == "pre_mortem_passed":
            target = ("finalized_conceptual"
                      if card.get("finalization_level") == "conceptual"
                      else "finalized_executable")
            gate_errs = check_transition(card, target)
            if gate_errs:
                errs.append(f"定版门（{target}）未过条目：")
                errs.extend(f"  · {e}" for e in gate_errs)
        if status in ("killed", "parked"):
            errs.append("旁路状态（killed/parked）的卡不导出交接件；"
                        "killed 的价值在已杀区留痕与 memory 方向条目，"
                        "不走 Design 交接")
        raise ExportError(errs)

    out_dir = export_dir(root, card["idea_id"])
    out_dir.mkdir(parents=True, exist_ok=True)
    handoff_path = out_dir / "design_handoff.md"
    handoff_path.write_text(_render_handoff(card, date), encoding="utf-8")
    card_json_path = out_dir / "idea_card.json"
    card_json_path.write_text(
        json.dumps(card, ensure_ascii=False, indent=1), encoding="utf-8")
    memory_path = out_dir / "memory_export.jsonl"
    entry = memory_entry(root, card, date=date)
    memory_path.write_text(
        json.dumps(entry, ensure_ascii=False) + "\n", encoding="utf-8")
    return {
        "idea_id": card["idea_id"],
        "date": date,
        "export_dir": str(out_dir),
        "design_handoff": str(handoff_path),
        "idea_card_json": str(card_json_path),
        "memory_export": str(memory_path),
        "finalization_level": card.get("finalization_level"),
    }


def _spec_value(v) -> str:
    if isinstance(v, list):
        if not v:
            return "（未填）"
        bits = []
        for x in v:
            if isinstance(x, dict):
                bits.append(x.get("name") or json.dumps(x, ensure_ascii=False))
            else:
                bits.append(str(x))
        return "；".join(bits)
    if isinstance(v, dict):
        if not v:
            return "（未填）"
        name = v.get("name")
        ref = v.get("paper_id") or v.get("doi")
        if name or ref:
            return " ".join(x for x in (name, f"({ref})" if ref else "") if x)
        return json.dumps(v, ensure_ascii=False)
    return str(v) if v else "（未填）"


def _render_handoff(card: dict, date: str) -> str:
    nov = card.get("novelty") or {}
    spec = card.get("exec_spec") or {}
    body = card.get("body") or {}
    neg = card.get("negative") or {}
    pilot = card.get("pilot") or {}
    level = card.get("finalization_level")
    L: list[str] = []
    L.append(f"# Design 交接件 — {card.get('title')}")
    L.append("")
    L.append(f"> idea_id: `{card['idea_id']}` ｜ 定版级别: **{level}**"
             f" ｜ 交接日期: {date} ｜ 来源算子: {card.get('operator')}")
    if level == "conceptual":
        L.append("> ⚠️ **概念定版**：执行级规格未齐，**不得直接开工**——"
                 "Design 的第一步是按 facet 与查新证据把规格补齐，"
                 "缺项见下方规格区「（未填）」条目。")
    if pilot.get("status") != "verified":
        L.append("> ⚠️ **未经试点验证**（pilot.status="
                 f"{pilot.get('status')}）：判别实验尚未实际执行，"
                 "本交接件中的预期均为文本阶段结论，标「暂定」。")
    L.append("")
    L.append("## 核心主张（core claims）")
    L.append("")
    L.append(f"- 一句话：{card.get('one_liner')}")
    L.append(f"- 假设：{body.get('hypothesis') or '（未填）'}")
    L.append(f"- 贡献类型：{body.get('contribution_type')}")
    if body.get("unexpected_prediction"):
        L.append(f"- 可证伪的意外预测：{body['unexpected_prediction']}")
    if body.get("mechanism_rationale"):
        L.append(f"- 机制说明：{body['mechanism_rationale']}")
    L.append("")
    L.append("## 方法概要（平语）")
    L.append("")
    for i, step in enumerate(body.get("method_steps") or [], 1):
        L.append(f"{i}. {step}")
    L.append("")
    L.append("## Facet 区")
    L.append("")
    facets = card.get("facets") or {}
    for f in ("purpose", "mechanism", "evaluation"):
        fd = facets.get(f) or {}
        L.append(f"- **{f}**：{fd.get('phrase') or '（未填）'}"
                 f" — {fd.get('detail') or ''}")
    L.append("")
    L.append("## 执行级规格（Design 按此开工，不得临场改口径）")
    L.append("")
    for key, label in (("datasets", "指名数据集"),
                       ("strongest_baseline", "最强基线（点名）"),
                       ("metrics", "指标（附领域惯例出处）"),
                       ("ablations", "计划消融"),
                       ("resource_budget", "资源预算"),
                       ("key_details", "关键实现细节")):
        L.append(f"- **{label}**：{_spec_value(spec.get(key))}")
    L.append("")
    exp = spec.get("discriminating_experiment")
    L.append("## 最小判别实验与判读标准（minimum convincing evidence）")
    L.append("")
    if isinstance(exp, dict):
        L.append(f"- 实验：{exp.get('description')}")
        L.append(f"- 正结果意味着：{exp.get('readout_positive')}")
        L.append(f"- 负结果意味着：{exp.get('readout_negative')}")
        L.append(f"- 零结果意味着：{exp.get('readout_null')}")
    else:
        L.append("（未写——概念定版缺口，Design 须先补此项）")
    L.append("")
    L.append("## 查新结论（判定区，证据可审计）")
    L.append("")
    L.append(f"- 判定：**{nov.get('verdict')}**"
             f"（checked_at: {nov.get('checked_at')}，"
             f"review_status: {nov.get('review_status')}）")
    if nov.get("caution_reason"):
        L.append(f"- CAUTION 薄点：{nov['caution_reason']}")
    scope = nov.get("search_scope") or {}
    L.append(f"- 检索范围：源 {scope.get('sources')}｜池规模 "
             f"{scope.get('pool_size')}｜已知盲区："
             f"{scope.get('known_blind_spots') or '—'}")
    works = nov.get("closest_works") or []
    if works:
        L.append("- 最接近工作（逐面异同见卡内 novelty 区）：")
        for w in works:
            ref = w.get("paper_id") or w.get("doi") or w.get("title")
            L.append(f"  - {ref}｜撞车面: {w.get('collided_facets')}"
                     f"｜delta: {w.get('delta')}")
    rc = nov.get("receipt") or {}
    if rc.get("verdict_id"):
        L.append(f"- 判定收据：verdict_id {rc['verdict_id']}｜判定 "
                 f"{rc.get('judge_model')}｜执行 {rc.get('executor_model')}")
    L.append(f"- 证据包：{nov.get('evidence_package') or '—'}")
    L.append("")
    L.append("## 风险与反对意见（Design 须正面回应，不许绕开）")
    L.append("")
    L.append(f"- 最强反对意见：{neg.get('strongest_objection') or '（未填）'}")
    for r in neg.get("risks") or []:
        L.append(f"- 风险：{r}")
    L.append("")
    L.append("## Next step")
    L.append("")
    L.append("- Light-Design 以本交接件 + idea_card.json 为输入做实验设计；"
             "细化时若动核心（facet 三面/假设），按保真规则回写本卡 "
             "lineage（核心未动 / 细节改了什么）。")
    L.append("- 本想法若在 Design/Experiment 阶段被证伪，从项目候选池"
             "（idea-stage/candidates.md）按备选顺序取下一张，不重跑全流程。")
    L.append("")
    return "\n".join(L)


def _direction_summary(card: dict) -> str:
    facets = card.get("facets") or {}
    purpose = (facets.get("purpose") or {}).get("phrase") or ""
    mechanism = (facets.get("mechanism") or {}).get("phrase") or ""
    bits = [b for b in (purpose, mechanism) if _nonempty_str(b)]
    if bits:
        return "：".join(bits) if len(bits) == 2 else bits[0]
    return card.get("one_liner") or card.get("title") or ""


def _retrieval_tags(card: dict) -> list[str]:
    tags: list[str] = []
    facets = card.get("facets") or {}
    for f in ("purpose", "mechanism", "evaluation"):
        phrase = ((facets.get(f) or {}).get("phrase") or "").strip()
        if phrase:
            tags.append(phrase)
    if card.get("operator"):
        tags.append(f"operator:{card['operator']}")
    ct = (card.get("body") or {}).get("contribution_type")
    if ct:
        tags.append(f"contribution:{ct}")
    return tags


def memory_entry(root: Path, card: dict, *, date: str | None = None) -> dict:
    """把一张定版卡抽象成方向层条目（evo-memory 风格字段）。

    抽象阶梯（约束 8）：条目写「方向」而非具体做法细节——Summary 给
    方向命题，Why 给成立理由与 delta，Evidence 只给指针（卡、查新
    证据包、收据），细节回指针处查，不在条目里复制全文。
    """
    date = date or today()
    nov = card.get("novelty") or {}
    rc = nov.get("receipt") or {}
    evidence = [f"cards/{card['idea_id']}/idea.yaml"]
    if nov.get("evidence_package"):
        evidence.append(nov["evidence_package"])
    if rc.get("verdict_id"):
        evidence.append(f"verdict:{rc['verdict_id']}")
    return {
        "entry_id": f"DIR-{card['idea_id']}",
        "level": "direction",
        "summary": _direction_summary(card),
        "why": (card.get("one_liner") or "")
               + (f"；查新判定 {nov.get('verdict')}"
                  if nov.get("verdict") else ""),
        "evidence": evidence,
        "status": "feasible",
        "retrieval_tags": _retrieval_tags(card),
        "boundary_conditions": (card.get("negative") or {}).get("risks") or [],
        "source": {
            "idea_id": card["idea_id"],
            "operator": card.get("operator"),
            "finalization_level": card.get("finalization_level"),
            "project": (read_yaml(project_paths(root)["project_yaml"])
                        .get("project") if project_paths(root)["project_yaml"]
                        .exists() else None),
        },
        "date": date,
    }


# ---------------------------------------------------------------------------
# 项目级报告 IDEA_REPORT.md

def build_report(root: Path, *, date: str | None = None) -> dict:
    """生成/刷新 idea-stage/IDEA_REPORT.md，返回汇总 dict。"""
    date = date or today()
    p = project_paths(root)
    meta = read_yaml(p["project_yaml"]) if p["project_yaml"].exists() else {}
    cards = list_cards(root)
    counts = Counter(c.get("status") for c in cards)
    rank = duel_mod.rank_project(root, cards)

    # 去重率：按 dedup 工序现场重算（口径与 dedup 命令一致）
    dedup_summary = None
    if len(cards) >= 2:
        pairs = dedup_mod.find_pairs(cards)
        dedup_summary = dedup_mod.dedup_report(
            cards, pairs, dedup_mod.DEFAULT_THRESHOLD)

    verdicts = Counter((c.get("novelty") or {}).get("verdict")
                       for c in cards if (c.get("novelty") or {}).get("verdict"))
    finalized = [c for c in cards if c.get("status") in FINAL_STATES]
    killed = [c for c in cards if c.get("status") == "killed"]
    parked = [c for c in cards if c.get("status") == "parked"]

    L: list[str] = []
    L.append(f"# IDEA_REPORT — {meta.get('project', root.name)}")
    L.append("")
    L.append(f"> 本方向唯一权威文档（report 命令生成/刷新于 {date}）："
             f"全池状态 / 定版清单 / 已杀区摘要 / 去重率 / 对决摘要。")
    L.append("")
    L.append("## 全池状态")
    L.append("")
    L.append(f"- 总卡数：{len(cards)}")
    for s in ALL_STATES:
        if counts.get(s):
            L.append(f"- {s}：{counts[s]}")
    if verdicts:
        L.append("- 查新结论分布：" + "、".join(
            f"{v} × {n}" for v, n in sorted(verdicts.items())))
    L.append("")
    L.append("| idea_id | 状态 | 算子 | 查新判定 | 题名 |")
    L.append("|---|---|---|---|---|")
    for c in sorted(cards, key=lambda c: c["idea_id"]):
        v = (c.get("novelty") or {}).get("verdict") or "—"
        L.append(f"| {c['idea_id']} | {c.get('status')} | "
                 f"{c.get('operator')} | {v} | {c.get('title')} |")
    L.append("")
    L.append("## 定版清单")
    L.append("")
    if not finalized:
        L.append("（暂无定版卡）")
    for c in finalized:
        pilot = (c.get("pilot") or {}).get("status")
        note = "" if pilot == "verified" else "｜⚠️ 未经试点验证"
        L.append(f"- `{c['idea_id']}`（{c.get('finalization_level')}）"
                 f"：{c.get('title')}{note}｜交接件 exports/{c['idea_id']}/")
    L.append("")
    L.append("## 已杀区摘要")
    L.append("")
    if not killed:
        L.append("（暂无 killed 卡）")
    for c in killed:
        k = c.get("kill") or {}
        L.append(f"- `{c['idea_id']}`：{k.get('reason')}（失败分类: "
                 f"{k.get('failure_class')}，来源: {k.get('source')}，"
                 f"{k.get('date')}）")
        if k.get("source") == "novelty_named_paper":
            named = k.get("named_paper") or {}
            L.append(f"  - 点名在先论文：{named.get('title') or named.get('doi') or named.get('paper_id')}")
        if k.get("failure_class") == "fundamental":
            L.append(f"  - 边界条件（何时可能复活）：{k.get('boundary_conditions')}")
        if k.get("failure_class") == "implementation":
            L.append(f"  - 重试指引：{k.get('retry_guidance')}")
    if parked:
        L.append("")
        L.append("搁置（parked）：")
        for c in parked:
            pk = c.get("park") or {}
            L.append(f"- `{c['idea_id']}`：{pk.get('reason')}"
                     f"｜复活条件：{pk.get('revival_condition')}")
    L.append("")
    L.append("## 去重率（生成健康体检，dedup 工序现场重算）")
    L.append("")
    if dedup_summary is None:
        L.append("（卡数 < 2，未跑）")
    else:
        L.append(f"- 生成总数：{dedup_summary['total_generated']}"
                 f"｜疑似重复对：{dedup_summary['suspected_pairs']}"
                 f"（阈值 {dedup_summary['threshold']}）")
        L.append(f"- 若裁决全部成立：冗余 {dedup_summary['redundant_if_all_confirmed']}"
                 f" 张、存活 {dedup_summary['survivors_if_all_confirmed']} 张、"
                 f"去重率 {dedup_summary['dedup_rate_if_all_confirmed']}")
        L.append("- 注：去重只报告供人工裁决，不自动删卡；逐对明细跑 "
                 "`light-idea dedup` 生成 idea-stage/dedup_report.md。")
    L.append("")
    L.append("## 对决摘要（I4；分数为辅助信号，一律「暂定，未经执行验证」，不作淘汰依据）")
    L.append("")
    if not rank["matches"]:
        L.append("（暂无对决记录）")
    else:
        L.append(f"- 对决总数：{len(rank['matches'])} 场")
        L.append("")
        L.append("| idea_id | Elo 参考分（暂定） | 胜 | 负 | 平 | 胜率 |")
        L.append("|---|---|---|---|---|---|")
        for s in rank["standings"]:
            L.append(f"| {s['idea_id']} | {s['elo']} | {s['win']} | "
                     f"{s['loss']} | {s['draw']} | {s['win_rate']} |")
        for cyc in rank["cycles"]:
            L.append(f"- ⚠️ 循环胜负：{'、'.join(cyc)} 之间对决分不开"
                     f"（循环胜负），Elo 在这些卡之间只作并列参考，"
                     f"不假装精度。")
        L.append("- 淘汰只凭三类证据：查新 ABANDON（点名论文）/ "
                 "试点 negative / 客观不可行——对决输赢只定先后，不定生死。")
    L.append("")
    text = "\n".join(L)
    p["idea_report"].write_text(text, encoding="utf-8")
    return {
        "date": date,
        "total": len(cards),
        "status_counts": {s: counts[s] for s in ALL_STATES if counts.get(s)},
        "finalized": [c["idea_id"] for c in finalized],
        "killed": [c["idea_id"] for c in killed],
        "dedup": dedup_summary,
        "duel_matches": len(rank["matches"]),
        "cycles": rank["cycles"],
        "report_path": str(p["idea_report"]),
    }
