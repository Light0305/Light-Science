"""状态机与定版门 + amendment 追加协议（确定性校验器）。

主线：draft → reviewed → frozen
旁路：returned（入口校验打回 Idea，附打回单）/ blocked（外部条件未备）
frozen 是终态：正文一字不回改，一切修订走 amendment 追加（约束 12）。

门规则一览（与 README / SKILL 同步维护）：
- draft → reviewed ：结构+硬规则全过（validate_design）+ 输入承接六项
                      全部 accepted/expanded 且无未清打回项（打回纪律：
                      六项未齐不许离开 draft，缺项不许 Design 临场发明）
- reviewed → frozen ：定版评审记录齐全——Stage 1 五条逐项 pass + 决议
                      pass + review_status 非 REVIEW_UNAVAILABLE（拍板 ①
                      跨模型硬门降级通道：评审不可用只许停、不许定版）
                      + 评审者与设计者不同模型家族（同族自审不作数，
                      约束 13）；过门即落 frozen_at + 内容哈希
- * → returned      ：return_record 齐全——missing_items 非空 + reason
- * → blocked       ：block_record 齐全——reason + unblock_condition
- returned → draft  ：打回项全部 resolved 后才许重新 intake 回 draft
- blocked → draft   ：解阻后回 draft

amendment 分级批准（拍板 ⑤）：命门字段（判读标准 / 主指标 / 主张 /
停止规则）的修订必须 user_signed，其余自动追加留痕。

amendment 增量评审与类别分流（v1.1 DES-D02 + C-补04）：每条
amendment 声明 category（prewritten_branch 定版预写偏离分支 /
unforeseen 未预见变更，默认 unforeseen 取最严口径）；命门 amendment
自落盘起 review.status=pending_review，增量评审（review prepare /
record --amendment）落盘前 export 被拦；预写分支类必须以 branch_ref
点名 plan.deviation_branches 中的定版分支且变更字段落在分支影响面
内，否则类别与影响面不符、点名拒绝。评审分流（轻/全两轨）在
review.py 执行。命门用户签纪律不放松。
"""

from __future__ import annotations

import copy
import re

from .schema import (
    AMD_CATEGORIES,
    INTAKE_ITEMS,
    REVIEW_DECISIONS,
    STAGE1_ITEMS,
    _nonempty_str,
    compute_content_hash,
    is_critical_field,
    validate_design,
)

NEXT = {
    "draft": ("reviewed", "returned", "blocked"),
    "reviewed": ("frozen", "blocked"),
    "frozen": (),
    "returned": ("draft", "blocked"),
    "blocked": ("draft",),
}


class GateError(Exception):
    """门校验失败。errors 为逐条人读原因。"""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("；".join(errors))


def _intake_errors(design: dict) -> list[str]:
    """输入承接门：六项逐项在场且 accepted/expanded、无未清打回项。"""
    errs = []
    intake = design.get("intake") or {}
    spec = intake.get("spec_intake") or []
    by_item = {s.get("item"): s for s in spec if isinstance(s, dict)}
    for item in INTAKE_ITEMS:
        s = by_item.get(item)
        if s is None:
            errs.append(f"输入承接缺项：{item} 未登记承接记录")
        elif s.get("status") not in ("accepted", "expanded"):
            errs.append(f"输入承接未过：{item} 状态为 {s.get('status')!r}"
                        "（六项未齐不许离开 draft；缺项须打回 Idea 回补，"
                        "不许 Design 临场发明口径）")
    for r in intake.get("returned_items") or []:
        if isinstance(r, dict) and not r.get("resolved"):
            errs.append(f"打回项未清：{r.get('item')}（{r.get('reason')}）")
    return errs


def _review_errors(design: dict) -> list[str]:
    """定版评审门（reviewed → frozen）。"""
    errs = []
    fr = design.get("freeze") or {}
    rev = fr.get("review")
    if not isinstance(rev, dict):
        return ["缺定版评审记录 freeze.review（Stage 1 式五条评审未落盘，"
                "不许「评审说差不多」式放行）"]
    if rev.get("review_status") == "REVIEW_UNAVAILABLE":
        errs.append("跨模型评审不可用（REVIEW_UNAVAILABLE）：硬门未过，"
                    "不许定版，恢复后补评审（拍板 ①降级通道）")
    if not _nonempty_str(rev.get("reviewer")):
        errs.append("freeze.review.reviewer 为空（评审者身份必须落盘）")
    if not _nonempty_str(rev.get("date")):
        errs.append("freeze.review.date 为空")
    items = rev.get("items")
    if not isinstance(items, dict):
        errs.append("freeze.review.items 缺失（Stage 1 五条须逐项评审）")
        items = {}
    for it in STAGE1_ITEMS:
        st = (items.get(it) or {}).get("status") if isinstance(items.get(it), dict) \
            else items.get(it)
        if st != "pass":
            errs.append(f"freeze.review.items.{it} 未 pass（当前 {st!r}）："
                        "五条逐项 pass 才许定版")
    if rev.get("decision") not in REVIEW_DECISIONS:
        errs.append(f"freeze.review.decision 非法：{rev.get('decision')!r}")
    elif rev.get("decision") != "pass":
        errs.append("freeze.review.decision 非 pass：评审未通过，不许定版")
    # 异家族校验：评审者不得与设计生成者同家族（自评不作定版依据）
    reg = design.get("registration") or {}
    designer = reg.get("designer") or {}
    dfam = designer.get("family")
    rfam = rev.get("family")
    if _nonempty_str(dfam) and _nonempty_str(rfam) \
            and str(dfam).strip().lower() == str(rfam).strip().lower():
        errs.append(f"评审者与设计者同模型家族（{rfam}）：同族自审不作定版依据"
                    "（约束 13），须异家族复核")
    return errs


def advance(design: dict, to: str, *, by: str = "", date: str,
            note: str = "") -> dict:
    """按状态机验门推进。成功返回 design（已就地修改状态与留痕）；
    失败抛 GateError 并逐条列明未过门的项。"""
    cur = design.get("status")
    if to not in NEXT.get(cur, ()):
        raise GateError([f"非法跃迁：{cur} → {to}"
                         f"（{cur} 只许去 {NEXT.get(cur, ()) or '终态，无出边'}）"])

    errs: list[str] = []
    if to == "reviewed":
        errs.extend(validate_design(design))
        errs.extend(_intake_errors(design))
    elif to == "frozen":
        errs.extend(validate_design(design))
        errs.extend(_review_errors(design))
    elif to == "returned":
        rr = design.get("return_record") or {}
        if not (isinstance(rr.get("missing_items"), list) and rr["missing_items"]):
            errs.append("打回须带缺项清单 return_record.missing_items（非空）")
        if not _nonempty_str(rr.get("reason")):
            errs.append("打回须带理由 return_record.reason")
    elif to == "blocked":
        br = design.get("block_record") or {}
        if not _nonempty_str(br.get("reason")):
            errs.append("blocked 须带原因 block_record.reason")
        if not _nonempty_str(br.get("unblock_condition")):
            errs.append("blocked 须带解阻条件 block_record.unblock_condition")
    elif to == "draft" and cur == "returned":
        for r in (design.get("intake") or {}).get("returned_items") or []:
            if isinstance(r, dict) and not r.get("resolved"):
                errs.append(f"打回项未回补：{r.get('item')} 尚未 resolved，"
                            "不许回 draft")

    if errs:
        raise GateError(errs)

    design["status"] = to
    design["updated"] = date
    if to == "frozen":
        fr = design.setdefault("freeze", {})
        fr["frozen_at"] = date
        fr["content_hash"] = compute_content_hash(design)
    hist = design.setdefault("status_history", [])
    hist.append({"from": cur, "to": to, "date": date,
                 "by": by or "light-design advance", "note": note})
    return design


# ---------- amendment（frozen 后唯一修订通道） ----------

_SEG_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)(?:\[(\d+)\])?$")


def _parse_path(path: str) -> list:
    """'claims.primary_claims[0].statement' → ['claims','primary_claims',0,'statement']"""
    parts: list = []
    for seg in path.split("."):
        m = _SEG_RE.match(seg.strip())
        if not m:
            raise ValueError(f"字段路径非法：{path!r}（段 {seg!r}）")
        parts.append(m.group(1))
        if m.group(2) is not None:
            parts.append(int(m.group(2)))
    return parts


def _set_path(obj, parts: list, value) -> None:
    cur = obj
    for p in parts[:-1]:
        if isinstance(p, int):
            cur = cur[p]
        else:
            if not isinstance(cur, dict):
                raise ValueError(f"字段路径穿过非映射节点：{p}")
            cur = cur.setdefault(p, {})
    last = parts[-1]
    if isinstance(last, int):
        cur[last] = value
    else:
        cur[last] = value


_MISSING = object()


def _get_path(obj, parts: list):
    """按路径取值，取不到返回 _MISSING（供 amendment 前后值记录）。"""
    cur = obj
    for p in parts:
        if isinstance(p, int):
            if not isinstance(cur, list) or p >= len(cur):
                return _MISSING
            cur = cur[p]
        else:
            if not isinstance(cur, dict) or p not in cur:
                return _MISSING
            cur = cur[p]
    return cur


def _path_within(path: str, prefix: str) -> bool:
    """字段路径是否落在 prefix 影响面内（相等 / 子字段 / 列表下标）。"""
    p, pre = (path or "").strip(), (prefix or "").strip()
    return p == pre or p.startswith(pre + ".") or p.startswith(pre + "[")


def _prewritten_branch_errors(design: dict, field_path: str,
                              branch_ref) -> list[str]:
    """DES-D02/C-补04 分流判据：声称预写分支，证据必须双查过——
    branch_ref 点名的分支真实存在于定版预写（plan.deviation_branches），
    且变更字段落在该分支声明的 fields 影响面内。任一不符点名返回。"""
    if not _nonempty_str(branch_ref):
        return ["category=prewritten_branch 必须以 branch_ref 点名定版时"
                "预写的偏离分支（plan.deviation_branches 中的 id）："
                "拿不出预写证据的变更按未预见变更（unforeseen）登记"]
    branches = (design.get("plan") or {}).get("deviation_branches") or []
    branch = next((b for b in branches
                   if isinstance(b, dict) and b.get("id") == branch_ref), None)
    if branch is None:
        return [f"branch_ref={branch_ref!r} 在 plan.deviation_branches 中"
                "不存在：类别与影响面不符——声称的预写分支未在定版文本中"
                "预写（DES-D02/C-补04），请改按 unforeseen 登记并走全评审"]
    fields = branch.get("fields") or []
    if not any(_path_within(field_path, str(f)) for f in fields):
        return [f"变更字段 {field_path} 不在预写分支 {branch_ref} 声明的"
                f"影响面 {fields} 内：类别与影响面不符（DES-D02/C-补04），"
                "超出预写范围的变更请改按 unforeseen 登记并走全评审"]
    return []


def apply_amendment(design: dict, field_path: str, value, *, reason: str,
                    results_seen: str, user_signed: bool = False,
                    by: str = "", date: str,
                    category: str = "unforeseen",
                    branch_ref: str | None = None) -> dict:
    """对 frozen 设计书追加一条 amendment 并就地应用修订。

    纪律（约束 12 + 拍板 ⑤）：
    - 只许 frozen 状态走 amendment；draft/reviewed 直接改 yaml；
    - 命门字段（判读标准/主指标/主张/停止规则）必须 user_signed=true；
    - 每条必须写明 reason 与 results_seen（改时是否已见结果）；
    - 修订后重算内容哈希并记进 amendment.new_hash，链式可回溯；
    - 原文字段不删历史：变更只通过本函数落盘并留痕；
    - 类别分流（DES-D02/C-补04）：category 必落盘（默认 unforeseen）；
      prewritten_branch 须过分支证据双查（见 _prewritten_branch_errors）；
    - 命门 amendment 落盘即带 review.status=pending_review：增量评审
      落盘（或 REVIEW_UNAVAILABLE 显式落字）前 export 被拦（export.py）；
      非命门 amendment review.status=not_required，不触发增量评审。
    返回新追加的 amendment 记录。失败抛 GateError / ValueError。
    """
    if design.get("status") != "frozen":
        raise GateError([f"amendment 只许对 frozen 设计书追加"
                         f"（当前状态 {design.get('status')}，未定版请直接改 design.yaml）"])
    if not _nonempty_str(reason):
        raise GateError(["amendment 必须写明 reason（为何改）"])
    if not _nonempty_str(results_seen):
        raise GateError(["amendment 必须声明 results_seen（改时是否已见结果、见了什么）"])
    if category not in AMD_CATEGORIES:
        raise GateError([f"amendment category 非法：{category!r}"
                         f"（须为 {AMD_CATEGORIES} 之一，DES-D02 类别分流）"])
    critical = is_critical_field(field_path)
    if critical and not user_signed:
        raise GateError([f"{field_path} 是命门字段（判读标准/主指标/主张/停止规则），"
                         "amendment 必须用户签（user_signed=true，拍板 ⑤）"])
    parts = _parse_path(field_path)  # ValueError 直接上抛
    if parts and parts[0] in ("freeze", "status_history", "status"):
        raise GateError([f"{field_path} 属冻结留痕区，不许经 amendment 改写"])
    if category == "prewritten_branch":
        berrs = _prewritten_branch_errors(design, field_path, branch_ref)
        if berrs:
            raise GateError(berrs)

    before = _get_path(design, parts)
    new_design = copy.deepcopy(design)
    _set_path(new_design, parts, value)
    # DES-D01：amendment 触及 SESOI 登记块时，登记行派生副本在同一条
    # amendment 内机械刷新（副本与登记块的一致性由 validate 覆盖，
    # 不另起 amendment、不许行内副本滞留旧值）。
    if len(parts) >= 2 and parts[0] == "evaluation" and parts[1] == "sesoi":
        _block = (new_design.get("evaluation") or {}).get("sesoi")
        _ho = new_design.get("handoff") or {}
        for _row in _ho.get("expected_registry") or []:
            if isinstance(_row, dict):
                if isinstance(_block, dict):
                    _row["sesoi"] = copy.deepcopy(_block)
                else:
                    _row.pop("sesoi", None)
    fr = new_design.setdefault("freeze", {})
    amd = {
        "date": date,
        "fields": [field_path],
        "reason": reason,
        "results_seen": results_seen,
        "user_signed": bool(user_signed),
        "approved_by": by or ("user" if user_signed else "light-design amend（自动留痕）"),
        "critical": critical,
        # DES-D02：类别分流落盘 + 变更前后值（增量评审包的对账基准）
        "category": category,
        "changes": [{
            "field": field_path,
            "before": None if before is _MISSING else copy.deepcopy(before),
            "after": copy.deepcopy(value),
        }],
        # DES-D02：增量评审状态——命门待审、非命门不触发
        "review": ({"status": "pending_review",
                    "track": "light" if category == "prewritten_branch"
                             else "full"}
                   if critical else {"status": "not_required"}),
        "new_hash": None,
    }
    if category == "prewritten_branch":
        amd["branch_ref"] = branch_ref
    fr.setdefault("amendments", []).append(amd)
    amd["new_hash"] = compute_content_hash(new_design)
    # 校验修订后仍合法（哈希链 + amendment 签核由 validate 覆盖）
    errs = validate_design(new_design)
    if errs:
        raise GateError([f"amendment 应用后设计书不合法：{e}" for e in errs])
    design.clear()
    design.update(new_design)
    design["updated"] = date
    return amd
