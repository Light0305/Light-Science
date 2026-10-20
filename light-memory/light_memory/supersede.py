"""取代链与判定落账（M3 核心）。

纪律锚点（LEARNING.md）：
- MM-10：失效裁决两层分工——模型只提名，失效由代码按双时间区间
  算术执行；区间不重叠不失效；无时间戳整段跳过算术，走争议账或
  人工裁决，不许静默处理。
- MM-11：取代闭环——新版生效、旧版标 superseded 保留可查、派生按
  新版再生（本期先标 stale）、全过程落取代事件。
- MM-12：派生失效传播——可重建派生物整组重建（索引/视图，Phase 2）；
  不可重建的派生事实显式标 stale 并带理由，不许假装仍有效。
- MM-14：判定五值词表 + 合并算子按类型查表；判定记录带提名者与依据。
- MM-15：争议只登记不裁决——事实本体不动，裁决是独立动作。

本模块的落账函数都以「pending events」方式工作：先在内存账本上执行，
再由 apply_nominations / resolve_dispute 统一落盘（账本 + 事件一起）。
"""

from __future__ import annotations

from pathlib import Path

from . import project as project_mod
from . import schema
from .util import component_hash, parse_time, utcnow


class VerdictError(Exception):
    """判定/裁决被拒。gaps 为逐条人读原因。"""

    def __init__(self, gaps):
        self.gaps = list(gaps)
        super().__init__("；".join(self.gaps))


# ---------------------------------------------------------------- 内部

def _facts_by_id(pkg) -> dict:
    return {f.get("fact_id"): f for f in pkg.get("facts") or []}


def _prov_for(nomination: dict, nominator: str) -> dict:
    prov = nomination.get("provenance")
    if isinstance(prov, dict) and not schema.provenance_gaps(prov):
        return prov
    return schema.make_provenance(
        "light-memory", f"verdict:{nominator}",
        nomination.get("target_fact_id") or
        (nomination.get("fact") or {}).get("object_id"),
        component_hash(nomination))


def _draft_fact(nomination: dict, nominator: str, *, status="current",
                at=None) -> dict:
    draft = nomination.get("fact") or {}
    prov = _prov_for(nomination, nominator)
    fact = schema.new_fact(
        draft.get("statement") or "", draft.get("fact_type") or "generic",
        draft.get("object_id") or "", prov,
        valid_at=draft.get("valid_at"), invalid_at=draft.get("invalid_at"),
        reference_time=draft.get("reference_time"),
        derived_from=draft.get("derived_from"),
        extra=draft.get("extra"), status=status, at=at)
    if draft.get("fact_id"):
        fact["fact_id"] = draft["fact_id"]
    return fact


def _event(events: list, event_type: str, summary: str, provenance: dict,
           *, object_id=None, payload=None) -> None:
    events.append(schema.new_event(0, event_type, summary, provenance,
                                   object_id=object_id, payload=payload))


def _chain_reaches(facts_by_id: dict, start_id: str, target_id: str) -> bool:
    """沿 superseded_by 链从 start 出发，能否到达 target（防环）。"""
    seen = set()
    cur = start_id
    while cur and cur not in seen:
        if cur == target_id:
            return True
        seen.add(cur)
        row = facts_by_id.get(cur)
        cur = row.get("superseded_by") if row else None
    return False


def _propagate_stale(pkg, events, invalidated_id: str, successor_id: str,
                     prov: dict, at: str) -> list:
    """派生失效传播（MM-12）：传递性标 stale；关系端点同步标注。"""
    facts = pkg.get("facts") or []
    frontier = {invalidated_id}
    stale_marked = []
    changed = True
    while changed:
        changed = False
        for f in facts:
            fid = f.get("fact_id")
            if fid in frontier or f.get("status") == "superseded":
                continue
            derived = set(f.get("derived_from") or [])
            if derived & frontier and not f.get("stale"):
                f["stale"] = True
                f["stale_reason"] = (
                    f"源事实 {sorted(derived & frontier)} 已被 "
                    f"{successor_id} 取代，派生内容待按新版再生")
                stale_marked.append(fid)
                frontier.add(fid)
                changed = True
    for rel in pkg.get("relations") or []:
        if invalidated_id in (rel.get("from_id"), rel.get("to_id")):
            rel["stale_endpoint"] = invalidated_id
    if stale_marked:
        _event(events, "propagation",
               f"派生失效传播：{len(stale_marked)} 条派生事实标 stale",
               prov, payload={"invalidated": invalidated_id,
                              "successor": successor_id,
                              "stale_marked": stale_marked})
    return stale_marked


def _invalidate(pkg, events, old: dict, new: dict, prov: dict, at: str,
                *, relation: bool = True) -> list:
    """执行失效（MM-11）：旧版标 superseded 保留，指针与边同步落账。"""
    old["invalid_at"] = new.get("valid_at")
    old["status"] = "superseded"
    old["expired_at"] = at
    old["superseded_by"] = new.get("fact_id")
    new["supersedes"] = old.get("fact_id")
    if relation:
        rel = schema.new_relation(
            "supersedes", new.get("fact_id"), old.get("fact_id"), prov,
            valid_at=new.get("valid_at"), at=at)
        rels = pkg.setdefault("relations", [])
        if all(r.get("relation_id") != rel["relation_id"] for r in rels):
            rels.append(rel)
    _event(events, "supersede",
           f"事实 {old.get('fact_id')} 被 {new.get('fact_id')} 取代",
           prov, object_id=new.get("object_id"),
           payload={"old_fact": old.get("fact_id"),
                    "new_fact": new.get("fact_id"),
                    "invalid_at": old.get("invalid_at")})
    return _propagate_stale(pkg, events, old.get("fact_id"),
                             new.get("fact_id"), prov, at)


# ---------------------------------------------------------------- 判定

def _apply_one(pkg, events, nomination: dict, at: str) -> dict:
    verdict = nomination.get("verdict")
    nominator = nomination.get("nominator") or "unknown"
    rationale = nomination.get("rationale") or ""
    facts_by_id = _facts_by_id(pkg)
    outcome = {"verdict": verdict, "nominator": nominator,
               "rationale": rationale, "result": None,
               "fact_id": None, "invalidated": [], "stale_marked": []}
    prov = _prov_for(nomination, nominator)
    _event(events, "verdict",
           f"判定 {verdict}（提名：{nominator}）", prov,
           payload={"verdict": verdict, "rationale": rationale,
                    "target_fact_id": nomination.get("target_fact_id")})

    if verdict not in schema.VERDICTS:
        outcome["result"] = "rejected_unknown_verdict"
        return outcome

    target_id = nomination.get("target_fact_id")
    target = facts_by_id.get(target_id) if target_id else None

    # ---- store：新信息新增 -------------------------------------------
    if verdict == "store":
        fact = _draft_fact(nomination, nominator, at=at)
        if not fact["statement"] or not fact["object_id"]:
            outcome["result"] = "rejected_incomplete_fact"
            return outcome
        if fact["fact_id"] in facts_by_id:
            outcome["result"] = "already_stored"
            outcome["fact_id"] = fact["fact_id"]
            return outcome
        pkg.setdefault("facts", []).append(fact)
        outcome["result"] = "stored"
        outcome["fact_id"] = fact["fact_id"]
        return outcome

    # ---- skip：旧的更好或无增量，只落判定事件 -------------------------
    if verdict == "skip":
        outcome["result"] = "skipped"
        return outcome

    # 以下三值都必须有目标事实
    if target is None:
        outcome["result"] = "rejected_target_missing"
        return outcome

    # ---- dispute：登记争议，事实本体不动（MM-15） ---------------------
    if verdict == "dispute":
        other_id = nomination.get("other_fact_id")
        if other_id and other_id in facts_by_id:
            challenger = facts_by_id[other_id]
        elif other_id == target_id:
            outcome["result"] = "rejected_same_fact"
            return outcome
        else:
            challenger = _draft_fact(nomination, nominator,
                                     status="disputed", at=at)
            if not challenger["statement"]:
                outcome["result"] = "rejected_incomplete_fact"
                return outcome
            if challenger["fact_id"] == target_id:
                outcome["result"] = "rejected_same_fact"
                return outcome
            if challenger["fact_id"] not in facts_by_id:
                pkg.setdefault("facts", []).append(challenger)
                facts_by_id[challenger["fact_id"]] = challenger
        disputes = pkg.setdefault("disputes", [])
        dispute_id = f"DSP-{len(disputes) + 1:04d}"
        disputes.append(schema.new_dispute(
            dispute_id, target.get("object_id"), target.get("fact_type"),
            [target_id, challenger["fact_id"]], prov,
            nominated_by=nominator, rationale=rationale, at=at))
        for f in (target, challenger):
            if f.get("status") == "current":
                f["status"] = "disputed"
        _event(events, "dispute", f"争议登记 {dispute_id}：事实本体未动",
               prov, object_id=target.get("object_id"),
               payload={"dispute_id": dispute_id,
                        "fact_ids": [target_id, challenger["fact_id"]]})
        outcome["result"] = "disputed"
        outcome["fact_id"] = challenger["fact_id"]
        outcome["dispute_id"] = dispute_id
        return outcome

    # ---- 算子表先行（MM-14）：merge 只查表，不许现场发明 ---------------
    if verdict == "merge":
        op = schema.merge_operator(target.get("fact_type"))
        if op not in schema.MERGEABLE_OPERATORS:
            outcome["result"] = "operator_forbidden"
            outcome["operator"] = op
            return outcome

    # ---- supersede / merge 共用：先造新事实 ---------------------------
    new_fact = _draft_fact(nomination, nominator, at=at)
    if verdict == "merge" and nomination.get("merged_statement"):
        merged = dict(new_fact)
        merged["statement"] = nomination["merged_statement"]
        merged["fact_id"] = schema.derive_fact_id(
            merged["object_id"], merged["statement"], merged["valid_at"],
            (merged["provenance"][0] or {}).get("source_package", ""))
        new_fact = merged
    if not new_fact["statement"]:
        outcome["result"] = "rejected_incomplete_fact"
        return outcome
    if verdict == "merge" and not new_fact["object_id"]:
        new_fact["object_id"] = target.get("object_id")
        new_fact["fact_id"] = schema.derive_fact_id(
            new_fact["object_id"], new_fact["statement"],
            new_fact["valid_at"],
            (new_fact["provenance"][0] or {}).get("source_package", ""))

    # 防环先行：沿新事实的 superseded_by 链能到达目标，则落账即成环。
    if _chain_reaches(facts_by_id, new_fact["fact_id"], target_id):
        outcome["result"] = "cycle_rejected"
        return outcome

    existing_new = facts_by_id.get(new_fact["fact_id"])
    if existing_new is not None and verdict == "merge":
        outcome["result"] = "already_stored"
        outcome["fact_id"] = new_fact["fact_id"]
        return outcome

    if verdict == "supersede":
        # MM-10：无时间戳整段跳过算术失效——明示阻断，不许静默处理。
        if target.get("valid_at") is None or \
                new_fact.get("valid_at") is None:
            _event(events, "verdict",
                   "supersede 被阻断：缺 valid_at，算术失效不执行"
                   "（请走 dispute 或补时间戳）", prov,
                   payload={"blocked": "no_timestamps",
                            "target_fact_id": target_id})
            outcome["result"] = "blocked_no_timestamps"
            return outcome
        if existing_new is not None:
            new_fact = existing_new  # 既有事实作新版复用，不长副本
        else:
            pkg.setdefault("facts", []).append(new_fact)
            facts_by_id[new_fact["fact_id"]] = new_fact
        outcome["fact_id"] = new_fact["fact_id"]
        overlap = schema.intervals_overlap(
            target.get("valid_at"), target.get("invalid_at"),
            new_fact.get("valid_at"), new_fact.get("invalid_at"))
        if overlap:
            outcome["stale_marked"] = _invalidate(
                pkg, events, target, new_fact, prov, at)
            outcome["invalidated"] = [target_id]
            outcome["result"] = "superseded"
        else:
            outcome["result"] = "stored_both_current_no_overlap"
        return outcome

    if verdict == "merge":
        # 合并：时间跨度取并集、溯源取并集、目标被吸收（MM-14）。
        t_valid, n_valid = target.get("valid_at"), new_fact.get("valid_at")
        if t_valid and n_valid:
            new_fact["valid_at"] = (t_valid if parse_time(t_valid)
                                    <= parse_time(n_valid) else n_valid)
        else:
            new_fact["valid_at"] = t_valid or n_valid
        t_inv, n_inv = target.get("invalid_at"), new_fact.get("invalid_at")
        if t_inv is None or n_inv is None:
            new_fact["invalid_at"] = None
        else:
            new_fact["invalid_at"] = (t_inv if parse_time(t_inv)
                                       >= parse_time(n_inv) else n_inv)
        seen_prov = {schema.component_hash(p)
                     for p in new_fact.get("provenance") or []}
        for p in target.get("provenance") or []:
            if schema.component_hash(p) not in seen_prov:
                new_fact.setdefault("provenance", []).append(p)
        derived = list(new_fact.get("derived_from") or [])
        if target_id not in derived:
            derived.append(target_id)
        new_fact["derived_from"] = derived
        new_fact.setdefault("extra", {})["merged_from"] = [target_id]
        pkg.setdefault("facts", []).append(new_fact)
        facts_by_id[new_fact["fact_id"]] = new_fact
        # 吸收：旧事实转 superseded，其有效区间收束到合并跨度之内。
        target["status"] = "superseded"
        target["expired_at"] = at
        target["superseded_by"] = new_fact["fact_id"]
        if target.get("invalid_at") is None:
            cand = new_fact.get("valid_at")
            t_v = target.get("valid_at")
            if cand and t_v and parse_time(cand) < parse_time(t_v):
                cand = t_v
            target["invalid_at"] = cand
        rel = schema.new_relation(
            "derived-from", new_fact["fact_id"], target_id, prov,
            valid_at=new_fact.get("valid_at"), at=at)
        rels = pkg.setdefault("relations", [])
        if all(r.get("relation_id") != rel["relation_id"] for r in rels):
            rels.append(rel)
        _event(events, "supersede",
               f"事实 {target_id} 被合并入 {new_fact['fact_id']}",
               prov, object_id=new_fact.get("object_id"),
               payload={"merged_from": target_id,
                        "new_fact": new_fact["fact_id"], "merge": True})
        outcome["stale_marked"] = _propagate_stale(
            pkg, events, target_id, new_fact["fact_id"], prov, at)
        outcome["invalidated"] = [target_id]
        outcome["fact_id"] = new_fact["fact_id"]
        outcome["result"] = "merged"
        return outcome

    outcome["result"] = "rejected_unknown_verdict"
    return outcome


def apply_nominations(root, nominations, *, at: str = None) -> list:
    """批量落账一组判定提名（模型只提名、本函数执行），返回逐条结果。"""
    root = Path(root)
    pkg = project_mod.load_package(root)
    if pkg.get("memory") is None:
        raise VerdictError([f"记忆项目不存在或缺登记头：{root}"])
    at = at or utcnow()
    events: list = []
    outcomes = [_apply_one(pkg, events, nom, at) for nom in nominations]
    project_mod.append_events(root, pkg, events)
    project_mod.save_facts(root, pkg.get("facts") or [])
    project_mod.save_relations(root, pkg.get("relations") or [])
    project_mod.save_disputes(root, pkg.get("disputes") or [])
    memory = pkg["memory"]
    project_mod.refresh_counts(memory, pkg)
    project_mod.save_memory(root, memory)
    return outcomes


# ---------------------------------------------------------------- 裁决

def resolve_dispute(root, dispute_id: str, outcome: str, *,
                    adjudicator: str, rationale: str = "",
                    at: str = None) -> dict:
    """争议裁决（独立动作）：裁决人 + 结论 + 理由落账，事实按结论执行。

    outcome 三值：
    - challenger_wins：挑战方生效，代码按区间算术失效在位方（须重叠，
      无时间戳或不重叠则拒绝，争议保持 open）；
    - incumbent_wins：在位方维持，挑战方以零长区间转 superseded；
    - both_stand：两方各表一时段/一面，并存回 current。
    """
    root = Path(root)
    pkg = project_mod.load_package(root)
    if pkg.get("memory") is None:
        raise VerdictError([f"记忆项目不存在或缺登记头：{root}"])
    at = at or utcnow()
    disputes = pkg.get("disputes") or []
    row = next((d for d in disputes if d.get("dispute_id") == dispute_id),
               None)
    if row is None:
        raise VerdictError([f"争议不存在：{dispute_id}"])
    if row.get("status") != "open":
        raise VerdictError([f"争议 {dispute_id} 已裁决，不许重复裁决"])
    if outcome not in ("challenger_wins", "incumbent_wins", "both_stand"):
        raise VerdictError([f"未知裁决结论：{outcome}"])
    facts_by_id = _facts_by_id(pkg)
    incumbent_id, challenger_id = (row.get("fact_ids") or [None, None])[:2]
    incumbent = facts_by_id.get(incumbent_id)
    challenger = facts_by_id.get(challenger_id)
    if incumbent is None or challenger is None:
        raise VerdictError(["争议指向的事实缺失，无法裁决"])
    prov = schema.make_provenance(
        "light-memory", f"adjudication:{adjudicator}", dispute_id,
        component_hash({"dispute": dispute_id, "outcome": outcome}))
    events: list = []
    stale_marked: list = []
    if outcome == "challenger_wins":
        if incumbent.get("valid_at") is None or \
                challenger.get("valid_at") is None:
            raise VerdictError(
                ["challenger_wins 须双方都有 valid_at 才能执行算术失效；"
                 "缺时间戳请改判 both_stand 或先补登记"])
        if not schema.intervals_overlap(
                incumbent.get("valid_at"), incumbent.get("invalid_at"),
                challenger.get("valid_at"), challenger.get("invalid_at")):
            raise VerdictError(
                ["双方有效区间不重叠，不构成失效关系；请改判 both_stand"])
        challenger["status"] = "current"
        stale_marked = _invalidate(pkg, events, incumbent, challenger,
                                   prov, at)
    elif outcome == "incumbent_wins":
        challenger["status"] = "superseded"
        challenger["expired_at"] = at
        challenger["superseded_by"] = incumbent_id
        if challenger.get("invalid_at") is None:
            challenger["invalid_at"] = challenger.get("valid_at")
        incumbent["status"] = "current"
    else:  # both_stand
        incumbent["status"] = "current"
        challenger["status"] = "current"
    row["status"] = "resolved"
    row["resolution"] = {"outcome": outcome, "adjudicator": adjudicator,
                         "rationale": rationale, "at": at}
    _event(events, "dispute", f"争议 {dispute_id} 裁决：{outcome}",
           prov, object_id=row.get("object_id"),
           payload={"dispute_id": dispute_id, "outcome": outcome,
                    "adjudicator": adjudicator,
                    "stale_marked": stale_marked})
    project_mod.append_events(root, pkg, events)
    project_mod.save_facts(root, pkg.get("facts") or [])
    project_mod.save_relations(root, pkg.get("relations") or [])
    project_mod.save_disputes(root, disputes)
    memory = pkg["memory"]
    project_mod.refresh_counts(memory, pkg)
    project_mod.save_memory(root, memory)
    return {"dispute_id": dispute_id, "outcome": outcome,
            "stale_marked": stale_marked}


# ---------------------------------------------------------------- 查询

def facts_as_of(facts, when, *, known_at=None) -> list:
    """as-of 回溯：返回在 when 时点有效的事实集（有效时间维度）。

    语义为半开区间 [valid_at, invalid_at)：when == valid_at 入选，
    when == invalid_at 不入选。known_at 给出时再叠事务时间过滤
    （当时系统已知：created_at <= known_at 且未在 known_at 前被失效化）。
    状态不设限——被取代的事实在其有效窗口内仍是「当时为真」。
    """
    w = parse_time(when)
    if w is None:
        raise VerdictError([f"as-of 时间无法解析：{when}"])
    k = parse_time(known_at) if known_at else None
    out = []
    for f in facts or []:
        valid = parse_time(f.get("valid_at"))
        if valid is None or valid > w:
            continue
        invalid = parse_time(f.get("invalid_at"))
        if invalid is not None and w >= invalid:
            continue
        if k is not None:
            created = parse_time(f.get("created_at"))
            if created is not None and created > k:
                continue
            expired = parse_time(f.get("expired_at"))
            if expired is not None and expired <= k:
                continue
        out.append(f)
    return out


def current_facts(facts) -> list:
    return [f for f in facts or [] if f.get("status") == "current"]
