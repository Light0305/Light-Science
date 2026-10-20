"""阶段规格表：全链接口图的机器可读形态（SKILL.md §2 与此表同源）。

每阶段登记：阶段 id、技能名、标准目录、状态载体（登记头文件名与状态
字段）、终态集合、开工条件与交接去向。总控的 status/route 全部由此
表驱动；各包内部布局细节不在此表内（只指针引用各包 SKILL）。
"""

from __future__ import annotations

#: 流水线顺序（Journal-Select 是 Write 前置扩展位，排在 Analysis 与
#: Write 之间；Figure 在 Write 成稿后可并行；Memory 横贯全程单列）。
PIPELINE = (
    "literature", "idea", "design", "experiment", "analysis",
    "journal-select", "write", "figure", "review",
)

STAGES = {
    "literature": {
        "skill": "light-literature",
        "dir": "literature",
        "carrier": "Literature/文献索引.csv（逐篇 status 列）",
        "header": "文献索引.csv",
        "terminal": (),  # 无状态机：以索引中出现精读完成篇目为可用标志
        "opens_when": "项目启动即可（全链源头）",
        "hands_to": "证据表.jsonl 与精读卡供 Idea/Design 承接；参考文献.bib 是 Write 引用的唯一来源",
    },
    "idea": {
        "skill": "light-idea",
        "dir": "idea",
        "carrier": "cards/<idea_id>/idea.yaml 的 status 字段",
        "header": "idea.yaml",
        "terminal": ("finalized_executable", "finalized_conceptual"),
        "design_ready": ("finalized_executable",),
        "opens_when": "Literature 证据表已有可用证据行",
        "hands_to": "定版卡导出 design_handoff.md + idea_card.json + memory_export.jsonl 供 Design 承接",
    },
    "design": {
        "skill": "light-design",
        "dir": "design",
        "carrier": "designs/<design_id>/design.yaml 的 status 字段",
        "header": "design.yaml",
        "terminal": ("frozen",),
        "opens_when": "Idea 有 finalized_executable 定版卡（conceptual 级不得直接开工）",
        "hands_to": "冻结后导出 experiment_brief.md + design_card.json + expected_registry.jsonl + reproducibility.md 供 Experiment 承接",
    },
    "experiment": {
        "skill": "light-experiment",
        "dir": "experiment",
        "carrier": "executions/<exec_id>/execution.yaml 的 status 字段",
        "header": "execution.yaml",
        "terminal": ("delivered",),
        "opens_when": "Design 已 frozen 且交接四件套齐备",
        "hands_to": "执行包（execution_card + events + reconciliation）供 Analysis 承接",
    },
    "analysis": {
        "skill": "light-analysis",
        "dir": "analysis",
        "carrier": "analysis.yaml 的 status 字段",
        "header": "analysis.yaml",
        "terminal": ("delivered",),
        "opens_when": "Experiment 执行包已 delivered",
        "hands_to": "结论包（conclusion_card + verdicts + conclusions）供 Journal-Select 指纹与 Write 主张登记承接",
    },
    "journal-select": {
        "skill": "light-journal-select",
        "dir": "journal-select",
        "carrier": "selection.yaml 的 status 字段",
        "header": "selection.yaml",
        "terminal": ("handed_off",),
        "opens_when": "Analysis 结论包已 delivered（Write 前置扩展位：先选刊再开写）",
        "hands_to": "定刊后 handoff 产物落项目 journal/target/（check-record.json 九组 + 下载清单），供 Write intake 消费",
    },
    "write": {
        "skill": "light-write",
        "dir": "write",
        "carrier": "manuscript.yaml 的 status 字段",
        "header": "manuscript.yaml",
        "terminal": ("submission_ready",),
        "opens_when": "Analysis 结论包 delivered + Journal-Select 已 handed_off（模板记录与目标刊就位）",
        "hands_to": "稿件包（audited 后）供 Review 承接；投稿后真实审稿意见的返修走 Write 自己的 W7",
    },
    "figure": {
        "skill": "light-figure",
        "dir": "figure",
        "carrier": "figure.yaml 的 status 字段",
        "header": "figure.yaml",
        "terminal": ("delivered",),
        "opens_when": "Write 章节已 drafted（可与 Write 后段并行，不必等 submission_ready）",
        "hands_to": "图包 delivery 供 Write 的 figures_manifest 对账与 Review 的数字↔图对账承接",
    },
    "review": {
        "skill": "light-review",
        "dir": "review",
        "carrier": "review.yaml 的 status 字段",
        "header": "review.yaml",
        "terminal": ("delivered",),
        "opens_when": "Write 稿件包已 audited（投稿前内部评审；以是否已收到真实审稿意见为界，未收到归 Review、已收到归 Write W7）",
        "hands_to": "评审交付 + handoff_to_write 回填清单供 Write 修订；concern 关闭史供 Memory 收编",
    },
    "memory": {
        "skill": "light-memory",
        "dir": "memory",
        "carrier": "memory.yaml 登记头 + objects/events/facts/relations 四账",
        "header": "memory.yaml",
        "terminal": (),  # 横贯层，无终态
        "opens_when": "任一阶段有产物即可建；收编触发点在各阶段的定版/终态点",
        "hands_to": "registry-view.json 对象注册统一视图供总控 registry 消费；recall 回供各阶段开工",
    },
}

#: 扩展位登记（LD-02，v1.1 集成步定版）：新三包不入十阶段主流水线，
#: 按 journal-select 前置扩展位的先例分置——patent 与
#: software-copyright 为出口层扩展位（与 review 之后并列的权利固化
#: 出口），crawler 为通道层扩展位（供 literature / experiment 的
#: 数据入口）。本表只登记总控需要知道的形态（项目内落点、状态载体、
#: 终态、触发条件）；包内规程以各包 SKILL 为准。status 汇总读其登记
#: 头，route 只在触发条件成立时点名提示，不给必经下一步、不影响
#: 主流水线的收官判定。
EXTENSIONS = {
    "patent": {
        "skill": "light-patent",
        "slot": "出口层扩展位",
        "dir": "patent/cases",
        "carrier": "cases/<case_id>/case.yaml 顶层 status"
                   "（kind=light-patent/case）+ ledger.yaml 期限清单",
        "header": "case.yaml",
        "terminal": ("granted", "closed"),
        "trigger": "成果成形后可随时启动；案件期限（答复期、优先权窗"
                   "等）由 route 按台账到期日点名提醒",
        "hands_to": "案件状态流转/期限/答复节点由 light-memory 的 "
                    "patent 适配器收编",
    },
    "software-copyright": {
        "skill": "light-software-copyright",
        "slot": "出口层扩展位",
        "dir": "软件著作权申请资料",
        "carrier": "案件根 copyright.yaml 顶层 status",
        "header": "copyright.yaml",
        "terminal": ("packaged",),
        "trigger": "项目内软件已定版时提示启动；进入补正回路"
                   "（correcting）时 route 点名补正期限",
        "hands_to": "定版/递交/补正/登记号回填节点由 light-memory 的 "
                    "software-copyright 适配器收编",
    },
    "crawler": {
        "skill": "light-crawler",
        "slot": "通道层扩展位",
        "dir": "data-sources",
        "carrier": "data-sources/crawler.yaml（工作区头） + "
                   "targets/<target_id>/target.yaml 与 state.yaml + "
                   "prechecks/<target_id>.jsonl 末行预检状态",
        "header": "crawler.yaml",
        "terminal": (),  # 通道层无终态：工作区持续可用
        "trigger": "项目有批量数据采集需求时启用；route 只点名目标的"
                   "预检与熔断状态，不点名采集内容",
        "hands_to": "抓取批次/预检/变更事件由 light-memory 的 "
                    "crawler 适配器收编",
    },
}

#: init 骨架要建的目录（阶段目录 + 选刊交接落点 + 项目级材料位 +
#: LD-02 扩展位落点：专利案件目录、软著案件目录、爬虫 data-sources）。
SCAFFOLD_DIRS = (
    "literature",
    "idea/cards",
    "design/designs",
    "experiment",
    "analysis",
    "journal-select",
    "journal/target/guideline",
    "journal/target/templates",
    "write",
    "figure",
    "review",
    "memory",
    "patent/cases",
    "软件著作权申请资料",
    "data-sources",
)

#: REVIEW_UNAVAILABLE 式硬门在各包登记头里的落点（route 据此点名）。
#: 字段名或路径逐包不同，值含 REVIEW_UNAVAILABLE 即视为门未过。
#: 这是 GATE_FIELD_FAMILIES 中 review_unavailable 族的逐包字段表。
GATE_FIELDS = {
    "idea": ("review_status",),          # 查新区 review_status
    "design": ("review_status",),        # freeze.review.review_status
    "analysis": ("review_status",),      # 复核区 review_status；另有 blocked.reason
    "write": ("submission_blocked_reason", "review_status"),
}

#: 硬门字段族登记表（LD-04）：route 只消费登记过的字段族，未登记的
#: 字段一律不解读。成文版在 SKILL.md §5，与本表同源；新门要被 route
#: 点名，先在此登记字段族（并与对应包对表），不许在 route 里临时加读。
#: 字段缺失行为：缺某族字段 = 该族无命中，不等于无门（见 SKILL §5）。
GATE_FIELD_FAMILIES = {
    "review_unavailable": {
        "desc": "跨家族复核不可用门（现行四包）：字段 review_status / "
                "submission_blocked_reason，值含 REVIEW_UNAVAILABLE；"
                "analysis 另认 blocked.reason 含该字样",
        "fields_by_stage": GATE_FIELDS,
        "marker": "REVIEW_UNAVAILABLE",
    },
    "blocked_gate": {
        "desc": "统一门字段（v1.1 新约，任一阶段可用）：登记头顶层 "
                "blocked_gate 映射，必备 gate_id，可带 detail 与 "
                "fix_pointer（解法指针）；形态不合不点名、只落字。"
                "字段名变体（LD-02 集成步对表登记）：light-patent 的"
                "案件头以顶层 blocked 字段承载同形映射（其契约先于"
                "本族定版，形态 {gate_id, detail, fix_pointer} 一致）",
        "field": "blocked_gate",
        "fields_by_stage": {"patent": "blocked"},
    },
    "return_block": {
        "desc": "打回/阻塞记录族（design 先行）：status=returned 时读 "
                "return_record.returned_items（缺项单，未回补项逐项点名）；"
                "status=blocked 时读 block_record 的 reason 与 "
                "unblock_condition（解阻条件即解法指针）",
        "stages": ("design",),
    },
}

GATE_FIX_POINTER = (
    "解法：把该包的复核包（review packet）交异家族模型复核，判定经该包"
    "自带的回填命令落账；在复核不可用期间状态停在原地，不许伪造收据"
    "（见各包 SKILL 的 REVIEW_UNAVAILABLE 降级纪律）。"
)
