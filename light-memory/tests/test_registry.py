"""对象注册：合并语义、前向登记转正、registry-view 导出。"""

from light_memory import project as project_mod, registry, schema


def _prov(pkg="idea"):
    return schema.make_provenance(pkg, "src", "a", "hash-1")


def _pkg(mem_root):
    return project_mod.load_package(mem_root)


def test_register_merges_same_object(mem_root):
    pkg = _pkg(mem_root)
    registry.register_object(pkg, "paper", "p1", _prov(), title="甲",
                             current_version="v1")
    row = registry.register_object(pkg, "paper", "p1", _prov(),
                                   current_version="v2")
    assert len(pkg["objects"]) == 1
    assert row["current_version"] == "v2"
    assert row["title"] == "甲"  # 后来的空题名不覆盖已有


def test_reference_then_register_promotes(mem_root):
    pkg = _pkg(mem_root)
    ref = registry.reference_object(pkg, "execution", "exec-9", _prov())
    assert ref["status"] == "referenced"
    row = registry.register_object(pkg, "execution", "exec-9", _prov(),
                                   current_version="h")
    assert row["status"] == "active"
    assert len(pkg["objects"]) == 1


def test_registry_view_groups_by_type(mem_root):
    pkg = _pkg(mem_root)
    registry.register_object(pkg, "paper", "p1", _prov())
    registry.register_object(pkg, "claim", "C1", _prov(pkg="analysis"))
    project_mod.save_objects(mem_root, pkg["objects"])
    view = registry.export_registry_view(mem_root, pkg)
    assert view["kind"] == "light-memory/registry-view"
    assert view["counts"] == {"claim": 1, "paper": 1}
    assert view["objects_by_type"]["paper"][0]["object_id"] == "paper:p1"
    assert (mem_root / "registry-view.json").exists()
