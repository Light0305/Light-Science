"""画像视图：只装处置与指针、可整删再生、自检咬无指针行；
立场视图按（项目，对象）键控分组不混答。"""

import pytest

from light_memory import bench
from light_memory import profile as prof
from light_memory import project as project_mod
from light_memory.supersede import apply_nominations


@pytest.fixture()
def world(tmp_path):
    base = tmp_path / "world"
    bench.build_mini_world(base)
    return base


def test_profile_build_and_check(world):
    a = world / "proj-a"
    res = prof.build_profile(a)
    from pathlib import Path
    assert Path(res["static"]).exists() and Path(res["dynamic"]).exists()
    assert prof.check_profile(a) == []
    static = Path(res["static"]).read_text(encoding="utf-8")
    # 只装处置与指针：每条内容行带回指
    for line in static.splitlines():
        if line.startswith("- "):
            assert "→" in line


def test_profile_regenerable_after_delete(world):
    a = world / "proj-a"
    prof.build_profile(a)
    static = a / "profile" / "profile-static.md"
    first = static.read_text(encoding="utf-8")
    static.unlink()
    assert prof.check_profile(a)  # 缺失被点名
    prof.build_profile(a)
    second = static.read_text(encoding="utf-8")
    body_first = [l for l in first.splitlines()
                  if not l.startswith("<!-- 生成于")]
    body_second = [l for l in second.splitlines()
                   if not l.startswith("<!-- 生成于")]
    assert body_first == body_second  # 同账本再生同内容（时间戳除外）


def test_profile_check_bites_pointerless_line(world):
    a = world / "proj-a"
    prof.build_profile(a)
    static = a / "profile" / "profile-static.md"
    with static.open("a", encoding="utf-8") as fh:
        fh.write("- 这是一条没有回指指针的结论性陈述\n")
    errs = prof.check_profile(a)
    assert any("无回指指针" in e for e in errs)


def test_profile_static_carries_decision_dispositions(mem_root):
    prov = {"source_package": "design", "source_artifact": "design.yaml",
            "source_anchor": "decision", "source_version": "1",
            "ingested_at": "2026-10-20T00:00:00+00:00"}
    from light_memory import registry
    pkg = project_mod.load_package(mem_root)
    registry.register_object(pkg, "design", "design-1", prov)
    project_mod.save_objects(mem_root, pkg["objects"])
    apply_nominations(mem_root, [{
        "verdict": "store", "nominator": "t", "provenance": prov,
        "fact": {"statement": "评估段数定为 10 段（用户已签）",
                 "fact_type": "decision", "object_id": "design:design-1",
                 "valid_at": "2026-01-10"}}])
    res = prof.build_profile(mem_root)
    assert res["decisions"] == 1
    assert prof.check_profile(mem_root) == []


def test_stance_view_separates_projects(world):
    a, b = world / "proj-a", world / "proj-b"
    view = prof.stance_view([("turkey-a", a), ("turkey-b", b)],
                            "method:tracker-threshold")
    pa = view["projects"]["turkey-a"]["facts"]
    pb = view["projects"]["turkey-b"]["facts"]
    assert any("顶视固定机位" in f["statement"] for f in pa)
    assert any("移动机位" in f["statement"] for f in pb)
    assert not any("移动机位" in f["statement"] for f in pa)
    text = prof.render_stance(view)
    assert "## 项目 turkey-a" in text and "## 项目 turkey-b" in text
