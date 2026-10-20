"""想法卡 schema：字段定义与结构校验。

设计依据：02-idea/REDESIGN-DRAFT.md §2.1 字段草案 + LEARNING.md 八条硬约束。
核心纪律（校验器写死）：
- 文献引用（种子文献、facet 出处、最接近工作）必须带 light-literature 的
  paper_id 或 DOI，不许裸文本（与 Literature「未核实成稿层一律不用」对齐）；
- 查新判定区（novelty）与辅助字段区（aux）物理分离：novelty 区不许出现
  相似度分等辅助信号，aux 区不许出现 verdict（约束 3：分数不进判定区）；
- 生成出处（provenance）必填，无出处不许入池（LEARNING §2 扇出纪律）。
"""

from __future__ import annotations

# ---------- 枚举 ----------

OPERATORS = ("evolution_chain", "collider", "graph_path", "user_supplied", "manual")
# 演进链 / 远域碰撞为 v1 算子（拍板 9.3-B）；graph_path 预留 v2；user_supplied/manual 为人工入口

CONTRIBUTION_TYPES = ("empirical", "method", "theory", "diagnostic")

FACETS = ("purpose", "mechanism", "evaluation")
FACET_SOURCE_TYPES = ("paper", "chain_node", "operator", "user")

VERDICTS = ("PROCEED", "PROCEED_WITH_CAUTION", "ABANDON")
REVIEW_STATUSES = ("ok", "REVIEW_UNAVAILABLE")

# 状态机主线与旁路（拍板 9.2-B 两级定版）
MAIN_STATES = (
    "draft",
    "screened",
    "novelty_checked",
    "pre_mortem_passed",
    "finalized_executable",
    "finalized_conceptual",
)
BYPASS_STATES = ("killed", "parked")
ALL_STATES = MAIN_STATES + BYPASS_STATES
TERMINAL_STATES = ("finalized_executable", "finalized_conceptual", "killed")

KILL_SOURCES = ("budget_gate", "novelty_named_paper", "pilot_negative", "pre_mortem", "manual")
FAILURE_CLASSES = ("fundamental", "implementation")  # 约束 8：失败二分类

PILOT_STATUSES = ("not_run", "verified", "negative")

# 执行级规格六项（定版 finalized_executable 的硬门，草案 §2.1 + 任务书口径）
EXEC_SPEC_ITEMS = (
    "datasets",            # 指名数据集（名称 + 版本/获取路径）
    "strongest_baseline",  # 指名最强基线（点名工作）
    "metrics",             # 指标 + 领域惯例出处
    "ablations",           # 计划中的消融（逐项列表）
    "resource_budget",     # 资源预算（算力/数据/工期）
    "key_details",         # 关键实现细节（先写死，防执行期即兴发挥）
)

# 能力缺口处置三选一（IDEA-D03：每项所需能力逐项给处置结论）
CAPABILITY_DISPOSITIONS = ("have", "fillable", "blocking")
CAPABILITY_DISPOSITION_LABELS = {
    "have": "已有",
    "fillable": "可短期补",
    "blocking": "构成不可行",
}

# pre-mortem 清单（LEARNING 自研缺口 6：执行阶段评审者问题集，逐项可判定）
PRE_MORTEM_ITEMS = (
    "strongest_baseline_attack",  # 以最强基线攻击，方法是否仍站得住
    "metric_convention",          # 指标是否合领域惯例
    "ablations_complete",         # 消融是否齐
    "resources_realistic",        # 资源是否现实
    "null_result_learning",       # 方法无效时能学到什么（已写明）
    "method_instantiable",        # 核心方法是否具体到可实例化（不含糊）
    "capability_match",           # 能力匹配（v1.1 IDEA-D03 独立成项）：
                                  # 所需能力与队伍现状逐项对账过了吗
)

# aux 区只许这些键（判定信号一律不许混入）
AUX_KEYS = (
    "neighbor_similarity",   # 最近邻相似度分（粗筛信号）
    "atypicality_z",         # 组合非典型性 z 分数（须与 conventionality_z 成对）
    "conventionality_z",
    "source_disruption",     # 来源论文 disruption 画像
    "pairwise_record",       # 两两对决战绩（标「暂定」）
    "elo",                   # 内部排序 Elo（标「暂定」）
)
AUX_FORBIDDEN_KEYS = ("verdict", "novelty_verdict", "decision", "score_gate")

CARD_SECTIONS = (
    "idea_id", "title", "one_liner", "status", "operator", "provenance",
    "created", "updated", "seed_refs", "facets", "body", "feasibility",
    "exec_spec", "negative", "pre_mortem", "finalization_level",
    "novelty", "aux", "pilot", "lineage",
    "dedup", "status_history", "kill", "park",
)


# ---------- 小工具 ----------

def _nonempty_str(v) -> bool:
    return isinstance(v, str) and bool(v.strip())


def _ref_ok(ref) -> bool:
    """文献引用合法性：必须是 dict 且带 paper_id 或 doi（不许裸文本）。"""
    if not isinstance(ref, dict):
        return False
    return _nonempty_str(ref.get("paper_id")) or _nonempty_str(ref.get("doi"))


def model_family(model: str) -> str:
    """从模型名粗取家族标识（跨模型收据校验用）。

    规则：小写后取第一个分隔符（/、空格、:）之前的部分，再剥掉常见
    厂商前缀后的主体名。例如 'claude-opus-4' 与 'anthropic/claude-opus-4'
    都归一到同一家族标识的近似比较——本函数只做确定性粗判，SKILL 中
    要求收据里同时登记 judge_family / executor_family 显式字段，
    显式字段优先于本函数的推断。
    """
    m = (model or "").strip().lower()
    if not m:
        return ""
    head = m.replace("/", " ").replace(":", " ").split()[0]
    return head


# ---------- 能力匹配子区（IDEA-D03） ----------

def _capability_fit_shape_errors(fit) -> list[str]:
    """capability_fit 的形状校验（只查结构与枚举，不查覆盖完整性）。

    结构：required = [{capability, detail}]（所需能力清单）；
    team_status = 队伍现状字符串（技能/设备/数据积累，须有据）；
    gaps = [{capability, disposition, note}]（逐项处置：三选一 +
    依据必填——评级不许空评）。
    """
    errs: list[str] = []
    if not isinstance(fit, dict):
        return ["exec_spec.capability_fit 必须是映射（required / "
                "team_status / gaps）"]
    required = fit.get("required")
    if not isinstance(required, list) or not required:
        errs.append("capability_fit.required 为空（所需能力清单必填，"
                    "逐项列 {capability, detail}）")
    else:
        for i, item in enumerate(required):
            if not isinstance(item, dict) \
                    or not _nonempty_str(item.get("capability")):
                errs.append(f"capability_fit.required[{i}] 缺 capability"
                            f"（所需能力须逐项点名）")
            elif not _nonempty_str(item.get("detail")):
                errs.append(f"capability_fit.required[{i}] 缺 detail"
                            f"（该能力具体指什么、要到什么程度）")
    if not _nonempty_str(fit.get("team_status")):
        errs.append("capability_fit.team_status 为空（队伍现状必填："
                    "技能/设备/数据积累的既往实绩，评级依据在此）")
    gaps = fit.get("gaps")
    if not isinstance(gaps, list):
        errs.append("capability_fit.gaps 必须是列表（逐项处置清单）")
    else:
        for i, g in enumerate(gaps):
            if not isinstance(g, dict) \
                    or not _nonempty_str(g.get("capability")):
                errs.append(f"capability_fit.gaps[{i}] 缺 capability")
                continue
            if g.get("disposition") not in CAPABILITY_DISPOSITIONS:
                errs.append(
                    f"capability_fit.gaps[{i}] disposition 非法："
                    f"{g.get('disposition')!r}（须为 "
                    f"{CAPABILITY_DISPOSITIONS} 之一：已有/可短期补/"
                    f"构成不可行）")
            if not _nonempty_str(g.get("note")):
                errs.append(f"capability_fit.gaps[{i}] 缺 note（处置"
                            f"结论须给依据，不许空评）")
    return errs


def capability_fit_errors(card: dict, *, for_executable: bool) -> list[str]:
    """能力匹配完整性校验（定版门用）：在场 + 形状 + 覆盖 + 定版口径。

    - 完整性：gaps 处置须覆盖 required 的每一项所需能力；
    - 可执行级：任一 blocking 缺口未解 → 不许定版（能力构成不可行
      还硬开工，是执行期死法）；
    - 概念级：blocking 允许（能力未就位正是概念定版的题中之义），
      但子区本身必须齐备——概念定版不许拿「没评估过」冒充。
    """
    fit = (card.get("exec_spec") or {}).get("capability_fit")
    if fit is None:
        return ["定版门：exec_spec.capability_fit 未填（能力匹配维度"
                "必填：这个想法该不该由这支队伍现在做，IDEA-D03）"]
    errs = _capability_fit_shape_errors(fit)
    if errs:
        return [f"定版门：{e}" for e in errs]
    required = {item["capability"].strip()
                for item in fit.get("required") or []}
    assessed = {}
    for g in fit.get("gaps") or []:
        assessed[g["capability"].strip()] = g.get("disposition")
    uncovered = sorted(required - set(assessed))
    if uncovered:
        errs.append("定版门：capability_fit.gaps 未覆盖所需能力："
                    + "、".join(uncovered)
                    + "（每项所需能力都要有处置结论）")
    blocking = sorted(c for c, d in assessed.items() if d == "blocking")
    if for_executable and blocking:
        errs.append("定版门（可执行）：能力缺口构成不可行："
                    + "、".join(blocking)
                    + "——缺口未解不许按可执行定版开工；要么补齐能力"
                      "改判处置，要么降为概念定版")
    return errs


def capability_summary(card: dict) -> dict:
    """能力匹配摘要（对决排序参考与卡面展示用；只汇总、不打分）。

    返回 {assessed: bool, counts: {have, fillable, blocking},
    worst: 'blocking'|'fillable'|'have'|'unassessed'}。
    worst 只是展示用的最差处置标记，不是淘汰信号（与 aux 同纪律）。
    """
    fit = (card.get("exec_spec") or {}).get("capability_fit")
    counts = {"have": 0, "fillable": 0, "blocking": 0}
    if not isinstance(fit, dict):
        return {"assessed": False, "counts": counts, "worst": "unassessed"}
    for g in fit.get("gaps") or []:
        d = (g or {}).get("disposition")
        if d in counts:
            counts[d] += 1
    worst = ("blocking" if counts["blocking"] else
             "fillable" if counts["fillable"] else
             "have" if counts["have"] else "unassessed")
    return {"assessed": bool(fit.get("required")), "counts": counts,
            "worst": worst}


# ---------- 结构校验 ----------

def validate_card(card: dict) -> list[str]:
    """校验想法卡的结构合法性，返回错误列表（空 = 合法）。只查结构，
    不查状态门（门在 gates.py）。每条错误都点名缺失/非法的字段。"""
    errs: list[str] = []
    if not isinstance(card, dict):
        return ["想法卡不是 YAML 映射"]

    for key in ("idea_id", "title", "one_liner", "status", "operator", "provenance"):
        if key not in card:
            errs.append(f"缺失必填字段：{key}")
    if "idea_id" in card and not _nonempty_str(card.get("idea_id")):
        errs.append("idea_id 为空")
    if "title" in card and not _nonempty_str(card.get("title")):
        errs.append("title 为空")
    if "status" in card and card.get("status") not in ALL_STATES:
        errs.append(f"status 非法：{card.get('status')!r}（须为 {ALL_STATES} 之一）")
    if "operator" in card and card.get("operator") not in OPERATORS:
        errs.append(f"operator 非法：{card.get('operator')!r}（须为 {OPERATORS} 之一）")

    # 生成出处：无出处不许入池
    prov = card.get("provenance")
    if prov is not None:
        if not isinstance(prov, dict) or not (
            _nonempty_str(prov.get("chain_id"))
            or _nonempty_str(prov.get("path_string"))
            or _nonempty_str(prov.get("combo"))
            or _nonempty_str(prov.get("note"))
        ):
            errs.append("provenance 无出处：须至少给出 chain_id / path_string / combo / note 之一")

    # 种子文献：每条必须带 paper_id 或 DOI
    refs = card.get("seed_refs", [])
    if refs is not None and not isinstance(refs, list):
        errs.append("seed_refs 必须是列表")
        refs = []
    for i, ref in enumerate(refs or []):
        if not _ref_ok(ref):
            errs.append(f"seed_refs[{i}] 不是合法文献引用：必须带 paper_id 或 doi，不许裸文本")

    # facet 区：三面齐全，每面 phrase + detail + source
    facets = card.get("facets")
    if not isinstance(facets, dict):
        errs.append("facets 缺失或不是映射")
    else:
        for facet in FACETS:
            f = facets.get(facet)
            if not isinstance(f, dict):
                errs.append(f"facets.{facet} 缺失")
                continue
            if not _nonempty_str(f.get("phrase")):
                errs.append(f"facets.{facet}.phrase 为空（须为结构化短语）")
            if not _nonempty_str(f.get("detail")):
                errs.append(f"facets.{facet}.detail 为空")
            src = f.get("source")
            if not isinstance(src, dict) or src.get("type") not in FACET_SOURCE_TYPES:
                errs.append(
                    f"facets.{facet}.source 非法：type 须为 {FACET_SOURCE_TYPES} 之一"
                )
            elif src.get("type") == "paper" and not _ref_ok(src):
                errs.append(f"facets.{facet}.source 是 paper 出处时必须带 paper_id 或 doi")

    # 正文区
    body = card.get("body")
    if not isinstance(body, dict):
        errs.append("body 缺失或不是映射")
    else:
        steps = body.get("method_steps")
        if not isinstance(steps, list) or not steps:
            errs.append("body.method_steps 为空（平语方法描述，2–4 步）")
        if not _nonempty_str(body.get("hypothesis")):
            errs.append("body.hypothesis 为空（一句话假设）")
        if body.get("contribution_type") not in CONTRIBUTION_TYPES:
            errs.append(
                f"body.contribution_type 非法：{body.get('contribution_type')!r}"
                f"（须为 {CONTRIBUTION_TYPES} 之一）"
            )

    # 查新区与辅助区的物理分离
    novelty = card.get("novelty", {})
    if novelty is not None and not isinstance(novelty, dict):
        errs.append("novelty 必须是映射")
        novelty = {}
    for bad in ("neighbor_similarity", "similarity", "atypicality_z", "elo"):
        if isinstance(novelty, dict) and bad in novelty:
            errs.append(f"novelty 区混入辅助信号 {bad}：相似度/排序信号只许在 aux 区")
    verdict = (novelty or {}).get("verdict")
    if verdict is not None and verdict not in VERDICTS:
        errs.append(f"novelty.verdict 非法：{verdict!r}（须为 {VERDICTS} 之一或 null）")
    rs = (novelty or {}).get("review_status")
    if rs is not None and rs not in REVIEW_STATUSES:
        errs.append(f"novelty.review_status 非法：{rs!r}（须为 {REVIEW_STATUSES} 之一）")
    for i, w in enumerate((novelty or {}).get("closest_works") or []):
        if not _ref_ok(w):
            errs.append(f"novelty.closest_works[{i}] 不是合法文献引用：必须带 paper_id 或 doi")

    aux = card.get("aux", {})
    if aux is not None and not isinstance(aux, dict):
        errs.append("aux 必须是映射")
    elif isinstance(aux, dict):
        for k in aux:
            if k in AUX_FORBIDDEN_KEYS:
                errs.append(f"aux 区混入判定字段 {k}：判定只许在 novelty 区")
            elif k not in AUX_KEYS:
                errs.append(f"aux 区未知字段 {k}（只许 {AUX_KEYS}）")

    # 能力匹配子区（IDEA-D03）：在场时查形状，完整性（覆盖每项所需
    # 能力、无 blocking 等）由定版门把（gates._capability_fit_errors）
    spec = card.get("exec_spec")
    if isinstance(spec, dict) and spec.get("capability_fit") is not None:
        errs += _capability_fit_shape_errors(spec.get("capability_fit"))

    # 状态旁路字段与状态一致性
    if card.get("status") == "killed" and not isinstance(card.get("kill"), dict):
        errs.append("status=killed 但缺 kill 记录")
    if card.get("status") == "parked" and not isinstance(card.get("park"), dict):
        errs.append("status=parked 但缺 park 记录")

    return errs


def empty_card(idea_id: str, title: str, one_liner: str, operator: str, today: str) -> dict:
    """生成一张结构合法的空白卡（draft），供 `new` 命令落盘后人工/流程填充。"""
    return {
        "idea_id": idea_id,
        "title": title,
        "one_liner": one_liner,
        "status": "draft",
        "operator": operator,
        "provenance": {"chain_id": None, "path_string": None, "combo": None, "note": None},
        "created": today,
        "updated": today,
        "seed_refs": [],
        "facets": {
            f: {"phrase": "", "detail": "", "source": {"type": "user"}}
            for f in FACETS
        },
        "body": {
            "method_steps": [],
            "hypothesis": "",
            "mechanism_rationale": "",
            "unexpected_prediction": "",
            "contribution_type": "method",
        },
        "feasibility": {"compute_within_budget": None, "compute_note": "",
                        "data_obtainable": None, "data_note": ""},
        "exec_spec": {
            "datasets": [],
            "strongest_baseline": None,
            "metrics": [],
            "ablations": [],
            "resource_budget": None,
            "key_details": [],
            "capability_fit": None,  # IDEA-D03：{required, team_status, gaps}
            "discriminating_experiment": None,
        },
        "negative": {"strongest_objection": "", "risks": [], "why_not_selected_first": ""},
        "pre_mortem": None,  # {date, checklist:{item:{status: pass|na, note}}, open_items: []}
        "finalization_level": None,  # 定版后由 advance 写入 executable / conceptual
        "novelty": {
            "checked_at": None,
            "search_scope": {"sources": [], "pool_size": None, "known_blind_spots": ""},
            "closest_works": [],
            "verdict": None,
            "caution_reason": "",
            "receipt": {"verdict_id": None, "judge_model": None, "judge_family": None,
                        "executor_model": None, "executor_family": None},
            "review_status": "ok",
            "evidence_package": None,
        },
        "aux": {},
        "pilot": {"status": "not_run", "note": ""},
        "lineage": {"changed_from": None, "revision_operator": None,
                    "revision_log": [], "bad_case_refs": []},
        "dedup": {"checked": False, "max_similarity": None,
                  "most_similar_to": None, "adjudication": None},
        "status_history": [{"from": None, "to": "draft", "date": today,
                            "by": "light-idea new", "note": "建卡"}],
        "kill": None,
        "park": None,
    }
