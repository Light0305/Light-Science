"""状态词规范化映射表（LD-03）：各包状态值 → leader 规范态。

背景：各包终态词互不相同（delivered / handed_off / submission_ready /
frozen / finalized 两档各行其是），各包内部状态机不动（既定裁决），
由 leader 侧持一张规范化映射表，把逐包状态值翻译为规范态供 status
汇总呈现与 route 判读。成文版在 SKILL.md §7，与本模块同源；映射表
变更须走与各包 SKILL 对表的显式动作，不许静默改（改表先改 SKILL、
再改本模块、并跑覆盖断言）。

规范态五值：未建 / 进行中 / 已达终态 / 被门拦 / 旁路。
- 未建是阶段级读数（无登记头），不出现在逐值映射里；
- 映射表外的状态值 canonical() 返回 None：原样呈现、不 reinterpret。

已知状态值的来源（2026-10-21 对各包 schema 状态常量逐个实核）：
idea MAIN_STATES + BYPASS_STATES、design MAIN_STATES + BYPASS_STATES、
experiment PKG_STATES、analysis PKG_STATES、journal-select STATES、
write STATES、figure STATES、review PKG_STATES、literature
PAPER_STATUSES（逐篇词汇，另含索引中实际出现的中文词「速读完成」）。
归类判断（本步自主判断 J1/J2，见 20-build/phase3-leader.md）：
- blocked（design / experiment / analysis）归被门拦：三包 blocked 均
  须带原因与解阻条件、解阻前不得推进，与门语义同构；
- design returned、idea killed / parked、literature excluded 归旁路；
- journal-select 的 gated 是主线步骤名（风险门核查步），归进行中，
  不因字面含 gate 误判为被门拦；
- literature 只作逐篇词汇标注：精读完成归已达终态，其余主线态归
  进行中；route 不据此改变 literature 的既有判定。
"""

from __future__ import annotations

#: 规范态（阶段级「未建」由 scan 的 found=False 表达，不入逐值表）。
CANONICAL_STATES = ("进行中", "已达终态", "被门拦", "旁路")

#: 逐阶段已知状态值（顺序按各包状态机主线在前、旁路在后）。
KNOWN_STATES = {
    "literature": ("ingested", "find_failed", "parsed", "speed_read",
                   "速读完成", "verified", "精读完成", "excluded"),
    "idea": ("draft", "screened", "novelty_checked", "pre_mortem_passed",
             "finalized_executable", "finalized_conceptual",
             "killed", "parked"),
    "design": ("draft", "reviewed", "frozen", "returned", "blocked"),
    "experiment": ("intake", "sanity", "executing", "reconciling",
                   "delivered", "blocked"),
    "analysis": ("intake", "checked", "judged", "graded", "delivered",
                 "blocked"),
    "journal-select": ("draft", "candidates_ready", "verified", "gated",
                       "decided", "handed_off"),
    "write": ("intake", "outlined", "drafted", "audited",
              "submission_ready"),
    "figure": ("intake", "contracted", "produced", "audited",
               "delivered"),
    "review": ("intake", "forensic_checked", "paneled", "reported",
               "adjudicated", "delivered"),
    # memory 横贯层无流水线状态机，不入表（scan 只报四账计数）。
    # LD-02 扩展位三包（v1.1 集成步补入，状态词逐包对各包 schema
    # 状态常量实核）：patent 十二态见 light_patent 案件状态词表；
    # software-copyright 八态见 light_copyright/schema.py 的 STATES；
    # crawler 只登记工作区头 status（active / attention，见
    # light_crawler/project.py 的机械置位），目标级预检状态词
    # （effective / pending_confirmation / blocked / incomplete）
    # 是逐目标读数、非工作区状态，不入本表。
    "patent": ("intake", "audited", "mined", "searched", "drafted",
               "checked", "filed", "office_action", "responded",
               "granted", "closed", "abandoned"),
    "software-copyright": ("draft", "facts_confirmed", "frozen",
                           "materials_ready", "confirmed",
                           "release_checked", "packaged", "correcting"),
    "crawler": ("active", "attention"),
}

#: 状态值 → 规范态（逐阶段）。与 KNOWN_STATES 一一对应，覆盖由测试断言。
STATUS_MAP = {
    "literature": {
        "ingested": "进行中", "find_failed": "进行中", "parsed": "进行中",
        "speed_read": "进行中", "速读完成": "进行中", "verified": "进行中",
        "精读完成": "已达终态", "excluded": "旁路",
    },
    "idea": {
        "draft": "进行中", "screened": "进行中",
        "novelty_checked": "进行中", "pre_mortem_passed": "进行中",
        "finalized_executable": "已达终态",
        "finalized_conceptual": "已达终态",
        "killed": "旁路", "parked": "旁路",
    },
    "design": {
        "draft": "进行中", "reviewed": "进行中", "frozen": "已达终态",
        "returned": "旁路", "blocked": "被门拦",
    },
    "experiment": {
        "intake": "进行中", "sanity": "进行中", "executing": "进行中",
        "reconciling": "进行中", "delivered": "已达终态",
        "blocked": "被门拦",
    },
    "analysis": {
        "intake": "进行中", "checked": "进行中", "judged": "进行中",
        "graded": "进行中", "delivered": "已达终态", "blocked": "被门拦",
    },
    "journal-select": {
        "draft": "进行中", "candidates_ready": "进行中",
        "verified": "进行中", "gated": "进行中", "decided": "进行中",
        "handed_off": "已达终态",
    },
    "write": {
        "intake": "进行中", "outlined": "进行中", "drafted": "进行中",
        "audited": "进行中", "submission_ready": "已达终态",
    },
    "figure": {
        "intake": "进行中", "contracted": "进行中", "produced": "进行中",
        "audited": "进行中", "delivered": "已达终态",
    },
    "review": {
        "intake": "进行中", "forensic_checked": "进行中",
        "paneled": "进行中", "reported": "进行中",
        "adjudicated": "进行中", "delivered": "已达终态",
    },
    # 扩展位归类（LD-02 集成步判断）：patent 的 granted（授权）与
    # closed（结案）为案件终局，abandoned（放弃）是权利人主动退出
    # 的旁路；software-copyright 的 packaged 是 v1 终点（材料包 +
    # 递交清单产出），correcting 是补正旁路（包内 STATES 注释同口
    # 径）；crawler 工作区 attention 仅在存在熔断目标时由其代码机
    # 械置位——熔断即抓取被停、须具名解阻，与被门拦语义同构。
    "patent": {
        "intake": "进行中", "audited": "进行中", "mined": "进行中",
        "searched": "进行中", "drafted": "进行中", "checked": "进行中",
        "filed": "进行中", "office_action": "进行中",
        "responded": "进行中", "granted": "已达终态",
        "closed": "已达终态", "abandoned": "旁路",
    },
    "software-copyright": {
        "draft": "进行中", "facts_confirmed": "进行中",
        "frozen": "进行中", "materials_ready": "进行中",
        "confirmed": "进行中", "release_checked": "进行中",
        "packaged": "已达终态", "correcting": "旁路",
    },
    "crawler": {
        "active": "进行中", "attention": "被门拦",
    },
}


def canonical(stage: str, status) -> str | None:
    """状态值的规范态；未知阶段/未知值/缺失一律 None（原样呈现，不猜）。"""
    if not status:
        return None
    return STATUS_MAP.get(stage, {}).get(status)
