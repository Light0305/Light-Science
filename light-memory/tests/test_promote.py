"""晋升通道：候选 → 确认 → 复制入全局层；撤回对账；原件不动。"""

import pytest

from light_memory import bench, candidates as cand
from light_memory import project as project_mod, promote
from light_memory.validate import validate_package


@pytest.fixture()
def world(tmp_path):
    base = tmp_path / "world"
    bench.build_mini_world(base)
    return base


def _lesson_id(root):
    pkg = project_mod.load_package(root)
    return next(f["fact_id"] for f in pkg["facts"]
                if f["fact_type"] == "lesson")


def test_promote_full_lifecycle(world):
    a, g = world / "proj-a", world / "global"
    fid = _lesson_id(a)
    row = promote.propose(g, a, fid, by="user", reason="跨项目通用")
    assert row["status"] == "pending"
    assert project_mod.load_package(g)["facts"] == []  # 未确认不复制
    # 候选通道的 accept 不许代办 promotion（须走 confirm 跨包复制）
    with pytest.raises(cand.CandidateError):
        cand.accept(g, row["candidate_id"], by="user")
    rec = promote.confirm(g, row["candidate_id"], by="user")
    assert rec["promotion_id"] == "PRM-0001"
    gpkg = project_mod.load_package(g)
    assert len(gpkg["facts"]) == 1
    clone = gpkg["facts"][0]
    assert clone["fact_id"] == fid
    assert clone["extra"]["promotion_id"] == "PRM-0001"
    assert clone["extra"]["promoted_from"]["source_project"] == "turkey-a"
    # 副本的 derived_from 不留悬空指针（源项目事实不在全局层）
    assert clone["derived_from"] == []
    assert clone["extra"]["source_derived_from"]
    # 对象在全局层有注册行；候选已 accepted 并回指晋升号
    assert any(o["object_id"] == clone["object_id"]
               for o in gpkg["objects"])
    kept = cand.get_candidate(g, row["candidate_id"])
    assert kept["status"] == "accepted"
    assert kept["result_ref"] == "PRM-0001"
    # 项目原件一字不动
    assert any(f["fact_id"] == fid
               for f in project_mod.load_package(a)["facts"])
    assert validate_package(g) == []


def test_double_promote_blocked(world):
    a, g = world / "proj-a", world / "global"
    fid = _lesson_id(a)
    promote.confirm(g, promote.propose(
        g, a, fid, by="user")["candidate_id"], by="user")
    row2 = promote.propose(g, a, fid, by="user")
    with pytest.raises(promote.PromoteError):
        promote.confirm(g, row2["candidate_id"], by="user")


def test_withdraw_reconciles_and_keeps_source(world):
    a, g = world / "proj-a", world / "global"
    fid = _lesson_id(a)
    rec = promote.confirm(g, promote.propose(
        g, a, fid, by="user")["candidate_id"], by="user")
    promote.withdraw(g, rec["promotion_id"], by="user", reason="口径变")
    gpkg = project_mod.load_package(g)
    assert gpkg["facts"] == []  # 全局副本对账删除
    rows = promote.load_promotions(g)
    assert [r["action"] for r in rows] == ["promoted", "withdrawn"]
    assert rows[1]["by"] == "user" and rows[1]["reason"] == "口径变"
    # 项目原件仍在
    assert any(f["fact_id"] == fid
               for f in project_mod.load_package(a)["facts"])
    with pytest.raises(promote.PromoteError):
        promote.withdraw(g, rec["promotion_id"], by="user")
    with pytest.raises(promote.PromoteError):
        promote.withdraw(g, "PRM-9999", by="user")


def test_propose_unknown_fact_blocked(world):
    a, g = world / "proj-a", world / "global"
    with pytest.raises(promote.PromoteError):
        promote.propose(g, a, "fact_nope", by="user")
