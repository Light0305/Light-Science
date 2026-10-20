"""取代链：五值判定各一、区间算术含界、无时间戳阻断、争议不改事实、
裁决三结论、算子查表、防环、派生 stale 传播、as-of 回溯。"""

import pytest

from light_memory import project as project_mod
from light_memory.supersede import VerdictError, apply_nominations, \
    facts_as_of, resolve_dispute


def _nom(verdict, statement=None, *, obj="claim:C1", valid=None,
         ftype="conclusion", target=None, nominator="tester", **kw):
    nom = {"verdict": verdict, "nominator": nominator,
           "rationale": "测试提名"}
    if statement is not None:
        nom["fact"] = {"statement": statement, "fact_type": ftype,
                       "object_id": obj, "valid_at": valid}
        nom["fact"].update(kw.pop("fact_extra", {}))
    if target:
        nom["target_fact_id"] = target
    nom.update(kw)
    return nom


def _store(root, statement, **kw):
    out = apply_nominations(root, [_nom("store", statement, **kw)])[0]
    assert out["result"] == "stored", out
    return out["fact_id"]


def _facts(root):
    return {f["fact_id"]: f
            for f in project_mod.load_package(root)["facts"]}


# ---------------------------------------------------------------- 五值

def test_store_and_skip(mem_root):
    fid = _store(mem_root, "结论一", valid="2026-01-01")
    out = apply_nominations(
        mem_root, [_nom("skip", "无增量草稿", valid="2026-01-02")])[0]
    assert out["result"] == "skipped"
    facts = _facts(mem_root)
    assert list(facts) == [fid]  # skip 不落事实，只落判定事件
    events = project_mod.load_package(mem_root)["events"]
    assert any(e["type"] == "verdict" for e in events)


def test_store_duplicate_is_idempotent(mem_root):
    _store(mem_root, "结论一", valid="2026-01-01")
    out = apply_nominations(
        mem_root, [_nom("store", "结论一", valid="2026-01-01")])[0]
    assert out["result"] == "already_stored"
    assert len(_facts(mem_root)) == 1


def test_supersede_overlap_invalidates(mem_root):
    old = _store(mem_root, "结论 v1", valid="2026-01-01")
    out = apply_nominations(mem_root, [
        _nom("supersede", "结论 v2", valid="2026-03-01", target=old)])[0]
    assert out["result"] == "superseded"
    facts = _facts(mem_root)
    assert facts[old]["status"] == "superseded"
    assert facts[old]["invalid_at"] == "2026-03-01"  # 盖新版 valid_at
    assert facts[old]["superseded_by"] == out["fact_id"]
    assert facts[out["fact_id"]]["supersedes"] == old
    rels = project_mod.load_package(mem_root)["relations"]
    assert any(r["type"] == "supersedes" and r["from_id"] == out["fact_id"]
               and r["to_id"] == old for r in rels)


def test_supersede_boundary_touching_no_overlap(mem_root):
    old = _store(mem_root, "结论 v1", valid="2026-01-01",
                 fact_extra={"invalid_at": "2026-02-01"})
    out = apply_nominations(mem_root, [
        _nom("supersede", "结论 v2", valid="2026-02-01", target=old)])[0]
    # 半开区间边界相接：不重叠 → 两版并存为 current
    assert out["result"] == "stored_both_current_no_overlap"
    facts = _facts(mem_root)
    assert facts[old]["status"] == "current"
    assert facts[old]["invalid_at"] == "2026-02-01"


def test_supersede_inside_interval(mem_root):
    old = _store(mem_root, "结论 v1", valid="2026-01-01",
                 fact_extra={"invalid_at": "2026-02-01"})
    out = apply_nominations(mem_root, [
        _nom("supersede", "结论 v2", valid="2026-01-15", target=old)])[0]
    assert out["result"] == "superseded"
    assert _facts(mem_root)[old]["invalid_at"] == "2026-01-15"


def test_supersede_without_timestamps_blocked(mem_root):
    old = _store(mem_root, "无时间结论")  # valid=None
    before = dict(_facts(mem_root)[old])
    out = apply_nominations(mem_root, [
        _nom("supersede", "新版", valid="2026-03-01", target=old)])[0]
    assert out["result"] == "blocked_no_timestamps"
    after = _facts(mem_root)[old]
    assert after["status"] == "current"
    assert after["invalid_at"] == before["invalid_at"]  # 本体未动


def test_merge_lesson_unions_span_and_provenance(mem_root):
    old = _store(mem_root, "教训 v1", valid="2026-01-10", ftype="lesson",
                 obj="failure:F-1")
    out = apply_nominations(mem_root, [
        _nom("merge", "教训补充", valid="2025-12-01", ftype="lesson",
             obj="failure:F-1", target=old,
             merged_statement="教训合并版")])[0]
    assert out["result"] == "merged"
    facts = _facts(mem_root)
    merged = facts[out["fact_id"]]
    assert merged["statement"] == "教训合并版"
    assert merged["valid_at"] == "2025-12-01"  # 跨度取并集（更早）
    assert len(merged["provenance"]) >= 2  # 溯源取并集
    assert facts[old]["status"] == "superseded"
    assert facts[old]["superseded_by"] == out["fact_id"]


def test_merge_conclusion_forbidden_by_operator_table(mem_root):
    old = _store(mem_root, "结论 v1", valid="2026-01-01")
    out = apply_nominations(mem_root, [
        _nom("merge", "结论补充", valid="2026-02-01", target=old,
             merged_statement="合并版")])[0]
    assert out["result"] == "operator_forbidden"
    assert out["operator"] == "supersede_only"
    assert _facts(mem_root)[old]["status"] == "current"  # 未被动


# ---------------------------------------------------------------- 争议

def _dispute_pair(root):
    old = _store(root, "在位结论", valid="2026-01-01")
    out = apply_nominations(root, [
        _nom("dispute", "挑战结论", valid="2026-02-01", target=old)])[0]
    assert out["result"] == "disputed"
    return old, out["fact_id"], out["dispute_id"]


def test_dispute_registers_without_changing_facts(mem_root):
    old = _store(mem_root, "在位结论", valid="2026-01-01")
    before = dict(_facts(mem_root)[old])
    out = apply_nominations(mem_root, [
        _nom("dispute", "挑战结论", valid="2026-02-01", target=old)])[0]
    after = _facts(mem_root)[old]
    # 事实本体不动：陈述与双时间一字未改，只状态转 disputed（MM-15）
    for key in ("statement", "valid_at", "invalid_at", "superseded_by"):
        assert after[key] == before[key]
    assert after["status"] == "disputed"
    pkg = project_mod.load_package(mem_root)
    assert pkg["disputes"][0]["status"] == "open"
    assert pkg["disputes"][0]["dispute_id"] == out["dispute_id"]


def test_resolve_challenger_wins(mem_root):
    old, challenger, did = _dispute_pair(mem_root)
    res = resolve_dispute(mem_root, did, "challenger_wins",
                          adjudicator="用户", rationale="新证据更强")
    facts = _facts(mem_root)
    assert facts[old]["status"] == "superseded"
    assert facts[old]["invalid_at"] == "2026-02-01"
    assert facts[challenger]["status"] == "current"
    pkg = project_mod.load_package(mem_root)
    assert pkg["disputes"][0]["status"] == "resolved"
    assert pkg["disputes"][0]["resolution"]["adjudicator"] == "用户"
    assert res["outcome"] == "challenger_wins"


def test_resolve_incumbent_wins(mem_root):
    old, challenger, did = _dispute_pair(mem_root)
    resolve_dispute(mem_root, did, "incumbent_wins", adjudicator="用户")
    facts = _facts(mem_root)
    assert facts[old]["status"] == "current"
    assert facts[challenger]["status"] == "superseded"
    # 挑战方从未生效：零长区间
    assert facts[challenger]["invalid_at"] == \
        facts[challenger]["valid_at"]


def test_resolve_both_stand(mem_root):
    old, challenger, did = _dispute_pair(mem_root)
    resolve_dispute(mem_root, did, "both_stand", adjudicator="用户")
    facts = _facts(mem_root)
    assert facts[old]["status"] == "current"
    assert facts[challenger]["status"] == "current"


def test_resolve_challenger_wins_needs_timestamps(mem_root):
    old = _store(mem_root, "无时间在位结论")
    out = apply_nominations(mem_root, [
        _nom("dispute", "无时间挑战", target=old)])[0]
    with pytest.raises(VerdictError):
        resolve_dispute(mem_root, out["dispute_id"], "challenger_wins",
                        adjudicator="用户")
    pkg = project_mod.load_package(mem_root)
    assert pkg["disputes"][0]["status"] == "open"  # 拒后保持 open


# ---------------------------------------------------------------- 防环/传播

def test_supersede_cycle_rejected(mem_root):
    a = _store(mem_root, "事实甲", valid="2026-01-01")
    b = _store(mem_root, "事实乙", valid="2026-02-01")
    out = apply_nominations(mem_root, [
        _nom("supersede", "事实乙", valid="2026-02-01", target=a)])[0]
    assert out["result"] == "superseded"  # 乙取代甲（复用既有事实）
    out2 = apply_nominations(mem_root, [
        _nom("supersede", "事实甲", valid="2026-01-01", target=b)])[0]
    assert out2["result"] == "cycle_rejected"  # 甲再取代乙即成环
    assert _facts(mem_root)[b]["status"] == "current"


def test_derived_propagation_marks_stale_transitively(mem_root):
    base = _store(mem_root, "基础事实", valid="2026-01-01",
                  ftype="generic", obj="paper:p1")
    mid = _store(mem_root, "一层派生", valid="2026-01-02", ftype="generic",
                 obj="paper:p1", fact_extra={"derived_from": [base]})
    leaf = _store(mem_root, "二层派生", valid="2026-01-03",
                  ftype="generic", obj="paper:p1",
                  fact_extra={"derived_from": [mid]})
    out = apply_nominations(mem_root, [
        _nom("supersede", "基础事实 v2", valid="2026-03-01",
             ftype="generic", obj="paper:p1", target=base)])[0]
    assert out["result"] == "superseded"
    assert set(out["stale_marked"]) == {mid, leaf}
    facts = _facts(mem_root)
    assert facts[mid]["stale"] is True and facts[leaf]["stale"] is True
    assert facts[mid]["status"] == "current"  # 标 stale 不改状态


# ---------------------------------------------------------------- as-of

def test_facts_as_of_boundaries(mem_root):
    old = _store(mem_root, "旧结论", valid="2026-01-01")
    new = apply_nominations(mem_root, [
        _nom("supersede", "新结论", valid="2026-03-01", target=old)
    ])[0]["fact_id"]
    facts = list(_facts(mem_root).values())
    ids = lambda rows: {f["fact_id"] for f in rows}
    assert ids(facts_as_of(facts, "2025-12-31")) == set()
    assert ids(facts_as_of(facts, "2026-02-15")) == {old}
    # 边界：when == 新版 valid_at 入选新版；== 旧版 invalid_at 不入旧版
    assert ids(facts_as_of(facts, "2026-03-01")) == {new}
    assert ids(facts_as_of(facts, "2026-01-01")) == {old}
