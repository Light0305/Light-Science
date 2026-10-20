"""v1.1 manifest 三件（FIG-D04/05/06）：User.* 语义 ID 钉扎、
renderer-effective-fields 声明一致性、arrow_plan 绑定与
round_noop 无效轮次门。"""

import re
import zipfile

import pytest

from light_figure.redraw import (
    RedrawError, build_vsdx, extract_and_reconcile, extract_shapes,
    validate_manifest,
)
from light_figure.util import dump_json, load_structured
from conftest import FIG_METHOD, method_manifest


def test_user_semantic_ids_written_and_reconciled(produced_pkg):
    root = produced_pkg["root"]
    vsdx = root / "schematic" / "redraw" / f"{FIG_METHOD}.vsdx"
    shapes = extract_shapes(vsdx)
    assert shapes, "成品应有形状"
    for shape in shapes:
        assert shape["user_semantic_id"] == shape["shape_id"]
    manifest = load_structured(
        root / "schematic" / "redraw" / f"{FIG_METHOD}.manifest.json")
    assert manifest["reconciliation"]["ok"] is True
    assert manifest["rounds"] and \
        manifest["rounds"][0]["projection_hash"]


def test_user_section_tamper_detected(produced_pkg, tmp_path):
    root = produced_pkg["root"]
    vsdx = root / "schematic" / "redraw" / f"{FIG_METHOD}.vsdx"
    with zipfile.ZipFile(vsdx) as zf:
        parts = {n: zf.read(n) for n in zf.namelist()}
    page = parts["visio/pages/page1.xml"].decode("utf-8")
    page = page.replace('V="input-frame"', 'V="forged-id"', 1)
    parts["visio/pages/page1.xml"] = page.encode("utf-8")
    with zipfile.ZipFile(vsdx, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in parts.items():
            zf.writestr(name, data)
    outcome = extract_and_reconcile(root, FIG_METHOD)
    assert outcome["ok"] is False
    assert any("SemanticId" in d for d in outcome["diffs"])


def test_effective_fields_declared_but_unconsumed_rejected():
    manifest = method_manifest()
    manifest["renderer_effective_fields"] = [
        {"field": "style.opacity", "effective": True}]
    gaps = validate_manifest(manifest)
    assert any("style.opacity" in g and "不消费" in g for g in gaps)


def test_effective_fields_shape_use_undeclared_rejected():
    manifest = method_manifest()
    manifest["renderer_effective_fields"] = [
        {"field": "text", "effective": False}]
    gaps = validate_manifest(manifest)
    assert any("text" in g and "未把它声明为生效" in g for g in gaps)


def test_effective_fields_shape_uses_unknown_field_rejected():
    manifest = method_manifest()
    manifest["shapes"][0]["style"]["opacity"] = 0.5
    gaps = validate_manifest(manifest)
    assert any("style.opacity" in g for g in gaps)


def _strict_manifest():
    manifest = method_manifest()
    manifest["version"] = "1.1"
    manifest["arrow_plan"] = [{
        "arrow_plan_id": "AP-1", "from": "input-frame",
        "to": "predictor", "fact": "参考图中输入框到预测框的箭头",
    }]
    return manifest


def test_arrow_plan_strict_requires_binding():
    manifest = _strict_manifest()
    # conftest 形态的 connect 未带 arrow_plan_id → 严格模式必拦
    gaps = validate_manifest(manifest)
    assert any("arrow_plan_id" in g for g in gaps)


def test_arrow_plan_strict_binding_ok():
    manifest = _strict_manifest()
    manifest["shapes"][2]["connect"]["arrow_plan_id"] = "AP-1"
    gaps = validate_manifest(manifest)
    assert not any("arrow_plan" in g for g in gaps)


def test_arrow_plan_endpoint_mismatch_rejected():
    manifest = _strict_manifest()
    manifest["shapes"][2]["connect"]["arrow_plan_id"] = "AP-1"
    manifest["arrow_plan"][0]["to"] = "input-label"
    gaps = validate_manifest(manifest)
    assert any("不一致" in g and "AP-1" in g for g in gaps)


def test_arrow_plan_legacy_manifest_compatible():
    manifest = method_manifest()  # version 1.0、无 arrow_plan 键
    gaps = validate_manifest(manifest)
    assert not any("arrow_plan" in g for g in gaps)


def test_round_noop_gate_blocks_metadata_only_round(produced_pkg):
    root = produced_pkg["root"]
    # produced 流程已 build 一轮且内容未变 → 再 build 必被 noop 门拦
    with pytest.raises(RedrawError) as excinfo:
        build_vsdx(root, FIG_METHOD)
    assert any("round_noop" in g for g in excinfo.value.gaps)
    # 实质改动（挪一个形状）后放行且轮次账增行
    mpath = root / "schematic" / "redraw" / f"{FIG_METHOD}.manifest.json"
    manifest = load_structured(mpath)
    manifest["shapes"][0]["box_local"] = [0.12, 0.1, 0.8, 0.6]
    dump_json(mpath, manifest)
    build_vsdx(root, FIG_METHOD)
    manifest = load_structured(mpath)
    assert len(manifest["rounds"]) == 2
