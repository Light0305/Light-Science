"""精读卡生成：从 paper.yaml + source_map.json 生成 阅读笔记.md 骨架。

骨架依据 deep-read-A.md 第五节 5.2 的本地化版本：文件头与证据状态头自动
生成；速读段 S1–S7 是精读流水线的中间检查点（不是终点——本项目口径为
入库默认直接精读 16 节精读卡）；S4 图表清单从 source_map 自动盘点；
精读 16 节逐节生成，每节带一行 HTML 注释写明该节的证据纪律。
笔记内容由执行 agent 按 SKILL.md 填写，本模块只保证结构与纪律约束。
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from .util import load_paper_yaml, read_json, save_paper_yaml

_TODO = "（待填）"


def _evidence_status(pdir: Path, paper: dict, smap: dict) -> dict:
    """证据状态头四项的初值：由 source_map 与（若已存在的）verify 报告推导。"""
    pending = smap.get("pending_pages", [])
    if paper.get("source_version") == "abstract_only":
        coverage = "Abstract only"
    elif pending:
        coverage = "Partial"
    else:
        coverage = "Full"

    anchored = [b for b in smap["blocks"] if b.get("id")]
    confs = [b.get("confidence") for b in anchored if b.get("confidence") is not None]
    mean_conf = sum(confs) / len(confs) if confs else 0.0
    level = "High" if mean_conf >= 0.85 else "Mixed" if mean_conf >= 0.6 else "Low"
    report_path = pdir / "verify_report.json"
    if report_path.exists():
        report = read_json(report_path)
        if not report.get("ok"):
            level = {"High": "Mixed", "Mixed": "Low", "Low": "Low"}[level]
    return {
        "Source coverage": coverage,
        "Extraction confidence": level,
        "Locator mode": paper.get("locator_mode", "page-grounded"),
        "Context verification": "Paper-only",
    }


def _s4_inventory(smap: dict) -> tuple[list[str], int]:
    """S4 图表清单：F/T/E 盘点（编号、页、配对图注、论证角色待填）。

    图自第六增量起按图组呈现：一幅图拆成多个 F 分片时只出一行（编号
    列出全部分片与组 ID、图注为整组共享的那一条），避免把一幅图盘点
    成多幅；无 group_id 的旧版 source_map 中每个 F 块自成一组。
    """
    anchored = [b for b in smap["blocks"] if b.get("id")]
    anchored.sort(key=lambda b: b.get("order") or 0)
    rows = []
    seen_groups: set[tuple] = set()
    fig_groups: dict[tuple, list[dict]] = {}
    for b in anchored:
        if b["type"] == "figure":
            key = (b["page"], b.get("group_id") or b["id"])
            fig_groups.setdefault(key, []).append(b)
    for b in anchored:
        if b["type"] == "figure":
            key = (b["page"], b.get("group_id") or b["id"])
            if key in seen_groups:
                continue  # 同组分片只在首块处出整组一行
            seen_groups.add(key)
            members = fig_groups[key]
            cap = next((m.get("caption_id") for m in members
                        if m.get("caption_id")), None) or "no_caption"
            if len(members) > 1:
                ids = "+".join(m["id"] for m in members)
                rows.append(
                    f"| {ids}（图组 {key[1]}，{len(members)} 分片） "
                    f"| p.{b['page']} | 图 | {cap} | {_TODO} |")
            else:
                rows.append(
                    f"| {b['id']} | p.{b['page']} | 图 | {cap} | {_TODO} |")
        elif b["type"] == "table":
            cap = b.get("caption_id") or "no_caption"
            rows.append(
                f"| {b['id']} | p.{b['page']} | 表 | {cap} | {_TODO} |")
        elif b["type"] == "equation":
            rows.append(
                f"| {b['id']} | p.{b['page']} | 公式 | — | {_TODO} |")
    return rows, len(rows)


# 精读 16 节：(节名, 纪律注释, 正文骨架)
_SECTIONS_16: list[tuple[str, str, str]] = [
    ("基本信息", "纪律：只写可核查的元数据；代码/数据链接须实际打开验证过才许写，无则写「未提供」。",
     "- 题名/作者/venue/年份/DOI：见文件头\n"
     "- 代码仓库：（待填，须核实许可证与可运行状态）\n"
     "- 数据链接：（待填）\n"
     "- 术语账本入口：../术语账本.md（本篇新术语先补账本）"),
    ("一句话总结", "纪律：沿用速读 S1，可修订但保留修订痕（旧版划改或注记）；一句话，禁宣传形容词，标 [Paper]。",
     f"{_TODO} [Paper]"),
    ("研究问题", "纪律：问题须具体到可判定是否被回答；指针回指摘要/引言块。",
     f"{_TODO}（指针：原文.md#S___）"),
    ("背景与发展路径", "纪律：每条背景陈述标明是 paper-framed（作者自述脉络）还是 externally verified（已外部核实），两者不许混写。",
     f"- 作者自述脉络 [Paper]：{_TODO}\n- 外部核实 [External]：{_TODO}"),
    ("核心痛点", "纪律：痛点须是原文证据支持的具体困难，不许把「效果不好」式空话写成痛点；每行带原文位置。",
     "| 痛点 | 表现 | 根源 | 原文位置 |\n|---|---|---|---|\n"
     f"| {_TODO} | {_TODO} | {_TODO} | 原文.md#S___ |"),
    ("核心思想", "纪律：分三层写——表面方法 / 核心洞见 / 我们的推断；第三层必须标 [Analysis] 并给推理所依据的源指针。",
     f"1. 表面方法 [Paper]：{_TODO}\n2. 核心洞见 [Paper]：{_TODO}\n"
     f"3. 推断 [Analysis]：{_TODO}"),
    ("方法概览", "纪律：输入→输出文本流须与原文方法节一致；假设清单逐条列出（含作者未明说但方法成立所必需的隐含假设，标 [Analysis]）。",
     f"- 输入 → 处理 → 输出：{_TODO}\n- 假设清单：{_TODO}"),
    ("核心模块拆解", "纪律：消融实测与预期分开写——作者真跑过的消融标「实测」，只有文字论述的标「预期」，不许混为一谈。",
     "| 模块 | 输入 | 输出 | 机制 | 消融证据（实测/预期） | 原文位置 |\n"
     "|---|---|---|---|---|---|\n"
     f"| {_TODO} | {_TODO} | {_TODO} | {_TODO} | {_TODO} | 原文.md#S___ |"),
    ("关键公式与符号", "纪律：只收理解方法必需的公式；一律引用 E 锚点不复制公式本体；文本层置信低的公式附原图位置待视觉复核。",
     f"- 公式：原文.md#E___（用途：{_TODO}；符号：{_TODO}）"),
    ("实验设计与证据链", "纪律：先记评测协议（数据/基线/指标/预算）再记结果；「不支持的更强结论」必填，不许只写支持面；嵌关键原图/表用 F/T 卡格式并逐项解释，不许只贴图。",
     "- 评测协议：（待填：数据集、基线、指标、比较预算）\n\n"
     "| 实验 | 目的 | 设置/协议 | 指标 | 关键结果（逐字） | 支持的结论与强度 | 原文位置 |\n"
     "|---|---|---|---|---|---|---|\n"
     f"| {_TODO} | {_TODO} | {_TODO} | {_TODO} | {_TODO} | {_TODO} | 原文.md#S___ |\n\n"
     f"**不支持的更强结论（必填）：** {_TODO}\n\n"
     "图/表卡（按需）：\n\n"
     "> ![F___](assets/figures/___)\n"
     "> 原图注：（引用 C 锚点）\n"
     "> 逐项解释：（待填：每个子图/列在证明什么）"),
    ("结论的正确解释", "纪律：先做边界审计逐项核对，再写有界重述；重述的每处限定（数据/条件/指标）都须有原文依据，结论不许比证据更强。",
     f"- 边界审计：{_TODO}（逐项核对适用条件、数据范围、指标口径、基线强度、不确定性、因果措辞、外推范围、负结果、版本差异）\n"
     f"- 有界重述 [Paper]：{_TODO}"),
    ("作者明确承认的局限", "纪律：本节只许作者自述的局限；作者没写的写明固定句。Agent 的批评一律写第 13 节，不许混入本节冒充作者自述。",
     "（若作者未自述局限，写明：「作者未在文中自述局限。」）"),
    ("批判分析", "纪律：全部标 [Analysis]；只收可证伪的关切（能说清什么证据出现时关切成立/消解），不收泛泛质疑。",
     "| 关切 | 依据 | 可证伪点 | 若成立的影响 | 原文位置 |\n|---|---|---|---|---|\n"
     f"| [Analysis] {_TODO} | {_TODO} | {_TODO} | {_TODO} | 原文.md#S___ |"),
    ("学到的知识（Agent 衍生的知识候选）", "纪律：本节为 Agent 衍生内容（用户亲自确认后才可去掉标题中的候选标记）；每条知识注明出处指针，不许写成普适真理。",
     f"- {_TODO}（出处：原文.md#S___）"),
    ("与已有知识的联系", "纪律：按相似/组合/冲突/可迁移四类写；没有核实过的联系不写——宁可留空，不许凭印象编造关联。",
     f"- 相似：{_TODO}\n- 组合：{_TODO}\n- 冲突：{_TODO}\n- 可迁移：{_TODO}"),
    ("研究想法（Agent 衍生的研究候选）", "纪律：每条想法必须过六道门——可溯源门（系于具体局限/失败/矛盾并带指针）、假设门（可为假的命题，拒空话）、delta 门（指明改的是表示/机制/数据/目标/反馈/评测/部署约束哪一项）、验证门（对照、控制变量、指标、数据、预期观察、证伪结果、预算）、失败门（≥2 个 plausible 失败原因）、新颖措辞门（未专门查新前只许 candidate idea / hypothesis / possible extension，禁用 novel/first/unexplored 与数字创新分）；创新状态三档：unverified / partially checked / prior-art checked。",
     "- 名称：（待填）\n"
     "  - 源自哪条局限/观察：（待填，带指针）\n"
     "  - 核心假设：（待填，须可为假）\n"
     "  - 与本文的 delta：（待填，指明改动项）\n"
     "  - 初步方法：（待填）\n"
     "  - 验证方案：（待填：对照/指标/数据/证伪结果/预算）\n"
     "  - 可能的失败模式：（待填，≥2 条）\n"
     "  - 创新状态：unverified"),
]

_ATOMIC_CARDS = ["金句卡", "概念卡", "反直觉卡", "方法卡", "结构卡"]


def generate_notes(project_dir: Path, paper_id: str) -> dict:
    """生成 阅读笔记.md（速读检查点 + 精读 16 节 + 原子卡附录）骨架。"""
    pdir, paper = load_paper_yaml(project_dir, paper_id)
    smap_path = pdir / "source_map.json"
    if not smap_path.exists():
        raise FileNotFoundError("source_map.json 不存在，先运行 parse（Doc2X 轨）或按 SKILL.md §5 模型直读轨生成")
    smap = read_json(smap_path)
    status = _evidence_status(pdir, paper, smap)
    s4_rows, s4_count = _s4_inventory(smap)
    today = date.today().isoformat()

    parts = [
        f"# 阅读笔记：{paper.get('title', paper_id)}\n",
        "## 文件头（自动生成）\n",
        f"- **题名**：{paper.get('title') or _TODO}",
        f"- **作者**：{_TODO}（paper.yaml 无作者字段，禁止凭记忆填写，须从原文首页核对）",
        f"- **venue**：{_TODO}（同上，须核对）",
        f"- **年份**：{_TODO}",
        f"- **DOI**：{paper.get('doi') or _TODO}",
        f"- **版本**：{paper.get('source_version', _TODO)}（source_version）",
        f"- **阅读日期**：{today}",
        f"- **项目位置**：Literature/{paper_id}/",
        "",
        "## 证据状态\n",
    ]
    for k, v in status.items():
        parts.append(f"- {k}: {v}")
    parts += [
        "",
        "<!-- 纪律：出处五标签 [Paper]/[External]/[Analysis]/[Hypothesis]/[User] 最小适用；"
        "定位符随 Locator mode 降级，任何档位不许编造页码与锚点 ID；"
        "指针格式：原文.md#Sxxx（正文）/ #Cxxx / #Fxxx / #Txxx / #Exxx。 -->",
        "",
        "---",
        "",
        "# 第一部分：速读检查点（中间检查点，非终点）",
        "",
        "<!-- 本项目口径：入库默认直接精读。速读段 S1–S7 是精读 16 节之前的"
        "中间检查点，填完后继续第二部分；仅当用户显式说「先速览」时才停在此处。 -->",
        "",
        "## S1 一句话总结",
        "<!-- 纪律：一句话讲清问题+方法+机制+有界结果；禁宣传形容词；标 [Paper]。 -->",
        f"{_TODO} [Paper]",
        "",
        "## S2 研究问题",
        "<!-- 纪律：写成具体问题 + 一个可判定的 Can …? 句；源指针到摘要/引言块。 -->",
        f"{_TODO}（指针：原文.md#S___）",
        "",
        "## S3 核心思想速览",
        "<!-- 纪律：表面方法与核心洞见分两层写；洞见若为己推断标 [Analysis]。 -->",
        f"- 表面方法：{_TODO}\n- 核心洞见：{_TODO}",
        "",
        "## S4 图表清单（自动盘点）",
        "<!-- 纪律：本表由 source_map 自动生成，只盘点不深析；论证角色由精读时填。"
        "漏盘点即质量门不合格——发现漏盘先回解析轨（parse / 模型直读）补块，不许手补假行。 -->",
        "",
        "| 编号 | 页 | 类型 | 配对图注 | 论证角色 |",
        "|---|---|---|---|---|",
        *s4_rows,
        "",
        "## S5 关键结果速览",
        "<!-- 纪律：只记 1–3 个主要数字；数字必须逐字可溯（与原文字符级一致），"
        "每条带页/块指针，格式 [Paper: PDF p.N, Sxxx]。 -->",
        f"- {_TODO} [Paper: PDF p.__, S___]",
        "",
        "## S6 结论边界",
        "<!-- 纪律：有界重述 + 作者自述局限一句；原文不支持的更强结论要显式写出并标明不支持。 -->",
        f"- 有界重述：{_TODO}\n- 作者自述局限：{_TODO}",
        "",
        "## S7 精读决策",
        "<!-- 纪律：默认继续精读（见第一部分头注）；暂缓/放弃须写理由与未决问题清单。 -->",
        "- 决策：继续精读（默认）",
        f"- 待精读问题清单：{_TODO}",
        "",
        "---",
        "",
        "# 第二部分：精读卡（16 节，默认终点）",
        "",
    ]
    for i, (name, discipline, body) in enumerate(_SECTIONS_16, start=1):
        parts += [f"## {i:02d} {name}", f"<!-- {discipline} -->", body, ""]

    parts += [
        "---",
        "",
        "# 附录：原子卡（按需生成）",
        "",
        "<!-- 微结构统一为：出处（自动生成：页 + 块指针）→ 复述（自己的话）→ 启发（与本项目的关系）。 -->",
        "",
    ]
    for card in _ATOMIC_CARDS:
        extra = "\n- **原文短引文**：（待填，上限一句，须逐字）" if card == "金句卡" else ""
        parts += [
            f"## {card}",
            f"- **出处**：（自动生成：原文.md#S___（p.__））{extra}",
            f"- **复述**：{_TODO}",
            f"- **启发**：{_TODO}",
            "",
        ]

    (pdir / "阅读笔记.md").write_text("\n".join(parts), encoding="utf-8")
    paper.setdefault("status", {})["notes"] = "scaffold"
    save_paper_yaml(pdir, paper)
    return {"paper_id": paper_id, "s4_items": s4_count,
            "sections_16": len(_SECTIONS_16), "evidence_status": status}
