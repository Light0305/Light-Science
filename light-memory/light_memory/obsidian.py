"""Obsidian 视图投影（M5，MM-27 至 MM-29）+ 标注回读。

纪律锚点（REDESIGN-DRAFT.md 第六节）：
- MM-27：视图是投影不是本体——项目内独立 vault（<项目>/memory/
  obsidian/ 本身即合法 vault），单向从记录生成，整册可删可重建；
  Memory 全部功能不依赖视图存在。
- MM-28：笔记与视图同形——视图笔记与记忆笔记同一 MD 形态，关系
  以 wikilink 落边，Obsidian 原生图谱直接渲染；投影只做精选 + 同步，
  同步带内容摘要门控（源未变不重写文件）。
- MM-29：标注只走回读通道——机器区/标注区物理分隔，重投影只动
  机器区；用户标注经 readback 整段提取为候选（走候选通道），
  不做双向同步引擎；回读是复制不是剪切，原文留在视图内。
- 精选规则成文（构建期不许临场增减）：入选事实类型与状态见
  SELECTED_FACT_TYPES / 入选状态集；两端均入选的关系全量落边，
  折返与否定边不许因精选密度被剪；争议未裁决事实不落笔记、
  只在索引页计数提及。
"""

from __future__ import annotations

import re
from pathlib import Path

from . import candidates as cand_mod
from . import project as project_mod, schema
from .util import component_hash, dump_json, load_structured, \
    sha256_text, slugify, utcnow

VAULT_DIR = "obsidian"
MANIFEST_FILE = ".projection.json"

MACHINE_START = "<!-- light-memory:machine:start -->"
MACHINE_END = "<!-- light-memory:machine:end -->"
ANNO_START = "<!-- light-memory:annotations:start -->"
ANNO_END = "<!-- light-memory:annotations:end -->"
ANNO_PLACEHOLDER = ("（用户标注区：在这里写下的内容不会被投影覆盖；"
                    "用 light-memory readback 回读为候选）")

#: 精选规则（成文）：入选事实类型（定版想法/冻结设计/结论两代/
#: 失败教训/决策/期刊事实/方向）与入选状态（current + superseded；
#: disputed 不落笔记，只在索引页计数）。
SELECTED_FACT_TYPES = ("direction", "design_claim", "conclusion",
                       "conclusion_verdict", "decision", "lesson",
                       "failure_record", "journal_fact", "method",
                       "evidence", "figure_provenance", "review_concern")
SELECTED_STATUSES = ("current", "superseded")

#: 事实类型 → 观察行类别词（MM-07 受控类别词表）。
OBSERVATION_CATEGORY = {
    "conclusion": "结论", "conclusion_verdict": "结论",
    "evidence": "证据", "journal_fact": "证据",
    "failure_record": "失败", "lesson": "失败",
    "decision": "决策", "design_claim": "方法", "method": "方法",
    "direction": "方法", "figure_provenance": "方法",
    "review_concern": "风险", "generic": "结论",
}

STAGE_BY_PACKAGE = {
    "literature": "Literature", "idea": "Idea", "design": "Design",
    "experiment": "Experiment", "analysis": "Analysis",
    "write": "Write", "figure": "Figure",
    "journal-select": "Journal-Select", "review": "Review",
    "light-memory": "Memory",
}


class ObsidianError(Exception):
    def __init__(self, gaps):
        self.gaps = list(gaps)
        super().__init__("；".join(self.gaps))


# ---------------------------------------------------------------- 精选

def select_objects(pkg: dict) -> dict:
    """按精选规则选对象：返回 {object_id: {object, facts}}。"""
    facts_by_object: dict[str, list] = {}
    for f in pkg.get("facts") or []:
        if f.get("fact_type") in SELECTED_FACT_TYPES and \
                f.get("status") in SELECTED_STATUSES:
            facts_by_object.setdefault(f.get("object_id"), []).append(f)
    selected = {}
    objects = {o.get("object_id"): o for o in pkg.get("objects") or []}
    for oid, facts in facts_by_object.items():
        if oid in objects:
            selected[oid] = {"object": objects[oid], "facts": facts}
    return selected


def _note_slug(object_id: str) -> str:
    return slugify(object_id, max_len=60, fallback="object")


def _touching_relations(pkg: dict, selected: dict) -> dict:
    """两端均入选的关系（端点为事实时映射到其对象），按对象归组。

    返回 {object_id: [(relation, other_object_id, outgoing)]}。
    折返与否定边与全部类型化边同等待遇——入选后不许被剪。
    """
    fact_object = {}
    for oid, slot in selected.items():
        for f in slot["facts"]:
            fact_object[f.get("fact_id")] = oid
    all_facts = {f.get("fact_id"): f.get("object_id")
                 for f in pkg.get("facts") or []}
    fact_object.update({k: v for k, v in all_facts.items()
                        if v in selected})

    def resolve(endpoint):
        if endpoint in selected:
            return endpoint
        return fact_object.get(endpoint)

    grouped: dict[str, list] = {oid: [] for oid in selected}
    for rel in pkg.get("relations") or []:
        if rel.get("status") == "superseded":
            continue
        a = resolve(rel.get("from_id"))
        b = resolve(rel.get("to_id"))
        if a is None or b is None or a == b:
            continue
        grouped[a].append((rel, b, True))
        grouped[b].append((rel, a, False))
    return grouped


# ---------------------------------------------------------------- 渲染

def _render_machine_zone(oid: str, slot: dict, relations: list) -> str:
    obj = slot["object"]
    lines = [f"# {obj.get('title') or oid}", ""]
    lines.append(f"- 对象：{oid}（类型 {obj.get('object_type')}，"
                 f"上游 ID {obj.get('upstream_id')}，"
                 f"状态 {obj.get('status')}）")
    artifacts = sorted({(p.get("source_package"), p.get("source_artifact"))
                        for f in slot["facts"]
                        for p in f.get("provenance") or []})
    for pkg_name, artifact in artifacts:
        lines.append(f"- 来源指针：{pkg_name} / {artifact}")
    lines.append("")
    lines.append("## 观察")
    for f in sorted(slot["facts"],
                    key=lambda x: (x.get("valid_at") or "",
                                   x.get("fact_id") or "")):
        cat = OBSERVATION_CATEGORY.get(f.get("fact_type"), "结论")
        status = "" if f.get("status") == "current" \
            else f"（{f.get('status')}）"
        stale = " [stale 待再生]" if f.get("stale") else ""
        lines.append(f"- [{cat}] {f.get('statement')}{status}{stale}")
        lines.append(f"  - 事实 {f.get('fact_id')}，有效 "
                     f"{f.get('valid_at') or '…'} → "
                     f"{f.get('invalid_at') or '…'}")
    if relations:
        lines.append("")
        lines.append("## 关系")
        for rel, other, outgoing in sorted(
                relations, key=lambda t: (t[0].get("type"),
                                          t[1])):
            arrow = rel.get("type") if outgoing \
                else f"被 {rel.get('type')}"
            lines.append(f"- {arrow} [[{_note_slug(other)}]]"
                         f"（来源计数 {rel.get('sources') or 1}）")
    return "\n".join(lines) + "\n"


def _render_note(oid: str, slot: dict, relations: list,
                 annotations: str) -> str:
    obj = slot["object"]
    prov0 = (slot["facts"][0].get("provenance") or [{}])[0]
    stage = STAGE_BY_PACKAGE.get(prov0.get("source_package"),
                                 prov0.get("source_package") or "Memory")
    fm = ["---",
          f"light_memory_object: {oid}",
          f"object_type: {obj.get('object_type')}",
          f"status: {obj.get('status')}",
          "tags:",
          f"  - stage/{stage}",
          f"  - status/{obj.get('status')}",
          "---", ""]
    body = "\n".join(fm)
    body += MACHINE_START + "\n"
    body += _render_machine_zone(oid, slot, relations)
    body += MACHINE_END + "\n\n"
    body += ANNO_START + "\n"
    body += (annotations.strip() + "\n") if annotations.strip() \
        else ANNO_PLACEHOLDER + "\n"
    body += ANNO_END + "\n"
    return body


def _render_index(pkg: dict, selected: dict) -> str:
    memory = pkg.get("memory") or {}
    disputed = sum(1 for f in pkg.get("facts") or []
                   if f.get("status") == "disputed")
    lines = [f"# {memory.get('memory_id') or '记忆'} · 阶段索引", "",
             "本页由 Light-Memory 从关系与事实记录单向投影生成"
             "（派生视图，可整册重建，非唯一副本）。", ""]
    by_stage: dict[str, list] = {}
    for oid, slot in selected.items():
        prov0 = (slot["facts"][0].get("provenance") or [{}])[0]
        stage = STAGE_BY_PACKAGE.get(prov0.get("source_package"),
                                     "Memory")
        by_stage.setdefault(stage, []).append(oid)
    for stage in sorted(by_stage):
        lines.append(f"## {stage}")
        for oid in sorted(by_stage[stage]):
            lines.append(f"- [[{_note_slug(oid)}]]（{oid}）")
        lines.append("")
    if disputed:
        lines.append(f"争议未裁决事实 {disputed} 条：按精选规则不落"
                     "笔记，仅在此计数提及。")
    retractions = [e for e in pkg.get("events") or []
                   if "retract" in (e.get("type") or "")]
    if retractions:
        lines.append(f"撤稿事件 {len(retractions)} 条（见事件账）。")
    return "\n".join(lines) + "\n"


def _render_relations_guide() -> str:
    lines = ["# 关系类型说明", "",
             "Obsidian 图谱只渲染链接存在性，不区分边类型与方向"
             "语义；语义以本页图例与各笔记关系行的类型词为准。", ""]
    for name, spec in schema.RELATION_TYPES.items():
        lines.append(f"- {name}：{spec.get('note')}"
                     f"（方向 {spec.get('direction')}，"
                     f"生成 {spec.get('generation')}）")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- 区分隔

_ANNO_RE = re.compile(
    re.escape(ANNO_START) + r"\n(.*?)" + re.escape(ANNO_END),
    re.DOTALL)


def extract_annotations(text: str) -> str:
    """取用户标注区内容（占位提示不算用户内容）。"""
    m = _ANNO_RE.search(text or "")
    if not m:
        return ""
    content = m.group(1)
    content = content.replace(ANNO_PLACEHOLDER, "").strip()
    return content


def _wrap_zones(machine_md: str, annotations: str) -> str:
    body = MACHINE_START + "\n" + machine_md + MACHINE_END + "\n\n"
    body += ANNO_START + "\n"
    body += (annotations.strip() + "\n") if annotations.strip() \
        else ANNO_PLACEHOLDER + "\n"
    body += ANNO_END + "\n"
    return body


# ---------------------------------------------------------------- 投影

def _manifest_path(root) -> Path:
    return Path(root) / VAULT_DIR / MANIFEST_FILE


def _load_manifest(root) -> dict:
    p = _manifest_path(root)
    if p.exists():
        return load_structured(p) or {}
    return {"kind": "light-memory/projection", "version": "1.0",
            "notes": {}}


def _source_hash(slot: dict, relations: list) -> str:
    return component_hash({
        "object": slot["object"], "facts": slot["facts"],
        "relations": [r for r, _, _ in relations]})


def project_obsidian(root, *, full: bool = False) -> dict:
    """单向投影：精选对象/事实/关系 → 项目内独立 vault 笔记。

    摘要门控：源哈希未变的笔记不重写文件；重投影只动机器区，
    标注区原文保留。full=True 强制全部重投影（机器区）。
    返回报告 {written, unchanged, orphaned, notes}。
    """
    root = Path(root)
    pkg = project_mod.load_package(root)
    if pkg.get("memory") is None:
        raise ObsidianError([f"记忆项目不存在或缺登记头：{root}"])
    vault = root / VAULT_DIR
    vault.mkdir(parents=True, exist_ok=True)
    manifest = _load_manifest(root)
    notes_meta = manifest.setdefault("notes", {})

    selected = select_objects(pkg)
    grouped = _touching_relations(pkg, selected)
    written, unchanged, seen = [], [], set()

    for oid, slot in selected.items():
        rel_name = f"{_note_slug(oid)}.md"
        seen.add(rel_name)
        path = vault / rel_name
        digest = _source_hash(slot, grouped.get(oid) or [])
        meta = notes_meta.get(rel_name) or {}
        if not full and path.exists() and \
                meta.get("source_hash") == digest:
            unchanged.append(rel_name)
            continue
        annotations = ""
        if path.exists():
            annotations = extract_annotations(
                path.read_text(encoding="utf-8"))
        path.write_text(
            _render_note(oid, slot, grouped.get(oid) or [], annotations),
            encoding="utf-8")
        notes_meta[rel_name] = {
            "object_id": oid, "source_hash": digest,
            "annotations_hash": sha256_text(annotations),
            "annotations_read_hash": meta.get("annotations_read_hash"),
        }
        written.append(rel_name)

    # 索引页与关系说明页：整页机器生成（仍带标注区，一致纪律）
    for name, content in (("index.md", _render_index(pkg, selected)),
                          ("relations-guide.md",
                           _render_relations_guide())):
        seen.add(name)
        path = vault / name
        digest = sha256_text(content)
        meta = notes_meta.get(name) or {}
        if not full and path.exists() and \
                meta.get("source_hash") == digest:
            unchanged.append(name)
            continue
        annotations = ""
        if path.exists():
            annotations = extract_annotations(
                path.read_text(encoding="utf-8"))
        fm = ("---\nlight_memory_view: " + name + "\n---\n\n")
        path.write_text(fm + _wrap_zones(content, annotations),
                        encoding="utf-8")
        notes_meta[name] = {
            "object_id": None, "source_hash": digest,
            "annotations_hash": sha256_text(annotations),
            "annotations_read_hash": meta.get("annotations_read_hash"),
        }
        written.append(name)

    orphaned = sorted(n for n in notes_meta if n not in seen)
    manifest["generated_at"] = utcnow()
    manifest["notes"] = notes_meta
    dump_json(_manifest_path(root), manifest)
    return {"written": written, "unchanged": unchanged,
            "orphaned": orphaned, "selected": len(selected),
            "vault": str(vault)}


# ---------------------------------------------------------------- 回读

def readback(root) -> dict:
    """标注回读：标注区新增内容整段收为候选（走候选通道，不直入账）。

    以投影清单的 annotations_read_hash 为水位：内容未变不重复提名；
    内容变了产新候选。标注原文保留在视图内（复制不是剪切）。
    """
    root = Path(root)
    pkg = project_mod.load_package(root)
    if pkg.get("memory") is None:
        raise ObsidianError([f"记忆项目不存在或缺登记头：{root}"])
    vault = root / VAULT_DIR
    manifest = _load_manifest(root)
    notes_meta = manifest.setdefault("notes", {})
    created, unchanged = [], 0
    if vault.exists():
        for path in sorted(vault.glob("*.md")):
            text = path.read_text(encoding="utf-8")
            content = extract_annotations(text)
            if not content:
                continue
            digest = sha256_text(content)
            meta = notes_meta.setdefault(path.name, {})
            if meta.get("annotations_read_hash") == digest:
                unchanged += 1
                continue
            row = cand_mod.propose(
                root, "annotation",
                {"text": content, "vault_note": path.name,
                 "object_id": meta.get("object_id")},
                nominator="obsidian-readback",
                basis=[path.name],
                rationale="Obsidian 视图标注回读（MM-29 批通道）",
                origin="annotation_readback")
            meta["annotations_read_hash"] = digest
            created.append(row["candidate_id"])
    dump_json(_manifest_path(root), manifest)
    return {"created": created, "unchanged": unchanged,
            "count": len(created)}
