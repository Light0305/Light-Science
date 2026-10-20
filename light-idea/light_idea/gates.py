"""状态机与定版门（确定性校验器）。

状态只许由对应环节的产物驱动，不许口头推进（草案 §2.2）。`advance`
按目标状态逐项验门，任一项不过 → 抛出 GateError 并逐条列明缺什么，
不许静默放行。

主线：draft → screened → novelty_checked → pre_mortem_passed
      → finalized_executable / finalized_conceptual
旁路：killed / parked（可从任何非终态进入）

门规则一览（与 README / SKILL 同步维护）：
- screened        ：结构合法 + provenance 有出处 + 客观可行性两条为真且有据
                    + 去重已查且未被判重复（LEARNING §2 生成期机械门）
- novelty_checked ：查新结构化记录合法（检索范围声明非空、checked_at 落盘、
                    最接近工作均为带 paper_id/doi 的结构化引用）且 verdict
                    已给出且非 ABANDON（一期只验结构与占位合法，检索流程二期）
- pre_mortem_passed：pre-mortem 记录存在、清单逐项 pass/na（na 须附理由）、
                    未清项为空、最强反对意见已写、最小判别实验+判读标准已写死
- finalized_executable：执行级规格六项齐全 + pre-mortem 已过 + verdict 合法
                    （CAUTION 须附薄点说明）+ 跨模型判定收据合法（异家族）
                    + 最接近工作全部已核实（verified）+ 试点状态已显式登记
                    + 能力匹配齐备且无 blocking 缺口（v1.1 IDEA-D03；
                    概念级同样要求齐备，但 blocking 允许）
- finalized_conceptual：同上的查新/收据/核实门 + 卡面显式标概念级；
                    执行级规格允许未齐，但缺项会被记录进定版备注
- killed          ：kill 记录齐全——reason/source/失败二分类必填；
                    fundamental 须附 root_cause + boundary_conditions；
                    implementation 须附 retry_guidance；
                    source=novelty_named_paper 须点名论文（paper_id 或 doi）
                    （拍板 9.1-A：ABANDON 须点名在先论文的对偶面）
- parked          ：park 记录齐全——reason + revival_condition（复活条件）必填
"""

from __future__ import annotations

from .schema import (
    EXEC_SPEC_ITEMS,
    FAILURE_CLASSES,
    KILL_SOURCES,
    MAIN_STATES,
    PRE_MORTEM_ITEMS,
    VERDICTS,
    _nonempty_str,
    _ref_ok,
    capability_fit_errors,
    model_family,
    validate_card,
)

# 允许的主线跃迁：当前状态 → 可达的下一状态
NEXT = {
    "draft": ("screened",),
    "screened": ("novelty_checked",),
    "novelty_checked": ("pre_mortem_passed",),
    "pre_mortem_passed": ("finalized_executable", "finalized_conceptual"),
    "finalized_executable": (),
    "finalized_conceptual": (),
    "killed": (),
    "parked": ("draft",),  # 复活：回到 draft 重新走门（复活条件满足后人工触发）
}


class GateError(Exception):
    """门校验失败。errors 为逐条人读原因。"""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("；".join(errors))


def _exec_missing(card: dict) -> list[str]:
    """执行级规格六项缺项清单（返回缺失的项名）。"""
    spec = card.get("exec_spec") or {}
    missing = []
    for item in EXEC_SPEC_ITEMS:
        v = spec.get(item)
        if isinstance(v, list):
            ok = len(v) > 0 and all(
                (_nonempty_str(x) if isinstance(x, str) else isinstance(x, dict))
                for x in v
            )
            # 数据集/基线等结构化条目还须自带名称信息
            if ok and item == "datasets":
                ok = all(
                    isinstance(x, dict) and _nonempty_str(x.get("name")) for x in v
                )
            if ok and item == "metrics":
                ok = all(
                    isinstance(x, dict)
                    and _nonempty_str(x.get("name"))
                    and _nonempty_str(x.get("convention_source"))
                    for x in v
                )
        elif isinstance(v, dict):
            ok = bool(v)
        else:
            ok = _nonempty_str(v) if isinstance(v, str) else bool(v)
        if not ok:
            missing.append(item)
    # 最强基线须点名工作（带 ref 或明确名称），不许写「与 SOTA 比较」
    base = spec.get("strongest_baseline")
    if "strongest_baseline" not in missing:
        if isinstance(base, dict):
            if not (_nonempty_str(base.get("name")) or _ref_ok(base)):
                missing.append("strongest_baseline（须点名：name 或 paper_id/doi）")
        elif _nonempty_str(base) and base.strip().lower() in ("sota", "与sota比较", "与 sota 比较"):
            missing.append("strongest_baseline（不许写「与 SOTA 比较」，须点名工作）")
    return missing


def _receipt_errors(card: dict) -> list[str]:
    """跨模型判定收据校验（约束 1 + 拍板 9.4-B 硬门）。

    收据须含 verdict_id、判定模型、执行者模型；判定与执行须不同模型
    家族（优先比显式 judge_family/executor_family，缺失时由模型名推断）。
    review_status=REVIEW_UNAVAILABLE 时不定版（拍板 9.4-B 降级通道）。
    """
    nov = card.get("novelty") or {}
    errs = []
    if nov.get("review_status") == "REVIEW_UNAVAILABLE":
        errs.append("跨模型判定不可用（REVIEW_UNAVAILABLE）：硬门未过，不许定版，恢复后补判定")
        return errs
    r = nov.get("receipt") or {}
    if not _nonempty_str(r.get("verdict_id")):
        errs.append("查新收据缺 verdict_id")
    if not _nonempty_str(r.get("judge_model")):
        errs.append("查新收据缺 judge_model（判定模型）")
    if not _nonempty_str(r.get("executor_model")):
        errs.append("查新收据缺 executor_model（执行者/生成者模型）")
    jf = _nonempty_str(r.get("judge_family")) and r["judge_family"].strip().lower()
    ef = _nonempty_str(r.get("executor_family")) and r["executor_family"].strip().lower()
    judge_family = jf or model_family(r.get("judge_model") or "")
    exec_family = ef or model_family(r.get("executor_model") or "")
    if judge_family and exec_family and judge_family == exec_family:
        errs.append(
            f"判定与执行同属一个模型家族（{judge_family}）：自评收据无效，须跨模型判定"
        )
    return errs


def _verdict_errors(card: dict) -> list[str]:
    nov = card.get("novelty") or {}
    errs = []
    v = nov.get("verdict")
    if v not in VERDICTS:
        errs.append("novelty.verdict 未给出（须为 PROCEED / PROCEED_WITH_CAUTION / ABANDON）")
    elif v == "ABANDON":
        errs.append("verdict=ABANDON 的想法不许定版：应走 killed（且须点名在先论文）")
    elif v == "PROCEED_WITH_CAUTION" and not _nonempty_str(nov.get("caution_reason")):
        errs.append("verdict=PROCEED_WITH_CAUTION 须附 caution_reason（delta 薄在哪，须说清）")
    return errs


def _gate_screened(card: dict) -> list[str]:
    errs = []
    feas = card.get("feasibility") or {}
    if feas.get("compute_within_budget") is not True:
        errs.append("可行性门：compute_within_budget 未确认为真（算力预算超限不许入围）")
    elif not _nonempty_str(feas.get("compute_note")):
        errs.append("可行性门：compute_note 为空（判断须有据）")
    if feas.get("data_obtainable") is not True:
        errs.append("可行性门：data_obtainable 未确认为真（数据集可证不可得不许入围）")
    elif not _nonempty_str(feas.get("data_note")):
        errs.append("可行性门：data_note 为空（判断须有据）")
    dedup = card.get("dedup") or {}
    if dedup.get("checked") is not True:
        errs.append("去重门：尚未跑 dedup（生成后必走去重工序，约束 5）")
    elif dedup.get("adjudication") == "duplicate":
        errs.append("去重门：该卡已被人工裁定为重复，不许推进（应 killed 或留档）")
    return errs


def _gate_novelty_checked(card: dict) -> list[str]:
    """一期口径：只验查新记录的结构与占位合法，检索/判定流程二期实现。"""
    nov = card.get("novelty") or {}
    errs = []
    if not _nonempty_str(nov.get("checked_at")):
        errs.append("查新门：novelty.checked_at 未落盘")
    scope = nov.get("search_scope") or {}
    if not (isinstance(scope.get("sources"), list) and scope["sources"]):
        errs.append("查新门：search_scope.sources 为空（检索范围声明必填，防乐观偏差）")
    works = nov.get("closest_works")
    if not isinstance(works, list):
        errs.append("查新门：closest_works 必须是列表（可为空列表，但须显式在场）")
    v = nov.get("verdict")
    if v == "ABANDON":
        errs.append("查新门：verdict=ABANDON 不许进入 novelty_checked，应走 killed 并点名论文")
    return errs


def _gate_pre_mortem(card: dict) -> list[str]:
    errs = []
    pm = card.get("pre_mortem")
    if not isinstance(pm, dict):
        return ["pre-mortem 门：pre_mortem 记录不存在（执行预演未做）"]
    if not _nonempty_str(pm.get("date")):
        errs.append("pre-mortem 门：pre_mortem.date 未落盘")
    checklist = pm.get("checklist") or {}
    for item in PRE_MORTEM_ITEMS:
        entry = checklist.get(item)
        if not isinstance(entry, dict) or entry.get("status") not in ("pass", "na"):
            errs.append(f"pre-mortem 门：清单项 {item} 未清（status 须为 pass 或 na）")
        elif entry.get("status") == "na" and not _nonempty_str(entry.get("note")):
            errs.append(f"pre-mortem 门：清单项 {item} 标 na 须附理由")
    open_items = pm.get("open_items")
    if not isinstance(open_items, list) or open_items:
        errs.append("pre-mortem 门：open_items 未清空（清单不清空不许定版）")
    neg = card.get("negative") or {}
    if not _nonempty_str(neg.get("strongest_objection")):
        errs.append("pre-mortem 门：negative.strongest_objection 为空（最强反对意见必填）")
    exp = (card.get("exec_spec") or {}).get("discriminating_experiment")
    if not isinstance(exp, dict):
        errs.append("pre-mortem 门：最小判别实验未写（exec_spec.discriminating_experiment）")
    else:
        for k in ("description", "readout_positive", "readout_negative", "readout_null"):
            if not _nonempty_str(exp.get(k)):
                errs.append(f"pre-mortem 门：判别实验缺 {k}（判读标准须预先写死）")
    return errs


def _gate_finalized_common(card: dict) -> list[str]:
    errs = []
    errs += _verdict_errors(card)
    errs += _receipt_errors(card)
    # 最接近工作全部已核实（未核实不许进成稿/定版层）
    for i, w in enumerate((card.get("novelty") or {}).get("closest_works") or []):
        if isinstance(w, dict) and w.get("verified") is not True:
            errs.append(
                f"定版门：closest_works[{i}] 未过 Literature 核实口径（verified 须为 true）"
            )
    pilot = card.get("pilot") or {}
    if pilot.get("status") not in ("not_run", "verified", "negative"):
        errs.append("定版门：pilot.status 未显式登记（not_run / verified / negative）")
    elif pilot.get("status") == "negative":
        errs.append("定版门：试点为负信号的想法不许定版（应 killed，source=pilot_negative）")
    return errs


def _gate_finalized_executable(card: dict) -> list[str]:
    errs = _gate_finalized_common(card)
    missing = _exec_missing(card)
    if missing:
        errs.append("定版门（可执行）：执行级规格缺项：" + "、".join(missing))
    # 能力匹配（IDEA-D03）：子区齐备 + 覆盖完整 + 无 blocking 缺口
    errs += capability_fit_errors(card, for_executable=True)
    return errs


def _gate_finalized_conceptual(card: dict) -> list[str]:
    errs = _gate_finalized_common(card)
    # 能力匹配（IDEA-D03）：子区须齐备，blocking 缺口允许（概念定版
    # 的题中之义），但不许以「未评估」冒充概念级
    errs += capability_fit_errors(card, for_executable=False)
    if card.get("finalization_level") != "conceptual":
        errs.append(
            "定版门（概念）：须先在卡上显式标注 finalization_level=conceptual"
            "（概念定版不许冒充可执行定版）"
        )
    return errs


def _gate_killed(card: dict) -> list[str]:
    kill = card.get("kill")
    if not isinstance(kill, dict):
        return ["killed 门：kill 记录不存在（杀想法必须留痕）"]
    errs = []
    if not _nonempty_str(kill.get("reason")):
        errs.append("killed 门：kill.reason 为空")
    if not _nonempty_str(kill.get("date")):
        errs.append("killed 门：kill.date 未落盘")
    if kill.get("source") not in KILL_SOURCES:
        errs.append(f"killed 门：kill.source 非法（须为 {KILL_SOURCES} 之一）")
    fc = kill.get("failure_class")
    if fc not in FAILURE_CLASSES:
        errs.append(
            f"killed 门：failure_class 必填且须二分类 {FAILURE_CLASSES}（约束 8）"
        )
    elif fc == "fundamental":
        if not _nonempty_str(kill.get("root_cause")):
            errs.append("killed 门：fundamental 失败须附 root_cause")
        if not _nonempty_str(kill.get("boundary_conditions")):
            errs.append("killed 门：fundamental 失败须附 boundary_conditions（什么条件下可能变得可行）")
    elif fc == "implementation":
        if not _nonempty_str(kill.get("retry_guidance")):
            errs.append("killed 门：implementation 失败须附 retry_guidance（可重试指引）")
    if kill.get("source") == "novelty_named_paper":
        named = kill.get("named_paper")
        if not _ref_ok(named):
            errs.append("killed 门：因查新被杀须点名在先论文（named_paper 带 paper_id 或 doi）")
    return errs


def _gate_parked(card: dict) -> list[str]:
    park = card.get("park")
    if not isinstance(park, dict):
        return ["parked 门：park 记录不存在"]
    errs = []
    if not _nonempty_str(park.get("reason")):
        errs.append("parked 门：park.reason 为空")
    if not _nonempty_str(park.get("revival_condition")):
        errs.append("parked 门：park.revival_condition 为空（搁置必须写明复活条件）")
    return errs


_GATES = {
    "screened": _gate_screened,
    "novelty_checked": _gate_novelty_checked,
    "pre_mortem_passed": _gate_pre_mortem,
    "finalized_executable": _gate_finalized_executable,
    "finalized_conceptual": _gate_finalized_conceptual,
    "killed": _gate_killed,
    "parked": _gate_parked,
}


def check_transition(card: dict, target: str) -> list[str]:
    """返回从当前状态到 target 的全部违规条目（空列表 = 可推进）。"""
    errs: list[str] = []
    current = card.get("status")
    if target not in _GATES and target != "draft":
        errs.append(f"目标状态非法：{target!r}")
        return errs
    # 跃迁合法性
    if target in ("killed", "parked"):
        if current in ("killed", "finalized_executable", "finalized_conceptual"):
            errs.append(f"当前状态 {current} 不许再转入 {target}")
    elif target == "draft":
        if current != "parked":
            errs.append("只有 parked 可以复活回 draft，其余状态不许回退")
    else:
        allowed = NEXT.get(current, ())
        if target not in allowed:
            errs.append(
                f"不许跳级/逆行：{current} → {target}（主线须逐级推进，"
                f"当前可达：{allowed or '无'}）"
            )
    if errs:
        return errs
    # 结构合法是一切门的前提（复活回 draft 除外，只查旁路记录本身）
    if target != "draft":
        errs += [f"结构校验：{e}" for e in validate_card(card)]
    gate = _GATES.get(target)
    if gate:
        errs += gate(card)
    return errs


def advance(card: dict, target: str, *, by: str, date: str, note: str = "") -> dict:
    """校验并推进状态（就地修改并返回 card）。失败抛 GateError。"""
    errors = check_transition(card, target)
    if errors:
        raise GateError(errors)
    old = card.get("status")
    card["status"] = target
    card["updated"] = date
    if target == "finalized_conceptual":
        card["finalization_level"] = "conceptual"
    if target == "finalized_executable":
        card["finalization_level"] = "executable"
    card.setdefault("status_history", []).append(
        {"from": old, "to": target, "date": date, "by": by, "note": note}
    )
    return card
