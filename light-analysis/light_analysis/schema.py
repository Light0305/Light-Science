"""数据模型与受控词表（Phase 1）。

本模块只定义结构与词表，不含任何判定计算：正式判定与最小判定计算集
在 Phase 2 落地。词表与 REDESIGN-DRAFT §2 对齐，用户拍板（2026-10-20）：

- 判定词表五值：positive / negative / null / undetermined / untested
  （undetermined 与 untested 是一等行级终态，不许硬判、不入强度档）；
- 四象限：significant_not_equivalent / significant_but_equivalent /
  equivalent_only / undetermined；
- 强度 4 档：conclusive / strong / suggestive / insufficient；
- 多重校正默认按主张族 BH-FDR（fdr_bh），primary 主张可声明 Holm（holm）；
- 事后功效禁令落成字段规则：type_sm.assumed_D.basis 只许
  sesoi_frozen / prior_external，出现 observed / posthoc 字样直接拒。
"""

from __future__ import annotations

from .util import today

# ---------------------------------------------------------------- 词表

PKG_STATES = ["intake", "checked", "judged", "graded", "delivered", "blocked"]
MAIN_STATES = ["intake", "checked", "judged", "graded", "delivered"]

VERDICTS = ["positive", "negative", "null", "undetermined", "untested"]
DIRECTIONAL_VERDICTS = ["positive", "negative", "null"]
QUADRANTS = [
    "significant_not_equivalent",
    "significant_but_equivalent",   # 存在但 <SESOI：verdict=positive 必须带此标记
    "equivalent_only",              # 干净 null
    "undetermined",
]
GRADES = ["conclusive", "strong", "suggestive", "insufficient"]
SUPPORT_VALUES = ["supported", "partial", "not_supported", "untested"]

CORRECTION_METHODS = ["fdr_bh", "holm", "bonferroni", "fdr_by"]
DEFAULT_CORRECTION_METHOD = "fdr_bh"
PRIMARY_CORRECTION_METHOD = "holm"

# Type S/M 三元组的 D 来源：只许外部代入（Design 冻结 SESOI 或外部先验范围）
POWER_BASIS_OK = ["sesoi_frozen", "prior_external"]
POWER_BASIS_BANNED = ["observed", "posthoc", "post_hoc", "post-hoc",
                      "observed_power", "retrospective"]

# TOST bounds 来源：只许 Design 冻结 SESOI
TOST_BOUNDS_SOURCES_OK = ["design_sesoi"]

# 贝叶斯诊断硬字段门（约束 4：rank-normalized R̂ < 1.01、ESS 双 >400）
R_HAT_MAX = 1.01
ESS_MIN = 400
BAYES_INTERVAL_KINDS = ["hdi", "eti"]
INTERVAL_KINDS = ["ci", "hdi", "eti"]

# 分布判据默认阈值 γ（P(A>B)，Bouthillier 口径；登记行另有冻结判据时以登记为准）
GAMMA_DEFAULT = 0.75

# 规格集展开上限：≤512 全展开，超限抽样并登记种子（拍板②）
SPEC_CAP = 512

# 强度/判定自由文本禁用词（拍板④冻结措辞词表）：
# 禁「显著/不显著」二分标签与「证明了/无影响」式绝对化表述。
FORBIDDEN_PHRASES = [
    "显著", "证明了", "无影响",
    "significant", "insignificant", "proved", "proof that", "no effect",
]
# 探索区禁用词表 = 判定词表 + 强度档位 + 上列禁用词（防词义滑移，§2.4）
EXPLORATORY_BANNED_WORDS = [
    "positive", "negative", "null", "undetermined", "untested",
    "conclusive", "strong", "suggestive", "insufficient",
] + FORBIDDEN_PHRASES

# 分布材料四件套（承 Experiment 纪律 14：readout_actual 只收分布不收单点）
DISTRIBUTION_KEYS = ["mean", "spread", "n", "replication_level"]

JUDGEABILITY_VALUES = [
    "judgeable", "untested_candidate", "undetermined_candidate",
]


def scan_forbidden(text, phrases=FORBIDDEN_PHRASES):
    """扫自由文本里的禁用词，返回命中列表。"""
    if not text:
        return []
    low = str(text).lower()
    return [p for p in phrases if p.lower() in low]


def scan_banned_words(text, words=EXPLORATORY_BANNED_WORDS):
    """探索区词表拦截：英文按整词匹配，中文按子串匹配。"""
    if not text:
        return []
    low = str(text).lower()
    hits = []
    for w in words:
        wl = w.lower()
        if all(ord(c) < 128 for c in wl):
            import re
            if re.search(r"(?<![a-z0-9_])" + re.escape(wl) + r"(?![a-z0-9_])", low):
                hits.append(w)
        elif wl in low:
            hits.append(w)
    return hits


# ---------------------------------------------------------------- 空结构

def empty_counts():
    return {v: 0 for v in VERDICTS} | {"total_lines": 0}


def new_analysis(analysis_id: str, title: str = "") -> dict:
    """analysis.yaml 登记头骨架（承接区/规格区在 intake 与冻结时回填）。"""
    return {
        "analysis_id": analysis_id,
        "title": title or analysis_id,
        "status": "intake",
        "status_history": [
            {"state": "intake", "at": today(), "by": "light-analysis init"},
        ],
        "blocked": None,               # {from_state, reason, at}，blocked 态时填
        # 承接区（intake 冻结）
        "execution_ref": None,         # {execution_id, package_path, execution_card, execution_card_hash, card_status}
        "design_ref": None,            # {design_id, content_hash, registry_hash, registry_lines}
        "registry_snapshot": {"line_ids": [], "lines": []},
        "claim_ids": [],
        # 规格区
        "spec_version": {"version": "0.1", "frozen_hash": None},
        "analyst": {"name": None, "family": None},
        "correction_families": [],     # [{family_id, member_line_ids, method, alpha, basis}]
        # 复核区（Phase 2 判定复核回填；delivered 门验）
        "review": None,                # {reviewer, family, review_status, receipt_id}
        # 汇总区（工具机械汇总，不许手填）
        "counts": empty_counts(),
        "reflux": [],
    }


def verdict_row(registry_line_id: str, verdict: str, **kw) -> dict:
    """verdicts.jsonl 一行的完整字段骨架（五组+溯源）。

    Phase 1 只做 schema 与校验：本函数不计算任何判定量，
    数值字段一律由调用方（Phase 2 判定规程/人工落字）显式给出。
    """
    row = {
        "registry_line_id": registry_line_id,
        "claim_ref": None,
        "row_ref": None,               # 校验器按行内序号核：<line>#v<n>
        "supersedes": None,
        # 判定组
        "verdict": verdict,
        "quadrant": None,
        "basis_spec_id": None,
        "criteria_ref": None,
        "direction": None,             # higher | lower（承登记行 primary_metric.direction）
        # 量组
        "effect_size": None,           # {type, value}
        "interval": None,              # {kind: ci|hdi|eti, level, lo, hi}
        "p_ab": None,                  # P(A>B) 分布判据值
        "p_ab_gamma": GAMMA_DEFAULT,
        "n_effective": None,
        "n_registered": None,
        # 校准组
        "type_sm": None,               # {assumed_D:{value,basis,source_ref}, power, type_s, type_m}
        # 等价组
        "tost": None,                  # {bounds:{lo,hi,source}, p_tost, ci90:{lo,hi}, ci90_in_bounds, result}
        # 诊断组
        "diagnostics": None,           # {r_hat, ess_bulk, ess_tail, mcse, chains}
        "bayes": False,
        # 校正组
        "correction": None,            # {family_id, method, p_raw, p_adj}
        # 强度组
        "strength_grade": None,
        "strength_cap_reason": None,
        # 留痕
        "note": None,
        "decided_by": None,
        "decided_at": None,
    }
    row.update(kw)
    return row


def new_spec_ledger() -> dict:
    """spec_ledger.yaml 骨架（决策点与规格在冻结前由规程/工具回填）。"""
    return {
        "spec_version": "0.1",
        "decisions": [],               # [{point, options:[{name, valid}], theoretical_justification}]
        "constraints": [],             # [{forbids: {point: option, ...}}]
        "sampling": None,              # 超限抽样时 {rule, seed, reachable_total, kept}
        "reachable_count": None,
        "specs": [],                   # [{spec_id, choices, gate:{...}, status, exclude_reason}]
        "expansions": [],              # 自由度账本（只增）：{at, decision, motivation, seen_results, affected_lines}
        "frozen_hash": None,
        "frozen_at": None,
    }


def new_conclusions() -> dict:
    """conclusions.yaml 骨架（Phase 2 填充判定映射，本期先定 schema）。"""
    return {
        "claims_verdict": [],          # [{claim_id, support, line_verdicts:{line:verdict}, aggregation_note}]
        "strength": [],                # [{claim_id, grade, inputs:{...}, cap_reason}]
        "boundaries": [],              # [{claim_id, conditions, not_extrapolatable, would_change_if}]
        "limitations": [],             # [str | {text, source}]
        "number_provenance": [],       # [{value, verdict_line, registry_line_id, run_refs, spec_id}]
        "reflux": [],                  # [{kind, target, detail}]
    }


def new_exploratory() -> dict:
    """exploratory/exploratory.yaml 骨架：条目禁用判定词表（校验器拦截）。"""
    return {
        "entries": [],                 # [{id, question, motivation, inputs, method_note, finding, exploratory: true, promotion_path}]
    }
