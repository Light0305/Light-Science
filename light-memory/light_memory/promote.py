"""晋升通道（M6，拍板 6）：项目层 → 全局层，候选 → 确认 → 复制。

纪律：
- 晋升走候选门：promote propose 只在全局层产 promotion 类候选，
  人工 confirm 才执行复制；候选通道的 accept 拒绝代办 promotion
  （跨包复制必须经本模块，留痕才完整）。
- 复制语义：原件留在项目层不动；全局层是可再生副本（副本行带
  promoted_from 回指 + promotion_id，derived_from 原样指针改存
  extra——全局层没有源项目的事实行，不许留悬空指针）。
- 撤回 = 对账式撤销：删除全局副本行 + promotions.jsonl 记
  withdrawn + 落事件；项目原件一字不动。晋升账只增，撤回不删账。
"""

from __future__ import annotations

import copy
from pathlib import Path

from . import candidates as cand_mod
from . import project as project_mod, registry, schema
from .util import component_hash, dump_jsonl, read_jsonl, utcnow

PROMOTIONS_FILE = "promotions.jsonl"


class PromoteError(Exception):
    def __init__(self, gaps):
        self.gaps = list(gaps)
        super().__init__("；".join(self.gaps))


def _promotions_path(root) -> Path:
    return Path(root) / PROMOTIONS_FILE


def load_promotions(root) -> list:
    return read_jsonl(_promotions_path(root))


def _save_promotions(root, rows) -> None:
    dump_jsonl(_promotions_path(root), rows)


def _next_promotion_id(rows) -> str:
    n = sum(1 for r in rows if r.get("action") == "promoted")
    return f"PRM-{n + 1:04d}"


def propose(global_root, source_root, fact_id: str, *, by: str,
            reason: str = "") -> dict:
    """在全局层产晋升候选（只产候选，不复制）。"""
    source_root = Path(source_root)
    spkg = project_mod.load_package(source_root)
    if spkg.get("memory") is None:
        raise PromoteError([f"来源记忆项目不存在或缺登记头：{source_root}"])
    fact = next((f for f in spkg.get("facts") or []
                 if f.get("fact_id") == fact_id), None)
    if fact is None:
        raise PromoteError([f"来源项目无此事实：{fact_id}"])
    content = {
        "source_root": str(source_root),
        "source_project": (spkg["memory"].get("project") or {}).get("id"),
        "source_fact_id": fact_id,
        "source_object_id": fact.get("object_id"),
        "snapshot_hash": component_hash(fact),
        "reason": reason,
    }
    return cand_mod.propose(
        global_root, "promotion", content, nominator=by,
        basis=[fact_id], rationale=reason or "跨项目晋升提名",
        origin="promotion")


def confirm(global_root, candidate_id: str, *, by: str) -> dict:
    """人工确认后执行复制：副本入全局事实层 + 晋升账 + 事件留痕。"""
    global_root = Path(global_root)
    cand = cand_mod.get_candidate(global_root, candidate_id)
    if cand is None:
        raise PromoteError([f"候选不存在：{candidate_id}"])
    if cand.get("kind") != "promotion":
        raise PromoteError([f"候选 {candidate_id} 不是 promotion 类"
                            f"（{cand.get('kind')}）"])
    if cand.get("status") != "pending":
        raise PromoteError([f"候选 {candidate_id} 已裁决"
                            f"（{cand.get('status')}）"])
    content = cand.get("content") or {}
    source_root = Path(content.get("source_root") or "")
    spkg = project_mod.load_package(source_root)
    fact = next((f for f in spkg.get("facts") or []
                 if f.get("fact_id") == content.get("source_fact_id")),
                None)
    if fact is None:
        raise PromoteError(
            [f"来源事实已不存在：{content.get('source_fact_id')}"
             "（候选保持 pending，请处置来源后重试或 reject）"])

    gpkg = project_mod.load_package(global_root)
    rows = load_promotions(global_root)
    withdrawn_ids = {r.get("promotion_id") for r in rows
                     if r.get("action") == "withdrawn"}
    for r in rows:
        if r.get("action") == "promoted" and \
                r.get("source_fact_id") == fact.get("fact_id") and \
                r.get("promotion_id") not in withdrawn_ids:
            raise PromoteError(
                [f"该事实已晋升在账（{r.get('promotion_id')}）；"
                 "如需更新，先 withdraw 旧晋升再重新提名"])
    promotion_id = _next_promotion_id(rows)

    # 对象先在 global 层登记（副本的 object_id 须有注册行可指）。
    prov = schema.make_provenance(
        "light-memory", f"promotion:{candidate_id}",
        content.get("source_fact_id"), content.get("snapshot_hash"))
    obj_row = next((o for o in spkg.get("objects") or []
                    if o.get("object_id") == fact.get("object_id")),
                   None)
    if obj_row is not None:
        registry.register_object(
            gpkg, obj_row.get("object_type"),
            obj_row.get("upstream_id"), prov,
            project=content.get("source_project") or "",
            title=obj_row.get("title") or "")
        project_mod.save_objects(global_root, gpkg.get("objects") or [])

    clone = copy.deepcopy(fact)
    clone.setdefault("extra", {})["promoted_from"] = {
        "source_root": str(source_root),
        "source_project": content.get("source_project"),
        "source_fact_id": fact.get("fact_id"),
    }
    clone["extra"]["promotion_id"] = promotion_id
    if clone.get("derived_from"):
        # 源项目的派生指针在全局层无对应行：原样存 extra，不留悬空。
        clone["extra"]["source_derived_from"] = clone["derived_from"]
        clone["derived_from"] = []
    clone.setdefault("provenance", []).append(prov)
    gpkg.setdefault("facts", []).append(clone)
    project_mod.save_facts(global_root, gpkg.get("facts") or [])

    record = {
        "promotion_id": promotion_id, "action": "promoted",
        "candidate_id": candidate_id,
        "source_root": str(source_root),
        "source_project": content.get("source_project"),
        "source_fact_id": fact.get("fact_id"),
        "global_fact_id": clone.get("fact_id"),
        "object_id": fact.get("object_id"),
        "by": by, "reason": content.get("reason") or "",
        "at": utcnow(),
    }
    rows.append(record)
    _save_promotions(global_root, rows)
    event = schema.new_event(
        0, "promotion",
        f"晋升生效 {promotion_id}：{fact.get('fact_id')} 自项目 "
        f"{content.get('source_project')} 复制入全局层", prov,
        object_id=fact.get("object_id"),
        payload={"promotion_id": promotion_id,
                 "candidate_id": candidate_id, "by": by})
    project_mod.append_events(global_root, gpkg, [event])
    cand_mod.set_decision(global_root, candidate_id, "accepted", by=by,
                          note="晋升确认", result_ref=promotion_id)
    fresh = project_mod.load_package(global_root)
    memory = fresh["memory"]
    project_mod.refresh_counts(memory, fresh)
    project_mod.save_memory(global_root, memory)
    return record


def withdraw(global_root, promotion_id: str, *, by: str,
             reason: str = "") -> dict:
    """撤回晋升 = 对账式撤销：删全局副本 + 记 withdrawn + 落事件。

    项目层原件一字不动；晋升账只增不删，撤回是新的一行。
    """
    global_root = Path(global_root)
    gpkg = project_mod.load_package(global_root)
    if gpkg.get("memory") is None:
        raise PromoteError([f"记忆项目不存在或缺登记头：{global_root}"])
    rows = load_promotions(global_root)
    promoted = next((r for r in rows
                     if r.get("promotion_id") == promotion_id
                     and r.get("action") == "promoted"), None)
    if promoted is None:
        raise PromoteError([f"晋升记录不存在：{promotion_id}"])
    if any(r.get("promotion_id") == promotion_id
           and r.get("action") == "withdrawn" for r in rows):
        raise PromoteError([f"晋升 {promotion_id} 已撤回，不许重复撤回"])
    facts = gpkg.get("facts") or []
    clone = next((f for f in facts
                  if (f.get("extra") or {}).get("promotion_id")
                  == promotion_id), None)
    if clone is None:
        raise PromoteError(
            [f"对账不一致：晋升 {promotion_id} 的全局副本不在事实层"
             "（账实不符，须人工核账，不许假装已撤回）"])
    gpkg["facts"] = [f for f in facts if f is not clone]
    project_mod.save_facts(global_root, gpkg["facts"])
    record = {
        "promotion_id": promotion_id, "action": "withdrawn",
        "source_fact_id": promoted.get("source_fact_id"),
        "global_fact_id": promoted.get("global_fact_id"),
        "by": by, "reason": reason, "at": utcnow(),
    }
    rows.append(record)
    _save_promotions(global_root, rows)
    prov = schema.make_provenance(
        "light-memory", f"promotion:{promotion_id}",
        promoted.get("source_fact_id"), None)
    prov["source_version"] = "n/a"
    event = schema.new_event(
        0, "promotion_withdraw",
        f"晋升撤回 {promotion_id}：全局副本已对账删除，项目原件不动",
        prov, object_id=promoted.get("object_id"),
        payload={"promotion_id": promotion_id, "by": by,
                 "reason": reason})
    project_mod.append_events(global_root, gpkg, [event])
    memory = gpkg["memory"]
    project_mod.refresh_counts(memory, gpkg)
    project_mod.save_memory(global_root, memory)
    return record


def list_promotions(root) -> list:
    return load_promotions(root)
