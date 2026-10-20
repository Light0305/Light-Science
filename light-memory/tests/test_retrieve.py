"""检索三路与渐进披露：效力纪律（失效默认不出、as-of 才出、
争议带标记）、作用域隔离、配方留痕、四封顶、强度记账。"""

import pytest

from light_memory import bench, index as index_mod
from light_memory import project as project_mod, retrieve
from light_memory.supersede import apply_nominations


@pytest.fixture()
def world(tmp_path):
    base = tmp_path / "world"
    bench.build_mini_world(base)
    return base


def _texts(result):
    return [i["match_text"] for i in result["items"]]


# ---------------------------------------------------------------- 效力

def test_superseded_fact_hidden_by_default(world):
    res = retrieve.recall(world / "proj-a", "MOTA 提升",
                          account_strength=False)
    assert res["ok"] is True
    assert any("3.10" in t for t in _texts(res))
    assert not any("5.25" in t for t in _texts(res))
    assert "数据处理" in res["poison_guard"]  # 投毒防线声明头（MM-33）


def test_as_of_recipe_reveals_then_valid_facts(world):
    res = retrieve.recall(world / "proj-a", "MOTA 提升",
                          recipe="as-of", as_of="2026-01-15",
                          account_strength=False)
    assert any("5.25" in t for t in _texts(res))
    assert all(i["validity"] == "as_of" for i in res["items"]
               if i["source_kind"] == "fact")


def test_as_of_recipe_requires_date(world):
    with pytest.raises(retrieve.RetrieveError):
        retrieve.recall(world / "proj-a", "MOTA", recipe="as-of")


def test_disputed_fact_flagged_not_hidden(mem_root):
    prov = {"source_package": "analysis", "source_artifact": "card",
            "source_anchor": "C1", "source_version": "1",
            "ingested_at": "2026-10-20T00:00:00+00:00"}
    from light_memory import registry, schema
    pkg = project_mod.load_package(mem_root)
    registry.register_object(pkg, "claim", "C1", prov)
    project_mod.save_objects(mem_root, pkg["objects"])
    out = apply_nominations(mem_root, [{
        "verdict": "store", "nominator": "t", "provenance": prov,
        "fact": {"statement": "结论甲口径", "fact_type": "conclusion",
                 "object_id": "claim:C1", "valid_at": "2026-01-01"}}])
    fid = out[0]["fact_id"]
    apply_nominations(mem_root, [{
        "verdict": "dispute", "nominator": "t", "provenance": prov,
        "target_fact_id": fid,
        "fact": {"statement": "结论乙口径", "fact_type": "conclusion",
                 "object_id": "claim:C1", "valid_at": "2026-02-01"}}])
    index_mod.build_index(mem_root)
    res = retrieve.recall(mem_root, "结论口径", account_strength=False)
    fact_items = [i for i in res["items"]
                  if i["source_kind"] == "fact"]
    assert fact_items and all(i["disputed"] for i in fact_items)


def test_dormant_fact_hidden_unless_recipe_includes(world):
    a = world / "proj-a"
    pkg = project_mod.load_package(a)
    for f in pkg["facts"]:
        if f["fact_type"] == "lesson":
            f["strength"]["dormant"] = True
    project_mod.save_facts(a, pkg["facts"])
    res = retrieve.recall(a, "数据交付前要核验什么",
                          account_strength=False)
    assert not any("教训" in t for t in _texts(res))
    res2 = retrieve.recall(a, "数据交付前要核验什么",
                           recipe="failure-lookup",
                           account_strength=False)
    assert any("教训" in t for t in _texts(res2))


# ---------------------------------------------------------------- 作用域

def test_project_isolation_by_default(world):
    res = retrieve.recall(world / "proj-a", "阈值预测映射",
                          account_strength=False)
    assert not any("移动机位" in t for t in _texts(res))
    assert {i["project"] for i in res["items"]} == {"turkey-a"}


def test_cross_project_groups_by_project(world):
    res = retrieve.recall(world / "proj-a", "阈值预测映射的稳定性",
                          recipe="cross-project",
                          extra_roots=[world / "proj-b"],
                          account_strength=False)
    by_project = {}
    for i in res["items"]:
        by_project.setdefault(i["project"], []).append(i["match_text"])
    assert any("顶视固定机位" in t for t in by_project["turkey-a"])
    assert any("移动机位" in t for t in by_project["turkey-b"])


# ---------------------------------------------------------------- 披露/封顶

def test_progressive_disclosure_depths(world):
    a = world / "proj-a"
    r0 = retrieve.recall(a, "MOTA 提升", account_strength=False)
    assert all("drill" not in i for i in r0["items"])
    r2 = retrieve.recall(a, "MOTA 提升", depth=2,
                         account_strength=False)
    fact = next(i for i in r2["items"] if i["source_kind"] == "fact")
    assert fact["drill"]["source_package"] == "analysis"
    assert fact["drill"]["source_anchor"]


def test_caps_max_items_and_timeout_failure(world):
    a = world / "proj-a"
    res = retrieve.recall(a, "阈值", caps={"max_items": 2},
                          account_strength=False)
    assert res["count"] == 2
    failed = retrieve.recall(a, "阈值", caps={"timeout_s": 0},
                             account_strength=False)
    assert failed["ok"] is False and failed["error"] == "timeout"


def test_strength_accounting_only_when_enabled(world):
    a = world / "proj-a"
    before = {f["fact_id"]: (f.get("strength") or {}).get("calls", 0)
              for f in project_mod.load_package(a)["facts"]}
    retrieve.recall(a, "MOTA 提升", account_strength=False)
    retrieve.recall(a, "MOTA 提升", account_strength=True)
    after = {f["fact_id"]: (f.get("strength") or {}).get("calls", 0)
             for f in project_mod.load_package(a)["facts"]}
    assert any(after[k] > before[k] for k in after)


# ---------------------------------------------------------------- 配方

def test_recipe_set_leaves_trace(world):
    a = world / "proj-a"
    eff = retrieve.set_recipe(a, "default", {"weights": {"fts": 2.0}},
                              by="user")
    assert eff["weights"]["fts"] == 2.0
    pkg = project_mod.load_package(a)
    assert any(e["type"] == "recipe_change" for e in pkg["events"])
    names = {r["name"] for r in retrieve.list_recipes(pkg["memory"])}
    assert names == {"default", "paraphrase", "failure-lookup",
                     "as-of", "cross-project"}
    with pytest.raises(retrieve.RetrieveError):
        retrieve.set_recipe(a, "no-such-recipe", {"hops": 1}, by="u")
    with pytest.raises(retrieve.RetrieveError):
        retrieve.recall(a, "x", recipe="no-such-recipe")


def test_missing_index_degrades_with_notice(mem_root):
    res = retrieve.recall(mem_root, "任意查询", account_strength=False)
    assert res["ok"] is True
    assert any("索引缺失" in d for d in res["degraded"])
