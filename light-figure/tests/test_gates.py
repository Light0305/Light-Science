"""状态机：contracted 全门、缺口点名、Phase 2 深门接口停口。"""

import pytest

from light_figure.gates import GateError, advance, status_summary
from light_figure.project import load_package


def test_advance_blocked_names_gaps(pkg):
    result = advance(pkg["root"])
    assert result["advanced"] is False
    assert result["from"] == "intake" and result["to"] == "contracted"
    joined = "\n".join(result["gaps"])
    assert "contract.five_point_missing" in joined
    assert "后端未决定" in joined
    # 状态未被推进
    assert load_package(pkg["root"])["head"]["status"] == "intake"


def test_advance_to_contracted_syncs_figure_rows(filled_pkg):
    result = advance(filled_pkg["root"])
    assert result["advanced"] is True, result["gaps"]
    head = load_package(filled_pkg["root"])["head"]
    assert head["status"] == "contracted"
    assert head["status_history"][-1]["state"] == "contracted"
    rows = {r["fig_id"]: r for r in head["figures"]}
    assert all(r["stage"] == "contracted" for r in rows.values())
    assert rows["fig-data"]["backend"] == "python"  # 解析结果回填逐图行
    assert rows["fig-method"]["backend"] is None


def test_advance_beyond_contracted_stops_at_produced_gate(filled_pkg):
    advance(filled_pkg["root"])
    result = advance(filled_pkg["root"])
    assert result["advanced"] is False
    assert result["to"] == "produced"
    joined = "\n".join(result["gaps"])
    # Phase 2 深门逐项点名缺失产物，不许整体放行
    assert "缺绘图脚本" in joined
    assert "参考图未入包登记" in joined
    assert "重绘 manifest" in joined
    assert load_package(filled_pkg["root"])["head"]["status"] == "contracted"


def test_contracted_gate_requires_policy_snapshot(tmp_path):
    # 只有方法图、无政策快照的包：contracted 门须点名政策缺口
    from light_figure.intake import run_intake
    from light_figure.project import init_package, save_backend, save_contract
    from light_figure.util import dump_yaml, today
    from conftest import make_journal_contract, schematic_contract

    root = tmp_path / "figs"
    init_package(root, "No Policy")
    standalone = tmp_path / "s.yaml"
    dump_yaml(standalone, {"figures": [
        {"fig_id": "fig-method", "kind": "schematic"}]})
    journal = tmp_path / "j.yaml"
    dump_yaml(journal, make_journal_contract())
    run_intake(root, standalone=str(standalone),
               journal_contract_file=str(journal))
    save_contract(root, schematic_contract())
    save_backend(root, {"backend": "python", "decided_via": "explicit",
                        "decided_at": today(), "scope": "package",
                        "overrides": []})
    result = advance(root)
    assert result["advanced"] is False
    assert any("AI 政策快照" in g for g in result["gaps"])


def test_advance_missing_package_raises(tmp_path):
    with pytest.raises(GateError):
        advance(tmp_path / "nope")


def test_status_summary(filled_pkg):
    summary = status_summary(filled_pkg["root"])
    assert summary["status"] == "intake"
    assert len(summary["figures"]) == 2
    assert summary["validate"]["ok"] is True
