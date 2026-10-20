"""承接收编调度（M0）：水位线、快照漂移、去重合并、缺口点名。

规程（REDESIGN 第三节 M0 + MM-01/MM-02）：
- 收编由命令触发，按登记头水位线只收增量；快照哈希未变直接跳过；
- 快照变了（上游漂移）才重跑适配器，漂移前后哈希都进收编报告；
- 任何一包收编失败不拖垮其余包（逐包水位线独立），失败停在水位线
  原处、缺口逐项点名，不许半收编冒充完成；
- 落账去重：对象按 object_id 合并、事件按内容去重键、事实按派生
  fact_id 合并溯源、关系按 relation_id 合并；前向引用在对象转正时
  自动补解析（MM-26）。
"""

from __future__ import annotations

from pathlib import Path

from . import adapters, project as project_mod, registry, schema
from .util import component_hash, sha256_file, utcnow


class IntakeError(Exception):
    """收编被拒。gaps 为逐项缺口。"""

    def __init__(self, gaps):
        self.gaps = list(gaps)
        super().__init__("；".join(self.gaps))


def snapshot_hash(source) -> str:
    """上游快照哈希：文件取文件哈希，目录取逐文件清单的规范化哈希。"""
    source = Path(source)
    if source.is_file():
        return sha256_file(source)
    if source.is_dir():
        manifest = {}
        for p in sorted(source.rglob("*")):
            if p.is_file() and "__pycache__" not in p.parts:
                manifest[str(p.relative_to(source))] = sha256_file(p)
        return component_hash(manifest)
    raise IntakeError([f"收编源不存在：{source}"])


class DraftCollector:
    """适配器的草稿收集器：统一构造溯源（MM-02），适配器只给锚点。"""

    def __init__(self, package: str, source: Path, snap: str,
                 project_key: str = ""):
        self.package = package
        self.source = Path(source)
        self.snap = snap
        self.project_key = project_key
        self.default_artifact = (self.source.name
                                 if self.source.is_file()
                                 else self.source.name)
        self.objects: list = []      # (fn, args, kwargs) 延迟到提交期执行
        self.events: list = []
        self.facts: list = []
        self.relations: list = []
        self.gaps: list = []

    # -- 溯源 ------------------------------------------------------------
    def provenance(self, artifact=None, anchor=None) -> dict:
        # MM-02 五字段不许缺：适配器未给细锚点时，以来源产物本身为锚
        # （整件产物即定位），不许留空进长期层。
        artifact = artifact or self.default_artifact
        return schema.make_provenance(
            self.package, artifact,
            anchor if anchor is not None else artifact, self.snap)

    # -- 草稿 ------------------------------------------------------------
    def object(self, object_type, upstream_id, *, title="",
               status="active", current_version=None, artifact=None):
        oid = schema.derive_object_id(object_type, upstream_id)
        self.objects.append({
            "kind": "register", "object_type": object_type,
            "upstream_id": upstream_id, "title": title, "status": status,
            "current_version": current_version,
            "provenance": self.provenance(artifact)})
        return oid

    def reference(self, object_type, upstream_id, *, artifact=None):
        oid = schema.derive_object_id(object_type, upstream_id)
        self.objects.append({
            "kind": "reference", "object_type": object_type,
            "upstream_id": upstream_id,
            "provenance": self.provenance(artifact)})
        return oid

    def event(self, event_type, summary, *, object_id=None, payload=None,
              artifact=None, anchor=None):
        prov = self.provenance(artifact, anchor)
        row = schema.new_event(0, event_type, summary, prov,
                               object_id=object_id, payload=payload)
        row["dedupe_key"] = component_hash({
            "package": self.package, "type": event_type,
            "summary": summary, "payload": payload or {},
            "anchor": anchor})
        self.events.append(row)
        return row

    def fact(self, statement, fact_type, object_id, *, valid_at=None,
             reference_time=None, extra=None, derived_from=None,
             artifact=None, anchor=None):
        prov = self.provenance(artifact, anchor)
        row = schema.new_fact(statement, fact_type, object_id, prov,
                              valid_at=valid_at,
                              reference_time=reference_time,
                              derived_from=derived_from, extra=extra)
        self.facts.append(row)
        return row

    def relation(self, rel_type, from_id, to_id, *, generation=None,
                 artifact=None, anchor=None):
        prov = self.provenance(artifact, anchor)
        row = schema.new_relation(rel_type, from_id, to_id, prov,
                                  generation=generation)
        self.relations.append(row)
        return row

    def gap(self, msg: str) -> None:
        self.gaps.append(msg)


def _merge_fact(existing: dict, incoming: dict) -> None:
    """同一 fact_id 重收编：溯源并集，其余以既有为准（事实本体不回改）。"""
    seen = {component_hash(p) for p in existing.get("provenance") or []}
    for p in incoming.get("provenance") or []:
        if component_hash(p) not in seen:
            existing.setdefault("provenance", []).append(p)


def _resolve_forward_refs(pkg: dict) -> int:
    """前向引用补解析（MM-26）：目标对象已登记的关系边转 resolved。"""
    known = {o.get("object_id") for o in pkg.get("objects") or []}
    resolved = 0
    for rel in pkg.get("relations") or []:
        if rel.get("status") == "unresolved" and rel.get("target_name"):
            target = rel["target_name"]
            if target in known:
                rel["to_id"] = target
                rel["status"] = "resolved"
                resolved += 1
    return resolved


def ingest(root, package: str, source) -> dict:
    """收编一个上游包的导出物，返回收编报告 dict。"""
    root = Path(root)
    source = Path(source)
    pkg = project_mod.load_package(root)
    memory = pkg.get("memory")
    if memory is None:
        raise IntakeError([f"记忆项目不存在或缺登记头：{root}"])
    if package not in adapters.ADAPTERS:
        raise IntakeError([f"未知上游包：{package}（可选："
                           f"{'、'.join(sorted(adapters.ADAPTERS))}）"])
    if not source.exists():
        raise IntakeError([f"收编源不存在：{source}"])
    snap = snapshot_hash(source)
    watermark = (memory.get("watermarks") or {}).get(package) or {}
    if watermark.get("snapshot_hash") == snap and \
            watermark.get("source") == str(source):
        return {"package": package, "status": "unchanged",
                "snapshot_hash": snap, "previous_hash": snap,
                "counts": watermark.get("counts") or {}, "gaps": []}

    ctx = DraftCollector(package, source, snap,
                         project_key=(memory.get("project") or {})
                         .get("id") or "")
    try:
        adapters.ADAPTERS[package](source, ctx)
    except adapters.AdapterError as exc:
        raise IntakeError(exc.gaps) from exc

    # ---- 提交：对象合并 -------------------------------------------------
    for draft in ctx.objects:
        if draft["kind"] == "register":
            registry.register_object(
                pkg, draft["object_type"], draft["upstream_id"],
                draft["provenance"], project=ctx.project_key,
                title=draft["title"], status=draft["status"],
                current_version=draft["current_version"])
        else:
            registry.reference_object(
                pkg, draft["object_type"], draft["upstream_id"],
                draft["provenance"], project=ctx.project_key)
    project_mod.save_objects(root, pkg.get("objects") or [])

    # ---- 提交：事件去重追加 ---------------------------------------------
    existing_keys = {e.get("dedupe_key") for e in pkg.get("events") or []}
    new_events = [e for e in ctx.events
                  if e.get("dedupe_key") not in existing_keys]
    project_mod.append_events(root, pkg, new_events)

    # ---- 提交：事实按派生 ID 合并 ---------------------------------------
    facts = pkg.get("facts") or []
    by_id = {f.get("fact_id"): f for f in facts}
    added_facts = 0
    for row in ctx.facts:
        if row["fact_id"] in by_id:
            _merge_fact(by_id[row["fact_id"]], row)
        else:
            facts.append(row)
            by_id[row["fact_id"]] = row
            added_facts += 1
    pkg["facts"] = facts
    project_mod.save_facts(root, facts)

    # ---- 提交：关系按派生 ID 合并 ---------------------------------------
    relations = pkg.get("relations") or []
    known_rel = {r.get("relation_id") for r in relations}
    added_relations = 0
    for row in ctx.relations:
        if row["relation_id"] not in known_rel:
            relations.append(row)
            known_rel.add(row["relation_id"])
            added_relations += 1
    pkg["relations"] = relations
    resolved = _resolve_forward_refs(pkg)
    project_mod.save_relations(root, relations)

    counts = {"objects": len(ctx.objects), "events": len(new_events),
              "facts": added_facts, "relations": added_relations,
              "forward_refs_resolved": resolved}
    memory.setdefault("watermarks", {})[package] = {
        "source": str(source), "snapshot_hash": snap,
        "previous_hash": watermark.get("snapshot_hash"),
        "adapter_version": adapters.ADAPTER_VERSIONS[package],
        "ingested_at": utcnow(), "counts": counts}
    memory.setdefault("adapters", {})[package] = \
        adapters.ADAPTER_VERSIONS[package]
    project_mod.refresh_counts(memory, pkg)
    project_mod.save_memory(root, memory)
    return {"package": package, "status": "ingested",
            "snapshot_hash": snap,
            "previous_hash": watermark.get("snapshot_hash"),
            "counts": counts, "gaps": ctx.gaps}
