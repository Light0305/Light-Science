"""修复批新行为（D-S1 成本点 / D-S2 正证据门槛 / D-S3 跨项目保底）。

- D-S2：判据从「单字 token 交集 >= 2」换成证据单元口径（中文
  bigram / 拉丁整词，命中 >= 2 且覆盖 >= 1/3）——钉住 rf-03/
  rf-04 型单 bigram 巧合不再算证据、真证据仍算证据。
- D-S3：跨项目合并按包内名次轮转交织——钉住保底位置界与条目
  集合不变（纯排序变更）。
- D-S1：三处缓存/按需取数——钉住结果与无缓存实现一致、且文件
  变更后缓存失效（不许读到旧状态）。
"""

import sqlite3
from pathlib import Path

import pytest

from light_memory import bench, index as index_mod, retrieve


@pytest.fixture()
def world(tmp_path):
    base = tmp_path / "world"
    bench.build_mini_world(base)
    return base


# ---------------------------------------------------------------- D-S2

def _item(text, routes=("fts",)):
    return {"match_text": text, "routes": list(routes)}


def test_refusal_single_bigram_coincidence_not_evidence():
    # rf-03 型：查询问葡萄糖，条目讲葡萄园——只共享 bigram「葡萄」
    q = "量子纠缠对葡萄糖代谢通路的影响"
    item = _item("葡萄园灌溉采用滴灌方式，葡萄采收期集中在九月")
    matched, total = bench._evidence_units(q, item["match_text"])
    assert matched == 1 and total > 3
    assert not bench._item_evidenced(q, item)


def test_refusal_greenhouse_tomato_not_evidence():
    # rf-04 型：查询问番茄炒蛋，条目讲温室番茄——只共享「番茄」
    q = "番茄炒蛋先放蛋还是先放番茄"
    item = _item("温室番茄采用熊蜂授粉，定植密度每亩两千株")
    assert not bench._item_evidenced(q, item)


def test_refusal_true_evidence_passes_gate():
    q = "跟踪器 MOTA 提升了多少个百分点"
    item = _item("跟踪器在 7 段视频上 MOTA 提升 3.10 个百分点"
                 "（复核修正版）")
    assert bench._item_evidenced(q, item)


def test_refusal_coverage_gate_blocks_thin_overlap():
    # 命中 2 个整词但只覆盖长查询的 1/5：不算证据
    q = "what did the committee decide about the annual budget " \
        "report yesterday"
    thin = _item("the committee met yesterday", routes=("relation",))
    assert not bench._item_evidenced(q, thin)
    solid = _item("the committee decided the annual budget report",
                  routes=("relation",))
    assert bench._item_evidenced(q, solid)


def test_refusal_vector_only_route_never_evidence():
    # 向量弱命中不算证据（路由门不变）：判分层验证
    q = "跟踪器 MOTA 提升了多少个百分点"
    result = {"items": [_item("跟踪器在 7 段视频上 MOTA 提升 3.10 "
                              "个百分点", routes=("vector",))]}
    ok, detail = bench._score_item(result, {"refusal": True}, q)
    assert ok and detail["evidenced_hits"] == 0


def test_refusal_score_item_uses_new_gate():
    q = "量子纠缠对葡萄糖代谢通路的影响"
    weak = {"items": [_item("葡萄园灌溉采用滴灌方式", ("fts",))]}
    ok, _ = bench._score_item(weak, {"refusal": True}, q)
    assert ok  # 单 bigram 巧合 -> 正确拒答
    strong = {"items": [_item("量子纠缠对葡萄糖代谢通路的影响已有"
                              "定论", ("fts",))]}
    ok, detail = bench._score_item(strong, {"refusal": True}, q)
    assert not ok and detail["evidenced_hits"] == 1


def test_refusal_single_unit_query_edge():
    # 查询只有一个证据单元（如两字词）：命中该单元即全覆盖
    assert bench._item_evidenced("番茄", _item("温室番茄栽培"))
    assert not bench._item_evidenced("番茄", _item("温室黄瓜栽培"))


# ---------------------------------------------------------------- D-S3

def test_interleave_guarantee_positions():
    roots = [(Path("pa"), {}), (Path("pb"), {})]
    items = [
        {"root": "pa", "score": 0.90, "tag": "a1"},
        {"root": "pa", "score": 0.80, "tag": "a2"},
        {"root": "pa", "score": 0.10, "tag": "a3"},
        {"root": "pb", "score": 0.95, "tag": "b1"},
        {"root": "pb", "score": 0.20, "tag": "b2"},
    ]
    merged = retrieve._interleave_by_project(items, roots)
    # 包优先级由首条分定：pb(0.95) 先行 -> b1 a1 b2 a2 a3
    assert [i["tag"] for i in merged] == ["b1", "a1", "b2", "a2", "a3"]
    # 条目集合不变（纯排序变更）
    assert {i["tag"] for i in merged} == {i["tag"] for i in items}
    # 保底位置界：两包时本地第 r 名位置 <= 2r（先行包 <= 2r-1）
    pos = {i["tag"]: n + 1 for n, i in enumerate(merged)}
    assert pos["b2"] <= 3 and pos["a2"] <= 4 and pos["a3"] <= 6


def test_cross_recall_interleaves_projects(world):
    a, b = world / "proj-a", world / "proj-b"
    result = retrieve.recall(a, "阈值预测映射的稳定性如何",
                             recipe="cross-project", extra_roots=[b],
                             account_strength=False)
    assert result["ok"]
    projects = [i["project"] for i in result["items"]]
    # 两包本地第 1 名必进合并序前 2 位
    assert set(projects[:2]) == {"turkey-a", "turkey-b"}


def test_single_root_recall_keeps_score_order(world):
    a = world / "proj-a"
    result = retrieve.recall(a, "阈值预测映射在顶视固定机位下稳定成立",
                             account_strength=False)
    scores = [i["score"] for i in result["items"]]
    assert scores == sorted(scores, reverse=True)


# ---------------------------------------------------------------- D-S1

def test_search_fts_matches_bruteforce_reference(world):
    a = world / "proj-a"
    got = index_mod.search_fts(a, "阈值预测映射", limit=10)
    con = sqlite3.connect(a / ".index" / index_mod.INDEX_DB)
    try:
        texts = {r[0]: r[1] for r in con.execute(
            "SELECT c0, c3 FROM chunks_fts_content").fetchall()}
    finally:
        con.close()
    units = set(index_mod._query_units("阈值预测映射"))
    expect_ids = set()
    for cid, text in texts.items():
        if index_mod._matched_units(units, text.split()) >= 2:
            expect_ids.add(cid)
    assert {r["chunk_id"] for r in got} <= expect_ids
    assert got  # 迷你世界里该查询确有词法命中


def test_vector_cache_invalidation_on_rebuild(world):
    a = world / "proj-a"
    before = index_mod.search_vector(a, "阈值预测", limit=30)
    from light_memory import project as project_mod, schema
    pkg = project_mod.load_package(a)
    prov = schema.make_provenance("test", "fixbatch", "t1", "1")
    fact = schema.new_fact("量子点发光二极管效率纪录刷新", "conclusion",
                           "obj:x", prov, valid_at="2026-03-01")
    pkg["facts"].append(fact)
    project_mod.save_facts(a, pkg["facts"])
    index_mod.build_index(a)
    after = index_mod.search_vector(a, "量子点发光二极管", limit=30)
    assert len(after) == len(before) + 1
    assert any(r["source_id"] == fact["fact_id"] for r in after)


def test_truth_manifest_memo_and_invalidation(world):
    a = world / "proj-a"
    m1 = index_mod.truth_manifest(a)
    m2 = index_mod.truth_manifest(a)
    assert m1 == m2 and m1  # 备忘回放一致
    p = a / "facts.jsonl"
    p.write_text(p.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    m3 = index_mod.truth_manifest(a)
    assert m3["facts.jsonl"] != m1["facts.jsonl"]  # 改文件即失效


def test_pkg_cache_invalidation_on_write(world):
    a = world / "proj-a"
    r1 = retrieve.recall(a, "阈值预测映射", account_strength=False)
    assert r1["ok"]
    from light_memory import project as project_mod, schema
    pkg = project_mod.load_package(a)
    prov = schema.make_provenance("test", "fixbatch", "t2", "1")
    fact = schema.new_fact("阈值预测映射在夜间红外机位下同样稳定",
                           "method", "obj:y", prov, valid_at="2026-03-02")
    pkg["facts"].append(fact)
    project_mod.save_facts(a, pkg["facts"])
    index_mod.build_index(a)
    r2 = retrieve.recall(a, "阈值预测映射", account_strength=False)
    assert any(i["source_id"] == fact["fact_id"] for i in r2["items"])
