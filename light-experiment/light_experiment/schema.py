"""执行包数据模型 + 确定性校验器。

权威源 = 结构化文件群（草案 §2）：
    executions/<exec_id>/
    ├── execution.yaml          登记头（承接、包级状态、预算总账）
    ├── runs/<run_id>/run.yaml  逐 run 记录（四区 + tags 注释区）
    ├── events.jsonl            轨迹事件日志（只增，见 events.py）
    ├── reconciliation.yaml     对账表占位（一期：行数与 registry 对齐；
    │                           实质回填在二期）
    └── EXECUTION_REPORT.md     渲染（摘要视图，非权威）

不对称可变性（约束 2）：
- 承接区 / 身份区：开跑即冻结——params 改动即哈希不符、identity 改动即
  身份重算不符，校验器逐项重算检出（改参数 = 新 run，不许原地改）；
- 观测区：只增（本期以事件日志的 run_started / run_finished 事件钉住
  params_hash / identity_hash / exit_status，结论区与事件对不上即报错——
  事件是防回改的锚）；
- 结论区：终态落字后不可改（reconciled 终态不可逆，状态历史校验兜底）；
- tags / note：唯一可变区。
"""

from __future__ import annotations

import re

from .events import validate_events
from .util import canonical_json, component_hash, sha256_text

# ---------- 状态与词表 ----------

PKG_STATES = ("intake", "sanity", "executing", "reconciling", "delivered", "blocked")
PKG_MAIN_STATES = ("intake", "sanity", "executing", "reconciling", "delivered")

RUN_STATES = ("planned", "running", "completed", "failed", "deviated", "reconciled")
RUN_TERMINAL_STATES = ("completed", "failed", "deviated", "reconciled")

# 终止分类词表（约束 4）：先分「怎么停的」，再谈「为什么」。
# 自由文本（如「执行失败」）不在词表内，校验器直接判不合格。
EXIT_STATUSES = (
    "completed",
    "failed_error",
    "failed_environment",
    "failed_data",
    "killed_budget",
    "killed_no_progress",
    "killed_external",
    "forfeited",
    "stuck",
    "context_exhausted",
)
FAILURE_EXITS = tuple(s for s in EXIT_STATUSES if s != "completed")

RUN_NEXT = {
    "planned": ("running",),
    "running": ("completed", "failed", "deviated"),
    # 二期：已终止的 run 被偏离闭包作废时先转 deviated 待处置，
    # 再以作废身份进 reconciled（草案 §2.6：作废不是删除）
    "completed": ("reconciled", "deviated"),
    "failed": ("reconciled", "deviated"),
    "deviated": ("reconciled",),
    "reconciled": (),
}

PKG_NEXT = {
    "intake": ("sanity",),
    "sanity": ("executing",),
    "executing": ("reconciling",),
    "reconciling": ("delivered",),
    "delivered": (),
    "blocked": PKG_MAIN_STATES[:-1],
}

RECONCILIATION_ROW_STATES = ("pending", "filled", "voided", "blocked")

# ---------- 二期词表（验收 / 偏离 / 失败 / 预算） ----------

# 基线复现验收（E1，草案 §5）：brief 中 role == baseline 的条目是验收
# 对象；结论拆三层叶子（实现 / 执行 / 结果），二值判定、按权重计分。
BASELINE_ROLE = "baseline"
ACCEPTANCE_LAYERS = ("implementation", "execution", "result")
ACCEPTANCE_LAYER_WEIGHTS = {"implementation": 1, "execution": 1, "result": 2}
ACCEPTANCE_VERDICTS = ("pass", "fail")
ACCEPTANCE_STATES = ("incomplete", "passed", "failed")
DEFAULT_ACCEPTANCE_THRESHOLD = 1.0   # 加权通过分须达此值（brief 可声明覆盖）
DEFAULT_RESULT_TOLERANCE_PCT = 2.0   # 结果层默认口径：主指标偏差 ≤2%（草案 §5）

# 偏离（E4，草案 §2.3）：type 是偏离的性质分类；trigger_dimension 是
# 出生证明逐维比对的触发维（Snakemake 五类触发器口径）。
DEVIATION_TYPES = ("config", "code", "data", "environment", "readout", "off_plan")
DEVIATION_DISPOSITIONS = ("continue_with_note", "void_and_rerun",
                          "stop_and_return_design", "accept_with_declaration")
# 五类触发器（Snakemake 口径）+ config：本工具出生证明把配置全文列为
# 独立一维，与 params（参数快照）分开比对，故 config 亦为一触发维。
TRIGGER_DIMENSIONS = ("code", "params", "input", "env", "data", "config")
# 触发维 → 出生证明/身份区的比对锚。口径写死：code 比代码快照维、
# params 比 params_hash、config 比配置维、env 比环境维；input（输入
# 文件）与 data（数据版本/划分）在本工具的出生证明里同属 data_version
# 维——输入文件版本即数据版本的一部分，两类触发器都比对该维。
TRIGGER_ANCHORS = {
    "code": ("birth", "code_snapshot"),
    "params": ("params_hash", None),
    "config": ("birth", "config"),
    "env": ("birth", "environment"),
    "input": ("birth", "data_version"),
    "data": ("birth", "data_version"),
}

# 失败分类（E5，草案 §2.4）：MAST 14 模式（Cemri 等，arXiv:2503.13657）
# 的执行域转译词表。FC2「agent 间错位」转译为执行者与设计书/子任务/
# 评审环节之间的信息错位（LEARNING 约束 11）。词表修订走留痕，不许静默改。
MAST_CODES = {
    "FM-1.1": {"fc": "FC1", "name": "不遵守任务规格",
               "translation": "未按 brief/设计书规格执行（取值、顺序、判读口径被改动或漏项）"},
    "FM-1.2": {"fc": "FC1", "name": "不遵守角色规格",
               "translation": "执行端越权做了设计/分析层的决策（改判读、改指标、放宽熔断）"},
    "FM-1.3": {"fc": "FC1", "name": "步骤重复",
               "translation": "同一动作/同一错误反复出现、无进展打转（熔断信号）"},
    "FM-1.4": {"fc": "FC1", "name": "对话历史丢失",
               "translation": "上下文/状态丢失后凭记忆续跑，轨迹与实际脱节"},
    "FM-1.5": {"fc": "FC1", "name": "不识别终止条件",
               "translation": "该停不停、到终止条件不收尾，或停在未定义状态"},
    "FM-2.1": {"fc": "FC2", "name": "对话重置",
               "translation": "与上游（Design/用户）已对齐的信息被重置丢失，重跑旧结论"},
    "FM-2.2": {"fc": "FC2", "name": "不请求澄清",
               "translation": "规格含糊不打回、带歧义硬跑，事后以解释代替登记"},
    "FM-2.3": {"fc": "FC2", "name": "任务跑偏",
               "translation": "实际执行目标偏离承接条目（跑的不是这一行登记的实验）"},
    "FM-2.4": {"fc": "FC2", "name": "信息扣留",
               "translation": "关键异常/偏离未上报未登记，下游在不知情下消费结果"},
    "FM-2.5": {"fc": "FC2", "name": "无视他人输入",
               "translation": "无视用户/评审的纠正输入，照旧执行已被指出的问题"},
    "FM-2.6": {"fc": "FC2", "name": "推理—行动不一致",
               "translation": "轨迹自述的计划/理由与实际动作脱节（说一套做一套）"},
    "FM-3.1": {"fc": "FC3", "name": "过早终止",
               "translation": "未达完成条件即收尾，自报完成但判读材料不齐"},
    "FM-3.2": {"fc": "FC3", "name": "无/不完整验证",
               "translation": "终止前未做核查或只做了部分核查（含干预生效未验）"},
    "FM-3.3": {"fc": "FC3", "name": "错误验证",
               "translation": "验证本身错误：假通过（表面检查放行）或假失败"},
}
FAILURE_CLASSES = ("implementation", "fundamental")
REFLUX_TARGETS = ("experiment", "design", "idea")
REFLUX_STATES = ("pending", "sent", "resolved")
# 失败预算制（草案 §6）：同签名（mast_code + root_cause）最多
# 2 次补丁 + 2 次干净重写，超限即报警停下报告，不许换姿势继续烧。
FAILURE_SIGNATURE_BUDGET = {"patch": 2, "rewrite": 2}
ATTEMPT_KINDS = ("patch", "rewrite")

# 对账 readout_actual 的分布摘要口径（草案 §2.5）：只收分布不收单点。
READOUT_DISTRIBUTION_KEYS = ("mean", "spread", "n", "replication_level")
READOUT_FORBIDDEN_KEYS = ("value", "point", "single", "single_value")
RESULT_FACT_VERDICTS = ("within", "outside", "incomparable")
# 随机源清单中「只换了种子」的判定词（Bouthillier 纪律，约束 12）
SEED_TOKENS = ("seed", "seeds", "random_seed", "random_seeds", "种子", "随机种子")

# 身份哈希的成分维度（草案 §2.7）：判定口径写死在此，变更走留痕。
IDENTITY_DIMENSIONS = ("config", "code_snapshot", "data_version", "environment")

# ---------- v1.1 词表（EXP-D04 占位符扫描 / EXP-D03 干预核验） ----------

# 零占位符扫描的模式清单（EXP-D04，草案 §4）：清单成文冻结在此，
# intake 对四件套原文逐行机械扫；修订清单走留痕（改本常量 + SKILL
# 同步），不许静默增删。每项 = (模式名, 正则)。
PLACEHOLDER_PATTERNS = (
    ("双花括号模板位", re.compile(r"\{\{[^{}]*\}\}")),
    ("尖括号占位记号", re.compile(r"<[A-Za-z_][A-Za-z0-9_]*>")),
    ("TODO 标记", re.compile(r"\bTODO\b")),
    ("TBD 标记", re.compile(r"\bTBD\b")),
    ("FIXME 标记", re.compile(r"\bFIXME\b")),
    ("XXX 占位", re.compile(r"\bX{3,}\b")),
    ("待填/待补标记", re.compile(r"待填|待补")),
    ("占位符字样", re.compile(r"占位符")),
    ("下划线填空", re.compile(r"_{4,}")),
    ("Lorem ipsum", re.compile(r"lorem ipsum", re.IGNORECASE)),
)

# 干预核查点机械核验（EXP-D03）：三类核验器——数值/标量相等、区间
# 内、文件哈希一致。实际值只许从来源文件机械读取，不收执行者自述。
INTERVENTION_VERIFY_KINDS = ("equals", "range", "file_hash")
# 逐条核验结论：pass 通过 / fail 不符 / unverifiable 登记了核验方式
# 但实际值机械取不到 / not_verified 未登记核验方式（v1.0 存档形态，
# 如实报未核验，不冒充已验）。
INTERVENTION_RESULT_STATES = ("pass", "fail", "unverifiable", "not_verified")
# run 级核验总判（优先级 failed > unverifiable > passed >
# not_verified > no_checks）。
INTERVENTION_VERDICTS = ("passed", "failed", "unverifiable",
                         "not_verified", "no_checks")
# 核验不符时阻断静默通过的总判集合：completed 终止遇之自动转
# deviated 候选（失败类终止本就不被消费，保留原状态只落记录）。
INTERVENTION_BLOCKING_VERDICTS = ("failed", "unverifiable")

SEED_DERIVATION_RULE = (
    "derived_seed = int(sha256(f'{root_seed}|{run_id}'.encode()).hexdigest()[:8], 16)"
)


def _nonempty_str(v) -> bool:
    return isinstance(v, str) and bool(v.strip())


def _present(v) -> bool:
    """字段「在场且非空」：字符串非空、映射/列表非空、其余非 None。"""
    if v is None:
        return False
    if isinstance(v, str):
        return bool(v.strip())
    if isinstance(v, (dict, list)):
        return len(v) > 0
    return True


# ---------- 哈希与种子 ----------

def compute_params_hash(params) -> str:
    return component_hash(params or {})


def identity_payload(identity: dict) -> dict:
    """身份哈希的输入展开（草案 §2.7）：
    最终配置全文 + 代码快照哈希 + 数据版本 + 环境声明。"""
    code = identity.get("code_snapshot") or {}
    return {
        "config": identity.get("config"),
        "code_snapshot_hash": code.get("hash"),
        "data_version": identity.get("data_version"),
        "environment": identity.get("environment"),
    }


def compute_identity_hash(identity: dict) -> str:
    return sha256_text(canonical_json(identity_payload(identity)))


def birth_components(identity: dict) -> dict:
    """出生证明的逐维成分哈希（偏离作废时逐维比对的锚，草案 §2.7）。"""
    code = identity.get("code_snapshot") or {}
    return {
        "config": component_hash(identity.get("config")),
        "code_snapshot": sha256_text(str(code.get("hash") or "")),
        "data_version": component_hash(identity.get("data_version")),
        "environment": component_hash(identity.get("environment")),
    }


def build_birth_certificate(identity: dict, issued_at: str) -> dict:
    return {
        "issued_at": issued_at,
        "identity_hash": identity.get("identity_hash"),
        "components": birth_components(identity),
    }


def derive_seed(root_seed, run_id: str) -> int:
    """根种子确定性派生本 run 的种子（规则见 SEED_DERIVATION_RULE）。"""
    digest = sha256_text(f"{root_seed}|{run_id}")
    return int(digest[:8], 16)


# ---------- 空结构工厂 ----------

def empty_execution(exec_id: str, date: str) -> dict:
    return {
        "exec_id": exec_id,
        "design_ref": {"design_id": "", "content_hash": "", "frozen_content_hash": "",
                       "amendments": 0, "export_dir": ""},
        "status": "intake",
        "created": date,
        "updated": date,
        "backend": None,  # 执行后端预留（拍板 ①：v1 规程执行，v2 可接运行器）
        "identity_dimensions": list(IDENTITY_DIMENSIONS),
        "budget_ledger": {
            "limits": {"wall_clock_s": None, "gpu_hours": None, "api_cost": None},
            "spent": {"wall_clock_s": 0, "gpu_hours": 0, "api_cost": 0},
            "design_budget": {},
            "circuit_breakers": [],
        },
        "intake_report": {"checked_at": "", "source_dir": "", "gaps": [],
                          "registry_run_ids": []},
        "brief_runs": [],
        "registry_lines": [],
        "block_record": None,
        "status_history": [{"from": None, "to": "intake", "date": date,
                            "by": "light-experiment intake", "note": "承接建包"}],
    }


def empty_run(run_id: str, design_run_id: str, attempt: int, design_ref: dict,
              brief_row: dict, registry_line: dict, date: str) -> dict:
    return {
        "run_id": run_id,
        "design_run_id": design_run_id,
        "attempt": attempt,
        "status": "planned",
        "created": date,
        "updated": date,
        # 承接区（冻结）
        "intake": {
            "design_ref": {"design_id": design_ref.get("design_id"),
                           "content_hash": design_ref.get("content_hash")},
            "brief_row": brief_row,
            "registry_line": registry_line,
            "depends_on": list((brief_row or {}).get("depends_on") or []),
        },
        # 身份区（run-start 时定型冻结）
        "identity": {
            "config": {},
            "code_snapshot": {"hash": "", "git_commit": "", "git_dirty": None,
                              "snapshot_ref": ""},
            "data_version": {},
            "environment": {},
            "seeds": {"root_seed": None, "derivation": SEED_DERIVATION_RULE,
                      "derived_seed": None},
            "params": {},
            "params_hash": "",
            "identity_hash": "",
            "birth_certificate": None,
            "intervention_checks": [],
            "lineage": {"origin_run": None, "retry_of": None,
                        "parent_run": None, "reused_segments": []},
            "backend": None,  # 执行后端预留（拍板 ①）
        },
        # 观测区（只增）
        "observation": {
            "timeline": {"queued_at": date, "started_at": "", "ended_at": ""},
            "attempts_budget": {"attempts_used": 0, "retries": 0,
                                "wall_clock_s": 0, "gpu_hours": 0, "api_cost": 0},
            "metrics_ref": None,
            "artifacts": [],
        },
        # 结论区（终态落字后不可改；对账指针除外）
        "conclusion": {
            "exit_status": None,
            "exit_detail": "",
            "failure_ref": None,
            "salvage": [],
            "salvage_note": "",
            "reconciliation": {"row": design_run_id, "filled": False,
                               "voided_by": None},
        },
        # 注释区（唯一可变区）
        "tags": [],
        "note": "",
        "status_history": [{"from": None, "to": "planned", "date": date,
                            "by": "light-experiment run-new", "note": "承接建 run"}],
    }


# ---------- 身份下限（Sacred 对表，约束 1） ----------

def identity_minimum_errors(run: dict) -> list[str]:
    """开跑前的身份字段下限清单：配置全文 / 根种子+派生规则 / 代码快照
    哈希 / 数据版本 / 环境声明。缺哪项点名哪项（草案 §2.1 字段下限）。"""
    errs: list[str] = []
    ident = run.get("identity") or {}
    rid = run.get("run_id")
    if not _present(ident.get("config")):
        errs.append(f"{rid} 身份下限缺失：最终配置全文 config 为空")
    seeds = ident.get("seeds") or {}
    if seeds.get("root_seed") is None:
        errs.append(f"{rid} 身份下限缺失：根种子 seeds.root_seed 未登记"
                    "（种子不许临场现编，约束 1）")
    if not _nonempty_str(seeds.get("derivation")):
        errs.append(f"{rid} 身份下限缺失：种子派生规则 seeds.derivation 未登记")
    code = ident.get("code_snapshot") or {}
    if not _nonempty_str(code.get("hash")):
        errs.append(f"{rid} 身份下限缺失：代码快照哈希 code_snapshot.hash 为空")
    if not _present(ident.get("data_version")):
        errs.append(f"{rid} 身份下限缺失：数据版本 data_version 未登记")
    env = ident.get("environment")
    env_ok = _nonempty_str(env) or (
        isinstance(env, dict) and _nonempty_str(env.get("declaration")))
    if not env_ok:
        errs.append(f"{rid} 身份下限缺失：环境声明 environment.declaration 为空")
    return errs


# ---------- 校验器 ----------

def _history_errors(history, next_map, label: str, *, blocked_ok: bool = False) -> list[str]:
    """状态历史合法性：每次跃迁必须在状态机内；终态后不许再有跃迁
    （终态不可逆的留痕侧校验，约束 2）。"""
    errs: list[str] = []
    hist = [h for h in (history or []) if isinstance(h, dict)]
    for prev, cur in zip(hist, hist[1:]):
        frm, to = prev.get("to"), cur.get("to")
        if cur.get("from") != frm:
            errs.append(f"{label} 状态历史断裂：{cur.get('from')} → {to} 的前态"
                        f"与上一条落字 {frm} 对不上")
            continue
        if blocked_ok and to == "blocked" and frm != "delivered":
            continue
        if blocked_ok and frm == "blocked" and to in PKG_MAIN_STATES:
            continue
        if to not in next_map.get(frm, ()):
            errs.append(f"{label} 状态历史含非法跃迁：{frm} → {to}"
                        "（终态不可逆，改状态只能按状态机走）")
    return errs


def _validate_run(run: dict, pkg: dict) -> list[str]:
    errs: list[str] = []
    execution = pkg["execution"]
    runs = pkg["runs"]
    events = pkg["events"]
    rid = run.get("run_id")
    label = f"run {rid}"
    if not _nonempty_str(rid):
        return ["run 缺 run_id"]
    for zone in ("intake", "identity", "observation", "conclusion"):
        if not isinstance(run.get(zone), dict):
            errs.append(f"{label} 缺区：{zone}（四区结构不全）")
            return errs

    # —— 承接区：与执行包登记头对齐 ——
    intake = run["intake"]
    dref = intake.get("design_ref") or {}
    edref = execution.get("design_ref") or {}
    if dref.get("design_id") != edref.get("design_id") or \
            dref.get("content_hash") != edref.get("content_hash"):
        errs.append(f"{label} 承接区 design_ref 与执行包登记头不一致"
                    "（run 承接的设计版本与包不是同一冻结版）")
    if not _present(intake.get("brief_row")):
        errs.append(f"{label} 承接区 brief_row 快照缺失（照单执行的『单』不在）")
    reg = intake.get("registry_line") or {}
    if reg.get("run_id") != run.get("design_run_id"):
        errs.append(f"{label} 预期登记行指针错位：registry_line.run_id="
                    f"{reg.get('run_id')!r} ≠ design_run_id={run.get('design_run_id')!r}")
    if reg.get("content_hash") != edref.get("content_hash"):
        errs.append(f"{label} 预期登记行 content_hash 与冻结哈希不一致")
    brief_ids = {b.get("run_id") for b in execution.get("brief_runs") or []
                 if isinstance(b, dict)}
    for dep in intake.get("depends_on") or []:
        if brief_ids and dep not in brief_ids:
            errs.append(f"{label} 依赖的 {dep} 不在 brief 运行清单内")

    status = run.get("status")
    if status not in RUN_STATES:
        errs.append(f"{label} 状态非法：{status!r}")
        return errs
    errs.extend(_history_errors(run.get("status_history"), RUN_NEXT, label))

    ident = run["identity"]
    obs = run["observation"]
    conc = run["conclusion"]

    # —— 身份区：已开跑的 run 必须过下限 + 哈希可重算（冻结验真） ——
    if status != "planned":
        errs.extend(identity_minimum_errors(run))
        if compute_params_hash(ident.get("params")) != ident.get("params_hash"):
            errs.append(f"{label} params 已被改动：重算哈希与开跑时锁定的 "
                        "params_hash 不符（改参数 = 新 run，不许原地改，约束 2）")
        if compute_identity_hash(ident) != ident.get("identity_hash"):
            errs.append(f"{label} 身份已被改动：重算 identity_hash 与出生证明"
                        "不一致（身份成分任一维变化即新身份，草案 §2.7）")
        bc = ident.get("birth_certificate") or {}
        if bc.get("identity_hash") != ident.get("identity_hash"):
            errs.append(f"{label} 出生证明 identity_hash 与身份区不一致")
        if bc.get("components") != birth_components(ident):
            errs.append(f"{label} 出生证明逐维成分哈希与实填成分重算不一致")
        seeds = ident.get("seeds") or {}
        if seeds.get("root_seed") is not None and \
                seeds.get("derived_seed") != derive_seed(seeds["root_seed"], rid):
            errs.append(f"{label} 派生种子与根种子+派生规则重算不一致")

    # —— 血缘：复用段必须带被复用 run 的身份哈希作证据（拍板 ②） ——
    lineage = ident.get("lineage") or {}
    for key in ("origin_run", "retry_of", "parent_run"):
        ref = lineage.get(key)
        if ref is not None and ref not in runs:
            errs.append(f"{label} 血缘指针 lineage.{key}={ref!r} 指向不存在的 run")
    for seg in lineage.get("reused_segments") or []:
        if not isinstance(seg, dict):
            errs.append(f"{label} 复用段登记不是对象：{seg!r}")
            continue
        src = runs.get(seg.get("from_run"))
        if src is None:
            errs.append(f"{label} 复用段来源 run 不存在：{seg.get('from_run')!r}")
        elif seg.get("identity_hash") != (src.get("identity") or {}).get("identity_hash"):
            errs.append(f"{label} 复用段缺内容哈希证据：登记的 identity_hash 与"
                        f"来源 run {seg.get('from_run')} 的实际身份哈希不符"
                        "（复用判据须为内容哈希，禁同名复用，拍板 ②）")
        if seg.get("from_run") == rid:
            errs.append(f"{label} 复用段指向自身（血缘不许自指）")

    # —— 结论区：终止分类词表 + 与事件锚对账（防回改） ——
    if status in RUN_TERMINAL_STATES:
        es = conc.get("exit_status")
        if es not in EXIT_STATUSES:
            errs.append(f"{label} exit_status={es!r} 不在终止分类词表内"
                        "（只写「执行失败」式自由文本视为留痕不合格，约束 4）")
        if status == "completed" and es != "completed":
            errs.append(f"{label} 状态 completed 但 exit_status={es!r}")
        if status == "failed" and es not in FAILURE_EXITS:
            errs.append(f"{label} 状态 failed 但 exit_status={es!r} 非失败类终止")
        if not _nonempty_str((obs.get("timeline") or {}).get("ended_at")):
            errs.append(f"{label} 已终止但 timeline.ended_at 未落字")
        if status == "failed":
            salvage = conc.get("salvage") or []
            if not salvage and not _nonempty_str(conc.get("salvage_note")):
                errs.append(f"{label} 失败 run 未登记抢救产物，也未写明无可抢救"
                            "（失败先抢救留产物，约束 4）")
        finished = [e for e in events if e.get("type") == "run_finished"
                    and e.get("run_id") == rid]
        if finished:
            anchor = finished[-1].get("payload") or {}
            if anchor.get("exit_status") != es:
                errs.append(f"{label} 结论区 exit_status 与 run_finished 事件"
                            "锚记录不一致（结论区终态后回改即在此暴露）")
    if status != "planned":
        started = [e for e in events if e.get("type") == "run_started"
                   and e.get("run_id") == rid]
        if started:
            anchor = started[-1].get("payload") or {}
            if anchor.get("params_hash") != ident.get("params_hash"):
                errs.append(f"{label} params_hash 与 run_started 事件锚不一致")
            if anchor.get("identity_hash") != ident.get("identity_hash"):
                errs.append(f"{label} identity_hash 与 run_started 事件锚不一致")
            # 冷启动标记同样钉在事件锚上：验收证据只认锚（见 _cold_start_ok）
            if bool(anchor.get("cold_start")) != bool(ident.get("cold_start")):
                errs.append(f"{label} 冷启动标记 cold_start 与 run_started "
                            "事件锚不一致（验收证据的真伪靠此锚，不许事后回填）")

    # —— 干预核验记录（EXP-D03）：终态 run 的核验结论与事件锚对账 ——
    checks = ident.get("intervention_checks") or []
    ver = conc.get("intervention_verification")
    if status in RUN_TERMINAL_STATES:
        if ver is None and any(isinstance(c, dict) and c.get("verify")
                               for c in checks):
            errs.append(f"{label} 登记了带核验方式的干预核查点，但结论区缺 "
                        "intervention_verification 核验记录（run-finish 时"
                        "应机械核验并落字，缺记录即未验）")
        if isinstance(ver, dict):
            results = ver.get("results") or []
            if len(results) != len(checks):
                errs.append(f"{label} 干预核验记录 {len(results)} 条与登记的"
                            f"核查点 {len(checks)} 条不一一对应")
            bad = [r for r in results
                   if isinstance(r, dict) and
                   r.get("status") in ("fail", "unverifiable")]
            if bad and conc.get("exit_status") == "completed" and \
                    status != "deviated":
                names = "、".join(str(r.get("point")) for r in bad)
                errs.append(f"{label} 干预核验不符（{names}）却落 "
                            f"{status} 未转 deviated 候选：核验不符不许"
                            "静默通过（EXP-D03）")
            check_events = [e for e in events
                            if e.get("type") == "intervention_check"
                            and e.get("run_id") == rid]
            if check_events:
                ev_pairs = sorted(
                    (str((e.get("payload") or {}).get("point")),
                     str((e.get("payload") or {}).get("status")))
                    for e in check_events)
                rec_pairs = sorted(
                    (str(r.get("point")), str(r.get("status")))
                    for r in results if isinstance(r, dict))
                if ev_pairs != rec_pairs:
                    errs.append(f"{label} 干预核验结论与 intervention_check "
                                "事件锚不一致（结论区核验记录终态后回改即"
                                "在此暴露）")

    # —— 对账指针 ——
    recon = pkg.get("reconciliation")
    if isinstance(recon, dict):
        row_ids = {r.get("registry_run_id") for r in recon.get("rows") or []
                   if isinstance(r, dict)}
        row = (conc.get("reconciliation") or {}).get("row")
        if row is not None and row not in row_ids:
            errs.append(f"{label} 对账指针 row={row!r} 不在对账表行内")
    return errs


# ---------- 二期纯函数（验收 / 偏离 / 失败 / 对账 / 预算） ----------

def placeholder_hits(text: str, *, limit: int = 3) -> list[dict]:
    """零占位符扫描（EXP-D04）：对交接件原文逐行扫冻结模式清单，
    返回命中 [{pattern, line, excerpt}]（每文件至多 limit 条，
    防打回清单被同一模式刷屏）。"""
    hits: list[dict] = []
    for lineno, line in enumerate(text.splitlines(), 1):
        for label, pat in PLACEHOLDER_PATTERNS:
            m = pat.search(line)
            if m:
                hits.append({"pattern": label, "line": lineno,
                             "excerpt": line.strip()[:80]})
                break
        if len(hits) >= limit:
            break
    return hits


def trigger_anchor(run: dict, dimension: str) -> str | None:
    """取 run 在某触发维上的比对锚（出生证明成分哈希 / params_hash）。
    run 未开跑（无出生证明）→ None（该维无从比对，不参与锚匹配）。"""
    kind, key = TRIGGER_ANCHORS[dimension]
    ident = run.get("identity") or {}
    if kind == "params_hash":
        return ident.get("params_hash") or None
    bc = ident.get("birth_certificate") or {}
    return (bc.get("components") or {}).get(key)


def cold_start_ok(pkg: dict, run_id: str) -> bool:
    """run 是否为可作验收证据的冷启动重跑：run 存在 + run_started 事件
    锚 cold_start=true（事后改 run.yaml 冒充冷启动，锚对不上即露馅）。"""
    run = (pkg.get("runs") or {}).get(run_id)
    if run is None:
        return False
    started = [e for e in pkg.get("events") or []
               if e.get("type") == "run_started" and e.get("run_id") == run_id]
    if not started:
        return False
    return bool((started[-1].get("payload") or {}).get("cold_start"))


def run_voided_by(run: dict) -> list[str]:
    """run 的作废标记（conclusion.reconciliation.voided_by：一期为单值
    字符串，二期起可为列表——读时统一成列表）。"""
    v = ((run.get("conclusion") or {}).get("reconciliation") or {}).get("voided_by")
    if not v:
        return []
    return list(v) if isinstance(v, list) else [v]


def bias_warnings(random_sources: dict) -> list[str]:
    """随机源清单的有偏估计警告（约束 12，Bouthillier 口径）：
    只重新随机化了种子、却冻结了其他随机源（尤其超参）时，
    「冻结超参换种子重跑」是有偏估计——自动标注，不靠人自觉。"""
    warns: list[str] = []
    if not isinstance(random_sources, dict):
        return warns
    rerand = [str(x).strip().lower() for x in random_sources.get("rerandomized") or []]
    frozen = [str(x) for x in random_sources.get("frozen") or []]
    seed_only = bool(rerand) and all(
        any(tok in item for tok in SEED_TOKENS) for item in rerand)
    if seed_only and frozen:
        warns.append("有偏估计警告：本行只重新随机化了种子、其余随机源被冻结"
                     f"（{frozen}）——冻结超参换种子重跑是有偏估计，"
                     "误差不随重跑次数消失（约束 12）")
    if random_sources.get("hyperparameters_frozen"):
        warns.append("有偏估计警告：登记声明超参被冻结（hyperparameters_frozen）"
                     "——分布摘要只刻画种子方差，不含调参方差（约束 12）")
    return warns


def readout_distribution_errors(readout, label: str) -> list[str]:
    """readout_actual 的分布口径校验：只收分布摘要、拒绝单点（约束 12）。"""
    errs: list[str] = []
    if not isinstance(readout, dict):
        return [f"{label} readout_actual 不是分布摘要对象：{readout!r}"
                "（对账只收分布 {mean, spread, n, replication_level}，不收单点）"]
    for key in READOUT_FORBIDDEN_KEYS:
        if key in readout:
            errs.append(f"{label} readout_actual 含单点键 {key!r}：对账不许单点读数")
    for key in READOUT_DISTRIBUTION_KEYS:
        if key not in readout:
            errs.append(f"{label} readout_actual 缺分布字段 {key}")
    for key in ("mean", "spread"):
        v = readout.get(key)
        if key in readout and not isinstance(v, (int, float)):
            errs.append(f"{label} readout_actual.{key} 须为数值，当前 {v!r}")
    n = readout.get("n")
    if "n" in readout:
        if not isinstance(n, int) or isinstance(n, bool):
            errs.append(f"{label} readout_actual.n 须为整数，当前 {n!r}")
        elif n < 2:
            errs.append(f"{label} readout_actual.n={n}：样本量 <2 的「分布」"
                        "实为单点，不许冒充分布摘要")
    if "replication_level" in readout and \
            not _nonempty_str(readout.get("replication_level")):
        errs.append(f"{label} readout_actual.replication_level 为空"
                    "（重复层级必须落字：哪一层被独立随机化，n 就是哪一层）")
    return errs


def reconciliation_problems(pkg: dict, *, pending_blocks: bool) -> list[str]:
    """对账逐行清零检查（reconcile check 与 delivered 门共用口径）：
    缺行 / blocked / 作废未替代 / 已回填但形状不合法恒为问题；
    pending 行仅当 pending_blocks 时算问题（delivered 门只对已进入
    实质对账的包要求逐行清零，见 gates 的口径注记）。"""
    errs: list[str] = []
    execution = pkg.get("execution") or {}
    runs = pkg.get("runs") or {}
    recon = pkg.get("reconciliation")
    registry_ids = (execution.get("intake_report") or {}).get("registry_run_ids") or []
    if not isinstance(recon, dict):
        return ["对账表缺失（reconciliation.yaml 不存在）"]
    rows = recon.get("rows") or []
    row_by_id = {r.get("registry_run_id"): r for r in rows if isinstance(r, dict)}
    for rid in registry_ids:
        if rid not in row_by_id:
            errs.append(f"对账缺行：登记行 {rid} 在对账表中不存在")
    for row in rows:
        if not isinstance(row, dict):
            continue
        rid = row.get("registry_run_id")
        label = f"对账行 {rid}"
        st = row.get("status")
        if st == "blocked":
            errs.append(f"{label} 处于 blocked（回填受阻未解，不算清零）")
        elif st == "pending" and pending_blocks:
            errs.append(f"{label} 尚未回填（pending，未清零）")
        elif st == "voided":
            live = [u for u in row.get("run_ids") or []
                    if u in runs and not run_voided_by(runs[u])]
            if not live:
                errs.append(f"{label} 已作废且无替代 run（作废未替代，不算清零）")
            else:
                errs.append(f"{label} 已有替代 run {live} 但行状态仍是 voided"
                            "（须以替代 run 的事实重新回填）")
        elif st == "filled":
            errs.extend(readout_distribution_errors(row.get("readout_actual"), label))
            layers = row.get("layers") or {}
            rf = layers.get("result_fact") or {}
            if rf.get("verdict") not in RESULT_FACT_VERDICTS:
                errs.append(f"{label} layers.result_fact.verdict 非法："
                            f"{rf.get('verdict')!r}")
            if not isinstance(row.get("random_sources"), dict):
                errs.append(f"{label} 已回填但缺 random_sources 随机源清单")
    return errs


def result_leaf_tolerance_problem(leaf: dict, tolerance_pct) -> str | None:
    """结果叶判 pass 的容差口径（草案 §5 闸门）：主指标偏差超容差且
    偏差绝对值不在报告方差内 → 返回问题描述，否则 None。validate /
    record_leaf / advance 门共用此单一口径（D-EXP-1：三处同判，
    不许只有事后校验认、登记与推进不认）。"""
    if leaf.get("layer") != "result" or leaf.get("verdict") != "pass":
        return None
    dev = leaf.get("deviation_pct")
    if not isinstance(dev, (int, float)):
        return None
    tol = tolerance_pct if isinstance(tolerance_pct, (int, float)) \
        else DEFAULT_RESULT_TOLERANCE_PCT
    var = leaf.get("reported_variance")
    within_var = isinstance(var, (int, float)) and \
        isinstance(leaf.get("deviation_abs"), (int, float)) and \
        leaf["deviation_abs"] <= var
    if dev > tol and not within_var:
        return (f"主指标偏差 {dev}% 超过容差 {tol}% 且不在报告方差内"
                "（草案 §5 闸门口径）")
    return None


def _validate_acceptance(pkg: dict) -> list[str]:
    errs: list[str] = []
    acc = pkg.get("acceptance")
    if not isinstance(acc, dict):
        return errs
    runs = pkg.get("runs") or {}
    leaves = acc.get("leaves") or []
    defs = [{k: leaf.get(k) for k in ("leaf_id", "run_id", "layer", "claim", "weight")}
            for leaf in leaves if isinstance(leaf, dict)]
    if component_hash(defs) != acc.get("leaves_hash"):
        errs.append("验收表叶子定义与生成时的 leaves_hash 不符"
                    "（验收表生成后冻结：改叶子走偏离登记，不许原地改表）")
    total_w = 0.0
    pass_w = 0.0
    all_recorded = True
    for leaf in leaves:
        if not isinstance(leaf, dict):
            errs.append("验收表叶子不是对象")
            continue
        lid = leaf.get("leaf_id")
        total_w += leaf.get("weight") or 0
        verdict = leaf.get("verdict")
        if verdict is None:
            all_recorded = False
            continue
        if verdict not in ACCEPTANCE_VERDICTS:
            errs.append(f"验收叶 {lid} 判定非法：{verdict!r}")
            continue
        if verdict == "pass":
            pass_w += leaf.get("weight") or 0
        ev_run_id = leaf.get("evidence_run")
        ev_run = runs.get(ev_run_id)
        if ev_run is None:
            errs.append(f"验收叶 {lid} 的证据 run 不存在：{ev_run_id!r}"
                        "（验收证据必须指向冷启动重跑产物登记）")
        else:
            if ev_run.get("design_run_id") != leaf.get("run_id"):
                errs.append(f"验收叶 {lid} 的证据 run {ev_run_id} 不是条目 "
                            f"{leaf.get('run_id')} 的尝试（张冠李戴不作数）")
            if not cold_start_ok(pkg, ev_run_id):
                errs.append(f"验收叶 {lid} 的证据 run {ev_run_id} 无冷启动标记"
                            "（执行期产物冒充验收证据被拒：证据只认干净环境"
                            "冷启动重跑，拍板 ③）")
        prob = result_leaf_tolerance_problem(leaf, acc.get("tolerance_pct"))
        if prob:
            errs.append(f"验收叶 {lid} 判 pass 但{prob}")
    score = (pass_w / total_w) if total_w else 0.0
    threshold = acc.get("threshold")
    threshold = threshold if isinstance(threshold, (int, float)) \
        else DEFAULT_ACCEPTANCE_THRESHOLD
    want = "passed" if (all_recorded and score >= threshold) else \
        ("failed" if all_recorded else "incomplete")
    if acc.get("verdict") != want:
        errs.append(f"验收结论落字 {acc.get('verdict')!r} 与逐叶重算 {want!r} 不符"
                    f"（score={score:.3f}，threshold={threshold}）")
    return errs


def _validate_deviations(pkg: dict) -> list[str]:
    errs: list[str] = []
    runs = pkg.get("runs") or {}
    for dev in pkg.get("deviations") or []:
        did = dev.get("deviation_id")
        label = f"偏离 {did}"
        if dev.get("type") not in DEVIATION_TYPES:
            errs.append(f"{label} type 非法：{dev.get('type')!r}")
        if dev.get("disposition") not in DEVIATION_DISPOSITIONS:
            errs.append(f"{label} disposition 非法：{dev.get('disposition')!r}")
        dim = dev.get("trigger_dimension")
        if dim is not None and dim not in TRIGGER_DIMENSIONS:
            errs.append(f"{label} trigger_dimension 非法：{dim!r}")
        for rid in dev.get("affected_runs_declared") or []:
            if rid not in runs:
                errs.append(f"{label} 人工估计影响集含不存在的 run：{rid}")
        applied = dev.get("applied")
        if applied:
            if not dev.get("published"):
                errs.append(f"{label} 未经公示（publish）即已生效（apply）："
                            "生效清单先公示后作废，不许先斩后奏")
            for rid in applied.get("invalidated") or []:
                if rid not in runs:
                    errs.append(f"{label} 作废集含不存在的 run：{rid}")
                elif did not in run_voided_by(runs[rid]):
                    errs.append(f"{label} 声称已作废 {rid}，但该 run 的 "
                                "voided_by 未落字（作废标记只追加，须与登记互验）")
        for ov in dev.get("overrides") or []:
            if not _nonempty_str(ov.get("by")) or not _nonempty_str(ov.get("reason")):
                errs.append(f"{label} 覆写缺覆写者或理由（覆写必须显式登记，"
                            "且报告中标红提示溯源代价）")
    return errs


def _validate_failures(pkg: dict) -> list[str]:
    errs: list[str] = []
    runs = pkg.get("runs") or {}
    failures = pkg.get("failures") or []
    counts: dict[tuple, dict[str, int]] = {}
    for f in failures:
        fid = f.get("failure_id")
        label = f"失败 {fid}"
        run = runs.get(f.get("run_id"))
        if run is None:
            errs.append(f"{label} 指向不存在的 run：{f.get('run_id')!r}")
        else:
            if (run.get("conclusion") or {}).get("failure_ref") != fid:
                errs.append(f"{label} 与 run {f.get('run_id')} 的 failure_ref "
                            "指针不一致（分类落定须回写 run 结论区指针）")
            if f.get("exit_status") != (run.get("conclusion") or {}).get("exit_status"):
                errs.append(f"{label} exit_status 与 run 结论区不一致")
        if f.get("mast_code") not in MAST_CODES:
            errs.append(f"{label} mast_code 不在 MAST 转译词表内："
                        f"{f.get('mast_code')!r}（只写「执行失败」视为未分类）")
        fc = f.get("failure_class")
        if fc not in FAILURE_CLASSES:
            errs.append(f"{label} failure_class 非法：{fc!r}")
        elif fc == "fundamental":
            if not _nonempty_str(f.get("root_cause")) or \
                    not _nonempty_str(f.get("boundary_conditions")):
                errs.append(f"{label} fundamental 必须附 root_cause + "
                            "boundary_conditions（与 Idea 杀卡同规则）")
        elif fc == "implementation":
            if not _nonempty_str(f.get("retry_guidance")):
                errs.append(f"{label} implementation 必须附 retry_guidance"
                            "（与 Idea 杀卡同规则）")
        if f.get("reflux_target") not in REFLUX_TARGETS:
            errs.append(f"{label} reflux_target 非法：{f.get('reflux_target')!r}")
        if f.get("reflux_status") not in REFLUX_STATES:
            errs.append(f"{label} reflux_status 非法：{f.get('reflux_status')!r}")
        kind = f.get("attempt_kind")
        if kind in ATTEMPT_KINDS:
            sig = (f.get("mast_code"), (f.get("root_cause") or "").strip())
            counts.setdefault(sig, {"patch": 0, "rewrite": 0})[kind] += 1
    for (mast, root), c in counts.items():
        for kind, limit in FAILURE_SIGNATURE_BUDGET.items():
            if c[kind] > limit:
                errs.append(f"失败签名预算超限报警：签名（{mast} + root_cause"
                            f"「{root}」）的 {kind} 失败已达 {c[kind]} 次，"
                            f"超过预算 {limit} 次——停下报告「计划或环境错了」，"
                            "不许换个姿势继续烧（草案 §6）")
    return errs


def _validate_budget(pkg: dict) -> list[str]:
    """熔断线防放宽（拍板 ⑤：只许停不许改）：ledger.limits 若被执行端
    抬高到 Design 熔断线之上，校验器直接点名；快照以承接时的
    circuit_breakers 为准，不许执行端自改口径。"""
    errs: list[str] = []
    execution = pkg.get("execution") or {}
    ledger = execution.get("budget_ledger") or {}
    limits = ledger.get("limits") or {}
    for cb in ledger.get("circuit_breakers") or []:
        if not isinstance(cb, dict):
            continue
        metric, threshold = cb.get("metric"), cb.get("threshold")
        if metric in ("wall_clock_s", "gpu_hours", "api_cost") and \
                isinstance(threshold, (int, float)):
            cur = limits.get(metric)
            if isinstance(cur, (int, float)) and cur > threshold:
                errs.append(f"熔断线被执行端放宽：budget_ledger.limits.{metric}"
                            f"={cur} 高于 Design 熔断线 {threshold}"
                            "（只许停不许改；上调只能回 Design 走 amendment，拍板 ⑤）")
    return errs


def validate_package(pkg: dict) -> list[str]:
    """执行包全量确定性校验。pkg 由 project.load_package 组装：
    {execution, runs{run_id: run}, events, event_errors, reconciliation}。"""
    errs: list[str] = []
    execution = pkg.get("execution") or {}
    runs = pkg.get("runs") or {}
    events = pkg.get("events") or []

    # —— 登记头 ——
    if not _nonempty_str(execution.get("exec_id")):
        errs.append("execution.yaml 缺 exec_id")
    dref = execution.get("design_ref") or {}
    if not _nonempty_str(dref.get("design_id")):
        errs.append("登记头 design_ref.design_id 为空（未承接任何设计）")
    if not _nonempty_str(dref.get("content_hash")):
        errs.append("登记头 design_ref.content_hash 为空（冻结哈希未落字）")
    status = execution.get("status")
    if status not in PKG_STATES:
        errs.append(f"执行包状态非法：{status!r}")
    ledger = execution.get("budget_ledger") or {}
    if not isinstance(ledger.get("limits"), dict) or \
            not isinstance(ledger.get("spent"), dict):
        errs.append("预算总账 budget_ledger 缺 limits/spent（预算账是登记头必备区）")
    if status == "blocked":
        br = execution.get("block_record") or {}
        if not _nonempty_str(br.get("reason")) or \
                not _nonempty_str(br.get("unblock_condition")):
            errs.append("blocked 状态须带 block_record（原因 + 解阻条件）")
    errs.extend(_history_errors(execution.get("status_history"), PKG_NEXT,
                                "执行包", blocked_ok=True))

    # —— 事件日志 ——
    errs.extend(f"事件日志：{e}" for e in pkg.get("event_errors") or [])
    errs.extend(f"事件日志：{e}" for e in validate_events(events))

    # —— 逐 run ——
    for run in runs.values():
        errs.extend(_validate_run(run, pkg))

    # —— 对账表占位：行数与 registry 逐行对齐，不许缺行 ——
    recon = pkg.get("reconciliation")
    registry_ids = (execution.get("intake_report") or {}).get("registry_run_ids") or []
    if recon is None:
        if registry_ids:
            errs.append("对账表缺失：reconciliation.yaml 不存在"
                        "（承接成功后必须生成占位对账表）")
    else:
        rows = recon.get("rows") or []
        row_ids = [r.get("registry_run_id") for r in rows if isinstance(r, dict)]
        if sorted(row_ids) != sorted(registry_ids):
            errs.append(f"对账表行与预期登记不对齐：对账行 {sorted(row_ids)} "
                        f"≠ 登记行 {sorted(registry_ids)}（逐行对账不许缺行）")
        for r in rows:
            if isinstance(r, dict) and \
                    r.get("status") not in RECONCILIATION_ROW_STATES:
                errs.append(f"对账行 {r.get('registry_run_id')} 状态非法："
                            f"{r.get('status')!r}")
            elif isinstance(r, dict) and r.get("status") == "filled":
                # 二期实质回填的形状校验（清零检查的全集在
                # reconciliation_problems，delivered 门与 check 命令共用）
                label = f"对账行 {r.get('registry_run_id')}"
                errs.extend(readout_distribution_errors(
                    r.get("readout_actual"), label))
                layers = r.get("layers") or {}
                for layer in ("implementation", "execution"):
                    if not isinstance(layers.get(layer), bool):
                        errs.append(f"{label} layers.{layer} 须为二值判定，"
                                    f"当前 {layers.get(layer)!r}")
                rf = layers.get("result_fact") or {}
                if rf.get("verdict") not in RESULT_FACT_VERDICTS:
                    errs.append(f"{label} layers.result_fact.verdict 非法："
                                f"{rf.get('verdict')!r}")
                if rf.get("verdict") == "incomparable" and \
                        not _nonempty_str(rf.get("reason")):
                    errs.append(f"{label} result_fact 判 incomparable 必须写明"
                                "不可比原因（如真值未过低方差门）")
                if not isinstance(r.get("random_sources"), dict):
                    errs.append(f"{label} 已回填但缺 random_sources 随机源清单"
                                "（哪些被重新随机化、哪些被冻结，须逐行落字）")
        if recon.get("content_hash") != dref.get("content_hash"):
            errs.append("对账表 content_hash 与登记头冻结哈希不一致"
                        "（对账所据版本必须钉死）")

    # —— 二期产物（在场才验；不在场 = 尚未进入该子流程，不报错） ——
    errs.extend(_validate_acceptance(pkg))
    errs.extend(_validate_deviations(pkg))
    errs.extend(_validate_failures(pkg))
    errs.extend(_validate_budget(pkg))
    return errs
