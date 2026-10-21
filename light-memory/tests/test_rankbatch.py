"""检索深度与排序批（2026-10-22）：三路同深 256、分数融合
（逐路原生分绝对归一）、标识符逐字命中项的行为钉子。

机制来源与实测依据见 20-build/memory-rankbatch.md；验收口径
20-build/memory-rankbatch-ACCEPTANCE.md。
"""

import pytest

from light_memory import bench, index as index_mod
from light_memory import project as project_mod, retrieve
from light_memory.supersede import apply_nominations


@pytest.fixture()
def world(tmp_path):
    base = tmp_path / "world"
    bench.build_mini_world(base)
    return base


def _hit(routes, **raw):
    return {"routes": list(routes), "raw": raw}


# ---------------------------------------------------------------- 融合

def test_fuse_native_score_beats_rank():
    """分数融合：原生分高者胜名次高者（弃秩改分的核心行为）。"""
    hits = {
        ("fact", "a"): _hit(["vector"], vector=0, vector_score=0.2),
        ("fact", "b"): _hit(["vector"], vector=1, vector_score=0.95),
    }
    fused = retrieve._fuse(hits, {"vector": 1.0})
    assert fused[0][0] == ("fact", "b")
    assert fused[0][1] == pytest.approx(0.95)


def test_fuse_fts_bm25_ratio_to_best():
    """fts 归一 = 与最佳 bm25 之比；非负 bm25（弱匹配）计 0。"""
    hits = {
        ("fact", "a"): _hit(["fts"], fts=0, fts_score=-20.0),
        ("fact", "b"): _hit(["fts"], fts=1, fts_score=-5.0),
        ("fact", "c"): _hit(["fts"], fts=2, fts_score=3.0),
    }
    fused = dict(retrieve._fuse(hits, {"fts": 1.0}))
    assert fused[("fact", "a")] == pytest.approx(1.0)
    assert fused[("fact", "b")] == pytest.approx(0.25)
    assert fused[("fact", "c")] == pytest.approx(0.0)


def test_fuse_relation_score_clamped():
    """关系传播分截断 [0,1]：>1 不溢出、梯度保留。"""
    hits = {
        ("fact", "a"): _hit(["relation"], relation=0,
                            relation_score=2.5),
        ("fact", "b"): _hit(["relation"], relation=1,
                            relation_score=0.5),
    }
    fused = dict(retrieve._fuse(hits, {"relation": 0.8}))
    assert fused[("fact", "a")] == pytest.approx(0.8)
    assert fused[("fact", "b")] == pytest.approx(0.4)


def test_fuse_id_match_bonus_once():
    """标识符逐字命中另加一份词法路权重，只计一次。"""
    base = _hit(["fts", "vector"], fts=0, fts_score=-10.0,
                vector=0, vector_score=0.5)
    marked = _hit(["fts", "vector"], fts=0, fts_score=-10.0,
                  vector=0, vector_score=0.5)
    marked["id_match"] = True
    hits = {("fact", "a"): base, ("fact", "b"): marked}
    fused = dict(retrieve._fuse(hits, {"fts": 1.0, "vector": 1.0}))
    assert fused[("fact", "b")] - fused[("fact", "a")] == \
        pytest.approx(1.0)


def test_fuse_missing_scores_do_not_crash():
    """某路原生分缺失（降级/旧索引）时该路不计分、不阻断。"""
    hits = {
        ("fact", "a"): _hit(["fts"], fts=0),
        ("fact", "b"): _hit(["vector"], vector=0, vector_score=0.3),
    }
    fused = retrieve._fuse(hits, {"fts": 1.0, "vector": 1.0})
    assert fused[0][0] == ("fact", "b")
    assert retrieve._fuse({}, {"fts": 1.0}) == []


# ---------------------------------------------------------------- 标识符

def test_query_identifiers_extraction():
    assert index_mod.query_identifiers("FM-3.1 对应哪条失败登记") == \
        ["fm-3.1"]
    assert index_mod.query_identifiers("F-0001 这次失败沉淀的教训") == \
        ["f-0001"]
    assert index_mod.query_identifiers("设计主张 C1 讲了什么") == ["c1"]
    assert index_mod.query_identifiers("火鸡项目的设计主张讲了什么") == []
    assert index_mod.query_identifiers("MOTA 提升 5.25 个百分点") == []
    assert index_mod.query_identifiers("") == []


def test_tokens_contain_seq():
    toks = index_mod.tokenize("FM-3.1 数据版本交付不完整")
    seq = index_mod.identifier_seqs("查 FM-3.1 记录")[0]
    assert index_mod.tokens_contain_seq(toks, seq)
    assert not index_mod.tokens_contain_seq(toks, ["fm", "9", "9"])
    assert not index_mod.tokens_contain_seq(toks, [])


# ---------------------------------------------------------------- 深度/封顶

def test_route_hits_depth_and_relation_cap(world, monkeypatch):
    """三路同深 ROUTE_LIMIT；关系路候选同深封顶。"""
    root = world / "proj-a"
    pkg = project_mod.load_package(root)
    recipe = retrieve.get_recipe(pkg["memory"], "default")
    seen = {}

    real_fts = index_mod.search_fts
    real_vec = index_mod.search_vector

    def cap_fts(r, q, limit=10):
        seen["fts"] = limit
        return real_fts(r, q, limit=limit)

    def cap_vec(r, q, limit=10):
        seen["vector"] = limit
        return real_vec(r, q, limit=limit)

    monkeypatch.setattr(index_mod, "search_fts", cap_fts)
    monkeypatch.setattr(index_mod, "search_vector", cap_vec)
    monkeypatch.setattr(
        retrieve, "_relation_route",
        lambda p, s, r: {f"fake-{i}": 1.0 - i * 0.001
                         for i in range(400)})
    hits = retrieve._route_hits(root, pkg, "MOTA 提升了多少", recipe,
                                [])
    assert seen == {"fts": retrieve.ROUTE_LIMIT,
                    "vector": retrieve.ROUTE_LIMIT}
    rel_keys = [k for k, v in hits.items() if "relation" in v["routes"]]
    assert len(rel_keys) == retrieve.ROUTE_LIMIT


# ---------------------------------------------------------------- 打标

def test_id_match_marked_on_verbatim_fact(mem_root):
    """查询标识符在词法命中事实原文中逐字出现才打标。"""
    root = mem_root
    pkg = project_mod.load_package(root)
    prov = {"source_package": "test", "source_artifact": "t",
            "source_anchor": None, "source_version": "1",
            "ingested_at": "2026-10-22"}
    out = apply_nominations(root, [{
        "verdict": "store", "nominator": "test", "rationale": "t",
        "provenance": prov,
        "fact": {"statement": "FM-3.1 数据版本交付不完整，执行失败",
                 "fact_type": "failure_record", "object_id": "run:R1",
                 "valid_at": "2026-10-20"}}])
    fid = out[0]["fact_id"]
    out2 = apply_nominations(root, [{
        "verdict": "store", "nominator": "test", "rationale": "t",
        "provenance": prov,
        "fact": {"statement": "FM-9.9 另一条不相关的失败记录",
                 "fact_type": "failure_record", "object_id": "run:R2",
                 "valid_at": "2026-10-20"}}])
    fid2 = out2[0]["fact_id"]
    index_mod.build_index(root)
    pkg = project_mod.load_package(root)
    recipe = retrieve.get_recipe(pkg["memory"], "default")
    hits = retrieve._route_hits(root, pkg, "FM-3.1 对应哪条失败登记",
                                recipe, [])
    assert hits[("fact", fid)].get("id_match") is True
    assert hits[("fact", fid2)].get("id_match") is not True
