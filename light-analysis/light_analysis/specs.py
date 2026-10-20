"""规格集账本：枚举展开（惰性求值口径）+ 机械两门 + 冻结哈希。

拍板②（双层）：工具负责枚举展开 + 机械两门校验（统计有效性、
非冗余）+ 展开账本冻结；「理论上正当」逐决策点落字理由（字段在，
理由缺失 → 全规格理论门不过、整集 excluded 并点名），复核环节抽查。

惰性求值口径：规格数 = 约束下**可达组合**数，不是名义叉积——
枚举用 DFS + 约束剪枝：部分赋值已命中某条 forbids 模式即剪掉整支，
不可达分支不展开、不计数。
"""

from __future__ import annotations

import itertools
import random

from .schema import SPEC_CAP
from .util import component_hash, today

DEFAULT_SAMPLE_SEED = 20261020
SAMPLE_RULE = "random_sample_without_replacement（规范序全集上无放回抽样）"


def normalize_decisions(decisions):
    """决策点规范化：options 统一成 {name, valid} 形态。"""
    out = []
    for d in decisions or []:
        opts = []
        for o in d.get("options") or []:
            if isinstance(o, dict):
                opts.append({"name": o["name"],
                             "valid": bool(o.get("valid", True))})
            else:
                opts.append({"name": o, "valid": True})
        out.append({
            "point": d["point"],
            "options": opts,
            "theoretical_justification": d.get("theoretical_justification"),
        })
    return out


def _pattern_hits(assignment: dict, pattern: dict) -> bool:
    """部分赋值是否已完整命中一条 forbids 模式（命中的点都已赋值且相等）。"""
    return all(p in assignment and assignment[p] == o
               for p, o in pattern.items())


def enumerate_reachable(decisions, constraints):
    """DFS + 剪枝枚举全部可达组合，返回 choices dict 列表（规范序）。

    规范序 = 按决策点声明顺序、选项声明顺序的字典序，
    保证同一输入永远展开出同一 spec_id 序列。
    """
    points = [d["point"] for d in decisions]
    patterns = [(c or {}).get("forbids") or {} for c in (constraints or [])]
    patterns = [p for p in patterns if p]
    results: list[dict] = []
    assignment: dict = {}

    def dfs(i: int):
        if any(_pattern_hits(assignment, p) for p in patterns):
            return
        if i == len(points):
            results.append(dict(assignment))
            return
        point = points[i]
        for opt in decisions[i]["options"]:
            assignment[point] = opt["name"]
            dfs(i + 1)
            del assignment[point]

    dfs(0)
    return results


def brute_force_reachable(decisions, constraints):
    """名义叉积全展开后过滤（仅供测试对拍 DFS 剪枝的正确性）。"""
    points = [d["point"] for d in decisions]
    names = [[o["name"] for o in d["options"]] for d in decisions]
    patterns = [(c or {}).get("forbids") or {} for c in (constraints or [])]
    out = []
    for combo in itertools.product(*names):
        a = dict(zip(points, combo))
        if any(all(a.get(p) == o for p, o in pat.items()) for pat in patterns if pat):
            continue
        out.append(a)
    return out


def evaluate_gates(choices: dict, decisions) -> dict:
    """逐规格三门：理论门看落字理由齐全，统计门看选项有效性，非冗余由枚举唯一性保证。"""
    by_point = {d["point"]: d for d in decisions}
    theoretical = all(
        (by_point[p].get("theoretical_justification") or "").strip()
        for p in choices)
    statistical = all(
        next(o for o in by_point[p]["options"] if o["name"] == name)["valid"]
        for p, name in choices.items())
    return {
        "theoretical": "pass" if theoretical else "fail",
        "statistical": "pass" if statistical else "fail",
        "nonredundant": "pass",
    }


def build_ledger(decisions, constraints=None, cap=SPEC_CAP,
                 seed=DEFAULT_SAMPLE_SEED, spec_version="0.1") -> dict:
    """由决策点 + 约束生成完整账本（未冻结）：展开 → 抽样（超限时）→ 逐规格过门。"""
    decisions = normalize_decisions(decisions)
    constraints = constraints or []
    reachable = enumerate_reachable(decisions, constraints)
    reachable_total = len(reachable)

    sampling = None
    kept = reachable
    if reachable_total > cap:
        rng = random.Random(seed)
        idx = sorted(rng.sample(range(reachable_total), cap))
        kept = [reachable[i] for i in idx]
        sampling = {
            "rule": SAMPLE_RULE,
            "seed": seed,
            "reachable_total": reachable_total,
            "kept": cap,
        }

    specs = []
    for i, choices in enumerate(kept, start=1):
        gate = evaluate_gates(choices, decisions)
        failed = [k for k, v in gate.items() if v != "pass"]
        specs.append({
            "spec_id": f"S{i:03d}",
            "choices": choices,
            "gate": gate,
            "status": "excluded" if failed else "included",
            "exclude_reason": (
                "入集门未过：" + "、".join(failed)) if failed else None,
        })

    return {
        "spec_version": spec_version,
        "decisions": decisions,
        "constraints": constraints,
        "sampling": sampling,
        "reachable_count": reachable_total,
        "specs": specs,
        "expansions": [],
        "frozen_hash": None,
        "frozen_at": None,
    }


def ledger_hash_content(ledger: dict) -> dict:
    """冻结哈希的覆盖面：决策点/约束/抽样/规格四区。

    expansions（自由度账本）是冻结后只增的留痕区，不入冻结哈希——
    记账不算篡改账本本体；但 expansions 的每条都带 affected_lines，
    校验器另行核对未登记扩增（Phase 2）。
    """
    return {
        "spec_version": ledger.get("spec_version"),
        "decisions": ledger.get("decisions"),
        "constraints": ledger.get("constraints"),
        "sampling": ledger.get("sampling"),
        "reachable_count": ledger.get("reachable_count"),
        "specs": ledger.get("specs"),
    }


def freeze_ledger(ledger: dict) -> dict:
    ledger["frozen_hash"] = component_hash(ledger_hash_content(ledger))
    ledger["frozen_at"] = today()
    return ledger


def verify_ledger_hash(ledger: dict):
    """返回 (ok, detail)：未冻结返回 (False, '未冻结')，哈希不符即篡改。"""
    frozen = ledger.get("frozen_hash")
    if not frozen:
        return False, "spec_ledger 未冻结（frozen_hash 为空）"
    actual = component_hash(ledger_hash_content(ledger))
    if actual != frozen:
        return False, ("spec_ledger 冻结后被改动：重算哈希 "
                       f"{actual[:12]}… ≠ 冻结哈希 {frozen[:12]}…")
    return True, "ok"
