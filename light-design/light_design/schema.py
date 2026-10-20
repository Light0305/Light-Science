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
- aux 辅助区与判定物理分离：分数/判定字段不许混入（约束 13）。
"""

from __future__ import annotations

import copy
import hashlib
import json

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
    "claims",                        # 主张
    "resources.circuit_breakers",    # 停止规则/熔断线
)

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
            "power": None,            # {sesoi, basis, alpha, target_power, method, derived, sensitivity_range, sufficient}
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
