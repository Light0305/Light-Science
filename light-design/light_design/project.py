"""项目骨架与设计书文件操作。

目录形态（单个研究方向一份项目，与 light-idea 项目同级衔接）：

    <project>/
    ├── project.yaml            # 项目元数据（方向名、创建日期）
    ├── index.yaml / index.md   # 项目级索引（机器读 / 人读，命令自动维护）
    ├── design-stage/
    │   ├── DESIGN_REPORT.md    # 唯一权威文档：入口校验/设计索引/定版决议/偏离汇总
    │   └── intake_log.md       # 入口校验与打回记录（每次消费交接逐条留痕）
    ├── designs/<design_id>/    # 一想法一份设计
    │   ├── design.yaml         # 设计书结构化本体（权威源）
    │   └── design.md           # 人读版（由 design.yaml 渲染，不许手改）
    └── exports/                # 给 Experiment 的交接四件套（二期生成，一期建目录）

design_id = slug + '_' + hash6（见 util.make_design_id）。
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

from .schema import (
    ALL_STATES,
    INTAKE_ITEMS,
    INTAKE_LOCATIONS,
    _present,
    empty_design,
)
from .util import make_design_id, read_yaml, slugify, today, write_yaml

DESIGNS_DIRNAME = "designs"
STAGE_DIRNAME = "design-stage"


def project_paths(root: Path) -> dict[str, Path]:
    return {
        "root": root,
        "project_yaml": root / "project.yaml",
        "index_yaml": root / "index.yaml",
        "index_md": root / "index.md",
        "stage": root / STAGE_DIRNAME,
        "design_report": root / STAGE_DIRNAME / "DESIGN_REPORT.md",
        "intake_log": root / STAGE_DIRNAME / "intake_log.md",
        "designs": root / DESIGNS_DIRNAME,
        "exports": root / "exports",
        "review": root / "review",
    }


def init_project(root: Path, direction: str) -> Path:
    """建项目骨架。已存在 project.yaml 时拒绝覆盖。"""
    p = project_paths(root)
    if p["project_yaml"].exists():
        raise FileExistsError(f"项目已存在：{p['project_yaml']}")
    p["stage"].mkdir(parents=True, exist_ok=True)
    p["designs"].mkdir(parents=True, exist_ok=True)
    p["exports"].mkdir(parents=True, exist_ok=True)
    p["review"].mkdir(parents=True, exist_ok=True)
    (p["exports"] / ".gitkeep").write_text("", encoding="utf-8")
    write_yaml(p["project_yaml"], {
        "project": direction,
        "project_id": f"{slugify(direction)}_{hashlib.sha256(direction.strip().lower().encode()).hexdigest()[:6]}",
        "created": today(),
        "tool": "light-design",
        "version": "1.0.0",
    })
    p["design_report"].write_text(
        f"# DESIGN_REPORT — {direction}\n\n"
        "> 本方向唯一权威文档：入口校验记录 / 设计索引 / 定版决议 / "
        "偏离汇总（各节由命令与流程折叠写入）。\n",
        encoding="utf-8",
    )
    p["intake_log"].write_text(
        f"# 入口校验与打回记录 — {direction}\n\n"
        "每次消费 Idea 交接、每次打回逐条留痕，不许删除往返记录。\n",
        encoding="utf-8",
    )
    refresh_index(root)
    return root


def design_dir(root: Path, design_id: str) -> Path:
    return project_paths(root)["designs"] / design_id


def design_yaml_path(root: Path, design_id: str) -> Path:
    return design_dir(root, design_id) / "design.yaml"


def load_design(root: Path, design_id: str) -> dict:
    path = design_yaml_path(root, design_id)
    if not path.exists():
        raise FileNotFoundError(f"设计书不存在：{design_id}（找 {path}）")
    return read_yaml(path)


def save_design(root: Path, design: dict) -> Path:
    d = design_dir(root, design["design_id"])
    d.mkdir(parents=True, exist_ok=True)
    write_yaml(d / "design.yaml", design)
    (d / "design.md").write_text(render_design_md(design), encoding="utf-8")
    return d


def list_designs(root: Path) -> list[dict]:
    designs_dir = project_paths(root)["designs"]
    out = []
    if designs_dir.exists():
        for d in sorted(designs_dir.iterdir()):
            y = d / "design.yaml"
            if d.is_dir() and y.exists():
                out.append(read_yaml(y))
    return out


# ---------- 从 Idea 交接导入 ----------

def load_handoff(path: Path) -> dict:
    """读 Idea 交接件：支持 idea_card.json（JSON）与 idea.yaml（YAML）。
    design_handoff.md 是人读件、不可机读，明确拒绝并提示用 idea_card.json。"""
    suffix = path.suffix.lower()
    if suffix == ".json":
        return json.loads(path.read_text(encoding="utf-8"))
    if suffix in (".yaml", ".yml"):
        return read_yaml(path)
    raise ValueError(
        f"交接件格式不支持：{path.name}（须为 idea_card.json 或 idea.yaml；"
        "design_handoff.md 是人读件，请用同批导出的 idea_card.json）")


def _summarize(value) -> str:
    """把交接原值压成一行摘要，登记进 spec_intake.handoff_value。"""
    if isinstance(value, str):
        return value
    text = json.dumps(value, ensure_ascii=False, default=str)
    return text if len(text) <= 300 else text[:297] + "…"


def import_intake(design: dict, handoff: dict, handoff_path: str,
                  date: str) -> list[str]:
    """把交接件的 exec_spec 六项逐项承接进 intake 区。

    纪律：有值 → accepted 并登记原值摘要；缺失/为空 → status=returned
    + returned_items 打回记录。Design 不许临场发明口径补上（草案 §4）。
    返回打回项清单（item 名列表，空 = 承接齐全）。
    顺带预填：strongest_baseline → status_quo 对照占位；
    discriminating_experiment → readout 三向 meaning。
    """
    spec = handoff.get("exec_spec") or {}
    intake = design["intake"]
    raw = json.dumps(handoff, ensure_ascii=False, sort_keys=True, default=str)
    intake["source_handoff"] = {
        "path": handoff_path,
        "consumed_at": date,
        "handoff_hash": hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16],
    }
    question = handoff.get("original_question") or handoff.get("title") or ""
    if question:
        intake["original_question"] = str(question)

    missing: list[str] = []
    intake["spec_intake"] = []
    intake["returned_items"] = []
    for item in INTAKE_ITEMS:
        value = spec.get(item)
        ok = _present(value)
        intake["spec_intake"].append({
            "item": item,
            "handoff_value": _summarize(value) if ok else "",
            "design_location": INTAKE_LOCATIONS[item],
            "status": "accepted" if ok else "returned",
        })
        if not ok:
            missing.append(item)
            intake["returned_items"].append({
                "item": item,
                "reason": "交接件中缺失或为空，Design 无法展开为可执行协议",
                "needed": f"请 Idea 回补 exec_spec.{item} 后重新交接",
                "date": date,
                "resolved": False,
            })

    # 预填 status_quo：最强基线点名 → 对照组一等对象占位
    base = spec.get("strongest_baseline")
    if isinstance(base, dict) and _present(base.get("name")):
        design["contract"]["controls"] = [{
            "name": base["name"],
            "role": "control",
            "status_quo": True,
            "source": base.get("paper_id") or base.get("doi") or "",
        }]
    # 预填判读三向：判别实验 readout → evaluation.readout meaning
    de = spec.get("discriminating_experiment")
    if isinstance(de, dict):
        ro = design["evaluation"]["readout"]
        for side, key in (("positive", "readout_positive"),
                          ("negative", "readout_negative"),
                          ("null", "readout_null")):
            if _present(de.get(key)):
                ro[side] = {"meaning": str(de[key]), "action": ""}
    return missing


def append_intake_log(root: Path, design: dict, missing: list[str],
                      date: str) -> None:
    p = project_paths(root)
    verdict = "承接齐全" if not missing else f"打回 {len(missing)} 项：{'、'.join(missing)}"
    with open(p["intake_log"], "a", encoding="utf-8") as f:
        f.write(f"\n## {date} — {design['design_id']}（idea: {design['idea_id']}）\n\n"
                f"- 消费交接：{(design['intake'].get('source_handoff') or {}).get('path')}\n"
                f"- 结论：{verdict}\n")


def new_design(root: Path, title: str, idea_id: str, tier: str = "full",
               handoff_path: Path | None = None) -> tuple[dict, list[str]]:
    """建一份 draft 设计书并落盘。给了交接件则导入承接区。
    返回 (design, 打回项清单)。"""
    design_id = make_design_id(title)
    if design_dir(root, design_id).exists():
        raise FileExistsError(f"同名设计书已存在：{design_id}（题名重复，先改名或续写原书）")
    design = empty_design(design_id, idea_id, title, tier, today())
    missing: list[str] = []
    if handoff_path is not None:
        handoff = load_handoff(handoff_path)
        if not idea_id:
            design["idea_id"] = str(handoff.get("idea_id") or "")
        missing = import_intake(design, handoff, str(handoff_path), today())
        append_intake_log(root, design, missing, today())
    save_design(root, design)
    refresh_index(root)
    return design, missing


def refresh_index(root: Path) -> None:
    """重建 index.yaml / index.md（状态计数 + 设计清单）。"""
    p = project_paths(root)
    designs = list_designs(root)
    counts = Counter(d.get("status") for d in designs)
    entries = [
        {
            "design_id": d["design_id"],
            "idea_id": d.get("idea_id"),
            "title": d.get("title"),
            "tier": d.get("tier"),
            "status": d.get("status"),
            "path": f"{DESIGNS_DIRNAME}/{d['design_id']}/",
            "updated": d.get("updated"),
        }
        for d in designs
    ]
    write_yaml(p["index_yaml"], {
        "generated": today(),
        "total": len(designs),
        "status_counts": {s: counts.get(s, 0) for s in ALL_STATES if counts.get(s, 0)},
        "designs": entries,
    })
    lines = ["# 项目索引（自动生成，勿手改）", ""]
    lines.append(f"总设计数：{len(designs)}")
    if counts:
        lines.append("状态分布：" + "、".join(
            f"{s} × {counts[s]}" for s in ALL_STATES if counts.get(s)))
    lines.append("")
    lines.append("| design_id | 状态 | 级别 | 题名 | 承接 idea_id |")
    lines.append("|---|---|---|---|---|")
    for e in entries:
        lines.append(f"| {e['design_id']} | {e['status']} | {e['tier']} "
                     f"| {e['title']} | {e['idea_id']} |")
    lines.append("")
    p["index_md"].write_text("\n".join(lines), encoding="utf-8")


# ---------- design.md 渲染 ----------

def render_design_md(design: dict) -> str:
    """把 design.yaml 渲染成人读 design.md。横幅纪律：
    - minimal 级带「极简设计 · 不承载确认性结论」标注（拍板 ③）；
    - frozen 带冻结哈希与结果可见性声明横幅（约束 2/12）；
    - aux 区物理分离排版且标「暂定」（约束 13）。"""
    L: list[str] = []
    L.append(f"# {design.get('title')}")
    L.append("")
    L.append(f"> design_id: `{design.get('design_id')}` ｜ 状态: **{design.get('status')}**"
             f" ｜ 级别: {design.get('tier')} ｜ 承接 idea: `{design.get('idea_id')}`"
             f" ｜ 创建 {design.get('created')} ｜ 修订 {design.get('updated')}")
    reg = design.get("registration") or {}
    vis = reg.get("visibility")
    if design.get("tier") == "minimal":
        L.append("> ⚠️ **极简设计 · 不承载确认性结论**：本级限判别实验级小设计，"
                 "要承载确认性主结论须补全字段、升完整级重过定版。")
    if design.get("status") == "frozen":
        fr = design.get("freeze") or {}
        amds = fr.get("amendments") or []
        cur_hash = amds[-1].get("new_hash") if amds else fr.get("content_hash")
        L.append(f"> 🔒 **已冻结**（{fr.get('frozen_at')}）：内容哈希 `{cur_hash}`"
                 f"（amendment {len(amds)} 条）｜ 结果可见性声明: **{vis}**"
                 " — 正文永不回改，修订只走 amendment 追加。")
    if design.get("status") == "returned":
        rr = design.get("return_record") or {}
        L.append(f"> ↩️ **已打回 Idea**：缺项 {rr.get('missing_items')}（{rr.get('reason')}）")
    if design.get("status") == "blocked":
        br = design.get("block_record") or {}
        L.append(f"> ⛔ **受阻**：{br.get('reason')}（解阻条件: {br.get('unblock_condition')}）")
    L.append("")

    intake = design.get("intake") or {}
    L.append("## 输入承接（Idea 交接六项）")
    if intake.get("original_question"):
        L.append(f"**原始研究问题（逐字）**：{intake['original_question']}")
    for s in intake.get("spec_intake") or []:
        L.append(f"- **{s.get('item')}** → {s.get('design_location')}"
                 f"｜状态: {s.get('status')}｜交接原值: {s.get('handoff_value') or '（缺）'}")
    for r in intake.get("returned_items") or []:
        L.append(f"- ↩️ 打回 **{r.get('item')}**：{r.get('reason')}"
                 f"（已回补: {r.get('resolved')}）")
    L.append("")

    claims = design.get("claims") or {}
    L.append("## 主张区（主张先行，实验从主张反推）")
    for c in claims.get("primary_claims") or []:
        kind = "确认性" if c.get("confirmatory") else "探索性"
        L.append(f"- **[{c.get('id')}]** {c.get('statement')}（{kind}）")
        L.append(f"  - 最低可信证据：{c.get('minimum_convincing_evidence')}")
        if c.get("why_it_matters"):
            L.append(f"  - 为何重要：{c['why_it_matters']}")
    for a in claims.get("anti_claims") or []:
        L.append(f"- **反主张 [{a.get('id')}]**：{a.get('statement')}"
                 f"（由 {a.get('excluded_by') or '—'} 排除）")
    L.append("")

    plan = design.get("plan") or {}
    L.append("## 方案区")
    L.append(f"- 设计类型：{plan.get('design_type') or '（未填）'}"
             f"｜独立重复层级：**{plan.get('replication_level') or '（未声明）'}**")
    for v in plan.get("variables") or []:
        dom = v.get("domain") or {}
        L.append(f"- 变量 **{v.get('name')}**（{v.get('group')}）：{dom}")
    cps = plan.get("intervention_checkpoints") or []
    if cps:
        L.append("- 干预生效核查点：" + "；".join(str(c) for c in cps))
    L.append("")

    contract = design.get("contract") or {}
    L.append("## 实验契约区")
    for c in contract.get("controls") or []:
        sq = "（status quo 一等对照）" if c.get("status_quo") else ""
        L.append(f"- 对照 **{c.get('name')}**{sq}")
    for a in contract.get("ablations") or []:
        L.append(f"- 消融 **{a.get('id')}**：测 {a.get('what_it_tests')}"
                 f"；组件重要则预期 {a.get('expected_if_component_matters')}")
    for u in contract.get("unnecessary_ablations") or []:
        L.append(f"- 不做消融：{u.get('what')}（{u.get('reason')}）")
    runs = contract.get("runs") or []
    if runs:
        L.append("")
        L.append("| run_id | 角色 | 对照 | 依赖（对照先行） | 阶段 |")
        L.append("|---|---|---|---|---|")
        for r in runs:
            deps = "、".join(r.get("depends_on") or []) or "—"
            L.append(f"| {r.get('run_id')} | {r.get('role')} | {r.get('control_run') or '—'}"
                     f" | {deps} | {r.get('stage') or '—'} |")
    L.append("")

    ev = design.get("evaluation") or {}
    L.append("## 评估协议区")
    pm = ev.get("primary_metric") or {}
    L.append(f"- 主指标：**{pm.get('name') or '（未填）'}**"
             f"（方向 {pm.get('direction') or '—'}，惯例出处 {pm.get('convention_source') or '—'}）")
    for g in ev.get("guardrail_metrics") or []:
        L.append(f"- 护栏指标：{g.get('name')}（界：{g.get('bound')}）")
    ro = ev.get("readout") or {}
    for side, label in (("positive", "正"), ("negative", "负"), ("null", "零")):
        s = ro.get(side) or {}
        L.append(f"- 判读·{label}：{s.get('meaning') or '（未填）'}"
                 + (f" → {s['action']}" if s.get("action") else ""))
    tp = ev.get("tuning_parity") or {}
    L.append(f"- 调参对等：{tp.get('statement') or '（未声明）'}")
    seeds = ev.get("seeds") or {}
    L.append(f"- 种子数：{seeds.get('count')}｜重复数：{ev.get('repetitions')}")
    L.append("")

    val = design.get("validity") or {}
    L.append("## 效度登记区（四分法 · 三态）")
    for t in val.get("threats") or []:
        L.append(f"- [{t.get('category')}] {t.get('item')} — **{t.get('status')}**"
                 f"：{t.get('note') or ''}")
    L.append("")

    res = design.get("resources") or {}
    L.append("## 资源区")
    power = res.get("power") or {}
    if power:
        L.append(f"- 功效：SESOI {power.get('sesoi')}｜敏感性范围 "
                 f"{power.get('sensitivity_range')}｜推导 {power.get('derived')}"
                 f"｜核算充足: {power.get('sufficient')}")
    budget = res.get("budget") or {}
    L.append(f"- 预算：算力 {budget.get('compute') or '—'}｜时间 {budget.get('time') or '—'}")
    for b in res.get("circuit_breakers") or []:
        L.append(f"- 熔断线：{b.get('metric')} @ {b.get('threshold')} → {b.get('action')}")
    L.append("")

    fr = design.get("freeze") or {}
    amds = fr.get("amendments") or []
    if fr.get("review") or amds:
        L.append("## 冻结与修订区")
        rev = fr.get("review") or {}
        if rev:
            L.append(f"- 定版评审：{rev.get('reviewer')}（{rev.get('family')}）"
                     f" {rev.get('date')} → **{rev.get('decision')}**")
        for i, a in enumerate(amds, 1):
            sign = "（用户签）" if a.get("user_signed") else ""
            L.append(f"- amendment #{i}（{a.get('date')}）{sign}：{a.get('fields')}"
                     f" — {a.get('reason')}｜改时结果可见性: {a.get('results_seen')}"
                     f"｜新哈希 `{str(a.get('new_hash'))[:12]}…`")
        L.append("")

    aux = design.get("aux") or {}
    L.append("## 辅助区（只许参考、不进判定；一律「暂定，未经执行验证」）")
    if aux:
        for k, v in aux.items():
            L.append(f"- {k}: {v}（暂定）")
    else:
        L.append("（空）")
    L.append("")

    hist = design.get("status_history") or []
    if hist:
        L.append("## 状态历史")
        for h in hist:
            L.append(f"- {h.get('date')}：{h.get('from')} → {h.get('to')}"
                     f"（{h.get('by')}）{h.get('note') or ''}")
        L.append("")
    return "\n".join(L)
