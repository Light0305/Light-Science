"""上游收编适配器（M0）：一包一个适配器，只读上游导出物。

分工（REDESIGN 第四节承接表）：
- 结构化直通（机器可读导出走确定性字段映射，零模型参与）：Idea /
  Experiment / Analysis / Figure / Journal-Select / Review；
- 约定转译（结构化文件群 + 明文约定，字段值一律照抄上游）：Design /
  Literature / Write；
- v1.1 集成步（MM2-13）新三包：Patent（案件目录 case.yaml +
  ledger.yaml 的 memory_export 段）、Software-Copyright（案件目录
  登记头 + 确认/工具留痕 + 源码快照）、Crawler（data-sources
  目录工作区头 + 目标登记 + 事件/留存两本流水），均照抄上游。
字段缺失逐项 ctx.gap 点名并跳过该条，不许编造补齐（MM-02：溯源不全
的条目只许留缓冲，本期以缺口形式留在收编报告里）。

适配器只往 ctx（收编草稿收集器，见 intake.py）里放对象/事件/事实/
关系草稿，不直接落盘；水位线、去重、漂移由 intake 统一处理。
"""

from __future__ import annotations

import csv
from pathlib import Path

from .util import load_structured, read_jsonl, sha256_file


class AdapterError(Exception):
    """适配器无法开工（如必需源文件缺失）。gaps 逐项点名。"""

    def __init__(self, gaps):
        self.gaps = list(gaps)
        super().__init__("；".join(self.gaps))


def _date(value):
    return str(value)[:10] if value else None


def _need_file(source: Path, name: str, package: str) -> Path:
    p = Path(source) / name if Path(source).is_dir() else Path(source)
    if not p.exists():
        raise AdapterError([f"{package} 收编源缺失：{p}"])
    return p


# ---------------------------------------------------------------- Idea

def adapt_idea(source: Path, ctx) -> None:
    """Idea memory_export.jsonl（仅定版卡的方向层条目）→ 事实 + 对象。"""
    path = _need_file(source, "memory_export.jsonl", "idea")
    for row in read_jsonl(path):
        src = row.get("source") or {}
        idea_id = src.get("idea_id") or \
            (row.get("entry_id") or "").removeprefix("DIR-")
        if not idea_id:
            ctx.gap(f"idea 条目缺 idea_id（entry_id={row.get('entry_id')}）"
                    "，跳过不入账")
            continue
        oid = ctx.object("idea_card", idea_id,
                         title=(row.get("summary") or "")[:60],
                         current_version=row.get("date"))
        statement = row.get("summary") or ""
        if row.get("why"):
            statement = f"{statement}；{row['why']}"
        ctx.fact(statement, "direction", oid,
                 valid_at=_date(row.get("date")),
                 anchor=row.get("entry_id"),
                 extra={"entry_id": row.get("entry_id"),
                        "status": row.get("status"),
                        "retrieval_tags": row.get("retrieval_tags"),
                        "boundary_conditions":
                            row.get("boundary_conditions"),
                        "evidence": row.get("evidence")})


# ---------------------------------------------------------------- Experiment

def adapt_experiment(source: Path, ctx) -> None:
    """Experiment 执行包目录：execution_card + events + failures 直通。"""
    source = Path(source)
    card_path = source / "execution_card.json"
    if not card_path.exists():
        raise AdapterError([f"experiment 收编源缺 execution_card.json："
                            f"{source}"])
    card = load_structured(card_path)
    exec_id = card.get("exec_id") or source.name
    exec_oid = ctx.object("execution", exec_id,
                          title=f"执行包 {exec_id}",
                          current_version=sha256_file(card_path),
                          artifact="execution_card.json")
    ctx.event("milestone",
              f"执行包 {exec_id} 收编：状态 {card.get('status')}",
              object_id=exec_oid, artifact="execution_card.json",
              payload={"status": card.get("status"),
                       "acceptance": (card.get("acceptance") or {})
                       .get("verdict")})
    run_oids = {}
    for run in card.get("runs") or []:
        rid = run.get("run_id")
        if rid:
            run_oids[rid] = ctx.object(
                "run", rid, title=f"运行 {rid}",
                artifact="execution_card.json")
            ctx.relation("derived-from", run_oids[rid], exec_oid,
                         artifact="execution_card.json")
    events_path = source / "events.jsonl"
    if events_path.exists():
        for row in read_jsonl(events_path):
            ctx.event("stage",
                      f"{row.get('type')} {row.get('event_id')}"
                      f"{' ' + row['run_id'] if row.get('run_id') else ''}",
                      object_id=run_oids.get(row.get("run_id"),
                                             exec_oid),
                      artifact="events.jsonl",
                      payload={"upstream_type": row.get("type"),
                               "upstream_event_id": row.get("event_id"),
                               "run_id": row.get("run_id"),
                               "payload": row.get("payload")})
    else:
        ctx.gap("experiment 执行包缺 events.jsonl，事件流未收编")
    failures_path = source / "failures.jsonl"
    if failures_path.exists():
        for row in read_jsonl(failures_path):
            kind = row.get("kind")
            if kind == "failure":
                run_oid = run_oids.get(row.get("run_id")) or \
                    ctx.reference("run", row.get("run_id") or "unknown")
                ctx.event("failure",
                          f"失败 {row.get('failure_id')}："
                          f"{row.get('mast_code')} {row.get('mast_name')}",
                          object_id=run_oid, artifact="failures.jsonl",
                          payload={"failure_id": row.get("failure_id"),
                                   "failure_class":
                                       row.get("failure_class"),
                                   "reflux_target":
                                       row.get("reflux_target"),
                                   "reflux_status":
                                       row.get("reflux_status")})
                ctx.fact(row.get("root_cause") or row.get("signature")
                         or f"失败 {row.get('failure_id')}",
                         "failure_record", run_oid,
                         valid_at=_date(row.get("date")),
                         artifact="failures.jsonl",
                         anchor=row.get("failure_id"),
                         extra={"failure_id": row.get("failure_id"),
                                "mast_code": row.get("mast_code"),
                                "mast_name": row.get("mast_name"),
                                "failure_class": row.get("failure_class"),
                                "signature": row.get("signature"),
                                "exit_status": row.get("exit_status"),
                                "reflux_target": row.get("reflux_target"),
                                "reflux_status": row.get("reflux_status")})
            elif kind == "failure_review":
                ctx.event("note",
                          f"失败复核 {row.get('failure_id')}："
                          f"同意={row.get('agrees')}",
                          object_id=exec_oid, artifact="failures.jsonl",
                          payload={"failure_id": row.get("failure_id"),
                                   "reviewer": row.get("reviewer")})
    deviations_path = source / "deviations.jsonl"
    if deviations_path.exists():
        for row in read_jsonl(deviations_path):
            ctx.event("deviation",
                      f"偏离 {row.get('deviation_id') or row.get('type')}",
                      object_id=exec_oid, artifact="deviations.jsonl",
                      payload=row)


# ---------------------------------------------------------------- Analysis

def adapt_analysis(source: Path, ctx) -> None:
    """Analysis conclusion_card.json → 结论判定事实 + 承接依赖边。"""
    path = _need_file(source, "conclusion_card.json", "analysis")
    card = load_structured(path)
    analysis_id = card.get("analysis_id") or path.stem
    pkg_oid = ctx.object("analysis_package", analysis_id,
                         title=f"结论包 {analysis_id}",
                         current_version=sha256_file(path))
    exe_ref = card.get("execution_ref") or {}
    if exe_ref.get("execution_id"):
        exe_oid = ctx.reference("execution", exe_ref["execution_id"])
        ctx.relation("depends-on", pkg_oid, exe_oid)
    des_ref = card.get("design_ref") or {}
    if des_ref.get("design_id"):
        des_oid = ctx.reference("design", des_ref["design_id"])
        ctx.relation("depends-on", pkg_oid, des_oid)
    review = card.get("review") or {}
    if review.get("review_status"):
        ctx.event("note",
                  f"结论包复核状态：{review['review_status']}",
                  object_id=pkg_oid,
                  payload={"review_status": review.get("review_status"),
                           "reason": review.get("reason")})
    boundaries = {}
    for b in card.get("boundaries") or []:
        boundaries.setdefault(b.get("claim_id"), []).append(b)
    for claim in card.get("claims") or []:
        cid = claim.get("claim_id")
        if not cid:
            ctx.gap("analysis 结论卡有 claim 缺 claim_id，跳过")
            continue
        # 主张 ID 是项目级口径（与 Write claims_register / Review
        # claim_pointer 的 token 对齐），不加分析包前缀。
        claim_oid = ctx.object("claim", cid, title=f"主张 {cid}")
        statement = (f"主张 {cid} 判定：support={claim.get('support')}，"
                     f"grade={claim.get('grade')}")
        if claim.get("cap_reason"):
            statement += f"（{claim['cap_reason']}）"
        ctx.fact(statement, "conclusion_verdict", claim_oid,
                 valid_at=_date(card.get("exported_at")),
                 extra={"support": claim.get("support"),
                        "grade": claim.get("grade"),
                        "cap_reason": claim.get("cap_reason"),
                        "line_verdicts": claim.get("line_verdicts"),
                        "boundaries": boundaries.get(cid)})


# ---------------------------------------------------------------- Figure

def adapt_figure(source: Path, ctx) -> None:
    """Figure provenance.yaml 一本账 → 图对象 + 出处事实 + 修订事件。"""
    path = _need_file(source, "provenance.yaml", "figure")
    data = load_structured(path) or {}
    file_version = sha256_file(path)
    for entry in data.get("entries") or []:
        fig_id = entry.get("fig_id")
        if not fig_id:
            ctx.gap("figure provenance 有条目缺 fig_id，跳过")
            continue
        oid = ctx.object("figure", fig_id, title=f"图 {fig_id}",
                         current_version=file_version)
        parts = [f"图 {fig_id}（{entry.get('line')} 线）"]
        if entry.get("backend"):
            parts.append(f"backend={entry['backend']}")
        if entry.get("prompt_version"):
            parts.append(f"提示词版本 {entry['prompt_version']}")
        gen = entry.get("generation_model") or {}
        if isinstance(gen, dict) and gen.get("name"):
            parts.append(f"生成模型 {gen['name']}")
        ctx.fact("：".join(parts), "figure_provenance", oid,
                 valid_at=_date(entry.get("opened_at")),
                 anchor=fig_id,
                 extra={"fig_id": fig_id, "line": entry.get("line"),
                        "backend": entry.get("backend"),
                        "prompt_version": entry.get("prompt_version"),
                        "script_hash": entry.get("script_hash"),
                        "source_data_hash":
                            entry.get("source_data_hash"),
                        "reference_image_hash":
                            entry.get("reference_image_hash")})
    for h in data.get("history") or []:
        ctx.event("figure_revision",
                  f"图 {h.get('fig_id')} 修订（{h.get('at')}）",
                  payload={"fig_id": h.get("fig_id"),
                           "supersedes": h.get("supersedes"),
                           "changes": sorted((h.get("changes") or {})
                                             .keys())})
    delivery = None
    for cand in (path.parent / "delivery.yaml",
                 path.parent / "exports" / "delivery.yaml"):
        if cand.exists():
            delivery = cand
            break
    if delivery is None:
        ctx.gap("delivery.yaml 未随附 provenance 同目录，图交付版本"
                "纪律未收编（只收了 provenance 账）")
    else:
        ddata = load_structured(delivery) or {}
        ctx.event("milestone", "图包 delivery 已收编",
                  payload={"delivery_version": sha256_file(delivery),
                           "keys": sorted(ddata.keys())},
                  artifact="delivery.yaml")


# ---------------------------------------------------------------- Journal-Select

def adapt_journal_select(source: Path, ctx) -> None:
    """Journal-Select selection.json → 定刊决策事实 + 已核验期刊事实。"""
    path = _need_file(source, "selection.json", "journal-select")
    data = load_structured(path)
    sel_id = data.get("selection_id") or path.stem
    sel_oid = ctx.object("journal_selection", sel_id,
                         title=(data.get("title") or "")[:60],
                         current_version=sha256_file(path))
    decision = data.get("decision") or {}
    journal_name = (decision.get("journal") or decision.get("journal_name")
                    or data.get("decided_journal")
                    or (data.get("target") or {}).get("journal"))
    if journal_name:
        j_oid = ctx.object("journal", journal_name, title=journal_name)
        ctx.fact(f"定刊：{journal_name}", "decision", sel_oid,
                 valid_at=_date(decision.get("date")
                                or data.get("updated_at")),
                 extra={"journal_object": j_oid,
                        "decided_by": decision.get("by")})
    else:
        ctx.gap(f"selection 尚无定刊记录（状态 {data.get('status')}），"
                "未生成决策事实")
    made = 0
    for cand in data.get("candidates") or []:
        name = cand.get("journal") or cand.get("name")
        if not name:
            continue
        verified = {}
        for key, val in (cand.get("verification") or {}).items():
            if isinstance(val, dict) and val.get("status") == "verified":
                verified[key] = val.get("value")
        for key, val in (cand.get("verified") or {}).items():
            verified.setdefault(key, val)
        if not verified:
            continue
        j_oid = ctx.object("journal", name, title=name)
        detail = "；".join(f"{k}={v}" for k, v in sorted(verified.items()))
        ctx.fact(f"{name} 已核验指标：{detail}", "journal_fact", j_oid,
                 valid_at=_date(data.get("updated_at")),
                 extra={"verified": verified})
        made += 1
    if made == 0:
        ctx.gap("候选刊均无已核验指标，未生成期刊事实（未核验不落值）")


# ---------------------------------------------------------------- Design

def adapt_design(source: Path, ctx) -> None:
    """Design design.yaml → 设计主张事实 + 冻结/修订事件（含 amendment 链）。"""
    path = _need_file(source, "design.yaml", "design")
    data = load_structured(path) or {}
    design_id = data.get("design_id")
    if not design_id:
        raise AdapterError(["design.yaml 缺 design_id，无法登记设计对象"])
    freeze = data.get("freeze") or {}
    oid = ctx.object("design", design_id,
                     title=(data.get("title") or "")[:60],
                     current_version=freeze.get("content_hash")
                     or sha256_file(path))
    claims = data.get("claims") or {}
    for claim in claims.get("primary_claims") or []:
        ctx.fact(claim.get("statement") or "", "design_claim", oid,
                 valid_at=_date(data.get("created")),
                 anchor=claim.get("id"),
                 extra={"claim_id": claim.get("id"),
                        "confirmatory": claim.get("confirmatory")})
    if freeze.get("frozen_at"):
        ctx.event("milestone", f"设计 {design_id} 冻结",
                  object_id=oid, payload={"frozen_at":
                                           freeze.get("frozen_at")})
    for i, amd in enumerate(freeze.get("amendments") or []):
        if not isinstance(amd, dict):
            ctx.gap(f"amendment[{i}] 非结构化条目，只记计数未落账")
            continue
        signed = bool(amd.get("user_signed"))
        ctx.event("decision" if signed else "amendment",
                  amd.get("summary") or amd.get("field")
                  or f"amendment[{i}]",
                  object_id=oid, payload=amd)
        if not (amd.get("field") or amd.get("zone")):
            ctx.gap(f"amendment[{i}] 无字段标识，只落事件、未建字段级"
                    "取代边（待 Design 侧结构化回填）")
    for h in data.get("status_history") or []:
        if isinstance(h, dict):
            ctx.event("milestone",
                      f"设计状态 {h.get('from')} → {h.get('to')}",
                      object_id=oid, payload=h)


# ---------------------------------------------------------------- Literature

def adapt_literature(source: Path, ctx) -> None:
    """Literature 目录：证据表.jsonl → 证据事实（锚点原样保留为回指）。"""
    source = Path(source)
    ev_path = source / "证据表.jsonl"
    if not ev_path.exists():
        raise AdapterError([f"literature 收编源缺 证据表.jsonl：{source}"])
    titles = {}
    idx_path = source / "文献索引.csv"
    if idx_path.exists():
        try:
            with idx_path.open(encoding="utf-8") as fh:
                for row in csv.DictReader(fh):
                    pid = row.get("paper_id") or row.get("id")
                    title = row.get("title") or row.get("题名") \
                        or row.get("标题")
                    if pid and title:
                        titles[pid] = title
        except Exception:
            ctx.gap("文献索引.csv 存在但解析失败，论文题名未补全")
    for row in read_jsonl(ev_path):
        pid = row.get("paper_id")
        if not pid:
            ctx.gap("证据表有行缺 paper_id，跳过")
            continue
        oid = ctx.object("paper", pid, title=titles.get(pid, ""),
                         artifact="证据表.jsonl")
        anchor = None
        if row.get("note_path"):
            anchor = f"{row['note_path']}#{row.get('note_anchor')}"
        ctx.fact(row.get("finding") or "", "evidence", oid,
                 valid_at=_date(row.get("created_at")),
                 artifact="证据表.jsonl", anchor=anchor,
                 extra={"evidence_id": row.get("evidence_id"),
                        "statistic": row.get("statistic"),
                        "quote": row.get("quote"),
                        "supports_claim": row.get("supports_claim"),
                        "claim_strength": row.get("claim_strength"),
                        "limitations": row.get("limitations"),
                        "page": row.get("page")})
    retract = [p for p in source.iterdir() if "撤稿" in p.name]
    if not retract:
        ctx.gap("撤稿/Find 线结果无结构化文件，撤稿事件未收编"
                "（事件 schema 待 Literature 侧回填后接入）")


# ---------------------------------------------------------------- Write

def adapt_write(source: Path, ctx) -> None:
    """Write manuscript.yaml → 稿件对象 + use_log 过程事件（缺版本只登记）。"""
    path = _need_file(source, "manuscript.yaml", "write")
    data = load_structured(path) or {}
    mid = data.get("manuscript_id") or data.get("id") or path.parent.name
    oid = ctx.object("manuscript", mid,
                     title=(data.get("title") or "")[:60],
                     current_version=sha256_file(path))
    for i, entry in enumerate(data.get("use_log") or []):
        if not entry.get("model_version"):
            ctx.gap(f"use_log[{i}] 缺 model_version，只登记不入账"
                    "（Write 披露纪律：缺版本即拒）")
            continue
        ctx.event("tool_use",
                  f"{entry.get('tool')}（{entry.get('model')} "
                  f"{entry.get('model_version')}）用于 "
                  f"{entry.get('purpose')}",
                  object_id=oid, anchor=entry.get("section"),
                  payload=entry)
    for h in data.get("status_history") or []:
        if isinstance(h, dict):
            ctx.event("milestone",
                      f"稿件状态 {h.get('from')} → {h.get('to')}",
                      object_id=oid, payload=h)
    reg_path = path.parent / "claims_register.yaml"
    if reg_path.exists():
        reg = load_structured(reg_path) or {}
        rows = reg.get("claims") if isinstance(reg, dict) else reg
        for claim in rows or []:
            if isinstance(claim, dict) and (claim.get("id")
                                            or claim.get("claim_id")):
                ctx.object("claim",
                           claim.get("id") or claim.get("claim_id"),
                           title=(claim.get("statement") or "")[:60],
                           artifact="claims_register.yaml")


# ---------------------------------------------------------------- Review

def adapt_review(source: Path, ctx) -> None:
    """Review handoff_to_write.json → concern 事实 + 回指主张的出处边。"""
    path = _need_file(source, "handoff_to_write.json", "review")
    data = load_structured(path)
    rid = data.get("review_id") or path.stem
    pkg_oid = ctx.object("review_package", rid, title=f"评审包 {rid}",
                         current_version=sha256_file(path))
    for item in data.get("items") or []:
        cid = item.get("concern_id")
        if not cid:
            ctx.gap("review handoff 有条目缺 concern_id，跳过")
            continue
        c_oid = ctx.object("concern", cid,
                           title=(item.get("statement") or "")[:60])
        ctx.fact(item.get("statement") or "", "review_concern", c_oid,
                 valid_at=_date(data.get("generated_at")),
                 anchor=item.get("evidence_pointer"),
                 extra={"severity": item.get("severity"),
                        "action_class": item.get("action_class"),
                        "close_criterion": item.get("close_criterion"),
                        "consensus": item.get("consensus"),
                        "source_seats": item.get("source_seats"),
                        "review_package": pkg_oid})
        pointer = item.get("claim_pointer") or ""
        if ":" in pointer:
            claim_token = pointer.rsplit(":", 1)[-1]
            claim_oid = ctx.reference("claim", claim_token)
            ctx.relation("derived-from", c_oid, claim_oid)
    ctx.gap("concern 关闭状态不在 handoff 源内（以 Write 回填为准），"
            "关闭史未收编")


# ---------------------------------------------------------------- Patent

def adapt_patent(source: Path, ctx) -> None:
    """Patent 案件目录：case.yaml + ledger.yaml（memory_export 段）。

    契约（phase5-patent 第 3 节）：案件即对象、状态流转/期限即事件、
    查新结论与 worth-it 判断即事实。状态当前态以 case.yaml 顶层
    status 与 status_history 为权威；ledger 的 memory_export 段生成
    时点可能早于案件头（集成契约偏差 D-INT-1），其 events 只取期限
    部分，facts 逐条照抄。
    """
    case_path = _need_file(source, "case.yaml", "patent")
    case_dir = case_path.parent
    case = load_structured(case_path) or {}
    case_id = case.get("case_id")
    if not case_id:
        raise AdapterError(["patent case.yaml 缺 case_id，无法登记案件对象"])
    oid = ctx.object("patent_case", case_id,
                     title=(case.get("title") or "")[:60],
                     current_version=sha256_file(case_path),
                     artifact="case.yaml")
    for h in case.get("status_history") or []:
        if not isinstance(h, dict):
            continue
        ctx.event("milestone",
                  f"专利案件 {case_id} 状态流转：{h.get('state')}",
                  object_id=oid, artifact="case.yaml",
                  payload={"state": h.get("state"), "at": h.get("at"),
                           "by": h.get("by")})
    blocked = case.get("blocked")
    if isinstance(blocked, dict) and blocked.get("gate_id"):
        ctx.event("note",
                  f"专利案件 {case_id} 被门拦：{blocked['gate_id']}",
                  object_id=oid, artifact="case.yaml",
                  payload={"blocked": blocked})
    ledger_path = case_dir / "ledger.yaml"
    if not ledger_path.exists():
        ctx.gap("patent 案件缺 ledger.yaml，期限与 memory_export "
                "判断事实未收编")
        return
    ledger = load_structured(ledger_path) or {}
    for d in ledger.get("deadlines") or []:
        if not isinstance(d, dict):
            continue
        ctx.event("deadline",
                  f"专利期限：{d.get('label')}（到期 {d.get('due')}）",
                  object_id=oid, artifact="ledger.yaml",
                  payload={"kind": d.get("kind"), "label": d.get("label"),
                           "due": d.get("due"), "basis": d.get("basis")})
    export = ledger.get("memory_export") or {}
    facts = export.get("facts") or []
    if not facts:
        ctx.gap("patent ledger.yaml 无 memory_export.facts，"
                "查新/worth-it 判断事实未收编")
    for row in facts:
        if not isinstance(row, dict) or not row.get("fact"):
            continue
        ctx.fact(row["fact"], "patent_assessment", oid,
                 artifact="ledger.yaml",
                 anchor=row.get("evidence_ref"),
                 extra={"evidence_ref": row.get("evidence_ref"),
                        "disclaimers": row.get("disclaimers")})


# ---------------------------------------------------------------- Copyright

def adapt_copyright(source: Path, ctx) -> None:
    """Software-Copyright 案件目录：copyright.yaml 登记头 + 留痕三件。

    形态（phase5-copyright 集成交接）：案件即对象（本包无 case_id，
    对象上游 ID 由登记事实派生：软件全称@版本）；定版/递交/补正等
    节点即事件（tool_use.jsonl 过程留痕 + confirmations.jsonl 确认
    回执 + 登记头状态）；登记事实与源码冻结快照即事实。登记号在 v1
    由用户递交后回填，有则收、无则不收（缺失非异常，不点名）。
    """
    head_path = _need_file(source, "copyright.yaml",
                            "software-copyright")
    case_dir = head_path.parent
    case = load_structured(head_path) or {}
    facts_data = None
    facts_path = case_dir / "facts.yaml"
    if facts_path.exists():
        facts_data = load_structured(facts_path) or {}
    else:
        ctx.gap("软著案件缺 facts.yaml，软件登记事实未收编（案件对象"
                "以登记头与目录名登记）")
    software = (facts_data or {}).get("software") or {}
    full_name = software.get("full_name")
    version = software.get("version")
    if full_name and version:
        upstream_id = f"{full_name}@{version}"
    elif full_name:
        upstream_id = full_name
    else:
        upstream_id = case_dir.name
    snapshot_path = case_dir / "snapshot.json"
    current_version = (sha256_file(snapshot_path)
                       if snapshot_path.exists()
                       else sha256_file(head_path))
    oid = ctx.object("copyright_case", upstream_id,
                     title=(case.get("title") or "")[:60],
                     current_version=current_version,
                     artifact="copyright.yaml")
    ctx.event("milestone",
              f"软著案件状态：{case.get('status')}",
              object_id=oid, artifact="copyright.yaml",
              payload={"status": case.get("status"),
                       "correction": case.get("correction")})
    tool_path = case_dir / "tool_use.jsonl"
    if tool_path.exists():
        for row in read_jsonl(tool_path):
            ctx.event("tool_use",
                      f"{row.get('action')} {row.get('target')}："
                      f"{row.get('detail')}",
                      object_id=oid, artifact="tool_use.jsonl",
                      payload={"actor": row.get("actor"),
                               "ts": row.get("ts"),
                               "action": row.get("action"),
                               "target": row.get("target")})
    else:
        ctx.gap("软著案件缺 tool_use.jsonl，过程留痕事件未收编")
    conf_path = case_dir / "confirmations.jsonl"
    if conf_path.exists():
        for row in read_jsonl(conf_path):
            ctx.event("confirmation",
                      f"确认 {row.get('kind')}:{row.get('target')}",
                      object_id=oid, artifact="confirmations.jsonl",
                      payload={"actor": row.get("actor"),
                               "ts": row.get("ts"),
                               "kind": row.get("kind"),
                               "target": row.get("target"),
                               "content_hash":
                                   (row.get("content_hash") or "")[:12],
                               "note": row.get("note")})
    else:
        ctx.gap("软著案件缺 confirmations.jsonl，确认回执事件未收编")
    if facts_data:
        owner = facts_data.get("owner") or {}
        dev = facts_data.get("development") or {}
        pub = facts_data.get("publication") or {}
        rights = facts_data.get("rights") or {}
        statement = (
            f"软件著作权登记事实：{full_name} {version}，著作权人 "
            f"{owner.get('name')}（{owner.get('type')}），开发方式 "
            f"{dev.get('mode')}，完成日期 {dev.get('completion_date')}，"
            f"发表状态 {pub.get('status')}，权利取得 {rights.get('acquisition')}")
        ctx.fact(statement, "copyright_facts", oid,
                 valid_at=_date(dev.get("completion_date")),
                 artifact="facts.yaml",
                 extra={"software": software, "owner": owner,
                        "development": dev, "publication": pub,
                        "rights": rights})
    if snapshot_path.exists():
        snap = load_structured(snapshot_path) or {}
        ctx.fact(f"源码冻结快照：{snap.get('file_count')} 个文件、"
                 f"源程序量 {snap.get('total_lines')} 行",
                 "source_snapshot", oid,
                 valid_at=_date(snap.get("frozen_at")),
                 artifact="snapshot.json",
                 extra={"file_count": snap.get("file_count"),
                        "total_lines": snap.get("total_lines"),
                        "nonempty_lines": snap.get("nonempty_lines"),
                        "languages": snap.get("languages"),
                        "files": snap.get("files")})
    reg_no = case.get("registration_no")
    if reg_no:
        ctx.fact(f"软件著作权登记号：{reg_no}",
                 "copyright_registration", oid,
                 artifact="copyright.yaml",
                 extra={"registration_no": reg_no})


# ---------------------------------------------------------------- Crawler

def adapt_crawler(source: Path, ctx) -> None:
    """Crawler data-sources 目录：crawler.yaml + targets/ + 两本流水。

    形态（phase5-crawler 定位：通道层扩展位）：工作区即对象、目标
    即对象（derived-from 工作区）；抓取批次、预检记录、变更事件是
    一等事件源（events.jsonl 逐条直通）；留存凭据即事实
    （provenance.jsonl 逐条，哈希与预检引用照抄）。
    """
    source = Path(source)
    head_path = _need_file(source, "crawler.yaml", "crawler")
    head = load_structured(head_path) or {}
    ws_id = head.get("workspace_id") or source.name
    ws_oid = ctx.object("crawl_workspace", ws_id,
                        title=f"采集工作区 {head.get('project') or ''}",
                        current_version=sha256_file(head_path),
                        artifact="crawler.yaml")
    target_oids = {}
    targets_dir = source / "targets"
    if targets_dir.is_dir():
        for tdir in sorted(targets_dir.iterdir()):
            tpath = tdir / "target.yaml"
            if not tdir.is_dir() or not tpath.exists():
                continue
            t = load_structured(tpath) or {}
            tid = t.get("target_id") or tdir.name
            t_oid = ctx.object("crawl_target", tid,
                               title=(t.get("name") or "")[:60],
                               artifact=f"targets/{tid}/target.yaml")
            target_oids[tid] = t_oid
            ctx.relation("derived-from", t_oid, ws_oid,
                         artifact=f"targets/{tid}/target.yaml")
            ctx.fact(f"采集目标 {tid}：通道 {t.get('channel')}，"
                     f"用途 {t.get('purpose_kind')}，供 "
                     f"{t.get('consumer')}",
                     "crawl_target_profile", t_oid,
                     artifact=f"targets/{tid}/target.yaml",
                     extra={"base_url": t.get("base_url"),
                            "channel": t.get("channel"),
                            "purpose_kind": t.get("purpose_kind"),
                            "consumer": t.get("consumer")})
            state_path = tdir / "state.yaml"
            if state_path.exists():
                st = load_structured(state_path) or {}
                if st.get("circuit_broken"):
                    ctx.event("note",
                              f"采集目标 {tid} 已熔断："
                              f"{st.get('circuit_reason')}",
                              object_id=t_oid,
                              artifact=f"targets/{tid}/state.yaml",
                              payload={"circuit_broken": True,
                                       "circuit_reason":
                                           st.get("circuit_reason"),
                                       "consecutive_refusals":
                                           st.get("consecutive_refusals")})
    else:
        ctx.gap("crawler data-sources 缺 targets/ 目录，采集目标未收编")
    events_path = source / "events.jsonl"
    if events_path.exists():
        for row in read_jsonl(events_path):
            ctx.event("stage",
                      row.get("detail") or row.get("type") or "",
                      object_id=target_oids.get(row.get("target_id"),
                                                ws_oid),
                      artifact="events.jsonl",
                      payload={"upstream_type": row.get("type"),
                               "upstream_event_id": row.get("event_id"),
                               "target_id": row.get("target_id"),
                               "data": row.get("data")})
    else:
        ctx.gap("crawler data-sources 缺 events.jsonl，"
                "批次/预检/变更事件未收编")
    prov_path = source / "provenance.jsonl"
    if prov_path.exists():
        for row in read_jsonl(prov_path):
            t_oid = target_oids.get(row.get("target_id"), ws_oid)
            ctx.fact(f"留存 {row.get('kind')}：{row.get('url')}"
                     f"（通道 {row.get('channel')}，HTTP "
                     f"{row.get('http_status')}，{row.get('bytes')} 字节）",
                     "crawl_provenance", t_oid,
                     valid_at=_date(row.get("at")),
                     artifact="provenance.jsonl",
                     anchor=row.get("prov_id"),
                     extra={"prov_id": row.get("prov_id"),
                            "run_id": row.get("run_id"),
                            "sha256": row.get("sha256"),
                            "fingerprint": row.get("fingerprint"),
                            "precheck_ref": row.get("precheck_ref"),
                            "retention_tier": row.get("retention_tier"),
                            "raw_path": row.get("raw_path"),
                            "supersedes": row.get("supersedes")})
    else:
        ctx.gap("crawler data-sources 缺 provenance.jsonl，"
                "留存事实未收编")


ADAPTERS = {
    "literature": adapt_literature,
    "idea": adapt_idea,
    "design": adapt_design,
    "experiment": adapt_experiment,
    "analysis": adapt_analysis,
    "write": adapt_write,
    "figure": adapt_figure,
    "journal-select": adapt_journal_select,
    "review": adapt_review,
    "patent": adapt_patent,
    "software-copyright": adapt_copyright,
    "crawler": adapt_crawler,
}

#: 适配器版本：上游格式在 v1.1 变更时随登记头登记，旧版保留一代。
ADAPTER_VERSIONS = {name: "1.0" for name in ADAPTERS}
