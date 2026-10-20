"""全链与门禁（SC5 逐段确认、declaration 门、SC7、补正回路）。"""

from __future__ import annotations

from pathlib import Path

import yaml

from light_copyright import case as case_mod, release, render
from conftest import (drive_to_confirmed, drive_to_materials,
                      drive_to_packaged, run_cli, write_source)


def test_full_chain_to_packaged(tmp_path, case_dir, facts_file):
    src = write_source(tmp_path)
    drive_to_packaged(case_dir, facts_file, src, tmp_path)
    assert case_mod.status_of(case_dir) == "packaged"
    pkg = case_dir / "资料包"
    names = {p.name for p in pkg.iterdir()}
    assert "递交清单.md" in names
    assert "源程序鉴别材料.txt" in names
    assert "工具使用记录.jsonl" in names
    checklist = (pkg / "递交清单.md").read_text(encoding="utf-8")
    assert "迷你测试软件" in checklist
    assert "源程序量" in checklist and "行" in checklist


def test_doc_type_routing_headless_is_design_spec(tmp_path, case_dir,
                                                  facts_file):
    src = write_source(tmp_path)
    drive_to_materials(case_dir, facts_file, src)
    man = render.load_segments(case_dir)
    assert man["doc_type"] == "设计说明书"


def test_doc_type_routing_gui_is_manual(tmp_path, case_dir):
    import copy
    from conftest import FACTS
    facts = copy.deepcopy(FACTS)
    facts["software"]["kind"] = "gui"
    ff = case_dir.parent / "facts-gui.yaml"
    ff.write_text(yaml.safe_dump(facts, allow_unicode=True), encoding="utf-8")
    src = write_source(case_dir.parent / "srcgui")
    from conftest import drive_to_materials as drive
    drive(case_dir, ff, src)
    man = render.load_segments(case_dir)
    assert man["doc_type"] == "操作手册"


def test_segments_have_real_evidence(tmp_path, case_dir, facts_file):
    src = write_source(tmp_path)
    drive_to_materials(case_dir, facts_file, src)
    man = render.load_segments(case_dir)
    module_segs = [s for s in man["segments"]
                   if s["section"].startswith("模块：")]
    assert module_segs
    core = next(s for s in module_segs if "core.py" in s["section"])
    symbols = {e["symbol"] for e in core["evidence"]}
    assert {"clean", "total"} <= symbols


def test_unconfirmed_segment_blocks_render_doc(tmp_path, case_dir,
                                               facts_file):
    src = write_source(tmp_path)
    drive_to_materials(case_dir, facts_file, src)
    code, out = run_cli("render-doc", str(case_dir))
    assert code == 1 and "confirmed" in out


def test_segment_edit_invalidates_confirmation(tmp_path, case_dir,
                                              facts_file):
    src = write_source(tmp_path)
    drive_to_confirmed(case_dir, facts_file, src)
    man = render.load_segments(case_dir)
    seg = man["segments"][0]
    assert case_mod.confirmation_valid(case_dir, "segment", seg["seg_id"],
                                       seg["sha256"])
    edited = case_dir / "edited.md"
    edited.write_text("改写后的段落内容。", encoding="utf-8")
    assert run_cli("revise-segment", str(case_dir), "--seg", seg["seg_id"],
                   "--from", str(edited))[0] == 0
    man2 = render.load_segments(case_dir)
    seg2 = man2["segments"][0]
    assert not case_mod.confirmation_valid(case_dir, "segment",
                                           seg2["seg_id"], seg2["sha256"])


def test_declaration_gate_blocks_until_recorded_and_verified(
        tmp_path, case_dir, facts_file):
    src = write_source(tmp_path)
    drive_to_confirmed(case_dir, facts_file, src)
    gaps = release.declaration_gate(case_dir)
    assert gaps and "未落案" in gaps[0]
    code, out = run_cli("check", str(case_dir))
    assert code == 1 and "declaration" in out
    decl = tmp_path / "decl.txt"
    decl.write_text("用户自备原文（测试）。", encoding="utf-8")
    assert run_cli("declaration", str(case_dir), "record", "--file",
                   str(decl), "--origin", "测试渠道")[0] == 0
    gaps = release.declaration_gate(case_dir)
    assert any("逐字核对回执" in g for g in gaps)
    assert run_cli("declaration", str(case_dir), "verify")[0] == 0
    assert release.declaration_gate(case_dir) == []


def test_declaration_text_change_invalidates_receipt(tmp_path, case_dir,
                                                     facts_file):
    src = write_source(tmp_path)
    drive_to_packaged(case_dir, facts_file, src, tmp_path)
    text_p = release.declaration_text_path(case_dir)
    text_p.write_text("被篡改的文本。", encoding="utf-8")
    gaps = release.declaration_gate(case_dir)
    assert any("哈希不符" in g for g in gaps)


def test_claims_no_tool_drafting_contradiction_blocked(tmp_path, case_dir,
                                                       facts_file):
    src = write_source(tmp_path)
    drive_to_confirmed(case_dir, facts_file, src)
    decl = tmp_path / "decl.txt"
    decl.write_text("用户自备原文（测试）。", encoding="utf-8")
    run_cli("declaration", str(case_dir), "record", "--file", str(decl),
            "--origin", "测试渠道")
    code, out = run_cli("declaration", str(case_dir), "verify",
                        "--claims-no-tool-drafting")
    assert code == 1 and "HC-4" in out


def test_placeholder_in_segment_blocks_check(tmp_path, case_dir, facts_file):
    """HC-3 回归：段落混入 TODO 占位，逐段确认了也须被发布门拦下。"""
    src = write_source(tmp_path)
    drive_to_confirmed(case_dir, facts_file, src)
    man = render.load_segments(case_dir)
    seg = man["segments"][1]
    bad = case_dir / "bad.md"
    bad.write_text(render.segment_text(case_dir, seg) + "\nTODO 待补充。\n",
                   encoding="utf-8")
    run_cli("revise-segment", str(case_dir), "--seg", seg["seg_id"],
            "--from", str(bad))
    run_cli("confirm-segment", str(case_dir), "--seg", seg["seg_id"])
    run_cli("render-doc", str(case_dir))
    res = release.run_release_checks(case_dir)
    assert not res["ok"]
    assert any("占位" in g for g in res["gaps"])


def test_source_drift_blocks_check(tmp_path, case_dir, facts_file):
    src = write_source(tmp_path)
    drive_to_confirmed(case_dir, facts_file, src)
    (src / "app" / "core.py").write_text("# 冻结后改动\n", encoding="utf-8")
    res = release.run_release_checks(case_dir)
    assert not res["ok"]
    assert any("漂移" in g for g in res["gaps"])


def test_correction_loop_deadline(tmp_path, case_dir, facts_file):
    src = write_source(tmp_path)
    drive_to_packaged(case_dir, facts_file, src, tmp_path)
    code, out = run_cli("correct", str(case_dir), "--notice-date",
                        "2026-11-02", "--items", "说明书第 2 页页眉缺版本号")
    assert code == 0 and "2026-12-02" in out
    case = case_mod.load_case(case_dir)
    assert case["status"] == "correcting"
    assert case["correction"]["deadline"] == "2026-12-02"
    # 补正回路中可直接重新 check + package（事实/材料未变时）
    assert run_cli("package", str(case_dir))[0] == 0
    assert case_mod.status_of(case_dir) == "packaged"
    assert case_mod.load_case(case_dir)["correction"] is not None


def test_header_consistency_from_single_source(tmp_path, case_dir,
                                               facts_file):
    src = write_source(tmp_path)
    drive_to_confirmed(case_dir, facts_file, src)
    code, doc = release.load_manifests(case_dir)
    assert code["header"] == "迷你测试软件 V2.0"
    assert doc["header"] == "迷你测试软件 V2.0"
    text = (case_dir / "materials" / code["file"]).read_text(
        encoding="utf-8")
    assert "[页眉]迷你测试软件 V2.0" in text


def test_tool_use_log_append_only_records_chain(tmp_path, case_dir,
                                                facts_file):
    src = write_source(tmp_path)
    drive_to_packaged(case_dir, facts_file, src, tmp_path)
    rows = case_mod.tool_use_rows(case_dir)
    actions = {(r["actor"], r["action"]) for r in rows}
    assert ("tool", "freeze") in actions
    assert ("tool", "draft") in actions
    assert ("user", "confirm") in actions
    assert ("tool", "package") in actions


def test_screenshot_import_only_with_hash(tmp_path, case_dir, facts_file):
    src = write_source(tmp_path)
    drive_to_materials(case_dir, facts_file, src)
    img = tmp_path / "shot.png"
    img.write_bytes(b"\x89PNG-fake")
    row = release.import_screenshot(case_dir, img, "主界面（用户截取）")
    assert (case_dir / "screenshots" / "shot.png").exists()
    assert row["caption"] == "主界面（用户截取）"
