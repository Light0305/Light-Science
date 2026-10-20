"""P6 静态台账：期限清单、版本链、worth-it 判断、memory 导出段。

期限只做机械计算 + 清单呈现，提醒靠 leader route 点名本案状态
与 blocked 字段（Q6/LD-02），本包不建 cron 与通知承诺。PCT 只
给优先权 12 个月窗与单一性提示（Q2）。
"""

from __future__ import annotations

from pathlib import Path

from . import schema
from .project import (
    PatentError, case_path, load_case, load_ledger, save_case, save_ledger,
    set_status,
)
from .util import add_months, parse_date, read_jsonl, today


def refresh_deadlines(root) -> list:
    """按已登记日期机械重算期限清单。"""
    root = Path(root)
    case = load_case(root)
    ledger = load_ledger(root)
    deadlines = []
    for prio in (case.get("parties") or {}).get("priority") or []:
        pdate = parse_date(prio.get("date"))
        if pdate:
            deadlines.append({
                "kind": "priority_window",
                "label": f"优先权/PCT 国际申请窗（基于 {prio.get('app_no')}）",
                "due": add_months(pdate, schema.PRIORITY_MONTHS).isoformat(),
                "basis": "优先权 12 个月；PCT 只提示时间窗与单一性，"
                         "不写外国申请文件（Q2）",
            })
    filing = case.get("filing") or {}
    fdate = parse_date(filing.get("filing_date"))
    if fdate:
        deadlines.append({
            "kind": "request_examination",
            "label": "请求实质审查期限（自申请日起 3 年）",
            "due": add_months(fdate, 36).isoformat(),
            "basis": "专利法（2020 年修正）第 35 条",
        })
    for act in read_jsonl(case_path(root, "oa_actions")):
        ndate = parse_date(act.get("notified_at"))
        if ndate and act.get("response_months"):
            deadlines.append({
                "kind": "office_action_response",
                "label": f"审查意见答复期（{act.get('action_id')}）",
                "due": add_months(ndate, int(act["response_months"])).isoformat(),
                "basis": "以通知书载明期限为准，本清单按登记月数机械算",
            })
    if case.get("status") == "granted" and fdate:
        deadlines.append({
            "kind": "annuity",
            "label": "年费周年（授权后逐年，金额以当年标准为准）",
            "due": add_months(fdate, 12).isoformat(),
            "basis": "静态清单口径：只列周年，不做缴费提醒承诺（Q6）",
        })
    deadlines.sort(key=lambda d: d["due"])
    ledger["deadlines"] = deadlines
    _sync_memory_export(root, case, ledger)
    save_ledger(root, ledger)
    return deadlines


def register_filing(root, payload: dict) -> dict:
    """登记递交事实（申请号/申请日由用户按受理通知书填写，
    本包不生成、不猜测）。"""
    root = Path(root)
    case = load_case(root)
    if not payload.get("application_no") or not payload.get("filing_date"):
        raise PatentError(["递交登记须带申请号与申请日（以受理通知书为准）"])
    case["filing"]["application_no"] = payload["application_no"]
    case["filing"]["filing_date"] = payload["filing_date"]
    save_case(root, case)
    set_status(root, case, "filed", "light-patent ledger file")
    deadlines = refresh_deadlines(root)
    return {"application_no": payload["application_no"],
            "deadlines": len(deadlines)}


def register_priority(root, payload: dict) -> dict:
    root = Path(root)
    case = load_case(root)
    if not payload.get("app_no") or not parse_date(payload.get("date")):
        raise PatentError(["优先权登记须带在先申请号与申请日"])
    case.setdefault("parties", {}).setdefault("priority", []).append({
        "app_no": payload["app_no"], "date": payload["date"],
        "country": payload.get("country") or "CN",
    })
    save_case(root, case)
    refresh_deadlines(root)
    return {"priority_count": len(case["parties"]["priority"])}


def set_worth_it(root, payload: dict) -> dict:
    """worth-it 判断（Q4）：允许给结论，证据账为空不许落。"""
    root = Path(root)
    case = load_case(root)
    gaps = []
    if payload.get("verdict") not in schema.WORTH_IT_VERDICTS:
        gaps.append(f"worth-it 结论 {payload.get('verdict')!r} 不在词表内"
                    "（file / file_narrowed / abandon）")
    evidence = payload.get("evidence") or []
    if not evidence:
        gaps.append("worth-it 证据账为空：允许给结论，但必须附证据账（Q4）")
    for e in evidence:
        if not e.get("ref"):
            gaps.append("worth-it 证据条目缺 ref 指针")
    if not (payload.get("rationale") or "").strip():
        gaps.append("worth-it 缺判断理由 rationale")
    if gaps:
        raise PatentError(gaps)
    ledger = load_ledger(root)
    ledger["worth_it"] = {
        "verdict": payload["verdict"],
        "rationale": payload["rationale"],
        "evidence": evidence,
        "decided_at": today(),
        "disclaimers": [schema.DRAFT_DISCLAIMER, schema.SCREENING_DISCLAIMER],
    }
    save_ledger(root, ledger)
    return ledger["worth_it"]


def _sync_memory_export(root, case, ledger) -> None:
    """memory 承接段（MM2-13 适配器直读）：案件即对象、状态流转
    与期限即事件、查新结论与 worth-it 即事实（带证据指针）。"""
    from .project import load_yaml_or
    events = [{"event": f"status:{h['state']}", "at": h["at"]}
              for h in case.get("status_history") or []]
    events += [{"event": f"deadline:{d['kind']}", "due": d["due"]}
               for d in ledger.get("deadlines") or []]
    facts = []
    d1 = load_yaml_or(root, "d1", None)
    if d1:
        facts.append({
            "fact": f"查新门={d1.get('gate')}，D1={d1.get('d1')}",
            "evidence_ref": "novelty/d1.yaml",
            "disclaimers": [schema.SCREENING_DISCLAIMER],
        })
    if ledger.get("worth_it"):
        facts.append({
            "fact": f"worth-it={ledger['worth_it']['verdict']}",
            "evidence_ref": "ledger.yaml#worth_it",
            "disclaimers": [schema.SCREENING_DISCLAIMER],
        })
    ledger["memory_export"] = {
        "objects": [{
            "object": "patent_case", "case_id": case["case_id"],
            "title": case["title"], "status": case["status"],
        }],
        "events": events,
        "facts": facts,
    }
