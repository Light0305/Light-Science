"""ai manifest 跨路线构建账隔离（user-delegated 主会话裁决
2026-10-21）回归覆盖。

裁决：redraw manifest 的内容（形状/文本/语义 ID）跨路线继承，
rounds/build 构建记录不跨后端继承，每条路线独立起账，
round_noop 只在本路线账内生效。复现规划期 P5 实测故障：ai
manifest 从已构建的 redraw manifest 整份派生时继承了 file_build
的 rounds 账，首轮 ai build 被 round_noop 误拦——修复后派生剥离
外来账并留痕（derived_from），首轮 build 放行；本路线账内的
round_noop 纪律不 relax。
"""
import pytest

from light_figure.aibuild import (
    AiError, ai_manifest_path, derive_ai_manifest,
    generate_build_scripts, install_ai_manifest, load_ai_manifest,
)
from light_figure.redraw import load_manifest as load_redraw_manifest
from light_figure.util import dump_json, sha256_file

from conftest import FIG_METHOD, method_manifest


def _pptx_flavored_source(root) -> dict:
    """powerpoint 路线已构建 manifest 的形态（带自家 rounds/build/
    reconciliation 账），作派生源。"""
    manifest = method_manifest()
    manifest["version"] = "1.1"
    manifest["backend"] = "powerpoint_file"
    manifest.pop("route")
    manifest["reference"]["sha256"] = sha256_file(
        root / "schematic" / "reference" / "fig-method.png")
    manifest["arrow_plan"] = [{
        "arrow_plan_id": "AP-1", "from": "input-frame",
        "to": "predictor", "fact": "帧流进入预测器",
    }]
    manifest["shapes"][2]["connect"]["arrow_plan_id"] = "AP-1"
    manifest["rounds"] = [{
        "round": 1, "at": "2026-10-21T00:00:00+00:00",
        "projection_hash": "f" * 64, "artifact_sha256": "e" * 64,
    }]
    manifest["build"] = {
        "builder": "light-figure pptx build (file layer)",
        "backend": "powerpoint_file",
        "powerpoint_verified": False,
        "artifact": "schematic/redraw/fig-method.pptx",
        "artifact_sha256": "e" * 64,
    }
    manifest["extracted_shapes_hash"] = "d" * 64
    manifest["reconciliation"] = {"ok": True, "diffs": [],
                                   "at": "2026-10-21T00:00:00+00:00"}
    manifest["status"] = "verified"
    return manifest


def test_derive_from_built_visio_manifest_unblocks_first_ai_build(
        produced_pkg):
    """P5 故障复现与修复：源 = produced 图包里已 build + extract
    过的 redraw manifest（rounds 1 轮、file_build 记录、对账 ok）。"""
    root = produced_pkg["root"]
    source_manifest = load_redraw_manifest(root, FIG_METHOD)
    assert source_manifest["route"] == "file_build"
    assert len(source_manifest["rounds"]) == 1
    assert source_manifest["reconciliation"]["ok"] is True

    source = root / "tmp-derive-visio.json"
    dump_json(source, source_manifest)
    manifest = install_ai_manifest(root, FIG_METHOD, source)

    # 内容继承：形状/面板/参考锚点与源逐项一致
    assert manifest["shapes"] == source_manifest["shapes"]
    assert manifest["panels"] == source_manifest["panels"]
    assert manifest["reference"] == source_manifest["reference"]
    # 构建账隔离：外来账剥离归零、本路线独立起账
    assert manifest["backend"] == "illustrator_extendscript"
    assert manifest["rounds"] == []
    assert manifest["build"] is None
    assert manifest["reconciliation"] is None
    assert manifest["extracted_shapes_hash"] is None
    assert manifest["status"] == "registered"  # 不是外来的 verified
    for key in ("route", "trace_layer", "label_check"):
        assert key not in manifest
    # 留痕：源路线、被剥账面、裁决出处齐
    trace = manifest["derived_from"]
    assert trace["source_route"] == "visio/file_build"
    assert trace["stripped_build_ledger"]["rounds"] == 1
    assert trace["stripped_build_ledger"]["build"]["route"] \
        == "file_build"
    assert trace["stripped_build_ledger"]["had_reconciliation"] is True
    assert "2026-10-21" in trace["ruling"]

    # 修复判据：首轮 ai build 不再被外来账的 round_noop 误拦
    out = generate_build_scripts(root, FIG_METHOD)
    assert out["illustrator_verified"] is False
    built = load_ai_manifest(root, FIG_METHOD)
    assert len(built["rounds"]) == 1  # 本路线自己的第一轮
    assert built["build"]["backend"] == "illustrator_extendscript"
    # 本路线账内纪律不 relax：同内容再 build 照旧被 round_noop 拦
    with pytest.raises(AiError) as exc:
        generate_build_scripts(root, FIG_METHOD)
    assert "round_noop" in str(exc.value)


def test_derive_from_pptx_manifest_strips_foreign_ledger(produced_pkg):
    root = produced_pkg["root"]
    source = root / "tmp-derive-pptx.json"
    dump_json(source, _pptx_flavored_source(root))
    manifest = install_ai_manifest(root, FIG_METHOD, source)
    assert manifest["backend"] == "illustrator_extendscript"
    assert manifest["rounds"] == []
    assert manifest["build"] is None
    assert manifest["reconciliation"] is None
    trace = manifest["derived_from"]
    assert trace["source_route"] == "powerpoint_file"
    assert trace["stripped_build_ledger"]["rounds"] == 1
    assert trace["stripped_build_ledger"]["build"]["backend"] \
        == "powerpoint_file"
    out = generate_build_scripts(root, FIG_METHOD)
    assert out["evidence_level"] == "script"


def test_native_ai_reinstall_preserves_own_ledger(produced_pkg):
    """自家 ai manifest 重登记不许被派生逻辑误剥（隔离只对外来账）。"""
    root = produced_pkg["root"]
    manifest = method_manifest()
    manifest["version"] = "1.1"
    manifest["backend"] = "illustrator_extendscript"
    manifest["reference"]["sha256"] = sha256_file(
        root / "schematic" / "reference" / "fig-method.png")
    manifest["arrow_plan"] = [{
        "arrow_plan_id": "AP-1", "from": "input-frame",
        "to": "predictor", "fact": "帧流进入预测器",
    }]
    manifest["shapes"][2]["connect"]["arrow_plan_id"] = "AP-1"
    source = root / "tmp-ai-native.json"
    dump_json(source, manifest)
    install_ai_manifest(root, FIG_METHOD, source)
    generate_build_scripts(root, FIG_METHOD)
    own = load_ai_manifest(root, FIG_METHOD)
    assert len(own["rounds"]) == 1 and own["build"] is not None

    again = install_ai_manifest(root, FIG_METHOD,
                                ai_manifest_path(root, FIG_METHOD))
    assert len(again["rounds"]) == 1          # 自家轮次账原样保留
    assert again["build"] is not None         # 自家构建记录原样保留
    assert again.get("derived_from") is None  # 无派生留痕


def test_derive_function_noop_for_native_manifest():
    native = {"fig_id": FIG_METHOD,
              "backend": "illustrator_extendscript",
              "rounds": [{"round": 1, "projection_hash": "a" * 64}],
              "build": {"backend": "illustrator_extendscript"}}
    out, trace = derive_ai_manifest(dict(native))
    assert trace is None
    assert out["rounds"] == native["rounds"]
    assert out["build"] == native["build"]
