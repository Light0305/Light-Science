import json

import pytest

from light_leader import registry as reg

from conftest import make_memory


def test_registry_renders_grouped_view(tmp_path):
    make_memory(tmp_path, with_view=True, n_objects=3)
    path, view = reg.load_view(tmp_path)
    assert path.name == "registry-view.json"
    text = reg.render_view(view)
    assert "[paper] 3 个" in text
    assert "p0" in text and "状态 active" in text
    assert "abcdef012345" in text  # 当前版本指针以短哈希呈现


def test_registry_missing_view_named_with_pointer(tmp_path):
    with pytest.raises(reg.RegistryError) as ei:
        reg.load_view(tmp_path)
    msg = str(ei.value)
    assert "未找到 registry-view.json" in msg
    assert "light-memory registry" in msg  # 生成方式指针


def test_registry_view_absent_but_memory_present(tmp_path):
    make_memory(tmp_path, with_view=False)
    with pytest.raises(reg.RegistryError):
        reg.load_view(tmp_path)


def test_registry_kind_mismatch_rejected(tmp_path):
    mem = make_memory(tmp_path, with_view=True)
    p = mem / "registry-view.json"
    view = json.loads(p.read_text(encoding="utf-8"))
    view["kind"] = "something/else"
    p.write_text(json.dumps(view), encoding="utf-8")
    with pytest.raises(reg.RegistryError) as ei:
        reg.load_view(tmp_path)
    assert "种类不符" in str(ei.value)


def test_registry_version_mismatch_rejected(tmp_path):
    mem = make_memory(tmp_path, with_view=True)
    p = mem / "registry-view.json"
    view = json.loads(p.read_text(encoding="utf-8"))
    view["version"] = "2.0"
    p.write_text(json.dumps(view), encoding="utf-8")
    with pytest.raises(reg.RegistryError) as ei:
        reg.load_view(tmp_path)
    assert "版本不兼容" in str(ei.value)
