"""规格集展开：计数、约束剪枝、超限抽样、入集门、冻结哈希。"""

import random

from light_analysis.specs import (
    brute_force_reachable, build_ledger, enumerate_reachable, freeze_ledger,
    verify_ledger_hash,
)

JUST = "有登记依据的决策点"


def dec(point, options, just=JUST):
    return {"point": point, "options": options,
            "theoretical_justification": just}


def test_full_product_expansion():
    ledger = build_ledger([dec("a", ["a1", "a2"]), dec("b", ["b1", "b2", "b3"])])
    assert ledger["reachable_count"] == 6
    assert [s["spec_id"] for s in ledger["specs"]] == \
        [f"S{i:03d}" for i in range(1, 7)]
    assert all(s["status"] == "included" for s in ledger["specs"])
    assert ledger["sampling"] is None


def test_forbids_pruning_count():
    decisions = [dec("a", ["a1", "a2"]), dec("b", ["b1", "b2"])]
    constraints = [{"forbids": {"a": "a1", "b": "b1"}}]
    ledger = build_ledger(decisions, constraints)
    assert ledger["reachable_count"] == 3  # 4 个名义组合剪掉 1 个不可达
    combos = {tuple(sorted(s["choices"].items())) for s in ledger["specs"]}
    assert (("a", "a1"), ("b", "b1")) not in combos


def test_dfs_matches_brute_force():
    rng = random.Random(7)
    decisions = []
    for i in range(4):
        decisions.append(dec(f"p{i}", [f"o{i}_{j}" for j in range(3)]))
    constraints = [
        {"forbids": {"p0": "o0_0", "p2": "o2_1"}},
        {"forbids": {"p1": "o1_2"}},
        {"forbids": {"p3": "o3_0", "p0": "o0_2", "p1": "o1_0"}},
    ]
    fast = enumerate_reachable(
        [{"point": d["point"],
          "options": [{"name": o, "valid": True} for o in
                      (d["options"] if isinstance(d["options"][0], str)
                       else d["options"])],
          "theoretical_justification": JUST} for d in decisions],
        constraints)
    slow = brute_force_reachable(
        [{"point": d["point"],
          "options": [{"name": o, "valid": True} for o in d["options"]],
          "theoretical_justification": JUST} for d in decisions],
        constraints)
    key = lambda rows: sorted(tuple(sorted(r.items())) for r in rows)
    assert key(fast) == key(slow)
    assert 0 < len(fast) < 81  # 名义叉积 3^4=81，约束确实剪掉了分支


def test_over_cap_sampling_records_seed():
    decisions = [dec(f"p{i}", ["x", "y"]) for i in range(10)]  # 2^10=1024
    ledger = build_ledger(decisions, seed=42)
    assert ledger["reachable_count"] == 1024
    assert len(ledger["specs"]) == 512
    assert ledger["sampling"]["seed"] == 42
    assert ledger["sampling"]["reachable_total"] == 1024
    assert ledger["sampling"]["kept"] == 512
    # 同种子重建 → 同一抽样集（可复现）
    again = build_ledger(decisions, seed=42)
    assert [s["choices"] for s in again["specs"]] == \
        [s["choices"] for s in ledger["specs"]]


def test_exactly_at_cap_no_sampling():
    decisions = [dec(f"p{i}", ["x", "y"]) for i in range(9)]  # 2^9=512
    ledger = build_ledger(decisions)
    assert ledger["reachable_count"] == 512
    assert ledger["sampling"] is None
    assert len(ledger["specs"]) == 512


def test_statistical_gate_excludes_invalid_option():
    decisions = [{"point": "model",
                  "options": [{"name": "ok", "valid": True},
                              {"name": "broken", "valid": False}],
                  "theoretical_justification": JUST}]
    ledger = build_ledger(decisions)
    by_choice = {s["choices"]["model"]: s for s in ledger["specs"]}
    assert by_choice["ok"]["status"] == "included"
    assert by_choice["broken"]["status"] == "excluded"
    assert by_choice["broken"]["gate"]["statistical"] == "fail"
    assert "statistical" in by_choice["broken"]["exclude_reason"]


def test_theoretical_gate_requires_written_justification():
    ledger = build_ledger([dec("a", ["a1"], just="")])
    assert ledger["specs"][0]["status"] == "excluded"
    assert ledger["specs"][0]["gate"]["theoretical"] == "fail"


def test_freeze_hash_roundtrip_and_tamper():
    ledger = build_ledger([dec("a", ["a1", "a2"])])
    ok, _ = verify_ledger_hash(ledger)
    assert not ok  # 未冻结
    freeze_ledger(ledger)
    ok, _ = verify_ledger_hash(ledger)
    assert ok
    ledger["specs"][0]["choices"]["a"] = "a2"  # 冻结后改动
    ok, detail = verify_ledger_hash(ledger)
    assert not ok and "改动" in detail
    # expansions 是冻结后只增留痕区，追加不触发篡改判定
    ledger2 = build_ledger([dec("a", ["a1"])])
    freeze_ledger(ledger2)
    ledger2["expansions"].append({"at": "2026-10-20", "decision": "加一条",
                                  "motivation": "复核要求", "seen_results": True,
                                  "affected_lines": ["L-OK"]})
    ok, _ = verify_ledger_hash(ledger2)
    assert ok
