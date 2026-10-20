"""Phase 2 段门：drafted 齐备性、lock 收窄清单、audited STALE 拦、ready 底线层。"""

from pathlib import Path

from light_write.audit import run_audit
from light_write.gates import advance
from light_write.project import load_package
from light_write.util import dump_yaml
from conftest import (
    add_checklist, add_numbers, full_pkg, online_records_for,
    set_declarations, set_executor, write_full_sections,
)
from light_write.disclose import generate_disclosures


def test_drafted_gate_records_lock_narrowing(drafted_pkg):
    narrowing = drafted_pkg["narrowing"]
    assert narrowing["cited"] == ["ST001"]
    # 未被引条目只列清单不删：lock 仍是全集（ST001/ST002/ST003/ST005）
    assert set(narrowing["uncited"]) == {"ST002", "ST003", "ST005"}
    entries = load_package(drafted_pkg["root"])["lock"]["entries"]
    assert len(entries) == 4


def test_drafted_gate_blocks_unanchored_claim(pkg, record_path):
    full_pkg(pkg, record_path)
    root = pkg["root"]
    set_declarations(root)
    write_full_sections(root)
    add_numbers(root)
    add_checklist(root)
    advance(root)  # → outlined
    # 删掉 C2 的锚点句 → drafted 门点名 C2
    results = Path(root) / "sections" / "03-results.md"
    results.write_text("Results without the claim anchor.\n",
                       encoding="utf-8")
    result = advance(root)
    assert result["advanced"] is False
    assert any("C2" in g for g in result["gaps"])


def test_drafted_gate_blocks_missing_section_role(pkg, record_path):
    full_pkg(pkg, record_path)
    root = pkg["root"]
    set_declarations(root)
    write_full_sections(root)
    add_numbers(root)
    add_checklist(root)
    advance(root)
    (Path(root) / "sections" / "02-methods.md").write_text(
        "", encoding="utf-8")
    result = advance(root)
    assert result["advanced"] is False
    assert any("methods" in g for g in result["gaps"])


def test_audited_gate_blocks_stale_audit(drafted_pkg):
    root = drafted_pkg["root"]
    run_audit(root, online_records=online_records_for(root))
    intro = Path(root) / "sections" / "01-introduction.md"
    intro.write_text(intro.read_text(encoding="utf-8")
                     + "Post-audit edit.\n", encoding="utf-8")
    result = advance(root)
    assert result["advanced"] is False
    assert any("STALE" in g for g in result["gaps"])


def test_ready_gate_blocks_baseline_item_not_addressed(audited_pkg):
    root = audited_pkg["root"]
    pkg_data = load_package(root)
    checklist = pkg_data["checklist"]
    checklist["items"][0]["status"] = "missing"
    dump_yaml(root / "submission_checklist.yaml", checklist)
    result = advance(root)
    assert result["advanced"] is False
    assert any("底线层" in g for g in result["gaps"])


def test_ready_gate_blocks_contested_contract(pkg, record_path):
    # contested 包一路走到 audited 也须被 ready 门拦下（拍板⑥）
    full_pkg(pkg, record_path, contested_ids=("A03",))
    root = pkg["root"]
    set_declarations(root)
    from conftest import add_use_log

    add_use_log(root)
    write_full_sections(root)
    add_numbers(root)
    add_checklist(root)
    advance(root)  # outlined（contested 不拦本段）
    advance(root)  # drafted
    set_executor(root)
    generate_disclosures(root)
    report = run_audit(root, online_records=online_records_for(root))
    assert report["overall"] == "pass", report
    advance(root)  # audited
    result = advance(root)
    assert result["advanced"] is False
    assert any("contested" in g for g in result["gaps"])


def test_cli_audit_exit_codes(drafted_pkg, tmp_path):
    from light_write.cli import main
    from light_write.util import dump_json

    root = str(drafted_pkg["root"])
    assert main(["audit", root]) == 1  # 离线：门一 unverified → 非 pass
    records_path = tmp_path / "online.json"
    dump_json(records_path, online_records_for(drafted_pkg["root"]))
    assert main(["audit", root, "--online-records",
                 str(records_path)]) == 0
