"""数据模型与受控词表（Phase 1）。

本模块只定义结构与词表。词表与 REDESIGN-DRAFT（拍板附录 R1–R6 全按推荐）
及 LEARNING（RV-01–RV-18）对齐：

- 状态机六态：intake → forensic_checked → paneled → reported →
  adjudicated → delivered（草案 §四）；
- 法医发现分类沿 D-R02 七类（passed 是检查结果不是发现，不入发现账）；
- 两层分类（RV-08）：数值不一致（inconsistency）是第一层门，
  结论翻转（conclusion_flip）只在第一层已成立时才许计算；
- 共识门（RV-05）：consensus 须 ≥2 席互盲下独立同向；佐证计数只影响
  排序与抽查优先级，永不抬升 severity——severity 由代码取各席独立
  提案的 MAX，校验器钉死，不许手填越过；
- 隔离降档（R1 硬纪律）：isolation_mode = full | degraded，做不到全
  规格时 delivered 产物必须带降档声明，做不到就明说、不冒充。
"""

from __future__ import annotations

from .util import today

# ---------------------------------------------------------------- 状态机

PKG_STATES = ["intake", "forensic_checked", "paneled", "reported",
              "adjudicated", "delivered"]
MAIN_STATES = PKG_STATES

# ---------------------------------------------------------------- 法医词表

FORENSIC_EDGES = ["claims_evidence", "numbers_numbers",
                  "numbers_figures", "citations_claims"]

# 逐项检查结果：decision_error 是 error 的第二层（结论翻转），不是独立结果
CHECK_RESULTS = ["pass", "error", "decision_error", "not_assessable"]

# D-R02 七类中的发现六类（passed 不入发现账）
FINDING_CATEGORIES = [
    "confirmed_error",
    "aggregation_ambiguity",
    "provenance_gap",
    "suspected_duplication",
    "unresolved_input",
    "not_assessable",
]

# 两层分类（RV-08）：inconsistency = 数值/指针不一致；
# conclusion_flip = 在不一致之上进一步翻转结论（强度/符号/决定）
FINDING_LAYERS = ["inconsistency", "conclusion_flip"]

# 人工裁决位（R2 硬度 a）：confirmed error 未裁决不许 delivered
ADJUDICATION_OUTCOMES = ["confirmed", "overruled"]

# 承接快照里必须点名的上游（图包与目标刊记录可缺，但缺必须落字）
SNAPSHOT_PARTS = ["manuscript", "analysis", "figure", "target_journal"]

# ---------------------------------------------------------------- GRIM 词表

GRIM_KINDS = ["mean", "percent", "total"]
COMPAT_RESULTS = ["compatible", "incompatible", "not_assessable"]
# 整数值量表（GRIM 族只对整数粒度数据成立；连续量一律 not assessable）
INTEGER_SCALE_TYPES = ["likert", "count", "score", "integer"]
SCALE_TYPES = INTEGER_SCALE_TYPES + ["continuous", "ratio", "unknown"]

# ---------------------------------------------------------------- 席位/共识词表

ISOLATION_MODES = ["full", "degraded"]
INTENSITIES = ["light", "standard", "thorough"]

# 可见性工件类（RV-01：可见性即权限，矩阵是数据不是口号）
ARTIFACT_KINDS = ["manuscript", "forensic", "own_materials",
                  "other_reports", "consensus"]
PANEL_STAGES = ["panel", "reported", "adjudication"]

SEAT_STATUSES = ["registered", "drafted", "frozen"]

SEVERITIES = ["minor", "major", "critical"]


def severity_rank(sev: str) -> int:
    return SEVERITIES.index(sev)


def computed_severity(proposals: dict) -> str | None:
    """共识 severity 的唯一算法（RV-05）：取各席独立提案的 MAX。

    佐证数（tally）不进入本函数——多席同提只记佐证、永不抬级，
    这是代码不变量，不是规程自觉。
    """
    vals = [s for s in (proposals or {}).values() if s in SEVERITIES]
    if not vals:
        return None
    return max(vals, key=severity_rank)


# Write writable_form 形态序（承 light-write §3 规则表，Review 只复核不重定）
WRITABLE_FORMS = ["full", "qualified", "downgraded", "limitations_only", "omit"]


def form_rank(form: str) -> int:
    """形态强度序：full 最强。writable_form 的 rank 不许小于 ceiling 的 rank。"""
    return WRITABLE_FORMS.index(form)


# ---------------------------------------------------------------- 空结构

def new_review(review_id: str, title: str = "", round_no: int = 1) -> dict:
    """review.yaml 登记头骨架（承接区在 intake 冻结）。"""
    return {
        "review_id": review_id,
        "title": title or review_id,
        "round": round_no,
        "status": "intake",
        "status_history": [
            {"state": "intake", "at": today(), "by": "light-review init"},
        ],
        "created_at": today(),
        "updated_at": today(),
        # 承接区（intake 冻结；缺项逐项点名，不许静默默认）
        "intake": None,        # {manuscript, analysis, figure, target_journal, input_scope, intake_at, intake_by}
        "constraints": None,   # {intensity, seats_spec, want_decision}
        "isolation": None,     # {mode: full|degraded, reason}
        # 冻结账（append-only：每次冻结一条 {seat_id, report_hash, at}）
        "freezes": [],
        # 交付区（deliver 落字；degraded 时 degradation_statement 必填）
        "delivery": None,      # {delivered_at, manifest, manifest_hash, degradation_statement}
        # Phase 2 待落地件（本期如实登记，不假装已有）
        "phase2_pending": ["domain_gate", "calibration", "meta_review",
                           "decision", "handoff_to_write"],
        # 汇总区（工具机械汇总，不许手填）
        "counts": {"findings": 0, "confirmed_error_open": 0,
                   "not_assessable": 0, "concerns": 0, "consensus": 0},
    }


def new_seats() -> dict:
    """seats.yaml 骨架：席位登记 + 逐席可见性矩阵行（RV-01/RV-02）。"""
    return {"seats": []}


def seat_row(seat_id: str, role: str, model_family: str, **kw) -> dict:
    """一席的登记行。visibility 为 {stage: [artifact_kind, ...]}。

    默认矩阵（panel 阶段）：可见 manuscript / forensic / own_materials；
    other_reports 与 consensus 在 reported 之前对任何席不可见——互盲由
    本数据结构强制，panel 读取接口按此放行（RV-01）。
    """
    row = {
        "seat_id": seat_id,
        "role": role,
        "model_family": model_family,
        "persona": kw.get("persona"),          # 人格参数（预设登记，RV-02）
        "knows_authors": kw.get("knows_authors", False),
        "visibility": kw.get("visibility") or {
            "panel": ["manuscript", "forensic", "own_materials"],
            "reported": ["manuscript", "forensic", "own_materials",
                         "other_reports", "consensus"],
            "adjudication": ["manuscript", "forensic", "own_materials",
                             "other_reports", "consensus"],
        },
        "status": "registered",
        "draft_path": None,
        "report_path": None,
        "report_hash": None,
        "frozen_at": None,
        "degraded_note": None,                  # 逐席降级留痕（RV-02）
    }
    return row


def check_row(check_id: str, edge: str, subject_ref: str, result: str,
              **kw) -> dict:
    """reconciliation.jsonl 一行：逐项检查结果 + 证据定位（RV-06/RV-07）。"""
    row = {
        "type": "check",
        "check_id": check_id,
        "edge": edge,
        "subject_ref": subject_ref,
        "result": result,               # pass | error | decision_error | not_assessable
        "detail": kw.get("detail"),
        "claim_pointer": kw.get("claim_pointer"),
        "evidence_pointer": kw.get("evidence_pointer"),
        "raw": kw.get("raw"),           # 抽取物原文片段（模型只做抽取，保留 raw）
    }
    return row


def edge_summary_row(edge: str, *, checked: int, assessable: int,
                     not_assessable: int, errors: int,
                     decision_errors: int) -> dict:
    """reconciliation.jsonl 的边级覆盖自报行（RV-07：每检出厂带分母）。"""
    return {
        "type": "summary",
        "edge": edge,
        "checked": checked,             # 应检数（分母）
        "assessable": assessable,
        "not_assessable": not_assessable,
        "errors": errors,
        "decision_errors": decision_errors,
    }


def finding_row(finding_id: str, check_id: str, edge: str, category: str,
                layer: str, **kw) -> dict:
    """findings.jsonl 一行：法医发现（只增不改，裁决走追加行）。

    两层分类是硬纪律：layer=conclusion_flip 只许出现在已有
    inconsistency 的发现上（由 check 结果 decision_error 派生）。
    """
    return {
        "type": "finding",
        "finding_id": finding_id,
        "check_id": check_id,
        "edge": edge,
        "category": category,           # D-R02 六类之一
        "layer": layer,                 # inconsistency | conclusion_flip
        "flag_only": kw.get("flag_only", False),   # GRIM 判败只作旗标（RV-09）
        "claim_pointer": kw.get("claim_pointer"),
        "evidence_pointer": kw.get("evidence_pointer"),
        "raw": kw.get("raw"),
        "detail": kw.get("detail"),
        "at": kw.get("at") or today(),
    }


def adjudication_row(finding_id: str, outcome: str, adjudicator: str,
                     reason: str, **kw) -> dict:
    """findings.jsonl 追加行：人工裁决留痕（findings 本体永不改写）。"""
    return {
        "type": "adjudication",
        "finding_id": finding_id,
        "outcome": outcome,             # confirmed | overruled
        "adjudicator": adjudicator,
        "reason": reason,
        "at": kw.get("at") or today(),
    }


# ---------------------------------------------------------------- 领域门（Phase 2）

DOMAIN_LAYERS = ["universal", "journal_fact", "overlay"]
# 逐条判定：hit = 命中问题；miss = 未命中（通过）；not_applicable = 不适用/未触发
DOMAIN_RESULTS = ["hit", "miss", "not_applicable"]

# 条目来源四分（RV-16）：对象显式 / 对象推导 / 历史校准 / 通用质量，
# 另带 Explicit-or-Inferred 标记与置信度；通用条目不许伪装成按刊事实。
SOURCE_KINDS = ["explicit_object", "derived_object",
                "historical_calibration", "generic_quality"]
EXPLICITNESS = ["explicit", "inferred"]

# 条目执行层（RV-10 条目卡五元数据之一）：确定性代码 / 模型辅助
ITEM_TIERS = ["deterministic", "model_assisted"]

# 按刊事实时效（RV-17）：与 Write 模板记录的过期口径同构——缺省取
# 记录 H 组 review_cycle_days，再缺省 180 天；过期/无核查日期一律
# UNVERIFIED，过期事实不许驱动判定（结果强制 not_applicable）。
FACT_STATUSES = ["verified", "unverified"]
FACT_FRESHNESS_DEFAULT_DAYS = 180

# 覆盖层与核心冲突时的优先序（RV-16(c)：优先序必须写明）
OVERLAY_PRECEDENCE = ["overlay_wins", "core_wins"]

# 覆盖层机械检查种类（v1 只落这三种确定性检查）
OVERLAY_CHECK_KINDS = ["keyword_present", "keyword_absent", "section_present"]


def domain_check_row(item_id: str, layer: str, result: str, **kw) -> dict:
    """domain_gate.jsonl 一行：逐条判定 + 证据指针（RV-16/RV-17）。"""
    return {
        "type": "domain_check",
        "item_id": item_id,
        "layer": layer,                 # universal | journal_fact | overlay
        "axis": kw.get("axis"),
        "title": kw.get("title"),
        "severity_if_hit": kw.get("severity_if_hit"),
        "result": result,               # hit | miss | not_applicable
        "effective": kw.get("effective", True),   # 被覆盖层/核心 supersede 后为 False
        "superseded_by": kw.get("superseded_by"),
        "overrides": kw.get("overrides"),
        "evidence_pointer": kw.get("evidence_pointer"),
        "detail": kw.get("detail"),
        "source_kind": kw.get("source_kind"),
        "fact": kw.get("fact"),         # journal_fact 层：{field, value, verified_at, fact_status, record_pointer}
    }


def domain_summary_row(*, checked: int, hits: int, misses: int,
                       not_applicable: int, effective_hits: int,
                       by_layer: dict) -> dict:
    """domain_gate.jsonl 的覆盖自报行（RV-07 口径：机械汇总）。"""
    return {
        "type": "summary",
        "checked": checked,
        "hits": hits,
        "misses": misses,
        "not_applicable": not_applicable,
        "effective_hits": effective_hits,
        "by_layer": by_layer,
    }


# ---------------------------------------------------------------- 校准门（Phase 2）

# 决定建议档位：自最有利（ready）至最不利（reject_risk），rank 越大越不利。
# 封顶 max_favorable=BAND：结果不许比 BAND 更有利（rank 不许小于 BAND）；
# min_favorable=BAND：结果不许比 BAND 更不利（rank 不许大于 BAND）。
DECISION_BANDS = ["ready", "minor_revision", "major_revision", "reject_risk"]


def band_rank(band: str) -> int:
    return DECISION_BANDS.index(band)


# 封顶规则触发器（v1 三个机械可判触发器，RV-14）
CAP_TRIGGERS = ["open_confirmed_error", "unverified_facts_present",
                "clerical_only"]
CAP_EFFECT_KINDS = ["max_favorable", "min_favorable"]

# 校准门四件（R3/RV-14/RV-15）：缺一即判不齐，决定建议自动降级
CALIBRATION_PIECES = ["scale_anchor", "caps", "asymmetry", "bench_report"]

# ---------------------------------------------------------------- meta/决定（Phase 2）

DECISION_MODES = ["full", "degraded"]

# severity → 风险权重（meta 不对称合成的数值登记，calibration 可覆盖）
SEVERITY_WEIGHTS = {"minor": 1, "major": 2, "critical": 4}

# ---------------------------------------------------------------- 自审门（Phase 2，RV-13）

SELFCHECK_TESTS = ["vague_unsupported", "wrong_object", "praise_only",
                   "mere_restatement", "contradicts_frozen"]
SELFCHECK_RESULTS = ["pass", "fail"]

# ---------------------------------------------------------------- 回填清单（Phase 2，R6）

ACTION_CLASSES = ["fixable-in-text", "needs-new-evidence",
                  "needs-author-decision"]

# 回填条目字段白名单：Review 只出清单不出补丁——条目只许这些字段，
# 任何稿件正文改写段落无处安放（结构校验钉死，见 validate）。
HANDOFF_ITEM_FIELDS = ["concern_id", "severity", "statement",
                       "claim_pointer", "evidence_pointer",
                       "action_class", "action_basis",
                       "source_seats", "consensus", "close_criterion"]
HANDOFF_MAX_TEXT = 500     # 字符串字段长度上限：防正文段落偷渡


def new_consensus() -> dict:
    """consensus.yaml 骨架：共识与分歧账（RV-05/RV-11）。"""
    return {"concerns": []}


def concern_row(concern_id: str, statement: str, raised_by: list,
                severity_proposals: dict, **kw) -> dict:
    """一条 concern。severity 由代码计算（computed_severity），不许手填。

    corroboration_count 只记佐证数（排序/抽查优先级用），与 severity
    的计算严格分离——校验器按 proposals 重算并比对方可落字。
    """
    return {
        "concern_id": concern_id,
        "statement": statement,
        "raised_by": list(raised_by),
        "severity_proposals": dict(severity_proposals),
        "severity": computed_severity(severity_proposals),
        "tally": len(set(raised_by)),
        "corroboration_count": kw.get("corroboration_count",
                                      len(set(raised_by))),
        "consensus": kw.get("consensus", False),
        "consensus_basis": kw.get("consensus_basis"),  # {independent_seats, via_escalation}
        "close_criterion": kw.get("close_criterion"),
        "status": kw.get("status", "open"),            # open | closed
        "close_reason": kw.get("close_reason"),        # closed 必填（RV-11）
        "pointers": kw.get("pointers"),                # {claim_pointer, evidence_pointer}
    }
