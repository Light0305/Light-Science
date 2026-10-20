"""CLI 端到端：init / intake / validate / advance / status。"""

from light_analysis.cli import main


def test_cli_init_creates_skeleton(tmp_path):
    root = tmp_path / "ana"
    assert main(["init", str(root), "--title", "演示分析"]) == 0
    for name in ("analysis.yaml", "verdicts.jsonl", "spec_ledger.yaml",
                 "spec_results.jsonl", "conclusions.yaml",
                 "exploratory/exploratory.yaml", "ANALYSIS_REPORT.md"):
        assert (root / name).exists(), name


def test_cli_init_refuses_overwrite(tmp_path):
    root = tmp_path / "ana"
    assert main(["init", str(root)]) == 0
    assert main(["init", str(root)]) == 1


def test_cli_intake_and_status(tmp_path, upstream, capsys):
    card_path, reg_path, dc_path = upstream
    root = tmp_path / "ana"
    assert main(["init", str(root)]) == 0
    assert main(["intake", str(root),
                 "--execution-card", str(card_path),
                 "--registry", str(reg_path),
                 "--design-card", str(dc_path)]) == 0
    out = capsys.readouterr().out
    assert "可判 2" in out and "untested 预登记 3" in out
    assert (root / "audit.json").exists() and (root / "audit.md").exists()
    assert main(["status", str(root)]) == 0
    out = capsys.readouterr().out
    assert "状态：intake" in out and "untested=3" in out


def test_cli_validate_fresh_and_intaken(tmp_path, upstream):
    card_path, reg_path, dc_path = upstream
    root = tmp_path / "ana"
    main(["init", str(root)])
    assert main(["validate", str(root)]) == 0
    main(["intake", str(root), "--execution-card", str(card_path),
          "--registry", str(reg_path), "--design-card", str(dc_path)])
    assert main(["validate", str(root)]) == 0


def test_cli_advance_blocked_reports_gaps(tmp_path, capsys):
    root = tmp_path / "ana"
    main(["init", str(root)])
    assert main(["advance", str(root)]) == 1
    err = capsys.readouterr().err
    assert "逐项缺口" in err
