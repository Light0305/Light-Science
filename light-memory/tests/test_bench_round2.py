"""bench 提分第二轮的检索管线回归（2026-10-21）。

钉住四处实现层改动，每处对应一个曾实测的失分形态：
- FTS 按 bm25 相关性排序（原来是近 rowid 序，目标事实被噪声
  条目压在 top-5 外）；
- FTS 证据单元门：中文以相邻字对（bigram）为证据单元，命中
  单元不足 2 的块不算词法命中（单字巧合子串不是证据，如查询
  「采集」对语料「数据集」）；
- 跨语言查询扩展：纯拉丁查询经伪相关反馈拼入中文 bigram；
- 关系路派生强化：种子间沿 derived-from 派生边互记传播分
  （取代边不参与强化）。
"""

from light_memory import bench, index as index_mod
from light_memory import project as project_mod, registry, retrieve
from light_memory.supersede import apply_nominations

_PROV = {"source_package": "analysis", "source_artifact": "card",
         "source_anchor": "C1", "source_version": "1",
         "ingested_at": "2026-10-20T00:00:00+00:00"}


def _store(mem_root, statement, object_id="claim:C1", **kw):
    out = apply_nominations(mem_root, [{
        "verdict": "store", "nominator": "t", "provenance": _PROV,
        "fact": {"statement": statement, "fact_type": "generic",
                 "object_id": object_id, "valid_at": "2026-01-01",
                 **kw}}])
    assert out[0]["result"] == "stored", out
    return out[0]["fact_id"]


def _pkg_with_object(mem_root):
    pkg = project_mod.load_package(mem_root)
    registry.register_object(pkg, "claim", "C1", _PROV)
    project_mod.save_objects(mem_root, pkg["objects"])
    return mem_root


def test_fts_bm25_ranks_fuller_match_first(mem_root):
    _pkg_with_object(mem_root)
    _store(mem_root, "苹果香蕉的说明记录")
    _store(mem_root, "苹果香蕉橙子葡萄的说明记录")
    index_mod.build_index(mem_root)
    hits = index_mod.search_fts(mem_root, "苹果香蕉橙子葡萄")
    texts = [h["source_id"] for h in hits]
    assert len(texts) == 2
    full = next(h for h in hits
                if h["chunk_id"] == hits[0]["chunk_id"])
    assert full is hits[0]
    # 命中单元更多（四词全中）的块必须排在只中两词的块之前
    import sqlite3
    con = sqlite3.connect(mem_root / ".index" / "memory_index.sqlite")
    by_chunk = {r[0]: r[1] for r in con.execute(
        "SELECT c0, c3 FROM chunks_fts_content").fetchall()}
    con.close()
    assert "橙 子" in by_chunk[hits[0]["chunk_id"]]
    assert "橙 子" not in by_chunk[hits[1]["chunk_id"]]


def test_fts_unit_gate_drops_single_bigram_coincidence(mem_root):
    _pkg_with_object(mem_root)
    _store(mem_root, "火鸡检测数据集规模统计")
    _store(mem_root, "脑电信号采集方案与电极布置记录")
    index_mod.build_index(mem_root)
    hits = index_mod.search_fts(mem_root, "火鸡脑电信号的采集方案")
    import sqlite3
    con = sqlite3.connect(mem_root / ".index" / "memory_index.sqlite")
    by_chunk = {r[0]: r[1] for r in con.execute(
        "SELECT c0, c3 FROM chunks_fts_content").fetchall()}
    con.close()
    texts = [by_chunk[h["chunk_id"]] for h in hits]
    # 只共享「火鸡」一个字对的块不算词法命中；真同题块必须在
    assert any("脑 电" in t for t in texts)
    assert not any("数 据 集" in t for t in texts)


def test_expand_query_only_for_latin_and_from_corpus(tmp_path):
    base = tmp_path / "world"
    bench.build_mini_world(base)
    root = base / "proj-a"
    zh = "阈值预测映射的稳定性如何"
    assert index_mod.expand_query(root, zh) == zh
    out = index_mod.expand_query(
        root, "tracker thresholds predicted from video statistics")
    assert out.startswith("tracker thresholds")
    # 扩展词必须来自语料本身（迷你世界多块共现的「阈值」）
    assert "阈值" in out


def test_derived_from_reinforcement_marks_relation_route(tmp_path):
    base = tmp_path / "world"
    bench.build_mini_world(base)
    res = retrieve.recall(base / "proj-a",
                          "核验版本完整性与登记对象完整形态",
                          account_strength=False)
    fail = next(i for i in res["items"]
                if "数据版本交付不完整" in i["match_text"])
    # 失败事实与教训同为种子时，旧管线下它拿不到 relation 路；
    # 沿 derived-from 派生边的强化分必须给它记上关系路信号。
    assert "relation" in fail["routes"]
