"""basesio：著述校验、离线求值子集（命中金标/不支持点名/公式跳过）。"""

import pytest

from light_memory import basesio


@pytest.fixture()
def vault(tmp_path):
    v = tmp_path / "vault"
    (v / "notes").mkdir(parents=True)
    (v / "notes" / "a.md").write_text(
        "---\nmemory_id: OBJ-A\nstage: Design\nstatus: current\n"
        "tags:\n  - stage/Design\nscore: 5\n---\n# A\n",
        encoding="utf-8")
    (v / "notes" / "b.md").write_text(
        "---\nmemory_id: OBJ-B\nstage: Write\nstatus: current\n"
        "tags:\n  - stage/Write\nscore: 2\n---\n# B\n",
        encoding="utf-8")
    (v / "c.md").write_text(
        "---\nstage: Design\n---\n# C 无 memory_id\n",
        encoding="utf-8")
    return v


SPEC = {
    "filters": {"and": ['file.hasProperty("memory_id")',
                         'stage == "Design"']},
    "views": [{"type": "table", "name": "全部对象",
               "order": ["file.name", "stage"]}],
}


def test_write_read_roundtrip(tmp_path):
    p = tmp_path / "view.base"
    r = basesio.write_base(p, SPEC)
    assert r["views"] == ["全部对象"]
    assert basesio.read_base(p)["views"][0]["type"] == "table"


def test_write_rejects_bad_view(tmp_path):
    with pytest.raises(basesio.BaseError):
        basesio.write_base(tmp_path / "x.base", {
            "filters": {}, "views": [{"type": "grid", "name": "g"}]})


def test_eval_subset_goldens(vault):
    basesio.write_base(vault / "view.base", SPEC)
    r = basesio.eval_base(vault, "view.base")
    assert r["label"] == "offline-eval"
    assert r["matched"] == ["notes/a.md"]  # b 阶段不符、c 缺属性
    # hasTag 嵌套匹配 + inFolder + or/not 组合
    basesio.write_base(vault / "v2.base", {
        "filters": {"or": ['file.hasTag("stage")',
                           'file.inFolder("notes")']},
        "views": [{"type": "cards", "name": "卡"}]})
    r2 = basesio.eval_base(vault, "v2.base")
    assert r2["matched"] == ["notes/a.md", "notes/b.md"]
    basesio.write_base(vault / "v3.base", {
        "filters": {"not": 'file.inFolder("notes")'},
        "views": [{"type": "list", "name": "列"}]})
    assert basesio.eval_base(vault, "v3.base")["matched"] == ["c.md"]
    # 数值比较
    basesio.write_base(vault / "v4.base", {
        "filters": "score >= 3",
        "views": [{"type": "table", "name": "表"}]})
    assert basesio.eval_base(vault, "v4.base")["matched"] == \
        ["notes/a.md"]


def test_eval_unsupported_expression_named(vault):
    basesio.write_base(vault / "bad.base", {
        "filters": 'file.mtime > 1',
        "views": [{"type": "table", "name": "表"}]})
    with pytest.raises(basesio.BaseError) as exc:
        basesio.eval_base(vault, "bad.base")
    assert "file.mtime" in str(exc.value)


def test_eval_formulas_skipped_and_labeled(vault):
    basesio.write_base(vault / "f.base", {
        "filters": 'file.hasProperty("memory_id")',
        "formulas": {"double_score": "score * 2"},
        "views": [{"type": "table", "name": "表"}]})
    r = basesio.eval_base(vault, "f.base")
    assert r["skipped_formulas"] == ["double_score"]
    assert r["matched"] == ["notes/a.md", "notes/b.md"]
