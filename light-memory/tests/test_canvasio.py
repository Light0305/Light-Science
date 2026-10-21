"""canvasio：结构校验、坐标保全往返、未知属性保留。"""

import json

import pytest

from light_memory import canvasio


def _nodes(*files):
    return [{"type": "file", "file": f} for f in files]


def _edges(*pairs):
    return [{"from_key": ("file", a), "to_key": ("file", b),
             "label": label} for a, b, label in pairs]


def test_validate_catches_bad_canvas():
    gaps = canvasio.validate_canvas({
        "nodes": [{"id": "n1", "type": "file", "x": 0, "y": 0,
                   "width": 1, "height": 1},
                  {"id": "n1", "type": "text", "text": "t",
                   "x": 0, "y": 0, "width": 1, "height": 1}],
        "edges": [{"id": "e1", "fromNode": "n1", "toNode": "ghost"}],
    })
    text = "；".join(gaps)
    assert "缺 file 路径" in text and "重复" in text
    assert "不存在的节点" in text


def test_build_then_user_move_then_rebuild_preserves(tmp_path):
    p = tmp_path / "graph.canvas"
    r1 = canvasio.build_canvas_file(
        p, _nodes("a.md", "b.md", "c.md"),
        _edges(("a.md", "b.md", "supports")))
    assert r1["nodes"] == 3 and r1["edges"] == 1
    data = json.loads(p.read_text(encoding="utf-8"))
    by_file = {n["file"]: n for n in data["nodes"]}
    assert by_file["a.md"]["x"] != by_file["b.md"]["x"] or \
        by_file["a.md"]["y"] != by_file["b.md"]["y"]
    # 用户在 Obsidian 里拖动 a 并给它上色
    by_file["a.md"]["x"] = 999
    by_file["a.md"]["y"] = 777
    by_file["a.md"]["color"] = "1"
    p.write_text(json.dumps(data, ensure_ascii=False),
                 encoding="utf-8")
    # 重生成：c 撤、d 新增、边换向
    r2 = canvasio.build_canvas_file(
        p, _nodes("a.md", "b.md", "d.md"),
        _edges(("b.md", "a.md", "derives")))
    data2 = json.loads(p.read_text(encoding="utf-8"))
    by_file2 = {n["file"]: n for n in data2["nodes"]}
    assert by_file2["a.md"]["x"] == 999
    assert by_file2["a.md"]["y"] == 777
    assert by_file2["a.md"]["color"] == "1"  # 附加属性原样保留
    assert "c.md" not in by_file2 and "d.md" in by_file2
    assert r2["nodes_kept"] == 2 and r2["nodes_added"] == 1
    assert r2["nodes_removed"] == 1
    assert len(data2["edges"]) == 1
    assert data2["edges"][0]["label"] == "derives"


def test_roundtrip_untouched_props(tmp_path):
    p = tmp_path / "x.canvas"
    original = {
        "nodes": [{"id": "t1", "type": "text", "text": "说明",
                   "x": 5, "y": 6, "width": 100, "height": 50,
                   "color": "3"}],
        "edges": [],
        "customTopLevel": {"keep": True},
    }
    p.write_text(json.dumps(original, ensure_ascii=False),
                 encoding="utf-8")
    loaded = canvasio.load_canvas(p)
    canvasio.save_canvas(p, loaded)
    again = json.loads(p.read_text(encoding="utf-8"))
    assert again["nodes"] == original["nodes"]


def test_load_missing_and_broken(tmp_path):
    with pytest.raises(canvasio.CanvasError):
        canvasio.load_canvas(tmp_path / "none.canvas")
    bad = tmp_path / "bad.canvas"
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(canvasio.CanvasError):
        canvasio.load_canvas(bad)
