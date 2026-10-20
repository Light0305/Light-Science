"""词表与规则表（权威定义层）。

本模块只放「口径」：状态机、writable_form 导出规则、双语措辞词表、
撤稿四态、引用核查的两套幻觉口径分名与容差/定级表（Phase 2 审计门消费）、
模板核查记录九组字段。校验逻辑在 validate.py，不许在此处散落第二份口径。

构建期差异落实（00-census-summary 纠错记录第 11 条）：
- (a) 两套「幻觉」口径分开落名：FIELD_LEVEL_HALLUCINATION_SCREEN（Chelli
  字段级筛）与 IDENTITY_LEVEL_FABRICATION（refchecker 身份级编造判定），
  粒度与用途不同，不得混用阈值。
- (b) 引用核查规则带容差层与 error/warning 定级层（FIELD_TOLERANCES），
  零容差执行会与约束 14（no-false-positive）冲突。
- (c) 撤稿四态 RETRACTION_STATES（retracted / no_doi / unknown / clean），
  「无证据绝不落 clean」（refchecker R11 口径）。
- (e) 模板字段以草案 §四为准：A–I 九组、约 37 字段（TEMPLATE_GROUPS）。
- (f) AI 政策组补「规定声明标题 / 措辞模板」字段、披露位置多值、
  「输出有效性评估」单列子项（见 TEMPLATE_GROUPS["G"]）。
"""

from __future__ import annotations

# ---------------------------------------------------------------- 状态机

STATES = ["intake", "outlined", "drafted", "audited", "submission_ready"]

# ---------------------------------------------------------------- 语言

LANGUAGES = ["en", "zh"]

# ---------------------------------------------------------------- 主张

UPSTREAM_STATUSES = ["supported", "partial", "untested", "undetermined"]
STRENGTH_GRADES = ["conclusive", "strong", "suggestive", "insufficient"]

# writable_form 序（高→低）：full > qualified > downgraded > limitations_only > omit
WRITABLE_FORMS = ["full", "qualified", "downgraded", "limitations_only", "omit"]
_FORM_RANK = {name: len(WRITABLE_FORMS) - i for i, name in enumerate(WRITABLE_FORMS)}


def form_rank(form: str) -> int:
    return _FORM_RANK[form]


def writable_ceiling(upstream_status: str, strength_grade: str) -> str:
    """由上游状态 × 强度档导出可写形态上限（草案 §1.2 规则表，不许临场决定）。

    - untested → limitations_only 上限（只许进局限节或不写）
    - undetermined → downgraded 上限
    - insufficient → downgraded 上限（无论上游状态）
    - partial → qualified 上限
    - supported + suggestive → qualified；supported + conclusive/strong → full
    """
    if upstream_status == "untested":
        return "limitations_only"
    if upstream_status == "undetermined":
        return "downgraded"
    if strength_grade == "insufficient":
        return "downgraded"
    if upstream_status == "partial":
        return "qualified"
    if strength_grade == "suggestive":
        return "qualified"
    return "full"


# ------------------------------------------------------- 措辞上限（双语各备）

# 每档：ceiling_label + allowed_terms（该档可用的最强措辞级）；
# banned_terms 为全档禁用（措辞门 Phase 2 逐条比对，此处为权威词表）。
# 中文版按用户口径含「证明了 / 显著」类禁用词；英文版含 proves 类与
# 二值标签式 significant / no effect（Analysis 强度词表口径的 Write 落点）。
WORDING_TABLES = {
    "en": {
        "grades": {
            "conclusive": {
                "ceiling_label": "demonstrative",
                "allowed_terms": ["demonstrates", "establishes", "confirms",
                                  "shows conclusively"],
            },
            "strong": {
                "ceiling_label": "assertive",
                "allowed_terms": ["shows", "indicates", "demonstrates"],
            },
            "suggestive": {
                "ceiling_label": "hedged",
                "allowed_terms": ["suggests", "is consistent with",
                                  "may indicate", "appears to"],
            },
            "insufficient": {
                "ceiling_label": "minimal",
                "allowed_terms": ["was observed", "is reported descriptively"],
            },
        },
        "banned_terms": ["proves", "proved", "proof that",
                         "no effect", "not significant", "highly significant"],
    },
    "zh": {
        "grades": {
            "conclusive": {
                "ceiling_label": "demonstrative",
                "allowed_terms": ["确立", "证实", "明确表明"],
            },
            "strong": {
                "ceiling_label": "assertive",
                "allowed_terms": ["表明", "显示", "证实"],
            },
            "suggestive": {
                "ceiling_label": "hedged",
                "allowed_terms": ["提示", "与……一致", "可能表明", "倾向于"],
            },
            "insufficient": {
                "ceiling_label": "minimal",
                "allowed_terms": ["观察到", "作描述性报告"],
            },
        },
        "banned_terms": ["证明了", "证明", "显著", "不显著", "高度显著",
                         "无影响", "没有影响", "彻底证明", "完全证明"],
    },
}


def wording_ceiling_for(language: str, strength_grade: str) -> dict:
    """按稿件语言取对应词表，导出一条主张的措辞上限登记形态。"""
    table = WORDING_TABLES[language]
    grade_entry = table["grades"][strength_grade]
    return {
        "language": language,
        "grade": strength_grade,
        "ceiling_label": grade_entry["ceiling_label"],
        "allowed_terms": list(grade_entry["allowed_terms"]),
        "banned_terms": list(table["banned_terms"]),
    }


# ---------------------------------------------------------------- 引用

# 撤稿四态（差异 c）：无证据绝不落 clean；no_doi 是形态不是结论。
RETRACTION_STATES = ["retracted", "no_doi", "unknown", "clean"]

# 两套幻觉口径分名（差异 a）——Phase 2 引用门消费，Phase 1 先落名与口径：
CITATION_FABRICATION_LEVELS = {
    # Chelli 操作化定义：题名 / 第一作者 / 年份任二与权威记录不符 → 字段级筛阳性。
    "field_level_hallucination_screen": {
        "source": "Chelli et al. 2024",
        "rule": "title/first_author/year 任二错",
        "granularity": "field",
        "effect": "整稿 fail 并逐条落字（成稿门）",
    },
    # refchecker LIKELY：作品不存在或作者名单实质不符；明确排除年份/venue 漂移。
    "identity_level_fabrication": {
        "source": "markrussinovich/refchecker LIKELY",
        "rule": "作品不存在，或作者名单实质不符（不含年份/venue 漂移）",
        "granularity": "identity",
        "effect": "判定编造须第二路阴性证据（约束 1）",
    },
}

# 字段级核查的容差层与定级层（差异 b；refchecker 表② R1–R12 口径）。
# Phase 1 的 validate 只执行存在性/撤稿/集合差；本表是 Phase 2 两段核对的权威口径。
FIELD_TOLERANCES = {
    "year": {"tolerance": "±1（在线年/正式年漂移）", "level": "warning"},
    "venue": {"tolerance": "缩写/全称/变体等价", "level": "warning"},
    "doi": {"tolerance": "归一化后全等；不一致时能解析降为 warning、不能解析才是 error;"
                          "截断前缀可接受", "level": "graded"},
    "title": {"tolerance": "大小写/标点/连字符/版本后缀豁免 + 副标题容差 + 编辑距离 ≤3 typo；"
                            "前提是身份已由标识符确认", "level": "graded"},
    "authors": {"tolerance": "首字母↔全名、姓氏粒子、变音归一、et al. 截断合法；"
                              "人数不符报错", "level": "graded"},
    "existence": {"tolerance": "查无此条", "level": "error"},
}

# 引用语境核对（约束 4）的条目处置词表（ARIS 形态）；与 amazon RefChecker 的
# 三元组蕴含三值（Entailment/Neutral/Contradiction + Abstain）是不同粒度，
# 不可混用（差异 d）——后者是语境轴的判定形态，前者是条目处置。
CONTEXT_DISPOSITIONS = ["KEEP", "FIX", "REPLACE", "REMOVE"]
CONTEXT_DISPOSITIONS_NEED_HUMAN = ["REPLACE", "REMOVE"]
ENTAILMENT_VERDICTS = ["entailment", "neutral", "contradiction", "abstain"]

# ------------------------------------------------- Phase 2：措辞档位序

# 强度档序（高→低）：conclusive > strong > suggestive > insufficient。
# 措辞门判定：正文句中出现的词表术语，其「最低可用档」高于该主张的强度档
# → 超限（term_required_rank > 主张档 rank）。同一术语可出现在多档的
# allowed_terms 中（如 demonstrates 同属 conclusive 与 strong），其最低
# 可用档取出现过的最低档。
GRADE_RANK = {"conclusive": 4, "strong": 3, "suggestive": 2, "insufficient": 1}


def term_required_rank(language: str, term: str):
    """术语的最低可用强度档 rank；不在该语言词表中 → None（不设限）。"""
    table = WORDING_TABLES[language]
    ranks = [GRADE_RANK[g] for g, entry in table["grades"].items()
             if term in entry["allowed_terms"]]
    return min(ranks) if ranks else None


def all_wording_terms(language: str) -> list:
    """该语言词表全部 allowed_terms（去重保序），措辞门逐句扫描用。"""
    seen, out = set(), []
    for entry in WORDING_TABLES[language]["grades"].values():
        for t in entry["allowed_terms"]:
            if t not in seen:
                seen.add(t)
                out.append(t)
    return out


# ------------------------------------------------- Phase 2：检查清单层级

# 落点映射条目层级（ARRIVE 分层口径）：baseline = 底线层（投稿就绪硬门），
# full = 完整层（落点复核覆盖、缺失记门四 findings 但分级处置见 audit）。
CHECKLIST_TIERS = ["baseline", "full"]
CHECKLIST_STATUSES = ["addressed", "not_applicable", "missing"]

# ------------------------------------------------- Phase 2：审计四门

AUDIT_GATES = ["citations", "numbers", "wording", "landing"]
AUDIT_GATE_TITLES = {
    "citations": "门一 · 引用两段核对",
    "numbers": "门二 · 数字对账",
    "wording": "门三 · 强度措辞门",
    "landing": "门四 · 落点映射复核",
}

# ------------------------------------------------- Phase 2：W7 返修

REVISION_CATEGORIES = ["major", "minor", "editorial"]
REVISION_DECISIONS = ["accept", "partial", "reject"]

# ------------------------------------------------- Phase 2：图表

FIGURE_KINDS = ["figure", "table"]

# ---------------------------------------------------------------- 声明

DECLARATION_KEYS = ["data_availability", "ethics", "conflict", "funding"]
DECLARATION_STATES = ["present", "absent", "na"]

# ---------------------------------------------------------------- 图表

FIGURE_STATUSES = ["placeholder", "delivered", "backfilled"]

# ---------------------------------------------------------------- 验收合同

CONTRACT_STATUSES = ["unset", "draft", "agreed", "contested"]
ASSERTION_STATUSES = ["agreed", "contested"]
CONTRACT_MIN_ASSERTIONS = 10
CONTRACT_MAX_ASSERTIONS = 20

# ------------------------------------------------------- 模板核查记录九组

# 草案 §四 A–I 九组（差异 e：以九组约 37 字段为准）。
# 每组：required = 组内必填字段；组本身缺失 = error（validate 逐组点名）。
TEMPLATE_GROUPS = {
    "A": {
        "name": "身份与版本",
        "required": ["record_id", "journal_name", "publisher",
                     "template_version", "journal_language"],
        "fields": ["record_id", "journal_name", "issn", "eissn", "publisher",
                   "journal_group", "template_version", "applicable_years",
                   "journal_language"],
    },
    "B": {
        "name": "格式轨与选项轴",
        "required": ["format_track"],
        "fields": ["format_track", "latex_class", "class_version",
                   "options_axis", "word_template", "citation_package"],
    },
    "C": {
        "name": "栏目与结构",
        "required": ["section_sequence"],
        "fields": ["section_sequence", "abstract_form", "keyword_limit",
                   "special_sections"],
    },
    "D": {
        "name": "限额（数值化）",
        "required": [],
        "fields": ["word_limit_total", "word_limit_abstract", "page_limit",
                   "figure_limit", "table_limit", "reference_limit",
                   "title_char_limit", "short_title_char_limit"],
        # 限额一律数值字段：组内至少一项在场且在场者全为数值（validate 执行）。
        "at_least_one": True,
    },
    "E": {
        "name": "参考文献",
        "required": ["style_name", "csl_id"],
        "fields": ["style_name", "csl_id", "bst_name", "citation_style_kind"],
    },
    "F": {
        "name": "图件",
        "required": ["figure_submission_mode"],
        "fields": ["figure_submission_mode", "figure_formats",
                   "figure_resolution", "caption_position"],
    },
    "G": {
        "name": "声明与披露",
        "required": ["declarations", "ai_policy"],
        "fields": ["declarations", "ai_policy"],
        # ai_policy 子字段（差异 f 补全）：
        # has_guideline / ai_authorship_banned / disclosure_required /
        # disclosure_content_standard / disclosure_title（规定声明标题）/
        # disclosure_wording_template（规定措辞模板）/
        # disclosure_positions（多值：Science 双落点、PLOS 可落图注）/
        # language_editing_stance / publisher_conflict{conflict, resolution_note} /
        # output_validity_evaluation（PLOS 独有项，单列子项）
        "ai_policy_required": ["has_guideline", "disclosure_required"],
    },
    "H": {
        "name": "来源与时效",
        "required": ["source_url", "official_channel", "verified_at"],
        "fields": ["source_url", "official_channel", "verified_at",
                   "review_cycle_days", "verified_by", "bundled"],
    },
    "I": {
        "name": "条款",
        "required": ["redistribution"],
        "fields": ["redistribution", "terms_pointer", "purpose_restriction"],
    },
}

REDISTRIBUTION_VALUES = ["packageable", "channel_only", "prohibited"]
FORMAT_TRACKS = ["latex", "word"]
BUNDLED_VALUES = ["official", "generic_scaffold"]

# 模板记录过期阈值（天）：缺省取记录 H 组 review_cycle_days，再缺省 180。
TEMPLATE_EXPIRY_DEFAULT_DAYS = 180


# --- Supplement D adoptions (nature-skills cluster) ---
RISK_TIERS = ("assistive", "evaluative_interpretive", "prohibited")  # D-W04
SUPPORT_LEVELS = ("strong", "partial", "background", "contradictory_limiting", "metadata_only")  # D-W07
REJECTION_REASONS = (  # D-W12 failure taxonomy (Boom claim-source-verification)
    "does_not_support_claim", "metadata_wrong", "wrong_site_or_population",
    "not_primary_but_required", "paywalled_unverifiable")
VERIFICATION_STATUSES = ("verified", "check_suggested", "needs_fix", "unverifiable")  # D-W06
ACCESS_PATHS = ("public_repository", "controlled_access", "within_paper", "reused_public",
                "third_party_restricted", "justified_request", "not_applicable")  # D-W08
CHECKLIST_STAGES = ("initial", "revision", "production")  # D-W09
APPLICABILITY = ("required", "optional", "not_applicable", "author_input_needed")  # D-W09
DRAFT_MARKERS = ("claim", "num", "rev", "fig", "todo-fact", "note-edit", "directive", "superseded")  # D-W13
LOCATION_ROLES = ("introduce", "demonstrate", "interpret", "synthesize", "shorten", "delete")  # D-W01
RESULT_FUNCTIONS = ("core_discovery", "necessary_support", "qualification", "robustness",
                    "heterogeneity", "provenance_detail", "alternative_inference", "edge_case")  # D-W01
DESTINATIONS = ("main_text", "figure_caption", "methods", "supplementary")  # D-W01
PROTECTED_KINDS = ("replication_unit_and_n", "no_pvalue_statement", "blinding_and_exclusions",
                   "data_access_path", "decision_counts", "estimator_assumptions",
                   "negative_results", "methods_scope_conditions", "journal_required_statement")  # D-W11
STATS_REPORTING_CHECKLIST = (  # D-W14 (nature-statistics field basis)
    {"item_id": "stats-independent-unit", "requirement": "Independent experimental unit defined; biological/technical replicates and repeated measures reported separately (no pseudo-replication)", "section": "methods"},
    {"item_id": "stats-claim-analysis-map", "requirement": "Claim-to-analysis mapping present: comparison/model, test family, assumptions, multiplicity correction, effect size, uncertainty, exact-p policy; missing fields marked AUTHOR_INPUT_NEEDED, never invented", "section": "methods"},
)
