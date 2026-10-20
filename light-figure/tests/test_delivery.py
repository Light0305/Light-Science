"""交付段（Phase 3）：delivery.yaml 生成、账行逐行复验、编号冻结
配合与解冻登记、audited→delivered 全门。"""

import pytest

from light_figure.audit import run_audit, set_review_disposition
from light_figure.delivery import (
    DeliveryError, generate_delivery, register_unfreeze,
    verify_provenance_rows,
)
from light_figure.gates import advance
from light_figure.project import load_package
from light_figure.util import load_structured, sha256_file

from conftest import FIG_DATA, FIG_METHOD


def _to_audited(root):
    result = advance(root)  # contracted → produced
    assert result["advanced"], result["gaps"]
    run_audit(root)
    for fig_id in (FIG_DATA, FIG_METHOD):
        record = load_structured(root / "audit" / f"{fig_id}.audit.json")
        for name, gate in record["gates"].items():
            if gate.get("applicable") and gate["verdict"] == \
                    "REVIEW_REQUIRED":
                set_review_disposition(root, fig_id, name,
                                       "已人工复核：容差内可接受")
    result = advance(root)  # produced → audited
    assert result["advanced"], result["gaps"]


def test_deliver_full_chain_to_delivered(produced_pkg):
    root = produced_pkg["root"]
    _to_audited(root)
    # 未生成 delivery.yaml 时 delivered 门点名拦下
    result = advance(root)
    assert result["advanced"] is False
    assert any("delivery.yaml" in g for g in result["gaps"])
    out = generate_delivery(root)
    assert out["numbering_frozen"] is True
    doc = load_structured(root / "exports" / "delivery.yaml")
    assert doc["kind"] == "light-figure/delivery"
    assert doc["version"] == 1 and doc["status"] == "current"
    assert doc["numbering"]["frozen"] is True
    rows = {r["fig_id"]: r for r in doc["figures"]}
    data_row = rows[FIG_DATA]
    assert data_row["files"][0]["path"] == f"exports/{FIG_DATA}.pdf"
    assert data_row["files"][0]["sha256"] == \
        sha256_file(root / "exports" / f"{FIG_DATA}.pdf")
    assert "caption_hash" in data_row  # 承接快照图注哈希回填位
    # （standalone 夹具无图注文本时为 None，交付门只验与快照一致）
    assert data_row["provenance"]["script_hash"]
    method_row = rows[FIG_METHOD]
    assert method_row["visio_verified"] is False  # 文件级路线如实标注
    assert method_row["ai_disclosure"]["reference_not_in_delivery"] is True
    assert method_row["provenance"]["ledger_ref"] == \
        f"provenance.yaml#{FIG_METHOD}"
    result = advance(root)  # audited → delivered
    assert result["advanced"], result["gaps"]
    pkg = load_package(root)
    assert pkg["head"]["status"] == "delivered"
    assert all(r["delivery_status"] == "delivered"
               for r in pkg["head"]["figures"])
    assert pkg["head"]["numbering_freeze"]["frozen"] is True
    assert pkg["head"]["numbering_changes"][0]["action"] == "freeze"


def test_deliver_requires_audited_stage(produced_pkg):
    root = produced_pkg["root"]
    advance(root)  # contracted → produced（未审计）
    with pytest.raises(DeliveryError) as exc:
        generate_delivery(root)
    assert any("audited" in g for g in exc.value.gaps)


def test_provenance_tamper_blocks_delivery(produced_pkg):
    root = produced_pkg["root"]
    _to_audited(root)
    script = root / "data" / "scripts" / f"{FIG_DATA}.py"
    with script.open("a", encoding="utf-8") as fh:
        fh.write("\n# tampered after produce\n")
    gaps = verify_provenance_rows(root, load_package(root))
    assert any("脚本哈希" in g for g in gaps)
    with pytest.raises(DeliveryError):
        generate_delivery(root)


def test_frozen_change_requires_unfreeze(produced_pkg):
    root = produced_pkg["root"]
    _to_audited(root)
    generate_delivery(root)
    result = advance(root)
    assert result["advanced"], result["gaps"]
    # 冻结后改交付物：重新交付被拒，须先解冻登记
    vsdx = root / "schematic" / "redraw" / f"{FIG_METHOD}.vsdx"
    original = vsdx.read_bytes()
    with vsdx.open("ab") as fh:
        fh.write(b"tamper")
    with pytest.raises(DeliveryError) as exc:
        generate_delivery(root)
    assert any("解冻" in g for g in exc.value.gaps)
    with pytest.raises(DeliveryError):
        register_unfreeze(root, "")  # 无理由不许解冻
    out = register_unfreeze(root, "演示后修正一处标签错字")
    assert out["unfrozen"] is True and out["delivery_superseded"] is True
    doc = load_structured(root / "exports" / "delivery.yaml")
    assert doc["status"] == "superseded"
    # 还原成品（模拟修正后重建产物与账面一致）后重新交付：version 递增
    vsdx.write_bytes(original)
    from light_figure.audit import run_audit as _ra
    _ra(root)  # 篡改件重跑审计会留 STALE 痕迹，恢复后须重跑
    out = generate_delivery(root)
    assert out["version"] == 2
    pkg = load_package(root)
    actions = [c["action"] for c in pkg["head"]["numbering_changes"]]
    assert actions == ["freeze", "unfreeze", "freeze"]
