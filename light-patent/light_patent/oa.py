"""P5 审查意见答复：缺陷结构化、修改账（第 33 条出处）、
后备特征、会稿问题清单导出（Q8，只导出不建状态机）。

答复复用 P2 的 D1/Fk 证据账：申请时锁定的区别特征表即答辩
骨架，不在答复时重建。每条修改必须指出在原说明书和权利要求
书中的出处（专利法第 33 条），无出处不许落账（LP-08）。
"""

from __future__ import annotations

from pathlib import Path

from . import schema
from .project import (
    PatentError, case_path, load_case, load_yaml_or, set_status,
)
from .util import append_jsonl, read_jsonl, today


def register_office_action(root, payload: dict) -> dict:
    """登记审查意见。payload: {action_id, notified_at, response_months,
    defects: [{defect_id, article, claim_refs, cited_docs, summary}]}。
    response_months 以通知书为准登记，本包不臆定法定期限。"""
    root = Path(root)
    case = load_case(root)
    gaps = []
    if not payload.get("action_id"):
        gaps.append("缺 action_id")
    if not payload.get("notified_at"):
        gaps.append("缺通知发文日 notified_at（答复期起算点）")
    if not payload.get("response_months"):
        gaps.append("缺答复期月数 response_months（以通知书为准登记）")
    if not (payload.get("defects") or []):
        gaps.append("缺逐条缺陷清单 defects（审查意见须结构化）")
    for d in payload.get("defects") or []:
        if not d.get("article"):
            gaps.append(f"缺陷 {d.get('defect_id')!r} 缺引用法条 article"
                        "（带版本年，如 专利法第 22 条第 3 款）")
    if gaps:
        raise PatentError(gaps)
    row = {"registered_at": today(), **payload}
    append_jsonl(case_path(root, "oa_actions"), [row])
    if case["status"] in ("filed", "checked"):
        set_status(root, case, "office_action", "light-patent oa")
    from .ledger import refresh_deadlines
    refresh_deadlines(root)
    return {"action_id": payload["action_id"],
            "defects": len(payload["defects"])}


def register_amendment(root, payload: dict) -> dict:
    """登记一条修改。必须带 basis_pointer（原申请文件出处）与
    basis_quote（出处原文摘录），缺一拒绝（LP-08）。"""
    root = Path(root)
    load_case(root)
    gaps = []
    for field in ("amendment_id", "target", "before", "after"):
        if not payload.get(field):
            gaps.append(f"修改条目缺字段 {field}")
    if not payload.get("basis_pointer"):
        gaps.append("修改缺 basis_pointer：必须指出修改在原说明书和"
                    "权利要求书中的出处（专利法第 33 条，LP-08）")
    if not payload.get("basis_quote"):
        gaps.append("修改缺 basis_quote：出处原文摘录必填，防指针虚设")
    if payload.get("art33_checked") is not True:
        gaps.append("修改未确认 art33_checked：第 33 条自查（修改未超出"
                    "原书记载范围）必须显式确认")
    if gaps:
        raise PatentError(gaps)
    row = {"registered_at": today(), **payload}
    append_jsonl(case_path(root, "oa_amendments"), [row])
    case = load_case(root)
    if case["status"] == "office_action":
        set_status(root, case, "responded", "light-patent oa amend")
    return {"amendment_id": payload["amendment_id"]}


def export_meeting_questions(root) -> dict:
    """会稿问题清单单向导出（Q8）：汇总未决缺陷、缺口与待确认
    修改，生成给代理师复核会议的问题清单。只导出，不建状态机。"""
    root = Path(root)
    case = load_case(root)
    actions = read_jsonl(case_path(root, "oa_actions"))
    amendments = read_jsonl(case_path(root, "oa_amendments"))
    gaps_data = load_yaml_or(root, "gaps", {"gaps": []})
    d1 = load_yaml_or(root, "d1", {}) or {}
    lines = [
        f"# 会稿问题清单：{case['title']}",
        "",
        f"声明：{schema.DRAFT_DISCLAIMER}。本清单为发明人自助成稿后交"
        "专利代理师复核的单向导出件，只列问题与证据指针，不含结论承诺。",
        "",
        "## 一、审查意见待决问题",
    ]
    amended_targets = {a.get("defect_ref") for a in amendments}
    open_count = 0
    for act in actions:
        for d in act.get("defects") or []:
            mark = "已拟修改" if d.get("defect_id") in amended_targets else "未拟修改"
            lines.append(f"- [{mark}] {d.get('defect_id')}（{d.get('article')}）："
                         f"{d.get('summary')}；引证 {d.get('cited_docs')}")
            open_count += 1
    if not actions:
        lines.append("- （暂无已登记审查意见）")
    lines += ["", "## 二、交底与说明书缺口（待发明人确认）"]
    for g in gaps_data.get("gaps") or []:
        lines.append(f"- {g.get('item')}（位置：{g.get('location')}）")
    if not gaps_data.get("gaps"):
        lines.append("- （无登记缺口）")
    lines += ["", "## 三、答辩骨架锚点（复用查新证据账）",
              f"- D1：{d1.get('d1')}；区别特征："
              f"{[f.get('fk') for f in d1.get('distinguishing_features') or []]}"]
    lines += ["", "## 四、请代理师裁断的问题",
              "- 独权是否按区别特征组合收窄，还是保留现宽度争辩？",
              "- 修改条目的第 33 条出处是否足以支撑修改后权要？",
              "- 是否需要分案或另行立项保护旁侧方案？"]
    target = case_path(root, "meeting_questions")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"path": str(target), "defects_listed": open_count,
            "gaps_listed": len(gaps_data.get("gaps") or [])}
