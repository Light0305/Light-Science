"""词表与规则表（权威定义层）。

本模块只放「口径」：状态机、候选来源路、来源状态四态、指标词表、
风险门条件分级（拍板 E3）、分档词表、先例路参数（JS-04）。
校验逻辑在 validate.py / verify.py / gate.py，不许在此处散落第二份口径。

依据：08-journal-select/LEARNING.md（JS-01–JS-05 存世部分）、
REDESIGN-DRAFT v0.1 与文末拍板附录 E1–E5。
"""

from __future__ import annotations

# ---------------------------------------------------------------- 状态机

STATES = ["draft", "candidates_ready", "verified", "gated",
          "decided", "handed_off"]

TRANSITIONS = {
    "draft": ["candidates_ready"],
    "candidates_ready": ["verified"],
    "verified": ["gated"],
    "gated": ["decided"],
    "decided": ["handed_off"],
    "handed_off": [],
}

# ---------------------------------------------------------------- 语言/类型

LANGUAGES = ["en", "zh"]
MANUSCRIPT_TYPES = ["research", "review", "methods"]

# ---------------------------------------------------------------- 稿件指纹

# 指纹必填区（草案 §三.1）：方法不许冒充领域，除非贡献本身是方法学。
FINGERPRINT_FIELDS = ["field", "subfield", "study_object", "core_problem",
                      "contribution_type", "audience", "methods_role"]
CONTRIBUTION_TYPES = ["method", "empirical", "theory", "resource",
                      "application", "review"]
METHODS_ROLES = ["core_method_contribution", "tool", "not_applicable"]

# 约束键全集（草案 §二）：缺项不许静默默认——键必须在场，
# 值可为 None（报告渲染为「未设」并逐项点名）。
CONSTRAINT_KEYS = ["tier_expectation", "apc_budget", "review_cycle_limit",
                   "excluded_journals", "excluded_publishers",
                   "excluded_modes", "journal_language_pref",
                   "recognized_catalogs"]

# ---------------------------------------------------------------- 候选来源

# 先例路为主 + 检索补充 + finder 带回人工入池（拍板 E2）。
CANDIDATE_SOURCES = ["precedent", "search", "finder_manual"]

# 来源状态四态（JS-02，学 sci-select source_status 合同）：
# succeeded=查完有记录 / attempted=查询失败 / partial=部分可用 /
# skipped=有意未查。不许把「没查」说成「没有」、「失败」说成「安全」。
SOURCE_STATUSES = ["succeeded", "attempted", "partial", "skipped"]

# ---------------------------------------------------------------- 核验指标

# 指标词表（JS-01 指标零记忆：每值必须带来源+年份+查询日期三元组）。
METRIC_KEYS = ["impact_factor", "quartile_jcr", "quartile_cas",
               "apc", "review_cycle", "indexing", "scope_fit",
               "self_cite_rate", "annual_volume", "warning_status"]

VERIFICATION_STATUSES = ["verified", "unconfirmed"]

# 指标来源类型（JS-03 来源优先级：官网 > 官方名单 > DOAJ > 聚合站）。
METRIC_PROVENANCES = ["official", "official_list", "doaj",
                      "aggregator", "crowd", "other"]

# 审稿周期双路（拍板 E4）：官方统计优先；众包（LetPub 等）入卡
# 强制三标注——众包口径 basis + 样本量 sample_size（未知写「未披露」）
# + 查询日期 queried_at；众包周期不单独决定分档。
REVIEW_CYCLE_CROWD_ANNOTATIONS = ["basis", "sample_size", "queried_at"]
SAMPLE_SIZE_UNDISCLOSED = "未披露"

# 分区词表（仅作 verified 值的形态校验；专有数值只许实时查询后
# 带源落字，永不落任何常驻库——红线沿用期刊信息库普查口径）。
JCR_QUARTILES = ["Q1", "Q2", "Q3", "Q4"]
CAS_ZONES = ["1区", "2区", "3区", "4区"]

# ---------------------------------------------------------------- 风险门（E3）

RISK_LEVELS = ["clear", "soft_warn", "quasi_hard", "hard_exclude"]

# 一级硬门：命中即出局，不可放行（拍板 E3 前半）。
HARD_CONDITIONS = ["warning_list_hit",      # 中科院预警名单命中
                   "ceased_or_delisted",    # 已停刊 / 被 Scopus·WoS 剔除
                   "scope_mismatch",        # 官网 scope 明显不符
                   "user_excluded"]         # 命中用户排除项

# 准硬门：默认排除；用户书面知情确认后可放行且永久留痕（拍板 E3 后半）。
QUASI_HARD_CONDITIONS = ["predatory_list_hit",   # 掠夺社区名单命中
                         "hijack_suspect",       # 劫持嫌疑（含域名不一致）
                         "domain_mismatch"]      # 官网域名与登记不一致

# 二级软警告：保留推荐，证据卡必须显形（草案 §四）。
SOFT_CONDITIONS = ["apc_opaque",               # APC 不透明/投稿后才披露
                   "review_cycle_crowd_only",  # 周期只有众包数据
                   "oa_not_in_doaj",           # 自称全 OA 但不在 DOAJ
                   "self_cite_high",           # 自引率异常高（>20%）
                   "volume_surge",             # 年发文量异常膨胀
                   "esci_only",                # ESCI-only（单位可能不认）
                   "metric_stale",             # 指标年份过期未复核
                   "finder_bias"]              # 候选主要来自单一出版商路

RISK_CONDITIONS = HARD_CONDITIONS + QUASI_HARD_CONDITIONS + SOFT_CONDITIONS

SELF_CITE_WARN_THRESHOLD = 0.20

# ---------------------------------------------------------------- 分档

TIERS = ["challenge", "target", "safety", "excluded"]
CARD_TIERS = ["challenge", "target", "safety"]
# 证据卡总数口径（草案 §三.5）：三档共 3–5 刊。
CARD_MIN, CARD_MAX = 3, 5

# ---------------------------------------------------------------- 先例路（JS-04）

OPENALEX_BASE = "https://api.openalex.org"
WINDOW_YEARS = 5            # 近 5 年窗口（Jane 近 10 年口径的移植修正）
PER_QUERY_LIMIT = 50        # 每条检索式取约 50 篇
ENTRY_MIN_SIMILAR = 2       # 入门门槛：相似论文 ≥2 篇
ENTRY_MIN_QUERIES = 2       # 或多式覆盖 ≥2 条检索式
ENTRY_TOP_RANK = 3          # 或单式名次 ≤3
MAX_PRECEDENTS_PER_JOURNAL = 5   # 每刊保留先例上限（渲染取 2–3）
RESEARCH_TYPES = ["article"]     # 剔非研究类（OpenAlex type 口径）
