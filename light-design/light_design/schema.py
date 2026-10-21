"""设计书 schema：十一区字段定义、确定性校验器与冻结哈希。

设计依据：03-design/REDESIGN-DRAFT.md §2.1（字段草案）+ LEARNING.md
十三条硬约束 + 2026-10-20 用户拍板 7 项（文末记录）。

校验器写死的硬规则（拍板 ④双层中的机械层）：
- 主张 ≤2 条 + anti_claims 非空（约束 1：主张先行、反主张必备）；
- status_quo 一等对照必须存在（约束 4 / Ax status quo 机制）；
- 每条消融 what_it_tests + expected_if_component_matters 必填（约束 1/D2）；
- 对照先行：处理组 run 必须把其对照 run 列入 depends_on，且依赖图无环
  （约束 3 + 拍板 ⑥）；
- 重复层级 replication_level 必须声明（约束 8：n 按独立随机化层级计）；
- 判读标准三向齐全（约束 2/10：positive / negative / null）；
- 调参对等条款 tuning_parity 必须声明（约束 7）；
- 效度四类齐全、逐项三态（na / mitigated / residual），整类缺失 = 不完整
  （约束 6）；
- 功效核算（完整级强制，拍板 ②）：SESOI + 敏感性范围 + 种子/重复推导；
  核算不足（sufficient=false）时不许保留确认性主张（给不起就下调声称）；
- 结果可见性为 results_seen（第 5 档）时不许有确认性主张（约束 2）；
- 极简级（minimal）底线六件缺一不可，且不许承载确认性主结论（拍板 ③）；
- frozen 后正文防回改：正文内容哈希须与冻结哈希（或最后一条 amendment
  的 new_hash）一致（约束 12）；已登记的命门字段 amendment 必须带
  user_signed=true（拍板 ⑤）；
- aux 辅助区与判定物理分离：分数/判定字段不许混入（约束 13）；
- SESOI 结构化登记（v1.1 DES-D01，清偿回流 RX-A001）：evaluation.sesoi
  为全设计单一事实源（数值/单位/方向/边界/推导依据/目标量引用/汇总
  度量七字段）；确认性主张的设计必须登记；登记行（handoff 与 export
  的 expected_registry）只许携带与登记块逐字段一致的派生副本，不许
  单独填；evaluation.sesoi 列入命门字段，冻结后变更走 amendment +
  用户签，登记行副本在同一 amendment 内机械刷新。
- 功效真计算落格（v1.2，验收规格 03-design/power-module-acceptance.md）：
  分组经典设计（双臂/配对/ANOVA）的样本量只认 light_design.power 的
  精确解（非中心 t/F），落 resources.power.design_size 原生落格；
  校验器对落格做实际功效拦截（achieved < target 报错）与复算拦截
  （登记 achieved 与求解器按登记参数复算差 > 1e-6 报错），z 近似
  route 直接拒；分组设计借 derived.repetitions 落位由 power_warnings
  点名警告（兼容读取、不沉默）。
- intake 跨区实体核查（v1.1 DES-D04）：spec_intake 中标 expanded 的
  六项逐项按 INTAKE_ENTITY_MAP 到对应区查实体存在性——只改状态字、
  不落实体的承接造假，校验器点名报错；accepted 不触发本核查。
- amendment 类别与评审状态（v1.1 DES-D02）：每条 amendment 声明
  category（prewritten_branch / unforeseen，C-补04 分流）；命门
  amendment 带 review 子记录（pending_review 待增量评审落盘，
  export 据此拦截，见 export.py / review.py）。
"""

from __future__ import annotations

import copy
import hashlib
import json
import math

from .power import (
    EXACT_ROUTES as POWER_EXACT_ROUTES,
    power_anova as _solver_power_anova,
    power_paired_t as _solver_power_paired,
    power_two_sample_t as _solver_power_two,
)

# ---------- 枚举 ----------

TIERS = ("full", "minimal")

MAIN_STATES = ("draft", "reviewed", "frozen")
BYPASS_STATES = ("returned", "blocked")
ALL_STATES = MAIN_STATES + BYPASS_STATES

# 结果可见性五档（OSF Existing data 的计算实验转译，约束 2）
VISIBILITY_LEVELS = (
    "no_runs_yet",        # 尚无任何运行
    "pilot_run_unseen",   # 判别实验已跑但结果未看
    "pilot_seen",         # 判别实验结果已看、主实验未跑
    "main_partial_seen",  # 主实验部分结果已看
    "results_seen",       # 结果已看过 — 只许探索性，不许确认性定版
)

DESIGN_TYPES = ("基准复现型", "对照实验型", "消融型", "序贯调优型", "观察分析型")

VARIABLE_GROUPS = ("treatment", "outcome", "covariate")  # 处理 / 结局 / 协变量
DOMAIN_KINDS = ("range", "choice", "fixed")

RUN_ROLES = ("control", "treatment", "ablation", "sanity", "other")

THREAT_CATEGORIES = ("conclusion", "internal", "construct", "external")
THREAT_STATUSES = ("na", "mitigated", "residual")

# Idea 交接 exec_spec 六项（Design 的下限输入，缺项打回、不许临场发明）
INTAKE_ITEMS = (
    "datasets",
    "strongest_baseline",
    "metrics",
    "ablations",
    "resource_budget",
    "key_details",
)
INTAKE_STATUSES = ("accepted", "expanded", "returned", "pending")
INTAKE_LOCATIONS = {
    "datasets": "evaluation.data_protocol / plan.variables",
    "strongest_baseline": "contract.controls（status_quo）",
    "metrics": "evaluation.primary_metric / guardrail_metrics",
    "ablations": "contract.ablations",
    "resource_budget": "resources.budget / power",
    "key_details": "plan / handoff.repro_fields",
}

# intake 跨区实体映射（v1.1 DES-D04，在此成文冻结）：status=expanded 的
# 承接项必须在对应区查得到展开后的实体；查无实体 = 只改状态字的承接
# 造假，validate 报错点名。key 为承接项，值为 (落点描述, 判定函数名)。
INTAKE_ENTITY_MAP = {
    "datasets": ("evaluation.data_protocol / plan.variables",
                 "_entity_datasets"),
    "strongest_baseline": ("contract.controls（status_quo 一等对照）",
                           "_entity_strongest_baseline"),
    "metrics": ("evaluation.primary_metric", "_entity_metrics"),
    "ablations": ("contract.ablations", "_entity_ablations"),
    "resource_budget": ("resources.budget / resources.power",
                        "_entity_resource_budget"),
    "key_details": ("plan.intervention_mechanism / "
                    "plan.intervention_checkpoints / handoff.repro_fields",
                    "_entity_key_details"),
}


def _entity_datasets(design: dict) -> bool:
    ev = design.get("evaluation") or {}
    if _present(ev.get("data_protocol")):
        return True
    plan = design.get("plan") or {}
    return isinstance(plan.get("variables"), list) and bool(plan["variables"])


def _entity_strongest_baseline(design: dict) -> bool:
    controls = (design.get("contract") or {}).get("controls") or []
    return any(isinstance(c, dict) and c.get("status_quo") for c in controls)


def _entity_metrics(design: dict) -> bool:
    pm = (design.get("evaluation") or {}).get("primary_metric")
    return isinstance(pm, dict) and _nonempty_str(pm.get("name"))


def _entity_ablations(design: dict) -> bool:
    abl = (design.get("contract") or {}).get("ablations")
    return isinstance(abl, list) and bool(abl)


def _entity_resource_budget(design: dict) -> bool:
    res = design.get("resources") or {}
    budget = res.get("budget")
    if isinstance(budget, dict) and any(_present(v) for v in budget.values()):
        return True
    return isinstance(res.get("power"), dict) and bool(res["power"])


def _entity_key_details(design: dict) -> bool:
    plan = design.get("plan") or {}
    if isinstance(plan.get("intervention_mechanism"), list) \
            and plan["intervention_mechanism"]:
        return True
    if isinstance(plan.get("intervention_checkpoints"), list) \
            and plan["intervention_checkpoints"]:
        return True
    ho = design.get("handoff") or {}
    return _present(ho.get("repro_fields"))


_INTAKE_ENTITY_CHECKS = {
    "datasets": _entity_datasets,
    "strongest_baseline": _entity_strongest_baseline,
    "metrics": _entity_metrics,
    "ablations": _entity_ablations,
    "resource_budget": _entity_resource_budget,
    "key_details": _entity_key_details,
}


def intake_expanded_entity_errors(design: dict) -> list[str]:
    """DES-D04 跨区实体核查：spec_intake 中 status=expanded 的项逐项
    按 INTAKE_ENTITY_MAP 查对应区实体；查无实体逐项点名返回。
    accepted / returned / pending 不触发本核查。"""
    errs: list[str] = []
    intake = design.get("intake") or {}
    for s in intake.get("spec_intake") or []:
        if not isinstance(s, dict) or s.get("status") != "expanded":
            continue
        item = s.get("item")
        check = _INTAKE_ENTITY_CHECKS.get(item)
        if check is None:
            continue
        if not check(design):
            where = INTAKE_ENTITY_MAP[item][0]
            errs.append(
                f"intake 承接 {item} 标 expanded 但在落点（{where}）查无"
                "展开后的实体（DES-D04 跨区实体核查：只改状态字样、"
                "不落实体不算展开承接，须把实体写进对应区或改回承接状态）")
    return errs


# amendment 类别（v1.1 DES-D02，C-补04 分流：定版预写偏离分支轻评审，
# 未预见变更全评审；未声明默认 unforeseen，取最严口径）
AMD_CATEGORIES = ("prewritten_branch", "unforeseen")

# amendment 字段依赖映射（v1.1 DES-D02，在此成文冻结）：增量评审的
# 影响面按此表生成——(字段前缀, 受影响 Stage 1 条目, 登记行范围,
# 主张范围)。登记行范围 all = handoff.expected_registry 全部行；
# 主张范围 all = 全部主主张，named = 字段路径点名的主张。未命中任何
# 前缀的字段回退为全量五条 + 登记行全行（保守口径）。
FIELD_DEPENDENCY_MAP = (
    ("evaluation.sesoi", ("methodological_soundness",
                          "analysis_predetermined"), "all", "named"),
    ("evaluation.readout", ("analysis_predetermined",), "all", "none"),
    ("evaluation.primary_metric", ("methodological_soundness",
                                   "analysis_predetermined"), "all", "none"),
    ("evaluation", ("methodological_soundness",
                    "analysis_predetermined"), "all", "none"),
    ("claims", ("question_quality", "theoretical_basis"), "all", "named"),
    ("contract.runs", ("methodological_soundness",
                        "competing_explanations"), "all", "none"),
    ("contract", ("competing_explanations",
                  "methodological_soundness"), "none", "none"),
    ("plan.variables", ("methodological_soundness",
                        "analysis_predetermined"), "none", "none"),
    ("plan", ("methodological_soundness",), "none", "none"),
    ("validity", ("competing_explanations",), "none", "none"),
    ("resources.circuit_breakers", ("methodological_soundness",),
     "none", "none"),
    ("resources", ("methodological_soundness",), "none", "none"),
    ("registration", ("analysis_predetermined",), "none", "none"),
    ("handoff", ("analysis_predetermined",), "none", "none"),
)


def amendment_impact_areas(field_path: str) -> dict:
    """按 FIELD_DEPENDENCY_MAP 给字段路径算增量评审影响面。
    返回 {stage1_items: [...], registry_scope, claims_scope}。"""
    p = (field_path or "").strip()
    for prefix, items, reg_scope, claim_scope in FIELD_DEPENDENCY_MAP:
        if p == prefix or p.startswith(prefix + ".") \
                or p.startswith(prefix + "["):
            return {"stage1_items": list(items),
                    "registry_scope": reg_scope,
                    "claims_scope": claim_scope}
    return {"stage1_items": list(STAGE1_ITEMS),
            "registry_scope": "all", "claims_scope": "all"}

# Stage 1 式定版评审五条（Chambers 2013 / Nosek 转述，LEARNING §7）
STAGE1_ITEMS = (
    "question_quality",          # 问题/假设的质量与重要性
    "theoretical_basis",         # 假设的逻辑与理论依据
    "methodological_soundness",  # 方法学健全可行且能回答问题（含功效）
    "analysis_predetermined",    # 分析管线详细到看数据前已确定解释
    "competing_explanations",    # 设计能区分竞争性解释（强推断）
)
REVIEW_STATUSES = ("ok", "REVIEW_UNAVAILABLE")
REVIEW_DECISIONS = ("pass", "reject")

# 命门字段（拍板 ⑤）：这些字段的 amendment 必须用户签
CRITICAL_FIELD_PREFIXES = (
    "evaluation.readout",            # 判读标准
    "evaluation.primary_metric",     # 主指标
    "evaluation.sesoi",              # SESOI 登记块（v1.1 DES-D01：判定标准的一部分）
    "claims",                        # 主张
    "resources.circuit_breakers",    # 停止规则/熔断线
)

# SESOI 结构化登记块（v1.1 DES-D01）：evaluation.sesoi 七字段
SESOI_DIRECTIONS = ("higher", "lower")
SESOI_FIELDS = ("value", "unit", "direction", "bounds", "basis",
                "estimand_ref", "summary_measure")
SESOI_TEXT_FIELDS = ("unit", "bounds", "basis", "estimand_ref",
                     "summary_measure")

# aux 区只许这些键（参考信号，一律标「暂定」；判定字段不许混入）
AUX_KEYS = (
    "info_gain_estimates",    # 候选运行信息增益粗估（排序参考）
    "run_priority_notes",     # 排序备注
    "similar_design_refs",    # 相似设计指针
    "history_refs",           # 历史成败指针
)
AUX_FORBIDDEN_KEYS = ("verdict", "decision", "review_decision", "score_gate", "gate")

DESIGN_SECTIONS = (
    "design_id", "idea_id", "title", "tier", "status", "created", "updated",
    "registration", "intake", "claims", "plan", "contract", "evaluation",
    "validity", "resources", "freeze", "handoff", "aux",
    "status_history", "return_record", "block_record",
)


# ---------- 小工具 ----------

def _nonempty_str(v) -> bool:
    return isinstance(v, str) and bool(v.strip())


def _present(v) -> bool:
    """交接项是否「有值」：非空列表/字典/字符串/数字。"""
    if isinstance(v, (list, dict, str)):
        return len(v) > 0 if not isinstance(v, str) else bool(v.strip())
    return v is not None


def is_critical_field(path: str) -> bool:
    """字段路径是否命中命门（拍板 ⑤）。"""
    p = (path or "").strip()
    return any(p == c or p.startswith(c + ".") or p.startswith(c + "[")
               for c in CRITICAL_FIELD_PREFIXES)


# ---------- SESOI 结构化登记块（DES-D01） ----------

def validate_sesoi_block(block, where: str = "evaluation.sesoi") -> list[str]:
    """校验一个 SESOI 登记块的完整性。返回错误列表（空 = 完整）。

    七字段缺一不可：value 须为正数；direction 须在 (higher, lower)；
    basis（推导依据引用）为空直接拒——无依据的 SESOI 不许登记；
    estimand_ref / summary_measure 为 C-补06 要求（SESOI 与估计目标
    绑定，不许裸数字）。"""
    errs: list[str] = []
    if not isinstance(block, dict):
        return [f"{where} 不是映射（结构化 SESOI 登记块须为映射）"]
    v = block.get("value")
    if isinstance(v, bool) or not isinstance(v, (int, float)) or float(v) <= 0:
        errs.append(f"{where}.value 非法：{v!r}（SESOI 数值须为正数）")
    for k in SESOI_TEXT_FIELDS:
        if not _nonempty_str(block.get(k)):
            if k == "basis":
                errs.append(f"{where}.basis 为空（推导依据引用必填："
                            "文献 / 领域惯例 / 上游判读阈值指针，"
                            "无依据的 SESOI 不许登记）")
            elif k == "estimand_ref":
                errs.append(f"{where}.estimand_ref 为空（目标量引用必填："
                            "SESOI 须绑定其估计目标，不许裸数字）")
            elif k == "summary_measure":
                errs.append(f"{where}.summary_measure 为空"
                            "（汇总度量类型必填，如 mean_diff）")
            else:
                errs.append(f"{where}.{k} 为空")
    d = block.get("direction")
    if d not in SESOI_DIRECTIONS:
        errs.append(f"{where}.direction 非法：{d!r}"
                    f"（须为 {SESOI_DIRECTIONS} 之一）")
    return errs


def sesoi_canonical(block) -> dict | None:
    """登记块规范形（只取七字段，value 归一为 float）；非映射返回 None。"""
    if not isinstance(block, dict):
        return None
    out: dict = {}
    for k in SESOI_FIELDS:
        v = block.get(k)
        if k == "value" and isinstance(v, (int, float)) \
                and not isinstance(v, bool):
            v = float(v)
        out[k] = v
    return out


def sesoi_diff_fields(a, b) -> list[str]:
    """两块规范形逐字段比对，返回不一致的字段名列表。"""
    ca, cb = sesoi_canonical(a), sesoi_canonical(b)
    if ca is None or cb is None:
        return ["<登记块不是映射>"]
    return [k for k in SESOI_FIELDS if ca.get(k) != cb.get(k)]


# ---------- 功效 design_size 原生落格校验（v1.2 真计算模块） ----------

# 分组经典设计的原生落格 resources.power.design_size（验收规格 §3）：
# {form, route, alpha, target_power, sesoi_value, sigma|sigma_diff|
# cohen_f, raw_n, per_group_n, groups, total_n, achieved_power,
# z_reference?, sim_check?}。旧 derived.repetitions 借位写法保留兼容
# 读取，但分组设计借位由 power_warnings 点名警告，不再沉默。
POWER_FORMS = ("two_arm", "paired", "anova")


def _is_num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _is_pos_int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool) and v >= 1


def _power_design_size_errors(power: dict) -> list[str]:
    """校验 resources.power 的求解器落格（design_size / sensitivity_table）。

    硬规则（03-design/power-module-acceptance.md §2/§3）：
    - 最终 n 只认精确解路线（nct_exact / ncf_exact）；route 为 z 近似
      直接报错——z 数不许充当达成功效的样本量；
    - 取整 n 的实际功效 achieved_power 必须落字且 ≥ target_power，
      未达标报错（不许 sufficient=true 静默通过）；
    - 登记的 achieved_power 由校验器按登记参数（形态/SESOI/σ 或 f/
      每组 n）当场复算，比对容差 1e-6——落字数字与求解器不一致即
      报错（防手填造假）；结构化敏感性表逐行同规。
    无 design_size 且未声明 caliber=grouped 的旧设计书不触发本校验
    （兼容读），借位写法走 power_warnings。"""
    errs: list[str] = []
    where = "resources.power.design_size"
    ds = power.get("design_size")
    if power.get("caliber") == "grouped" and ds is None:
        errs.append("resources.power.caliber=grouped（分组经典设计）但缺 "
                    "design_size 原生落格（每组 n / 总 N / 设计形态须落 "
                    "design_size，不许再借 derived.repetitions 解释性落位，"
                    "验收规格 §3）")
    if ds is not None:
        if not isinstance(ds, dict):
            errs.append(f"{where} 不是映射（求解器落格须为映射）")
            ds = None
    if isinstance(ds, dict):
        form = ds.get("form")
        if form not in POWER_FORMS:
            errs.append(f"{where}.form 非法：{form!r}（须为 {POWER_FORMS} 之一）")
        route = ds.get("route")
        if route not in POWER_EXACT_ROUTES:
            if isinstance(route, str) and route.startswith("z"):
                errs.append(f"{where}.route={route!r}：z 近似路线只许作"
                            "合理性速查（z_reference），不许作最终产出"
                            "（验收规格 §2：最终 n 只认精确解 "
                            "nct_exact / ncf_exact）")
            else:
                errs.append(f"{where}.route 非法：{route!r}（须为精确解路线 "
                            f"{POWER_EXACT_ROUTES} 之一）")
        groups, per, total = ds.get("groups"), ds.get("per_group_n"), \
            ds.get("total_n")
        for k, v in (("groups", groups), ("per_group_n", per),
                     ("total_n", total)):
            if not _is_pos_int(v):
                errs.append(f"{where}.{k} 非法：{v!r}（须为正整数）")
        if _is_pos_int(groups) and _is_pos_int(per) and _is_pos_int(total) \
                and total != per * groups:
            errs.append(f"{where}.total_n={total} 与 per_group_n×groups="
                        f"{per}×{groups}={per * groups} 不一致")
        if form == "two_arm" and _is_pos_int(groups) and groups != 2:
            errs.append(f"{where}.groups={groups}（two_arm 形态须为 2）")
        if form == "paired" and _is_pos_int(groups) and groups != 1:
            errs.append(f"{where}.groups={groups}（paired 形态以对为单位，"
                        "groups 须为 1、per_group_n 即对数）")
        if form == "anova" and _is_pos_int(groups) and groups < 2:
            errs.append(f"{where}.groups={groups}（anova 形态须 ≥ 2）")
        tp = ds.get("target_power", power.get("target_power"))
        if _is_num(ds.get("target_power")) and _is_num(power.get("target_power")) \
                and float(ds["target_power"]) != float(power["target_power"]):
            errs.append(f"{where}.target_power={ds['target_power']} 与 "
                        f"resources.power.target_power={power['target_power']} "
                        "不一致（目标功效只许一处口径）")
        ach = ds.get("achieved_power")
        if not _is_num(ach):
            errs.append(f"{where}.achieved_power 缺失或非数值（取整 n 的"
                        "实际功效必须落字，验收规格 §2）")
        elif _is_num(tp) and float(ach) < float(tp) - 1e-9:
            errs.append(f"{where}.achieved_power={ach} < target_power={tp}："
                        "取整 n 的实际功效未达目标——不许 sufficient=true "
                        "静默通过（验收规格 §2）：按精确解增大 n，或下调"
                        "声称/目标并落字")
        raw = ds.get("raw_n")
        if _is_num(raw) and _is_pos_int(per):
            raw_per = float(raw) / groups if form == "anova" \
                and _is_pos_int(groups) else float(raw)
            if not (per - 1 < raw_per <= per + 1e-9):
                errs.append(f"{where}.raw_n={raw} 与 per_group_n={per} 的"
                            "取整关系不符（per_group_n 须为精确解原值的"
                            "向上取整）")
        # 复算拦截：按登记参数当场重算实际功效，与落字比对
        if _is_num(ach) and _is_pos_int(per):
            recomputed = None
            try:
                if form == "two_arm" and _is_num(ds.get("sigma")) \
                        and _is_num(ds.get("sesoi_value")):
                    recomputed = _solver_power_two(
                        per, float(ds["sesoi_value"]) / float(ds["sigma"]),
                        float(ds.get("alpha", power.get("alpha") or 0.05)))
                elif form == "paired" and _is_num(ds.get("sigma_diff")) \
                        and _is_num(ds.get("sesoi_value")):
                    recomputed = _solver_power_paired(
                        per, float(ds["sesoi_value"]) / float(ds["sigma_diff"]),
                        float(ds.get("alpha", power.get("alpha") or 0.05)))
                elif form == "anova" and _is_num(ds.get("cohen_f")) \
                        and _is_pos_int(groups) and _is_pos_int(total):
                    recomputed = _solver_power_anova(
                        total, groups, float(ds["cohen_f"]),
                        float(ds.get("alpha", power.get("alpha") or 0.05)))
            except ValueError:
                recomputed = None
            if recomputed is not None:
                if abs(recomputed - float(ach)) > 1e-6:
                    errs.append(f"{where}.achieved_power 登记值 {ach} 与"
                                f"求解器按登记参数复算 {recomputed:.6f} "
                                "不一致（容差 1e-6）：功效数字只许由求解器"
                                "产出，不许手填")
                elif _is_num(tp) and recomputed < float(tp) - 1e-9:
                    errs.append(f"{where} 求解器复算实际功效 "
                                f"{recomputed:.6f} < target_power={tp}："
                                "取整 n 未达目标（验收规格 §2 拦截）")
        sim = ds.get("sim_check")
        if sim is not None:
            if not isinstance(sim, dict) or not _is_num(sim.get("estimate")) \
                    or not _is_num(sim.get("mc_se")):
                errs.append(f"{where}.sim_check 结构非法（模拟交叉验证落格"
                            "须含 estimate 与 mc_se 数值；模拟只作交叉"
                            "验证，不作产出口径）")
    rows = power.get("sensitivity_table")
    if rows is not None:
        if not isinstance(rows, list):
            errs.append("resources.power.sensitivity_table 不是列表")
        else:
            tp2 = power.get("target_power")
            form2 = ds.get("form") if isinstance(ds, dict) else None
            for i, row in enumerate(rows):
                if not isinstance(row, dict):
                    errs.append(f"resources.power.sensitivity_table[{i}] 不是映射")
                    continue
                rach = row.get("achieved_power")
                if not _is_num(rach):
                    errs.append(f"resources.power.sensitivity_table[{i}]"
                                ".achieved_power 缺失或非数值（敏感性表逐点"
                                "须给实际功效，验收规格 §1.4）")
                elif _is_num(tp2) and float(rach) < float(tp2) - 1e-9:
                    errs.append(f"resources.power.sensitivity_table[{i}]"
                                f".achieved_power={rach} < target_power={tp2}"
                                "（敏感性表逐点实际功效须达标）")
                rraw, rper = row.get("raw_n"), row.get("per_group_n")
                if form2 in ("two_arm", "paired") and _is_num(rraw) \
                        and _is_pos_int(rper) \
                        and math.ceil(float(rraw) - 1e-9) != rper:
                    errs.append(f"resources.power.sensitivity_table[{i}]"
                                f".per_group_n={rper} 不是 raw_n={rraw} 的"
                                "向上取整")
    return errs


def power_warnings(design: dict) -> list[str]:
    """功效落位警告（不拦截，只点名）：分组设计借 derived.repetitions
    落每组 n 的旧写法（验收规格 §3：兼容读取但给警告而非沉默）。"""
    warns: list[str] = []
    res = design.get("resources") or {}
    power = res.get("power")
    if not isinstance(power, dict) or not power:
        return warns
    if power.get("design_size") is not None:
        return warns
    groups = (design.get("contract") or {}).get("groups")
    derived = power.get("derived")
    if isinstance(groups, list) and groups and isinstance(derived, dict) \
            and _is_num(derived.get("repetitions")):
        warns.append(
            "resources.power 未登记 design_size 原生落格，但 contract.groups "
            "已声明分组设计且 derived.repetitions 在场：每组 n 若借 "
            "repetitions 解释性落位属借位写法——分组设计请用 "
            "resources.power.design_size（form/per_group_n/total_n/"
            "achieved_power，求解器 light-design power）原生登记"
            "（v1.2 警告，不拦截；计算实验替代口径不受此限）")
    return warns


# ---------- 冻结哈希 ----------

def compute_content_hash(design: dict) -> str:
    """正文内容哈希：排除 status_history / updated / freeze.content_hash /
    freeze.amendments（留痕区不进指纹，amendment 链以 new_hash 衔接）。"""
    body = copy.deepcopy(design)
    body.pop("status_history", None)
    body.pop("updated", None)
    fr = body.get("freeze")
    if isinstance(fr, dict):
        fr.pop("content_hash", None)
        fr.pop("amendments", None)
    payload = json.dumps(body, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def current_frozen_hash(design: dict) -> str | None:
    """当前应有的冻结哈希：有 amendment 取最后一条的 new_hash，
    否则取 freeze.content_hash。"""
    fr = design.get("freeze") or {}
    amds = fr.get("amendments") or []
    if amds:
        return amds[-1].get("new_hash")
    return fr.get("content_hash")


# ---------- 结构 + 硬规则校验 ----------

def validate_design(design: dict) -> list[str]:
    """校验设计书：结构合法性 + 全部可机械验的硬规则（分级感知）。
    返回错误列表（空 = 合法）。每条错误点名字段与所犯规则。
    状态门（能否推进）不在此处，见 gates.py。"""
    errs: list[str] = []
    if not isinstance(design, dict):
        return ["设计书不是 YAML 映射"]

    # ---- 头部 ----
    for key in ("design_id", "idea_id", "title", "tier", "status"):
        if key not in design:
            errs.append(f"缺失必填字段：{key}")
    if "design_id" in design and not _nonempty_str(design.get("design_id")):
        errs.append("design_id 为空")
    if "idea_id" in design and not _nonempty_str(design.get("idea_id")):
        errs.append("idea_id 为空（设计书必须承接一张定版想法卡）")
    if "title" in design and not _nonempty_str(design.get("title")):
        errs.append("title 为空")
    tier = design.get("tier")
    if tier is not None and tier not in TIERS:
        errs.append(f"tier 非法：{tier!r}（须为 {TIERS} 之一）")
    if design.get("status") is not None and design.get("status") not in ALL_STATES:
        errs.append(f"status 非法：{design.get('status')!r}（须为 {ALL_STATES} 之一）")
    full = tier != "minimal"

    # ---- 登记头 registration ----
    reg = design.get("registration")
    if not isinstance(reg, dict):
        errs.append("registration（登记头）缺失或不是映射")
        reg = {}
    vis = reg.get("visibility")
    if vis not in VISIBILITY_LEVELS:
        errs.append(
            f"registration.visibility 非法或缺失：{vis!r}"
            f"（结果可见性五档声明必填，须为 {VISIBILITY_LEVELS} 之一）")

    # ---- 主张区 claims ----
    claims = design.get("claims")
    if not isinstance(claims, dict):
        errs.append("claims（主张区）缺失或不是映射")
        claims = {}
    primary = claims.get("primary_claims")
    if not isinstance(primary, list) or not primary:
        errs.append("claims.primary_claims 为空（至少 1 条主张）")
        primary = primary if isinstance(primary, list) else []
    if len(primary) > 2:
        errs.append(f"claims.primary_claims 有 {len(primary)} 条 > 2"
                    "（约束 1：主主张上限 2 条，防设计摊大饼）")
    for i, c in enumerate(primary):
        if not isinstance(c, dict):
            errs.append(f"claims.primary_claims[{i}] 不是映射")
            continue
        if not _nonempty_str(c.get("statement")):
            errs.append(f"claims.primary_claims[{i}].statement 为空")
        if not _nonempty_str(c.get("minimum_convincing_evidence")):
            errs.append(f"claims.primary_claims[{i}].minimum_convincing_evidence 为空"
                        "（约束 1：每条主张须写明什么证据能让强审稿人信服）")
    anti = claims.get("anti_claims")
    if not isinstance(anti, list) or not anti:
        errs.append("claims.anti_claims 为空（约束 1：必须登记要排除的反主张）")
    else:
        for i, a in enumerate(anti):
            if not isinstance(a, dict) or not _nonempty_str(a.get("statement")):
                errs.append(f"claims.anti_claims[{i}].statement 为空")
    has_confirmatory = any(
        isinstance(c, dict) and c.get("confirmatory") for c in primary)
    if tier == "minimal" and has_confirmatory:
        errs.append("极简级设计不许承载确认性主结论（拍板 ③）："
                    "claims 中存在 confirmatory=true 的主张，与 tier=minimal 冲突")
    if vis == "results_seen" and has_confirmatory:
        errs.append("registration.visibility=results_seen（结果已看过）时"
                    "不许有确认性主张（约束 2：第 5 档只许探索性）")

    # ---- 方案区 plan ----
    plan = design.get("plan")
    if not isinstance(plan, dict):
        errs.append("plan（方案区）缺失或不是映射")
        plan = {}
    if full and plan.get("design_type") not in DESIGN_TYPES:
        errs.append(f"plan.design_type 非法或缺失：{plan.get('design_type')!r}"
                    f"（须为 {DESIGN_TYPES} 之一）")
    variables = plan.get("variables")
    if not isinstance(variables, list) or not variables:
        errs.append("plan.variables 为空（变量表必填，取值全枚举）")
        variables = variables if isinstance(variables, list) else []
    seen_groups = set()
    for i, v in enumerate(variables):
        if not isinstance(v, dict):
            errs.append(f"plan.variables[{i}] 不是映射")
            continue
        if not _nonempty_str(v.get("name")):
            errs.append(f"plan.variables[{i}].name 为空")
        g = v.get("group")
        if g not in VARIABLE_GROUPS:
            errs.append(f"plan.variables[{i}].group 非法：{g!r}"
                        f"（变量三组须为 {VARIABLE_GROUPS} 之一）")
        else:
            seen_groups.add(g)
        dom = v.get("domain")
        if not isinstance(dom, dict) or dom.get("kind") not in DOMAIN_KINDS:
            errs.append(f"plan.variables[{i}].domain 非法：须声明取值域"
                        f"（kind ∈ {DOMAIN_KINDS}）")
        else:
            k = dom["kind"]
            if k == "range" and not (isinstance(dom.get("min"), (int, float))
                                     and isinstance(dom.get("max"), (int, float))):
                errs.append(f"plan.variables[{i}].domain 为 range 时须给 min/max")
            if k == "choice" and not (isinstance(dom.get("values"), list)
                                      and dom["values"]):
                errs.append(f"plan.variables[{i}].domain 为 choice 时须给非空 values")
            if k == "fixed" and "value" not in dom:
                errs.append(f"plan.variables[{i}].domain 为 fixed 时须给 value（冻结值）")
    if variables and seen_groups != set(VARIABLE_GROUPS):
        errs.append(f"plan.variables 三组不齐：已有 {sorted(seen_groups)}，"
                    f"缺 {sorted(set(VARIABLE_GROUPS) - seen_groups)}")
    if not _nonempty_str(plan.get("replication_level")):
        errs.append("plan.replication_level 未声明（约束 8：独立重复层级必填，"
                    "n 按处理被独立随机化到的层级计）")
    if full:
        cps = plan.get("intervention_checkpoints")
        if not isinstance(cps, list) or not cps:
            errs.append("plan.intervention_checkpoints 为空（约束 4："
                        "每个处理须预置干预生效核查点，执行后留证）")

    # ---- 实验契约区 contract ----
    contract = design.get("contract")
    if not isinstance(contract, dict):
        errs.append("contract（实验契约区）缺失或不是映射")
        contract = {}
    controls = contract.get("controls")
    if not isinstance(controls, list) or not controls:
        errs.append("contract.controls 为空（对照组是必填一等字段，约束 3）")
        controls = controls if isinstance(controls, list) else []
    for i, c in enumerate(controls):
        if not isinstance(c, dict) or not _nonempty_str(c.get("name")):
            errs.append(f"contract.controls[{i}] 缺 name（对照须点名）")
    if controls and not any(isinstance(c, dict) and c.get("status_quo") for c in controls):
        errs.append("contract.controls 无 status_quo 一等对照（须把最强基线"
                    "标记为 status_quo=true，自动进入每一批运行）")
    ablations = contract.get("ablations")
    if not isinstance(ablations, list):
        errs.append("contract.ablations 必须是列表")
        ablations = []
    if full and not ablations:
        errs.append("contract.ablations 为空（完整级须有消融矩阵）")
    for i, a in enumerate(ablations):
        if not isinstance(a, dict):
            errs.append(f"contract.ablations[{i}] 不是映射")
            continue
        if not _nonempty_str(a.get("what_it_tests")):
            errs.append(f"contract.ablations[{i}].what_it_tests 为空"
                        "（每条消融须先行写明测什么）")
        if not _nonempty_str(a.get("expected_if_component_matters")):
            errs.append(f"contract.ablations[{i}].expected_if_component_matters 为空"
                        "（每条消融须先行写明组件重要则预期看到什么）")
    if not isinstance(contract.get("unnecessary_ablations"), list):
        errs.append("contract.unnecessary_ablations 必须是列表"
                    "（「不做什么」也要显式登记，可为空列表但须在场）")

    # 运行清单 + 对照先行 + 无环
    runs = contract.get("runs")
    if not isinstance(runs, list):
        errs.append("contract.runs 必须是列表（运行清单）")
        runs = []
    run_by_id: dict[str, dict] = {}
    for i, r in enumerate(runs):
        if not isinstance(r, dict) or not _nonempty_str(r.get("run_id")):
            errs.append(f"contract.runs[{i}] 缺 run_id")
            continue
        if r.get("role") is not None and r.get("role") not in RUN_ROLES:
            errs.append(f"contract.runs[{i}].role 非法：{r.get('role')!r}"
                        f"（须为 {RUN_ROLES} 之一）")
        run_by_id[r["run_id"]] = r
    for r in runs:
        if not isinstance(r, dict) or not _nonempty_str(r.get("run_id")):
            continue
        deps = r.get("depends_on") or []
        if not isinstance(deps, list):
            errs.append(f"contract.runs[{r['run_id']}].depends_on 必须是列表")
            continue
        for d in deps:
            if d not in run_by_id:
                errs.append(f"contract.runs[{r['run_id']}].depends_on 引用了"
                            f"不存在的 run：{d}")
        if r.get("role") == "treatment":
            ctrl = r.get("control_run")
            if not _nonempty_str(ctrl):
                errs.append(f"contract.runs[{r['run_id']}] 是处理组但未声明 "
                            "control_run（对照先行，拍板 ⑥）")
            elif ctrl not in run_by_id:
                errs.append(f"contract.runs[{r['run_id']}].control_run={ctrl} "
                            "不在运行清单中")
            elif run_by_id[ctrl].get("role") != "control":
                errs.append(f"contract.runs[{r['run_id']}].control_run={ctrl} "
                            "不是 control 角色的 run")
            elif ctrl not in deps:
                errs.append(f"contract.runs[{r['run_id']}] 未把其对照 {ctrl} 列入 "
                            "depends_on（约束 3：对照先行是调度不变量，不是建议）")
    # 依赖无环（DFS）
    graph = {rid: [d for d in (r.get("depends_on") or []) if d in run_by_id]
             for rid, r in run_by_id.items()}
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {rid: WHITE for rid in graph}
    cycle: list[str] = []

    def _dfs(u: str, stack: list[str]) -> None:
        color[u] = GRAY
        for w in graph.get(u, []):
            if cycle:
                return
            if color.get(w) == GRAY:
                cycle.extend(stack + [u, w])
                return
            if color.get(w) == WHITE:
                _dfs(w, stack + [u])
        color[u] = BLACK

    for rid in graph:
        if color[rid] == WHITE:
            _dfs(rid, [])
        if cycle:
            errs.append(f"contract.runs 依赖图有环：{' → '.join(cycle)}")
            break

    # ---- 评估协议区 evaluation ----
    ev = design.get("evaluation")
    if not isinstance(ev, dict):
        errs.append("evaluation（评估协议区）缺失或不是映射")
        ev = {}
    pm = ev.get("primary_metric")
    if not isinstance(pm, dict) or not _nonempty_str(pm.get("name")):
        errs.append("evaluation.primary_metric 缺失或无 name（主指标唯一，须点名）")
    elif full and not _nonempty_str(pm.get("convention_source")):
        errs.append("evaluation.primary_metric.convention_source 为空"
                    "（主指标须带领域惯例出处）")
    if not isinstance(ev.get("guardrail_metrics"), list):
        errs.append("evaluation.guardrail_metrics 必须是列表（护栏指标与主指标分离登记）")
    readout = ev.get("readout")
    if not isinstance(readout, dict):
        errs.append("evaluation.readout 缺失（判读标准三向必填）")
        readout = {}
    for side in ("positive", "negative", "null"):
        s = readout.get(side)
        if not isinstance(s, dict) or not _nonempty_str(s.get("meaning")):
            errs.append(f"evaluation.readout.{side}.meaning 为空"
                        "（判读三向齐全：正/负/零各自意味着什么，须见结果前写死）")
    tp = ev.get("tuning_parity")
    if not isinstance(tp, dict) or not _nonempty_str(tp.get("statement")):
        errs.append("evaluation.tuning_parity.statement 未声明（约束 7："
                    "自家方法与每个基线的调参预算须对等登记）")
    seeds = ev.get("seeds")
    if not isinstance(seeds, dict) or not (isinstance(seeds.get("count"), int)
                                            and seeds["count"] >= 1):
        errs.append("evaluation.seeds.count 未声明或 < 1（种子数须预先定明，约束 7）")
    if not (isinstance(ev.get("repetitions"), int) and ev["repetitions"] >= 1):
        errs.append("evaluation.repetitions 未声明或 < 1（重复数须与重复层级对账）")

    # ---- SESOI 结构化登记（DES-D01）：evaluation.sesoi 为单一事实源 ----
    sesoi_block = ev.get("sesoi")
    if sesoi_block is not None:
        errs.extend(validate_sesoi_block(sesoi_block))
        pm_dir = pm.get("direction") if isinstance(pm, dict) else None
        if isinstance(sesoi_block, dict) and _nonempty_str(pm_dir):
            head = str(pm_dir).split("_")[0]
            sd = sesoi_block.get("direction")
            if head in SESOI_DIRECTIONS and sd in SESOI_DIRECTIONS \
                    and head != sd:
                errs.append(
                    f"evaluation.sesoi.direction={sd!r} 与主指标方向 "
                    f"{pm_dir!r} 不一致（SESOI 方向须与主指标改善方向同向）")
    elif full and has_confirmatory:
        errs.append("evaluation.sesoi 缺失（DES-D01：带确认性主张的完整级"
                    "设计必须在 evaluation 区登记结构化 SESOI——数值/单位/"
                    "方向/边界/推导依据/目标量引用/汇总度量，"
                    "下游判定只认登记块，不认文本叙述）")

    # ---- 登记行 SESOI 派生一致性（DES-D01）：行内只许机械复制 ----
    _ho = design.get("handoff")
    _ho_rows = _ho.get("expected_registry") if isinstance(_ho, dict) else None
    if isinstance(_ho_rows, list):
        for i, row in enumerate(_ho_rows):
            if not isinstance(row, dict):
                continue
            rid = row.get("run_id") or f"#{i}"
            row_sesoi = row.get("sesoi")
            if row_sesoi is not None and sesoi_block is None:
                errs.append(
                    f"handoff.expected_registry[{rid}].sesoi 无 evaluation "
                    "登记来源（登记行 SESOI 只能从 evaluation.sesoi 派生，"
                    "不许登记行单独填）")
            elif row_sesoi is not None:
                diff = sesoi_diff_fields(row_sesoi, sesoi_block)
                if diff:
                    errs.append(
                        f"handoff.expected_registry[{rid}].sesoi 与 "
                        f"evaluation.sesoi 登记不一致（字段 {diff}）："
                        "登记行只许携带登记块的派生副本")
            elif sesoi_block is not None and has_confirmatory:
                errs.append(
                    f"handoff.expected_registry[{rid}] 缺 sesoi 派生副本"
                    "（确认性设计的登记行须携带与 evaluation.sesoi "
                    "逐字段一致的 sesoi 块）")

    # ---- 效度区 validity ----
    val = design.get("validity")
    if not isinstance(val, dict):
        errs.append("validity（效度区）缺失或不是映射")
        val = {}
    threats = val.get("threats")
    if not isinstance(threats, list):
        errs.append("validity.threats 必须是列表")
        threats = []
    covered = set()
    for i, t in enumerate(threats):
        if not isinstance(t, dict):
            errs.append(f"validity.threats[{i}] 不是映射")
            continue
        cat = t.get("category")
        if cat not in THREAT_CATEGORIES:
            errs.append(f"validity.threats[{i}].category 非法：{cat!r}"
                        f"（四分法须为 {THREAT_CATEGORIES} 之一）")
        else:
            covered.add(cat)
        if not _nonempty_str(t.get("item")):
            errs.append(f"validity.threats[{i}].item 为空")
        st = t.get("status")
        if st not in THREAT_STATUSES:
            errs.append(f"validity.threats[{i}].status 非法：{st!r}"
                        f"（三态须为 {THREAT_STATUSES} 之一）")
        elif not _nonempty_str(t.get("note")):
            errs.append(f"validity.threats[{i}] 状态为 {st} 但 note 为空"
                        "（na 须附理由、mitigated 须附措施、residual 须附残余声明）")
    missing_cats = [c for c in THREAT_CATEGORIES if c not in covered]
    if missing_cats:
        errs.append(f"validity.threats 效度类别缺失：{missing_cats}"
                    "（约束 6：四分法逐类登记，整类缺失即设计不完整）")
    if full and not isinstance(val.get("structural_checks"), list):
        errs.append("validity.structural_checks 必须是列表（结构错误清单逐项自查）")

    # ---- 资源区 resources ----
    res = design.get("resources")
    if not isinstance(res, dict):
        errs.append("resources（资源区）缺失或不是映射")
        res = {}
    breakers = res.get("circuit_breakers")
    if not isinstance(breakers, list) or not breakers:
        errs.append("resources.circuit_breakers 为空（量化熔断线必填："
                    "失败率/超时/早停须有预先写死的数值）")
    else:
        for i, b in enumerate(breakers):
            if not isinstance(b, dict) or not _nonempty_str(b.get("metric")) \
                    or not _nonempty_str(str(b.get("threshold") or "")):
                errs.append(f"resources.circuit_breakers[{i}] 缺 metric/threshold")
    power = res.get("power")
    if full:
        if not isinstance(power, dict):
            errs.append("resources.power 缺失（拍板 ②：功效核算强制）")
            power = {}
        if not _nonempty_str(power.get("sesoi")):
            errs.append("resources.power.sesoi 为空（须以 SESOI/MDE 为据，不许发明效应量）")
        sr = power.get("sensitivity_range")
        if not (_nonempty_str(sr) if isinstance(sr, str)
                else isinstance(sr, dict) and bool(sr)):
            errs.append("resources.power.sensitivity_range 为空"
                        "（约束 9：交付物是敏感性范围，不是单个 n）")
        derived = power.get("derived")
        if not isinstance(derived, dict) or not any(
                isinstance(derived.get(k), (int, float))
                for k in ("seeds", "repetitions", "eval_set_size")):
            errs.append("resources.power.derived 未给出种子数/重复数/评估集规模"
                        "核算结果（计算实验替代口径，拍板 ②）")
        stages = res.get("stages")
        if not isinstance(stages, list) or not stages:
            errs.append("resources.stages 为空（阶段表必填：进入/退出转移条件开跑前写死）")
    if isinstance(power, dict) and power.get("sufficient") is False and has_confirmatory:
        errs.append("resources.power.sufficient=false（功效核算给不起所需重复）"
                    "但仍保留确认性主张（拍板 ②：给不起须下调声称为探索性）")
    if isinstance(power, dict) and power:
        errs.extend(_power_design_size_errors(power))

    # ---- 冻结区 freeze ----
    fr = design.get("freeze")
    if not isinstance(fr, dict):
        errs.append("freeze（冻结区）缺失或不是映射")
        fr = {}
    amds = fr.get("amendments") or []
    if not isinstance(amds, list):
        errs.append("freeze.amendments 必须是列表（只许追加）")
        amds = []
    for i, a in enumerate(amds):
        if not isinstance(a, dict):
            errs.append(f"freeze.amendments[{i}] 不是映射")
            continue
        for k in ("date", "fields", "reason", "results_seen", "new_hash"):
            if k not in a:
                errs.append(f"freeze.amendments[{i}] 缺 {k}")
        fields = a.get("fields") or []
        crit = [f for f in fields if is_critical_field(str(f))]
        if crit and a.get("user_signed") is not True:
            errs.append(f"freeze.amendments[{i}] 修订了命门字段 {crit} 但无用户签"
                        "（拍板 ⑤：判读标准/主指标/主张/停止规则的 amendment "
                        "须 user_signed=true）")
        # DES-D02：类别声明合法性（旧 amendment 无 category 字段不追溯）
        cat = a.get("category")
        if cat is not None and cat not in AMD_CATEGORIES:
            errs.append(f"freeze.amendments[{i}].category 非法：{cat!r}"
                        f"（须为 {AMD_CATEGORIES} 之一，DES-D02 类别分流）")
        if cat == "prewritten_branch" and not _nonempty_str(a.get("branch_ref")):
            errs.append(f"freeze.amendments[{i}] 声明 category="
                        "prewritten_branch 但缺 branch_ref（预写分支须"
                        "点名定版预写的分支，DES-D02/C-补04）")
    if design.get("status") == "frozen" or fr.get("content_hash"):
        expected = current_frozen_hash(design)
        if not expected:
            errs.append("已冻结但 freeze.content_hash 缺失")
        elif compute_content_hash(design) != expected:
            errs.append("正文与冻结哈希不一致：冻结后正文被回改"
                        "（约束 12：修订只许走 amendment 追加，原文永不回改）")

    # ---- 交接区 handoff（结构层） ----
    ho = design.get("handoff")
    if ho is not None and not isinstance(ho, dict):
        errs.append("handoff（交接区）必须是映射")

    # ---- intake 跨区实体核查（DES-D04）：expanded 必须有实体落点 ----
    errs.extend(intake_expanded_entity_errors(design))

    # ---- 辅助区 aux：与判定物理分离 ----
    aux = design.get("aux", {})
    if aux is not None and not isinstance(aux, dict):
        errs.append("aux 必须是映射")
    elif isinstance(aux, dict):
        for k in aux:
            if k in AUX_FORBIDDEN_KEYS:
                errs.append(f"aux 区混入判定字段 {k}：判定只许在 freeze.review")
            elif k not in AUX_KEYS:
                errs.append(f"aux 区未知字段 {k}（只许 {AUX_KEYS}）")

    # ---- 旁路记录一致性 ----
    if design.get("status") == "returned" and not isinstance(design.get("return_record"), dict):
        errs.append("status=returned 但缺 return_record（打回单）")
    if design.get("status") == "blocked" and not isinstance(design.get("block_record"), dict):
        errs.append("status=blocked 但缺 block_record")

    return errs


def empty_design(design_id: str, idea_id: str, title: str, tier: str, today: str) -> dict:
    """生成一份结构在位的空白设计书（draft），供 `new` 落盘后填充。
    空白书不满足硬规则——validate 会逐条列出缺什么，这正是骨架的用途。"""
    return {
        "design_id": design_id,
        "idea_id": idea_id,
        "title": title,
        "tier": tier,
        "status": "draft",
        "created": today,
        "updated": today,
        "registration": {
            "visibility": None,       # 结果可见性五档声明（必填）
            "existing_assets": [],    # 定版时已存在的数据/代码/历史结果
            "software_env": "",       # 软件与环境版本
            "designer": {"model": None, "family": None},  # 设计生成者（复核异族校验用）
        },
        "intake": {
            "source_handoff": None,   # {path, consumed_at, handoff_hash}
            "original_question": "",  # 原始研究问题逐字保留
            "spec_intake": [],        # 六项逐项承接 {item, handoff_value, design_location, status}
            "returned_items": [],     # 打回记录 {item, reason, needed, date, resolved}
        },
        "claims": {
            "primary_claims": [],     # ≤2 {id, statement, why_it_matters, minimum_convincing_evidence, confirmatory}
            "supporting_claim": None,
            "anti_claims": [],        # {id, statement, excluded_by}
        },
        "plan": {
            "design_type": None,
            "variables": [],          # {name, group, domain{kind, ...}}
            "variable_constraints": [],
            "randomization": {"method": "", "seed_policy": ""},
            "blocking_stratification": "",
            "intervention_mechanism": [],   # {variable, how}
            "intervention_checkpoints": [],  # 干预生效核查点
            "deviation_branches": [],   # 定版预写偏离分支（DES-D02/C-补04）：{id, trigger, fields, fallback}；冻结后执行分支内变更走 amendment category=prewritten_branch + branch_ref 轻评审
            "replication_level": None,       # 独立重复层级声明
            "replication_counts": {},
        },
        "contract": {
            "controls": [],           # {name, role, status_quo, source}
            "groups": [],
            "ablations": [],          # {id, what_it_tests, expected_if_component_matters, type, form, claim_ref}
            "unnecessary_ablations": [],  # {what, reason}
            "sanity_checks": [],
            "runs": [],               # {run_id, role, control_run, depends_on, stage, priority}
        },
        "evaluation": {
            "primary_metric": None,   # {name, definition, direction, convention_source}
            "sesoi": None,            # 结构化 SESOI 登记块（DES-D01）：{value, unit, direction, bounds, basis, estimand_ref, summary_measure}
            "guardrail_metrics": [],  # {name, bound}
            "construct_mapping": [],
            "data_protocol": None,
            "analysis_plan": None,
            "readout": {"positive": None, "negative": None, "null": None},
            "exclusion_rules": "",
            "tuning_parity": None,    # {statement, details}
            "seeds": {"count": None, "policy": ""},
            "repetitions": None,
            "exploratory_notes": "",
        },
        "validity": {
            "threats": [],            # {category, item, status, note}
            "structural_checks": [],  # {item, status: pass|flagged, note}
            "failure_modes": [],
        },
        "resources": {
            "power": None,            # {sesoi, basis, alpha, target_power, method, derived, sensitivity_range, sufficient}；分组经典设计另落 design_size 求解器落格 + sensitivity_table 结构化敏感性表（v1.2，见 power.py 与 _power_design_size_errors）
            "budget": {"compute": "", "time": "", "human": ""},
            "attempt_budget": None,
            "stages": [],             # {name, goal, entry_condition, exit_condition}
            "circuit_breakers": [],   # {metric, threshold, action}
        },
        "freeze": {
            "review": None,           # {reviewer, family, date, items, decision, review_status}
            "frozen_at": None,
            "content_hash": None,
            "amendments": [],         # 只追加 {date, fields, reason, results_seen, user_signed, approved_by, new_hash}
        },
        "handoff": {
            "expected_registry": [],  # {run_id, expected}
            "repro_fields": None,
            "checkpoints": [],        # {node, human_confirm}
            "alignment_gate": "",
        },
        "aux": {},
        "status_history": [{"from": None, "to": "draft", "date": today,
                            "by": "light-design new", "note": "建书"}],
        "return_record": None,
        "block_record": None,
    }
