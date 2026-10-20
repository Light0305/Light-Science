"""项目骨架与想法卡文件操作。

目录形态（单个研究方向一份项目）：

    <project>/
    ├── project.yaml            # 项目元数据（方向名、创建日期）
    ├── index.yaml / index.md   # 项目级索引（机器读 / 人读，命令自动维护）
    ├── idea-stage/
    │   ├── IDEA_REPORT.md      # 唯一权威文档（二期起折叠各环结论）
    │   ├── candidates.md       # 候选池活名单（幸存者 + 已杀区 + 切换日志）
    │   └── research_contract.md# 交接契约（选定想法后生成，一期为占位说明）
    ├── cards/<idea_id>/        # 一卡一目录
    │   ├── idea.yaml           # 结构化字段（权威源）
    │   └── card.md             # 人读版（由 idea.yaml 渲染，不许手改后脱节）
    ├── novelty/                # 查新证据包落盘处（二期）
    ├── chains/                 # 演进链素材（三期，chain 命令落盘）
    └── exports/                # 交接三件套（三期，export 命令落盘）

idea_id = slug + '_' + hash6（见 util.make_idea_id）。
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from . import casebook as casebook_mod
from .schema import ALL_STATES, empty_card
from .util import make_idea_id, read_yaml, slugify, today, write_yaml

CARDS_DIRNAME = "cards"
STAGE_DIRNAME = "idea-stage"


def project_paths(root: Path) -> dict[str, Path]:
    return {
        "root": root,
        "project_yaml": root / "project.yaml",
        "index_yaml": root / "index.yaml",
        "index_md": root / "index.md",
        "stage": root / STAGE_DIRNAME,
        "idea_report": root / STAGE_DIRNAME / "IDEA_REPORT.md",
        "candidates": root / STAGE_DIRNAME / "candidates.md",
        "contract": root / STAGE_DIRNAME / "research_contract.md",
        "cards": root / CARDS_DIRNAME,
        "novelty": root / "novelty",
    }


def init_project(root: Path, direction: str) -> Path:
    """建项目骨架。已存在 project.yaml 时拒绝覆盖。"""
    p = project_paths(root)
    if p["project_yaml"].exists():
        raise FileExistsError(f"项目已存在：{p['project_yaml']}")
    p["stage"].mkdir(parents=True, exist_ok=True)
    p["cards"].mkdir(parents=True, exist_ok=True)
    p["novelty"].mkdir(parents=True, exist_ok=True)
    (root / "chains").mkdir(parents=True, exist_ok=True)   # 三期：演进链素材
    (root / "exports").mkdir(parents=True, exist_ok=True)  # 三期：交接三件套
    (p["novelty"] / ".gitkeep").write_text("", encoding="utf-8")
    # v1.1（IDEA-D04）：判例集冷启动——建项即播种随包种子判例
    casebook_mod.seed_casebook(root)
    write_yaml(p["project_yaml"], {
        "project": direction,
        "project_id": f"{slugify(direction)}_{__import__('hashlib').sha256(direction.strip().lower().encode()).hexdigest()[:6]}",
        "created": today(),
        "tool": "light-idea",
        "version": "1.0.0",
    })
    p["idea_report"].write_text(
        f"# IDEA_REPORT — {direction}\n\n"
        "> 本方向唯一权威文档：landscape / 缺口清单 / ranked-ideas / "
        "查新报告 / 评审记录（二期起由各环折叠写入锚点节）。\n",
        encoding="utf-8",
    )
    p["candidates"].write_text(
        f"# 候选池 — {direction}\n\n"
        "## Landscape 与缺口清单（I0 人工维护，report 不覆盖本文件）\n\n"
        "（challenge-insight 读图得出的缺口逐条登记：形态（未解/迁移/红海）"
        "+ 回指论文 paper_id/DOI + 读图依据。）\n\n"
        "## 幸存者\n\n（由 index 索引，此处记人工备注。）\n\n"
        "## 已杀区\n\n（killed 想法在此留痕：原因、失败分类、复活条件见各卡 kill 记录。）\n\n"
        "## 切换日志（Idea Switch Log）\n\n| 日期 | From | To | Reason |\n|---|---|---|---|\n\n"
        "## 方向层留痕\n\n（周期结束时按抽象阶梯提升到方向层级，字段对齐 evo-memory，供 Memory 收编。）\n",
        encoding="utf-8",
    )
    p["contract"].write_text(
        "# 研究契约（research contract）\n\n"
        "选定想法定版后在此生成：core claims + minimum convincing evidence "
        "+ next-step pointer（交接三件套之一，见 SKILL.md）。一期为占位。\n",
        encoding="utf-8",
    )
    refresh_index(root)
    return root


def card_dir(root: Path, idea_id: str) -> Path:
    return project_paths(root)["cards"] / idea_id


def card_yaml_path(root: Path, idea_id: str) -> Path:
    return card_dir(root, idea_id) / "idea.yaml"


def load_card(root: Path, idea_id: str) -> dict:
    path = card_yaml_path(root, idea_id)
    if not path.exists():
        raise FileNotFoundError(f"想法卡不存在：{idea_id}（找 {path}）")
    return read_yaml(path)


def save_card(root: Path, card: dict) -> Path:
    d = card_dir(root, card["idea_id"])
    d.mkdir(parents=True, exist_ok=True)
    write_yaml(d / "idea.yaml", card)
    (d / "card.md").write_text(render_card_md(card), encoding="utf-8")
    return d


def list_cards(root: Path) -> list[dict]:
    cards_dir = project_paths(root)["cards"]
    out = []
    if cards_dir.exists():
        for d in sorted(cards_dir.iterdir()):
            y = d / "idea.yaml"
            if d.is_dir() and y.exists():
                out.append(read_yaml(y))
    return out


def new_card(root: Path, title: str, one_liner: str, operator: str,
             provenance_note: str | None = None) -> dict:
    """建一张 draft 卡并落盘（idea.yaml + card.md），刷新索引。"""
    idea_id = make_idea_id(title)
    if card_dir(root, idea_id).exists():
        raise FileExistsError(f"同名想法卡已存在：{idea_id}（题名重复，先改名或续写原卡）")
    card = empty_card(idea_id, title, one_liner, operator, today())
    if provenance_note:
        card["provenance"]["note"] = provenance_note
    save_card(root, card)
    refresh_index(root)
    return card


def refresh_index(root: Path) -> None:
    """重建 index.yaml / index.md（状态计数 + 卡清单）。"""
    p = project_paths(root)
    cards = list_cards(root)
    counts = Counter(c.get("status") for c in cards)
    entries = [
        {
            "idea_id": c["idea_id"],
            "title": c.get("title"),
            "status": c.get("status"),
            "operator": c.get("operator"),
            "path": f"{CARDS_DIRNAME}/{c['idea_id']}/",
            "updated": c.get("updated"),
        }
        for c in cards
    ]
    write_yaml(p["index_yaml"], {
        "generated": today(),
        "total": len(cards),
        "status_counts": {s: counts.get(s, 0) for s in ALL_STATES if counts.get(s, 0)},
        "cards": entries,
    })
    lines = ["# 项目索引（自动生成，勿手改）", ""]
    lines.append(f"总卡数：{len(cards)}")
    if counts:
        lines.append("状态分布：" + "、".join(
            f"{s} × {counts[s]}" for s in ALL_STATES if counts.get(s)))
    lines.append("")
    lines.append("| idea_id | 状态 | 算子 | 题名 |")
    lines.append("|---|---|---|---|")
    for e in entries:
        lines.append(f"| {e['idea_id']} | {e['status']} | {e['operator']} | {e['title']} |")
    lines.append("")
    p["index_md"].write_text("\n".join(lines), encoding="utf-8")


# ---------- card.md 渲染 ----------

def _ref_str(ref) -> str:
    if not isinstance(ref, dict):
        return str(ref)
    bits = []
    if ref.get("paper_id"):
        bits.append(f"paper_id: {ref['paper_id']}")
    if ref.get("doi"):
        bits.append(f"doi: {ref['doi']}")
    if ref.get("title"):
        bits.append(str(ref["title"]))
    return "；".join(bits) or "（未登记）"


def render_card_md(card: dict) -> str:
    """把 idea.yaml 渲染成人读 card.md。判定区与辅助区物理分开排版。"""
    L: list[str] = []
    L.append(f"# {card.get('title')}")
    L.append("")
    L.append(f"> idea_id: `{card.get('idea_id')}` ｜ 状态: **{card.get('status')}**"
             f" ｜ 算子: {card.get('operator')}"
             f" ｜ 创建 {card.get('created')} ｜ 修订 {card.get('updated')}")
    if card.get("status") in ("finalized_executable", "finalized_conceptual"):
        lvl = card.get("finalization_level")
        if lvl == "conceptual":
            L.append("> ⚠️ **概念定版**：核心与查新齐、执行级规格未齐，"
                     "**不得直接开工**，只许交 Design 做规格化。")
        pilot = (card.get("pilot") or {}).get("status")
        if pilot != "verified":
            L.append("> ⚠️ **未经试点验证**（pilot 未跑或未登记为 verified）。")
    if card.get("status") == "killed":
        k = card.get("kill") or {}
        L.append(f"> ☠️ 已杀：{k.get('reason')}（失败分类: {k.get('failure_class')}，"
                 f"来源: {k.get('source')}，{k.get('date')}）")
    L.append("")
    L.append(f"**一句话**：{card.get('one_liner')}")
    L.append("")

    prov = card.get("provenance") or {}
    prov_bits = [f"{k}: {v}" for k, v in prov.items() if v]
    L.append(f"**生成出处**：{'；'.join(prov_bits) if prov_bits else '（未登记 — 无出处不许入池）'}")
    L.append("")

    refs = card.get("seed_refs") or []
    if refs:
        L.append("## 种子文献（均须带 paper_id / DOI）")
        for r in refs:
            L.append(f"- {_ref_str(r)}")
        L.append("")

    L.append("## Facet 区（骨架）")
    facets = card.get("facets") or {}
    for f in ("purpose", "mechanism", "evaluation"):
        fd = facets.get(f) or {}
        src = fd.get("source") or {}
        L.append(f"- **{f}**：{fd.get('phrase') or '（未填）'} — {fd.get('detail') or ''}"
                 f"（来源: {src.get('type', '?')}）")
    L.append("")

    body = card.get("body") or {}
    L.append("## 正文区")
    steps = body.get("method_steps") or []
    if steps:
        L.append("**平语方法描述**：")
        for i, s in enumerate(steps, 1):
            L.append(f"{i}. {s}")
    L.append(f"**一句话假设**：{body.get('hypothesis') or '（未填）'}")
    if body.get("mechanism_rationale"):
        L.append(f"**机制说明**：{body['mechanism_rationale']}")
    if body.get("unexpected_prediction"):
        L.append(f"**可证伪的意外预测**：{body['unexpected_prediction']}")
    L.append(f"**贡献类型**：{body.get('contribution_type')}")
    L.append("")

    spec = card.get("exec_spec") or {}
    L.append("## 执行级规格区（可执行定版必填六项 + 能力匹配 + 判别实验）")
    for key in ("datasets", "strongest_baseline", "metrics", "ablations",
                "resource_budget", "key_details"):
        v = spec.get(key)
        if isinstance(v, list):
            disp = "；".join(
                (x.get("name") if isinstance(x, dict) else str(x)) or str(x) for x in v
            ) if v else "（未填）"
        elif isinstance(v, dict):
            disp = _ref_str(v) if ("paper_id" in v or "doi" in v) else str(v)
        else:
            disp = str(v) if v else "（未填）"
        L.append(f"- **{key}**：{disp}")
    exp = spec.get("discriminating_experiment")
    if isinstance(exp, dict):
        L.append(f"- **最小判别实验**：{exp.get('description')}"
                 f"（正: {exp.get('readout_positive')}；负: {exp.get('readout_negative')}"
                 f"；零: {exp.get('readout_null')}）")
    else:
        L.append("- **最小判别实验**：（未填）")
    L.append("")

    # 能力匹配（IDEA-D03）：这个想法该不该由这支队伍现在做
    fit = spec.get("capability_fit")
    L.append("## 能力匹配区（这支队伍现在能不能做这个想法）")
    if isinstance(fit, dict):
        L.append(f"- **队伍现状**：{fit.get('team_status') or '（未填）'}")
        for item in fit.get("required") or []:
            if isinstance(item, dict):
                L.append(f"- 所需能力：{item.get('capability')}"
                         f"——{item.get('detail') or ''}")
        labels = {"have": "已有", "fillable": "可短期补",
                  "blocking": "构成不可行"}
        for g in fit.get("gaps") or []:
            if isinstance(g, dict):
                L.append(f"- 处置[{labels.get(g.get('disposition'), g.get('disposition'))}]"
                         f" {g.get('capability')}：{g.get('note') or ''}")
    else:
        L.append("（未评估——定版门会拦：能力匹配必填）")
    L.append("")

    neg = card.get("negative") or {}
    L.append("## 负面字段区")
    L.append(f"- **最强反对意见**：{neg.get('strongest_objection') or '（未填）'}")
    for r in neg.get("risks") or []:
        L.append(f"- 风险：{r}")
    if neg.get("why_not_selected_first"):
        L.append(f"- **Why not selected first**：{neg['why_not_selected_first']}")
    L.append("")

    nov = card.get("novelty") or {}
    L.append("## 查新证据区（判定区 — 辅助信号不许入内）")
    L.append(f"- 判定: **{nov.get('verdict') or '（未判定）'}**"
             f" ｜ 检查于: {nov.get('checked_at') or '—'}"
             f" ｜ review_status: {nov.get('review_status')}")
    if nov.get("caution_reason"):
        L.append(f"- CAUTION 薄点: {nov['caution_reason']}")
    scope = nov.get("search_scope") or {}
    if scope:
        L.append(f"- 检索范围: 源 {scope.get('sources')} ｜ 池规模 {scope.get('pool_size')}"
                 f" ｜ 已知盲区: {scope.get('known_blind_spots') or '—'}")
    works = nov.get("closest_works") or []
    if works:
        L.append("- 最接近工作:")
        for w in works:
            L.append(f"  - {_ref_str(w)}｜撞车面: {w.get('collided_facets')}"
                     f"｜delta: {w.get('delta') or '—'}｜已核实: {w.get('verified')}")
    rc = nov.get("receipt") or {}
    if rc.get("verdict_id"):
        L.append(f"- 判定收据: verdict_id {rc['verdict_id']}｜判定 {rc.get('judge_model')}"
                 f"｜执行 {rc.get('executor_model')}")
    L.append("")

    aux = card.get("aux") or {}
    L.append("## 辅助字段区（只许参考、不进判定；一律「暂定，未经执行验证」）")
    if aux:
        for k, v in aux.items():
            L.append(f"- {k}: {v}（暂定）")
    else:
        L.append("（空）")
    L.append("")

    lin = card.get("lineage") or {}
    log = lin.get("revision_log") or []
    if log or lin.get("changed_from"):
        L.append("## 谱系与迭代日志")
        if lin.get("changed_from"):
            L.append(f"- Changed From: {lin['changed_from']}"
                     f"（修订算子: {lin.get('revision_operator')}）")
        for e in log:
            L.append(f"- {e.get('date')}：{e.get('reason')}（触发: {e.get('trigger')}）")
        L.append("")

    hist = card.get("status_history") or []
    if hist:
        L.append("## 状态历史")
        for h in hist:
            L.append(f"- {h.get('date')}：{h.get('from')} → {h.get('to')}"
                     f"（{h.get('by')}）{h.get('note') or ''}")
        L.append("")
    return "\n".join(L)
