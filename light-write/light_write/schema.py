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
- (e) 模板字段以草案 §四为准：A–I 九组、46 字段（TEMPLATE_GROUPS）。
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


# ------------------------------------------------- WRT-D02 词表证据登记

# 词表条目逐条的证据指针与处置依据（WRT-D02 第一次实测后立）：
# 「冻结」的口径 = 冻结版本与变更纪律——经验内容可经实测修订，修订
# 须附测量报告指针，被推翻条目存档于测量报告、不静默删（见
# 06-write/WORDING-MEASUREMENT-v1.1.md）。validate_wording_tables()
# 强校验：任一条目缺 evidence 或 disposition 即报错。
_MEAS = "06-write/WORDING-MEASUREMENT-v1.1.md（2026-10-21 首测）"
_NORM = "LEARNING 约束 12 + Analysis 强度措辞词表（规范来源）"

WORDING_EVIDENCE = {
    "en": {
        "banned": {
            "proves": {"evidence": _NORM + "；匹配口径实测见 " + _MEAS,
                       "disposition": "证明级断言超出任何单研究证据强度，全档禁。匹配口径：子串口径已被首测证伪（已发表语料 7 命中全为 improves 误报、词界命中 0），门三已改词界匹配"},
            "proved": {"evidence": _NORM + "；匹配口径实测见 " + _MEAS,
                       "disposition": "同 proves（时态变体；子串口径 16 命中全为 improved 误报，同改词界）"},
            "proof that": {"evidence": _NORM, "disposition": "同 proves（名词形态）"},
            "no effect": {"evidence": _NORM + "；实测见 " + _MEAS,
                          "disposition": "零效应断言与「未检出」混同，二分标签式表述全档禁；合法形态是报告效应量与区间"},
            "not significant": {"evidence": _NORM + "；实测见 " + _MEAS + "；变体命中形态见 20-build/phase4-eval-report.md §8.1（heldout 实测）",
                                "disposition": "显著性二分标签全档禁（与 Analysis 词表同口径）；结果报告走精确 p 值与区间，不以标签替代。匹配口径：词界精确 + 变体归一——首词与 significant 间插入副词（statistically 等）或 at all 仍判命中（快修批修复 heldout 绕过）；聚焦副词 only/just/also/simply/merely 不入间隙（防误杀 not only significant 类正向断言）"},
            "highly significant": {"evidence": _NORM, "disposition": "显著性分级标签，同 not significant 口径全档禁（含同一变体归一匹配）"},
        },
        "grades": {
            "conclusive": {
                "demonstrates": {"evidence": _NORM, "disposition": "确立档最强措辞，仅 conclusive 可用"},
                "establishes": {"evidence": _NORM, "disposition": "同档"},
                "confirms": {"evidence": _NORM, "disposition": "同档"},
                "shows conclusively": {"evidence": _NORM, "disposition": "同档"},
            },
            "strong": {
                "shows": {"evidence": _NORM, "disposition": "断言档下限措辞，strong 起可用"},
                "indicates": {"evidence": _NORM, "disposition": "同档"},
                "demonstrates": {"evidence": _NORM, "disposition": "跨档词：strong 起可用，conclusive 亦收"},
            },
            "suggestive": {
                "suggests": {"evidence": _NORM, "disposition": "提示档措辞，suggestive 起可用"},
                "is consistent with": {"evidence": _NORM, "disposition": "同档"},
                "may indicate": {"evidence": _NORM, "disposition": "同档"},
                "appears to": {"evidence": _NORM, "disposition": "同档"},
            },
            "insufficient": {
                "was observed": {"evidence": _NORM, "disposition": "最低档：只许观察性陈述"},
                "is reported descriptively": {"evidence": _NORM, "disposition": "同档"},
            },
        },
    },
    "zh": {
        "banned": {
            "证明了": {"evidence": _NORM, "disposition": "证明级断言超出单研究证据强度，全档禁"},
            "证明": {"evidence": _NORM, "disposition": "同「证明了」（基形态，覆盖复合词）"},
            "显著": {"evidence": _NORM + "；形态实测见 " + _MEAS,
                     "disposition": "显著性二分标签与程度副词式空转全档禁。首测：已发表译文语料 6 命中全为程度副词形态（显著增加/显著大于/显著改进），属本条目标形态；「显著性」0 命中，切分未触发、维持全形匹配（见 BANNED_MATCH_CARVEOUTS 注记）"},
            "不显著": {"evidence": _NORM, "disposition": "二分标签，同「显著」口径"},
            "高度显著": {"evidence": _NORM, "disposition": "显著性分级标签，全档禁"},
            "无影响": {"evidence": _NORM, "disposition": "零效应断言与未检出混同，全档禁"},
            "没有影响": {"evidence": _NORM, "disposition": "同「无影响」"},
            "彻底证明": {"evidence": _NORM, "disposition": "证明级断言的强化形态，全档禁"},
            "完全证明": {"evidence": _NORM, "disposition": "同「彻底证明」"},
        },
        "grades": {
            "conclusive": {
                "确立": {"evidence": _NORM, "disposition": "确立档措辞，仅 conclusive 可用"},
                "证实": {"evidence": _NORM, "disposition": "跨档词：conclusive 与 strong 均收，suggestive 用即超限"},
                "明确表明": {"evidence": _NORM, "disposition": "同档"},
            },
            "strong": {
                "表明": {"evidence": _NORM, "disposition": "断言档措辞，strong 起可用"},
                "显示": {"evidence": _NORM, "disposition": "同档"},
                "证实": {"evidence": _NORM, "disposition": "跨档词，见 conclusive 档登记"},
            },
            "suggestive": {
                "提示": {"evidence": _NORM, "disposition": "提示档措辞，suggestive 起可用"},
                "与……一致": {"evidence": _NORM, "disposition": "模板形态条目（含省略号占位）：登记其口径，字面匹配不命中自然文本，实测零命中已登记于 " + _MEAS},
                "可能表明": {"evidence": _NORM, "disposition": "同档"},
                "倾向于": {"evidence": _NORM, "disposition": "同档"},
            },
            "insufficient": {
                "观察到": {"evidence": _NORM, "disposition": "最低档：只许观察性陈述"},
                "作描述性报告": {"evidence": _NORM, "disposition": "同档"},
            },
        },
    },
}

# 禁用词匹配面切分（WRT-D02 实测驱动）：某些禁用词条若含成系统的
# 合法形态，门三匹配前先从句中剥离合法形态再判，词条本身与禁令
# 不变。切分须有测量报告证据，不许临场豁免。
# 首测结论（2026-10-21，见 06-write/WORDING-MEASUREMENT-v1.1.md）：
# zh「显著性」在已发表译文语料 0 命中、「显著」6 命中全为程度副词
# 形态——切分未触发，本表保持空；后续语料见「显著性」成系统出现
# 再议。英文侧的对应修订是词界匹配（在门三实现，非本表）。
BANNED_MATCH_CARVEOUTS: dict = {}


def validate_wording_tables() -> list:
    """词表自检：每条 banned / allowed 条目须有证据指针与处置依据。"""
    problems = []
    for language, table in WORDING_TABLES.items():
        ev = WORDING_EVIDENCE.get(language) or {}
        for term in table["banned_terms"]:
            entry = (ev.get("banned") or {}).get(term)
            if not entry or not entry.get("evidence") \
                    or not entry.get("disposition"):
                problems.append(
                    f"{language} banned 词条 {term!r} 缺证据指针或处置依据")
        for grade, grade_entry in table["grades"].items():
            for term in grade_entry["allowed_terms"]:
                entry = ((ev.get("grades") or {}).get(grade) or {}).get(term)
                if not entry or not entry.get("evidence") \
                        or not entry.get("disposition"):
                    problems.append(
                        f"{language} {grade} 档 allowed 词条 {term!r} "
                        "缺证据指针或处置依据")
    return problems


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

# 草案 §四 A–I 九组（差异 e：以九组为准；字段实数 46，WRT-D08(1) 已清账）。
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
        # WRT-D08(5)：AI 政策子字段逐项必填（规程为准，校验补齐）——
        # 按「键在场」校验，值可为 null 的字段（无规定标题的刊等）以
        # 键在场为准，不许整项缺席。
        "ai_policy_required": ["has_guideline", "ai_authorship_banned",
                               "disclosure_required",
                               "disclosure_content_standard",
                               "disclosure_title",
                               "disclosure_wording_template",
                               "disclosure_positions",
                               "language_editing_stance",
                               "publisher_conflict",
                               "output_validity_evaluation"],
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
# H 组 official_channel 词表（WRT-D08(4)）：种子只收两包核查记录实测
# 在用值（light-write 登记记录与 light-journal-select 检查记录），
# 校验目的在拦拼写漂移；新增取值须改本常量落字，不许临场自造。
OFFICIAL_CHANNELS = ["publisher_page", "journal homepage", "journal_homepage"]
FORMAT_TRACKS = ["latex", "word"]
BUNDLED_VALUES = ["official", "generic_scaffold"]

# 模板记录过期阈值（天）：缺省取记录 H 组 review_cycle_days，再缺省 180。
TEMPLATE_EXPIRY_DEFAULT_DAYS = 180


# ------------------------------------------------- WRT-D01 程式化核查层

# 程式化/AI 味核查规则（advisory 先行：只报不改、不阻断定版）。
# 立规纪律（lieflat 实测体例）：规则只收可定位的触发标记，逐条带正例
# （必报）与反例（不许报）；中英分开立规，中文规则只收自家语料可定位
# 的触发标记，不直接搬英文结论。kind: pattern = 正则命中逐处报；
# ordinal = 序数脚手架成串检出（整节一报）；structure = 相邻句同构。
# 与 TONE_NOT_CHANGE（不改表）同等地位：不改表所列特征永不作报警依据。
TONE_RULES = [
    {
        "rule_id": "tone.en.reversal_frame", "language": "en",
        "name": "翻案腔（not merely X, but Y）",
        "kind": "pattern",
        "patterns": [r"not (merely|just|only) [^.!?]{1,60}?,\s*but",
                     r"is not (merely|just) an? [^.!?]{1,40}?,\s*but an?",
                     r"goes beyond [^.!?]{1,50}? to (offer|provide|enable)"],
        "description": "用「不是 A，而是 B」的翻案句式制造洞见感，"
                       "A 往往是无人主张的稻草人",
        "positive_example": "The method is not merely a tracker, but a "
                            "new paradigm for behaviour analysis.",
        "negative_example": "The method is not only faster but also more "
                            "accurate on short clips.",
        "suggestion": "直陈 B 本身并给出证据；确有被推翻的在先说法时，"
                    "点名其出处再翻案",
    },
    {
        "rule_id": "tone.en.boilerplate", "language": "en",
        "name": "套话衔接与空转强调",
        "kind": "pattern",
        "patterns": [r"it is worth noting that",
                     r"it should be noted that",
                     r"plays a (crucial|vital|key) role",
                     r"has attracted (wide|growing|increasing) attention",
                     r"with the (rapid )?development of",
                     r"in recent years, with the",
                     r"a growing body of (research|literature|work)"],
        "description": "无信息增量的衔接套话与重要性自夸，删后句意不变",
        "positive_example": "It is worth noting that the segments were "
                            "recorded at one site.",
        "negative_example": "Worth noting as a limitation: all segments "
                            "came from one site.",
        "suggestion": "删套话外壳、直陈事实；事实本身若是限定条件，"
                    "按限定条件写进局限或方法（信息守恒：不许删限定语）",
    },
    {
        "rule_id": "tone.en.ordinal_scaffold", "language": "en",
        "name": "序数词脚手架（First/Second/Third 成串）",
        "kind": "ordinal",
        "patterns": [],
        "description": "无真实先后关系的并列内容被序数词排成伪序列",
        "positive_example": "First, the data are diverse. Second, the "
                            "method is simple. Third, the results are "
                            "robust. Finally, the cost is low.",
        "negative_example": "First, segments were extracted. Second, "
                            "each segment was scored. Finally, scores "
                            "were aggregated.",
        "suggestion": "并列要点改用各自的小标题或主题句；只有真实时序"
                    "（操作步骤）才保留序数（见不改表）",
    },
    {
        "rule_id": "tone.en.adjacent_isostructural", "language": "en",
        "name": "相邻句结构同款",
        "kind": "structure",
        "patterns": [],
        "description": "连续三句以上以同一内容词开篇、同款句式推进，"
                       "是模板化生成的典型表面特征（功能词开篇与"
                       "参考文献条目等非正文行不计，口径经 D02 语料"
                       "对照修订）",
        "positive_example": "Method A improves recall. Method A "
                            "improves precision. Method A improves "
                            "robustness.",
        "negative_example": "The model improves recall and precision. "
                            "Robustness, however, is unchanged.",
        "suggestion": "合并同构句或变换主语与句式重心；合并时逐项保留"
                    "原句的限定条件",
    },
    {
        "rule_id": "tone.zh.boilerplate_opener", "language": "zh",
        "name": "套话开场",
        "kind": "pattern",
        "patterns": ["值得注意的是", "不难发现", "众所周知",
                     "综上所述", "总而言之", "显而易见"],
        "description": "以套话开场替代论证衔接，删后句意不变",
        "positive_example": "值得注意的是，本研究只使用了一个场的片段。",
        "negative_example": "需要注意的一个限定是：片段只来自一个场。",
        "suggestion": "删套话、直陈内容；若内容是限定条件，按限定条件"
                    "落到方法或局限节（信息守恒：不许删限定语）",
    },
    {
        "rule_id": "tone.zh.translationese", "language": "zh",
        "name": "翻译腔句式",
        "kind": "pattern",
        "patterns": [r"随着[^。！？]{1,30}的发展",
                     "具有重要的理论意义和现实意义",
                     "为[^。！？]{1,20}提供了新的思路",
                     "日益受到(广泛)?关注"],
        "description": "英式句法直译的空转句式：随着……的发展、"
                       "具有重要的……意义类无信息增量表述",
        "positive_example": "随着视频分析技术的发展，行为检测日益受到"
                            "广泛关注。",
        "negative_example": "2020 年以来，养殖场视频行为检测的公开数据"
                            "集从 2 个增至 9 个。",
        "suggestion": "换成可核的具体陈述（时间、数量、事件）；无具体"
                    "内容可陈述时整句删（先过信息守恒检查）",
    },
    {
        "rule_id": "tone.zh.ordinal_scaffold", "language": "zh",
        "name": "序数枚举脚手架（首先/其次/再次成串）",
        "kind": "ordinal",
        "patterns": [],
        "description": "无真实先后关系的并列内容被序数词排成伪序列",
        "positive_example": "首先，数据多样。其次，方法简单。再次，"
                            "结果稳健。最后，成本低廉。",
        "negative_example": "首先提取片段。其次逐段打分。最后汇总得分。",
        "suggestion": "并列要点改用小标题或主题句；只有真实时序"
                    "（操作步骤）才保留序数（见不改表）",
    },
    {
        "rule_id": "tone.zh.adjacent_isostructural", "language": "zh",
        "name": "相邻句结构同款",
        "kind": "structure",
        "patterns": [],
        "description": "连续三句以上以同一双字开篇、同款句式推进，"
                       "是模板化生成的典型表面特征",
        "positive_example": "本方法提高了召回率。本方法提高了精确率。"
                            "本方法提高了稳健性。",
        "negative_example": "本方法提高了召回率与精确率，但稳健性没有"
                            "变化。",
        "suggestion": "合并同构句或变换主语与句式重心；合并时逐项保留"
                    "原句的限定条件",
    },
]

# 不改表（与规则同等地位）：下列特征实测与人类写作无差别或属学术
# 语体构成，永不作程式化报警依据，改写时不许据此动手。
TONE_NOT_CHANGE = [
    {"feature": "sentence_length_variance", "scope": "en/zh",
     "note": "句长参差：长短句交错是人类写作常态，不作 AI 味证据"},
    {"feature": "passive_voice", "scope": "en/zh",
     "note": "被动句：方法节被动语态是规范常态，不许以被动率报警"},
    {"feature": "nominalization", "scope": "en/zh",
     "note": "名词化：术语名词化是学术语体的构成方式，不许据此改写"},
    {"feature": "hedging_and_qualifiers", "scope": "en/zh",
     "note": "限定与对冲词：承载证据强度，信息守恒——核查只报不改，"
             "改写不许删限定词"},
    {"feature": "ordinal_real_sequence", "scope": "en/zh",
     "note": "真实时序的序数步骤：操作流程的真实先后用序数是合法"
             "结构；序数脚手架规则只提示复核是否为空转衔接"},
    {"feature": "intentional_parallelism", "scope": "en/zh",
     "note": "有意排比：内容逐项不同的平行结构是修辞选择，与同构"
             "空转的区别在内容，不在句式"},
]


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
