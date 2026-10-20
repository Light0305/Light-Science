"""light-patent 词表与登记表（单一事实源）。

含：案件状态词表、分级声明原文、支持状态四值、专利法第 24 条
宽限四情形、渠道登记表（Q3，含可审计性/可复现性一等字段）、
不确定词表、过程词表（正文洁净）、政策雷达种子条目（84 号令，
信源 A 级 = CNIPA 官方决定原文）。

规范锚点：专利法（2020 年修正）；专利法实施细则（2023 年修订）；
专利审查指南（含局令第 84 号修改，2026-01-01 施行）。引用实施
细则条号一律带版本年。
"""

from __future__ import annotations

# ---------------------------------------------------------------- 声明分级（Q4）

#: 一级：全案一切交付物固定携带。
DRAFT_DISCLAIMER = "草案，需专利代理师复核"
#: 二级：初筛类产物（查新结论、worth-it 判断、FTO/对照类底稿）再加一级。
SCREENING_DISCLAIMER = "只作初筛底稿、不作法律意见"

# ---------------------------------------------------------------- 案件状态

CASE_STATES = (
    "intake", "audited", "mined", "searched", "drafted", "checked",
    "filed", "office_action", "responded", "granted", "closed",
    "abandoned",
)

#: 状态推进的最小前置（validate 用；不许跳段落字）。
STATE_ORDER = {name: i for i, name in enumerate(CASE_STATES)}

PATENT_TYPES_V1 = ("invention",)  # Q1：v1 只做发明
JURISDICTIONS_V1 = ("CN",)         # Q2：v1 只做中国

# ---------------------------------------------------------------- 输入四路（Q5）

INPUT_ROUTES = ("paper", "code", "experiment", "oral")
#: 口头交底只作补充输入：其单独支撑的特征至多 needs-confirmation。
ORAL_ONLY_SUPPORT_CAP = "needs-confirmation"

CANDIDATE_FIELDS = (
    "candidate_id", "title", "technical_problem", "technical_means",
    "technical_effect", "evidence", "claim_category", "gaps", "risks",
)

#: 源图谱锚点前缀：P 文本块 / E 公式 / F 图 / C 代码（与文献四件套纪律同构）。
SOURCE_KINDS = {"P": "text", "E": "equation", "F": "figure", "C": "code"}

SUPPORT_STATES = ("explicit", "inherent", "needs-confirmation", "unsupported")

# ---------------------------------------------------------------- P0 公开审计

#: 专利法（2020 年修正）第 24 条不丧失新颖性的四种情形。
GRACE_SITUATIONS = (
    "public_interest_first_disclosure",   # 国家紧急/非常情况、为公共利益目的首次公开
    "government_exhibition",              # 中国政府主办或承认的国际展览会首次展出
    "prescribed_academic_meeting",        # 在规定的学术会议或技术会议上首次发表
    "disclosure_without_consent",         # 他人未经申请人同意而泄露
)
GRACE_MONTHS = 6          # 第 24 条：申请日以前六个月内
GRACE_PROOF_MONTHS = 2    # 实施细则（2023 年修订）第 33 条：声明后二个月内提交证明

DISCLOSURE_KINDS = (
    "paper_published", "preprint", "code_public", "conference_talk",
    "thesis_deposited", "product_release", "other",
)

AUDIT_CONCLUSIONS = (
    "clear",                    # 未见公开：先申请后公开
    "grace_possible",           # 宽限内且属四情形：声明 + 2 个月内证明
    "blocked_prior_disclosure", # 已公开且非宽限：论文即现有技术（LP-09 显著告知）
    "unknown",                  # 公开状态未知：待确认，不许进撰写
)

# ---------------------------------------------------------------- 渠道层（Q3/Q9）

#: 渠道登记字段（一等字段含可审计性/可复现性与披露考量）。
CHANNEL_FIELDS = (
    "channel_id", "name", "kind", "mode", "automation_default",
    "requires_login", "auditability", "reproducibility",
    "disclosure_note", "status",
)

#: 内置渠道登记。mode: manual_assist（人工辅助，默认）/ automation
#: （自动化，默认关，开启须登记 crawler 预检引用）/ api（登记制）。
CHANNELS = (
    {
        "channel_id": "cnipa-epub-manual",
        "name": "中国专利公布公告系统（人工辅助）",
        "kind": "official_public",
        "mode": "manual_assist",
        "automation_default": "off",
        "requires_login": False,
        "auditability": "high：官方公布站，著录页 URL 可复查",
        "reproducibility": "high：检索式 + 日期留痕即可复现候选池",
        "disclosure_note": "检索词经浏览器提交官方站；按最小披露构造（分类号 + 手段短语）",
        "status": "default",
    },
    {
        "channel_id": "cnipa-pss-manual",
        "name": "专利检索及分析系统 PSS（人工复核）",
        "kind": "official_public",
        "mode": "manual_assist",
        "automation_default": "off",
        "requires_login": True,
        "auditability": "high：官方系统，登录态人工操作",
        "reproducibility": "medium：登录态会话不可全量复现，靠检索式留痕",
        "disclosure_note": "登录账号内操作；禁止自动化（登录 + 合规边界）",
        "status": "optional",
    },
    {
        "channel_id": "google-patents-manual",
        "name": "Google Patents（著录复核/补充）",
        "kind": "public_database",
        "mode": "manual_assist",
        "automation_default": "off",
        "requires_login": False,
        "auditability": "medium：著录页 URL 稳定可复查",
        "reproducibility": "medium：结果排序随时间漂移，靠快照留痕",
        "disclosure_note": "境内可达性不稳定；只许有限次尝试，失败即跳过并留痕",
        "status": "optional",
    },
    {
        "channel_id": "cnipa-epub-automation",
        "name": "中国专利公布公告系统（自动化抓取）",
        "kind": "official_public",
        "mode": "automation",
        "automation_default": "off",
        "requires_login": False,
        "auditability": "medium：抓取留痕可复查，但站点改版即失效",
        "reproducibility": "low：依赖站点结构稳定性",
        "disclosure_note": "默认关；开启须逐目标过 light-crawler 预检门并登记引用（crawler_precheck_ref），本包只点名不代行其门",
        "status": "gated_off",
    },
    {
        "channel_id": "patsnap-api",
        "name": "智慧芽 API/MCP（厂商渠道）",
        "kind": "vendor_api",
        "mode": "api",
        "automation_default": "off",
        "requires_login": True,
        "auditability": "medium：厂商托管数据，口径以其文档为准",
        "reproducibility": "medium：同式同参可复现，数据版本随厂商更新",
        "disclosure_note": "需商业账号；检索词出境至厂商，登记此考量后再启用",
        "status": "optional",
    },
    {
        "channel_id": "epo-ops-api",
        "name": "EPO Open Patent Services（官方 API）",
        "kind": "official_api",
        "mode": "api",
        "automation_default": "off",
        "requires_login": True,
        "auditability": "high：官方 API，请求参数全留痕",
        "reproducibility": "high：注册 key + 配额内确定性复现",
        "disclosure_note": "欧洲侧数据通道；v1 中国主线只登记不用",
        "status": "optional",
    },
)

# ---------------------------------------------------------------- 查新（P2）

SEARCH_ROUNDS = ("means_phrases", "classification_neighborhood")
#: LP-06 失败分型三态（另加补强第三态：成功但未评估）。
SEARCH_OUTCOMES = ("ok", "channel_failure", "zero_results", "pool_empty_not_evaluated")
EVIDENCE_LEVELS = ("abstract", "full_text")
NOVELTY_GATES = ("pass", "pass_with_doubts", "fail")

# ---------------------------------------------------------------- 撰写（P3）

FEATURE_BOXES = ("necessary", "embodiment_choice", "interface_detail")
CLAIM_TYPES = ("method", "apparatus", "device", "medium", "program_product", "system")
CARRIER_CLAIM_TYPES = ("apparatus", "device", "medium", "program_product")
ABSTRACT_MAX_CHARS = 300        # 审查指南口径：摘要不超 300 字
TITLE_WARN_CHARS = 25           # 发明名称超此长度给 WARN
EXTRA_CLAIM_FEE_FROM = 10       # 权利要求超 10 项起收附加费（每项 150 元，费用减缴另计）

#: 确定性检查的不确定词表（权要正文命中即 ERROR 点名）。
UNCERTAIN_WORDS = (
    "等", "约", "大约", "可以", "例如", "优选", "不限于", "左右",
    "基本", "差不多", "若干", "某种程度上",
)

#: 正文洁净（LP-04）：申报副本中零命中的过程词表。
PROCESS_TOKENS = (
    "查新过程", "支持状态", "撰写说明", "自检记录", "检索工具", "待确认标记",
    "needs-confirmation", "unsupported", "explicit", "inherent",
    "light-patent", "代理师评注",
)

#: AI 类案件充分公开清单（84 号令 6.3.1 撰写要求的操作化）。
AI_SUFFICIENCY_ITEMS = (
    "model_modules",       # 模型必要的模块
    "model_levels_links",  # 层级或者连接关系
    "training_steps_params",  # 训练必需的具体步骤、参数
    "input_output_setting",   # 输入、输出数据如何设置及其内在关联
    "scenario_binding",       # 模型/算法如何与具体领域场景相结合
)

#: 84 号令 6.1.1 伦理审查触发面（专利法第 5 条第 1 款）。
ETHICS_TRIGGER_AREAS = ("数据采集", "标签管理", "规则设置", "推荐决策")

# ---------------------------------------------------------------- 答复（P5）

AMENDMENT_BASES_REQUIRED = True  # LP-08：修改必须带原申请文件出处指针（专利法第 33 条）

# ---------------------------------------------------------------- 台账（P6）

PRIORITY_MONTHS = 12   # 优先权/PCT 国际申请窗
WORTH_IT_VERDICTS = ("file", "file_narrowed", "abandon")

# ---------------------------------------------------------------- 政策雷达（P7 lite）

POLICY_SOURCE_GRADES = ("A", "B")  # A 官方原文可支撑口径；B 不得单独改口径

#: 种子条目：局令第 84 号五项（信源 = CNIPA 官网决定原文，A 级）。
POLICY_RADAR_SEED = (
    {
        "entry_id": "PR-2026-001",
        "title": "AI/大数据专节第 6.1.1 节：专利法第 5 条第 1 款伦理审查",
        "source_grade": "A",
        "source": "国家知识产权局局令第 84 号决定原文（审查指南第二部分第九章第 6 节）",
        "effective": "2026-01-01",
        "summary": "数据采集、标签管理、规则设置、推荐决策等含有违反法律、社会公德或者妨害公共利益内容的，不能授予专利权。",
        "impact_disclosure": "交底阶段先行伦理自查：涉个人信息/歧视性决策的方案在交底书中单列说明与合规依据。",
        "impact_drafting": "权要与说明书避免把违规数据处理写成技术特征；命中触发面时先落伦理审查登记再撰写。",
    },
    {
        "entry_id": "PR-2026-002",
        "title": "第 6.3.1 节：AI 模型充分公开的撰写要求",
        "source_grade": "A",
        "source": "国家知识产权局局令第 84 号决定原文（审查指南第二部分第九章第 6.3.1 节）",
        "effective": "2026-01-01",
        "summary": "涉及模型构建/训练的，说明书须清楚记载模型必要的模块、层级或者连接关系，训练必需的具体步骤、参数等；涉及场景应用的，须记载模型如何与场景相结合、输入输出数据如何设置以表明内在关联。",
        "impact_disclosure": "交底书对 AI 方案须挖齐模块/层级/连接、训练步骤参数、输入输出设置三组材料，缺项进缺口清单。",
        "impact_drafting": "说明书按充分公开清单逐项落字；例 21 式（只给数据名目、不给关键指标与因果依据）为判败样本。",
    },
    {
        "entry_id": "PR-2026-003",
        "title": "第二部分第四章第 6.4 节：创造性贡献特征须入权要",
        "source_grade": "A",
        "source": "国家知识产权局局令第 84 号决定原文",
        "effective": "2026-01-01",
        "summary": "对现有技术作出贡献的技术特征应当写入权利要求；未写入的，评价创造性时不予考虑；对解决技术问题没有贡献的特征写入权要通常也不带来创造性。",
        "impact_disclosure": "交底候选点须标明哪些特征对技术问题有贡献，查新区别特征 Fk 与贡献标注对齐。",
        "impact_drafting": "独权特征三箱分拣以贡献为准：贡献特征必入权要，非贡献特征不许用来凑创造性论述。",
    },
    {
        "entry_id": "PR-2026-004",
        "title": "新增第二部分第九章第 7 节：比特流审查与撰写",
        "source_grade": "A",
        "source": "国家知识产权局局令第 84 号决定原文",
        "effective": "2026-01-01",
        "summary": "单纯比特流属专利法第 25 条第 1 款第 (二) 项客体排除；由特定视频编码方法限定的存储/传输方法与存储介质属第 2 条第 2 款技术方案；此类权要一般应以编码方法权要为基础引用或包含其全部特征撰写。",
        "impact_disclosure": "涉编解码/流媒体的交底须先定编码方法方案，比特流只作从属形态登记。",
        "impact_drafting": "禁止单独撰写比特流权要；存储/传输/介质权要必须回引编码方法权要。",
    },
    {
        "entry_id": "PR-2026-005",
        "title": "第一部分第一章第 4.1.2 节：发明人须自然人且身份信息真实",
        "source_grade": "A",
        "source": "国家知识产权局局令第 84 号决定原文",
        "effective": "2026-01-01",
        "summary": "发明人应当是个人（即自然人），请求书中应当填写所有发明人的身份信息并确保真实；不得填写单位、集体或人工智能名称；不得填写虚假的发明人。",
        "impact_disclosure": "交底登记发明人只记自然人姓名与贡献对应，身份信息线下核对、不落本包文件。",
        "impact_drafting": "请求书信息确认表中发明人栏出现单位/集体/AI 名称即校验拦截。",
    },
)

# ---------------------------------------------------------------- 评测集（Q10）

#: 只借形态：IPBench 的 DOK 四级分层。
DOK_LEVELS = ("L1_information", "L2_reasoning", "L3_evaluation", "L4_creation")
