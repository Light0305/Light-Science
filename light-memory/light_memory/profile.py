"""画像视图（M6，MM-31）：可再生视图，只装处置与指针。

纪律锚点：
- 画像只许装四类内容——工作习惯、方法偏好、口径裁决史的索引、
  当前项目状态；每条必须可回指底层事件或对象；任何发现/结论/
  证据不得只存在于画像里（画像最多持指针 + 一句摘录）。
- 静态层（profile-static.md）放稳定处置，低频全量重算；动态层
  （profile-dynamic.md）放项目近况，随事件再生。两文件都是派生
  视图：整删后一条命令从账本重建（与 MM-03 投影律同构）。
- 项目立场视图：以（项目，对象）键控现场组装，不落独立存储——
  同一对象在不同项目下的事实集分开呈现，不混答（借 honcho 的
  (observer, observed) 键控思想，内容由各项目自有产物支撑）。
"""

from __future__ import annotations

from pathlib import Path

from . import candidates as cand_mod
from . import project as project_mod
from .util import utcnow

STATIC_FILE = "profile-static.md"
DYNAMIC_FILE = "profile-dynamic.md"
GENERATED_MARK = "<!-- light-memory:generated 派生视图，可整删再生 -->"
EXCERPT_CHARS = 80


class ProfileError(Exception):
    def __init__(self, gaps):
        self.gaps = list(gaps)
        super().__init__("；".join(self.gaps))


def _excerpt(statement: str) -> str:
    s = (statement or "").replace("\n", " ")
    return s if len(s) <= EXCERPT_CHARS else s[:EXCERPT_CHARS] + "…"


def build_profile(root) -> dict:
    """由账本再生画像两文件（整文件重写，内容只装处置与指针）。"""
    root = Path(root)
    pkg = project_mod.load_package(root)
    if pkg.get("memory") is None:
        raise ProfileError([f"记忆项目不存在或缺登记头：{root}"])
    memory = pkg["memory"]
    facts = pkg.get("facts") or []
    now = utcnow()

    # ---- 静态层：稳定处置（决策口径 + 方法偏好 + 裁决史索引） ---------
    static = [GENERATED_MARK, f"<!-- 生成于 {now} -->", "",
              "# 研究者画像 · 静态层（稳定处置）", "",
              "本文件只装处置与指针：每条摘录一句、回指底层条目；"
              "证据与结论本体住在上游产物与事实层，不住在这里。", ""]
    decisions = [f for f in facts if f.get("status") == "current"
                 and f.get("fact_type") == "decision"]
    methods = [f for f in facts if f.get("status") == "current"
               and f.get("fact_type") == "method"]
    static.append("## 口径与决策处置")
    if decisions:
        for f in decisions:
            static.append(f"- {_excerpt(f.get('statement'))} "
                          f"→ {f.get('fact_id')}（对象 "
                          f"{f.get('object_id')}）")
    else:
        static.append("（暂无已生效的决策类处置）")
    static.append("")
    static.append("## 方法偏好")
    if methods:
        for f in methods:
            static.append(f"- {_excerpt(f.get('statement'))} "
                          f"→ {f.get('fact_id')}（对象 "
                          f"{f.get('object_id')}）")
    else:
        static.append("（暂无已登记的方法偏好）")
    static.append("")
    static.append("## 裁决史索引")
    resolved = [d for d in pkg.get("disputes") or []
                if d.get("status") == "resolved"]
    if resolved:
        for d in resolved:
            res = d.get("resolution") or {}
            static.append(f"- 争议 {d.get('dispute_id')}："
                          f"{res.get('outcome')}（裁决人 "
                          f"{res.get('adjudicator')}）→ "
                          f"{d.get('dispute_id')}")
    else:
        static.append("（暂无裁决记录）")
    static_text = "\n".join(static) + "\n"

    # ---- 动态层：项目近况（事件近况 + 未决项 + 状态计数） -------------
    dynamic = [GENERATED_MARK, f"<!-- 生成于 {now} -->", "",
               "# 研究者画像 · 动态层（项目近况）", "",
               f"项目 {memory.get('project', {}).get('id')}；"
               "本层随事件再生，只装近况摘录与指针。", ""]
    dynamic.append("## 近期事件")
    recent = sorted(pkg.get("events") or [],
                    key=lambda e: e.get("seq") or 0)[-12:]
    if recent:
        for e in reversed(recent):
            dynamic.append(f"- {e.get('ts')} {e.get('type')}："
                           f"{_excerpt(e.get('summary'))} "
                           f"→ {e.get('event_id')}")
    else:
        dynamic.append("（暂无事件）")
    dynamic.append("")
    dynamic.append("## 未决与状态")
    open_disputes = [d for d in pkg.get("disputes") or []
                     if d.get("status") == "open"]
    for d in open_disputes:
        dynamic.append(f"- 未决争议 → {d.get('dispute_id')}"
                       f"（对象 {d.get('object_id')}）")
    pending = cand_mod.list_candidates(root, status="pending")
    for c in pending:
        dynamic.append(f"- 待确认候选 → {c.get('candidate_id')}"
                       f"（{c.get('kind')}，提名 {c.get('nominator')}）")
    unresolved = [r for r in pkg.get("relations") or []
                  if r.get("status") == "unresolved"]
    for r in unresolved:
        dynamic.append(f"- 未解析关系 → {r.get('relation_id')}"
                       f"（目标原文标识 {r.get('target_name')}）")
    counts = memory.get("counts") or {}
    dynamic.append(f"- 账面计数：对象 {counts.get('objects')}、"
                   f"事件 {counts.get('events')}、事实 "
                   f"{counts.get('facts')}、关系 "
                   f"{counts.get('relations')}、open 争议 "
                   f"{counts.get('disputes_open')} → memory.yaml")
    dynamic_text = "\n".join(dynamic) + "\n"

    profile_dir = root / "profile"
    profile_dir.mkdir(parents=True, exist_ok=True)
    (profile_dir / STATIC_FILE).write_text(static_text, encoding="utf-8")
    (profile_dir / DYNAMIC_FILE).write_text(dynamic_text,
                                            encoding="utf-8")
    return {"static": str(profile_dir / STATIC_FILE),
            "dynamic": str(profile_dir / DYNAMIC_FILE),
            "decisions": len(decisions), "methods": len(methods),
            "recent_events": len(recent)}


def check_profile(root) -> list:
    """画像自检：每条内容行必须带可回指的指针（MM-31 纪律）。

    发现无指针的陈述行即点名——证据性内容只许住在事实层/上游，
    画像里出现无回指的陈述即违规。
    """
    root = Path(root)
    pkg = project_mod.load_package(root)
    known_ids = set()
    for coll in ("objects", "facts", "relations", "disputes"):
        key = {"objects": "object_id", "facts": "fact_id",
               "relations": "relation_id",
               "disputes": "dispute_id"}[coll]
        for row in pkg.get(coll) or []:
            known_ids.add(row.get(key))
    for e in pkg.get("events") or []:
        known_ids.add(e.get("event_id"))
    for c in cand_mod.load_candidates(root):
        known_ids.add(c.get("candidate_id"))
    known_ids.add("memory.yaml")
    errs = []
    for name in (STATIC_FILE, DYNAMIC_FILE):
        p = root / "profile" / name
        if not p.exists():
            errs.append(f"画像文件缺失：profile/{name}"
                        "（运行 profile build 再生）")
            continue
        for i, line in enumerate(
                p.read_text(encoding="utf-8").splitlines(), 1):
            if not line.startswith("- "):
                continue
            if "→" not in line:
                errs.append(f"profile/{name} 第 {i} 行无回指指针："
                            f"{line[:40]}")
                continue
            target = line.rsplit("→", 1)[1].strip().split("（")[0].strip()
            if target and target not in known_ids:
                errs.append(f"profile/{name} 第 {i} 行指针指向不存在"
                            f"的条目：{target}")
    return errs


# ---------------------------------------------------------------- 立场视图

def stance_view(roots, object_id: str) -> dict:
    """（项目，对象）键控立场视图：逐项目现场组装，不落独立存储。

    roots 为 [(项目标签, 记忆包路径), ...]；同一对象在不同项目下
    的事实集分开呈现（状态/有效区间/口径随各项目自有账本）。
    """
    projects = {}
    for label, root in roots:
        pkg = project_mod.load_package(root)
        if pkg.get("memory") is None:
            raise ProfileError([f"记忆项目不存在或缺登记头：{root}"])
        facts = [f for f in pkg.get("facts") or []
                 if f.get("object_id") == object_id]
        facts.sort(key=lambda f: (f.get("valid_at") or "",
                                  f.get("fact_id") or ""))
        fact_ids = {f.get("fact_id") for f in facts}
        relations = [r for r in pkg.get("relations") or []
                     if r.get("from_id") in fact_ids
                     or r.get("to_id") in fact_ids
                     or object_id in (r.get("from_id"),
                                      r.get("to_id"))]
        projects[label] = {"root": str(root), "facts": facts,
                           "relations": relations}
    return {"object_id": object_id, "projects": projects}


def render_stance(view: dict) -> str:
    lines = [f"# 立场视图：{view['object_id']}", "",
             "按（项目，对象）键控现场组装；各项目的事实集分开"
             "呈现，不混答。"]
    for label, slot in view["projects"].items():
        lines.append("")
        lines.append(f"## 项目 {label}")
        if not slot["facts"]:
            lines.append("- （本项目无该对象的事实）")
        for f in slot["facts"]:
            lines.append(f"- [{f.get('fact_type')}] "
                         f"{f.get('statement')}（状态 "
                         f"{f.get('status')}，有效 "
                         f"{f.get('valid_at') or '…'} → "
                         f"{f.get('invalid_at') or '…'}）"
                         f" → {f.get('fact_id')}")
        for r in slot["relations"]:
            lines.append(f"- 关系 {r.get('type')}："
                         f"{r.get('from_id')} → {r.get('to_id')}"
                         f" → {r.get('relation_id')}")
    return "\n".join(lines) + "\n"
